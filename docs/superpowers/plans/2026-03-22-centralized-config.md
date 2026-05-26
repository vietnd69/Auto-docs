# Centralized Configuration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all scattered configuration constants into `llm/src/llm/settings.py` backed by `config.toml`, with `MOD_DOC_*` env override support.

**Architecture:** New `settings.py` in the existing `llm` package (already a dependency of every other package) loads `config.toml` via Python's built-in `tomllib`, exposing typed constants. All current files that define these constants are updated to import from `llm.settings` instead. `config.toml` is git-excluded; `config.toml.template` is tracked.

**Tech Stack:** Python 3.11 `tomllib` (stdlib, no new deps), `uv run pytest` for tests, existing `uv` workspace.

---

## Chunk 1: Create the settings module and config files

### Task 1: Write tests for `llm/src/llm/settings.py`

**Files:**
- Create: `llm/tests/test_settings.py`

- [x] **Step 1: Write failing tests for `settings.py`**

Create `llm/tests/test_settings.py`:

```python
"""Tests for llm.settings — config loading and typed constants."""
import os


def test_model_constants_exist():
    from llm.settings import MODEL_MAIN, MODEL_UPDATE, MODEL_EMBED, MODEL_COMPRESS
    assert isinstance(MODEL_MAIN, str) and MODEL_MAIN
    assert isinstance(MODEL_UPDATE, str) and MODEL_UPDATE
    assert isinstance(MODEL_EMBED, str) and MODEL_EMBED
    assert isinstance(MODEL_COMPRESS, str) and MODEL_COMPRESS


def test_token_constants_are_positive_ints():
    from llm.settings import (
        PROMPT_TOKEN_LIMIT, MERGE_TOKEN_LIMIT, CONTEXT_RESERVE,
        STUB_FULL_THRESHOLD, CHUNKED_TOKEN_THRESHOLD, OLLAMA_NUM_CTX,
    )
    for val in [PROMPT_TOKEN_LIMIT, MERGE_TOKEN_LIMIT, CONTEXT_RESERVE,
                STUB_FULL_THRESHOLD, CHUNKED_TOKEN_THRESHOLD, OLLAMA_NUM_CTX]:
        assert isinstance(val, int) and val > 0


def test_timing_constants_are_positive_ints():
    from llm.settings import CHUNK_SLEEP, MERGE_SLEEP, NORMAL_SLEEP
    for val in [CHUNK_SLEEP, MERGE_SLEEP, NORMAL_SLEEP]:
        assert isinstance(val, int) and val > 0


def test_validator_constants_are_positive_ints():
    from llm.settings import (
        VALIDATOR_MAX_ITERATIONS, VALIDATOR_LOOP_MAX_ITERATIONS,
        MDX_NODE_TIMEOUT, LUA_CONTEXT_TOKENS,
    )
    assert VALIDATOR_MAX_ITERATIONS == 10
    assert VALIDATOR_LOOP_MAX_ITERATIONS == 5
    assert MDX_NODE_TIMEOUT == 20
    assert LUA_CONTEXT_TOKENS == 8000


def test_env_override_for_int(monkeypatch):
    """MOD_DOC_TOKENS_PROMPT_LIMIT env var overrides the TOML/default value."""
    monkeypatch.setenv("MOD_DOC_TOKENS_PROMPT_LIMIT", "9999")
    import importlib
    import llm.settings as s
    importlib.reload(s)
    assert s.PROMPT_TOKEN_LIMIT == 9999
    importlib.reload(s)  # restore module state to match restored env


def test_env_override_for_str(monkeypatch):
    """MOD_DOC_MODEL_MAIN env var overrides the TOML/default value."""
    monkeypatch.setenv("MOD_DOC_MODEL_MAIN", "test-model:local")
    import importlib
    import llm.settings as s
    importlib.reload(s)
    assert s.MODEL_MAIN == "test-model:local"
    importlib.reload(s)  # restore module state to match restored env


def test_graceful_fallback_without_config_toml(tmp_path, monkeypatch):
    """If config.toml is missing, defaults are used (no exception raised)."""
    monkeypatch.setattr("llm.settings._CONFIG_PATH", tmp_path / "nonexistent.toml")
    import importlib
    import llm.settings as s
    importlib.reload(s)
    assert s.PROMPT_TOKEN_LIMIT == 16000
    assert s.MODEL_MAIN == "qwen3.5:cloud"
    importlib.reload(s)  # restore module state to match restored _CONFIG_PATH
```

