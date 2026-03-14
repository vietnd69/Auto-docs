# Require-Only Stub Extraction Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject lightweight context for `require()`-only refs into per-chunk LLM prompts so `external_deps` descriptions are accurate.

**Architecture:** Split `chunk_refs` into `func_refs` (have function calls) and `req_refs` (require-only). Existing pipeline handles `func_refs` with budget 8000. New `extract_require_stubs()` uses the remaining budget for `req_refs`: small files included in full, large files compressed to a 3–5 line module summary via LLM with caching.

**Tech Stack:** Python 3.11, tiktoken (token counting), ollama (LLM calls), existing compression cache system (MD5 + JSON files in `.cache/compression_cache/`).

---

## Chunk 1: Config + constants

### Task 1: Add `STUB_FULL_THRESHOLD` to config and raise `CONTEXT_RESERVE`

**Files:**
- Modify: `config.py` (after `COMPRESSION_CACHE_DIR` line ~21)
- Modify: `chunked.py:31`

- [ ] **Step 1: Write failing test for STUB_FULL_THRESHOLD existence**

Create `test_require_stubs.py`:

```python
"""Tests for require-only stub extraction pipeline."""
import importlib


def test_stub_full_threshold_exists():
    import config
    assert hasattr(config, "STUB_FULL_THRESHOLD")
    assert isinstance(config.STUB_FULL_THRESHOLD, int)
    assert config.STUB_FULL_THRESHOLD == 400


def test_context_reserve_raised():
    import chunked
    assert chunked.CONTEXT_RESERVE == 8000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_stub_full_threshold_exists test_require_stubs.py::test_context_reserve_raised -v
```

Expected: FAIL — `AttributeError: module 'config' has no attribute 'STUB_FULL_THRESHOLD'`

- [ ] **Step 3: Add `STUB_FULL_THRESHOLD` to `config.py`**

In `config.py`, after line `COMPRESSION_CACHE_DIR = ...` (line ~21), add:

```python
STUB_FULL_THRESHOLD = 400   # tokens — require-only files smaller than this are included in full
```

- [ ] **Step 4: Update `CONTEXT_RESERVE` in `chunked.py`**

In `chunked.py` line 31, change:
```python
CONTEXT_RESERVE = 6000
```
to:
```python
CONTEXT_RESERVE = 8000
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_stub_full_threshold_exists test_require_stubs.py::test_context_reserve_raised -v
```

Expected: PASS both

- [ ] **Step 6: Commit**

```bash
git add config.py chunked.py test_require_stubs.py
git commit -m "feat: add STUB_FULL_THRESHOLD=400 and raise CONTEXT_RESERVE to 8000"
```

---

## Chunk 2: `_compress_module_stub()`

### Task 2: Implement `_compress_module_stub(lua_code, ref_path)`

This is a private function in `rag_get_fnc_content.py` that calls the LLM to produce a 3–5 line module summary. It reuses the existing cache system.

**Files:**
- Modify: `rag_get_fnc_content.py` (add after `compress_connected_content()`, around line ~406)
- Modify: `test_require_stubs.py`

- [ ] **Step 1: Write failing tests**

Append to `test_require_stubs.py`:

