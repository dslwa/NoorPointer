import asyncio
import re
import time

import httpx

from app.detectors.base import CostModel, Detector, Rejected
from app.schemas import CheckResult, ScanRequest

HAZARDS = {
    "S1": "Violent Crimes",
    "S2": "Non-Violent Crimes",
    "S3": "Sex-Related Crimes",
    "S4": "Child Sexual Exploitation",
    "S5": "Defamation",
    "S6": "Specialized Advice",
    "S7": "Privacy",
    "S8": "Intellectual Property",
    "S9": "Indiscriminate Weapons",
    "S10": "Hate",
    "S11": "Suicide & Self-Harm",
    "S12": "Sexual Content",
    "S13": "Elections",
    "S14": "Code Interpreter Abuse",
}


HAZARD_CODE = re.compile(r"S\d{1,2}")
# Small enough that one call (always attempted) stays bounded even for the densest text, ~4 tokens per char.
CHUNK_CHARS = 2000
CHUNK_OVERLAP = 200  # so content split across a chunk boundary is still seen whole
PROMPT_CONTEXT_CHARS = 1000
# Truncation is made impossible by construction rather than detected: Llama 3's byte-level tokenizer needs at
# most 4 tokens per character (one per UTF-8 byte), so the worst case is 4 * (2000 + 1000) tokens plus the
# Llama Guard template (~600) = 12,600 < 16,384. (Ollama silently drops what doesn't fit, and its
# prompt_eval_count can't be trusted to show it: cached prompt prefixes aren't counted.) The cost is KV-cache
# memory in Ollama, ~0.5 GB per parallel slot for llama-guard3:1b.
NUM_CTX = 16_384
# Lines that would read as a new conversation turn or a template marker in Llama Guard's prompt. The model
# rates the *last* turn, so text ending in a fake benign "User:" turn could steer it to "safe".
ROLE_LABEL = re.compile(r"(?im)^(\s*)(user|agent|assistant|system)(\s*):")
TEMPLATE_MARKER = re.compile(r"(?i)(BEGIN|END)(\s+)(CONVERSATION|UNSAFE CONTENT CATEGORIES)")


def neutralize(text: str) -> str:
    """Content can't open a new turn, close the conversation, or inject special tokens."""
    text = "\n".join(text.splitlines())  # \r, \x0b, \x0c, \x85, \u2028, \u2029 all start a line too
    text = text.replace("<|", "< |").replace("|>", "| >")  # <|eot_id|>, <|start_header_id|>, ...
    text = ROLE_LABEL.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)} -", text)
    return TEMPLATE_MARKER.sub(lambda m: f"{m.group(1)}_{m.group(2)}{m.group(3)}", text)
# One check never queues more than this many Llama Guard calls in front of other requests (~43k chars);
# longer text is rejected (always blocked by the gateway, never failed open).
MAX_CHUNKS = 24
MAX_SPLIT_DEPTH = 2
# Ollama unloads an idle model after 5 minutes; reloading llama-guard3:1b on CPU took 4.4 s, far past any check
# budget. -1 keeps it loaded while Ollama runs (about 1.6 GB of memory).
KEEP_ALIVE = -1
OLLAMA_CONCURRENCY = 4  # Llama Guard calls in flight per service; more just queue inside Ollama


def _size(text: str) -> int:
    return len(text.encode("utf-8", "replace"))


def chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    step = CHUNK_CHARS - CHUNK_OVERLAP
    return [text[i : i + CHUNK_CHARS] for i in range(0, len(text) - CHUNK_OVERLAP, step)]


class _Truncated(Exception):
    pass


class _CallPlan:
    """The Llama Guard calls of one check share its budget: every call after the first (further chunks, or
    halves of a split) must fit what is left at the rate this input is actually costing, or the check is
    Rejected before its timeout fires."""

    def __init__(self, cost: CostModel, deadline: float, what: str) -> None:
        self.cost, self.deadline, self.what = cost, deadline, what
        self.started, self.done_chars = time.monotonic(), 0

    def before_call(self, chars: int) -> None:
        if self.done_chars:
            run_rate = (time.monotonic() - self.started) / self.done_chars
            self.cost.refuse_next(chars, self.deadline, self.what, run_rate)

    def after_call(self, chars: int) -> None:
        self.done_chars += chars


def parse_guard_output(raw: str) -> tuple[bool, list[str]]:
    """Llama Guard replies 'safe' or 'unsafe\\nS1,S10'. Anything else (empty, a refusal, the wrong model)
    raises, so the engine reports STATUS_ERROR and the gateway applies on_semantic_timeout instead of 'safe'."""
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    verdict = lines[0].lower() if lines else ""
    if verdict == "safe" and len(lines) == 1:
        return False, []
    if verdict != "unsafe":
        raise ValueError(f"unrecognized Llama Guard output: {raw[:80]!r}")
    codes = [code.strip().upper() for code in lines[1].split(",")] if len(lines) > 1 else []
    return True, [code for code in codes if HAZARD_CODE.fullmatch(code)]


