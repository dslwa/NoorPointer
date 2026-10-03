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
