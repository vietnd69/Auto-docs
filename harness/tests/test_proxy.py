from __future__ import annotations

import json

import httpx
import pytest
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


@pytest.mark.parametrize("role", ["planner", "reviewer"])
def test_planner_falls_back_on_quota_but_reflector_does_not(settings_obj, monkeypatch, role):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deep-key")
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append((request.url.host, body["model"], request.headers["authorization"]))
        if request.url.host == "ollama.com":
            return httpx.Response(403, json={"error": "quota"})
        return httpx.Response(200, json={"choices": [], "usage": {"total_tokens": 7}})

    client, _, _ = make(settings_obj, handler, ["ollama-key"])
    with client:
        assert client.post("/v1/chat/completions", json={"model": role}).status_code == 200
        assert seen == [
            ("ollama.com", "gpt-oss:120b", "Bearer ollama-key"),
            ("api.deepseek.com", "deepseek-flash", "Bearer deep-key"),
        ]
        seen.clear()
        assert client.post("/v1/chat/completions", json={"model": "reflector"}).status_code == 403
        assert seen == [("ollama.com", "gemma4:31b", "Bearer ollama-key")]


def test_ollama_streams_share_one_slot(settings_obj):
    import asyncio

    active = maximum = 0

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            try:
                await asyncio.sleep(0.02)
                yield b'data: {"usage":{"total_tokens":1}}\n\ndata: [DONE]\n\n'
            finally:
                active -= 1

    def upstream(request):
        assert json.loads(request.content)["stream_options"]["include_usage"]
        return httpx.Response(200, stream=Stream())

    pool = KeyPool(["key"], lambda n, tried: 0, lambda i: None, lambda i, t: None)
    app = create_app(settings_obj, pool, httpx.MockTransport(upstream))

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            responses = await asyncio.gather(
                *[
                    client.post("/v1/chat/completions", json={"model": "reflector", "stream": True})
                    for _ in range(3)
                ]
            )
            assert all(r.status_code == 200 for r in responses)

    asyncio.run(exercise())
    assert maximum == 1


def test_stream_failure_releases_slot():
    import asyncio

    from starlette.responses import StreamingResponse

    from harness.proxy import SerialStream

    async def broken():
        yield b"partial"
        raise RuntimeError("upstream disconnected")

    async def exercise():
        slot = asyncio.Semaphore(1)
        await slot.acquire()
        response = SerialStream(StreamingResponse(broken()), slot)

        async def receive():
            return {"type": "http.disconnect"}

        async def send(message):
            pass

        with pytest.raises(RuntimeError, match="upstream disconnected"):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        await asyncio.wait_for(slot.acquire(), timeout=1)
        slot.release()

    asyncio.run(exercise())
