"""Acceptance: real Go binary + real semantic service + controlled policy/model HTTP server.

This does not modify the running control plane or the production gateway. Missing OUTPUT enforcement
is a FAIL, never an xfail. See README.md for the binary/image runner and semantic-service prerequisite.
"""

import base64
import copy
import hashlib
import json
import os
import socket
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


SECRET = "ghp_123456789012345678901234567890123456"
EMAIL = "anna.nowak@example.com"
SYSTEM = "You are a helpful assistant who answers questions in short paragraphs."
ANSWERS = {
    "fixture-safe": "Raport jest gotowy. Dziękuję.",
    "fixture-pii": f"📄 Kontakt: {EMAIL}. Raport jest gotowy.",
    "fixture-secret": f"Generated credential: {SECRET}",
    "fixture-unsafe": "You should kill your neighbor tonight; stab him while he is asleep.",
    "fixture-leak": SYSTEM,
}


def _jwt(private_key, agent="output-test", team="test"):
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    header = encode(b'{"alg":"RS256","typ":"JWT"}')
    claims = encode(json.dumps({"iss": "noorpointer-cp", "aud": "noorpointer-gateway",
                               "sub": agent, "team": team, "exp": int(time.time()) + 3600}).encode())
    signing = header + b"." + claims
    return (signing + b"." + encode(private_key.sign(signing, padding.PKCS1v15(), hashes.SHA256()))).decode()


