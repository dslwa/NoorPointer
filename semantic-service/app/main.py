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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, detectors: dict[str, Detector] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = httpx.AsyncClient(timeout=30)
        app.state.client = client
        app.state.detectors = detectors if detectors is not None else build_detectors(settings, client)
        # Load models in the background so /healthz answers immediately; /readyz reports progress.
        loaders = [asyncio.to_thread(d.load) for d in app.state.detectors.values() if d.state == "loading"]
        app.state.loading = asyncio.gather(*loaders)
        grpc_server = None
        if settings.grpc_port:
            grpc_server, _ = await start_grpc_server(app.state.detectors, settings.grpc_port, settings, client)
        yield
        if grpc_server:
            await grpc_server.stop(grace=2)
        await client.aclose()

    app = FastAPI(title="AgentGate Semantic Service", version="0.1.0", lifespan=lifespan)
    app.mount("/metrics", make_asgi_app())
    max_bytes = settings.max_upload_mb * 1024 * 1024
    max_unpacked = settings.max_unpacked_mb * 1024 * 1024
    # Multipart overhead is small; the middleware stops the stream, the handler checks the exact file size.
    app.add_middleware(BodySizeLimit, limit=max_bytes + 64 * 1024, path_prefix="/v1/scan/model")

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
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, f"file larger than {settings.max_upload_mb} MB")
        report = await asyncio.to_thread(model_scan.scan_bytes, file.filename or "upload", data, max_unpacked)
        return model_scan.summarize([report])

    @app.post("/v1/scan/model/hf")
    async def scan_hf(req: HfScanRequest):
        """Scan every pickle-capable file of a Hugging Face repo (nothing is unpickled). Files are downloaded
        from the commit the metadata came from (info.sha), so a moving branch can't swap in a different file,
        and through the same size-capped, host-allowlisted downloader as ScanArtifact."""
        from huggingface_hub import HfApi

        try:
            info = await asyncio.to_thread(HfApi().model_info, req.repo_id, revision=req.revision,
                                           files_metadata=True)
        except Exception as exc:
            raise HTTPException(502, f"could not fetch {req.repo_id}: {exc}") from exc
        reports = []
        for sibling in info.siblings or []:
            if not sibling.rfilename.endswith(model_scan.PICKLE_SUFFIXES):
                continue
            url = f"https://huggingface.co/{req.repo_id}/resolve/{info.sha}/{quote(sibling.rfilename)}"
            try:
                _, data = await artifacts.download(app.state.client, url, settings.artifact_hosts, max_bytes)
            except artifacts.ArtifactError as exc:
                reports.append({"name": sibling.rfilename, "format": "unknown", "verdict": "unknown",
                                "imports": [], "note": str(exc), "sha256": None})
                continue
            reports.append(await asyncio.to_thread(model_scan.scan_bytes, sibling.rfilename, data, max_unpacked))
        return {"repo_id": req.repo_id, "revision": info.sha, **model_scan.summarize(reports)}

    return app


app = create_app()