- [x] **Step 2: Run tests to verify they fail (module not yet created)**

```
uv run pytest llm/tests/test_settings.py -v
```

Expected: `ERRORS` — `ModuleNotFoundError: No module named 'llm.settings'`

---

### Task 2: Create `llm/src/llm/settings.py`

**Files:**
- Create: `llm/src/llm/settings.py`

- [x] **Step 3: Create `llm/src/llm/settings.py`**

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
    """TOML value → env override MOD_DOC_<SECTION>_<KEY> → default.

    Type casting: env values are cast to type(default). Supports int and str.
    WARNING: Do NOT add bool defaults — bool("false") == True in Python.
    """
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

- [x] **Step 4: Run tests to verify they pass**

```
uv run pytest llm/tests/test_settings.py -v
```

Expected: all 7 tests PASS

---

### Task 3: Create `config.toml.template` and `config.toml`, update `.gitignore`

**Files:**
- Create: `config.toml.template`
- Create: `config.toml`
- Modify: `.gitignore`

- [x] **Step 5: Create `config.toml.template`**

```toml
# mod-document configuration
# Env override: MOD_DOC_<SECTION>_<KEY> (uppercase)
# Example: MOD_DOC_MODEL_MAIN=qwen3-coder:cloud uv run mod-document
#
# Copy this file to config.toml and adjust values as needed.
# config.toml is git-excluded; this template is tracked.

[model]
main     = "qwen3.5:cloud"             # Main pipeline (doc gen + validator)
update   = "qwen3-coder-next:cloud"    # core/update/docs.py
embed    = "BAAI/bge-small-en-v1.5"   # RAG embedding model
compress = "qwen3.5:cloud"            # Compression stub generation

[tokens]
prompt_limit     = 16000   # Full prompt > limit → chunked doc gen
merge_limit      = 20000   # Chunk results > limit → hierarchical merge
context_reserve  = 7000    # Reserved cho connected content per chunk
stub_threshold   = 400     # File ≤ threshold → include full (no compression)
chunked_validate = 16000   # Lua tokens ≥ threshold → per-section validation
ollama_ctx       = 256000  # Ollama context window size

[timing]
chunk_sleep  = 10   # Seconds to wait between chunk LLM calls
merge_sleep  = 40   # Seconds to wait after merge
normal_sleep = 20   # Seconds to wait in standard pipeline

[validator]
max_iterations      = 10    # PipelineConfig default (CLI entry point)
loop_max_iterations = 5     # ContentLoopConfig default (standalone)
mdx_timeout         = 20    # Timeout (seconds) for Node.js MDX validation
lua_context_tokens  = 8000  # Token guard cho Lua context extract per section
```

- [x] **Step 6: Create `config.toml`** (same content as template, without the instructional header comment)

```toml
# mod-document configuration
# Env override: MOD_DOC_<SECTION>_<KEY> (uppercase)

[model]
main     = "qwen3.5:cloud"
update   = "qwen3-coder-next:cloud"
embed    = "BAAI/bge-small-en-v1.5"
compress = "qwen3.5:cloud"

[tokens]
prompt_limit     = 16000
merge_limit      = 20000
context_reserve  = 7000
stub_threshold   = 400
chunked_validate = 16000
ollama_ctx       = 256000

[timing]
chunk_sleep  = 10
merge_sleep  = 40
normal_sleep = 20

[validator]
max_iterations      = 10
loop_max_iterations = 5
mdx_timeout         = 20
lua_context_tokens  = 8000
```

- [x] **Step 7: Add `config.toml` to `.gitignore`**

In `.gitignore`, add this line under the `# Environment` section (after the `.env` line):

```
config.toml
```

- [x] **Step 8: Commit Chunk 1 (template + settings + tests + .gitignore; NOT config.toml)**

```bash
git add llm/tests/test_settings.py llm/src/llm/settings.py config.toml.template .gitignore
git commit -m "feat(config): add llm/settings.py with config.toml support and env override"
```