```python
from unittest.mock import patch, MagicMock


def _make_valid_stub_response(ref_path: str) -> str:
    return (
        f"-- [REQUIRE MODULE: {ref_path}] ---\n"
        "-- MODULE: BufferedAction\n"
        "-- exports: DoAction, Fail, Succeed\n"
        "-- purpose: Wraps deferred action execution with success/fail callbacks\n"
    )


def test_compress_module_stub_success():
    """LLM returns valid output with -- MODULE: marker → return formatted string."""
    from rag_get_fnc_content import _compress_module_stub

    lua_code = "BufferedAction = Class(function(self) end)"
    ref_path = "./bufferedaction.lua"

    llm_raw = "-- MODULE: BufferedAction\n-- exports: DoAction\n-- purpose: wraps actions"

    with patch("config.ollama_chat") as mock_chat, \
         patch("rag_get_fnc_content._load_compression_cache", return_value=None), \
         patch("rag_get_fnc_content._save_compression_cache"):
        mock_chat.return_value = {"message": {"content": llm_raw}}
        result = _compress_module_stub(lua_code, ref_path)

    assert result is not None
    assert "-- [REQUIRE MODULE: ./bufferedaction.lua] ---" in result
    assert "-- MODULE: BufferedAction" in result


def test_compress_module_stub_missing_marker():
    """LLM returns output without -- MODULE: → return None, log warning."""
    from rag_get_fnc_content import _compress_module_stub

    with patch("config.ollama_chat") as mock_chat, \
         patch("rag_get_fnc_content._load_compression_cache", return_value=None), \
         patch("rag_get_fnc_content._save_compression_cache"), \
         patch("builtins.print") as mock_print:
        mock_chat.return_value = {"message": {"content": "some garbage output"}}
        result = _compress_module_stub("local x = 1", "./util.lua")

    assert result is None
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "STUB" in printed and "MODULE" in printed


def test_compress_module_stub_llm_exception():
    """LLM raises exception → return None, log warning."""
    from rag_get_fnc_content import _compress_module_stub

    with patch("config.ollama_chat", side_effect=Exception("network error")), \
         patch("rag_get_fnc_content._load_compression_cache", return_value=None), \
         patch("builtins.print") as mock_print:
        result = _compress_module_stub("local x = 1", "./class.lua")

    assert result is None
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "STUB" in printed


def test_compress_module_stub_cache_hit():
    """Cache hit → return cached value without calling LLM."""
    from rag_get_fnc_content import _compress_module_stub

    cached = "-- [REQUIRE MODULE: ./class.lua] ---\n-- MODULE: Class\n-- purpose: OOP base"

    with patch("config.ollama_chat") as mock_chat, \
         patch("rag_get_fnc_content._load_compression_cache", return_value=cached):
        result = _compress_module_stub("anything", "./class.lua")

    mock_chat.assert_not_called()
    assert result == cached


def test_compress_module_stub_lenient_validation():
    """Output with -- MODULE: but missing -- exports: is still accepted."""
    from rag_get_fnc_content import _compress_module_stub

    llm_raw = "-- MODULE: SomeModule\n-- purpose: does something"

    with patch("config.ollama_chat") as mock_chat, \
         patch("rag_get_fnc_content._load_compression_cache", return_value=None), \
         patch("rag_get_fnc_content._save_compression_cache"):
        mock_chat.return_value = {"message": {"content": llm_raw}}
        result = _compress_module_stub("local x = 1", "./somemodule.lua")

    assert result is not None
    assert "-- MODULE: SomeModule" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_compress_module_stub_success test_require_stubs.py::test_compress_module_stub_missing_marker test_require_stubs.py::test_compress_module_stub_llm_exception test_require_stubs.py::test_compress_module_stub_cache_hit test_require_stubs.py::test_compress_module_stub_lenient_validation -v
```

Expected: FAIL — `ImportError: cannot import name '_compress_module_stub'`

- [ ] **Step 3: Implement `_compress_module_stub()` in `rag_get_fnc_content.py`**

Add after `compress_connected_content()` (around line 406), before `extract_connected_content()`:

```python
def _compress_module_stub(lua_code: str, ref_path: str) -> str | None:
    """
    Dùng LLM để tạo module-level summary (3–5 dòng) cho require-only refs.
    Reuses compression cache system.

    Returns:
        Formatted stub string nếu thành công (contains "-- [REQUIRE MODULE: ...]").
        None nếu LLM thất bại hoặc output không hợp lệ.
    """
    cache_key = _compression_cache_key(lua_code)
    cached = _load_compression_cache(cache_key)
    if cached is not None:
        return cached

    prompt = f"""Summarize this Lua module in 3–5 lines. Output format:
-- MODULE: <ClassName or module name>
-- exports: <key functions/constants, comma-separated>
-- purpose: <one sentence: what this module does>
-- notes: <side effects, globals registered> (omit if none)

Rules: Never invent. Output only the summary, no preamble.
SOURCE:
{lua_code}"""

    try:
        response = config.ollama_chat(
            model=config.COMPRESSION_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response["message"]["content"]
        raw = clean_model_output(raw)
    except Exception as e:
        print(f"  [STUB] LLM call failed for {ref_path}: {e}")
        return None

    if "-- MODULE:" not in raw:
        print(f"  [STUB] Output missing -- MODULE: marker, skipping {ref_path}")
        return None

    result = f"-- [REQUIRE MODULE: {ref_path}] ---\n{raw}"
    _save_compression_cache(cache_key, result)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_compress_module_stub_success test_require_stubs.py::test_compress_module_stub_missing_marker test_require_stubs.py::test_compress_module_stub_llm_exception test_require_stubs.py::test_compress_module_stub_cache_hit test_require_stubs.py::test_compress_module_stub_lenient_validation -v
```

