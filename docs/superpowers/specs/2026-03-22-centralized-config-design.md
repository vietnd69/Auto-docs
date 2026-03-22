# Centralized Configuration — Design Spec

**Date:** 2026-03-22
**Status:** Approved

## Problem

Configuration parameters are currently scattered across 6+ locations:

| Constant | Location | Issue |
|---|---|---|
| `MODEL_NAME = "qwen3.5:cloud"` | `core/config.py`, `validator/constants.py`, `validator/pipeline.py` | 3 bản, 2 giá trị khác nhau |
| `COMPRESSION_MODEL = "qwen3.5:cloud"` | `llm/src/llm/client.py` | Hardcoded riêng, không liên kết với `MODEL_NAME` |
| `MDX_NODE_TIMEOUT = 20` | `core/config.py` + `validator/constants.py` | Trùng lặp hoàn toàn |
| `PROMPT_TOKEN_LIMIT = 16_000` | `core/pipeline/chunking.py` | — |
| `CHUNKED_TOKEN_THRESHOLD = 16_000` | `validator/pipeline.py` | Cùng giá trị nhưng định nghĩa lại |
| `CONTEXT_RESERVE`, `MERGE_TOKEN_LIMIT`, `STUB_FULL_THRESHOLD` | Mỗi cái 1 module | Không liên kết |
| `content_max_iterations = 10` vs `max_iterations = 5` | `pipeline.py` vs `content/loop.py` | Default khác nhau, dễ nhầm |
| `8_000` (lua context token guard) | `sections.py` dòng 139, 178 | Magic number hardcoded |

**Hệ quả:** Để thay đổi 1 tham số (ví dụ model name) phải sửa nhiều file, dễ bỏ sót, không có chỗ để nhìn tổng quan.

---

## Approach: `config.toml` + `llm/src/llm/settings.py`

### Lý do chọn approach này

- `llm` package là foundation layer — mọi package (`core`, `rag`, `validator`, `prompts`) đã depend vào `llm`. Thêm `settings.py` vào đây là zero new dependencies.
- Python 3.11 có `tomllib` built-in — không cần cài thêm thư viện.
- `config.toml` dễ đọc, có thể có comment, phân nhóm rõ ràng.
- Env override (`MOD_DOC_*`) cho phép runtime override mà không sửa file.

---

## Section 1: Architecture & File Structure

```
mod-document/
├── config.toml                      ← MỚI (git-excluded): file chỉnh tham số
├── config.toml.template             ← MỚI (git-tracked): template có comment
└── llm/src/llm/
    ├── settings.py                  ← MỚI: load TOML + env override, expose constants
    └── paths.py                     ← giữ nguyên (chỉ paths)
```

**Luồng load:**
```
config.toml
    ↓ tomllib.load()
llm/settings.py
    ↓ os.environ override (MOD_DOC_SECTION_KEY)
    ↓ expose typed constants
core/, rag/, validator/, prompts/
    ↓ from llm.settings import X
```

---

## Section 2: `config.toml` Schema

```toml
# mod-document configuration
# Env override: MOD_DOC_<SECTION>_<KEY> (uppercase)
# Example: MOD_DOC_MODEL_MAIN=qwen3-coder:cloud uv run mod-document

[model]
main     = "qwen3.5:cloud"             # Pipeline chính (doc gen + validator)
update   = "qwen3-coder-next:cloud"    # core/update/docs.py
embed    = "BAAI/bge-small-en-v1.5"   # RAG embedding model
compress = "qwen3.5:cloud"            # Compression stub generation (llm/client.py)

[tokens]
prompt_limit     = 16000   # Full prompt > limit → chunked doc gen
merge_limit      = 20000   # Chunk results > limit → hierarchical merge
context_reserve  = 7000    # Reserved cho connected content per chunk
stub_threshold   = 400     # File ≤ threshold → include full (không compress)
chunked_validate = 16000   # Lua tokens ≥ threshold → per-section validation
ollama_ctx       = 256000  # Ollama context window size

[timing]
chunk_sleep  = 10   # Giây chờ giữa các chunk LLM call
merge_sleep  = 40   # Giây chờ sau merge
normal_sleep = 20   # Giây chờ trong standard pipeline

[validator]
max_iterations      = 10    # PipelineConfig default (CLI entry point)
loop_max_iterations = 5     # ContentLoopConfig default (standalone)
mdx_timeout         = 20    # Timeout (giây) cho Node.js MDX validation
lua_context_tokens  = 8000  # Token guard cho Lua context extract per section
```

