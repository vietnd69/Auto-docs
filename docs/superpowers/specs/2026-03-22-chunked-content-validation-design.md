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
4. Apply patches to the section text, write the full reassembled doc to disk after each apply

Final result aggregates across all sections.

---

## Architecture

### Files

| File | Action | Purpose |
|------|--------|---------|
| `validator/src/validator/content/sections.py` | CREATE | Split/parse helpers, function name extraction, Lua context extraction |
| `validator/src/validator/content/chunked.py` | MODIFY | `run_chunked_content_loop()` + `review_section()` + `write_section_patches()` |
| `validator/src/validator/content/prompts.py` | MODIFY | Add section-level reviewer + writer prompts |
| `validator/src/validator/pipeline.py` | MODIFY | Call chunked loop instead of skipping |

Note: `chunked.py` already exists as a placeholder stub — this implements it.

### Data Flow

```python
md_content = Path(md_filepath).read_text(encoding="utf-8")  # exception propagates if unreadable
lua_source = safe_read_lua(lua_filepath)
if lua_source is None:
    return ContentLoopResult(
        approved=False, iterations=0,
        final_issues=[f"Cannot read Lua source: {lua_filepath}"],
    )

frontmatter, sections = split_md_sections(md_content)

if not sections:
    return ContentLoopResult(approved=True, iterations=0, final_issues=[])

total_iterations = 0
all_failed_issues = []

for idx, section in enumerate(sections):
    fn_names = extract_function_names(section.text)
    lua_ctx  = extract_lua_context(lua_source, fn_names)
    section_approved = False
    last_review = None

    for i in range(config.max_iterations):
        if config.stop_check():
            return ContentLoopResult(
                approved=False, iterations=total_iterations,
                final_issues=["Interrupted by user"],
            )

        total_iterations += 1
        last_review = review_section(section.text, lua_ctx, config.reviewer_model)

        if last_review.approved:
            section_approved = True
            break

        patches = write_section_patches(section.text, lua_ctx, last_review, config.writer_model)
        if not patches:
            break  # writer gave up, section stays failed

        section.text, failed = apply_patches(section.text, patches)
        # apply_patches imported from validator.content.writer — not duplicated
        # partial failure: log warning if failed > 0, continue loop regardless
        Path(md_filepath).write_text(
            join_md_sections(frontmatter, sections), encoding="utf-8"
        )

    else:
        # max_iterations exhausted — run a final review on the current (post-patch) text
        # mirrors loop.py lines 110-120 to ensure final_issues reflect actual current state
        last_review = review_section(section.text, lua_ctx, config.reviewer_model)
        total_iterations += 1
        section_approved = last_review.approved

    if not section_approved and last_review is not None:
        all_failed_issues.extend(last_review.issues)

return ContentLoopResult(
    approved=len(all_failed_issues) == 0,
    iterations=total_iterations,
    final_issues=all_failed_issues,
)
```

Note on `iterations`: "total LLM review cycles across all sections" (not per-file). Noted in log output.

Note on interrupted status: when `stop_check()` fires, `approved=False` propagates through `pipeline.py` as `final_status="content_failed"`. This is expected behavior — same as the standard loop.

---

## Component Design

### `sections.py`

#### `DocSection` dataclass
```python
@dataclass
class DocSection:
    heading: str    # e.g. "## Functions"  (empty string for preamble before first ##)
    text: str       # full text: heading line + "\n" + body, ending with "\n"
                    # invariant: join_md_sections(fm, sections) == original content
```

`text` always ends with `"\n"`. Reassembly joins sections with no extra delimiter.

#### `split_md_sections(md_content: str) -> tuple[str, list[DocSection]]`
- **Line ending normalisation:** `content = md_content.replace("\r\n", "\n")` at entry. `join_md_sections` will produce LF-only output.
- `frontmatter`: matched via `re.match(r'^---\n([\s\S]*?)\n---\n', content)` — same pattern as `checks.py:check_frontmatter`. Includes delimiters + trailing newline. `""` if absent.
- Splits remaining content via `re.split(r'(?m)^(?=## )', remaining)` (exactly two hashes + space)
- `###` and deeper headings are NOT split points
- Text before first `##` → section with `heading=""`
- Round-trip invariant: `frontmatter + "".join(s.text for s in sections) == content` (LF-normalised)

#### `join_md_sections(frontmatter: str, sections: list[DocSection]) -> str`
```python
def join_md_sections(frontmatter: str, sections: list[DocSection]) -> str:
    return frontmatter + "".join(s.text for s in sections)
```
Tests import from `validator.content.sections` — `__init__.py` need not be modified.

