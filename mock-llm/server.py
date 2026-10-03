"""Deterministic mock LLM, OpenAI- and Ollama-compatible, zero dependencies (stdlib only).

  * gateway proxies POST /v1/chat/completions here (OpenAI contract)
  * semantic content_safety calls GET /api/tags + POST /api/chat (Ollama contract)

Swap for real Ollama/OpenAI by pointing UPSTREAM_LLM_URL / OLLAMA_URL elsewhere - no code changes.
Listens on :11434 (drop-in for the ollama service it replaces).
"""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_DEFAULT = os.getenv("MOCK_MODEL", "mock-llm")
GUARD_MODEL = os.getenv("MOCK_GUARD_MODEL", "llama-guard3:1b")
HAZARD_KEYWORDS = ("bomb", "explosive", "nerve agent", "bioweapon", "sarin", "how to kill")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def echo_text(messages: list) -> str:
    last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    return f"[mock-llm] echo: {last_user[:400]}" if last_user else "[mock-llm] no user message"


def guard_verdict(messages: list) -> str:
    blob = " ".join(str(m.get("content", "")) for m in messages).lower()
    return "unsafe\nS1,S9" if any(k in blob for k in HAZARD_KEYWORDS) else "safe"


def log(level: str, msg: str) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "level": level, "component": "mock-llm", "msg": msg}), flush=True)


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 + Content-Length on every response keeps connections alive under load, so k6 VUs
    # reuse sockets instead of opening a new one per request.
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args) -> None:
        log("info", "%s - %s" % (self.address_string(), fmt % args))

    def _send(self, status: int, payload, content_type: str = "application/json") -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._send(200, {"status": "ok", "component": "mock-llm"})
        if path == "/v1/models":
            return self._send(200, {"object": "list", "data": [
                {"id": MODEL_DEFAULT, "object": "model", "created": int(time.time()), "owned_by": "noorpointer"}]})
        if path == "/api/tags":
            return self._send(200, {"models": [
                {"name": GUARD_MODEL, "model": GUARD_MODEL, "size": 0, "digest": "mock",
                 "modified_at": "2026-01-01T00:00:00Z"}]})
        return self._send(404, {"error": {"message": f"no such path: {path}", "type": "invalid_request_error"}})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        body = self._read_json()
        if body is None:
            return self._send(400, {"error": {"message": "invalid JSON", "type": "invalid_request_error"}})
        if path == "/v1/chat/completions":
            return self._chat_completions(body)
        if path == "/api/chat":
            return self._send(200, {"model": body.get("model", GUARD_MODEL),
                                    "message": {"role": "assistant",
                                                "content": guard_verdict(body.get("messages", []))},
                                    "done": True, "done_reason": "stop"})
        return self._send(404, {"error": {"message": f"no such path: {path}", "type": "invalid_request_error"}})

    def _chat_completions(self, body: dict) -> None:
        model = body.get("model") or MODEL_DEFAULT
        messages = body.get("messages", [])
        content = echo_text(messages)
        created = int(time.time())
        cid = f"chatcmpl-mock-{created}-{os.getpid()}"
        prompt_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
        completion_tokens = estimate_tokens(content)

        if body.get("stream"):
            # SSE is close-delimited (no Content-Length), so end the connection after the stream.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            def chunk(delta: dict, finish=None) -> None:
                payload = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                           "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                self.wfile.flush()

            chunk({"role": "assistant", "content": ""})
            chunk({"content": content})
            chunk({}, "stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        return self._send(200, {
            "id": cid, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                      "total_tokens": prompt_tokens + completion_tokens}})


class Server(ThreadingHTTPServer):
    """ThreadingHTTPServer with a listen backlog big enough for k6 ramps (default is 5, so bursts of
    new connections overflowed the accept queue and retried ~1s later - the benchmark tail)."""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 256


if __name__ == "__main__":
    port = int(os.getenv("PORT", "11434"))
    log("info", f"mock LLM listening on :{port} (model={MODEL_DEFAULT}, guard={GUARD_MODEL})")
    Server(("0.0.0.0", port), Handler).serve_forever()
