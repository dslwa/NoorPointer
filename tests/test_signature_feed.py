"""Importer tests against a local HTTP catalog; no Go/Java service or tokens required."""

import importlib.util
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("signature_feed", ROOT / "scripts/signature_feed.py")
feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feed)


def rule(identifier="test-rule", value="a|b", target="prompt"):
    return dict(id=identifier, name="Test", source="https://example.com/rule", category="test",
                action="block", target=target, match={"type": "literal", "value": value}, enabled=True)


def write_feed(tmp_path, rules):
    path = tmp_path / "feed.json"
    path.write_text(json.dumps({"signatures": rules}))
    return path


@pytest.fixture
def catalog():
    state, writes = {}, []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, status=200):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_GET(self):
            assert self.headers.get("Authorization") == "Bearer test-token"
            if self.path == "/api/v1/signature-feed":
                self.reply({"signatures": list(state.values())})
            else:
                identifier = self.path.rsplit("/", 1)[-1]
                self.reply(state.get(identifier, {}), 200 if identifier in state else 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            writes.append(body)
            if body["id"] in state:
                self.reply({}, 409)
            else:
                state[body["id"]] = body
                self.reply(body, 201)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state, writes
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_import_preserves_literal_and_target_and_is_idempotent(tmp_path, catalog):
    url, state, writes = catalog
    rules = [rule(), rule("tool", "../", "tool_arguments")]
    path = write_feed(tmp_path, rules)
    assert feed.import_feed([path], url, "test-token") == (2, 0)
    assert feed.import_feed([path], url, "test-token") == (0, 2)
    assert writes == rules and state["test-rule"]["match"]["value"] == "a|b"


@pytest.mark.parametrize("invalid", [
    {"id": "legacy", "pattern_type": "regex", "pattern": "(one|two)"},
    {**rule(), "match": {"type": "regex", "value": "(one|two)"}},
    {**rule(), "target": "ray_api"},
    {**rule(), "target": ["prompt"]},
    {**rule(), "action": "redact"},
    {**rule(), "enabled": "false"},
])
def test_invalid_feed_is_rejected_before_any_writes(tmp_path, catalog, invalid):
    url, _, writes = catalog
    path = write_feed(tmp_path, [rule("valid"), invalid])
    with pytest.raises(ValueError):
        feed.import_feed([path], url, "test-token")
    assert writes == []


def test_conflicting_id_preserves_existing_catalog(tmp_path, catalog):
    url, state, writes = catalog
    state["test-rule"] = rule(value="keep me")
    path = write_feed(tmp_path, [rule("new"), rule(value="different")])
    with pytest.raises(ValueError, match="differs"):
        feed.import_feed([path], url, "test-token")
    assert writes == [] and state["test-rule"]["match"]["value"] == "keep me"


def test_add_preserves_other_rules_and_rejects_duplicate_ids(tmp_path):
    path = write_feed(tmp_path, [rule()])
    feed.add_rule(path, rule("new"))
    original = path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        feed.add_rule(path, rule("new"))
    assert path.read_bytes() == original
    assert feed.read_feeds([path]) == [rule(), rule("new")]


def test_shipped_feed_has_explicit_targets_for_payloads():
    rules = feed.read_feeds([ROOT / "signatures-feed/signatures.json"])
    for value in ("/api/jobs/", "/api/job/submit", "../../", "/etc/passwd"):
        assert any(r["target"] == "prompt" and r["match"]["value"] == value for r in rules)
    assert any(r["target"] == "tool_arguments" and "posix.system" == r["match"]["value"] for r in rules)