#### `extract_function_names(section_text: str) -> list[str]`
All four patterns run; results collected as `(char_offset, name)` tuples, sorted by offset, then deduplicated:

| Pattern | Regex (approximate) | Example → Captures |
|---------|---------------------|-------------------|
| `### FunctionName` heading | `r'^###\s+`?(\w+)`?'` (multiline) | `### GetOwner` → `GetOwner` |
| Backtick + paren | `` r'`(\w+)\s*\(' `` | `` `GetOwner(` `` → `GetOwner` |
| Code block method call | `r'[\w.]+:(\w+)\s*\('` | `inst:GetOwner(` → `GetOwner` |
| Standalone backtick | `` r'`([A-Z][A-Za-z_]\w*)`' `` | `` `GetOwner` `` → `GetOwner` (capitalized names only, to reduce false positives from type/constant references) |

Returns `list[str]`, unique, ordered by first-match position in text.

#### `extract_lua_context(lua_source: str, fn_names: list[str]) -> str`
```python
def extract_lua_context(lua_source: str, fn_names: list[str]) -> str: ...
```

For each name, match definition via these patterns (Name = literal function name):
```
function\s+\w+:Name\s*\(        ← method on table
function\s+Name\s*\(            ← global/local function
\w+\.Name\s*=\s*function\s*\(   ← table field assignment
\bName\s*=\s*function\s*\(      ← local variable assignment
```

**Extraction algorithm:**

1. Find the definition line.
2. If `end` appears on the **same line** → single-line function; extract that line only, depth scan skipped.
3. Multi-line scan (start depth=1 after definition line):
   - `function`, `if`, `for`, `while`, `do` at line start (or after whitespace) → depth += 1
   - `repeat` → depth += 1 (block closed by `until <condition>`, not `end`)
   - bare `end` (not in comment/string) → depth -= 1; if depth == 0 → emit this line and stop
   - `until` (closes `repeat`) → depth -= 1; emit the `until <condition>` line as the closing boundary (analogous to `end`)

Concatenate all matches separated by `"\n"`.

**Fallback:** `fn_names` empty or no match → `""`.

**Token guard:** `count_tokens(extracted)` from `llm.tokens`:
- Returns `-1` (tiktoken absent) → skip guard, return full string
- Returns > 8,000 → truncate to last complete extracted function block that fits, append `"-- [truncated]\n"`

---

### `chunked.py` — Functions

#### `run_chunked_content_loop`
```python
def run_chunked_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
```
Main entry point. Same signature as `run_content_loop`. LLM errors propagate to caller.

**Why no `connected_content`:** Section-centric review uses focused `lua_ctx` (functions found in the section) instead of the cross-file connected content used in standard review. For large files, connected content is typically already embedded in the markdown as separate sections; including it per-section would re-inflate context. This is intentional.

**Logging pattern:**
```
[content/chunked] 8 sections found
[content/chunked] Section 2/8 "## Functions" — 3 fn(s) found, reviewing... (iter 1/3)
[content/chunked] Section 2/8 — approved at iteration 1
[content/chunked] Section 5/8 "## Events" — 0 fn(s) found, reviewing structure only... (iter 1/3)
[content/chunked] Section 5/8 — patches: 2 applied, 0 failed
[content/chunked] Section 5/8 — approved at iteration 2
[content/chunked] Final: 7/8 approved, 1 section failed (total 13 iterations)
```

#### `review_section`
```python
def review_section(
    section_text: str,
    lua_context: str,
    model: str,
) -> ReviewResult:
```
Builds prompt via `build_section_reviewer_prompt`, calls `ollama_chat`, parses via `parse_review_response` (from `reviewer.py`).

#### `write_section_patches`
```python
def write_section_patches(
    section_text: str,
    lua_context: str,
    review: ReviewResult,
    model: str,
) -> list[Patch]:
```
Builds prompt via `build_section_writer_prompt`, calls `ollama_chat`, parses via `parse_writer_response` (from `writer.py`). `apply_patches` imported from `validator.content.writer` — not redefined.

---

### `prompts.py` — New Functions

#### `build_section_reviewer_prompt(section_text: str, lua_context: str) -> str`
- Scoped to one section; no `connected_content` (see rationale above)
- If `lua_context == ""`: "No Lua context available — review structural accuracy and internal consistency only"
- Same JSON response: `{"approved": bool, "issues": [...], "suggestions": [...]}`

