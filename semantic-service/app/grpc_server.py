import asyncio
import logging
import time
from pathlib import Path

import grpc
import httpx
from semantic.v1 import semantic_pb2 as pb
from semantic.v1 import semantic_pb2_grpc

from app import artifacts, model_scan
from app.config import Settings
from app.detectors.base import Detector
from app.engine import run_check
from app.schemas import (MAX_CANARIES, MAX_CANARY_CHARS, MAX_TEXT_CHARS, CheckResult, ChecksConfig, PiiConfig,
                         ScanContext, ScanRequest)
from app.workers import BoundedWorkers, Overloaded

log = logging.getLogger(__name__)

CHECKS = {
    pb.CHECK_PROMPT_INJECTION: "prompt_injection",
    pb.CHECK_CONTENT_SAFETY: "content_safety",
    pb.CHECK_PII_NER: "pii_ner",
    pb.CHECK_SYSTEM_PROMPT_LEAK: "leakage",
}
# "skipped" only happens when there is provably nothing to find (leak check without a system prompt or
# canaries): it is reported as OK with score 0 and the reason in `error`, never dropped.
STATUS = {"ok": pb.STATUS_OK, "skipped": pb.STATUS_OK, "timeout": pb.STATUS_TIMEOUT, "error": pb.STATUS_ERROR,
          "rejected": pb.STATUS_REJECTED}
# No UNKNOWN in the proto: a file we can't parse is not proven safe, so it is SUSPICIOUS (allowlist approach).
VERDICT = {"safe": pb.VERDICT_SAFE, "suspicious": pb.VERDICT_SUSPICIOUS, "unknown": pb.VERDICT_SUSPICIOUS,
           "dangerous": pb.VERDICT_MALICIOUS}
ARTIFACT_ERRORS = {
    artifacts.InvalidSource: grpc.StatusCode.INVALID_ARGUMENT,
    artifacts.NotFound: grpc.StatusCode.NOT_FOUND,
    artifacts.TooLarge: grpc.StatusCode.RESOURCE_EXHAUSTED,
    artifacts.FetchFailed: grpc.StatusCode.UNAVAILABLE,
}
DEFAULT_CHECK_TIMEOUT_MS = 1000
MIN_CHECK_TIMEOUT_MS = 10
# Answer this much before the caller's deadline so partial results (STATUS_TIMEOUT) still arrive.
DEADLINE_MARGIN_MS = 20
DEFAULT_ARTIFACT_TIMEOUT_S = 120  # when the caller sets no deadline
# Beyond max_messages each message gets its own REJECTED result; past this, answering per message would itself
# be the amplification (a 4 MB request of tiny messages -> millions of results), so the whole request gets
# request-level REJECTED results (message_id "") instead: still a block, never an RPC error to fail open on.
HARD_MAX_MESSAGES = 1000


def _byte_offsets(text: str, char_indices: set[int]) -> dict[int, int]:
    """UTF-8 byte offset of each character index, in one pass over the text (not one encode per entity)."""
    offsets, byte_pos, prev = {}, 0, 0
    for index in sorted(char_indices):
        byte_pos += len(text[prev:index].encode("utf-8"))
        offsets[index], prev = byte_pos, index
    return offsets


def _to_proto(r: CheckResult, check: int, msg: pb.Message) -> pb.CheckResult:
    error = r.error or (f"skipped: {r.details.get('reason', '')}" if r.status == "skipped" else "")
    out = pb.CheckResult(check=check, status=STATUS[r.status], message_id=msg.id, score=r.score or 0.0,
                         latency_ms=round(r.latency_ms), error=error)
    if r.status != "ok":
        return out
    if r.check == "content_safety":
        out.categories.extend(c["code"] for c in r.details.get("categories", []))
    elif r.check == "pii_ner":
        # Presidio gives character offsets; Go slices strings by UTF-8 bytes ("Łódź" would shift otherwise).
        entities = r.details.get("entities", [])
        to_bytes = _byte_offsets(msg.content, {i for e in entities for i in (e["start"], e["end"])})
        for e in entities:
            out.spans.append(pb.Span(message_id=msg.id, start=to_bytes[e["start"]], end=to_bytes[e["end"]],
                                     entity=e["type"], score=e["score"]))
    return out


async def _ready(result: CheckResult) -> CheckResult:
    return result


def _pool_size(detector: Detector | None) -> int:
    workers = getattr(detector, "workers", None)
    return workers.size if workers is not None else getattr(detector, "concurrency", 2)


