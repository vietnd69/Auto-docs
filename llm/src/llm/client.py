# llm/src/llm/client.py
import os
import concurrent.futures as _futures
from pathlib import Path
from dotenv import load_dotenv
import httpx
import ollama
from llm.settings import OLLAMA_NUM_CTX, OLLAMA_TIMEOUT, OLLAMA_TIMEOUT_RETRIES
# Re-exported so rag/content.py can continue: from llm.client import COMPRESSION_MODEL
from llm.settings import MODEL_COMPRESS as COMPRESSION_MODEL
from llm.router import select_key, record_call, get_stats, mark_rate_limited, get_rate_limited

# Load .env từ workspace root (parents[3] từ llm/src/llm/client.py)
load_dotenv(Path(__file__).parents[3] / ".env")

# === OLLAMA CLOUD API ===
OLLAMA_HOST = "https://ollama.com"

TOTAL_ACCOUNT = int(os.getenv("TOTAL_ACCOUNT", "0"))
OLLAMA_API_KEYS: list[str] = []
for _i in range(1, TOTAL_ACCOUNT + 1):
    _key = os.getenv(f"ACCOUNT_{_i}", "").strip()
    if _key:
        OLLAMA_API_KEYS.append(_key)

def _make_client(account_index: int) -> ollama.Client:
    """Tạo ollama.Client cho account tại index."""
    api_key = OLLAMA_API_KEYS[account_index]
    return ollama.Client(
        host=OLLAMA_HOST,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=OLLAMA_TIMEOUT,
    )


def get_ollama_client() -> ollama.Client:
    """
    Trả về ollama.Client đã cấu hình host + API key.
    Chọn key ít tải nhất (least-loaded), bỏ qua key đang bị rate limit.
    """
    if not OLLAMA_API_KEYS:
        return ollama.Client()
    idx = select_key(len(OLLAMA_API_KEYS), set())
    if idx < 0:
        idx = 0
    return _make_client(idx)


def _is_rate_limit_error(error: Exception) -> bool:
    """Kiểm tra xem lỗi có phải rate limit (HTTP 429) không."""
    if isinstance(error, ollama.ResponseError):
        return error.status_code == 429
    return False


def _is_timeout_error(error: Exception) -> bool:
    """Kiểm tra xem lỗi có phải timeout hoặc connection drop không."""
    return isinstance(error, (
        httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException,
        httpx.RemoteProtocolError,  # "peer closed connection / incomplete chunked read"
    ))


def _is_retryable_error(error: Exception) -> bool:
    """Kiểm tra xem lỗi có thể retry không (500, 502 — transient server errors)."""
    if isinstance(error, ollama.ResponseError):
        return error.status_code in (500, 502)
    return False


def ollama_chat(model: str, messages: list[dict], *, think: bool = True,
                temperature: float | None = None,
                format: dict | str | None = None,
                **kwargs) -> dict:
    """
    Wrapper gọi ollama chat với tự động failover khi bị rate limit,
    và retry khi timeout.

    Args:
        model: Tên model Ollama.
        messages: Danh sách message theo định dạng chat.
        think: Bật/tắt extended thinking (mặc định True).
        temperature: Nhiệt độ sampling; None = dùng default của model.
        format: JSON schema hoặc "json" để ép Ollama trả về JSON.
        **kwargs: Tham số thêm truyền thẳng vào client.chat().
    """
    if not OLLAMA_API_KEYS:
        client = ollama.Client()
        chat_kwargs: dict = dict(model=model, messages=messages, think=think, stream=False)
        if format is not None:
            chat_kwargs["format"] = format
        if temperature is not None:
            chat_kwargs["options"] = {"temperature": temperature}
        return client.chat(**chat_kwargs, **kwargs)

    opts = kwargs.pop("options", {}) or {}
    opts["num_ctx"] = OLLAMA_NUM_CTX
    if temperature is not None:
        opts["temperature"] = temperature

    chat_extra: dict = {}
    if format is not None:
        chat_extra["format"] = format

    n = len(OLLAMA_API_KEYS)
    errors: list[str] = []

    # Outer loop: retry on timeout (up to OLLAMA_TIMEOUT_RETRIES extra attempts)
    for timeout_attempt in range(OLLAMA_TIMEOUT_RETRIES + 1):
        # Inner loop: failover across available accounts
        tried_this_round: set[int] = set()
        had_timeout = False
        for _ in range(n):
            idx = select_key(n, tried_this_round)
            if idx < 0:
                break  # không còn key khả dụng
            tried_this_round.add(idx)
            print(f"  [TRY] Account {idx + 1}...")
            try:
                client = _make_client(idx)
                # Wall-clock timeout: httpx read-timeout resets on each streamed token,
                # so a degraded server can stall forever. A thread-based hard limit prevents this.
                _wall = OLLAMA_TIMEOUT * 3
                _pool = _futures.ThreadPoolExecutor(max_workers=1)
                _fut = _pool.submit(
                    client.chat,
                    model=model, messages=messages, options=opts,
                    think=think, stream=False, **chat_extra, **kwargs,
                )
                _pool.shutdown(wait=False)
                try:
                    response = _fut.result(timeout=_wall)
                except _futures.TimeoutError:
                    raise httpx.ReadTimeout(f"wall-clock timeout {_wall:.0f}s")
                tokens = (getattr(response, "prompt_eval_count", None) or 0) + (getattr(response, "eval_count", None) or 0)
                record_call(idx, tokens)
                stats = get_stats()
                total = stats.get(idx, {}).get("total", 0)
                tokens_1h = stats.get(idx, {}).get("tokens_1h", 0)
                print(f"  [ROUTER] Account {idx + 1} | call #{total} | tokens_1h: {tokens_1h:,} (+{tokens:,})")
                return response
            except Exception as e:
                if _is_rate_limit_error(e):
                    mark_rate_limited(idx)
                    limited = get_rate_limited(n)
                    available = n - len(limited)
                    print(f"  [RATE LIMIT] Account {idx + 1} bị 429 → cooldown 5h ({available} còn lại)")
                    errors.append(f"Account {idx + 1}: 429")
                elif _is_timeout_error(e):
                    had_timeout = True
                    remaining = OLLAMA_TIMEOUT_RETRIES - timeout_attempt
                    print(f"  [TIMEOUT] Account {idx + 1} timeout sau {OLLAMA_TIMEOUT:.0f}s → switch account ({remaining} retry còn lại)")
                    errors.append(f"Account {idx + 1}: timeout")
                    # Không break — tiếp tục thử account khác trong round này
                elif _is_retryable_error(e):
                    status = e.status_code  # type: ignore[attr-defined]
                    print(f"  [SERVER ERROR] Account {idx + 1} trả về {status} → switch account")
                    errors.append(f"Account {idx + 1}: {status}")
                else:
                    raise
        # Tất cả account trong round đã thử — nếu có timeout, retry toàn bộ
        if had_timeout and timeout_attempt < OLLAMA_TIMEOUT_RETRIES:
            print(f"  [RETRY] Tất cả account đã thử, retry lần {timeout_attempt + 1}/{OLLAMA_TIMEOUT_RETRIES}...")
            continue
        break

    raise Exception(f"Tất cả account thất bại: {'; '.join(errors)}")