Expected: PASS all 5

- [ ] **Step 5: Commit**

```bash
git add rag_get_fnc_content.py test_require_stubs.py
git commit -m "feat: add _compress_module_stub() for require-only LLM module summaries"
```

---

## Chunk 3: `extract_require_stubs()`

### Task 3: Implement `extract_require_stubs(req_refs, max_tokens)`

This is the main new public function. For each require-only ref: if the file is small (≤ `STUB_FULL_THRESHOLD` tokens) include it in full; otherwise call `_compress_module_stub()`. Budget is checked incrementally.

**Files:**
- Modify: `rag_get_fnc_content.py` (add after `_compress_module_stub()`)
- Modify: `test_require_stubs.py`

- [ ] **Step 1: Write failing tests**

Append to `test_require_stubs.py`:

```python
import tempfile
import os


def _write_temp_lua(content: str) -> str:
    """Write a temp .lua file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_extract_require_stubs_empty_refs():
    """Empty req_refs → return empty string immediately."""
    from rag_get_fnc_content import extract_require_stubs
    assert extract_require_stubs([], max_tokens=5000) == ""


def test_extract_require_stubs_zero_budget():
    """max_tokens <= 0 → return empty string without reading files, no log emitted."""
    from rag_get_fnc_content import extract_require_stubs
    with patch("builtins.print") as mock_print:
        result = extract_require_stubs([("./class.lua", [])], max_tokens=0)
    assert result == ""
    mock_print.assert_not_called()


def test_extract_require_stubs_small_file_full():
    """File with token count <= STUB_FULL_THRESHOLD → included in full with REQUIRE FULL marker."""
    from rag_get_fnc_content import extract_require_stubs

    small_lua = "-- tiny module\nlocal M = {}\nreturn M\n"
    tmp = _write_temp_lua(small_lua)

    try:
        with patch("rag_get_fnc_content._resolve_lua_path", return_value=tmp):
            result = extract_require_stubs([("./tiny.lua", [])], max_tokens=5000)
    finally:
        os.unlink(tmp)

    assert "-- [REQUIRE FULL: ./tiny.lua]" in result
    assert small_lua.strip() in result


def test_extract_require_stubs_large_file_stub():
    """File larger than STUB_FULL_THRESHOLD → calls _compress_module_stub, uses its output."""
    from rag_get_fnc_content import extract_require_stubs

    # 401+ tokens of Lua — we mock count_tokens to return 401
    large_lua = "x = 1\n" * 200
    tmp = _write_temp_lua(large_lua)
    stub_output = "-- [REQUIRE MODULE: ./big.lua] ---\n-- MODULE: Big\n-- purpose: big module"

    try:
        with patch("rag_get_fnc_content._resolve_lua_path", return_value=tmp), \
             patch("rag_get_fnc_content._compress_module_stub", return_value=stub_output) as mock_stub, \
             patch("rag_get_fnc_content.count_tokens", return_value=401):
            result = extract_require_stubs([("./big.lua", [])], max_tokens=5000)
    finally:
        os.unlink(tmp)

    mock_stub.assert_called_once()
    assert stub_output in result


def test_extract_require_stubs_file_not_found():
    """File not found (_resolve_lua_path returns None) → skip silently."""
    from rag_get_fnc_content import extract_require_stubs

    with patch("rag_get_fnc_content._resolve_lua_path", return_value=None):
        result = extract_require_stubs([("./missing.lua", [])], max_tokens=5000)

    assert result == ""


def test_extract_require_stubs_budget_exhausted():
    """Budget runs out after first ref → second ref skipped, log printed."""
    from rag_get_fnc_content import extract_require_stubs

    small_lua = "-- mod\nlocal M = {}\n"
    tmp = _write_temp_lua(small_lua)

    try:
        with patch("rag_get_fnc_content._resolve_lua_path", return_value=tmp), \
             patch("rag_get_fnc_content.count_tokens", return_value=300), \
             patch("builtins.print") as mock_print:
            # budget=350 — first ref uses 300, second would exceed
            result = extract_require_stubs(
                [("./a.lua", []), ("./b.lua", [])],
                max_tokens=350,
            )
    finally:
        os.unlink(tmp)

    assert "-- [REQUIRE FULL: ./a.lua]" in result
    assert "-- [REQUIRE FULL: ./b.lua]" not in result
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Require-stub" in printed and "budget exhausted" in printed.lower()


def test_extract_require_stubs_stub_failure_skipped():
    """_compress_module_stub returns None → ref skipped, no crash."""
    from rag_get_fnc_content import extract_require_stubs

    large_lua = "x = 1\n" * 200
    tmp = _write_temp_lua(large_lua)

    try:
        with patch("rag_get_fnc_content._resolve_lua_path", return_value=tmp), \
             patch("rag_get_fnc_content._compress_module_stub", return_value=None), \
             patch("rag_get_fnc_content.count_tokens", return_value=401):
            result = extract_require_stubs([("./big.lua", [])], max_tokens=5000)
    finally:
        os.unlink(tmp)

    assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_extract_require_stubs_empty_refs test_require_stubs.py::test_extract_require_stubs_zero_budget test_require_stubs.py::test_extract_require_stubs_small_file_full test_require_stubs.py::test_extract_require_stubs_large_file_stub test_require_stubs.py::test_extract_require_stubs_file_not_found test_require_stubs.py::test_extract_require_stubs_budget_exhausted test_require_stubs.py::test_extract_require_stubs_stub_failure_skipped -v
```