---

## Chunk 2: Migrate llm and core packages ✅ DONE (2026-03-23)

### Task 4: Migrate `llm/src/llm/client.py` and `llm/src/llm/tokens.py`

**Files:**
- Modify: `llm/src/llm/client.py:13` (`OLLAMA_NUM_CTX = 256_000` → import)
- Modify: `llm/src/llm/client.py:122` (`COMPRESSION_MODEL = "qwen3.5:cloud"` → import + re-export alias)
- Modify: `llm/src/llm/tokens.py:7` (`STUB_FULL_THRESHOLD = 400` → import)
- Modify: `llm/tests/test_client.py:1-5` — update import source for `OLLAMA_NUM_CTX`
- Modify: `rag/tests/test_require_stubs.py:6` — update import source for `STUB_FULL_THRESHOLD`

- [x] **Step 1: Run existing llm and rag tests to establish baseline**

```
uv run pytest llm/tests/ rag/tests/ -v
```

Expected: all PASS

- [x] **Step 2: Update `llm/src/llm/client.py` — replace `OLLAMA_NUM_CTX` definition**

Replace line 13 only (keep the surrounding comment block intact):
```python
# Before (line 13):
OLLAMA_NUM_CTX = 256_000
```
```python
# After (line 13):
from llm.settings import OLLAMA_NUM_CTX
```

- [x] **Step 3: Update `llm/src/llm/client.py` — replace `COMPRESSION_MODEL` definition**

Replace line 122 only (keep the `# === COMPRESSION CONFIG ===` comment on line 121 intact):
```python
# Before (line 122 only):
COMPRESSION_MODEL = "qwen3.5:cloud"   # model used for compression (can be overridden)
```
```python
# After (line 122 only):
# Re-exported so rag/content.py can continue: from llm.client import COMPRESSION_MODEL
from llm.settings import MODEL_COMPRESS as COMPRESSION_MODEL
```

- [x] **Step 4: Update `llm/src/llm/tokens.py`**

Replace line 7:
```python
# Before
STUB_FULL_THRESHOLD = 400
```
```python
# After
from llm.settings import STUB_FULL_THRESHOLD
```

- [x] **Step 5: Update `llm/tests/test_client.py` — import `OLLAMA_NUM_CTX` from `llm.settings`**

Replace lines 1-5:
```python
# Before
from llm.client import (
    OLLAMA_HOST, OLLAMA_NUM_CTX,
    OLLAMA_API_KEYS, get_ollama_client,
    _is_rate_limit_error,
)
```
```python
# After
from llm.client import (
    OLLAMA_HOST,
    OLLAMA_API_KEYS, get_ollama_client,
    _is_rate_limit_error,
)
from llm.settings import OLLAMA_NUM_CTX
```

- [x] **Step 6: Update `rag/tests/test_require_stubs.py` — import `STUB_FULL_THRESHOLD` from `llm.settings`**

Replace line 6:
```python
# Before
from llm.tokens import STUB_FULL_THRESHOLD
```
```python
# After
from llm.settings import STUB_FULL_THRESHOLD
```

- [x] **Step 7: Run llm and rag tests to verify no regressions**

```
uv run pytest llm/tests/ rag/tests/ -v
```

Expected: all PASS

- [x] **Step 8: Commit**

```bash
git add llm/src/llm/client.py llm/src/llm/tokens.py llm/tests/test_client.py rag/tests/test_require_stubs.py
git commit -m "refactor(llm): import OLLAMA_NUM_CTX, STUB_FULL_THRESHOLD, COMPRESSION_MODEL from settings"
```

---

### Task 5: Migrate `core/src/core/config.py`

**Files:**
- Modify: `core/src/core/config.py` — delete 5 constants, keep 3 items + `get_shared_file_tree()`

- [x] **Step 1: Run existing core tests to establish baseline**

```
uv run pytest core/tests/ -v
```

Expected: all PASS

- [x] **Step 2: Replace the entire content of `core/src/core/config.py`**