class ContentSafetyDetector(Detector):
    """Llama Guard 3 served by Ollama."""

    name = "content_safety"

    def __init__(self, client: httpx.AsyncClient, ollama_url: str, model: str,
                 concurrency: int = OLLAMA_CONCURRENCY) -> None:
        super().__init__()
        if not 1 <= concurrency <= 16:
            raise ValueError("GUARD_CONCURRENCY must be between 1 and 16")
        self.client = client
        self.url = ollama_url
        self.model = model
        self.concurrency = concurrency
        self.slots = asyncio.Semaphore(concurrency)
        # seconds per UTF-8 byte reviewed (bytes track tokens: dense CJK/emoji text is up to 4 bytes and 4
        # tokens per character); the first call may include loading the model
        self.cost = CostModel(min_units=500, skip_first=1)

    def _load(self) -> None:
        tags = httpx.get(f"{self.url}/api/tags", timeout=5).json()
        names = {m["name"] for m in tags.get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            raise RuntimeError(f"model {self.model} not pulled in Ollama (run: ollama pull {self.model})")
        # Load the model into Ollama now, so the first real check doesn't pay for it.
        httpx.post(f"{self.url}/api/chat", timeout=120, json={
            "model": self.model, "messages": [{"role": "user", "content": "warm up"}], "stream": False,
            "keep_alive": KEEP_ALIVE, "options": {"temperature": 0, "num_ctx": NUM_CTX}}).raise_for_status()

    async def _classify(self, text: str, prompt: str | None) -> tuple[bool, list[str]]:
        if prompt is None:
            messages = [{"role": "user", "content": neutralize(text)}]
        else:
            messages = [{"role": "user", "content": neutralize(prompt)},
                        {"role": "assistant", "content": neutralize(text)}]
        async with self.slots:
            call_started = time.monotonic()
            resp = await self.client.post(
                f"{self.url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False, "keep_alive": KEEP_ALIVE,
                      "options": {"temperature": 0, "num_ctx": NUM_CTX}},
            )
            self.cost.observe(_size(text), time.monotonic() - call_started)
        resp.raise_for_status()
        body = resp.json()
        # Defence in depth (sizes above make this unreachable): a prompt that filled the context was cut.
        if body.get("prompt_eval_count", 0) >= NUM_CTX * 0.95:
            raise _Truncated(f"{body['prompt_eval_count']} tokens, num_ctx {NUM_CTX}")
        try:
            return parse_guard_output(body["message"]["content"])
        except ValueError as exc:
            # the text under review can steer the guard model's answer: an unusable verdict is the attacker's
            # doing as much as a failure, so it must block rather than fail open
            raise Rejected(str(exc)) from exc

    async def _classify_fitting(self, text: str, prompt: str | None, plan: "_CallPlan",
                                depth: int = 0) -> tuple[bool, list[str]]:
        """Classify, splitting the text in half (with overlap) when Ollama reports it didn't fit."""
        plan.before_call(_size(text))
        try:
            result = await self._classify(text, prompt)
            plan.after_call(_size(text))
            return result
        except _Truncated as exc:
            plan.after_call(_size(text))
            if depth >= MAX_SPLIT_DEPTH or len(text) <= 2 * CHUNK_OVERLAP:
                # dense text is attacker-shapeable: refusing it must block, not fail open
                raise Rejected(f"Llama Guard input truncated even after splitting ({exc})") from exc
        mid = len(text) // 2
        halves = (text[: mid + CHUNK_OVERLAP // 2], text[mid - CHUNK_OVERLAP // 2 :])
        verdicts = [await self._classify_fitting(h, prompt, plan, depth + 1) for h in halves]
        return any(u for u, _ in verdicts), [c for _, cs in verdicts for c in cs]

    async def check(self, req: ScanRequest) -> CheckResult:
        # Output direction: rate the reply in the context of the user's prompt (its tail is enough context).
        prompt = None if req.direction == "input" else (req.context.prompt or "")[-PROMPT_CONTEXT_CHARS:]
        chunks = chunk_text(req.text)
        if len(chunks) > MAX_CHUNKS:
            raise Rejected(f"text too long for content safety ({len(req.text)} chars, {len(chunks)} chunks; "
                               f"limit {MAX_CHUNKS})")
        # One chunk at a time: a check holds at most one Ollama slot, so the per-request gate in Analyze
        # really bounds how much of Ollama one request can take.
        budget = req.timeout_ms / 1000
        plan = _CallPlan(self.cost, time.monotonic() + budget, f"content-safety scan of {len(chunks)} chunks")
        # Even a single chunk is checked: its cost depends on how dense the attacker made it, not on load.
        self.cost.refuse_if_too_big(sum(map(_size, chunks)), budget, plan.deadline, True, plan.what)
        verdicts = [await self._classify_fitting(chunk, prompt, plan) for chunk in chunks]
        unsafe = any(u for u, _ in verdicts)
        codes = list(dict.fromkeys(c for _, cs in verdicts for c in cs))
        wanted = req.config.content_safety.categories
        matched = [c for c in codes if wanted is None or c in wanted]
        return CheckResult(
            check=self.name,
            status="ok",
            # unsafe without a category code can't be filtered, so it always counts
            flagged=unsafe and (wanted is None or not codes or bool(matched)),
            score=1.0 if unsafe else 0.0,
            details={
                "unsafe": unsafe,
                "categories": [{"code": c, "name": HAZARDS.get(c, "Unknown")} for c in codes],
                "matched": matched,
                "chunks": len(verdicts),
                "model": self.model,
            },
        )