class SemanticServicer(semantic_pb2_grpc.SemanticServiceServicer):
    def __init__(self, detectors: dict[str, Detector], settings: Settings, client: httpx.AsyncClient,
                 scan_workers: BoundedWorkers) -> None:
        self.detectors = detectors
        self.settings = settings
        self.client = client
        self.scan_workers = scan_workers

    async def Analyze(self, request: pb.AnalyzeRequest, context: grpc.aio.ServicerContext) -> pb.AnalyzeResponse:
        """Every (message, check) pair of the request gets exactly one result, so a missing result never
        looks like a clean one. Messages are judged independently: one oversized or over-budget message
        gets STATUS_ERROR for its checks while the others are still scored."""
        remaining = context.time_remaining()
        budget_ms = None if remaining is None else int(remaining * 1000) - DEADLINE_MARGIN_MS

        if request.direction not in (pb.DIRECTION_INPUT, pb.DIRECTION_OUTPUT):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "direction must be INPUT or OUTPUT")
        direction = "output" if request.direction == pb.DIRECTION_OUTPUT else "input"
        specs, seen = [], set()
        for spec in request.checks:  # a duplicated check would otherwise produce two results per message
            if spec.check not in seen:
                seen.add(spec.check)
                specs.append(spec)
        # no checks listed = every check that applies to this direction (the leak check is OUTPUT only)
        specs = specs or [pb.CheckSpec(check=c) for c in CHECKS
                          if direction == "output" or c != pb.CHECK_SYSTEM_PROMPT_LEAK]
        unknown = [s.check for s in specs if s.check not in CHECKS]
        if unknown:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"unknown checks: {unknown}")
        if direction == "input" and any(s.check == pb.CHECK_SYSTEM_PROMPT_LEAK for s in specs):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "CHECK_SYSTEM_PROMPT_LEAK is OUTPUT only")
        if len(request.canaries) > MAX_CANARIES or any(len(c) > MAX_CANARY_CHARS for c in request.canaries):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT,  # gateway config, not attacker input
                                f"at most {MAX_CANARIES} canaries of <= {MAX_CANARY_CHARS} chars")
        if len(request.messages) > HARD_MAX_MESSAGES:
            refused = f"more than {HARD_MAX_MESSAGES} messages in one request"
            return pb.AnalyzeResponse(results=[pb.CheckResult(check=s.check, status=pb.STATUS_REJECTED, error=refused)
                                               for s in specs])

        # INPUT: every message is scanned, role=system included: agent frameworks let untrusted content into
        # system messages, and the gateway can still apply a different policy per role via message_id.
        # OUTPUT: role=system (leak reference) and role=user (Llama Guard context) were scanned on INPUT and
        # are only context here; the targets are the model/tool outputs.
        # The system prompt is only the leak check's reference (OUTPUT); an oversized one rejects that check,
        # never the whole request (system messages can be attacker-influenced).
        system_prompt = "\n".join(m.content for m in request.messages if m.role == "system") \
            if direction == "output" else ""
        leak_refused = f"system messages exceed {MAX_TEXT_CHARS} chars" if len(system_prompt) > MAX_TEXT_CHARS else None
        if leak_refused:
            system_prompt = ""
        user_turns = [m.content for m in request.messages if m.role == "user"]
        prompt = user_turns[-1][-MAX_TEXT_CHARS:] if direction == "output" and user_turns else None
        targets = [m for m in request.messages if direction == "input" or m.role not in ("system", "user")]
        if not targets:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "no messages to analyze")
        scan_context = ScanContext(system_prompt=system_prompt or None, canaries=list(request.canaries),
                                   prompt=prompt)
        # the gRPC contract returns spans, not redacted text: skip the anonymizer pass
        config = ChecksConfig(pii_ner=PiiConfig(redact=False))

        # Per request, a check may use at most half of its pool, so one many-message request can't hold every
        # slot for its whole deadline while other agents' checks time out.
        gates = {name: asyncio.Semaphore(max(1, _pool_size(self.detectors.get(name)) // 2))
                 for name in {CHECKS[s.check] for s in specs}}
        jobs = []
        used_chars = 0
        for index, msg in enumerate(targets):
            if len(msg.content) > MAX_TEXT_CHARS:
                refused = f"message too long ({len(msg.content)} chars, limit {MAX_TEXT_CHARS})"
            elif index >= self.settings.max_messages:
                refused = f"too many messages in request (limit {self.settings.max_messages})"
            elif used_chars + len(msg.content) > self.settings.max_request_chars:
                refused = f"request character budget exceeded (limit {self.settings.max_request_chars})"
            else:
                refused = None
                used_chars += len(msg.content)
            for spec in specs:
                name = CHECKS[spec.check]
                timeout = spec.timeout_ms or DEFAULT_CHECK_TIMEOUT_MS
                if budget_ms is not None:
                    timeout = min(timeout, budget_ms)
                refusal = refused or (leak_refused if name == "leakage" else None)
                if refusal:  # attacker-controllable, so never STATUS_ERROR (which a fail-open policy lets through)
                    coro = _ready(CheckResult(check=name, status="rejected", error=refusal))
                elif timeout < MIN_CHECK_TIMEOUT_MS:
                    coro = _ready(CheckResult(check=name, status="timeout", error="no time left before deadline"))
                else:
                    scan = ScanRequest(request_id=request.request_id or None, direction=direction, text=msg.content,
                                       checks=[name], config=config, context=scan_context,
                                       timeout_ms=min(timeout, 30_000))
                    coro = self._fair_check(name, scan, gates)
                jobs.append((spec.check, msg, coro))

        results = await asyncio.gather(*(coro for _, _, coro in jobs))
        return pb.AnalyzeResponse(results=[_to_proto(r, check, msg) for (check, msg, _), r in zip(jobs, results)])

    async def _fair_check(self, name: str, scan: ScanRequest, gates: dict[str, asyncio.Semaphore]) -> CheckResult:
        """run_check behind this request's gate; time spent waiting for the gate counts against the check's
        timeout, so a queued check still answers before the deadline."""
        started = time.monotonic()
        # The gate only queues behind this same request's messages, so running out of time there is caused by
        # the request's own size: REJECTED, never a timeout a fail-open policy would let through.
        self_inflicted = f"no time left after this request's other messages (limit {scan.timeout_ms} ms)"
        try:
            await asyncio.wait_for(gates[name].acquire(), scan.timeout_ms / 1000)
        except TimeoutError:
            return CheckResult(check=name, status="rejected", error=self_inflicted)
        try:
            left_ms = scan.timeout_ms - int((time.monotonic() - started) * 1000)
            if left_ms < MIN_CHECK_TIMEOUT_MS:
                return CheckResult(check=name, status="rejected", error=self_inflicted)
            return await run_check(name, self.detectors.get(name), scan.model_copy(update={"timeout_ms": left_ms}))
        finally:
            gates[name].release()

    async def ScanArtifact(self, request: pb.ScanArtifactRequest,
                           context: grpc.aio.ServicerContext) -> pb.ScanArtifactResponse:
        start = time.perf_counter()
        remaining = context.time_remaining()
        # like Analyze, answer before the caller's deadline so it gets our status rather than its own timeout
        budget = DEFAULT_ARTIFACT_TIMEOUT_S if remaining is None else remaining - DEADLINE_MARGIN_MS / 1000
        deadline = time.monotonic() + budget
        cap = self.settings.max_upload_mb * 1024 * 1024
        max_bytes = min(request.max_bytes or cap, cap)  # the caller may lower the limit, never raise it
        max_unpacked = self.settings.max_unpacked_mb * 1024 * 1024
        source = request.WhichOneof("source")
        if source not in ("url", "path"):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "set url or path")

        def left() -> float:
            return max(deadline - time.monotonic(), 0)

        try:
            # The slot is held until the job's thread finishes (download + scan, or read + scan), which
            # bounds memory to scan_workers x (max_bytes + max_unpacked) even when callers time out.
            async with self.scan_workers.reserve(wait_s=left()) as reservation:
                if source == "url":
                    name, data = await asyncio.wait_for(
                        artifacts.download(self.client, request.url, self.settings.artifact_hosts, max_bytes), left())
                    scan = reservation.submit(model_scan.scan_bytes, name, data, max_unpacked)
                else:
                    scan = reservation.submit(_read_and_scan, request.path, Path(self.settings.artifact_root),
                                              max_bytes, max_unpacked)
            # On timeout the job finishes in the background and then frees its slot.
            report = await asyncio.wait_for(scan, left())
        except Overloaded as exc:
            await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, f"scanner busy: {exc}")
        except artifacts.ArtifactError as exc:
            await context.abort(ARTIFACT_ERRORS[type(exc)], str(exc))
        except httpx.HTTPError as exc:
            await context.abort(grpc.StatusCode.UNAVAILABLE, f"download failed: {exc}")
        except TimeoutError:
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "artifact scan exceeded the deadline")
        log.info("artifact %s (%s): %s", report["name"], report["sha256"][:12], report["verdict"])
        return pb.ScanArtifactResponse(
            verdict=VERDICT[report["verdict"]],
            format=report["format"],
            sha256=report["sha256"],
            findings=[pb.ArtifactFinding(module=i["module"], name=i["name"], verdict=VERDICT[i["severity"]])
                      for i in report["imports"]],
            latency_ms=round((time.perf_counter() - start) * 1000),
        )


def _read_and_scan(path: str, root: Path, max_bytes: int, max_unpacked: int) -> dict:
    name, data = artifacts.read_path(path, root, max_bytes)
    return model_scan.scan_bytes(name, data, max_unpacked)


async def start_grpc_server(detectors: dict[str, Detector], port: int, settings: Settings,
                            client: httpx.AsyncClient, scan_workers: BoundedWorkers) -> tuple[grpc.aio.Server, int]:
    server = grpc.aio.server()
    servicer = SemanticServicer(detectors, settings, client, scan_workers)
    semantic_pb2_grpc.add_SemanticServiceServicer_to_server(servicer, server)
    bound = server.add_insecure_port(f"[::]:{port}")
    await server.start()
    log.info("gRPC server listening on :%d", bound)
    return server, bound
