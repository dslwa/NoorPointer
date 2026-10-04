import asyncio

import httpx
import pytest

from app.config import Settings
from app.detectors import build_detectors
from app.schemas import ScanRequest


async def test_configured_guard_concurrency_bounds_actual_ollama_calls(monkeypatch):
    monkeypatch.setenv("ENABLED_CHECKS", "content_safety")
    monkeypatch.setenv("GUARD_CONCURRENCY", "1")
    active, peak = 0, 0

    async def respond(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(.02)
            return httpx.Response(200, json={"message": {"content": "safe"}})
        finally:
            active -= 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        detector = build_detectors(Settings.from_env(), client)["content_safety"]
        results = await asyncio.gather(*(detector.check(ScanRequest(text="Hello", timeout_ms=1000)) for _ in range(3)))
    assert peak == 1 and active == 0
    assert all(r.status == "ok" and not r.flagged for r in results)


@pytest.mark.parametrize("value", ["0", "17", "-1"])
async def test_invalid_concurrency_fails_at_startup(monkeypatch, value):
    monkeypatch.setenv("ENABLED_CHECKS", "content_safety")
    monkeypatch.setenv("GUARD_CONCURRENCY", value)
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="GUARD_CONCURRENCY"):
            build_detectors(Settings.from_env(), client)
