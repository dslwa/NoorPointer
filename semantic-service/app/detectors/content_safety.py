import re

import httpx

from app.detectors.base import Detector
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

    def __init__(self, client: httpx.AsyncClient, ollama_url: str, model: str) -> None:
        super().__init__()
        self.client = client
        self.url = ollama_url
        self.model = model

    def _load(self) -> None:
        tags = httpx.get(f"{self.url}/api/tags", timeout=5).json()
        names = {m["name"] for m in tags.get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            raise RuntimeError(f"model {self.model} not pulled in Ollama (run: ollama pull {self.model})")

    async def check(self, req: ScanRequest) -> CheckResult:
        if req.direction == "input":
            messages = [{"role": "user", "content": req.text}]
        else:
            messages = [
                {"role": "user", "content": req.context.prompt or ""},
                {"role": "assistant", "content": req.text},
            ]
        resp = await self.client.post(
            f"{self.url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False, "options": {"temperature": 0}},
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"]
        unsafe, codes = parse_guard_output(raw)
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
                "model": self.model,
            },
        )