#### `build_section_writer_prompt(section_text: str, lua_context: str, issues: list[str], suggestions: list[str]) -> str`
- Scoped to one section; no `connected_content`
- Instructs: `old_text` must be an exact substring of **this section only** (not full doc) — prevents cross-boundary leakage
- Instructs: avoid overlapping `old_text` values within a single response
- Patches applied to `section.text` via `apply_patches`; if LLM leaks context from another section, the patch silently fails (counted as `failed`)

---

### `pipeline.py` — Integration

```python
# BEFORE (lines 57–64):
if lua_code and count_tokens(lua_code) >= CHUNKED_TOKEN_THRESHOLD:
    print(f"  [pipeline] File is chunked (...), skipping content")
    return FileResult(...)

# AFTER:
if lua_code and count_tokens(lua_code) >= CHUNKED_TOKEN_THRESHOLD:
    print(f"  [pipeline] File is chunked, running per-section validation...")
    content_result = run_chunked_content_loop(md_filepath, lua_filepath, content_config)
    # falls through — format validation also runs for chunked files (intentional)
```

**`skipped_chunked` retirement:** The `"skipped_chunked"` status will no longer be produced for large-Lua files. Update `process_batch` summary to remove the separate `skipped` counter; fold large-file results into `ok` / `content_failed`. Any existing tests asserting `final_status == "skipped_chunked"` must be updated.

**`count_tokens` == -1 note:** If tiktoken is absent, `count_tokens(lua_code)` returns `-1 < 32_000` so large files fall through to standard validation (pre-existing behavior, not addressed here).

---

## Edge Cases

| Case | Handling |
|------|---------|
| `lua_source` is None | `return ContentLoopResult(approved=False, iterations=0, final_issues=["Cannot read Lua source: ..."])` |
| `md_filepath` unreadable | Exception propagates (same policy as LLM errors) |
| `sections` is empty | `return ContentLoopResult(approved=True, iterations=0, final_issues=[])` |
| Section with no function names | `lua_ctx = ""`, reviewer prompt: "structure only" |
| `count_tokens` returns -1 | Skip 8K token guard, return full extracted string |
| `extract_lua_context` > 8K tokens | Truncate to last complete block, append `-- [truncated]` |
| Single-line Lua function | `end` on definition line → extract that line only, skip multi-line scan |
| `repeat`/`until` in Lua blocks | `repeat` → depth+1; `until <cond>` → depth-1 + emit line as closing boundary |
| Some patches fail (partial) | Log `"N patches failed"`, continue iteration loop |
| All patches fail | Same — section only marked failed if final review rejects |
| Writer returns no patches | Break inner loop, section marked failed |
| Max iterations exhausted | Final review called on post-patch text before marking result |
| `config.stop_check()` fires | `return ContentLoopResult(approved=False, iterations=<so far>, final_issues=["Interrupted"])` |
| Interrupted → `content_failed` | Expected — same behavior as standard loop |
| Cross-section patch leakage | Patch silently fails (`failed` count +1), loop continues |
| Markdown has no `##` headings | One section with `heading=""`, near-standard behavior |
| Chunked files now run format validation | Intentional — previously skipped with content |
| LLM exception | Propagates to caller |
| "Failed section" definition | `last_review.approved == False` after final review |

---

## Not in Scope

- Cross-section consistency checks
- Async/parallel section processing
- Caching of `extract_lua_context` results
- Fixing `count_tokens == -1` routing issue (pre-existing)

---

## Testing

- Unit: `split_md_sections` — frontmatter detection, CRLF normalisation, section splitting, empty body, round-trip invariant
- Unit: `extract_function_names` — all 4 patterns, deduplication, offset ordering, false-positive filtering (capitalized-only for standalone backtick)
- Unit: `extract_lua_context` — method/function/table patterns; single-line fn; multi-line with `if`/`for`/`repeat`; no-match fallback; 8K truncation; -1 skip
- Unit: `join_md_sections` — join invariant
- Integration: mock `ollama_chat`, run `run_chunked_content_loop` on fixture doc + Lua; assert patches applied, `ContentLoopResult` correct
- Integration: max_iterations exhausted → final review called, issues reflect post-patch state
- Integration: `config.stop_check()` fires mid-section → `approved=False` returned immediately
- Integration: partial patch failure → section not immediately marked failed
- Integration: overlapping patches → second patch fails silently, loop continues
- Regression: `pipeline.process_file` with chunked fixture → no longer returns `skipped_chunked`
- Regression: `join_md_sections(*split_md_sections(content)) == content.replace("\r\n", "\n")` for fixture files