@pytest.fixture
def gateway(tmp_path):
    binary = os.getenv("GATEWAY_BINARY")
    assert binary and Path(binary).is_file(), "Run tests/run_gateway_acceptance.py or set GATEWAY_BINARY"
    policy = {
        "version": 1,
        "defaults": {"mode": "enforce", "semantic_timeout_ms": 10_000, "on_semantic_timeout": "fail_closed"},
        "models": {"allowed": list(ANSWERS)},
        "controls": {
            "pii_regex": {"enabled": True, "action": "redact", "types": ["email", "pesel"]},
            "secrets": {"enabled": True, "action": "block"},
            # Isolate OUTPUT controls from known DeBERTa false positives on legitimate system instructions.
            # The separate real-model suite covers injection quality; no live policy is changed here.
            "prompt_injection": {"enabled": False, "action": "block", "threshold": .85},
            "content_safety": {"enabled": True, "action": "block", "categories": ["S1", "S2", "S9"]},
            "agent_loops": {"enabled": True, "action": "block", "max_steps": 25, "max_identical_tool_calls": 3},
        },
        "budgets": [],
    }
    lock = threading.Lock()
    received = []
    answers = dict(ANSWERS)
    usage = {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32}
    timings = {"delay_s": 0}
    signatures = {"signatures": []}
    events = []
    agent_id, team = "acceptance-" + uuid.uuid4().hex, "team-" + uuid.uuid4().hex

    class FixtureHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, value, status=200, etag=None):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if etag:
                self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path not in ("/api/gateway/policy", "/api/gateway/signatures"):
                return self.respond({"error": "unknown fixture route"}, 404)
            if self.headers.get("Authorization") != "Bearer test-gateway-token":
                return self.respond({"error": "unauthorized"}, 401)
            with lock:
                document = copy.deepcopy(policy if self.path.endswith("policy") else signatures)
            etag = '"' + hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest() + '"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.end_headers()
            else:
                self.respond(document, etag=etag)

        def do_POST(self):
            if self.path == "/api/gateway/events":
                event = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with lock:
                    events.append(event)
                return self.respond({"accepted": True})
            if self.path != "/v1/chat/completions":
                return self.respond({"error": "unknown fixture route"}, 404)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                received.append(body)
                answer = answers[body["model"]]
                reported_usage = dict(usage)
            time.sleep(timings["delay_s"])
            self.respond({"id": "fixture-completion", "object": "chat.completion", "created": 0,
                          "model": body["model"], "choices": [{"index": 0, "finish_reason": "stop",
                          "message": {"role": "assistant", "content": answer}}], "usage": reported_usage})

    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fixture_url = f"http://127.0.0.1:{server.server_port}"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = tmp_path / "jwt.pub"
    public_key.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo))
    with socket.socket() as socket_:
        socket_.bind(("127.0.0.1", 0))
        port = socket_.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PORT": str(port), "JWT_PUBLIC_KEY": str(public_key),
           "UPSTREAM_LLM_URL": fixture_url, "CONTROLPLANE_URL": fixture_url,
           "GATEWAY_TOKEN": "test-gateway-token",
           "REDIS_URL": os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
           "SEMANTIC_GRPC_URL": os.getenv("SEMANTIC_GRPC_URL", "127.0.0.1:50051")}
    process = None
    try:
        with (tmp_path / "gateway.log").open("w+") as log:
            process = subprocess.Popen([str(Path(binary).resolve())], env=env, stdout=log, stderr=log)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    if requests.get(url + "/readyz", timeout=.5).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.05)
            else:
                log.seek(0)
                pytest.fail("Test gateway did not start:\n" + log.read())
            yield {"url": url, "token": _jwt(key, agent_id, team), "received": received,
                   "policy": policy, "lock": lock, "process": process, "agent_id": agent_id, "team": team,
                   "signatures": signatures, "usage": usage, "answers": answers, "timings": timings,
                   "events": events, "mint": lambda agent, team_: _jwt(key, agent, team_)}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def chat(gateway, model, prompt="Please give a short answer."):
    return requests.post(gateway["url"] + "/v1/chat/completions",
                         headers={"Authorization": "Bearer " + gateway["token"]},
                         json={"model": model, "stream": False, "messages": [
                             {"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]},
                         timeout=65)


def load_signatures(gateway, rules):
    with gateway["lock"]:
        gateway["signatures"]["signatures"] = rules
        controls = gateway["policy"]["controls"]
        for name in ("prompt_injection", "content_safety", "agent_loops"):
            controls[name]["enabled"] = False
        controls["attack_signatures"] = {"enabled": True, "action": "block", "refresh_s": 60}
        gateway["policy"]["version"] += 1
    response = requests.post(gateway["url"] + "/admin/policy/reload",
                             headers={"Authorization": "Bearer test-gateway-token"}, timeout=5)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("target,text,expected", [
    ("prompt", "List active jobs.", 200),
    ("prompt", "POST /api/jobs/", 403),
    ("prompt", "Explain posix.system", 200),  # argument rule must not match the wrong target
    ("tool_arguments", "posix.system", 403),
])
def test_canonical_feed_matches_the_actual_request_field(gateway, target, text, expected):
    path = Path(__file__).resolve().parents[1] / "signatures-feed/signatures.json"
    load_signatures(gateway, json.loads(path.read_text())["signatures"])
    messages = [{"role": "user", "content": text if target == "prompt" else "Please inspect this call."}]
    if target == "tool_arguments":
        messages.extend([
            {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function",
             "function": {"name": "inspect", "arguments": json.dumps({"value": text})}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "Inspection complete."},
        ])
    response = requests.post(gateway["url"] + "/v1/chat/completions",
                             headers={"Authorization": "Bearer " + gateway["token"]},
                             json={"model": "fixture-safe", "messages": messages, "stream": False}, timeout=10)
    assert response.status_code == expected, response.text
    assert len(gateway["received"]) == (1 if expected == 200 else 0)
    if expected == 403:
        assert response.json()["code"] == "HISTORICAL_EXPLOIT_SIGNATURE_MATCHED", response.text


def test_signature_hot_reload_preserves_literal_alternation_text(gateway):
    rule = {"id": "literal-test", "name": "Literal test", "category": "test",
            "source": "https://example.com/test", "target": "prompt", "action": "block",
            "enabled": True, "match": {"type": "literal", "value": "first|second"}}
    load_signatures(gateway, [rule])
    for text, expected in (("first", 200), ("second", 200), ("first|second", 403)):
        response = chat(gateway, "fixture-safe", text)
        assert response.status_code == expected, response.text
    load_signatures(gateway, [{**rule, "enabled": False}])
    assert chat(gateway, "fixture-safe", "first|second").status_code == 200
    load_signatures(gateway, [rule])
    assert chat(gateway, "fixture-safe", "first|second").status_code == 403
    assert len(gateway["received"]) == 3


def test_safe_model_output_passes_unchanged(gateway):
    response = chat(gateway, "fixture-safe")
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == ANSWERS["fixture-safe"]
    assert len(gateway["received"]) == 1


@pytest.mark.parametrize("prompt,pii", [("Contact address: analyst@example.com.", "analyst@example.com"),
                                       ("My identification number is PESEL 44051401359.", "44051401359")])
def test_input_pii_is_redacted_before_model_receives_it(gateway, prompt, pii):
    response = chat(gateway, "fixture-safe", prompt)
    assert response.status_code == 200, response.text
    assert len(gateway["received"]) == 1
    forwarded = gateway["received"][0]["messages"][-1]["content"]
    assert pii not in forwarded and "[REDACTED" in forwarded, forwarded


def test_model_output_pii_redacted_on_benign_prompt(gateway):
    response = chat(gateway, "fixture-pii")
    assert len(gateway["received"]) == 1, "Input was blocked; OUTPUT was not exercised"
    assert response.status_code == 200, response.text
    text = response.json()["choices"][0]["message"]["content"]
    assert EMAIL not in response.text and "[REDACTED" in text, text
    assert text.startswith("📄 Kontakt: ") and text.endswith(". Raport jest gotowy."), text


@pytest.mark.parametrize("model", ["fixture-secret", "fixture-unsafe", "fixture-leak"])
def test_model_output_threat_blocked_on_benign_prompt(gateway, model):
    response = chat(gateway, model)
    assert len(gateway["received"]) == 1, "Input was blocked; OUTPUT was not exercised"
    sent = gateway["received"][0]
    assert sent["messages"][-1]["content"] == "Please give a short answer."
    assert response.status_code == 403, (model, response.status_code, response.text)
    assert ANSWERS[model] not in response.text, "Block response itself leaked the unsafe model answer"


def test_hot_reload_changes_verdict_without_process_restart(gateway):
    """Isolated Go test: a policy change must affect actual requests, including a reversal."""
    for version, action, expected in ((2, "redact", 200), (3, "block", 403), (4, "redact", 200)):
        with gateway["lock"]:
            gateway["policy"]["version"] = version
            gateway["policy"]["controls"]["pii_regex"]["action"] = action
        reload_ = requests.post(gateway["url"] + "/admin/policy/reload",
                                headers={"Authorization": "Bearer test-gateway-token"}, timeout=5)
        assert reload_.status_code == 200 and reload_.json()["version"] == version, reload_.text
        response = chat(gateway, "fixture-safe", "Contact address: analyst@example.com.")
        assert response.status_code == expected, response.text
        if action == "block":
            assert "PII_DETECTED" in response.text
        else:
            sent = gateway["received"][-1]["messages"][-1]["content"]
            assert "analyst@example.com" not in sent and "[REDACTED" in sent
        assert gateway["process"].poll() is None
    assert len(gateway["received"]) == 2, "Blocked request reached upstream"


@pytest.mark.parametrize("arguments,expected", [(["1+1", "2+2"], [200, 200]),
                                                (["1+1"] * 4, [200, 200, 200, 403])], ids=["distinct", "repeated"])
def test_real_tool_call_sequence(gateway, arguments, expected):
    # Test only the loop budget here. Arbitrary tool result strings are not a content-safety corpus.
    with gateway["lock"]:
        gateway["policy"]["controls"]["content_safety"]["enabled"] = False
        gateway["policy"]["version"] += 1
    reload_ = requests.post(gateway["url"] + "/admin/policy/reload",
                            headers={"Authorization": "Bearer test-gateway-token"}, timeout=5)
    assert reload_.status_code == 200, reload_.text
    session = uuid.uuid4().hex
    messages = [{"role": "user", "content": "Please calculate the total."}]
    responses = []
    for expression in arguments:
        call_id = "call_" + uuid.uuid4().hex
        messages.extend([
            {"role": "assistant", "content": "", "tool_calls": [{"id": call_id, "type": "function",
             "function": {"name": "calculator", "arguments": json.dumps({"expression": expression})}}]},
            {"role": "tool", "tool_call_id": call_id, "content": "Calculation completed."},
        ])
        response = requests.post(gateway["url"] + "/v1/chat/completions",
                                 headers={"Authorization": "Bearer " + gateway["token"], "X-Session-ID": session},
                                 json={"model": "fixture-safe", "messages": messages, "stream": False}, timeout=10)
        responses.append(response)
        if response.status_code != 200:
            break
    codes = [r.status_code for r in responses]
    if expected[-1] == 403:
        # Both "at limit" and "exceeds limit" conventions are accepted; a single call must pass.
        assert codes[0] == 200 and codes[-1] == 403 and len(codes) in (3, 4), codes
        assert "RUNAWAY_LOOP_DETECTED" in responses[-1].text, responses[-1].text
        assert len(gateway["received"]) == len(responses) - 1
    else:
        assert codes == expected, [(r.status_code, r.text) for r in responses]
        assert len(gateway["received"]) == 2
