FROM python:3.12-slim

# Wersja "uv" przypieta na sztywno - "latest" psul powtarzalnosc budowy.
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/models/hf PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Konto bez uprawnien roota. Katalog modeli oddajemy mu od razu, zeby pliki byly jego wlasnoscia.
RUN useradd --create-home --uid 10002 --user-group semantic \
 && mkdir -p /models/hf && chown semantic:semantic /models/hf

COPY app ./app
# Plik wygenerowany z ../proto i wrzucony do repo, bo budowa nie widzi katalogu obok.
COPY semantic ./semantic
# Model do wykrywania atakow wgrywamy do obrazu, zeby dzialal bez internetu.
USER semantic
RUN python -m app.download
# Offline tylko dla modelu - globalne HF_HUB_OFFLINE psuloby skanowanie repozytoriow HF.
ENV MODELS_OFFLINE=1

EXPOSE 8001 50051
HEALTHCHECK --interval=10s --timeout=3s --start-period=120s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz')"
# grpc.aio korzysta z petli uvicorna, wiec uzywamy zwyklego asyncio, a nie uvloop.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--loop", "asyncio"]