```python
from datetime import datetime
from llm.paths import PROJECT_ROOT

# === PATHS ===
CHECKPOINT_DIR = str(PROJECT_ROOT / ".cache" / "chunked_checkpoints")

# === MODEL SETTINGS ===
VERSION = "714014"
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")


def get_shared_file_tree(max_depth=3):
    """Generate a condensed directory tree for prompt content."""
    from core.utils.tree import generate_slim_tree
    from llm.paths import BASE_LUA_DIR
    return generate_slim_tree(BASE_LUA_DIR, max_depth=max_depth)
```

- [x] **Step 3: Run core tests to verify no regressions**

```
uv run pytest core/tests/ -v
```

Expected: all PASS

- [x] **Step 4: Commit**

```bash
git add core/src/core/config.py
git commit -m "refactor(core): remove MODEL_NAME, MDX_NODE_TIMEOUT, timing constants from config.py"
```

---

### Task 6: Migrate `core/src/core/main.py`

**Files:**
- Modify: `core/src/core/main.py` — add top-level import for `MODEL_MAIN`, delete line 54

- [x] **Step 1: Update `core/src/core/main.py`**

Add a new line immediately after line 23 (`from llm.paths import BASE_LUA_DIR, BASE_DOCS_DIR`):
```python
from llm.settings import MODEL_MAIN as MODEL_NAME
```

Then delete line 54 inside `main()` (the local redefinition):
```python
# Delete this line:
MODEL_NAME = config.MODEL_NAME
```

After the edit, the top of the file's imports should end:
```python
from llm.paths import BASE_LUA_DIR, BASE_DOCS_DIR
from llm.settings import MODEL_MAIN as MODEL_NAME
```
And inside `main()`, line 54 should no longer exist — `MODEL_NAME` is now from the module-level import.

- [x] **Step 2: Verify the module loads correctly**

```
uv run python -c "from core.main import main; print('OK')"
```

Expected: `OK`

- [x] **Step 3: Commit**

```bash
git add core/src/core/main.py
git commit -m "refactor(core): import MODEL_NAME from llm.settings instead of core.config"
```

---

### Task 7: Migrate `core/src/core/pipeline/chunking.py`

**Files:**
- Modify: `core/src/core/pipeline/chunking.py:24-33` — remove 3 constants, import from `llm.settings`
- Modify: `core/tests/test_per_chunk.py:18` — update import source for `CONTEXT_RESERVE`

- [x] **Step 1: Update `core/src/core/pipeline/chunking.py`**

Replace lines 24-33 (the three-constant block including comments):
```python
# Before (lines 24-33)
# Token threshold for the ENTIRE PROMPT (includes system instruction + context + code)
PROMPT_TOKEN_LIMIT = 16000   # If full prompt > 16K tokens, chunked pipeline is used

# Token threshold for MERGE (total chunk results)
MERGE_TOKEN_LIMIT = 20000

# Token reserve for per-chunk connected context (signatures or full bodies).
# calc_token_budget() subtracts this from the code budget.
# CALIBRATION: Full bodies 3–5 refs ~2000–3000 tokens; signatures 30 refs ~1500 tokens.
CONTEXT_RESERVE = 7000    # If total chunk results > this threshold → use hierarchical merge
```
```python
# After (single line replacing the entire block)
from llm.settings import PROMPT_TOKEN_LIMIT, MERGE_TOKEN_LIMIT, CONTEXT_RESERVE
```

- [x] **Step 2: Update `core/tests/test_per_chunk.py` — import `CONTEXT_RESERVE` from `llm.settings`**

Replace line 18:
```python
# Before
from core.pipeline.chunking import CONTEXT_RESERVE
```
```python
# After
from llm.settings import CONTEXT_RESERVE
```

- [x] **Step 3: Run core tests**

```
uv run pytest core/tests/ -v
```

Expected: all PASS

- [x] **Step 4: Commit**

```bash
git add core/src/core/pipeline/chunking.py core/tests/test_per_chunk.py
git commit -m "refactor(core): import PROMPT_TOKEN_LIMIT, MERGE_TOKEN_LIMIT, CONTEXT_RESERVE from llm.settings"
```

---

### Task 8: Migrate `core/src/core/update/docs.py` and `rag/src/rag/indexer.py`

