# Validator Restructure Design

**Date:** 2026-03-21
**Status:** Draft
**Scope:** Restructure `validator/` into two functional groups: LLM-based content validation and no-LLM format validation

---

## Context

The current `validator/` package mixes multiple responsibilities across files:
- `validator.py` — format checks (frontmatter, headings, duplication, emoji, MDX)
- `autofix_mdx.py` — 12+ auto-fix strategies with iterative MDX loop
- `fix_format.py` — LLM-powered full file regeneration for severe format issues
- `validate_update.py` — metadata/change tracking validation
- `validate_mdx.mjs` — Node.js MDX compile & eval

The goal is to split into two clear groups:
1. **Content validation** — LLM2 reviews content created by LLM1, iterative loop until approved
2. **Format validation** — check and fix .md format for Docusaurus rendering, no LLM needed

## Decisions

- **Approach B (Pipeline-oriented)** — 3 sub-packages: `content/`, `format/`, `update/`
- **`fix_format.py` removed** — replaced by content validation loop
- **LLM1/LLM2 models are configurable** — can use different models for writer and reviewer
- **Sequential per file** — File N (content loop -> format fix) before File N+1
- **Content loop exits** on structured `approved=true` OR max iterations reached
- **Format refactored** — `checks.py` (detect only) separated from `autofix.py` (fix only)

---

## Directory Structure

```
validator/src/validator/
├── __init__.py
├── __main__.py              # Entry point — CLI args for content/format/full
├── constants.py             # Shared constants
├── utils.py                 # Shared utilities: resolve_lua_path(), DOCS_DIR resolution
│
├── content/                 # Group 1: LLM-based content validation
│   ├── __init__.py
│   ├── reviewer.py          # LLM2: review doc, return structured feedback
│   ├── writer.py            # LLM1: patch-based rewrite from reviewer feedback
│   ├── loop.py              # Orchestrate write → review → fix → approve loop
│   ├── chunked.py           # (Future) Chunked file content validation strategy
│   └── prompts.py           # Prompt templates for writer & reviewer
│
├── format/                  # Group 2: No-LLM format validation
│   ├── __init__.py
│   ├── checks.py            # Pure validation — returns errors, never modifies files
│   ├── autofix.py           # Fix logic — receives errors, modifies files
│   ├── mdx.py               # Python wrapper calling validate_mdx.mjs
│   └── validate_mdx.mjs     # Node.js MDX compile + eval (unchanged)
│
├── update/                  # Group 3: Metadata/change tracking
│   ├── __init__.py
│   └── validate_update.py   # Existing logic, moved here
│
└── pipeline.py              # Full pipeline: content loop → format fix, per file
```

### File Migration Map

| Current File | New Location | Notes |
|---|---|---|
| `validator.py` | `format/checks.py` + `format/mdx.py` | Split + extract: `check_frontmatter`, `check_required_headings`, `check_duplication` exist as functions; `check_emoji` and `check_filler_text` are **new extractions** from inline logic in `validate_full()` |
| `autofix_mdx.py` | `format/autofix.py` | Renamed, restructured return types. **Behavioral change:** Phase 2 now calls `checks.validate_all()` for detection instead of inline `get_mdx_errors()` |
| `fix_format.py` | **Deleted** | Replaced by `content/loop.py`. Lua path resolution logic (md→lua mapping) ported to shared `utils.py` |
| `validate_update.py` | `update/validate_update.py` | Moved. **Import changes required:** `from .validator import validate_full` → `from validator.format.checks import validate_all`; adapt `["OK"]` check to empty `list[ValidationError]` check |
| `validate_mdx.mjs` | `format/validate_mdx.mjs` | Moved, unchanged |
| `constants.py` | `constants.py` | Stays at package root |
| `__main__.py` | `__main__.py` | Rewritten for new pipeline. **Fix:** `DOCS_DIR` resolution uses `llm.paths.PROJECT_ROOT` instead of relative `__file__` path |

---

## Shared Utilities (`utils.py`)

Ported from `fix_format.py` lines 117-131. Contains non-trivial business logic for mapping between .md docs and Lua source files.

```python
from llm.paths import PROJECT_ROOT

DOCS_DIR = PROJECT_ROOT / "dst-api-webdocs" / "docs"
LUA_DIR = PROJECT_ROOT / "dst-scripts"

def resolve_lua_path(md_filepath: str) -> str | None:
    """
    Map .md doc path to corresponding .lua source path.
    e.g. dst-api-webdocs/docs/map/rooms/four.md → dst-scripts/map/rooms/four.lua
    Returns None if Lua file doesn't exist.
    """

def resolve_connected_content(lua_filepath: str) -> tuple[str, str]:
    """
    Extract connected section + connected content from Lua source.
    Calls rag.docs.extract_lua_references() + rag.docs.format_connected_section()
    + rag.content.extract_connected_content()
    Returns (connected_section, connected_content)
    """
```

