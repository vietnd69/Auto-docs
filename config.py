# config.py
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import ollama

# Load .env từ thư mục project
load_dotenv(Path(__file__).parent / ".env")

# === PROJECT PATHS ===
# Sử dụng đường dẫn tuyệt đối để tránh lỗi khi chạy từ các thư mục con
PROJECT_ROOT = Path(__file__).parent.absolute()
BASE_LUA_DIR = str(PROJECT_ROOT / "dst-scripts")
BASE_DOCS_DIR = str(PROJECT_ROOT / "dst-api-webdocs" / "docs")

# === LLM CONFIG ===
MODEL_NAME = "qwen3-coder-next:cloud"
VERSION = "714014"
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")

# === OLLAMA CLOUD API ===
# Load API keys từ .env (ACCOUNT_1, ACCOUNT_2, ... ACCOUNT_N)
OLLAMA_HOST = "https://ollama.com"  # thư viện ollama tự thêm /api/chat
OLLAMA_NUM_CTX = 256_000  # Context length — phải set qua API, không dùng setting desktop

TOTAL_ACCOUNT = int(os.getenv("TOTAL_ACCOUNT", "0"))
OLLAMA_API_KEYS: list[str] = []
for _i in range(1, TOTAL_ACCOUNT + 1):
    _key = os.getenv(f"ACCOUNT_{_i}", "").strip()
    if _key:
        OLLAMA_API_KEYS.append(_key)

_account_counter = 0  # round-robin counter
# Account bị rate limit trong session hiện tại (không track thời gian reset vì là real-time)
_rate_limited: set[int] = set()


def _make_client(account_index: int) -> ollama.Client:
    """Tạo ollama.Client cho account tại index."""
    api_key = OLLAMA_API_KEYS[account_index]
    return ollama.Client(
        host=OLLAMA_HOST,
        headers={"Authorization": f"Bearer {api_key}"},
    )


def get_ollama_client() -> ollama.Client:
    """
    Trả về ollama.Client đã cấu hình host + API key.
    Round-robin qua danh sách account, bỏ qua account đang bị rate limit.
    Nếu không có API key nào, trả về client mặc định (local).
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

    # Tất cả đều bị rate limit
    print(f"  [RATE LIMIT] Tất cả {n} account đều bị limit!")
    # Dùng account đầu tiên (có thể đã reset)
    return _make_client(0)


def _is_rate_limit_error(error: Exception) -> bool:
    """Kiểm tra xem lỗi có phải rate limit (HTTP 429) không."""
    if isinstance(error, ollama.ResponseError):
        return error.status_code == 429
    return False


def ollama_chat(
    model: str,
    messages: list[dict],
    **kwargs,
) -> dict:
    """
    Wrapper gọi ollama chat với tự động failover khi bị rate limit.
    Khi account bị 429 → đánh dấu "dead" cho session → chuyển account tiếp.

    Args:
        model: Tên model (vd: "qwen3-coder-next:cloud")
        messages: Danh sách messages cho chat API
        **kwargs: Các tham số khác truyền thẳng cho client.chat()

    Returns:
        Response dict từ Ollama API

    Raises:
        Exception: Khi tất cả account đều bị rate limit
    """
    global _account_counter

    if not OLLAMA_API_KEYS:
        client = ollama.Client()
        return client.chat(model=model, messages=messages, **kwargs)

    # Luôn truyền num_ctx, không để Ollama dùng default
    opts = kwargs.pop("options", {}) or {}
    opts["num_ctx"] = OLLAMA_NUM_CTX
    opts["repeat_penalty"] = 1.15
    opts["repeat_last_n"] = 256
    opts["top_k"] = 40
    opts["frequency_penalty"] = 0.8
    opts["presence_penalty"] = 0.6
    opts["mirostat"] = 2
    opts["mirostat_tau"] = 5.0
    opts["mirostat_eta"] = 0.1

    n = len(OLLAMA_API_KEYS)
    errors: list[str] = []

    for attempt in range(n):
        idx = (_account_counter + attempt) % n

        if idx in _rate_limited:
            errors.append(f"Account {idx + 1}: đã bị limit")
            continue

        try:
            client = _make_client(idx)
            response = client.chat(model=model, messages=messages, options=opts, **kwargs)
            _account_counter = idx + 1
            return response

        except Exception as e:
            if _is_rate_limit_error(e):
                _rate_limited.add(idx)
                print(f"  [RATE LIMIT] Account {idx + 1} bị 429 → chuyển account ({n - len(_rate_limited)} còn lại)")
                errors.append(f"Account {idx + 1}: 429")
            else:
                raise

    _account_counter += n
    error_detail = "; ".join(errors)
    raise Exception(f"Tất cả {n} account đều bị rate limit: {error_detail}")


# === VALIDATOR & CACHE ===
MDX_NODE_TIMEOUT = 20
CHECKPOINT_DIR = str(PROJECT_ROOT / ".cache" / "chunked_checkpoints")

# === TIMING ===
# Thời gian nghỉ (giây) để tránh rate limit
CHUNK_SLEEP = 10
MERGE_SLEEP = 40
NORMAL_SLEEP = 20

# === HELPER ===
def get_shared_file_tree(max_depth=3):
    """Sinh cây thư mục thu gọn cho prompt content."""
    from get_tree import generate_slim_tree
    return generate_slim_tree(BASE_LUA_DIR, max_depth=max_depth)