**Hai `max_iterations` khác nhau vì:**
- `max_iterations = 10` → `PipelineConfig.content_max_iterations` — dùng khi chạy `uv run python -m validator`
- `loop_max_iterations = 5` → `ContentLoopConfig.max_iterations` — default khi không truyền config

---

## Section 3: `llm/src/llm/settings.py` — Loading Logic

```python
import os
import tomllib
from llm.paths import PROJECT_ROOT

_CONFIG_PATH = PROJECT_ROOT / "config.toml"

def _load() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}

_cfg = _load()

def _get(section: str, key: str, default):
    """TOML value → env override MOD_DOC_SECTION_KEY → default."""
    env_key = f"MOD_DOC_{section.upper()}_{key.upper()}"
    toml_val = _cfg.get(section, {}).get(key, default)
    env_val = os.environ.get(env_key)
    if env_val is None:
        return toml_val
    return type(default)(env_val)

# === Model ===
MODEL_MAIN: str     = _get("model", "main",     "qwen3.5:cloud")
MODEL_UPDATE: str   = _get("model", "update",   "qwen3-coder-next:cloud")
MODEL_EMBED: str    = _get("model", "embed",    "BAAI/bge-small-en-v1.5")
MODEL_COMPRESS: str = _get("model", "compress", "qwen3.5:cloud")

# === Tokens ===
PROMPT_TOKEN_LIMIT: int      = _get("tokens", "prompt_limit",     16000)
MERGE_TOKEN_LIMIT: int       = _get("tokens", "merge_limit",      20000)
CONTEXT_RESERVE: int         = _get("tokens", "context_reserve",  7000)
STUB_FULL_THRESHOLD: int     = _get("tokens", "stub_threshold",   400)
CHUNKED_TOKEN_THRESHOLD: int = _get("tokens", "chunked_validate", 16000)
OLLAMA_NUM_CTX: int          = _get("tokens", "ollama_ctx",       256000)

# === Timing ===
CHUNK_SLEEP: int  = _get("timing", "chunk_sleep",  10)
MERGE_SLEEP: int  = _get("timing", "merge_sleep",  40)
NORMAL_SLEEP: int = _get("timing", "normal_sleep", 20)

# === Validator ===
VALIDATOR_MAX_ITERATIONS: int      = _get("validator", "max_iterations",      10)
VALIDATOR_LOOP_MAX_ITERATIONS: int = _get("validator", "loop_max_iterations", 5)
MDX_NODE_TIMEOUT: int              = _get("validator", "mdx_timeout",         20)
LUA_CONTEXT_TOKENS: int            = _get("validator", "lua_context_tokens",  8000)
```

**Graceful fallback:** Nếu `config.toml` không tồn tại (fresh clone), dùng default values. Không raise exception. `config.toml.template` và `.gitignore` phải được commit cùng nhau trong cùng 1 commit để mọi clone đều có template tham khảo.

**Type casting:** `type(default)(env_val)` — cast env string sang `int`/`float`/`str` dựa trên type của default.

**Giới hạn:** `type(default)(env_val)` KHÔNG hỗ trợ `bool` (`bool("false") == True` trong Python). Tất cả settings hiện tại đều là `int` hoặc `str` — không thêm `bool` defaults vào `_get()` mà không sửa hàm này trước.

---

## Section 4: Migration — Files Thay Đổi

