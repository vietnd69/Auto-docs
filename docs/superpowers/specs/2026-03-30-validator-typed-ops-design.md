# Validator Redesign: Pre-filter + Typed Operations

**Date:** 2026-03-30
**Status:** Draft
**Scope:** `validator/src/validator/content/`

---

## Problem

The current validator uses a 3-guard system to compensate for LLM unreliability after applying
free-text patches. Guards use regex pattern matching on reviewer issue text to infer intent —
whether a deleted heading was intentional or accidental. This inference is inherently fragile:

- Guard 1 (heading integrity): fails when function names use single quotes instead of backticks,
  or are snake_case (not CamelCase). Root cause of the componentutil.lua oscillation failure.
- Guard 2 (hallucination enforcement): only recognises specific phrase patterns; misses the
  "local function / not exported" category entirely.
- Guard 3 (scope filter): heuristic field-label matching that conflicts with valid edge cases.

Each fix introduces new edge cases. This is the 5th logic error from the same root cause:
**text-patch + heuristic guards cannot reliably infer LLM intent**.

Research validation (Aider, Google, Huang et al. 2023):
- Text-anchor patches have ~15% application failure rate in production codebases.
- LLM self-correction without external grounding degrades or plateaus after 3–5 iterations.
- Structured typed operations + deterministic convergence criterion are the production standard.

---

## Goals

1. Reviewer has enough (and correctly scoped) context to verify every section of the `.md`
   against the `.lua` source — Overview, Usage example, Dependencies & tags, Properties,
   Main functions, Events & listeners.
2. Document format always has required fields; reviewer may flag 2–3 additional fields as
   appropriate.
3. Eliminate all guards. Replace with deterministic pre-filter + typed operations.
4. Stay within Qwen 3.5 Cloud effective context limit: ≤ 16K tokens per LLM call.

---

## Architecture

```
[Lua source + .md file]
        │
        ▼
Phase 1 — Deterministic Pre-filter          (no LLM, extend sections.py)
  ├── classify_lua_functions()     → local vs global map
  ├── prefilter_fn_blocks()        → strip local + hallucinated fn entries
  └── ensure_required_fields()    → auto-add skeleton for missing fields (fn-level only)
        │
        ▼ (clean doc: only public fns, required fn fields present)
Phase 2 — Section-aware LLM Review          (reviewer.py, prompts.py)
  Input per section: section text + section-specific Lua context (≤ 16K total)
  Output: typed findings list[Finding]
        │
        ▼
Phase 3 — Typed Writer Operations           (writer.py, prompts.py)
  Input per finding: one Finding + current target text snippet + Lua context (≤ 6K)
  Output: one TypedOp
        │
        ▼
Phase 4 — Deterministic Apply               (sections.py)
  apply_typed_ops(sections, ops, frontmatter) -> list[DocSection]
  → update_section, update_field, rewrite_function, delete_function
  No text-anchor matching. No guards.
        │
        ▼
Convergence: repeat Phase 2–4 until findings == [] or max_iterations reached
```

---

## Component Design

### 1. Pre-filter (`sections.py` extensions)

**`classify_lua_functions(lua_source: str) -> dict[str, str]`**

Scan each line of `lua_source`. Classification is line-prefix based, not via `_def_patterns`:

- Line matches `local function <name>` → `"local"`
- Line matches `local <name> = function` (i.e. `local\s+(\w+)\s*=\s*function`) → `"local"`
- Line matches `function <name>(` or `<name> = function` without `local` prefix → `"global"`

`_def_patterns(name)` is used only inside `prefilter_fn_blocks` to check function existence,
not to classify locality.

Returns `{"_ispassable": "local", "HasMeatInInventoryFor": "global", ...}`.

If the same name appears as both local (inner closure) and global (public wrapper), the last
definition wins, which is correct Lua scoping behaviour: the public wrapper is the one visible
to `require()`.

**`prefilter_fn_blocks(fn_blocks: list[str], lua_source: str) -> tuple[list[str], list[str]]`**