**Files:**
- Modify: `core/src/core/update/docs.py:36` — `MODEL_NAME = "qwen3-coder-next:cloud"` → import
- Modify: `rag/src/rag/indexer.py:24` — `EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"` → import

- [x] **Step 1: Update `core/src/core/update/docs.py`**

Replace line 36:
```python
# Before
MODEL_NAME = "qwen3-coder-next:cloud"
```
```python
# After
from llm.settings import MODEL_UPDATE as MODEL_NAME
```

- [x] **Step 2: Update `rag/src/rag/indexer.py`**

Replace line 24:
```python
# Before
EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
```
```python
# After
from llm.settings import MODEL_EMBED as EMBED_MODEL_NAME
```

- [x] **Step 3: Verify imports**

```
uv run python -c "from core.update.docs import MODEL_NAME; print(MODEL_NAME)"
uv run python -c "from rag.indexer import EMBED_MODEL_NAME; print(EMBED_MODEL_NAME)"
```

Expected:
```
qwen3-coder-next:cloud
BAAI/bge-small-en-v1.5
```

- [x] **Step 4: Run rag tests**

```
uv run pytest rag/tests/ -v
```

Expected: all PASS

- [x] **Step 5: Commit**

```bash
git add core/src/core/update/docs.py rag/src/rag/indexer.py
git commit -m "refactor(core,rag): import MODEL_UPDATE and MODEL_EMBED from llm.settings"
```

---

## Chunk 3: Migrate validator package and delete constants.py ✅ DONE (2026-03-23)

### Task 9: Migrate `validator/src/validator/pipeline.py`

**Files:**
- Modify: `validator/src/validator/pipeline.py` — remove `CHUNKED_TOKEN_THRESHOLD` module-level definition, update `PipelineConfig` defaults, add imports

- [x] **Step 1: Run validator tests to establish baseline**

```
uv run pytest validator/tests/ -v
```

Expected: all PASS

- [x] **Step 2: Update `validator/src/validator/pipeline.py`**

Add import after line 13 (after existing imports, before `def _never_stop()`):
```python
from llm.settings import CHUNKED_TOKEN_THRESHOLD, VALIDATOR_MAX_ITERATIONS, MODEL_MAIN
```

Update `PipelineConfig` defaults (lines 23-25):
```python
# Before
    content_max_iterations: int = 10
    writer_model: str = "qwen3.5:cloud"
    reviewer_model: str = "qwen3.5:cloud"
```
```python
# After
    content_max_iterations: int = VALIDATOR_MAX_ITERATIONS
    writer_model: str = MODEL_MAIN
    reviewer_model: str = MODEL_MAIN
```

Delete line 40 (the module-level constant definition):
```python
# Delete this line:
CHUNKED_TOKEN_THRESHOLD = 16_000
```

Note: `CHUNKED_TOKEN_THRESHOLD` is referenced in `process_file()` lines 62 and 64. After deleting the module-level assignment and adding the import above, the name resolves correctly via the import — no further changes needed.

- [x] **Step 3: Run validator tests**

```
uv run pytest validator/tests/test_pipeline.py -v
```

Expected: FAIL — `test_pipeline.py` line 5 still imports `CHUNKED_TOKEN_THRESHOLD` from `validator.pipeline` (will be fixed in Task 12). Verify exact error: `ImportError: cannot import name 'CHUNKED_TOKEN_THRESHOLD' from 'validator.pipeline'`

- [x] **Step 4: Commit (test intentionally broken — will be fixed in Task 12)**

```bash
git add validator/src/validator/pipeline.py
git commit -m "refactor(validator): import CHUNKED_TOKEN_THRESHOLD, max_iterations, models from llm.settings"
```

---

### Task 10: Migrate `validator/src/validator/content/loop.py`

**Files:**
- Modify: `validator/src/validator/content/loop.py` — update `ContentLoopConfig` defaults

- [x] **Step 1: Update `validator/src/validator/content/loop.py`**

Add import after line 10 (after `from validator.utils import resolve_connected_content`), before `def _never_stop()`:
```python
from llm.settings import VALIDATOR_LOOP_MAX_ITERATIONS, MODEL_MAIN
```

