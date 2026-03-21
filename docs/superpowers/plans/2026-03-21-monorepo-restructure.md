# Monorepo Restructure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tái cấu trúc ~25 Python file phẳng ở root thành Python monorepo gồm 6 packages độc lập (llm, core, rag, prompts, watcher, validator).

**Architecture:** uv workspace với 6 packages, mỗi package có `src/` layout và `tests/` riêng. Dependency graph theo tầng không có cycle: `llm` (base) ← `prompts` / `rag` / `watcher` ← `core`. Spec đầy đủ tại `docs/superpowers/specs/2026-03-21-monorepo-restructure-design.md`.

**Tech Stack:** Python 3.11+, uv workspace, pytest, tiktoken, ollama, llama-index, chromadb, pyyaml, python-dotenv

---

## Chunk 1: Scaffolding — pyproject.toml, data/, .gitignore

### Task 1: Baseline — chạy test hiện tại để có điểm so sánh

**Files:**
- Read: `requirements.txt`

- [x] **Step 1: Chạy toàn bộ test ở root để thiết lập baseline**

```bash
cd d:/code/mod-document
.venv/Scripts/activate
python -m pytest test_per_chunk.py test_pre_synthesis.py test_chunk_prompts.py test_events_section.py test_file_type_detection.py test_skills_loader.py test_require_stubs.py -v 2>&1 | head -60
```

Ghi lại số test PASSED/FAILED để so sánh sau khi migration.

---

### Task 2: Root workspace `pyproject.toml`

**Files:**
- Create: `pyproject.toml`

- [x] **Step 1: Tạo root `pyproject.toml`**

```toml
[tool.uv.workspace]
members = ["llm", "core", "rag", "prompts", "watcher", "validator"]

[tool.uv]
dev-dependencies = ["pytest>=8.0"]
```

