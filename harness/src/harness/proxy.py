"""OpenAI-compatible proxy in front of Ollama Cloud with multi-key failover.

OpenCode talks to ``http://127.0.0.1:<port>/v1``; each request is forwarded unchanged to
``ollama_base_url`` using the least-loaded API key (``llm.router``). 429 → key cooldown and
retry on the next key; timeouts/5xx → next key. A per-job token budget (header
``X-Harness-Job``) is enforced here as a hard stop independent of the agent (goal G7).
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from harness.config import Settings, settings

log = logging.getLogger("harness.proxy")
RETRY_STATUSES = frozenset({500, 502, 503, 504})


@dataclass
class KeyPool:
    """Key selection and bookkeeping; defaults delegate to ``llm.router``."""

    keys: list[str]
    select: Callable[[int, set[int]], int]
    on_rate_limit: Callable[[int], None]
    on_success: Callable[[int, int], None]


def default_pool() -> KeyPool:
    from llm.client import OLLAMA_API_KEYS
    from llm.router import mark_rate_limited, record_call, select_key

    return KeyPool(list(OLLAMA_API_KEYS), select_key, mark_rate_limited, record_call)


@dataclass
class Budget:
    limit: int
    used: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def exhausted(self, job: str) -> bool:
        return bool(job) and self.used[job] >= self.limit

    def charge(self, job: str, tokens: int) -> None:
        if job:
            self.used[job] += tokens


def _usage_tokens(payload: dict[str, Any]) -> int:
    usage = payload.get("usage") or {}
    return int(
        usage.get("total_tokens") or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
    )


class Forwarder:
    """Forward one chat request, failing over across keys."""

    def __init__(self, cfg: Settings, pool: KeyPool, client: httpx.AsyncClient) -> None:
        self.base = cfg.get_str("ollama_base_url").rstrip("/")
        self.pool = pool
        self.client = client
        self.budget = Budget(cfg.get_int("max_tokens"))

    async def open(self, body: dict[str, Any]) -> tuple[httpx.Response | None, int, list[str]]:
        tried: set[int] = set()
        errors: list[str] = []
        for _ in range(max(1, len(self.pool.keys))):
            idx = self.pool.select(len(self.pool.keys), tried) if self.pool.keys else -1
            if self.pool.keys and idx < 0:
                break
            tried.add(idx)
            headers = {"Authorization": f"Bearer {self.pool.keys[idx]}"} if idx >= 0 else {}
            request = self.client.build_request(
                "POST", f"{self.base}/chat/completions", json=body, headers=headers
            )
            try:
                response = await self.client.send(request, stream=True)
            except httpx.TimeoutException:
                errors.append(f"key {idx + 1}: timeout")
                continue
            if response.status_code == 429:
                await response.aclose()
                self.pool.on_rate_limit(idx)
                errors.append(f"key {idx + 1}: 429")
                continue
            if response.status_code in RETRY_STATUSES:
                await response.aclose()
                errors.append(f"key {idx + 1}: {response.status_code}")
                continue
            return response, idx, errors
        return None, -1, errors


def create_app(
    cfg: Settings | None = None,
    pool: KeyPool | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Starlette:
    cfg = cfg or settings()
    timeout = httpx.Timeout(cfg.get_float("request_timeout"), connect=30.0)
    client = httpx.AsyncClient(timeout=timeout, transport=transport)
    forwarder = Forwarder(cfg, pool or default_pool(), client)

    async def chat(request: Request) -> Response:
        job = request.headers.get("x-harness-job", "")
        if forwarder.budget.exhausted(job):
            return JSONResponse({"error": {"message": "BUDGET_EXHAUSTED: job token budget spent"}}, 402)
        body = await request.json()
        response, idx, errors = await forwarder.open(body)
        if response is None:
            return JSONResponse({"error": {"message": "all keys failed: " + "; ".join(errors)}}, 503)
        if not body.get("stream"):
            data = json.loads(await response.aread())
            await response.aclose()
            tokens = _usage_tokens(data)
            forwarder.budget.charge(job, tokens)
            forwarder.pool.on_success(idx, tokens)
            return JSONResponse(data, response.status_code)
        return StreamingResponse(
            _relay(response, forwarder, job, idx),
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "text/event-stream"),
        )

    async def models(_: Request) -> Response:
        model = cfg.get_str("model")
        return JSONResponse(
            {"object": "list", "data": [{"id": model, "object": "model", "owned_by": "ollama"}]}
        )

    async def health(_: Request) -> Response:
        return JSONResponse(
            {"ok": True, "keys": len(forwarder.pool.keys), "jobs": dict(forwarder.budget.used)}
        )

    return Starlette(
        routes=[
            Route("/v1/chat/completions", chat, methods=["POST"]),
            Route("/v1/models", models, methods=["GET"]),
            Route("/health", health, methods=["GET"]),
        ]
    )


async def _relay(response: httpx.Response, fwd: Forwarder, job: str, idx: int) -> AsyncIterator[bytes]:
    tokens = 0
    try:
        async for line in response.aiter_lines():
            if line.startswith("data: ") and '"usage"' in line:
                with contextlib.suppress(json.JSONDecodeError):
                    tokens = _usage_tokens(json.loads(line[6:])) or tokens
            yield (line + "\n").encode("utf-8")
    finally:
        await response.aclose()
        fwd.budget.charge(job, tokens)
        fwd.pool.on_success(idx, tokens)


def main() -> None:
    import uvicorn

    cfg = settings()
    host = cfg.get_str("proxy_host")
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("proxy must bind to loopback only (ISO/IEC 27001 A.8.28)")
    uvicorn.run(create_app(cfg), host=host, port=cfg.get_int("proxy_port"), log_level="warning")


if __name__ == "__main__":
    main()