Expected: FAIL — `ImportError: cannot import name 'extract_require_stubs'`

- [ ] **Step 3: Implement `extract_require_stubs()` in `rag_get_fnc_content.py`**

Add after `_compress_module_stub()`, before `extract_connected_for_chunk()`:

```python
def extract_require_stubs(
    req_refs: list[tuple[str, list[str]]],
    max_tokens: int = 0,
) -> str:
    """
    Trích xuất stub content cho require-only refs (func_names rỗng).

    - File nhỏ (≤ STUB_FULL_THRESHOLD tokens): include toàn bộ nội dung.
    - File lớn: dùng LLM tạo module summary 3–5 dòng.

    Budget được kiểm tra incrementally — dừng khi tổng vượt max_tokens.

    Returns:
        str: nội dung ghép, prefix bởi marker "-- [REQUIRE FULL:" hoặc "-- [REQUIRE MODULE:".
             Trả về "" nếu không có gì.
    """
    from chunked import count_tokens  # lazy import, same pattern as rest of this file

    if not req_refs or max_tokens <= 0:
        return ""

    sections: list[str] = []
    running_tokens = 0
    total = len(req_refs)

    for idx, (ref_path, _) in enumerate(req_refs):
        real_path = _resolve_lua_path(ref_path)
        if real_path is None:
            continue

        try:
            with open(real_path, encoding="utf-8", errors="ignore") as f:
                lua_code = f.read()
        except Exception:
            continue

        file_tokens = count_tokens(lua_code)
        if file_tokens == -1:
            file_tokens = len(lua_code) // 4

        if file_tokens <= config.STUB_FULL_THRESHOLD:
            section = f"-- [REQUIRE FULL: {ref_path}] ---\n{lua_code}"
        else:
            section = _compress_module_stub(lua_code, ref_path)
            if section is None:
                continue

        section_tokens = count_tokens(section)
        if section_tokens == -1:
            section_tokens = len(section) // 4

        if running_tokens + section_tokens > max_tokens:
            print(
                f"  [CTX] Require-stub budget exhausted after {len(sections)}/{total} refs"
            )
            break

        sections.append(section)
        running_tokens += section_tokens

    return "\n\n".join(sections)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_extract_require_stubs_empty_refs test_require_stubs.py::test_extract_require_stubs_zero_budget test_require_stubs.py::test_extract_require_stubs_small_file_full test_require_stubs.py::test_extract_require_stubs_large_file_stub test_require_stubs.py::test_extract_require_stubs_file_not_found test_require_stubs.py::test_extract_require_stubs_budget_exhausted test_require_stubs.py::test_extract_require_stubs_stub_failure_skipped -v
```