- [x] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add uv workspace root config"
```

---

### Task 3: Tạo scaffold cho 5 packages mới

**Files:**
- Create: `llm/pyproject.toml`, `llm/src/llm/__init__.py`, `llm/tests/.gitkeep`
- Create: `rag/pyproject.toml`, `rag/src/rag/__init__.py`, `rag/tests/.gitkeep`
- Create: `prompts/pyproject.toml`, `prompts/src/prompts/__init__.py`, `prompts/tests/.gitkeep`
- Create: `watcher/pyproject.toml`, `watcher/src/watcher/__init__.py`, `watcher/tests/.gitkeep`, `watcher/scripts/.gitkeep`
- Create: `core/pyproject.toml`, `core/src/core/__init__.py`, `core/src/core/pipeline/__init__.py`, `core/src/core/update/__init__.py`, `core/src/core/utils/__init__.py`, `core/tests/.gitkeep`

- [x] **Step 1: Tạo `llm/pyproject.toml`**

```toml
[project]
name = "mod-document-llm"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["ollama", "tiktoken", "python-dotenv"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [x] **Step 2: Tạo `rag/pyproject.toml`**

```toml
[project]
name = "mod-document-rag"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mod-document-llm",
    "llama-index-core",
    "llama-index-vector-stores-chroma",
    "llama-index-embeddings-huggingface",
    "llama-index-llms-ollama",
    "chromadb",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [x] **Step 3: Tạo `prompts/pyproject.toml`**

```toml
[project]
name = "mod-document-prompts"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["mod-document-llm", "pyyaml"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [x] **Step 4: Tạo `watcher/pyproject.toml`**

```toml
[project]
name = "mod-document-watcher"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
mod-watcher = "watcher.diff:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [x] **Step 5: Tạo `core/pyproject.toml`**

```toml
[project]
name = "mod-document-core"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mod-document-llm",
    "mod-document-rag",
    "mod-document-prompts",
    "mod-document-validator",
    "python-frontmatter",
    "emoji",
]

[project.scripts]
mod-document = "core.main:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [x] **Step 6: Tạo `__init__.py` cho tất cả packages**

```bash
# Tạo thư mục và __init__.py trống
mkdir -p llm/src/llm llm/tests
mkdir -p rag/src/rag rag/tests
mkdir -p prompts/src/prompts prompts/tests
mkdir -p watcher/src/watcher watcher/tests watcher/scripts
mkdir -p core/src/core/pipeline core/src/core/update core/src/core/utils core/tests

touch llm/src/llm/__init__.py
touch rag/src/rag/__init__.py
touch prompts/src/prompts/__init__.py
touch watcher/src/watcher/__init__.py
touch core/src/core/__init__.py
touch core/src/core/pipeline/__init__.py
touch core/src/core/update/__init__.py
touch core/src/core/utils/__init__.py
```

- [x] **Step 7: Commit scaffolding**

```bash
git add llm/ rag/ prompts/ watcher/ core/
git commit -m "chore: scaffold 5 new packages with pyproject.toml and src layout"
```

---

### Task 4: `validator/pyproject.toml` và data migration

**Files:**
- Create: `validator/pyproject.toml`
- Create: `data/` directory
- Modify: `.gitignore`

- [x] **Step 1: Tạo `validator/pyproject.toml`**

```toml
[project]
name = "mod-document-validator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["python-frontmatter", "emoji"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["validator*"]
```

- [x] **Step 2: Tạo `data/` và di chuyển runtime files**

```bash
mkdir -p data
# Di chuyển runtime files (nếu tồn tại)
[ -f diff_tracker.json ] && mv diff_tracker.json data/
[ -f file_tracker.json ] && mv file_tracker.json data/
[ -f diff_report.json ] && mv diff_report.json data/
[ -f version_log.txt ] && mv version_log.txt data/
[ -f diff_log.txt ] && mv diff_log.txt data/
```

- [x] **Step 3: Cập nhật `.gitignore`**

Thêm vào `.gitignore` (tạo nếu chưa có):

```
# Runtime data (auto-generated)
data/diff_tracker.json
data/file_tracker.json
data/diff_report.json
data/diff_log.txt

# Caches & temp
tmp/
dst_chroma_db/
.cache/
__pycache__/
*.pyc
.venv/
```

- [x] **Step 4: Commit**

```bash
git add validator/pyproject.toml data/ .gitignore
git commit -m "chore: add validator pyproject.toml, create data/ dir, update .gitignore"
```

> **Note:** Chunk 1 committed as single commit `83cf775` on branch `feat/monorepo-restructure`.
> Fix applied: `validator/pyproject.toml` changed from `packages.find` (broken for flat layout) to explicit `packages + package-dir`.

---

## Chunk 2: llm/ package

### Task 5: `llm/paths.py` — shared path constants

**Files:**
- Create: `llm/src/llm/paths.py`

- [x] **Step 1: Tạo `llm/src/llm/paths.py`**

Tách từ `config.py` lines 14–16:

```python
# llm/src/llm/paths.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3].absolute()
BASE_LUA_DIR = str(PROJECT_ROOT / "dst-scripts")
BASE_DOCS_DIR = str(PROJECT_ROOT / "dst-api-webdocs" / "docs")
```

**Lưu ý:** `parents[3]` từ `llm/src/llm/paths.py` = workspace root.

- [x] **Step 2: Viết test**

Tạo `llm/tests/test_paths.py`:

```python
from llm.paths import PROJECT_ROOT, BASE_LUA_DIR, BASE_DOCS_DIR
from pathlib import Path

def test_project_root_exists():
    assert PROJECT_ROOT.exists()

def test_base_lua_dir_is_absolute():
    assert Path(BASE_LUA_DIR).is_absolute()
    assert "dst-scripts" in BASE_LUA_DIR

def test_base_docs_dir_is_absolute():
    assert Path(BASE_DOCS_DIR).is_absolute()
    assert "dst-api-webdocs" in BASE_DOCS_DIR
```

- [x] **Step 3: Chạy test (cần cài package trước)**

```bash
cd d:/code/mod-document
pip install -e llm/ --quiet
python -m pytest llm/tests/test_paths.py -v
```

Expected: PASS

- [x] **Step 4: Commit**

```bash
git add llm/src/llm/paths.py llm/tests/test_paths.py
git commit -m "feat(llm): add paths.py with PROJECT_ROOT, BASE_LUA_DIR, BASE_DOCS_DIR"
```

---

### Task 6: `llm/tokens.py` — token counting utilities

**Files:**
- Create: `llm/src/llm/tokens.py`

- [x] **Step 1: Tạo `llm/src/llm/tokens.py`**

Tách từ `chunked.py` functions `count_tokens` (lines 182–193) và `estimate_merge_tokens` (lines 196–205):

```python
# llm/src/llm/tokens.py
try:
    import tiktoken
except ImportError:
    tiktoken = None


def count_tokens(text: str) -> int:
    """
    Đếm số token của một chuỗi text bằng tiktoken.
    Trả về -1 nếu không có tiktoken (fallback sang đếm dòng).
    """
    if tiktoken:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass
    return -1


def estimate_merge_tokens(chunk_results: list[str]) -> int:
    """
    Ước tính tổng số token của tất cả chunk results.
    Dùng để quyết định strategy trước khi gọi LLM merge.

    Returns:
        Số token ước tính. -1 nếu không có tiktoken.
    """
    combined = "\n".join(chunk_results)
    return count_tokens(combined)
```

- [x] **Step 2: Viết test**

Tạo `llm/tests/test_tokens.py`:

```python
from llm.tokens import count_tokens, estimate_merge_tokens

def test_count_tokens_returns_int():
    result = count_tokens("hello world")
    assert isinstance(result, int)
    assert result == -1 or result > 0

def test_count_tokens_empty_string():
    result = count_tokens("")
    assert result >= 0 or result == -1

def test_estimate_merge_tokens_empty():
    result = estimate_merge_tokens([])
    assert result == -1 or result >= 0

def test_estimate_merge_tokens_list():
    result = estimate_merge_tokens(["hello", "world"])
    assert isinstance(result, int)
```

- [x] **Step 3: Chạy test**

```bash
pip install -e llm/ --quiet
python -m pytest llm/tests/test_tokens.py -v
```

Expected: PASS

- [x] **Step 4: Commit**

```bash
git add llm/src/llm/tokens.py llm/tests/test_tokens.py
git commit -m "feat(llm): add tokens.py with count_tokens and estimate_merge_tokens"
```

---

### Task 7: `llm/client.py` — Ollama API client với failover

**Files:**
- Create: `llm/src/llm/client.py`

- [x] **Step 1: Tạo `llm/src/llm/client.py`**

Tách từ `config.py` lines 27–149 (toàn bộ phần Ollama Cloud API):

```python
# llm/src/llm/client.py
import os
from pathlib import Path
from dotenv import load_dotenv
import ollama

# Load .env từ workspace root (parents[3] từ llm/src/llm/client.py)
load_dotenv(Path(__file__).parents[3] / ".env")

# === OLLAMA CLOUD API ===
OLLAMA_HOST = "https://ollama.com"
OLLAMA_NUM_CTX = 256_000

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


def ollama_chat(model: str, messages: list[dict], **kwargs) -> dict:
    """
    Wrapper gọi ollama chat với tự động failover khi bị rate limit.
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
            else:
                raise

    _account_counter += n
    raise Exception(f"Tất cả {n} account đều bị rate limit: {'; '.join(errors)}")
```

- [x] **Step 2: Viết test**

Tạo `llm/tests/test_client.py`:

```python
from llm.client import (
    OLLAMA_HOST, OLLAMA_NUM_CTX,
    OLLAMA_API_KEYS, get_ollama_client,
    _is_rate_limit_error,
)
import ollama

def test_ollama_host_is_string():
    assert isinstance(OLLAMA_HOST, str)
    assert OLLAMA_HOST.startswith("http")

def test_num_ctx_is_large_int():
    assert isinstance(OLLAMA_NUM_CTX, int)
    assert OLLAMA_NUM_CTX >= 32_000

def test_api_keys_is_list():
    assert isinstance(OLLAMA_API_KEYS, list)

def test_get_ollama_client_returns_client():
    client = get_ollama_client()
    assert isinstance(client, ollama.Client)

def test_rate_limit_detection_negative():
    assert _is_rate_limit_error(ValueError("not rate limit")) is False
```

- [x] **Step 3: Chạy test**

```bash
pip install -e llm/ --quiet
python -m pytest llm/tests/test_client.py -v
```

Expected: PASS

- [x] **Step 4: Update `llm/src/llm/__init__.py`**

```python
# llm/src/llm/__init__.py
from llm.client import ollama_chat, get_ollama_client
from llm.tokens import count_tokens, estimate_merge_tokens
from llm.paths import PROJECT_ROOT, BASE_LUA_DIR, BASE_DOCS_DIR
```

- [x] **Step 5: Commit**

```bash
git add llm/src/llm/client.py llm/tests/test_client.py llm/src/llm/__init__.py
git commit -m "feat(llm): add client.py with ollama_chat and round-robin failover"
```

---

## Chunk 3: watcher/ package

### Task 8: `watcher/diff.py` — phát hiện thay đổi .lua

**Files:**
- Create: `watcher/src/watcher/diff.py` (từ `get_diff_update.py`)
- Create: `watcher/src/watcher/hash.py` (từ `patch_hash.py`)
- Move: `simulate_changes.py` → `watcher/scripts/simulate_changes.py`

- [x] **Step 1: Copy `get_diff_update.py` → `watcher/src/watcher/diff.py`**

```bash
cp get_diff_update.py watcher/src/watcher/diff.py
```

- [x] **Step 2: Cập nhật path constants trong `watcher/src/watcher/diff.py`**

Tìm các dòng khai báo path cứng và thay bằng dynamic resolution. Thêm import `from pathlib import Path` nếu chưa có, sau đó:

```python
# Thay:
# DIFF_TRACKER = "./diff_tracker.json"
# DIFF_LOG = "./diff_log.txt"
# DIFF_REPORT = "./diff_report.json"
# VERSION_LOG = "./version_log.txt"
# SCRIPTS_DIR = "./dst-scripts"

# Thành:
_WORKSPACE_ROOT = Path(__file__).parents[3]
_DATA_DIR = _WORKSPACE_ROOT / "data"
DIFF_TRACKER = str(_DATA_DIR / "diff_tracker.json")
DIFF_LOG = str(_DATA_DIR / "diff_log.txt")
DIFF_REPORT = str(_DATA_DIR / "diff_report.json")
VERSION_LOG = str(_DATA_DIR / "version_log.txt")
SCRIPTS_DIR = str(_WORKSPACE_ROOT / "dst-scripts")
```

- [x] **Step 3: Thêm `main()` entry point ở cuối file** (nếu chưa có)

```python
def main():
    """Entry point for mod-watcher CLI."""
    run()   # gọi hàm chính của script — thay "run()" bằng tên hàm thực tế trong get_diff_update.py
```

- [x] **Step 4: Copy `patch_hash.py` → `watcher/src/watcher/hash.py`**

```bash
cp patch_hash.py watcher/src/watcher/hash.py
```

Cập nhật path nếu `patch_hash.py` có hardcoded paths (kiểm tra và sửa tương tự Task 8 Step 2).

- [x] **Step 5: Copy `simulate_changes.py` → `watcher/scripts/simulate_changes.py`**

```bash
cp simulate_changes.py watcher/scripts/simulate_changes.py
```

Cập nhật `SCRIPTS_DIR` trong file:

```python
# Thay:
# SCRIPTS_DIR = "dst-scripts/prefabs"

# Thành:
from pathlib import Path
_WORKSPACE_ROOT = Path(__file__).parents[2]
SCRIPTS_DIR = str(_WORKSPACE_ROOT / "dst-scripts" / "prefabs")
```

- [x] **Step 6: Kiểm tra import watcher package**

```bash
pip install -e watcher/ --quiet
python -c "from watcher.diff import DIFF_TRACKER, DIFF_REPORT; print('OK:', DIFF_TRACKER)"
python -c "from watcher.hash import PATCH_CONFIGS; print('OK')"
```

Expected: In ra paths chính xác trỏ vào `data/`

- [x] **Step 7: Commit**

```bash
git add watcher/src/watcher/ watcher/scripts/
git commit -m "feat(watcher): add diff.py and hash.py with dynamic data/ path resolution"
```

> **Note:** Chunk 3 committed as `1e0c9f3` + `5bbd0dc` (docstring fix) on branch `feat/monorepo-restructure`.
> Extra fix: `.gitignore` negation rule added for `watcher/scripts/simulate_changes.py` (blocked by existing `simulate**` pattern).

---

## Chunk 4: prompts/ package

### Task 9: `prompts/skills_loader.py` — load skill markdown files

**Files:**
- Create: `prompts/src/prompts/skills_loader.py` (từ `skills_loader.py`)
- Move: `docs_SKILL.md` → `skills/docs_SKILL.md`

- [x] **Step 1: Move `docs_SKILL.md` vào `skills/`**

```bash
mv docs_SKILL.md skills/docs_SKILL.md
```

- [x] **Step 2: Copy `skills_loader.py` → `prompts/src/prompts/skills_loader.py`**

```bash
cp skills_loader.py prompts/src/prompts/skills_loader.py
```

- [x] **Step 3: Cập nhật `_DEFAULT_INDEX` trong `prompts/src/prompts/skills_loader.py`**

Tìm dòng 11:
```python
# Thay:
_DEFAULT_INDEX = _os.path.join(_os.path.dirname(__file__), "docs_SKILL.md")

# Thành:
from pathlib import Path as _Path
_DEFAULT_INDEX = str(_Path(__file__).parents[3] / "skills" / "docs_SKILL.md")
```

**Lưu ý:** `parents[3]` từ `prompts/src/prompts/skills_loader.py` = workspace root. `skills/docs_SKILL.md` sẽ resolve đúng vì `load_skill` dùng `root = Path(index_path).parent` = `skills/`, và các skill files (`dst_conventions.md`, v.v.) đều nằm trong `skills/`.

- [x] **Step 4: Chạy test cũ để verify**

```bash
pip install -e prompts/ --quiet
python -m pytest test_skills_loader.py -v
```

Expected: PASS (test vẫn import từ `skills_loader` ở root, kiểm tra logic chưa bị phá)

- [x] **Step 5: Copy test → `prompts/tests/test_skills_loader.py`**

```bash
cp test_skills_loader.py prompts/tests/test_skills_loader.py
```

Cập nhật import trong test file:

```python
# Thay: from skills_loader import ...
# Thành:
from prompts.skills_loader import load_skill, load_skills_for
```

- [x] **Step 6: Chạy test từ package mới**

```bash
python -m pytest prompts/tests/test_skills_loader.py -v
```

Expected: PASS

- [x] **Step 7: Commit** *(deferred — will commit all Chunk 4 together)*

```bash
git add prompts/src/prompts/skills_loader.py prompts/tests/test_skills_loader.py skills/docs_SKILL.md
git commit -m "feat(prompts): add skills_loader.py with updated path to skills/docs_SKILL.md"
```

---

### Task 10: `prompts/pre_synthesis.py`

**Files:**
- Create: `prompts/src/prompts/pre_synthesis.py` (từ `pre_synthesis.py`)

- [x] **Step 1: Copy và kiểm tra imports** *(no project imports — pure stdlib)*

```bash
cp pre_synthesis.py prompts/src/prompts/pre_synthesis.py
```

Mở file, kiểm tra tất cả imports và cập nhật nếu cần (tùy nội dung thực tế của `pre_synthesis.py`):
- Nếu import từ `skills_loader` → đổi thành `from prompts.skills_loader import ...`
- Nếu import từ `config` → đổi thành `from llm.client import ...` hoặc `from llm.paths import ...`

- [x] **Step 2: Copy test**

```bash
cp test_pre_synthesis.py prompts/tests/test_pre_synthesis.py
```

Cập nhật imports trong test:

```python
# Thay: from pre_synthesis import ...
# Thành: from prompts.pre_synthesis import ...
```

- [x] **Step 3: Chạy test** *(16/16 passed)*

```bash
python -m pytest prompts/tests/test_pre_synthesis.py -v
```

Expected: PASS

- [x] **Step 4: Commit** *(deferred — will commit all Chunk 4 together)*

```bash
git add prompts/src/prompts/pre_synthesis.py prompts/tests/test_pre_synthesis.py
git commit -m "feat(prompts): add pre_synthesis.py"
```

---

### Task 11: Prompt templates — standard, chunked, update

**Files:**
- Create: `prompts/src/prompts/standard.py` (từ `prompt.py`)
- Create: `prompts/src/prompts/chunked.py` (từ `chunked_prompt.py`)
- Create: `prompts/src/prompts/update.py` (từ `update_prompt.py`)

- [x] **Step 1: Copy `prompt.py` → `prompts/src/prompts/standard.py`** *(imports updated: get_docs→rag.docs, skills_loader→prompts.skills_loader)*

```bash
cp prompt.py prompts/src/prompts/standard.py
```

Cập nhật imports:
- `from skills_loader import` → `from prompts.skills_loader import`
- `from pre_synthesis import` → `from prompts.pre_synthesis import`

- [x] **Step 2: Copy `chunked_prompt.py` → `prompts/src/prompts/chunked.py`** *(3 imports updated)*

```bash
cp chunked_prompt.py prompts/src/prompts/chunked.py
```

Cập nhật imports:
- `from prompt import` → `from prompts.standard import`
- `from pre_synthesis import` → `from prompts.pre_synthesis import`
- `from skills_loader import` → `from prompts.skills_loader import`

- [x] **Step 3: Copy `update_prompt.py` → `prompts/src/prompts/update.py`** *(no project imports — standalone)*

```bash
cp update_prompt.py prompts/src/prompts/update.py
```

Cập nhật imports nếu có.

- [x] **Step 4: Copy tests** *(test_chunk_prompts.py copied; test_events_section.py skipped — imports chunked_olm from llm/, belongs in llm/tests/)*

```bash
cp test_chunk_prompts.py prompts/tests/test_chunk_prompts.py
# test_events_section.py → llm/tests/ (imports chunked_olm, not a prompts test)
```

Cập nhật imports trong mỗi test file:
- `from chunked_prompt import` → `from prompts.chunked import`
- `from prompt import` → `from prompts.standard import`

- [x] **Step 5: Chạy tests** *(skills_loader 8/8 PASS, pre_synthesis 16/16 PASS; test_chunk_prompts blocked on rag/ — Chunk 5 dependency)*

```bash
python prompts/tests/test_skills_loader.py   # 8 passed
python prompts/tests/test_pre_synthesis.py    # 16 passed
# test_chunk_prompts.py: ModuleNotFoundError: rag — will pass after Chunk 5
```

- [x] **Step 6: Cập nhật `prompts/src/prompts/__init__.py`** *(standard/chunked deferred until rag/ exists)*

```python
from prompts.skills_loader import load_skill, load_skills_for
from prompts.pre_synthesis import PreSynthesisResult, pre_synthesize
# NOTE: standard, chunked imports deferred until rag/ package exists (Chunk 5)
```

- [x] **Step 7: Commit** *(deferred — will commit all Chunk 4 together)*

```bash
git add prompts/src/prompts/ prompts/tests/
git commit -m "feat(prompts): add standard, chunked, update prompt templates and tests"
```

---

## Chunk 5: rag/ package

### Task 12: `rag/docs.py` — Lua file reading utilities

**Files:**
- Create: `rag/src/rag/docs.py` (từ `get_docs.py`)

- [x] **Step 1: Copy và cập nhật imports** *(done — stdlib only, no changes needed)*

```bash
cp get_docs.py rag/src/rag/docs.py
```

Kiểm tra và cập nhật imports nếu có dependency nào.

- [x] **Step 2: Viết smoke test** *(done — 2 tests, fixed extract_lua_references 2nd arg)*

Tạo `rag/tests/test_docs.py`:

```python
from rag.docs import safe_read_lua, extract_lua_references
import os

def test_safe_read_lua_nonexistent():
    result = safe_read_lua("nonexistent_file.lua")
    assert result is None

def test_extract_lua_references_empty():
    result = extract_lua_references("")
    assert isinstance(result, (list, set, dict))
```

- [x] **Step 3: Chạy test** *(16/16 passed)*

```bash
pip install -e rag/ --quiet
python -m pytest rag/tests/test_docs.py -v
```

Expected: PASS

- [x] **Step 4: Commit** *(7cc0639)*

```bash
git add rag/src/rag/docs.py rag/tests/test_docs.py
git commit -m "feat(rag): add docs.py (Lua file reading utilities)"
```

---

### Task 13: `rag/content.py` — function signature extraction

**Files:**
- Create: `rag/src/rag/content.py` (từ `rag_get_fnc_content.py`)
- Modify: `llm/src/llm/client.py` (thêm `COMPRESSION_MODEL`, `COMPRESSION_CACHE_DIR`)
- Modify: `llm/src/llm/tokens.py` (thêm `STUB_FULL_THRESHOLD`)

**Lưu ý kiến trúc:** `rag_get_fnc_content.py` dùng `config.COMPRESSION_MODEL`, `config.COMPRESSION_CACHE_DIR`, `config.STUB_FULL_THRESHOLD`. Để giữ dependency graph `rag → llm` (không tạo cycle `rag → core`), các constants này được đưa vào `llm/` thay vì `core/`.

- [x] **Step 1: Thêm LLM constants vào `llm/src/llm/client.py`** *(COMPRESSION_MODEL added)*

Thêm vào cuối phần constants (sau `OLLAMA_NUM_CTX`):

```python
# === COMPRESSION CONFIG ===
COMPRESSION_MODEL = "qwen3.5:cloud"   # model dùng cho compression (có thể override)
```

- [x] **Step 2: Thêm `COMPRESSION_CACHE_DIR` vào `llm/src/llm/paths.py`**

Thêm sau `BASE_DOCS_DIR`:

```python
COMPRESSION_CACHE_DIR = str(PROJECT_ROOT / ".cache" / "compression_cache")
```

- [x] **Step 3: Thêm `STUB_FULL_THRESHOLD` vào `llm/src/llm/tokens.py`**

Thêm sau imports:

```python
# Token threshold: require-only files nhỏ hơn ngưỡng này được include đầy đủ
STUB_FULL_THRESHOLD = 400
```

- [x] **Step 4: Copy và cập nhật imports trong `rag/src/rag/content.py`** *(all config.X → direct imports, removed lazy chunked imports)*

```bash
cp rag_get_fnc_content.py rag/src/rag/content.py
```

Cập nhật toàn bộ imports trong file:

```python
# Thay: import config  (và tất cả config.X usages)
# Thành:
from llm.client import ollama_chat, COMPRESSION_MODEL
from llm.paths import BASE_LUA_DIR, COMPRESSION_CACHE_DIR
from llm.tokens import count_tokens, STUB_FULL_THRESHOLD

# Thay: from get_docs import ...
# Thành:
from rag.docs import extract_lua_references, format_connected_section, clean_model_output

# Thay: from chunked import count_tokens
# Đã được thay ở trên bởi from llm.tokens import count_tokens
```

Tìm và thay toàn bộ:
- `config.ollama_chat(...)` → `ollama_chat(...)`
- `config.BASE_LUA_DIR` → `BASE_LUA_DIR`
- `config.COMPRESSION_CACHE_DIR` → `COMPRESSION_CACHE_DIR`
- `config.COMPRESSION_MODEL` → `COMPRESSION_MODEL`
- `config.STUB_FULL_THRESHOLD` → `STUB_FULL_THRESHOLD`

Xóa dòng `LUA_BASE_DIR = "./dst-scripts"` (nếu có) và thay tất cả usage bằng `BASE_LUA_DIR`.

- [x] **Step 5: Copy tests** *(patch paths updated, removed chunked_olm/CONTEXT_RESERVE tests)*

```bash
cp test_require_stubs.py rag/tests/test_require_stubs.py
```

Cập nhật imports trong test:
- `from rag_get_fnc_content import` → `from rag.content import`

- [x] **Step 6: Chạy tests** *(18/18 passed)*

```bash
pip install -e llm/ -e rag/ --quiet
python -m pytest rag/tests/ -v
```

Expected: PASS

- [x] **Step 7: Commit** *(40b988b)*

```bash
git add rag/src/rag/content.py rag/tests/test_require_stubs.py
git commit -m "feat(rag): add content.py with updated imports (llm.client, llm.paths, llm.tokens)"
```

---

### Task 14: `rag/search.py` — RAG vector search

**Files:**
- Create: `rag/src/rag/search.py` (từ `rag.py`)

- [x] **Step 1: Copy và cập nhật imports** *(TRACKER_FILE → data/file_tracker.json via parents[3])*

```bash
cp rag.py rag/src/rag/search.py
```

Cập nhật path constant trong file:

```python
# Tìm: TRACKER_FILE = "./file_tracker.json"
# Thay bằng:
from pathlib import Path
_WORKSPACE_ROOT = Path(__file__).parents[3]
TRACKER_FILE = str(_WORKSPACE_ROOT / "data" / "file_tracker.json")
```

- [x] **Step 2: Cập nhật `rag/src/rag/__init__.py`** *(exports docs+content, search excluded — heavy side effects)*

```python
from rag.search import (...)   # export các function cần thiết
from rag.content import (...)
from rag.docs import (...)
```

- [x] **Step 3: Chạy full rag tests** *(18/18 passed)*

```bash
python -m pytest rag/tests/ -v
```

Expected: PASS

- [x] **Step 4: Commit** *(e777c77)*

```bash
git add rag/src/rag/search.py rag/src/rag/__init__.py
git commit -m "feat(rag): add search.py with dynamic TRACKER_FILE path"
```

---

## Chunk 6: core/ package

### Task 15: `core/config.py` — model config & timing

**Files:**
- Create: `core/src/core/config.py` (phần còn lại của `config.py` sau khi tách sang llm/)

- [x] **Step 1: Tạo `core/src/core/config.py`**

Tách phần còn lại từ `config.py` (không bao gồm phần đã đưa vào `llm/`). Lưu ý: `COMPRESSION_MODEL`, `COMPRESSION_CACHE_DIR`, `STUB_FULL_THRESHOLD` đã được đưa vào `llm/` ở Task 13 — không khai báo lại ở đây.

```python
# core/src/core/config.py
from datetime import datetime
from llm.paths import PROJECT_ROOT

# === LLM CONFIG ===
MODEL_NAME = "qwen3.5:cloud"

# === PATHS ===
CHECKPOINT_DIR = str(PROJECT_ROOT / ".cache" / "chunked_checkpoints")

# === MODEL SETTINGS ===
VERSION = "714014"
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")

# === VALIDATOR & CACHE ===
MDX_NODE_TIMEOUT = 20

# === TIMING ===
CHUNK_SLEEP = 10
MERGE_SLEEP = 40
NORMAL_SLEEP = 20


def get_shared_file_tree(max_depth=3):
    """Sinh cây thư mục thu gọn cho prompt content."""
    from core.utils.tree import generate_slim_tree
    from llm.paths import BASE_LUA_DIR
    return generate_slim_tree(BASE_LUA_DIR, max_depth=max_depth)
```

- [x] **Step 2: Commit**

```bash
git add core/src/core/config.py
git commit -m "feat(core): add config.py (model settings, timing, cache paths)"
```

---

### Task 16: `core/utils/` — tree, shutdown, utilities

**Files:**
- Create: `core/src/core/utils/tree.py` (từ `get_tree.py`)
- Create: `core/src/core/utils/shutdown.py` (từ `shutdown.py`)

- [x] **Step 1: Copy files**

```bash
cp get_tree.py core/src/core/utils/tree.py
cp shutdown.py core/src/core/utils/shutdown.py
```

Kiểm tra và cập nhật imports nếu cần.

- [x] **Step 2: Verify import**

```bash
pip install -e core/ --quiet
python -c "from core.utils.tree import generate_slim_tree; print('OK')"
python -c "from core.utils.shutdown import setup_shutdown_handler; print('OK')"
```

- [x] **Step 3: Commit**

```bash
git add core/src/core/utils/
git commit -m "feat(core): add utils/tree.py and utils/shutdown.py"
```

---

### Task 17: `core/pipeline/chunking.py` — chunking logic

**Files:**
- Create: `core/src/core/pipeline/chunking.py` (phần chunking từ `chunked.py`, không bao gồm `count_tokens`/`estimate_merge_tokens`)

- [x] **Step 1: Tạo `core/src/core/pipeline/chunking.py`**

Copy `chunked.py` → `core/src/core/pipeline/chunking.py`, sau đó:

- Xóa hàm `count_tokens` và `estimate_merge_tokens` (đã ở `llm/tokens.py`)
- Thêm import:

```python
from llm.tokens import count_tokens, estimate_merge_tokens
from prompts.chunked import build_chunk_prompt   # được dùng trong calc_token_budget
```

- Cập nhật `from chunked_prompt import build_chunk_prompt` → `from prompts.chunked import build_chunk_prompt`

- Xóa block `if __name__ == "__main__"` ở cuối file (hoặc cập nhật import `from get_docs import` → `from rag.docs import`)

- [x] **Step 2: Copy test**

```bash
cp test_per_chunk.py core/tests/test_per_chunk.py
cp test_file_type_detection.py core/tests/test_file_type_detection.py
```

Cập nhật imports trong tests:
- `from chunked import` → `from core.pipeline.chunking import`

- [x] **Step 3: Chạy tests**

```bash
python -m pytest core/tests/test_per_chunk.py core/tests/test_file_type_detection.py -v
```

Expected: PASS

- [x] **Step 4: Commit**

```bash
git add core/src/core/pipeline/chunking.py core/tests/test_per_chunk.py core/tests/test_file_type_detection.py
git commit -m "feat(core): add pipeline/chunking.py with updated imports (llm.tokens, prompts.chunked)"
```

---

### Task 18: `core/pipeline/standard.py` và `core/pipeline/chunked.py`

**Files:**
- Create: `core/src/core/pipeline/standard.py` (từ `olm.py`)
- Create: `core/src/core/pipeline/chunked.py` (từ `chunked_olm.py`)

- [x] **Step 1: Copy `olm.py` → `core/src/core/pipeline/standard.py`**

```bash
cp olm.py core/src/core/pipeline/standard.py
```

Cập nhật imports:
- `from config import` → `from core.config import` và/hoặc `from llm.client import`
- `from prompt import` → `from prompts.standard import`
- `from rag_get_fnc_content import` → `from rag.content import`
- `from get_docs import` → `from rag.docs import`
- `from chunked import` → `from core.pipeline.chunking import`

- [x] **Step 2: Copy `chunked_olm.py` → `core/src/core/pipeline/chunked.py`**

```bash
cp chunked_olm.py core/src/core/pipeline/chunked.py
```

Cập nhật imports tương tự:
- `from config import` → `from core.config import` / `from llm.client import`
- `from chunked_prompt import` → `from prompts.chunked import`
- `from chunked import` → `from core.pipeline.chunking import`
- `from rag_get_fnc_content import` → `from rag.content import`
- `from get_docs import` → `from rag.docs import`
- `from pre_synthesis import` → `from prompts.pre_synthesis import`

- [x] **Step 3: Copy và cập nhật test**

```bash
cp chunked_test.py core/tests/chunked_test.py
```

Cập nhật imports trong test.

- [x] **Step 4: Chạy test**

```bash
python -m pytest core/tests/chunked_test.py -v
```

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add core/src/core/pipeline/standard.py core/src/core/pipeline/chunked.py core/tests/chunked_test.py
git commit -m "feat(core): add pipeline/standard.py and pipeline/chunked.py"
```

---

### Task 19: `core/update/docs.py` và `core/main.py`

**Files:**
- Create: `core/src/core/update/docs.py` (từ `update_docs.py`)
- Create: `core/src/core/main.py` (từ `main.py`)

- [x] **Step 1: Copy `update_docs.py` → `core/src/core/update/docs.py`**

```bash
cp update_docs.py core/src/core/update/docs.py
```

Cập nhật imports:
- `from config import` → `from core.config import` / `from llm.client import`
- `from get_tree import` → `from core.utils.tree import`
- `from rag_get_fnc_content import` → `from rag.content import`
- `from get_docs import` → `from rag.docs import`
- `from update_prompt import` → `from prompts.update import`
- `from olm import` → `from core.pipeline.standard import`
- `from validator.validate_update import` → không đổi (validator package đã có pyproject.toml)

Cập nhật path constant:
```python
# Thay: DIFF_REPORT = "./diff_report.json"
# Thành:
from pathlib import Path
_WORKSPACE_ROOT = Path(__file__).parents[4]
DIFF_REPORT = str(_WORKSPACE_ROOT / "data" / "diff_report.json")
```

- [x] **Step 2: Copy `main.py` → `core/src/core/main.py`**

```bash
cp main.py core/src/core/main.py
```

Cập nhật tất cả imports theo bảng mapping trong spec.

Thêm `main()` function entry point nếu chưa có:

```python
def main():
    """Entry point for mod-document CLI."""
    # nội dung hiện tại của if __name__ == "__main__": block
    ...

if __name__ == "__main__":
    main()
```

- [x] **Step 3: Copy remaining tests**

```bash
cp test.py core/tests/test.py
```

Cập nhật imports và chạy:

```bash
python -m pytest core/tests/ -v
```

- [x] **Step 4: Verify CLI entry point**

```bash
pip install -e core/ --quiet
python -c "from core.main import main; print('Entry point OK')"
```

- [x] **Step 5: Commit**

```bash
git add core/src/core/update/docs.py core/src/core/main.py core/tests/
git commit -m "feat(core): add update/docs.py and main.py entry point"
```

---

## Chunk 7: Cleanup & Verification

### Task 20: Chạy full test suite

- [ ] **Step 1: Chạy tất cả package tests**

```bash
python -m pytest llm/tests/ rag/tests/ prompts/tests/ watcher/tests/ core/tests/ -v 2>&1 | tail -30
```

Expected: Số PASSED >= số test baseline từ Task 1.

- [ ] **Step 2: Nếu có failures, fix từng cái trước khi tiếp tục**

---

### Task 21: Xóa file gốc ở root

Chỉ xóa sau khi Task 20 pass hoàn toàn.

- [ ] **Step 1: Xóa source files đã được migrate**

```bash
rm config.py olm.py chunked_olm.py chunked.py chunked_prompt.py prompt.py update_prompt.py
rm pre_synthesis.py skills_loader.py
rm rag.py rag_get_fnc_content.py get_docs.py
rm get_diff_update.py patch_hash.py simulate_changes.py update_docs.py
rm get_tree.py shutdown.py main.py
```

- [ ] **Step 2: Xóa test files đã được migrate**

```bash
rm test_per_chunk.py test_pre_synthesis.py test_chunk_prompts.py test_events_section.py
rm test_file_type_detection.py test_skills_loader.py test_require_stubs.py
rm chunked_test.py test.py
```

- [ ] **Step 3: Chạy lại full test suite để verify không có regression**

```bash
python -m pytest llm/tests/ rag/tests/ prompts/tests/ watcher/tests/ core/tests/ -v
```

Expected: Tất cả PASS.

- [ ] **Step 4: Commit cleanup**

```bash
git add -A
git commit -m "chore: remove migrated root-level files after all tests pass"
```

---

### Task 22: Cập nhật CLAUDE.md

- [ ] **Step 1: Cập nhật CLAUDE.md theo checklist**

Sửa các sections sau trong `CLAUDE.md`:

**Section `.venv`:**
```markdown
## Environment
project sử dụng uv workspace
chạy: `uv sync` để cài dependencies
chạy: `uv run mod-document` thay cho `python main.py`
```

**Section "Common Development Commands":**
```bash
# Chạy document generation
uv run mod-document

# Chạy diff watcher
uv run mod-watcher

# Test riêng từng package
uv run pytest core/tests/
uv run pytest rag/tests/
uv run pytest prompts/tests/
uv run pytest watcher/tests/

# Test toàn workspace
uv run pytest
```

**Section "Key Components":**
- `config.py` → `llm/src/llm/client.py` (LLM client) + `core/src/core/config.py` (settings)
- `olm.py` → `core/src/core/pipeline/standard.py`
- `chunked_olm.py` → `core/src/core/pipeline/chunked.py`
- `chunked.py` → `core/src/core/pipeline/chunking.py` + `llm/src/llm/tokens.py`
- `rag_get_fnc_content.py` → `rag/src/rag/content.py`
- `get_docs.py` → `rag/src/rag/docs.py`
- `prompt.py` → `prompts/src/prompts/standard.py`
- `chunked_prompt.py` → `prompts/src/prompts/chunked.py`

**Section "Important Files":**
- `main.py` → `core/src/core/main.py`
- `config.py` → `llm/src/llm/client.py` + `core/src/core/config.py`

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with new package paths and uv commands"
```

---

### Task 23: Final verification

- [ ] **Step 1: Verify workspace structure**

```bash
ls llm/src/llm/ rag/src/rag/ prompts/src/prompts/ watcher/src/watcher/ core/src/core/
```

- [ ] **Step 2: Verify CLI entry points**

```bash
python -c "from core.main import main; print('core: OK')"
python -c "from watcher.diff import main; print('watcher: OK')"
```

- [ ] **Step 3: Chạy full test suite lần cuối**

```bash
python -m pytest llm/tests/ rag/tests/ prompts/tests/ watcher/tests/ core/tests/ -v --tb=short
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: complete monorepo restructure - all packages migrated and tests passing"
```
