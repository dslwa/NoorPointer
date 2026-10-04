#!/usr/bin/env python3
"""Lossless literal feed validation/import. Uses only Python's standard library."""

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request
import uuid

TARGETS = {"prompt", "tool_name", "tool_arguments", "model_artifact", "upstream_path"}
FIELDS = {"id", "name", "source", "category", "action", "target", "match"}


def validate_rule(rule):
    if not isinstance(rule, dict) or not FIELDS <= rule.keys() or rule.keys() - FIELDS - {"description", "enabled"}:
        raise ValueError("Each rule must use the canonical signature schema; legacy regex feeds are not converted")
    for field, maximum in (("id", 120), ("name", 200), ("source", 1000), ("category", 80)):
        value = rule[field]
        if not isinstance(value, str) or not 1 <= len(value) <= maximum:
            raise ValueError(f"Invalid {field}")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", rule["id"]):
        raise ValueError("Invalid signature ID")
    if not rule["source"].startswith("https://") or not isinstance(rule["target"], str) or rule["target"] not in TARGETS:
        raise ValueError("Invalid source or target")
    if rule["action"] not in ("block", "monitor"):
        raise ValueError("Signature action must be block or monitor")
    match = rule["match"]
    if not isinstance(match, dict) or set(match) != {"type", "value"} or match["type"] != "literal":
        raise ValueError("Only explicit literal matches are supported; split alternatives into independent rules")
    if not isinstance(match["value"], str) or not 1 <= len(match["value"]) <= 2000:
        raise ValueError("Literal must contain 1..2000 characters")
    if "enabled" in rule and not isinstance(rule["enabled"], bool):
        raise ValueError("enabled must be boolean")
    if "description" in rule and (not isinstance(rule["description"], str) or len(rule["description"]) > 2000):
        raise ValueError("description must contain at most 2000 characters")
    return rule


def read_feeds(paths):
    merged = {}
    for path in paths:
        doc = json.loads(Path(path).read_text())
        if not isinstance(doc, dict) or set(doc) != {"signatures"} or not isinstance(doc["signatures"], list):
            raise ValueError(f"{path}: expected canonical {{signatures: [...]}} feed")
        seen = set()
        for rule in doc["signatures"]:
            validate_rule(rule)
            identifier = rule["id"]
            if identifier in seen or (identifier in merged and merged[identifier] != rule):
                raise ValueError(f"Duplicate/conflicting signature ID: {identifier}")
            seen.add(identifier)
            merged[identifier] = rule
    if len(merged) > 1000:
        raise ValueError("Feed exceeds 1000 rules")
    return list(merged.values())


def api(url, token, method="GET", body=None):
    request = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def import_feed(paths, url, token):
    # Validate the complete input and preflight existing IDs before any writes.
    rules = read_feeds(paths)
    existing = {r["id"]: r for r in api(url + "/api/v1/signature-feed", token)["signatures"]}
    if len(set(existing) | {r["id"] for r in rules}) > 1000:
        raise ValueError("Import would exceed the catalog limit of 1000 rules")
    for rule in rules:
        old = existing.get(rule["id"])
        if old is not None and old != rule:
            raise ValueError(f"Existing rule {rule['id']} differs. Use a new ID or explicitly edit the feed; nothing overwritten")
    created = 0
    for rule in rules:
        if rule["id"] in existing:
            continue
        try:
            api(url + "/api/v1/signatures", token, "POST", rule)
        except urllib.error.HTTPError as exc:
            if exc.code != 409:
                raise
            old = api(url + "/api/v1/signatures/" + rule["id"], token)
            if old != rule:
                raise ValueError(f"Concurrent signature conflict: {rule['id']}") from exc
        else:
            created += 1
    return created, len(rules) - created


def add_rule(path, rule):
    import fcntl
    path = Path(path)
    # Same-host concurrent demo commands must not lose each other's additions.
    with path.with_suffix(path.suffix + ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rules = read_feeds([path])
        validate_rule(rule)
        if any(r["id"] == rule["id"] for r in rules):
            raise ValueError(f"Signature ID already exists: {rule['id']}")
        if len(rules) >= 1000:
            raise ValueError("Feed exceeds 1000 rules")
        rules.append(rule)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
                temporary = handle.name
                json.dump({"signatures": rules}, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                os.fchmod(handle.fileno(), path.stat().st_mode & 0o777)
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "import", "add"])
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            print(f"Valid: {len(read_feeds(args.paths))} literal rules")
        elif args.command == "import":
            created, existing = import_feed(args.paths, os.getenv("CONTROLPLANE_URL", "http://localhost:8082").rstrip("/"),
                                            os.getenv("ADMIN_TOKEN", "local-dev-admin"))
            print(f"Signatures: {created} created, {existing} unchanged")
        else:
            if len(args.paths) != 1 or os.getenv("MATCH_TYPE", "literal") != "literal":
                raise ValueError("add expects one feed and MATCH_TYPE=literal; regex conversion is not supported")
            rule = {"id": os.getenv("NEW_ID") or "SIG-" + uuid.uuid4().hex[:16],
                    "name": os.getenv("NAME") or "Demo literal indicator",
                    "source": os.getenv("SOURCE") or "https://genai.owasp.org/llmrisk/llm01-prompt-injection/",
                    "category": os.getenv("CATEGORY") or "LLM01:2025",
                    "target": os.getenv("TARGET") or "prompt", "action": os.getenv("ACTION") or "block",
                    "match": {"type": "literal", "value": os.getenv("PATTERN") or "HACKATHON_ZERO_DAY_PAYLOAD_TEST"},
                    "description": os.getenv("DESCRIPTION") or "Locally defined demo indicator; not an official OWASP signature.",
                    "enabled": True}
            add_rule(args.paths[0], rule)
            print(f"Added {rule['id']} (literal, target={rule['target']})")
    except (ValueError, OSError, urllib.error.URLError) as exc:
        parser.exit(1, f"signature-feed: {exc}\n")


if __name__ == "__main__":
    main()