Expected: PASS all 7

- [ ] **Step 5: Commit**

```bash
git add rag_get_fnc_content.py test_require_stubs.py
git commit -m "feat: add extract_require_stubs() for require-only context injection"
```

---

## Chunk 4: Wire into `extract_connected_for_chunk()`

### Task 4: Update `extract_connected_for_chunk()` to split refs and call `extract_require_stubs()`

This is the integration step. The fallback path (lines 558–579) is left **unchanged**. Only the normal path (lines 581–599) is modified.

**Files:**
- Modify: `rag_get_fnc_content.py:533-599`
- Modify: `test_require_stubs.py`

- [ ] **Step 1: Write failing integration test**

Append to `test_require_stubs.py`:

```python
def test_extract_connected_for_chunk_req_stubs_appended():
    """
    Chunk with require-only refs → extract_require_stubs() output appended to connected_content.
    Fallback path (chunk_refs empty) is NOT triggered.
    """
    from rag_get_fnc_content import extract_connected_for_chunk

    # Chunk that require()s a module but makes no component.X calls
    chunk_code = 'require "util"\nlocal x = util.DoSomething()'
    stub_output = "-- [REQUIRE FULL: ./util.lua] ---\n-- tiny util"

    with patch("rag_get_fnc_content.extract_connected_content", return_value="") as mock_func, \
         patch("rag_get_fnc_content.extract_require_stubs", return_value=stub_output) as mock_stubs:
        section, content, ref_count = extract_connected_for_chunk(
            chunk_code=chunk_code,
            own_filename="actions.lua",
            max_total_tokens=8000,
        )

    mock_stubs.assert_called_once()
    assert stub_output in content
    # ref_count counts only func_refs; chunk has no components.X calls → 0
    assert ref_count == 0


def test_extract_connected_for_chunk_func_refs_use_full_budget():
    """
    func_refs use the full budget; remaining_budget passed to extract_require_stubs.
    """
    from rag_get_fnc_content import extract_connected_for_chunk

    chunk_code = (
        'require "util"\n'
        'components.health:DoDelta(-10)\n'
    )
    func_content = "-- [full bodies content]"

    # count_tokens is lazily imported from chunked inside the function body,
    # so patch the source binding in chunked (not rag_get_fnc_content)
    with patch("rag_get_fnc_content.extract_connected_content", return_value=func_content), \
         patch("rag_get_fnc_content.extract_require_stubs", return_value="") as mock_stubs, \
         patch("chunked.count_tokens", return_value=100):
        extract_connected_for_chunk(
            chunk_code=chunk_code,
            own_filename="actions.lua",
            max_total_tokens=8000,
        )

    # remaining_budget should be 8000 - 100 = 7900
    call_kwargs = mock_stubs.call_args
    assert call_kwargs is not None
    passed_budget = call_kwargs[1].get("max_tokens") or call_kwargs[0][1]
    assert passed_budget == 7900


def test_extract_connected_for_chunk_fallback_path_unchanged():
    """
    Fallback path (chunk_refs empty, full_refs provided) still returns early
    without calling extract_require_stubs.
    """
    from rag_get_fnc_content import extract_connected_for_chunk

    # chunk with no refs at all
    chunk_code = "local x = 1"
    full_refs = [("./components/health.lua", ["DoDelta"])]

    with patch("rag_get_fnc_content.extract_require_stubs") as mock_stubs, \
         patch("rag_get_fnc_content.extract_signatures_only", return_value=("", [])):
        extract_connected_for_chunk(
            chunk_code=chunk_code,
            own_filename="actions.lua",
            full_refs=full_refs,
            max_total_tokens=8000,
        )

    mock_stubs.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_extract_connected_for_chunk_req_stubs_appended test_require_stubs.py::test_extract_connected_for_chunk_func_refs_use_full_budget test_require_stubs.py::test_extract_connected_for_chunk_fallback_path_unchanged -v
```

