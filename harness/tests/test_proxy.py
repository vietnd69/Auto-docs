from __future__ import annotations

import json

import httpx
from starlette.testclient import TestClient

from harness.config import Settings
from harness.proxy import KeyPool, create_app


def make(
    settings_obj: Settings, handler, keys: list[str]
) -> tuple[TestClient, list[int], list[tuple[int, int]]]:
    limited: list[int] = []
    success: list[tuple[int, int]] = []

    def select(n: int, tried: set[int]) -> int:
        free = [i for i in range(n) if i not in tried and i not in limited]
        return free[0] if free else -1

    pool = KeyPool(keys, select, limited.append, lambda i, t: success.append((i, t)))
    app = create_app(settings_obj, pool, httpx.MockTransport(handler))
    return TestClient(app), limited, success


def test_failover_on_429_then_success(settings_obj: Settings) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        if request.headers["authorization"] == "Bearer k1":
            return httpx.Response(429, json={"error": "rate"})
        return httpx.Response(
            200, json={"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 7}}
        )

    client, limited, success = make(settings_obj, handler, ["k1", "k2"])
    response = client.post(
        "/v1/chat/completions", json={"model": "m", "messages": []}, headers={"X-Harness-Job": "j"}
    )
    assert response.status_code == 200
    assert seen == ["Bearer k1", "Bearer k2"] and limited == [0] and success == [(1, 12)]
    assert client.get("/health").json()["jobs"] == {"j": 12}


def test_all_keys_fail_and_budget_stop(settings_obj: Settings) -> None:
    client, _, _ = make(settings_obj, lambda r: httpx.Response(503), ["k1", "k2"])
    response = client.post("/v1/chat/completions", json={"messages": []})
    assert response.status_code == 503 and "all keys failed" in response.text

    tiny = Settings(settings_obj.root, dict(settings_obj.values, max_tokens=10))
    body = {"usage": {"total_tokens": 50}}
    client, _, _ = make(tiny, lambda r: httpx.Response(200, json=body), ["k1"])
    headers = {"X-Harness-Job": "j"}
    assert client.post("/v1/chat/completions", json={}, headers=headers).status_code == 200
    stopped = client.post("/v1/chat/completions", json={}, headers=headers)
    assert stopped.status_code == 402 and "BUDGET_EXHAUSTED" in stopped.text


def test_streaming_relays_and_counts_usage(settings_obj: Settings) -> None:
    chunks = 'data: {"choices":[]}\n\ndata: {"usage":{"total_tokens":9}}\n\ndata: [DONE]\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks.encode(), headers={"content-type": "text/event-stream"})

    client, _, success = make(settings_obj, handler, ["k1"])
    response = client.post("/v1/chat/completions", json={"stream": True})
    assert "[DONE]" in response.text and success == [(0, 9)]
    models = client.get("/v1/models").json()
    assert models["data"][0]["id"] == settings_obj.get_str("model")


def test_timeout_moves_to_next_key(settings_obj: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["authorization"] == "Bearer k1":
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, content=json.dumps({"usage": {}}).encode())

    client, _, success = make(settings_obj, handler, ["k1", "k2"])
    assert client.post("/v1/chat/completions", json={}).status_code == 200
    assert success == [(1, 0)]