Update `ContentLoopConfig` defaults (lines 20-22):
```python
# Before
    max_iterations: int = 5
    writer_model: str = "qwen3.5:cloud"
    reviewer_model: str = "qwen3.5:cloud"
```
```python
# After
    max_iterations: int = VALIDATOR_LOOP_MAX_ITERATIONS
    writer_model: str = MODEL_MAIN
    reviewer_model: str = MODEL_MAIN
```

- [x] **Step 2: Commit**

```bash
git add validator/src/validator/content/loop.py
git commit -m "refactor(validator): import VALIDATOR_LOOP_MAX_ITERATIONS and MODEL_MAIN from llm.settings"
```

---

### Task 11: Migrate `sections.py`, `autofix.py`, `mdx.py`

**Files:**
- Modify: `validator/src/validator/content/sections.py` — replace `8_000` magic numbers with `LUA_CONTEXT_TOKENS`
- Modify: `validator/src/validator/format/autofix.py:6` — replace `validator.constants` import
- Modify: `validator/src/validator/format/mdx.py:8` — replace `validator.constants` import

- [x] **Step 1: Update `validator/src/validator/content/sections.py`**

**This step requires three edits that must all be applied — they are interdependent.**

**Edit A** — add import after line 7 (after `from llm.tokens import count_tokens`):
```python
from llm.settings import LUA_CONTEXT_TOKENS
```

**Edit B** — rename function `_truncate_blocks_to_8k` and replace the `8_000` literal in its body (lines 134-145):
```python
# Before
def _truncate_blocks_to_8k(blocks: list[str]) -> str:
    """Return the longest prefix of blocks whose token count stays ≤ 8000."""
    kept: list[str] = []
    for block in blocks:
        candidate = "\n".join(kept + [block])
        if count_tokens(candidate) > 8_000:
            break
        kept.append(block)
    result = "\n".join(kept)
    if result:
        result += "\n-- [truncated]"
    return result
```
```python
# After
def _truncate_blocks_to_lua_limit(blocks: list[str]) -> str:
    """Return the longest prefix of blocks whose token count stays ≤ LUA_CONTEXT_TOKENS."""
    kept: list[str] = []
    for block in blocks:
        candidate = "\n".join(kept + [block])
        if count_tokens(candidate) > LUA_CONTEXT_TOKENS:
            break
        kept.append(block)
    result = "\n".join(kept)
    if result:
        result += "\n-- [truncated]"
    return result
```

**Edit C** — update the call-site of `_truncate_blocks_to_8k` in `extract_lua_context()` (lines 177-179). Both the condition literal AND the function call name must change:
```python
# Before (lines 177-179)
    if token_count != -1 and token_count > 8_000:
        result = _truncate_blocks_to_8k(blocks)
```
```python
# After
    if token_count != -1 and token_count > LUA_CONTEXT_TOKENS:
        result = _truncate_blocks_to_lua_limit(blocks)
```

After all three edits, verify no remaining references to the old name:
```
grep -n "_truncate_blocks_to_8k\|8_000" validator/src/validator/content/sections.py
```
Expected: no matches

- [x] **Step 2: Update `validator/src/validator/format/autofix.py`**

Replace line 6:
```python
# Before
from validator.constants import MDX_NODE_TIMEOUT
```
```python
# After
from llm.settings import MDX_NODE_TIMEOUT
```

- [x] **Step 3: Update `validator/src/validator/format/mdx.py`**

Replace line 8:
```python
# Before
from validator.constants import MDX_NODE_TIMEOUT
```
```python
# After
from llm.settings import MDX_NODE_TIMEOUT
```

- [x] **Step 4: Commit**

```bash
git add validator/src/validator/content/sections.py validator/src/validator/format/autofix.py validator/src/validator/format/mdx.py
git commit -m "refactor(validator): replace magic 8_000 with LUA_CONTEXT_TOKENS, MDX_NODE_TIMEOUT from llm.settings"
```

---

### Task 12: Update tests and delete `validator/constants.py`

**Files:**
- Modify: `validator/tests/test_smoke.py:49-52` — update `test_import_constants`
- Modify: `validator/tests/test_pipeline.py:5,11-12` — fix `CHUNKED_TOKEN_THRESHOLD` import and model assertions
- Modify: `validator/tests/test_content_loop.py:1-9` — update model default assertions, move settings import to module level
- Delete: `validator/src/validator/constants.py`

