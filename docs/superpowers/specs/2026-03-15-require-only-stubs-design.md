# Design: Require-Only Stub Extraction

**Date:** 2026-03-15
**Branch:** feat/chunk-pipeline-quality-fixes
**Status:** Approved

## Problem

`extract_lua_references()` captures `require("class")`, `require("bufferedaction")`, etc. as refs with empty `func_names`. Every extractor (`extract_connected_content`, `extract_compact_content`, `extract_signatures_only`) skips these with `if not func_names: continue`. The LLM receives zero context about what required modules provide, making `external_deps` descriptions shallow or inaccurate.

## Goal

For require-only refs (empty `func_names`), inject enough context for the LLM to describe what each required module provides — without blowing the token budget.

## Approach: New `extract_require_stubs()` function (Approach B)

A dedicated function handles require-only refs separately from function-call refs. `extract_connected_for_chunk()` calls both, combines results, within a shared 8000-token budget.

## Architecture & Data Flow

```
chunk_refs = extract_lua_references(chunk_code)
         │
         ├─ func_refs  = [(path, funcs)] where funcs non-empty  ← existing pipeline
         └─ req_refs   = [(path, [])]    where funcs empty      ← NEW

[Existing pipeline]
  func_content = extract_connected_content(func_refs, max_total_tokens=8000)

[New pipeline]
  remaining_budget = 8000 - count_tokens(func_content)
  req_content = extract_require_stubs(req_refs, max_tokens=remaining_budget)

final_content = func_content + "\n\n" + req_content  (if req_content non-empty)
```

### `extract_require_stubs(req_refs, max_tokens)` — in `rag_get_fnc_content.py`

Per require-only ref:

```
read Lua file
    │
    ├─ file_tokens ≤ STUB_FULL_THRESHOLD (400 tokens)
    │     → include full content
    │       prefix: "-- [REQUIRE FULL: path] ---"
    │
    └─ file_tokens > STUB_FULL_THRESHOLD
          → call _compress_module_stub(lua_code) via LLM
               │
               ├─ success → "-- [REQUIRE MODULE: path] ---\n-- MODULE: ...\n-- exports: ...\n-- purpose: ..."
               └─ failure → skip ref (no fallback — no func_names to extract sig from)
```

Budget is checked incrementally (same pattern as `_truncate_sections_to_budget`). When cumulative tokens exceed `max_tokens`, remaining refs are dropped.

### `_compress_module_stub(lua_code)` — new private function

LLM prompt:
```
Summarize this Lua module in 3–5 lines. Output format:
-- MODULE: <ClassName or module name>
-- exports: <key functions/constants, comma-separated>
-- purpose: <one sentence: what this module does>
-- notes: <side effects, globals registered> (omit if none)

Rules: Never invent. Output only the summary, no preamble.
SOURCE: {lua_code}
```

Uses existing cache system (`_compression_cache_key` / `_load/_save_compression_cache`). Reuses `config.COMPRESSION_MODEL`.

## Config Changes

### `config.py`
```python
STUB_FULL_THRESHOLD = 400   # tokens — files smaller than this are included in full
```

`STUB_FULL_THRESHOLD = 400` ≈ 1600 chars / ~40 lines of Lua. Small helper files go full; larger modules (like `class.lua` at 258 lines ≈ 2000 tokens) go through LLM.

### Budget

| | Before | After |
|---|---|---|
| `max_total_tokens` default in `extract_connected_for_chunk()` | 3500 | 8000 |
| Budget for func-call refs | 3500 | 8000 (used first) |
| Budget for require-stubs | 0 | `8000 - func_tokens` (remainder) |

If func-call refs exhaust all 8000 tokens → require-stubs are skipped entirely (graceful degrade).

## Marker Strings

Two new markers for `_detect_context_mode()` in `chunked_olm.py`:
- `"-- [REQUIRE FULL:"` → mode `"require_full"`
- `"-- [REQUIRE MODULE:"` → mode `"require_module"`

Used only for logging, no impact on merge logic.

## Files Changed

| File | Change |
|---|---|
| `rag_get_fnc_content.py` | Add `_compress_module_stub()` and `extract_require_stubs()` |
| `chunked_olm.py` | Split `req_refs` in `extract_connected_for_chunk()`, call `extract_require_stubs()`, combine results; update `_detect_context_mode()` |
| `config.py` | Add `STUB_FULL_THRESHOLD = 400` |
| `get_docs.py` | No changes |
| `chunked_prompt.py` | No changes |

## Error Handling

| Scenario | Behavior |
|---|---|
| File not found | skip (same as existing behavior) |
| LLM output missing `-- MODULE:` marker | discard, skip ref |
| `remaining_budget <= 0` | return `""` immediately, no file reads |
| `req_refs` empty | return `""` immediately |
| LLM call exception | skip ref, log warning |

## Log Output

```
[CTX] Chunk 3: 2 require-only refs → 1 full (380 tokens) + 1 module-summary (120 tokens)
[CTX] Require-stub budget exhausted after 3/5 refs
```

## Out of Scope

- Modifying `extract_connected_content()`, `extract_signatures_only()`, `extract_compact_content()`
- Modifying prompt templates in `chunked_prompt.py`
- Checkpoint system changes
- Handling require-only refs in the non-chunked pipeline (`olm.py`)
