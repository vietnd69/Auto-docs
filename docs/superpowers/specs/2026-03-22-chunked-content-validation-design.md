# Chunked Content Validation — Design Spec

**Date:** 2026-03-22
**Status:** Approved
**Scope:** `validator/src/validator/content/`

---

## Problem

The content validation loop (`loop.py`) sends the full Lua source + full markdown doc to an LLM for review. Files with Lua source >= 32,000 tokens cannot fit in a single LLM context, so `pipeline.py` currently skips content validation for these files and logs `final_status = "skipped_chunked"`.

This means large files — often the most complex components in DST — receive zero content validation.

---

## Goal

Implement full-accuracy content validation for large files by processing the markdown document section-by-section, each section reviewed against a focused Lua context derived from the function names mentioned in that section.

The result must be a `ContentLoopResult` with the same semantics as the standard loop: `approved=True` means all sections passed, `approved=False` means at least one section has unresolved issues.

---

## Approach: Doc-Section-Centric Per-Section Loop

For each `##` section in the markdown doc:
1. Extract function names mentioned in the section
2. Find those functions in the Lua source → focused `lua_context`
3. Run a `[review → fix → review]` loop (up to `max_iterations`) on the section
4. Apply patches to the section text, write updated content to disk after each patch apply

Final result aggregates across all sections.

---

## Architecture

### Files

| File | Action | Purpose |
|------|--------|---------|
| `validator/src/validator/content/sections.py` | CREATE | Split/parse helpers, function name extraction, Lua context extraction |
| `validator/src/validator/content/chunked.py` | MODIFY | `run_chunked_content_loop()` — main entry point |
| `validator/src/validator/content/prompts.py` | MODIFY | Add section-level reviewer + writer prompts |
| `validator/src/validator/pipeline.py` | MODIFY | Call chunked loop instead of skipping |

### Data Flow

```
md_filepath → read → split_md_sections() → [Section, Section, ...]
lua_filepath → read → lua_source (full text, not passed to LLM directly)

for each section (frontmatter excluded):
    fn_names = extract_function_names(section.text)
    lua_ctx  = extract_lua_context(lua_source, fn_names)

    for i in range(config.max_iterations):
        if stop_check(): return interrupted result

        review = review_section(section.text, lua_ctx, reviewer_model)
        if review.approved: break

        patches = write_section_patches(section.text, lua_ctx, review, writer_model)
        if not patches: break

        section.text, failed = apply_patches(section.text, patches)
        write updated md_content to disk

reassemble md_content from updated sections + frontmatter
write final md_content to disk

return ContentLoopResult(
    approved  = all sections approved,
    iterations = total iterations summed across sections,
    final_issues = flat list from all failed sections,
)
```

---

## Component Design

### `sections.py`

#### `DocSection` dataclass
```python
@dataclass
class DocSection:
    heading: str    # e.g. "## Functions"
    text: str       # full text including heading line
```

#### `split_md_sections(md_content: str) -> tuple[str, list[DocSection]]`
- Returns `(frontmatter, sections)`
- Splits on `##` headings only (not `###`)
- Frontmatter (`---...---` block at top) is extracted and excluded from sections
- Each section includes its heading line through to the next `##` heading

#### `extract_function_names(section_text: str) -> list[str]`
Regex scan to extract function identifiers. Patterns in priority order:

| Pattern | Example | Captures |
|---------|---------|---------|
| `### FunctionName` heading | `### GetOwner` | `GetOwner` |
| Backtick + paren | `` `GetOwner(` `` | `GetOwner` |
| Code block method call | `inst:GetOwner(` | `GetOwner` |
| Standalone backtick | `` `GetOwner` `` | `GetOwner` |

Returns unique, deduped list.

#### `extract_lua_context(lua_source: str, fn_names: list[str]) -> str`
For each function name, find its definition in Lua source using patterns:
- `function X:Name(`
- `function Name(`
- `X.Name = function(`
- `Name = function(`

Extract from the definition line through the matching `end` (via indentation/end counting). Concatenate all matches.

