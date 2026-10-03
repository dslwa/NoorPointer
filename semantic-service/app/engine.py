import asyncio
import logging
import time

from prometheus_client import Counter, Histogram

from app.detectors.base import Detector
from app.schemas import CheckResult, ScanRequest, ScanResponse

log = logging.getLogger(__name__)

CHECK_LATENCY = Histogram(
    "semantic_check_latency_seconds",
    "Latency of a single semantic check",
    ["check", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5),
)
CHECK_FLAGGED = Counter("semantic_check_flagged_total", "Checks that flagged content", ["check", "direction"])


async def run_check(name: str, detector: Detector | None, req: ScanRequest) -> CheckResult:
    start = time.perf_counter()
    if detector is None:
        result = CheckResult(check=name, status="error", error="check not enabled in this service")
    elif not detector.ready:
        result = CheckResult(check=name, status="error", error=f"detector {detector.state}")
    else:
        try:
            result = await asyncio.wait_for(detector.check(req), timeout=req.timeout_ms / 1000)
        except TimeoutError:
            result = CheckResult(check=name, status="timeout", error=f"exceeded {req.timeout_ms} ms")
        except Exception as exc:
            log.exception("check %s failed", name)
            result = CheckResult(check=name, status="error", error=f"{type(exc).__name__}: {exc}")
    elapsed = time.perf_counter() - start
    result.latency_ms = round(elapsed * 1000, 2)
    CHECK_LATENCY.labels(name, result.status).observe(elapsed)
    if result.flagged:
        CHECK_FLAGGED.labels(name, req.direction).inc()
    return result


async def run_scan(req: ScanRequest, detectors: dict[str, Detector]) -> ScanResponse:
    start = time.perf_counter()
    names = list(dict.fromkeys(req.checks)) if req.checks is not None else list(detectors)
    results = await asyncio.gather(*(run_check(n, detectors.get(n), req) for n in names))
    redacted = None
    for r in results:
        if r.check == "pii_ner":
            redacted = r.details.pop("redacted_text", None)
    return ScanResponse(
        request_id=req.request_id,
        flagged=any(r.flagged for r in results),
        results=list(results),
        redacted_text=redacted,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
    )