Expected: FAIL — `mock_stubs.assert_called_once()` fails (function not wired yet)

- [ ] **Step 3: Modify `extract_connected_for_chunk()` in `rag_get_fnc_content.py`**

Replace the normal path (lines 581–599) with the new split/combine logic. The fallback path (lines 557–579) is **not touched**.

Old normal path (lines 581–599):
```python
    connected_content = extract_connected_content(
        chunk_refs,
        max_lines_per_file=max_lines_per_file,
        max_total_tokens=max_total_tokens,
    )

    if not connected_content:
        return "", "", len(chunk_refs)

    # Rebuild section từ kept_refs thực tế
    if "--[SIGONLY:" in connected_content:
        _, kept_refs = extract_signatures_only(chunk_refs, max_output_tokens=max_total_tokens)
    elif "-- COMPRESSED:" in connected_content or "-- COMPACT:" in connected_content:
        kept_refs = chunk_refs
    else:
        kept_refs = chunk_refs

    connected_section = format_connected_section(kept_refs)
    return connected_section, connected_content, len(kept_refs)
```

New normal path:
```python
    # Tách func_refs (có function calls) và req_refs (require-only)
    func_refs = [(path, funcs) for path, funcs in chunk_refs if funcs]
    req_refs  = [(path, funcs) for path, funcs in chunk_refs if not funcs]

    # Pipeline cũ: func_refs với full budget
    func_content = extract_connected_content(
        func_refs,
        max_lines_per_file=max_lines_per_file,
        max_total_tokens=max_total_tokens,
    )

    # Pipeline mới: require-only stubs với budget còn lại
    from chunked import count_tokens
    func_tokens = count_tokens(func_content)
    if func_tokens == -1:
        func_tokens = len(func_content) // 4
    remaining_budget = max_total_tokens - func_tokens
    req_content = extract_require_stubs(req_refs, max_tokens=remaining_budget)

    # Ghép kết quả
    if func_content and req_content:
        connected_content = func_content + "\n\n" + req_content
    elif req_content:
        connected_content = req_content
    else:
        connected_content = func_content

    if not connected_content:
        return "", "", len(func_refs)

    # Rebuild section từ kept_refs thực tế (chỉ func_refs — req_refs không có func_names)
    if "--[SIGONLY:" in func_content:
        _, kept_refs = extract_signatures_only(func_refs, max_output_tokens=max_total_tokens)
    else:
        kept_refs = func_refs

    connected_section = format_connected_section(kept_refs)
    return connected_section, connected_content, len(kept_refs)
```

Also update the docstring to mention `max_total_tokens` default changed from 3500 to 8000.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_extract_connected_for_chunk_req_stubs_appended test_require_stubs.py::test_extract_connected_for_chunk_func_refs_use_full_budget test_require_stubs.py::test_extract_connected_for_chunk_fallback_path_unchanged -v
```

Expected: PASS all 3

- [ ] **Step 5: Run the full test suite for this feature**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py -v
```

Expected: PASS all tests

- [ ] **Step 6: Commit**

```bash
git add rag_get_fnc_content.py test_require_stubs.py
git commit -m "feat: wire extract_require_stubs into extract_connected_for_chunk normal path"
```

---

## Chunk 5: Update `chunked_olm.py` markers + logging

### Task 5: Add new markers to `_detect_context_mode()` and update logging

Two call sites in `chunked_olm.py` use `_detect_context_mode()` and print log lines. Both need updating to handle the new combined content.

**Files:**
- Modify: `chunked_olm.py:27-35` (add markers)
- Modify: `chunked_olm.py:588-594` (first call site logging)
- Modify: `chunked_olm.py:646-652` (second call site, retry loop)
- Modify: `test_require_stubs.py`

- [ ] **Step 1: Write failing tests for `_detect_context_mode()`**

Append to `test_require_stubs.py`:

