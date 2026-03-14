# Design: Require-Only Stub Extraction

**Date:** 2026-03-15
**Branch:** feat/chunk-pipeline-quality-fixes
**Status:** Approved

## Problem

`extract_lua_references()` captures `require("class")`, `require("bufferedaction")`, etc. as refs with empty `func_names`. Every extractor (`extract_connected_content`, `extract_compact_content`, `extract_signatures_only`) skips these with `if not func_names: continue`. The LLM receives zero context about what required modules provide, making `external_deps` descriptions shallow or inaccurate.

## Goal

For require-only refs (empty `func_names`), inject enough context for the LLM to describe what each required module provides — without blowing the token budget.

## Scope

This feature targets the **per-chunk path only** (`extract_connected_for_chunk()` in `rag_get_fnc_content.py`). The file-level merge path (`main.py` → `process_chunked_file()` → `build_merge_prompt()`) uses `extract_connected_content()` directly and is **out of scope** — require-only refs at the merge level continue to appear as `("path", [])` with no content. This is acceptable because the merge prompt already receives per-chunk analyses that mention the required modules; full module stubs at merge level would duplicate tokens without proportional benefit.

## Approach: New `extract_require_stubs()` function (Approach B)

A dedicated function handles require-only refs separately from function-call refs. `extract_connected_for_chunk()` (in `rag_get_fnc_content.py`) calls both, combines results, within a shared 8000-token budget.

## Architecture & Data Flow

`extract_connected_for_chunk()` is defined in `rag_get_fnc_content.py` (not `chunked_olm.py`). All changes to the split/combine logic happen in that file.

### Fallback path interaction

`extract_connected_for_chunk()` has an early-return fallback branch that fires when `chunk_refs` is empty but `full_refs` is provided (the "cross-chunk require" case). This fallback returns before the new split/combine logic runs. **The new require-stub logic is NOT applied in the fallback path.** Rationale: the fallback already extracts signatures from `full_refs` via `components.X` pattern matching (func-call refs only); adding require-stub processing there would complicate the fallback for marginal gain. The fallback path continues unchanged.

The new split/combine logic runs only in the **normal path** (after the fallback guard), on `chunk_refs`:

```
chunk_refs = extract_lua_references(chunk_code, own_filename)

# --- Existing fallback path (UNCHANGED) ---
if not chunk_refs and full_refs:
    filtered_refs = [...]  # components.X pattern match on full_refs
    if not filtered_refs:
        return "", "", 0
    # ... signatures fallback, early return
    return fallback_section, fallback_content, len(fallback_kept_refs)

# --- Normal path — NEW split logic applied here ---
func_refs = [(path, funcs) for path, funcs in chunk_refs if funcs]
req_refs  = [(path, funcs) for path, funcs in chunk_refs if not funcs]

[Existing pipeline — budget: up to 8000 tokens]
  func_content = extract_connected_content(func_refs, max_total_tokens=8000)
  # func_content is already budget-capped (may be compressed/compact/sig-only internally)

[New pipeline — uses remaining budget]
  remaining_budget = 8000 - count_tokens(func_content)
  # count_tokens() called on the return value of extract_connected_content(), not intermediate state
  req_content = extract_require_stubs(req_refs, max_tokens=remaining_budget)
  # returns plain str (see Return Type section)

[Combine]
  if req_content:
      connected_content = func_content + "\n\n" + req_content
  else:
      connected_content = func_content

# connected_section includes only func_refs (format_connected_section(kept_refs))
# require-only refs are NOT added to connected_section — they have no func_names
# and format_connected_section("path", []) adds no useful information to the prompt header
```

### Return type of `extract_connected_for_chunk()`

Signature unchanged: `(connected_section, connected_content, ref_count)`. The combined content string is returned as `connected_content`. `ref_count` continues to count only `func_refs` (require-only refs excluded — consistent with existing behavior where empty-func refs returned 0).

## `extract_require_stubs(req_refs, max_tokens)` — new function in `rag_get_fnc_content.py`

**Return type:** `str` (plain string, not `(str, kept_refs)` tuple). Kept-refs is unnecessary here because require-only refs have no `func_names`, so `format_connected_section` would emit `("path", [])` which provides no additional information to the prompt header. The section header is handled entirely by inline markers in the content string.

Per require-only ref:

```
if max_tokens <= 0:
    return ""

if req_refs empty:
    return ""

for each (ref_path, []) in req_refs:
    read Lua file → lua_code
    file_tokens = count_tokens(lua_code)

    if file_tokens <= STUB_FULL_THRESHOLD:
        section = "-- [REQUIRE FULL: {ref_path}] ---\n" + lua_code
    else:
        section = _compress_module_stub(lua_code, ref_path)
        # returns formatted string or None on failure

    if section is None:
        continue  # skip, log warning

    if running_tokens + count_tokens(section) > max_tokens:
        log "[CTX] Require-stub budget exhausted after N/total refs"
        break

    append section, increment running_tokens

return "\n\n".join(sections)
```

