FROM python:3.12-slim

# uv jest przypiety do wersji - `latest` czynil build niedeterministycznym.
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/models/hf PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Non-root runtime user. Katalog modeli tworzymy i oddajemy temu uzytkownikowi ZANIM pobierzemy modele,
# zeby pliki od razu byly jego wlasnoscia (chown po fakcie kopiowalby cale modele do nowej warstwy).
RUN useradd --create-home --uid 10002 --user-group semantic \
 && mkdir -p /models/hf && chown semantic:semantic /models/hf

COPY app ./app
# Generated from ../proto by gen-proto.sh (committed, since the build context can't see ../proto).
COPY semantic ./semantic
# Bake the prompt-injection model into the image (the spaCy model is a pip dependency), so it runs offline.
USER semantic
RUN python -m app.download
# Offline only for loading the inference model; a global HF_HUB_OFFLINE would also break HF repo scanning.
ENV MODELS_OFFLINE=1

EXPOSE 8001 50051
HEALTHCHECK --interval=10s --timeout=3s --start-period=120s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz')"
# grpc.aio shares uvicorn's event loop, so use the stdlib asyncio loop rather than uvloop.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--loop", "asyncio"]