- [x] **Step 1: Verify no remaining consumers of `DEFAULT_MODEL` from `validator.constants`**

Before deleting `constants.py`, check whether anything imports `DEFAULT_MODEL` (the third export not covered by the rest of this migration):

```
grep -r "from validator.constants import" --include="*.py" .
```

Expected output:
```
validator/tests/test_smoke.py:    from validator.constants import MDX_NODE_TIMEOUT, DEFAULT_MAX_ITERATIONS
```
(Only `test_smoke.py`, which will be updated in Step 2. If any other file appears, update it to import from `llm.settings` before proceeding.)

- [x] **Step 2: Update `validator/tests/test_smoke.py`**

Replace lines 49-52 (`test_import_constants`):
```python
# Before
def test_import_constants():
    from validator.constants import MDX_NODE_TIMEOUT, DEFAULT_MAX_ITERATIONS
    assert MDX_NODE_TIMEOUT == 20
    assert DEFAULT_MAX_ITERATIONS == 10
```
```python
# After
def test_import_settings():
    from llm.settings import MDX_NODE_TIMEOUT, VALIDATOR_MAX_ITERATIONS
    assert MDX_NODE_TIMEOUT == 20
    assert VALIDATOR_MAX_ITERATIONS == 10
```

- [x] **Step 3: Update `validator/tests/test_pipeline.py`**

Replace line 5:
```python
# Before
from validator.pipeline import PipelineConfig, FileResult, process_file, CHUNKED_TOKEN_THRESHOLD
```
```python
# After
from validator.pipeline import PipelineConfig, FileResult, process_file
from llm.settings import CHUNKED_TOKEN_THRESHOLD, MODEL_MAIN
```

Replace lines 11-12 in `test_pipeline_config_defaults`:
```python
# Before
    assert config.writer_model == "qwen3.5:cloud"
    assert config.reviewer_model == "qwen3.5:cloud"
```
```python
# After
    assert config.writer_model == MODEL_MAIN
    assert config.reviewer_model == MODEL_MAIN
```

- [x] **Step 4: Update `validator/tests/test_content_loop.py`**

Add module-level imports at the top of the file (after line 2, after the existing `from validator.content.loop import ContentLoopConfig, ContentLoopResult`):
```python
from llm.settings import VALIDATOR_LOOP_MAX_ITERATIONS, MODEL_MAIN
```

Update `test_content_loop_config_defaults` (lines 5-9) to use the imported constants:
```python
# Before
def test_content_loop_config_defaults():
    config = ContentLoopConfig()
    assert config.max_iterations == 5
    assert config.writer_model == "qwen3.5:cloud"
    assert config.reviewer_model == "qwen3.5:cloud"
```
```python
# After
def test_content_loop_config_defaults():
    config = ContentLoopConfig()
    assert config.max_iterations == VALIDATOR_LOOP_MAX_ITERATIONS
    assert config.writer_model == MODEL_MAIN
    assert config.reviewer_model == MODEL_MAIN
```

- [x] **Step 5: Delete `validator/src/validator/constants.py`**

```bash
git rm validator/src/validator/constants.py
```

- [x] **Step 6: Run all validator tests**

```
uv run pytest validator/tests/ -v
```

Expected: all PASS

- [x] **Step 7: Commit**

```bash
git add validator/tests/test_smoke.py validator/tests/test_pipeline.py validator/tests/test_content_loop.py
git commit -m "refactor(validator): update tests to import from llm.settings, delete constants.py"
```

---

## Chunk 4: Final verification

### Task 13: Full workspace test run and smoke check

- [x] **Step 1: Run the full test suite**

```
uv run pytest -v
```

Expected: all tests PASS across all packages (`llm`, `core`, `rag`, `prompts`, `validator`, `watcher`)

- [x] **Step 2: Verify no remaining references to deleted `validator.constants`**

```
grep -r "from validator.constants" --include="*.py" .
grep -r "import validator.constants" --include="*.py" .
```

Expected: no matches. If any match appears, update the file to import from `llm.settings` instead.

