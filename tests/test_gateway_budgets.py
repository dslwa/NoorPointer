"""Acceptance of real gateway budget enforcement. A name in the JSON body is never an identity.

Token accounting uses the controlled provider's usage; cost/GPU cases use explicit trusted-provider
usage.cost_usd and usage.gpu_seconds extensions, documented in tests/GO_HANDOFF.md. No paid API is used.
Missing gateway accounting/reservation is FAIL, not a skip. All subjects are unique per test run.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading
import uuid

import pytest
import requests

from test_gateway_acceptance import gateway  # shared real-process fixture


def configure(gateway, metric="daily_tokens", limit=96, subject=None):
    with gateway["lock"]:
        doc = gateway["policy"]
        for name in ("prompt_injection", "content_safety", "agent_loops"):
            doc["controls"][name]["enabled"] = False
        doc["budgets"] = [{"subject": subject or "agent:" + gateway["agent_id"], metric: limit, "on_exceed": "block"}]
        doc["version"] += 1
        version = doc["version"]
    response = requests.post(gateway["url"] + "/admin/policy/reload",
                             headers={"Authorization": "Bearer test-gateway-token"}, timeout=5)
    assert response.status_code == 200 and response.json()["version"] == version, response.text


def call(gateway, token=None, model="fixture-safe", body_agent=None, headers=None):
    # Deliberately small inputs; the controlled provider accounts 12 input + 20 output tokens.
    return requests.post(gateway["url"] + "/v1/chat/completions",
                         headers={"Authorization": "Bearer " + (token or gateway["token"]), **(headers or {})},
                         json={"model": model, "messages": [{"role": "user", "content": "Hello."}],
                               "max_tokens": 20, "stream": False, "agent_id": body_agent or "untrusted-body-agent"},
                         timeout=10)


def assert_budget_block(response):
    assert response.status_code == 429, (response.status_code, response.text)
    assert response.json().get("code") == "BUDGET_EXCEEDED", response.text


def test_token_budget_is_actually_consumed_and_stays_exhausted(gateway):
    configure(gateway)
    first = call(gateway)
    assert first.status_code == 200, first.text
    assert first.json()["usage"]["total_tokens"] == 32
    responses = [first]
    for _ in range(3):
        responses.append(call(gateway))
        if responses[-1].status_code == 429:
            break
    assert_budget_block(responses[-1])
    used = sum(r.json()["usage"]["total_tokens"] for r in responses if r.status_code == 200)
    assert 0 < used <= 96
    reached = len(gateway["received"])
    assert reached == sum(r.status_code == 200 for r in responses)
    assert_budget_block(call(gateway))
    assert len(gateway["received"]) == reached, "Exhausted request was still billed by the model"


def test_concurrent_requests_do_not_overspend(gateway):
    configure(gateway)
    gateway["timings"]["delay_s"] = .1  # overlap upstream calls; counting only after completion is insufficient
    barrier = threading.Barrier(12)

    def worker(_):
        barrier.wait(timeout=5)
        return call(gateway)

    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(worker, range(12)))
    assert all(r.status_code in (200, 429) for r in responses), [(r.status_code, r.text) for r in responses]
    accepted = [r for r in responses if r.status_code == 200]
    assert accepted, "A budget that permits requests must not block all of them"
    assert len(accepted) * 32 <= 96, f"Overspend: {len(accepted) * 32} tokens against 96"
    assert len(gateway["received"]) == len(accepted), "A refused request reached the provider"
    for response in responses:
        if response.status_code == 429:
            assert_budget_block(response)


def test_body_agent_and_team_headers_cannot_bypass_authenticated_budget(gateway):
    configure(gateway, limit=0)
    response = call(gateway, body_agent="agent-with-unlimited-budget",
                    headers={"X-Agent-ID": "other", "X-Team-ID": "other", "X-Request-ID": uuid.uuid4().hex})
    assert_budget_block(response)
    assert gateway["received"] == []


def test_other_authenticated_agent_has_an_independent_budget(gateway):
    configure(gateway, limit=0)
    assert_budget_block(call(gateway))
    other = gateway["mint"]("other-" + uuid.uuid4().hex, gateway["team"])
    response = call(gateway, token=other)
    assert response.status_code == 200, response.text
    assert len(gateway["received"]) == 1


def test_team_budget_is_shared_by_distinct_authenticated_agents(gateway):
    configure(gateway, subject="team:" + gateway["team"], limit=32)
    response = call(gateway)
    assert response.status_code == 200, response.text
    other = gateway["mint"]("other-" + uuid.uuid4().hex, gateway["team"])
    assert_budget_block(call(gateway, token=other))
    assert len(gateway["received"]) == 1


def test_local_model_token_budget_uses_model_subject(gateway):
    model = "local/" + uuid.uuid4().hex
    gateway["answers"][model] = "Hello."
    gateway["policy"]["models"]["allowed"].append(model)
    configure(gateway, subject="model:" + model, limit=32)
    response = call(gateway, model=model)
    assert response.status_code == 200, response.text
    other = gateway["mint"]("other-" + uuid.uuid4().hex, "other-team")
    assert_budget_block(call(gateway, model=model, token=other))


@pytest.mark.parametrize("metric,usage_field,unit,limit", [
    ("monthly_usd", "cost_usd", .01, .03),
    ("gpu_seconds_per_hour", "gpu_seconds", .25, .75),
])
def test_provider_cost_and_local_compute_are_consumed(gateway, metric, usage_field, unit, limit):
    gateway["usage"][usage_field] = unit
    configure(gateway, metric=metric, limit=limit)
    accepted = []
    for _ in range(4):
        response = call(gateway)
        if response.status_code == 429:
            break
        assert response.status_code == 200, response.text
        accepted.append(response)
    assert accepted, "Expected an allowed request before budget exhaustion"
    assert_budget_block(response)
    assert sum(Decimal(str(r.json()["usage"][usage_field])) for r in accepted) <= Decimal(str(limit))
    assert len(gateway["received"]) == len(accepted)
