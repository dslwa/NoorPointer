#!/usr/bin/env bash
# Regenerate Python gRPC stubs from the shared contract in ../proto (run after any .proto change).
set -euo pipefail
cd "$(dirname "$0")"
uv run python -m grpc_tools.protoc -I ../proto --python_out=. --pyi_out=. --grpc_python_out=. \
  ../proto/semantic/v1/semantic.proto
