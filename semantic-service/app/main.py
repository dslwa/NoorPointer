import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app import artifacts, model_scan
from app.config import Settings
from app.detectors import Detector, build_detectors
from app.engine import run_scan
from app.grpc_server import start_grpc_server
from app.limits import BodySizeLimit
from app.schemas import HfScanRequest, ScanRequest, ScanResponse
from app.workers import BoundedWorkers, Overloaded

HF_MAX_FILES = 100
HF_SCAN_TIMEOUT_S = 600
HTTP_SLOT_WAIT_S = 30

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, detectors: dict[str, Detector] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    max_unpacked = settings.max_unpacked_mb * 1024 * 1024
    hf_scans_running = 0

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = httpx.AsyncClient(timeout=30)
        app.state.client = client
        # One pool for every artifact scan (HTTP and gRPC); a slot covers download + scan, which bounds memory.
        # Created per lifespan, so a restarted app never inherits a shut-down pool.
        app.state.scan_workers = BoundedWorkers("artifact-scan", settings.scan_workers)
        owned = detectors is None
        app.state.detectors = build_detectors(settings, client) if owned else detectors
        # Load models in the background so /healthz answers immediately; /readyz reports progress.
        loaders = [asyncio.to_thread(d.load) for d in app.state.detectors.values() if d.state == "loading"]
        app.state.loading = asyncio.gather(*loaders)
        grpc_server = None
        if settings.grpc_port:
            grpc_server, _ = await start_grpc_server(app.state.detectors, settings.grpc_port, settings, client,
                                                     app.state.scan_workers)
        yield
        if grpc_server:
            await grpc_server.stop(grace=2)
        await client.aclose()
        # don't let in-flight scans or inferences block process exit; only shut down pools this app created
        app.state.scan_workers.shutdown()
        if owned:
            for detector in app.state.detectors.values():
                if getattr(detector, "workers", None) is not None:
                    detector.workers.shutdown()

    app = FastAPI(title="NoorPointer Semantic Service", version="0.1.0", lifespan=lifespan)
    app.mount("/metrics", make_asgi_app())
    app.add_middleware(BodySizeLimit, default=64 * 1024, limits={
        # text + system_prompt + prompt, up to 200k chars each, worst case 6 bytes per char as JSON escapes
        "/v1/scan": 4 * 1024 * 1024,
        # multipart overhead is small; the handler checks the exact file size
        "/v1/scan/model": max_bytes + 64 * 1024,
    })

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        states = {name: d.state for name, d in app.state.detectors.items()}
        ready = all(d.ready for d in app.state.detectors.values())
        return JSONResponse({"ready": ready, "detectors": states}, status_code=200 if ready else 503)

    @app.post("/v1/scan", response_model=ScanResponse)
    async def scan(req: ScanRequest) -> ScanResponse:
        return await run_scan(req, app.state.detectors)

    @app.post("/v1/scan/model")
    async def scan_model(file: UploadFile):
        try:
            async with app.state.scan_workers.reserve(wait_s=HTTP_SLOT_WAIT_S) as reservation:  # before reading into memory
                data = await file.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise HTTPException(413, f"file larger than {settings.max_upload_mb} MB")
                scan = reservation.submit(model_scan.scan_bytes, file.filename or "upload", data, max_unpacked)
        except Overloaded as exc:
            raise HTTPException(503, f"scanner busy: {exc}") from exc
        return model_scan.summarize([await scan])

    @app.post("/v1/scan/model/hf")
    async def scan_hf(req: HfScanRequest):
        """Scan a Hugging Face repo (nothing is unpickled). Files come from the commit the metadata came from
        (info.sha), so a moving branch can't swap in a different file, through the same size-capped,
        host-allowlisted downloader as ScanArtifact. Every file that isn't provably harmless shows up in the
        report: unscannable weights and custom code are "unknown", and a repo with nothing scanned is never safe."""
        nonlocal hf_scans_running
        if hf_scans_running >= 1:  # one at a time: a repo scan holds at most one shared scan slot
            raise HTTPException(503, "another repository scan is running")
        hf_scans_running += 1
        try:
            return await asyncio.wait_for(_scan_hf(req), HF_SCAN_TIMEOUT_S)
        except TimeoutError as exc:
            raise HTTPException(504, f"repository scan exceeded {HF_SCAN_TIMEOUT_S}s") from exc
        finally:
            hf_scans_running -= 1

    async def _scan_hf(req: HfScanRequest) -> dict:
        from huggingface_hub import HfApi

        try:
            info = await asyncio.to_thread(HfApi().model_info, req.repo_id, revision=req.revision,
                                           files_metadata=True)
        except Exception as exc:
            raise HTTPException(502, f"could not fetch {req.repo_id}: {exc}") from exc
        if not info.sha:  # without a commit hash we can't pin the files we download to what we listed
            raise HTTPException(502, f"no commit hash for {req.repo_id}")
        reports = []  # at most HF_MAX_FILES entries, scanned or not
        for sibling in info.siblings or []:
            name = sibling.rfilename
            kind = model_scan.classify_repo_file(name)
            if kind == "benign":
                continue
            if kind != "scan" or len(reports) >= HF_MAX_FILES:
                note = kind if kind != "scan" else f"not scanned: more than {HF_MAX_FILES} files"
                reports.append(model_scan.unscanned_report(name, note))
                continue
            url = f"https://huggingface.co/{req.repo_id}/resolve/{info.sha}/{quote(name)}"
            try:
                async with app.state.scan_workers.reserve() as reservation:  # waits; bounded by HF_SCAN_TIMEOUT_S
                    _, data = await artifacts.download(app.state.client, url, settings.artifact_hosts, max_bytes)
                    scan = reservation.submit(model_scan.scan_bytes, name, data, max_unpacked)
            except (artifacts.ArtifactError, httpx.HTTPError) as exc:
                reports.append(model_scan.unscanned_report(name, f"download failed: {exc}"))
                continue
            reports.append(await scan)
        return {"repo_id": req.repo_id, "revision": info.sha, **model_scan.summarize(reports)}

    return app


app = create_app()