For each fn_block:
1. Extract raw function name from `### ` heading. Strip backticks and parameter list:
   `re.match(r'^### `?([^`(\n]+)', heading)` — same pattern already used in
   `extract_fn_headings_from_text`. The stripped name is used for all lookups.
2. Cross-check existence: run `_def_patterns(name)` against `lua_source`. Not found → strip
   (hallucination).
3. Check locality: look up name in `classify_lua_functions` result. `"local"` → strip.

Returns `(kept_blocks, stripped_names)`. `stripped_names` is passed into the review loop and
stored as `intentionally_removed: set[str]` so that `apply_typed_ops` can silently no-op any
`delete_function` op targeting an already-removed name.

**`ensure_required_fields(fn_blocks: list[str]) -> list[str]`**

Scope: fn_block fields only (`## Main functions` entries). Top-level section scaffolding
(e.g. a missing `## Properties` heading) is out of scope for this function — those gaps
are caught by the format validator (`format/checks.py`) which runs before content validation.

For each fn_block, check presence of:
- `* **Description:**`
- `* **Parameters:**`
- `* **Returns:**`

If any are absent, append a skeleton line (e.g. `* **Returns:** TODO`) so the reviewer always
has a target field, never an absent one. Returns updated `list[str]` (pure function,
not in-place mutation).

---

### 2. Section-specific Lua Context (`sections.py` extension)

**`extract_section_lua_context(section_heading: str, lua_source: str, max_tokens: int) -> str`**

Returns a Lua excerpt tailored to the section being reviewed. All extraction is line-regex
based on the existing `lua_source` string. Reuses `_truncate_blocks_to_lua_limit`.

| section_heading | Extraction strategy | Max tokens |
|---|---|---|
| `## Overview` | Lines from top of file until first `function` definition (module header, requires, constants) | 6K |
| `## Usage example` | Public function signatures only: lines matching `^function \w+` (name + params, no body) | 4K |
| `## Dependencies & tags` | Lines matching `require(`, `\.components\.`, `:HasTag(`, `:AddTag(`, `:RemoveTag(` | 5K |
| `## Properties` | If `Class(function` found: lines between it and the first nested `function` (constructor body). Fallback for utility modules (no `Class`): lines matching `^local [A-Z_]+\s*=` (module-level constants) + `^\w+\.\w+\s*=` (table property assignments). | 5K |
| `## Main functions` | Full source blocks for the function names in the current batch — existing `extract_lua_context()`. Batch size is determined dynamically (see below). | 8K |
| `## Events & listeners` | Lines matching `ListenForEvent\|PushEvent` + 2 lines of context around each | 4K |
| (other / unknown) | Empty string | — |

These are additive regex passes over `lua_source`, not recursive parsers. Each extraction
computes a concatenated string, then calls `_truncate_blocks_to_lua_limit` to enforce the token
cap.

**Dynamic batching for `## Main functions`**

Batch formation uses the existing `sub_chunk_section_lua_aware(fn_blocks, lua_source, lua_token_limit, doc_token_limit)`. The batch size is not a fixed function count — it is determined per-file by the Lua source token budget:

```
Total reviewer prompt budget:    16K  (Qwen 3.5 effective limit)
  − fixed overhead (rules, etc):  ~1K
  = available for content:        ~15K
    ├── Lua source blocks (primary constraint):  8K
    └── Doc fn_blocks (secondary constraint):    4K
```

`sub_chunk_section_lua_aware` iterates through `fn_blocks` in order. For each function it
calls `extract_lua_context(lua_source, [fn_name])` to measure the Lua token cost of that
function's source block. It groups functions into the current batch until the next function
would push cumulative Lua tokens past 8K **or** cumulative doc tokens past 4K. At that point
a new batch starts.

Result: each batch is exactly as large as will fit with full, untruncated Lua source attached.
After pre-filter strips local functions, batches naturally become smaller → remaining functions
get richer context. Functions whose Lua source is larger (e.g. complex multi-branch functions)
form smaller batches; simple getter/setter clusters form larger ones.

`sub_chunk_section_lua_aware` is called with `lua_token_limit=8000, doc_token_limit=4000`.

---

### 3. Typed Findings Schema (`reviewer.py`, `schemas.py`)

Replace `ReviewResult.issues: list[str]` with structured findings:

```python
@dataclass
class Finding:
    section: str          # e.g. "## Overview", "## Main functions"
    function: str | None  # None for non-function sections
    field: str | None     # e.g. "Returns", "Components used", None = whole section/function
    rule_id: str
    issue: str            # human-readable description

@dataclass
class ReviewResult:
    approved: bool
    findings: list[Finding]
```

One `Finding` per (section, function, field) tuple. If a function has three wrong fields,
the reviewer emits three separate `Finding` objects. This drives three separate writer calls
(one per finding), each with a focused ≤ 6K prompt. Latency trade-off is acceptable: each
writer call is much smaller than the current batch writer call, and convergence in ≤ 3 iterations
means the total call count is bounded.

**`rule_id` enum by section:**

| Section | Allowed rule_ids |
|---|---|
| `## Overview` | `WRONG_FILE_TYPE`, `INACCURATE_DESCRIPTION`, `MISSING_KEY_INFO` |
| `## Usage example` | `WRONG_FUNCTION_CALL`, `USES_INVALID_API`, `UNREALISTIC_EXAMPLE` |
| `## Dependencies & tags` | `MISSING_ENTRY`, `EXTRA_ENTRY`, `WRONG_USAGE_DESC` |
| `## Properties` | `WRONG_TYPE`, `WRONG_DEFAULT`, `MISSING_PROPERTY`, `EXTRA_PROPERTY` |
| `## Main functions` | `WRONG_VALUE`, `MISSING_PARAM`, `EXTRA_PARAM`, `WRONG_DESCRIPTION` |
| `## Events & listeners` | `MISSING_EVENT`, `WRONG_EVENT_NAME` |

Convergence criterion: `len(findings) == 0` → approved. No fingerprint heuristics needed.

---

### 4. Typed Operations Schema (`writer.py`, `schemas.py`)

```python
@dataclass
class TypedOp:
    op: str               # "update_section" | "update_field" | "rewrite_function" | "delete_function"
    section: str          # target section heading, e.g. "## Main functions"
    function: str | None  # None for non-function ops
    field: str | None     # None for whole-section or whole-function ops
    value: str | None     # new field value (single-line text), used by update_field
    content: str | None   # full replacement content, used by update_section / rewrite_function
```

Writer receives **one Finding at a time** + the current text of the target (section text for
section ops, fn_block text for function ops) + Lua context for that target. Prompt ≈ 3–5K tokens.

**Op types:**

| op | target | description |
|---|---|---|
| `update_section` | section | Replace full `section.text` (for Overview, Usage example rewrites) |
| `update_field` | section + optional function + field | Replace one field's value |
| `rewrite_function` | section + function | Replace entire fn_block for named function |
| `delete_function` | section + function | Remove fn_block for named function |

---

### 5. Apply Engine (`sections.py` extension)

**`apply_typed_ops(sections: list[DocSection], ops: list[TypedOp], frontmatter: str, intentionally_removed: set[str] | None = None) -> list[DocSection]`**

Returns a new `list[DocSection]` (does not mutate in place).

**`update_section`**: find `DocSection` where `section.heading == op.section`; replace
`section.text` with `op.content`. No-op if section not found (log warning).

**`update_field` (function = None)**: find section by heading; locate the field label
`* **{op.field}:**` in `section.text`; replace the remainder of that line (after the colon)
with `op.value`. Field boundary = single line only (the label + inline value). Multi-line
fields (e.g. `## Parameters` nested bullets) are not targeted by `update_field` — those
require `update_section` or `rewrite_function` instead.

**`update_field` (function = name)**: find section → split into fn_blocks via
`split_section_blocks` → find fn_block whose heading matches `op.function` using the same
backtick-stripping pattern as `delete_fn_block` (i.e. `re.escape(fn_name)` with optional
backtick prefix) → locate field label in fn_block → replace inline value on that line.
Reassemble fn_blocks into section text.

**`rewrite_function`**: find section → split into fn_blocks → replace block matching
`op.function` with `op.content`. If name not found: no-op + log warning (do not raise).

**`delete_function`**: find section → split into fn_blocks → remove block matching
`op.function`. If name is in `intentionally_removed` or not found: silent no-op.

---

### 6. Review Loop (`chunked.py` rewrite)

```python
# Top-level: iterate sections
frontmatter, sections = split_md_sections(md_content)
lua_classification = classify_lua_functions(lua_source)

for section in sections:
    lua_ctx = extract_section_lua_context(section.heading, lua_source, max_tokens=8000)

    if section.heading == "## Main functions":
        preamble, fn_blocks = split_section_blocks(section.text)
        fn_blocks, stripped_names = prefilter_fn_blocks(fn_blocks, lua_source)
        fn_blocks = ensure_required_fields(fn_blocks)
        intentionally_removed = set(stripped_names)

        # Batch size driven by Lua token budget, not fixed count.
        # lua_token_limit=8000 is primary; doc_token_limit=4000 is secondary.
        # A batch holds as many functions as can fit with full Lua source attached (≤ 16K total).
        batches = sub_chunk_section_lua_aware(
            fn_blocks, lua_source,
            lua_token_limit=8000, doc_token_limit=4000
        )
        for batch in batches:
            batch_text = "".join(batch)
            batch_lua_ctx = extract_lua_context(
                lua_source, extract_function_names(batch_text), max_tokens=8000
            )
            batch_text = _run_typed_loop(
                batch_text, batch_lua_ctx, section.heading,
                intentionally_removed, config
            )
            # write batch_text back into fn_blocks at correct offset
        section.text = preamble + "".join(fn_blocks)
    else:
        section.text = _run_typed_loop(
            section.text, lua_ctx, section.heading,
            intentionally_removed=set(), config=config
        )

Path(md_filepath).write_text(join_md_sections(frontmatter, sections), encoding="utf-8")


def _run_typed_loop(
    text: str,
    lua_ctx: str,
    section_heading: str,
    intentionally_removed: set[str],
    config: ValidationConfig,
) -> str:
    """Review + fix loop for one section or batch. Returns updated text."""
    for i in range(config.max_iterations):  # max_iterations = 3
        findings = _call_reviewer(text, lua_ctx, section_heading, config)
        if not findings:
            break
        for finding in findings:
            # Build a minimal context for the writer: target snippet + lua context
            target_text = _extract_target_text(text, finding)
            op = _call_writer(target_text, lua_ctx, finding, config)
            if op is None:
                continue
            # Apply single op: work on sections list, then extract updated text
            dummy_section = DocSection(heading=section_heading, text=text)
            updated = apply_typed_ops(
                [dummy_section], [op], frontmatter="",
                intentionally_removed=intentionally_removed
            )
            text = updated[0].text
    return text
```

`apply_typed_ops` receives `intentionally_removed` as a parameter so `delete_function` ops
targeting already-removed names are silently skipped without error.

Max iterations: **3**. Research shows beyond 3 iterations adds noise, not signal.

---

## Files Changed

| File | Change |
|---|---|
| `validator/src/validator/content/sections.py` | Add `classify_lua_functions`, `extract_section_lua_context`, `prefilter_fn_blocks`, `ensure_required_fields`, `apply_typed_ops` |
| `validator/src/validator/content/reviewer.py` | Replace `issues: list[str]` with `findings: list[Finding]`; add `Finding` dataclass; update parse functions |
| `validator/src/validator/content/writer.py` | Replace `Patch`/`apply_patches` with `TypedOp`; update parse functions |
| `validator/src/validator/content/prompts.py` | Section-specific reviewer prompts; per-finding writer prompt |
| `validator/src/validator/content/schemas.py` | Replace `REVIEW_SCHEMA` and `PATCHES_SCHEMA` with new typed schemas |
| `validator/src/validator/content/chunked.py` | Remove all guard logic; implement new loop as described above |
| `validator/tests/test_content_chunked.py` | Update for new schemas and loop behaviour |

Files **not** changed: `format/checks.py`, `format/autofix.py`, `pipeline.py`, `loop.py`
(small-section path), `update/validate_update.py`.

---

## Test Scenarios Required

1. `classify_lua_functions`: name appears as both `local` closure and public wrapper → global wins.
2. `prefilter_fn_blocks`: heading uses backtick notation (`### \`_ispassable(...)\``) → name
   extraction strips backticks correctly before lookup.
3. `apply_typed_ops` `update_field`: field has single-line value — only that line is replaced.
4. `apply_typed_ops` `rewrite_function`: function name not found → silent no-op, no exception.
5. `apply_typed_ops` `delete_function`: name in `intentionally_removed` → silent no-op.
6. `_run_typed_loop`: writer returns op for already-removed function → no error, loop continues.
7. `prefilter_fn_blocks`: all fn_blocks stripped (all functions are local) → empty kept_blocks,
   loop skips review entirely.

---

## What Gets Eliminated

| Current mechanism | Replaced by |
|---|---|
| Guard 1 — restore accidentally lost headings | Impossible: typed ops target by name |
| Guard 2 — enforce hallucination removals | Pre-filter: cross-check against Lua source |
| Guard 3 — reject structure-changing patches | Impossible: op schema has no structure op |
| Oscillation fingerprint heuristic | Unnecessary: convergence = `findings == []` |
| `_named_in_issues` regex patterns | Eliminated entirely |
| `_REMOVAL_PHRASES` list | Eliminated entirely |
| `restore_lost_blocks()` call in batch loop | Eliminated entirely |
| Free-text `Patch` / `apply_patches` | Replaced by `TypedOp` / `apply_typed_ops` |