## `_compress_module_stub(lua_code, ref_path)` — new private function in `rag_get_fnc_content.py`

Uses existing cache system (`_compression_cache_key` / `_load/_save_compression_cache`). Reuses `config.COMPRESSION_MODEL`.

**LLM prompt:**
```
Summarize this Lua module in 3–5 lines. Output format:
-- MODULE: <ClassName or module name>
-- exports: <key functions/constants, comma-separated>
-- purpose: <one sentence: what this module does>
-- notes: <side effects, globals registered> (omit if none)

Rules: Never invent. Output only the summary, no preamble.
SOURCE: {lua_code}
```

**Validation:** lenient — output is accepted if it contains at least `-- MODULE:`. If `-- exports:` or `-- purpose:` are missing, the result is still accepted (LLM may omit them for trivial modules). If `-- MODULE:` is absent entirely, discard and log:
```
[STUB] Output missing -- MODULE: marker, skipping {ref_path}
```

**On exception:** log `[STUB] LLM call failed for {ref_path}: {e}`, return `None`.

**Prefix for valid output:**
```
-- [REQUIRE MODULE: {ref_path}] ---
-- MODULE: ...
-- exports: ...
-- purpose: ...
```

## Config & Budget Changes

### `config.py`
```python
STUB_FULL_THRESHOLD = 400   # tokens — files smaller than this are included in full
```

`400 tokens` ≈ 1600 chars / ~40 lines of Lua. Small helper files go full; larger modules (e.g. `class.lua` at ~2000 tokens) go through LLM compression.

### Budget

| | Before | After |
|---|---|---|
| `max_total_tokens` default in `extract_connected_for_chunk()` | 3500 | 8000 |
| `CONTEXT_RESERVE` in `chunked.py` | 6000 | 8000 |
| Budget for func-call refs | 3500 | 8000 (used first) |
| Budget for require-stubs | 0 | `8000 - func_tokens` (remainder) |

**Critical:** `extract_connected_for_chunk()` is called from `chunked_olm.py` with `max_total_tokens=CONTEXT_RESERVE` (explicit argument, overrides default). Therefore `CONTEXT_RESERVE` in `chunked.py` **must also be updated to 8000** — otherwise the default change in `extract_connected_for_chunk()` has no effect in production. Both must be updated together.

If func-call refs exhaust all 8000 tokens → require-stubs are skipped entirely (graceful degrade).

## Marker Strings & Logging

Two new content markers:
- `"-- [REQUIRE FULL:"` — file included in full
- `"-- [REQUIRE MODULE:"` — LLM module summary

`_detect_context_mode()` in `chunked_olm.py` is used for logging only. When combined content contains both func content and require-stub content, **two separate `_detect_context_mode()` calls** are made — one for `func_content`, one for `req_content` — and both modes are logged. The combined `connected_content` string passed to the prompt is not re-analyzed by `_detect_context_mode()`.

Example log:
```
[CTX] Chunk 3: func_mode=compressed | 2 require-only refs → 1 full (380 tokens) + 1 module-summary (120 tokens)
[CTX] Require-stub budget exhausted after 3/5 refs
```

## Files Changed

| File | Change |
|---|---|
| `rag_get_fnc_content.py` | Add `_compress_module_stub()` and `extract_require_stubs()`; update `extract_connected_for_chunk()` to split refs, call `extract_require_stubs()`, combine content |
| `chunked_olm.py` | Update `_detect_context_mode()` to add new markers; update logging in call sites |
| `config.py` | Add `STUB_FULL_THRESHOLD = 400` |
| `chunked.py` | Update `CONTEXT_RESERVE` from 3500 to 8000 |
| `get_docs.py` | No changes |
| `chunked_prompt.py` | No changes |

## Error Handling Summary

| Scenario | Behavior |
|---|---|
| File not found | skip (same as existing behavior) |
| LLM output missing `-- MODULE:` marker | discard, log `[STUB] Output missing -- MODULE: marker, skipping {path}` |
| LLM output present but missing `-- exports:` or `-- purpose:` | accept (lenient validation) |
| LLM call exception | return `None`, log `[STUB] LLM call failed for {path}: {e}` |
| `remaining_budget <= 0` | return `""` immediately, no file reads |
| `req_refs` empty | return `""` immediately |
| func-call refs exhaust full 8000-token budget | require-stubs skipped with no log (normal operation) |

## Out of Scope

- File-level merge context (`main.py` / `build_merge_prompt()`) — see Scope section
- Modifying `extract_connected_content()`, `extract_signatures_only()`, `extract_compact_content()`
- Require-only refs in the non-chunked pipeline (`olm.py`)
- Checkpoint system changes