---

## Content Validation Loop (`content/`)

### Data Flow

```
LLM2 review doc ──► approved? ──yes──► done
                       │
                       no
                       │
                       ▼
               LLM1 fix doc (using feedback)
                       │
                       ▼
               LLM2 review again ──► loop
                       │
                  max iterations? ──► exit with remaining issues
```

First iteration: LLM2 reviews the doc that was already created by the core pipeline (LLM1). No rewrite needed upfront.

### `reviewer.py`

```python
@dataclass
class ReviewResult:
    approved: bool
    issues: list[str]       # Description of each problem found
    suggestions: list[str]  # Specific fix suggestions

def review_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    model: str,
) -> ReviewResult:
```

**Review criteria (LLM2 checks against source code + context):**
1. Function signatures/params match Lua source — detect hallucination
2. Code examples match actual API
3. Descriptions are accurate and complete
4. Connected references are mentioned correctly

### `writer.py`

```python
@dataclass
class Patch:
    old_text: str
    new_text: str
    reason: str

def rewrite_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    review_feedback: ReviewResult,
    model: str,
) -> list[Patch]:
```

LLM1 receives specific feedback (issues + suggestions) and returns **patches** — targeted `old_text` → `new_text` replacements. Does NOT rewrite the entire document.

**Patch application:**
```python
for patch in patches:
    content = content.replace(patch.old_text, patch.new_text, 1)
```

**Fallback:** If >50% of patches fail to match (LLM hallucinated `old_text`), LLM1 rewrites the full content body (keeping frontmatter intact).

### `loop.py`

```python
@dataclass
class ContentLoopConfig:
    max_iterations: int = 3
    writer_model: str = "qwen3.5:cloud"
    reviewer_model: str = "qwen3.5:cloud"

@dataclass
class ContentLoopResult:
    approved: bool
    iterations: int
    final_issues: list[str]

def run_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
```

Internally calls `utils.resolve_connected_content(lua_filepath)` to obtain connected content for both reviewer and writer. This creates a dependency on `rag` package (via `utils.py`).

**Loop steps:**
1. Read .md + lua source + resolve connected content via `utils.py`
2. LLM2 review → `ReviewResult`
3. If `approved=True` → return success
4. If `approved=False` → LLM1 rewrite using feedback → write .md
5. Back to step 2
6. If `iterations >= max_iterations` → return with `approved=False` + remaining issues

### `chunked.py` — Future: Chunked File Strategy

**Scope:** Directory and file placeholder only. No implementation in this spec.

Files ≥32K tokens cannot fit in a single LLM context for review. The content loop (`loop.py`) only handles standard-size files. `chunked.py` will define a separate strategy for large files — likely section-by-section review or chunk-level review with cross-chunk consistency checks.

**For now:** `pipeline.py` skips content validation for chunked files (detected via `llm.tokens.count_tokens()`), logs them as `"skipped_chunked"`, and proceeds to format validation only.

### `prompts.py`

Prompt templates for both writer and reviewer roles. Reviewer prompt instructs LLM2 to return structured JSON. Writer prompt includes the review feedback to guide targeted fixes.

---

## Format Validation (`format/`)

### Principle: Detect vs Fix Separation

`checks.py` only detects and returns errors. `autofix.py` only fixes. They never cross responsibilities.

### `checks.py`

```python
@dataclass
class ValidationError:
    category: str      # "mdx", "yaml", "format", "frontmatter"
    severity: str      # "error", "warning"
    message: str
    line: int | None = None

def check_frontmatter(text: str) -> list[ValidationError]
def check_required_headings(text: str) -> list[ValidationError]
def check_duplication(text: str) -> list[ValidationError]
def check_emoji(text: str) -> list[ValidationError]
def check_filler_text(text: str) -> list[ValidationError]

def validate_all(filepath: str) -> list[ValidationError]:
    """Run all checks including MDX validation. Returns structured errors."""
```

Changes from current `validator.py`:
- Returns `ValidationError` dataclass instead of raw strings
- Each check is an independent function, testable in isolation
- `validate_all()` aggregates all checks including MDX

### `mdx.py`

```python
def validate_mdx(filepath: str) -> list[ValidationError]:
    """Call validate_mdx.mjs via subprocess, parse JSON into ValidationError list."""
```

Extracted from `validate_mdx_via_node()` in current `validator.py`.

### `autofix.py`

```python
@dataclass
class FixResult:
    changes: list[str]
    remaining_errors: list[ValidationError]

def autofix_file(filepath: str) -> FixResult:
    """
    Phase 1: Static fixes (emoji, frontmatter, filler, tables, braces, etc.)
    Phase 2: Iterative MDX loop (max 10 iterations)
    Returns: changes made + remaining errors after fix
    """
```