### Files mới tạo
- `config.toml` — git-excluded, full config với values hiện tại
- `config.toml.template` — git-tracked, bản copy có comment
- `llm/src/llm/settings.py` — loading module

### Files xóa
- `validator/src/validator/constants.py` — toàn bộ nội dung chuyển sang `settings.py`

### Files rút gọn
- `core/src/core/config.py` — xóa `MODEL_NAME`, `MDX_NODE_TIMEOUT`, `CHUNK_SLEEP`, `MERGE_SLEEP`, `NORMAL_SLEEP`; chỉ giữ `get_shared_file_tree()`, `TODAY_DATE`, `CHECKPOINT_DIR`

### Files cập nhật import

| File | Thay đổi |
|---|---|
| `llm/src/llm/client.py` | `OLLAMA_NUM_CTX = 256_000` → `from llm.settings import OLLAMA_NUM_CTX`; `COMPRESSION_MODEL = "qwen3.5:cloud"` → `from llm.settings import MODEL_COMPRESS as COMPRESSION_MODEL` |
| `llm/src/llm/tokens.py` | `STUB_FULL_THRESHOLD = 400` → `from llm.settings import STUB_FULL_THRESHOLD` |
| `core/src/core/pipeline/chunking.py` | Xóa 3 constants, import từ `llm.settings` |
| `core/src/core/main.py` | Xóa `MODEL_NAME = config.MODEL_NAME` (dòng 54); thay bằng `from llm.settings import MODEL_MAIN as MODEL_NAME` ở top-level imports |
| `core/src/core/update/docs.py` | `from llm.settings import MODEL_UPDATE as MODEL_NAME` |
| `rag/src/rag/indexer.py` | `from llm.settings import MODEL_EMBED as EMBED_MODEL_NAME` |
| `validator/src/validator/pipeline.py` | Xóa module-level `CHUNKED_TOKEN_THRESHOLD = 16_000`; thêm `from llm.settings import CHUNKED_TOKEN_THRESHOLD, VALIDATOR_MAX_ITERATIONS`; dùng `VALIDATOR_MAX_ITERATIONS` làm default cho `PipelineConfig.content_max_iterations` |
| `validator/src/validator/content/loop.py` | Dùng `VALIDATOR_LOOP_MAX_ITERATIONS` làm default `ContentLoopConfig` |
| `validator/src/validator/content/sections.py` | `8_000` → `from llm.settings import LUA_CONTEXT_TOKENS` |
| `validator/src/validator/format/autofix.py` | `from llm.settings import MDX_NODE_TIMEOUT` |
| `validator/src/validator/format/mdx.py` | `from llm.settings import MDX_NODE_TIMEOUT` |

### Tests cập nhật

| File | Thay đổi |
|---|---|
| `validator/tests/test_smoke.py` | Đổi `from validator.constants import MDX_NODE_TIMEOUT, DEFAULT_MAX_ITERATIONS` → `from llm.settings import MDX_NODE_TIMEOUT, VALIDATOR_MAX_ITERATIONS`; đổi assertion `DEFAULT_MAX_ITERATIONS == 10` → `VALIDATOR_MAX_ITERATIONS == 10` |
| `rag/tests/test_require_stubs.py` | Import `STUB_FULL_THRESHOLD` từ `llm.settings` |
| `llm/tests/test_client.py` | Import `OLLAMA_NUM_CTX` từ `llm.settings` |
| `core/tests/test_per_chunk.py` | Import `CONTEXT_RESERVE` từ `llm.settings` |
| `validator/tests/test_pipeline.py` | Đổi `from validator.pipeline import ..., CHUNKED_TOKEN_THRESHOLD` → thêm `from llm.settings import CHUNKED_TOKEN_THRESHOLD` (import riêng, không còn re-exported từ `validator.pipeline`) |

---

## `.gitignore` Update

```gitignore
config.toml
```

`config.toml.template` được commit vào git.
