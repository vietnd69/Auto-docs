# llm/src/llm/client.py
import os
from pathlib import Path
from dotenv import load_dotenv
import httpx
import ollama

# Load .env từ workspace root (parents[3] từ llm/src/llm/client.py)
load_dotenv(Path(__file__).parents[3] / ".env")

# === OLLAMA CLOUD API ===
OLLAMA_HOST = "https://ollama.com"
OLLAMA_NUM_CTX = 256_000

OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "300"))      # seconds per attempt
OLLAMA_TIMEOUT_RETRIES = int(os.getenv("OLLAMA_TIMEOUT_RETRIES", "2"))  # retries on timeout

TOTAL_ACCOUNT = int(os.getenv("TOTAL_ACCOUNT", "0"))
OLLAMA_API_KEYS: list[str] = []
for _i in range(1, TOTAL_ACCOUNT + 1):
    _key = os.getenv(f"ACCOUNT_{_i}", "").strip()
    if _key:
        OLLAMA_API_KEYS.append(_key)

_account_counter = 0
_rate_limited: set[int] = set()


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
    Round-robin qua danh sách account, bỏ qua account đang bị rate limit.
    """
    global _account_counter
    if not OLLAMA_API_KEYS:
        return ollama.Client()
    n = len(OLLAMA_API_KEYS)
    for _ in range(n):
        idx = _account_counter % n
        _account_counter += 1
        if idx not in _rate_limited:
            return _make_client(idx)
    print(f"  [RATE LIMIT] Tất cả {n} account đều bị limit!")
    return _make_client(0)


def _is_rate_limit_error(error: Exception) -> bool:
    """Kiểm tra xem lỗi có phải rate limit (HTTP 429) không."""
    if isinstance(error, ollama.ResponseError):
        return error.status_code == 429
    return False


def _is_timeout_error(error: Exception) -> bool:
    """Kiểm tra xem lỗi có phải timeout không."""
    return isinstance(error, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException))


def ollama_chat(model: str, messages: list[dict], **kwargs) -> dict:
    """
    Wrapper gọi ollama chat với tự động failover khi bị rate limit,
    và retry khi timeout.
    """
    global _account_counter
    if not OLLAMA_API_KEYS:
        client = ollama.Client()
        return client.chat(model=model, messages=messages, think=True, stream=False, **kwargs)

    opts = kwargs.pop("options", {}) or {}
    opts["num_ctx"] = OLLAMA_NUM_CTX
    opts["mirostat"] = 2
    opts["mirostat_tau"] = 5.0
    opts["mirostat_eta"] = 0.1

    n = len(OLLAMA_API_KEYS)
    errors: list[str] = []

    # Outer loop: retry on timeout (up to OLLAMA_TIMEOUT_RETRIES extra attempts)
    for timeout_attempt in range(OLLAMA_TIMEOUT_RETRIES + 1):
        # Inner loop: failover across accounts on rate limit
        for attempt in range(n):
            idx = (_account_counter + attempt) % n
            if idx in _rate_limited:
                errors.append(f"Account {idx + 1}: đã bị limit")
                continue
            try:
                client = _make_client(idx)
                response = client.chat(model=model, messages=messages, options=opts, think=True, stream=False, **kwargs)
                _account_counter = idx + 1
                return response
            except Exception as e:
                if _is_rate_limit_error(e):
                    _rate_limited.add(idx)
                    print(f"  [RATE LIMIT] Account {idx + 1} bị 429 → chuyển account ({n - len(_rate_limited)} còn lại)")
                    errors.append(f"Account {idx + 1}: 429")
                elif _is_timeout_error(e):
                    remaining = OLLAMA_TIMEOUT_RETRIES - timeout_attempt
                    print(f"  [TIMEOUT] Account {idx + 1} timeout sau {OLLAMA_TIMEOUT:.0f}s → retry ({remaining} còn lại)")
                    errors.append(f"Account {idx + 1}: timeout")
                    break  # exit inner loop → outer loop retries
                else:
                    raise
        else:
            # All accounts rate-limited
            break

    _account_counter += n
    raise Exception(f"Tất cả account thất bại: {'; '.join(errors)}")


# === COMPRESSION CONFIG ===
COMPRESSION_MODEL = "qwen3.5:cloud"   # model dùng cho compression (có thể override)
