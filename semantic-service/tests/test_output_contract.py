"""OUTPUT wire contract. Real gRPC, deterministic detector/LLM substitutes; no model downloads."""

import asyncio
import base64
import json
from collections import Counter
from contextlib import asynccontextmanager

import grpc
import httpx
import pytest
from semantic.v1 import semantic_pb2 as pb
from semantic.v1 import semantic_pb2_grpc

from app.config import Settings
from app.detectors.base import Detector, Rejected
from app.detectors.content_safety import ContentSafetyDetector
from app.detectors.leakage import LeakageDetector
from app.grpc_server import start_grpc_server
from app.schemas import CheckResult
from app.workers import BoundedWorkers


CHECKS = (pb.CHECK_PII_NER, pb.CHECK_CONTENT_SAFETY, pb.CHECK_SYSTEM_PROMPT_LEAK)
SYSTEM = "Internal instruction: never publish the secret treasury reconciliation procedure."
PERSON = "Łukasz Wójcik"


class Pii(Detector):
    name = "pii_ner"

    def __init__(self):
        super().__init__()
        self.seen = []

    async def check(self, req):
        self.seen.append(req)
        start = req.text.find(PERSON)
        entities = [] if start < 0 else [dict(type="PERSON", start=start, end=start + len(PERSON), score=.95)]
        return CheckResult(check=self.name, status="ok", score=.95 if entities else 0,
                           details={"entities": entities})


@asynccontextmanager
async def serve(detectors, client, settings=None):
    workers = BoundedWorkers("output-contract-artifacts", 1)
    server, port = await start_grpc_server(detectors, 0, settings or Settings(), client, workers)
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            yield semantic_pb2_grpc.SemanticServiceStub(channel)
    finally:
        await server.stop(None)
        workers.shutdown()
        for detector in detectors.values():
            if getattr(detector, "workers", None):
                detector.workers.shutdown()


def request(text, checks=CHECKS, timeout_ms=1000):
    return pb.AnalyzeRequest(direction=pb.DIRECTION_OUTPUT, messages=[
        pb.Message(id="system", role="system", content=SYSTEM),
        pb.Message(id="user", role="user", content="Please give a short answer."),
        pb.Message(id="answer", role="assistant", content=text),
    ], checks=[pb.CheckSpec(check=c, timeout_ms=timeout_ms) for c in checks])