- [x] **Step 3: Verify no remaining hardcoded constants that should come from settings**

```
grep -rn "OLLAMA_NUM_CTX\s*=" --include="*.py" .
grep -rn "STUB_FULL_THRESHOLD\s*=" --include="*.py" .
grep -rn "CHUNKED_TOKEN_THRESHOLD\s*=" --include="*.py" .
grep -rn "MDX_NODE_TIMEOUT\s*=" --include="*.py" .
grep -rn "COMPRESSION_MODEL\s*=" --include="*.py" .
grep -rn "PROMPT_TOKEN_LIMIT\s*=" --include="*.py" .
grep -rn "MERGE_TOKEN_LIMIT\s*=" --include="*.py" .
grep -rn "CONTEXT_RESERVE\s*=" --include="*.py" .
```

For each grep: the only match should be in `llm/src/llm/settings.py`. If any match appears in a different file, that file was not migrated — update it before proceeding.

- [x] **Step 4: Verify `config.toml` is git-excluded**

```bash
git check-ignore -v config.toml
```

Expected output: `.gitignore:N:config.toml    config.toml` (where N is the line number)

- [x] **Step 5: Verify `config.toml.template` is git-tracked**

```bash
git log --oneline config.toml.template
```

Expected: one commit log entry (the Chunk 1 commit). Confirms the template is tracked.

---

## Summary: Files Changed

| File | Action |
|---|---|
| `llm/src/llm/settings.py` | **Create** — loads config.toml + env override, exposes all constants |
| `llm/tests/test_settings.py` | **Create** — tests for settings loading, env override, graceful fallback |
| `config.toml` | **Create** (git-excluded) — runtime config |
| `config.toml.template` | **Create** (git-tracked) — template for fresh clones |
| `.gitignore` | **Modify** — add `config.toml` |
| `llm/src/llm/client.py` | **Modify** — import `OLLAMA_NUM_CTX`, re-export `COMPRESSION_MODEL` from settings |
| `llm/src/llm/tokens.py` | **Modify** — import `STUB_FULL_THRESHOLD` from settings |
| `llm/tests/test_client.py` | **Modify** — import `OLLAMA_NUM_CTX` from `llm.settings` directly |
| `core/src/core/config.py` | **Modify** — delete 5 constants, keep `CHECKPOINT_DIR`, `VERSION`, `TODAY_DATE`, function |
| `core/src/core/main.py` | **Modify** — import `MODEL_MAIN as MODEL_NAME` from settings, delete line 54 |
| `core/src/core/pipeline/chunking.py` | **Modify** — remove 3-constant block, import from settings |
| `core/src/core/update/docs.py` | **Modify** — import `MODEL_UPDATE as MODEL_NAME` from settings |
| `core/tests/test_per_chunk.py` | **Modify** — import `CONTEXT_RESERVE` from `llm.settings` directly |
| `rag/src/rag/indexer.py` | **Modify** — import `MODEL_EMBED as EMBED_MODEL_NAME` from settings |
| `rag/tests/test_require_stubs.py` | **Modify** — import `STUB_FULL_THRESHOLD` from `llm.settings` directly |
| `validator/src/validator/pipeline.py` | **Modify** — import from settings, use constants as `PipelineConfig` defaults |
| `validator/src/validator/content/loop.py` | **Modify** — import from settings, use constants as `ContentLoopConfig` defaults |
| `validator/src/validator/content/sections.py` | **Modify** — replace `8_000` magic numbers with `LUA_CONTEXT_TOKENS`, rename private function |
| `validator/src/validator/format/autofix.py` | **Modify** — import `MDX_NODE_TIMEOUT` from `llm.settings` |
| `validator/src/validator/format/mdx.py` | **Modify** — import `MDX_NODE_TIMEOUT` from `llm.settings` |
| `validator/src/validator/constants.py` | **Delete** |
| `validator/tests/test_smoke.py` | **Modify** — `test_import_constants` → `test_import_settings` |
| `validator/tests/test_pipeline.py` | **Modify** — import `CHUNKED_TOKEN_THRESHOLD` from `llm.settings`, update model assertions |
| `validator/tests/test_content_loop.py` | **Modify** — module-level import of settings constants, assert against named constants |