Changes from current `autofix_mdx.py`:
- Returns `FixResult` with structured remaining errors
- Calls `checks.validate_all()` for detection instead of inline detection
- `remaining_errors` tells pipeline what to do next

### `validate_mdx.mjs`

Unchanged. Moved to `format/` directory.

---

## Pipeline & Entry Point

### `pipeline.py`

```python
@dataclass
class PipelineConfig:
    content_max_iterations: int = 3
    writer_model: str = "qwen3.5:cloud"
    reviewer_model: str = "qwen3.5:cloud"
    skip_content: bool = False
    skip_format: bool = False

@dataclass
class FileResult:
    filepath: str
    content_result: ContentLoopResult | None
    format_result: FixResult | None
    final_status: str   # "ok", "content_failed", "format_failed", "skipped_chunked"

def process_file(md_filepath: str, config: PipelineConfig) -> FileResult:
    """
    Resolves lua_filepath via utils.resolve_lua_path(md_filepath).
    If Lua source not found and content validation requested, logs warning and skips content step.
    If file is chunked (≥32K tokens), skips content validation, logs as "skipped_chunked", proceeds to format only.
    """

def process_batch(target: str, config: PipelineConfig) -> list[FileResult]
```

**Per-file flow:**
1. Resolve Lua source path via `utils.resolve_lua_path(md_filepath)`
2. If `skip_content=False` and Lua source exists: run content loop
2. If `skip_format=False`: run format checks → autofix if needed → re-validate
3. Return `FileResult` with combined status

**Batch features:**
- Ctrl+C safe — saves progress, logs remaining files
- Summary report at end

### `__main__.py` CLI

```
uv run validator                          # full pipeline (content + format)
uv run validator --content-only           # content loop only
uv run validator --format-only            # format validation only
uv run validator path/to/file.md          # single file
uv run validator path/to/dir/             # batch directory
uv run validator --max-iterations 5       # custom max iterations
uv run validator --writer-model X         # custom writer model
uv run validator --reviewer-model Y       # custom reviewer model
```

### `update/validate_update.py`

Moved from root. Logic unchanged. Called separately when needed (requires `diff_report` input, not part of default pipeline).

---

## Dependencies

### New Python Dependencies

Add workspace dependencies to `validator/pyproject.toml`:
- `mod-document-llm` — for `ollama_chat` (content loop LLM calls)
- `mod-document-rag` — for `extract_connected_content`, `extract_lua_references`, etc.

No new external (PyPI) dependencies needed.

### Cross-Package Imports

```
utils.py
  → llm.paths.PROJECT_ROOT          # Path resolution
  → rag.content.extract_connected_content  # Connected content
  → rag.docs.safe_read_lua, extract_lua_references, format_connected_section

content/loop.py
  → utils.resolve_connected_content  # Connected content (via utils)
  → llm.client.ollama_chat           # LLM calls

format/checks.py
  → format/mdx.py                   # MDX validation subprocess

format/autofix.py
  → format/checks.py                # Detect errors before fixing

pipeline.py
  → content/loop.py
  → format/checks.py
  → format/autofix.py
```

---

## Test Migration

| Current Test | New Location | Changes |
|---|---|---|
| `tests/test.py` | `tests/test_smoke.py` | Update imports |
| `tests/test_fix_ref.py` | `tests/test_format_autofix.py` | `from validator.autofix_mdx` → `from validator.format.autofix` |
| `tests/test_logic.py` | `tests/test_format_checks.py` | `from validator.autofix_mdx` → `from validator.format.autofix`; fix `AssertionError` typo → `AssertionError` |

New tests to add:
- `tests/test_content_reviewer.py` — test ReviewResult parsing from LLM response
- `tests/test_content_loop.py` — test loop termination conditions (approved, max iterations)
- `tests/test_utils.py` — test `resolve_lua_path` mapping logic

---

## What Gets Deleted

- `fix_format.py` — entirely replaced by content validation loop
- Raw string error format (`"[mdx] ..."`) — replaced by `ValidationError` dataclass
- Inline detection logic in `autofix_mdx.py` — delegates to `checks.py`

## What Stays Unchanged

- `validate_mdx.mjs` — Node.js MDX validation logic
- `constants.py` — shared constants (may add new ones for content loop)
- All existing auto-fix strategies in `autofix_mdx.py` — logic preserved, just reorganized

## What Requires Adaptation (not just move)

- `validate_update.py` — import paths change, `["OK"]` return contract replaced by `list[ValidationError]`
- `autofix_mdx.py` → `autofix.py` — Phase 2 detection delegates to `checks.validate_all()` instead of inline `get_mdx_errors()`
- `__main__.py` — full rewrite; `DOCS_DIR` resolution fixed via `utils.py`
