import asyncio
import logging
import time
from pathlib import Path

import grpc
import httpx
from pydantic import ValidationError
from semantic.v1 import semantic_pb2 as pb
from semantic.v1 import semantic_pb2_grpc

from app import artifacts, model_scan
from app.config import Settings
from app.detectors.base import Detector
from app.engine import run_check
from app.schemas import CheckResult, ScanContext, ScanRequest

log = logging.getLogger(__name__)

CHECKS = {
    pb.CHECK_PROMPT_INJECTION: "prompt_injection",
    pb.CHECK_CONTENT_SAFETY: "content_safety",
    pb.CHECK_PII_NER: "pii_ner",
    pb.CHECK_SYSTEM_PROMPT_LEAK: "leakage",
}
STATUS = {"ok": pb.STATUS_OK, "timeout": pb.STATUS_TIMEOUT, "error": pb.STATUS_ERROR}
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
# Answer this much before the caller's deadline so partial results (STATUS_TIMEOUT) still arrive.
DEADLINE_MARGIN_MS = 20


def _byte_offset(text: str, char_index: int) -> int:
    return len(text[:char_index].encode("utf-8"))


def _to_proto(r: CheckResult, check: int, msg: pb.Message) -> pb.CheckResult:
    out = pb.CheckResult(check=check, status=STATUS[r.status], message_id=msg.id, score=r.score or 0.0,
                         latency_ms=round(r.latency_ms), error=r.error or "")
    if r.status != "ok":
        return out
    if r.check == "content_safety":
        out.categories.extend(c["code"] for c in r.details.get("categories", []))
    elif r.check == "pii_ner":
        # Presidio gives character offsets; Go slices strings by UTF-8 bytes ("Łódź" would shift otherwise).
        for e in r.details.get("entities", []):
            out.spans.append(pb.Span(message_id=msg.id, start=_byte_offset(msg.content, e["start"]),
                                     end=_byte_offset(msg.content, e["end"]), entity=e["type"], score=e["score"]))
    return out


class SemanticServicer(semantic_pb2_grpc.SemanticServiceServicer):
    def __init__(self, detectors: dict[str, Detector], settings: Settings, client: httpx.AsyncClient) -> None:
        self.detectors = detectors
        self.settings = settings
        self.client = client

    async def Analyze(self, request: pb.AnalyzeRequest, context: grpc.aio.ServicerContext) -> pb.AnalyzeResponse:
        remaining = context.time_remaining()
        budget_ms = None if remaining is None else int(remaining * 1000) - DEADLINE_MARGIN_MS
        specs = list(request.checks) or [pb.CheckSpec(check=c) for c in CHECKS]
        unknown = [s.check for s in specs if s.check not in CHECKS]
        if unknown:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"unknown checks: {unknown}")

        direction = "output" if request.direction == pb.DIRECTION_OUTPUT else "input"
        # role=system messages are trusted reference material (for leak detection), not something to scan.
        system_prompt = "\n".join(m.content for m in request.messages if m.role == "system")
        jobs = []
        try:
            for msg in request.messages:
                if msg.role == "system":
                    continue
                for spec in specs:
                    name = CHECKS[spec.check]
                    if name == "leakage" and (direction != "output" or not system_prompt):
                        continue  # OUTPUT only, and needs a system prompt to compare against
                    timeout = spec.timeout_ms or DEFAULT_CHECK_TIMEOUT_MS
                    if budget_ms is not None:
                        timeout = min(timeout, budget_ms)
                    scan = ScanRequest(request_id=request.request_id or None, direction=direction, text=msg.content,
                                       checks=[name], context=ScanContext(system_prompt=system_prompt or None),
                                       timeout_ms=min(max(timeout, 10), 30_000))
                    jobs.append((spec.check, msg, run_check(name, self.detectors.get(name), scan)))
        except ValidationError as exc:
            for _, _, coro in jobs:
                coro.close()
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        results = await asyncio.gather(*(coro for _, _, coro in jobs))
        return pb.AnalyzeResponse(results=[_to_proto(r, check, msg)
                                           for (check, msg, _), r in zip(jobs, results) if r.status != "skipped"])

    async def ScanArtifact(self, request: pb.ScanArtifactRequest,
                           context: grpc.aio.ServicerContext) -> pb.ScanArtifactResponse:
        start = time.perf_counter()
        max_bytes = request.max_bytes or self.settings.max_upload_mb * 1024 * 1024
        source = request.WhichOneof("source")
        try:
            if source == "url":
                name, data = await artifacts.download(self.client, request.url, self.settings.artifact_hosts,
                                                      max_bytes)
            elif source == "path":
                name, data = await asyncio.to_thread(artifacts.read_path, request.path,
                                                     Path(self.settings.artifact_root), max_bytes)
            else:
                raise artifacts.InvalidSource("set url or path")
        except artifacts.ArtifactError as exc:
            await context.abort(ARTIFACT_ERRORS[type(exc)], str(exc))
        except httpx.HTTPError as exc:
            await context.abort(grpc.StatusCode.UNAVAILABLE, f"download failed: {exc}")

        report = await asyncio.to_thread(model_scan.scan_bytes, name, data,
                                         self.settings.max_unpacked_mb * 1024 * 1024)
        log.info("artifact %s (%s): %s", name, report["sha256"][:12], report["verdict"])
        return pb.ScanArtifactResponse(
            verdict=VERDICT[report["verdict"]],
            format=report["format"],
            sha256=report["sha256"],
            findings=[pb.ArtifactFinding(module=i["module"], name=i["name"], verdict=VERDICT[i["severity"]])
                      for i in report["imports"]],
            latency_ms=round((time.perf_counter() - start) * 1000),
        )


async def start_grpc_server(detectors: dict[str, Detector], port: int, settings: Settings,
                            client: httpx.AsyncClient) -> tuple[grpc.aio.Server, int]:
    server = grpc.aio.server()
    semantic_pb2_grpc.add_SemanticServiceServicer_to_server(SemanticServicer(detectors, settings, client), server)
    bound = server.add_insecure_port(f"[::]:{port}")
    await server.start()
    log.info("gRPC server listening on :%d", bound)
    return server, bound