```python
def test_detect_context_mode_require_full():
    from chunked_olm import _detect_context_mode
    assert _detect_context_mode("-- [REQUIRE FULL: ./class.lua] ---\nlocal x=1") == "require_full"


def test_detect_context_mode_require_module():
    from chunked_olm import _detect_context_mode
    assert _detect_context_mode("-- [REQUIRE MODULE: ./class.lua] ---\n-- MODULE: Class") == "require_module"


def test_detect_context_mode_existing_modes_unchanged():
    from chunked_olm import _detect_context_mode
    assert _detect_context_mode("--[SIGONLY: foo]") == "signatures"
    assert _detect_context_mode("-- COMPRESSED: Foo:Bar()") == "compressed"
    assert _detect_context_mode("-- COMPACT: Foo:Bar()") == "compact"
    assert _detect_context_mode("function Foo:Bar() end") == "full"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_detect_context_mode_require_full test_require_stubs.py::test_detect_context_mode_require_module test_require_stubs.py::test_detect_context_mode_existing_modes_unchanged -v
```

Expected: `test_detect_context_mode_require_full` and `test_detect_context_mode_require_module` FAIL; existing modes PASS

- [ ] **Step 3: Update `_detect_context_mode()` in `chunked_olm.py`**

Replace (lines 27–35):
```python
def _detect_context_mode(content: str) -> str:
    """Xác định mode của connected content dựa trên marker strings."""
    if "--[SIGONLY:" in content:
        return "signatures"
    if "-- COMPRESSED:" in content:
        return "compressed"
    if "-- COMPACT:" in content:
        return "compact"
    return "full"
```

With:
```python
def _detect_context_mode(content: str) -> str:
    """Xác định mode của connected content dựa trên marker strings."""
    if "--[SIGONLY:" in content:
        return "signatures"
    if "-- COMPRESSED:" in content:
        return "compressed"
    if "-- COMPACT:" in content:
        return "compact"
    if "-- [REQUIRE FULL:" in content:
        return "require_full"
    if "-- [REQUIRE MODULE:" in content:
        return "require_module"
    return "full"
```

- [ ] **Step 4: Run marker tests to verify they pass**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py::test_detect_context_mode_require_full test_require_stubs.py::test_detect_context_mode_require_module test_require_stubs.py::test_detect_context_mode_existing_modes_unchanged -v
```

Expected: PASS all 3

- [ ] **Step 5: Update logging in first call site (`chunked_olm.py` ~line 588)**

Old:
```python
        if chunk_content:
            mode = _detect_context_mode(chunk_content)
            print(f"    [CTX] Chunk {i}: {ref_count} refs, mode={mode}")
        elif ref_count > 0:
            print(f"    [CTX] Chunk {i}: {ref_count} refs nhưng không extract được content (require-only, không có function call)")
        else:
            print(f"    [CTX] Chunk {i}: không có external context (chunk độc lập)")
