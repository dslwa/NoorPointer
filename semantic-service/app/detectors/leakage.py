import re

from app.detectors.base import Detector
from app.schemas import CheckResult, ScanRequest

WORD = re.compile(r"\w+")


def _words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def system_prompt_overlap(system_prompt: str, output: str, n: int) -> float:
    """Fraction of the system prompt's word n-grams that appear in the output."""
    sp_words = _words(system_prompt)
    out_words = _words(output)
    if not sp_words:
        return 0.0
    if len(sp_words) < n:  # very short system prompt: require it verbatim
        joined = " ".join(sp_words)
        return 1.0 if joined in " ".join(out_words) else 0.0
    sp_grams = _ngrams(sp_words, n)
    return len(sp_grams & _ngrams(out_words, n)) / len(sp_grams)


class LeakageDetector(Detector):
    """Detects a model response leaking the system prompt or planted canary tokens."""

    name = "leakage"

    def __init__(self) -> None:
        super().__init__()

    async def check(self, req: ScanRequest) -> CheckResult:
        if req.direction != "output":
            return self.skipped("leakage applies to model outputs only")
        ctx, cfg = req.context, req.config.leakage
        if not ctx.system_prompt and not ctx.canaries:
            return self.skipped("no system_prompt or canaries in context")
        lowered = req.text.lower()
        canary_hits = sum(1 for c in ctx.canaries if c and c.lower() in lowered)
        overlap = system_prompt_overlap(ctx.system_prompt, req.text, cfg.ngram) if ctx.system_prompt else 0.0
        return CheckResult(
            check=self.name,
            status="ok",
            flagged=canary_hits > 0 or overlap >= cfg.threshold,
            score=1.0 if canary_hits else round(overlap, 4),
            details={"canary_hits": canary_hits, "system_prompt_overlap": round(overlap, 4)},
        )
