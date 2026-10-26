"""Serial Ollama proxy with role aliases, planner/reviewer quota fallback and per-job accounting."""

from __future__ import annotations

import asyncio
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
from starlette.types import Receive, Scope, Send

from harness.config import Settings, settings
from harness.role_config import credentials

log = logging.getLogger("harness.proxy")
RETRY_STATUSES = frozenset({500, 502, 503, 504})


class SerialStream(StreamingResponse):
    """Release the shared slot even if upstream fails or the client disconnects."""

    def __init__(self, response: StreamingResponse, slot: asyncio.Semaphore) -> None:
        super().__init__(
            response.body_iterator, status_code=response.status_code, headers=dict(response.headers)
        )
        self.slot = slot

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.slot.release()


@dataclass
class KeyPool:
    """Injectable key selection; the runtime defaults to a single free account."""

    keys: list[str]
    select: Callable[[int, set[int]], int]
    on_rate_limit: Callable[[int], None]
    on_success: Callable[[int, int], None]


def default_pool(cfg: Settings) -> KeyPool:
    """One free account; never rotate across accounts to bypass its quota."""
    env = credentials(cfg)
    key = env.get("OLLAMA_API_KEY") or env.get("ACCOUNT_1", "")
    return KeyPool(
        [key] if key else [],
        lambda n, tried: 0 if n and 0 not in tried else -1,
        lambda _: None,
        lambda _i, _t: None,
    )


async def planner_fallback(
    cfg: Settings, client: httpx.AsyncClient, body: dict[str, Any]
) -> httpx.Response | None:
    key = credentials(cfg).get("DEEPSEEK_API_KEY")
    if not key:
        return None
    request = client.build_request(
        "POST",
        f"{cfg.get_str('deepseek_base_url').rstrip('/')}/chat/completions",
        json={**body, "model": cfg.get_str("deepseek_model"), "thinking": {"type": "disabled"}},
        headers={"Authorization": f"Bearer {key}"},
    )
    return await client.send(request, stream=True)


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


async def _json_response(response: httpx.Response, fwd: Forwarder, job: str, idx: int) -> Response:
    try:
        data = json.loads(await response.aread())
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": {"message": "upstream returned non-JSON response"}},
            response.status_code if response.is_error else 502,
        )
    finally:
        await response.aclose()
    tokens = _usage_tokens(data)
    fwd.budget.charge(job, tokens)
    fwd.pool.on_success(idx, tokens)
    return JSONResponse(data, response.status_code)


def _quota_response(response: httpx.Response | None, errors: list[str]) -> bool:
    if response is not None:
        return response.status_code in (402, 403, 429)
    return any("429" in error for error in errors)


def _route_body(cfg: Settings, body: dict[str, Any]) -> str:
    role = str(body.get("model", ""))
    aliases = {
        "planner": cfg.get_str("planner_model"),
        "reviewer": cfg.get_str("reviewer_model"),
        "reflector": cfg.get_str("reflector_model"),
        "writer-experimental": cfg.get_str("experimental_writer_model"),
    }
    body["model"] = aliases.get(role, role)
    if body.get("stream"):
        body["stream_options"] = {**body.get("stream_options", {}), "include_usage": True}
    return role


async def _with_fallback(
    cfg: Settings, fwd: Forwarder, body: dict[str, Any], role: str
) -> tuple[httpx.Response | None, int, list[str]]:
    response, idx, errors = await fwd.open(body)
    if role in ("planner", "reviewer") and _quota_response(response, errors):
        if response is not None:
            await response.aclose()
        response = await planner_fallback(cfg, fwd.client, body)
        idx = -1
    return response, idx, errors


def create_app(
    cfg: Settings | None = None,
    pool: KeyPool | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Starlette:
    cfg = cfg or settings()
    timeout = httpx.Timeout(cfg.get_float("request_timeout"), connect=30.0)
    client = httpx.AsyncClient(timeout=timeout, transport=transport)
    forwarder = Forwarder(cfg, pool or default_pool(cfg), client)
    # Shared by all roles/jobs; held until the entire SSE response has drained.
    ollama_slot = asyncio.Semaphore(1)

    async def chat(request: Request) -> Response:
        job = request.headers.get("x-harness-job", "")
        if forwarder.budget.exhausted(job):
            return JSONResponse({"error": {"message": "BUDGET_EXHAUSTED: job token budget spent"}}, 402)
        body = await request.json()
        role = _route_body(cfg, body)
        response, idx, errors = await _with_fallback(cfg, forwarder, body, role)
        if response is None:
            return JSONResponse({"error": {"message": "all keys failed: " + "; ".join(errors)}}, 503)
        if not body.get("stream"):
            return await _json_response(response, forwarder, job, idx)
        return StreamingResponse(
            _relay(response, forwarder, job, idx),
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "text/event-stream"),
        )

    async def serial_chat(request: Request) -> Response:
        await ollama_slot.acquire()
        try:
            response = await chat(request)
        except BaseException:
            ollama_slot.release()
            raise
        if isinstance(response, StreamingResponse):
            return SerialStream(response, ollama_slot)
        ollama_slot.release()
        return response

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
            Route("/v1/chat/completions", serial_chat, methods=["POST"]),
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