**Fallback:** If no functions found → return `""`. The section reviewer prompt handles this gracefully (reviews structure only).

**Token guard:** If extracted context > 8,000 tokens → truncate with `-- [truncated]` comment appended.

---

### `chunked.py` — `run_chunked_content_loop`

```python
def run_chunked_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
```

Same signature as `run_content_loop`. Pipeline calls either interchangeably.

**Logging pattern:**
```
[content/chunked] 8 sections found
[content/chunked] Section 2/8 "## Functions" — 3 fn(s) found, reviewing...
[content/chunked] Section 2/8 — approved at iteration 1
[content/chunked] Section 5/8 "## Events" — 0 fn(s) found, reviewing structure only...
[content/chunked] Section 5/8 — rejected (2 issues), patching...
[content/chunked] Section 5/8 — approved at iteration 2
[content/chunked] Final: 7/8 approved, 1 section failed
```

**Disk write:** After each `apply_patches`, reassemble full md_content and write to disk — consistent with `loop.py` line 107.

---

### `prompts.py` — New Functions

#### `build_section_reviewer_prompt(section_text, lua_context) -> str`
Parallel to `build_reviewer_prompt` but:
- Scoped to one section, not full doc
- Uses focused `lua_context` (not full Lua source)
- If `lua_context == ""`: prompt states "no Lua context available, review structural accuracy only"
- Same JSON response format: `{"approved": bool, "issues": [...], "suggestions": [...]}`

#### `build_section_writer_prompt(section_text, lua_context, issues, suggestions) -> str`
Parallel to `build_writer_prompt` but:
- Scoped to one section
- `old_text` in patches must be a substring of `section_text`
- Patches applied to full doc via existing `apply_patches()` — works because section text is unique in doc context

---

### `pipeline.py` — Integration

Replace the current skip block (lines 57–64) with:

```python
# BEFORE:
if lua_code and count_tokens(lua_code) >= CHUNKED_TOKEN_THRESHOLD:
    print(f"  [pipeline] File is chunked (>={CHUNKED_TOKEN_THRESHOLD} tokens), skipping content")
    return FileResult(
        filepath=md_filepath,
        content_result=None,
        format_result=None,
        final_status="skipped_chunked",
    )

# AFTER:
if lua_code and count_tokens(lua_code) >= CHUNKED_TOKEN_THRESHOLD:
    print(f"  [pipeline] File is chunked, running per-section validation...")
    content_result = run_chunked_content_loop(md_filepath, lua_filepath, content_config)
    # falls through to normal content_result handling
```

`final_status = "skipped_chunked"` is retained in `FileResult` for backward compatibility but will no longer be set for chunked files after this change.

---

## Edge Cases

| Case | Handling |
|------|---------|
| Section with no function names found | `lua_ctx = ""`, reviewer prompt says "structure only" |
| `extract_lua_context` extracts > 8K tokens | Truncate with `-- [truncated]` |
| All patches fail for a section | Log warning, mark section as failed, continue |
| `stop_check()` fires mid-loop | Return `ContentLoopResult(approved=False, final_issues=["Interrupted"])` immediately |
| Markdown has no `##` headings | Return single section = full doc (degrades gracefully to almost-standard behavior) |
| Lua source file unreadable | Return `ContentLoopResult(approved=False, final_issues=["Cannot read Lua source"])` |

---

## Not in Scope

- Cross-section consistency checks (e.g., verifying that cross-references between sections are accurate)
- Async/parallel section processing
- Caching of `extract_lua_context` results across iterations

---

## Testing

- Unit tests for `split_md_sections` (frontmatter extraction, section splitting)
- Unit tests for `extract_function_names` (pattern coverage)
- Unit tests for `extract_lua_context` (method/function/table patterns, fallback, token guard)
- Integration test: mock LLM, run `run_chunked_content_loop` on a fixture large doc, assert patches applied and result structure correct
- Regression: `pipeline.py` `process_file` with chunked fixture no longer returns `skipped_chunked`