@pytest.fixture
async def output_service():
    calls = []

    def ollama(req):
        body = json.loads(req.content)
        calls.append(body)
        # Only the LLM verdict is substituted. The actual content-safety adapter formats/parses it.
        verdict = "unsafe\nS1" if "unsafe fixture" in body["messages"][-1]["content"] else "safe"
        return httpx.Response(200, json={"message": {"content": verdict}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(ollama)) as client:
        pii, leakage = Pii(), LeakageDetector()
        pii.load()
        leakage.load()
        guard = ContentSafetyDetector(client, "http://ollama.test", "guard-fixture")
        guard.state = "ready"  # No model load: this suite verifies transport, not ML accuracy.
        async with serve({d.name: d for d in (pii, guard, leakage)}, client) as stub:
            yield stub, pii, calls


@pytest.mark.parametrize("text,positive", [
    ("Raport został przygotowany. Dziękuję za cierpliwość.", set()),
    (f"📄 Łódź — kontakt: {PERSON}.", {pb.CHECK_PII_NER}),
    ("unsafe fixture", {pb.CHECK_CONTENT_SAFETY}),
    (SYSTEM, {pb.CHECK_SYSTEM_PROMPT_LEAK}),
    (f"{PERSON}: unsafe fixture. {SYSTEM}", set(CHECKS)),
])
async def test_output_controls_allow_and_detect_independently(output_service, text, positive):
    stub, _, _ = output_service
    response = await stub.Analyze(request(text), timeout=3)
    assert Counter((r.message_id, r.check) for r in response.results) == Counter(
        ("answer", c) for c in CHECKS)
    assert all(r.status == pb.STATUS_OK and not r.error for r in response.results)
    assert {r.check for r in response.results if r.score >= .5} == positive
    safety = next(r for r in response.results if r.check == pb.CHECK_CONTENT_SAFETY)
    assert list(safety.categories) == (["S1"] if pb.CHECK_CONTENT_SAFETY in positive else [])


async def test_context_is_not_scanned_and_last_user_and_all_system_turns_are_used(output_service):
    stub, pii, calls = output_service
    req = request("Dziękuję.", checks=(*CHECKS, pb.CHECK_PII_NER))
    req.messages.insert(1, pb.Message(id="system-2", role="system", content="Secondary internal rule."))
    req.messages.insert(2, pb.Message(id="old-user", role="user", content=f"{PERSON}: unsafe fixture"))
    req.messages.append(pb.Message(id="tool", role="tool", content="Completed."))
    response = await stub.Analyze(req, timeout=3)
    assert Counter((r.message_id, r.check) for r in response.results) == Counter(
        (m, c) for m in ("answer", "tool") for c in CHECKS)
    assert all(r.status == pb.STATUS_OK and r.score == 0 for r in response.results)
    assert {r.text for r in pii.seen} == {"Dziękuję.", "Completed."}
    assert all(r.direction == "output" and not r.config.pii_ner.redact for r in pii.seen)
    assert all(r.context.system_prompt == SYSTEM + "\nSecondary internal rule." for r in pii.seen)
    assert len(calls) == 2
    for call in calls:
        assert call["messages"][0] == {"role": "user", "content": "Please give a short answer."}
        assert call["messages"][1]["role"] == "assistant"


async def test_output_pii_offsets_roundtrip_multibyte_entity_and_surroundings(output_service):
    stub, _, _ = output_service
    text = f"📄 Łódź — kontakt: {PERSON}; zakończono ✅"
    response = await stub.Analyze(request(text, (pb.CHECK_PII_NER,)), timeout=3)
    span, = response.results[0].spans
    encoded = text.encode("utf-8")
    assert (span.message_id, span.entity) == ("answer", "PERSON")
    assert span.start == len(text[:text.index(PERSON)].encode("utf-8"))
    assert encoded[span.start:span.end].decode("utf-8") == PERSON
    # Apply the public contract exactly as a byte-slicing gateway does.
    redacted = (encoded[:span.start] + b"[REDACTED:PERSON]" + encoded[span.end:]).decode("utf-8")
    assert redacted == text.replace(PERSON, "[REDACTED:PERSON]")


@pytest.mark.parametrize("encode", [str, lambda s: base64.b64encode(s.encode()).decode()])
async def test_output_canary_leak_with_benign_user_context(output_service, encode):
    stub, _, _ = output_service
    req = request(encode("CANARY-output-73d812"), (pb.CHECK_SYSTEM_PROMPT_LEAK,))
    req.canaries.append("CANARY-output-73d812")
    result, = (await stub.Analyze(req, timeout=3)).results
    assert result.status == pb.STATUS_OK and result.score == 1


class Failure(Detector):
    name = "content_safety"

    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.state = "failed: unavailable model" if mode == "not_ready" else "ready"

    async def check(self, req):
        if self.mode == "error":
            raise RuntimeError("model failed")
        if self.mode == "rejected":
            raise Rejected("model input exceeds resource budget")
        await asyncio.sleep(5)
        raise AssertionError("timeout was not enforced")


@pytest.mark.parametrize("mode,status", [
    ("missing", pb.STATUS_ERROR), ("not_ready", pb.STATUS_ERROR), ("error", pb.STATUS_ERROR),
    ("timeout", pb.STATUS_TIMEOUT), ("rejected", pb.STATUS_REJECTED),
])
async def test_output_failure_keeps_a_result_for_every_check(mode, status):
    pii, leakage = Pii(), LeakageDetector()
    pii.load()
    leakage.load()
    detectors = {d.name: d for d in (pii, leakage)}
    if mode != "missing":
        detectors["content_safety"] = Failure(mode)
    async with httpx.AsyncClient() as client:
        async with serve(detectors, client) as stub:
            response = await stub.Analyze(request(PERSON, timeout_ms=100), timeout=3)
    assert Counter((r.message_id, r.check) for r in response.results) == Counter(("answer", c) for c in CHECKS)
    results = {r.check: r for r in response.results}
    assert results[pb.CHECK_PII_NER].status == pb.STATUS_OK
    assert results[pb.CHECK_PII_NER].spans
    assert results[pb.CHECK_SYSTEM_PROMPT_LEAK].status == pb.STATUS_OK
    failed = results[pb.CHECK_CONTENT_SAFETY]
    assert failed.status == status and failed.error
    assert not failed.spans and not failed.categories


async def test_output_empty_checks_runs_all_four_including_missing_detector(output_service):
    stub, _, _ = output_service
    results = (await stub.Analyze(request("Dziękuję.", checks=()), timeout=3)).results
    assert Counter(r.check for r in results) == Counter((*CHECKS, pb.CHECK_PROMPT_INJECTION))
    missing = next(r for r in results if r.check == pb.CHECK_PROMPT_INJECTION)
    assert missing.status == pb.STATUS_ERROR and missing.error


async def test_output_oversize_rejects_every_control_without_losing_other_answer(output_service):
    stub, _, _ = output_service
    req = request("x" * 200_001)
    req.messages.append(pb.Message(id="short", role="assistant", content="Dziękuję."))
    results = (await stub.Analyze(req, timeout=3)).results
    assert Counter((r.message_id, r.check) for r in results) == Counter(
        (m, c) for m in ("answer", "short") for c in CHECKS)
    for result in results:
        assert result.status == (pb.STATUS_REJECTED if result.message_id == "answer" else pb.STATUS_OK)
