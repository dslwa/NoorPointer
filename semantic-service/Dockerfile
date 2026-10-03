FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/models/hf PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
# Generated from ../proto by gen-proto.sh (committed, since the build context can't see ../proto).
COPY semantic ./semantic
# Bake the prompt-injection model into the image (the spaCy model is a pip dependency), so it runs offline.
RUN python -m app.download
# Offline only for loading the inference model; a global HF_HUB_OFFLINE would also break HF repo scanning.
ENV MODELS_OFFLINE=1

EXPOSE 8001 50051
HEALTHCHECK --interval=10s --timeout=3s --start-period=120s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz')"
# grpc.aio shares uvicorn's event loop, so use the stdlib asyncio loop rather than uvloop.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--loop", "asyncio"]
