<<<<<<< HEAD
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
=======
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl gcc python3-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# Instalacja PyTorch CPU (oszczędność ~3 GB w obrazie Dockera)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY guardrails.proto ./
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. guardrails.proto

COPY server.py ./

EXPOSE 8001 50051

CMD ["python", "server.py"]
>>>>>>> 3c329da00f724e8e55fef1c269891037b8e4e8de