```

New — the spec calls for two separate `_detect_context_mode()` calls on `func_content` and `req_content`. However, `chunked_olm.py` only receives the combined `chunk_content` string (the signature of `extract_connected_for_chunk()` is unchanged). **Pragmatic deviation:** use marker-string detection on the combined string to infer both modes. `func_mode` is derived from `_detect_context_mode(chunk_content)` which correctly identifies the func-content mode because func markers (`-- COMPRESSED:`, `--[SIGONLY:`, etc.) appear before require markers in the combined string and match first. Require mode is detected by explicit `in` check:

```python
        if chunk_content:
            # Detect modes for func content and req stubs separately
            func_mode = _detect_context_mode(chunk_content)
            has_req_full = "-- [REQUIRE FULL:" in chunk_content
            has_req_module = "-- [REQUIRE MODULE:" in chunk_content
            req_mode = "require_full" if has_req_full else ("require_module" if has_req_module else None)
            if req_mode:
                print(f"    [CTX] Chunk {i}: {ref_count} refs, func_mode={func_mode} | req_stubs={req_mode}")
            else:
                print(f"    [CTX] Chunk {i}: {ref_count} refs, mode={func_mode}")
        elif ref_count > 0:
            print(f"    [CTX] Chunk {i}: {ref_count} refs nhưng không extract được content (require-only, không có function call)")
        else:
            print(f"    [CTX] Chunk {i}: không có external context (chunk độc lập)")
```

- [ ] **Step 6: Update logging in second call site (retry loop, `chunked_olm.py` ~line 646)**

Replace (lines ~646–652):
```python
            if chunk_content:
                mode = _detect_context_mode(chunk_content)
                print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs, mode={mode}")
            elif ref_count > 0:
                print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs nhưng không extract được content (require-only, không có function call)")
            else:
                print(f"    [CTX] Chunk {chunk_i} (retry): không có external context (chunk độc lập)")
```

With:
```python
            if chunk_content:
                func_mode = _detect_context_mode(chunk_content)
                has_req_full = "-- [REQUIRE FULL:" in chunk_content
                has_req_module = "-- [REQUIRE MODULE:" in chunk_content
                req_mode = "require_full" if has_req_full else ("require_module" if has_req_module else None)
                if req_mode:
                    print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs, func_mode={func_mode} | req_stubs={req_mode}")
                else:
                    print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs, mode={func_mode}")
            elif ref_count > 0:
                print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs nhưng không extract được content (require-only, không có function call)")
            else:
                print(f"    [CTX] Chunk {chunk_i} (retry): không có external context (chunk độc lập)")
```

- [ ] **Step 7: Run full test suite**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py -v
```

Expected: PASS all tests

- [ ] **Step 8: Commit**

```bash
git add chunked_olm.py test_require_stubs.py
git commit -m "feat: add require-stub markers to _detect_context_mode and update logging"
```

---

## Chunk 6: Final verification

### Task 6: Smoke test end-to-end with a real chunked file

Verify the new pipeline runs without errors on an actual Lua file that has require-only refs.

**Files:**
- No file changes — read-only verification

- [ ] **Step 1: Identify a suitable test file**

```bash
head -5 dst-scripts/actions.lua
```

`actions.lua` starts with `require "class"`, `require "bufferedaction"`, etc. — ideal for verifying require-only stubs. It's also large enough to trigger the chunked pipeline.

- [ ] **Step 2: Run a quick extraction test against a real file**

Create a throwaway script `_smoke_require_stubs.py`:

```python
"""Smoke test: extract require stubs for actions.lua chunk 1."""
import sys
sys.path.insert(0, ".")

from get_docs import safe_read_lua, extract_lua_references
from rag_get_fnc_content import extract_require_stubs, _resolve_lua_path
import config

lua = safe_read_lua("./dst-scripts/actions.lua")
refs = extract_lua_references(lua[:3000], "actions.lua")  # first 3000 chars

req_refs = [(p, f) for p, f in refs if not f]
print(f"require-only refs in first 3000 chars: {[p for p,f in req_refs]}")

if req_refs:
    result = extract_require_stubs(req_refs, max_tokens=2000)
    print(f"\n--- extract_require_stubs output ---\n{result[:500]}")
else:
    print("No require-only refs found in first 3000 chars")
```

```bash
.venv/Scripts/python _smoke_require_stubs.py
```

Expected: prints require-only refs and either full content or `-- [REQUIRE MODULE:` / `-- [REQUIRE FULL:` prefixed stubs. No exceptions.

- [ ] **Step 3: Clean up smoke test script**

```bash
rm _smoke_require_stubs.py
```

- [ ] **Step 4: Run all tests one final time**

```bash
.venv/Scripts/python -m pytest test_require_stubs.py -v
```

Expected: PASS all tests

- [ ] **Step 5: Final commit**

```bash
git add test_require_stubs.py
git commit -m "test: finalize require-only stub extraction test suite"
```

---

## Summary

| Task | Files | Tests |
|---|---|---|
| 1: Config constants | `config.py`, `chunked.py` | `test_stub_full_threshold_exists`, `test_context_reserve_raised` |
| 2: `_compress_module_stub()` | `rag_get_fnc_content.py` | 5 tests |
| 3: `extract_require_stubs()` | `rag_get_fnc_content.py` | 7 tests |
| 4: Wire into `extract_connected_for_chunk()` | `rag_get_fnc_content.py` | 3 integration tests |
| 5: `_detect_context_mode()` + logging | `chunked_olm.py` | 3 marker tests |
| 6: Smoke test | none | manual |

**Total new test functions:** 20
