# Chunked Content Validation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement full-accuracy content validation for Lua files ≥32K tokens by reviewing the markdown document section-by-section, each section checked against a focused Lua context derived from functions mentioned in that section.

**Architecture:** A new `sections.py` module handles markdown splitting and Lua context extraction. `chunked.py` (currently a stub) is fully implemented with a per-section `[review → fix → review]` loop sharing the same `ContentLoopConfig`/`ContentLoopResult` contract as the standard loop. `pipeline.py` routes large files to this loop instead of skipping them.

**Tech Stack:** Python 3.11, `re`, `dataclasses`, `pathlib`, `unittest.mock` for tests, `uv run pytest` as test runner.

---

## Chunk 1: Markdown Section Splitting

### Task 1: DocSection, split_md_sections, join_md_sections

**Files:**
- Create: `validator/src/validator/content/sections.py`
- Create: `validator/tests/test_sections.py`

- [x] **Step 1: Write failing tests** _(done: 41f7d98)_

```python
# validator/tests/test_sections.py
import pytest
from validator.content.sections import DocSection, split_md_sections, join_md_sections


def test_split_no_frontmatter():
    """Text with no frontmatter and no ## headings → one preamble section."""
    content = "Some intro text.\n"
    fm, sections = split_md_sections(content)
    assert fm == ""
    assert len(sections) == 1
    assert sections[0].heading == ""
    assert sections[0].text == "Some intro text.\n"


def test_split_frontmatter_no_sections():
    """Frontmatter extracted; body with no ## becomes one preamble section."""
    content = "---\ntitle: Foo\n---\nsome body\n"
    fm, sections = split_md_sections(content)
    assert fm == "---\ntitle: Foo\n---\n"
    assert len(sections) == 1
    assert sections[0].heading == ""
    assert sections[0].text == "some body\n"


def test_split_one_section():
    """Single ## section captured with heading as first line."""
    content = "---\ntitle: Foo\n---\n## Functions\nbody text\n"
    fm, sections = split_md_sections(content)
    assert fm == "---\ntitle: Foo\n---\n"
    assert len(sections) == 1
    assert sections[0].heading == "## Functions"
    assert sections[0].text == "## Functions\nbody text\n"


def test_split_multiple_sections_with_preamble():
    """Preamble + two ## sections → three DocSection objects."""
    content = "---\ntitle: T\n---\npreamble\n## A\na text\n## B\nb text\n"
    fm, sections = split_md_sections(content)
    assert fm == "---\ntitle: T\n---\n"
    assert len(sections) == 3
    assert sections[0].heading == "" and sections[0].text == "preamble\n"
    assert sections[1].heading == "## A" and sections[1].text == "## A\na text\n"
    assert sections[2].heading == "## B" and sections[2].text == "## B\nb text\n"


def test_split_ignores_triple_hash():
    """### headings are NOT split points."""
    content = "## Functions\n### GetOwner\nbody\n### SetOwner\nbody2\n"
    _, sections = split_md_sections(content)
    assert len(sections) == 1
    assert "### GetOwner" in sections[0].text
    assert "### SetOwner" in sections[0].text


def test_split_empty_body_after_frontmatter():
    """Empty body after frontmatter → empty sections list."""
    content = "---\ntitle: T\n---\n"
    fm, sections = split_md_sections(content)
    assert fm == "---\ntitle: T\n---\n"
    assert sections == []


def test_split_crlf_normalized():
    """CRLF line endings normalised to LF; no \\r in output."""
    content = "---\r\ntitle: Foo\r\n---\r\n## Sec\r\nbody\r\n"
    fm, sections = split_md_sections(content)
    assert "\r" not in fm
    assert all("\r" not in s.text for s in sections)


def test_split_roundtrip():
    """join_md_sections(*split_md_sections(x)) == x (LF-normalised)."""
    content = "---\ntitle: T\n---\npreamble\n## A\na text\n### Sub\nmore\n## B\nb text\n"
    fm, sections = split_md_sections(content)
    assert join_md_sections(fm, sections) == content


def test_split_crlf_roundtrip():
    """CRLF input round-trips to LF-only output."""
    content = "---\r\ntitle: T\r\n---\r\n## A\r\ntext\r\n"
    fm, sections = split_md_sections(content)
    reassembled = join_md_sections(fm, sections)
    assert reassembled == content.replace("\r\n", "\n")


def test_join_md_sections():
    """join_md_sections concatenates frontmatter + all section texts."""
    sections = [
        DocSection("## A", "## A\ntext\n"),
        DocSection("## B", "## B\nmore\n"),
    ]
    result = join_md_sections("---\ntitle: T\n---\n", sections)
    assert result == "---\ntitle: T\n---\n## A\ntext\n## B\nmore\n"
```

- [x] **Step 2: Run tests to verify they fail** _(done: confirmed ModuleNotFoundError)_

```bash
uv run pytest validator/tests/test_sections.py -v
```

Expected: `ModuleNotFoundError: No module named 'validator.content.sections'`

- [x] **Step 3: Implement sections.py (split/join only)** _(done: 41f7d98)_

```python
# validator/src/validator/content/sections.py
"""Markdown section splitting and Lua context extraction for chunked content validation."""

import re
from dataclasses import dataclass


@dataclass
class DocSection:
    """A ## section from a markdown document (or the preamble before the first ##).

    heading: first line of the section (e.g. "## Functions"), empty for preamble.
    text:    full text including heading line; invariant: join produces original content.
    """
    heading: str
    text: str


def split_md_sections(md_content: str) -> tuple[str, list[DocSection]]:
    """Split markdown into (frontmatter, sections). Normalises CRLF → LF.

    frontmatter: the "---\\n...\\n---\\n" block (empty string if absent).
    sections:    one DocSection per ## heading, plus a preamble section (heading="")
                 if there is content before the first ##. Empty if nothing remains.

    Round-trip invariant: join_md_sections(*split_md_sections(x)) == x.replace("\\r\\n", "\\n")
    """
    content = md_content.replace("\r\n", "\n")

    # Extract YAML frontmatter — same pattern as checks.py:check_frontmatter
    fm_match = re.match(r'^---\n[\s\S]*?\n---\n', content)
    frontmatter = fm_match.group(0) if fm_match else ""
    remaining = content[len(frontmatter):]

    # Split on ## heading boundaries (exactly two hashes + space)
    chunks = re.split(r'(?m)^(?=## )', remaining)

    sections: list[DocSection] = []
    for chunk in chunks:
        if not chunk:
            continue
        first_line = chunk.split("\n", 1)[0]
        heading = first_line if first_line.startswith("## ") else ""
        sections.append(DocSection(heading=heading, text=chunk))

    return frontmatter, sections


def join_md_sections(frontmatter: str, sections: list[DocSection]) -> str:
    """Reassemble document from frontmatter and section list."""
    return frontmatter + "".join(s.text for s in sections)
```

- [x] **Step 4: Run tests to verify they pass** _(done: 10/10 passed)_

```bash
uv run pytest validator/tests/test_sections.py -v
```

Expected: All 10 tests pass.

- [x] **Step 5: Commit** _(done: 41f7d98)_

```bash
git add validator/src/validator/content/sections.py validator/tests/test_sections.py
git commit -m "feat(sections): add DocSection, split_md_sections, join_md_sections"
```

---

## Chunk 2: Function Name and Lua Context Extraction

### Task 2: extract_function_names

**Files:**
- Modify: `validator/src/validator/content/sections.py` (append)
- Modify: `validator/tests/test_sections.py` (append)

- [x] **Step 1: Append failing tests for extract_function_names** _(done: c071031)_

```python
# Append to validator/tests/test_sections.py
from validator.content.sections import extract_function_names


def test_extract_fn_heading_pattern():
    """### FunctionName headings (with optional backtick) are captured."""
    text = "## Functions\n### GetOwner\nReturns owner.\n### `SetOwner`\nSets owner.\n"
    names = extract_function_names(text)
    assert "GetOwner" in names
    assert "SetOwner" in names


def test_extract_fn_backtick_paren():
    """`FuncName(` pattern captured."""
    text = "Call `GetOwner()` to get the owner.\n"
    assert "GetOwner" in extract_function_names(text)


def test_extract_fn_method_call():
    """`inst:Method(` captures Method (not inst)."""
    text = "Use `inst:GetOwner()` or `self:SetOwner()`.\n"
    names = extract_function_names(text)
    assert "GetOwner" in names
    assert "SetOwner" in names


def test_extract_fn_capitalized_standalone_backtick():
    """`CapitalizedName` (no parens, capital first letter) is captured."""
    text = "The `GetOwner` function returns the owner.\n"
    assert "GetOwner" in extract_function_names(text)


def test_extract_fn_lowercase_standalone_not_captured():
    """`lowercase` standalone backtick NOT captured (false-positive filter)."""
    text = "The `owner` variable holds the owner.\n"
    assert "owner" not in extract_function_names(text)


def test_extract_fn_deduplication():
    """Same name via multiple patterns appears only once."""
    text = "`GetOwner()` mentioned again as `GetOwner`.\n"
    names = extract_function_names(text)
    assert names.count("GetOwner") == 1


def test_extract_fn_offset_ordering():
    """Names ordered by first occurrence position in text."""
    text = "`Alpha()` then `Beta()`.\n"
    assert extract_function_names(text) == ["Alpha", "Beta"]


def test_extract_fn_empty_text():
    """Empty section returns empty list."""
    assert extract_function_names("") == []
```

- [x] **Step 2: Run new tests to verify they fail** _(done: confirmed ImportError)_

```bash
uv run pytest validator/tests/test_sections.py -k "extract_fn" -v
```

Expected: `ImportError: cannot import name 'extract_function_names'`

- [x] **Step 3: Append extract_function_names to sections.py** _(done: c071031)_

```python
# Append to validator/src/validator/content/sections.py

_FN_PATTERNS: list[tuple[str, int]] = [
    (r'^###\s+`?(\w+)`?', re.MULTILINE),  # ### FunctionName heading
    (r'`(\w+)\s*\(',      0),             # `FuncName(
    (r'[\w.]+:(\w+)\s*\(', 0),           # inst:Method(
    (r'`([A-Z][A-Za-z_]\w*)`', 0),       # `CapitalizedName` (no parens)
]


def extract_function_names(section_text: str) -> list[str]:
    """Extract Lua function names mentioned in a markdown section.

    Runs four regex patterns; results deduplicated and ordered by first occurrence.
    """
    matches: list[tuple[int, str]] = []
    for pattern, flags in _FN_PATTERNS:
        for m in re.finditer(pattern, section_text, flags):
            matches.append((m.start(), m.group(1)))

    matches.sort(key=lambda x: x[0])
    seen: set[str] = set()
    result: list[str] = []
    for _, name in matches:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result
```

- [x] **Step 4: Run all sections tests** _(done: 18/18 passed)_

```bash
uv run pytest validator/tests/test_sections.py -v
```

Expected: All tests pass.

- [x] **Step 5: Commit** _(done: c071031)_

```bash
git add validator/src/validator/content/sections.py validator/tests/test_sections.py
git commit -m "feat(sections): add extract_function_names with 4 patterns and offset-ordered dedup"
```

---

### Task 3: extract_lua_context

**Files:**
- Modify: `validator/src/validator/content/sections.py` (append)
- Modify: `validator/tests/test_sections.py` (append)

- [x] **Step 1: Append failing tests for extract_lua_context** _(done: 2e3fde9)_

```python
# Append to validator/tests/test_sections.py
from unittest.mock import patch
from validator.content.sections import extract_lua_context


def test_extract_lua_empty_names():
    """No function names → empty string immediately."""
    assert extract_lua_context("function Foo() end\n", []) == ""


def test_extract_lua_no_match():
    """Name not in Lua source → empty string."""
    assert extract_lua_context("function Foo() end\n", ["Bar"]) == ""


def test_extract_lua_single_line_fn():
    """Function with 'end' on the definition line → only that line extracted."""
    lua = "function GetOwner() return self.owner end\n"
    result = extract_lua_context(lua, ["GetOwner"])
    assert "function GetOwner()" in result
    assert result.count("end") == 1
    assert "\n" not in result.strip()  # single line


def test_extract_lua_multi_line_fn():
    """Multi-line function body with closing end is fully extracted."""
    lua = "function GetOwner()\n    return self.owner\nend\n"
    result = extract_lua_context(lua, ["GetOwner"])
    assert "function GetOwner()" in result
    assert "return self.owner" in result
    assert result.count("end") == 1


def test_extract_lua_method_pattern():
    """Entity:Method() definition is matched."""
    lua = "function Entity:GetOwner()\n    return self.owner\nend\n"
    result = extract_lua_context(lua, ["GetOwner"])
    assert "Entity:GetOwner" in result


def test_extract_lua_table_field():
    """Table.Name = function() definition is matched."""
    lua = "Entity.GetOwner = function(self)\n    return self.owner\nend\n"
    result = extract_lua_context(lua, ["GetOwner"])
    assert "Entity.GetOwner = function" in result


def test_extract_lua_local_var_assignment():
    """Local variable assignment (Name = function()) definition is matched."""
    lua = "local GetOwner = function(self)\n    return self.owner\nend\n"
    result = extract_lua_context(lua, ["GetOwner"])
    assert "GetOwner = function" in result


def test_extract_lua_nested_if_depth():
    """Nested if/end increases depth; only the outer end closes extraction."""
    lua = (
        "function Foo()\n"
        "    if true then\n"
        "        return 1\n"
        "    end\n"
        "end\n"
    )
    result = extract_lua_context(lua, ["Foo"])
    assert "if true then" in result
    assert result.count("end") == 2  # inner if-end + outer fn-end


def test_extract_lua_repeat_until():
    """repeat/until block depth tracked; until line emitted as closing boundary."""
    lua = (
        "function Foo()\n"
        "    repeat\n"
        "        x = x + 1\n"
        "    until x > 10\n"
        "end\n"
    )
    result = extract_lua_context(lua, ["Foo"])
    assert "repeat" in result
    assert "until x > 10" in result
    assert "end" in result


def test_extract_lua_token_guard_minus1():
    """-1 from count_tokens → skip guard; full string returned even if large."""
    big_lua = "function GetOwner()\n" + "    -- comment\n" * 500 + "end\n"
    with patch("validator.content.sections.count_tokens", return_value=-1):
        result = extract_lua_context(big_lua, ["GetOwner"])
    assert "-- [truncated]" not in result
    assert "function GetOwner()" in result


def test_extract_lua_token_guard_truncates():
    """Result > 8000 tokens → truncated to last complete block; marker appended."""
    lua = (
        "function Alpha()\n    -- alpha\nend\n"
        "function Beta()\n    -- beta\nend\n"
    )

    def mock_count(text: str) -> int:
        # Alpha alone fits; Alpha+Beta would exceed 8K
        return 9_000 if "Beta" in text else 4_000

    with patch("validator.content.sections.count_tokens", side_effect=mock_count):
        result = extract_lua_context(lua, ["Alpha", "Beta"])
    assert "Alpha" in result
    assert "-- [truncated]" in result
```

- [x] **Step 2: Run new tests to verify they fail** _(done: confirmed ImportError)_

```bash
uv run pytest validator/tests/test_sections.py -k "extract_lua" -v
```

Expected: `ImportError: cannot import name 'extract_lua_context'`

- [x] **Step 3: Append extract_lua_context to sections.py** _(done: 2e3fde9)_

Add this import at the **top** of `sections.py` (alongside existing imports):
```python
from llm.tokens import count_tokens
```

Then append these functions:

```python
# Append to validator/src/validator/content/sections.py

# Lua keyword regexes for depth tracking
_LUA_DEPTH_UP = re.compile(
    r'^\s*(function|if|for|while|do)\b|^\s*local\s+function\b'
)
_LUA_REPEAT = re.compile(r'^\s*repeat\b')
_LUA_UNTIL  = re.compile(r'^\s*until\b')
_LUA_END    = re.compile(r'^\s*end\b')


def _def_patterns(name: str) -> list[re.Pattern[str]]:
    """Return compiled patterns that match a Lua definition of `name`."""
    n = re.escape(name)
    return [re.compile(p) for p in [
        rf'function\s+\w+:{n}\s*\(',       # Entity:Name(
        rf'function\s+{n}\s*\(',            # function Name(
        rf'\w+\.{n}\s*=\s*function\s*\(',  # Tbl.Name = function(
        rf'\b{n}\s*=\s*function\s*\(',     # Name = function(
    ]]


def _extract_block(lines: list[str], def_idx: int) -> str:
    """Extract the full Lua function block starting at def_idx."""
    def_line = lines[def_idx]

    # Single-line function: 'end' on the same line as the definition
    if _LUA_END.search(def_line):
        return def_line.rstrip("\n")

    # Multi-line: depth scan (depth starts at 1 for the definition line)
    block: list[str] = [def_line.rstrip("\n")]
    depth = 1
    for line in lines[def_idx + 1:]:
        if _LUA_UNTIL.match(line):
            depth -= 1
            block.append(line.rstrip("\n"))
            if depth == 0:
                break
        elif _LUA_END.match(line):
            depth -= 1
            block.append(line.rstrip("\n"))
            if depth == 0:
                break
        else:
            if _LUA_DEPTH_UP.match(line) or _LUA_REPEAT.match(line):
                depth += 1
            block.append(line.rstrip("\n"))

    return "\n".join(block)


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


def extract_lua_context(lua_source: str, fn_names: list[str]) -> str:
    """Extract Lua function bodies for the given names from lua_source.

    Returns a single string (blocks joined by "\\n"), or "" if no names / no matches.
    Truncates to 8K tokens if count_tokens is available (returns -1 → skip guard).
    """
    if not fn_names:
        return ""

    lines = lua_source.splitlines(keepends=True)
    blocks: list[str] = []

    for name in fn_names:
        patterns = _def_patterns(name)
        def_idx: int | None = None
        for i, line in enumerate(lines):
            if any(p.search(line) for p in patterns):
                def_idx = i
                break
        if def_idx is None:
            continue
        blocks.append(_extract_block(lines, def_idx))

    if not blocks:
        return ""

    result = "\n".join(blocks)

    # Token guard
    token_count = count_tokens(result)
    if token_count != -1 and token_count > 8_000:
        result = _truncate_blocks_to_8k(blocks)

    return result
```

- [x] **Step 4: Run all sections tests** _(done: 29/29 passed)_

```bash
uv run pytest validator/tests/test_sections.py -v
```

Expected: All tests pass.

- [x] **Step 5: Run full validator suite to catch any regressions** _(done: no regressions)_

```bash
uv run pytest validator/tests/ -v
```

Expected: All existing tests still pass.

- [x] **Step 6: Commit** _(done: 2e3fde9)_

```bash
git add validator/src/validator/content/sections.py validator/tests/test_sections.py
git commit -m "feat(sections): add extract_lua_context with depth scan and 8K token guard"
```

---

## Chunk 3: Section-Level Prompts and chunked.py

### Task 4: build_section_reviewer_prompt and build_section_writer_prompt

**Files:**
- Modify: `validator/src/validator/content/prompts.py` (append two functions)

- [x] **Step 1: Append section-level prompt functions to prompts.py** _(done: 37d6290)_

```python
# Append to validator/src/validator/content/prompts.py

def build_section_reviewer_prompt(section_text: str, lua_context: str) -> str:
    """Prompt for reviewing one markdown section against its focused Lua context."""
    if lua_context:
        lua_block = f"```lua\n{lua_context}\n```"
        lua_instruction = "Review the section against the Lua functions below."
    else:
        lua_block = "(none — no Lua functions referenced in this section)"
        lua_instruction = (
            "No Lua context available — review structural accuracy "
            "and internal consistency only."
        )

    return f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.

{lua_instruction}

## Lua Context (functions referenced in this section)
{lua_block}

## Section to Review
{section_text}

## Response Format
Respond in JSON only:
```json
{{
    "approved": true/false,
    "issues": ["list of specific problems found"],
    "suggestions": ["list of specific fix suggestions"]
}}
```

If the section is accurate and complete, set approved=true with empty lists.
If there are problems, set approved=false and list each issue with a specific suggestion."""


def build_section_writer_prompt(
    section_text: str,
    lua_context: str,
    issues: list[str],
    suggestions: list[str],
) -> str:
    """Prompt for patching one markdown section based on review feedback."""
    feedback = ""
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback += f"{i}. Issue: {issue}\n"
        if suggestion:
            feedback += f"   Suggestion: {suggestion}\n"

    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"

    return f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.

Fix the following documentation section based on reviewer feedback.

## Lua Context (ground truth for this section)
{lua_block}

## Current Section
{section_text}

## Reviewer Feedback
{feedback}

## Response Format
Return a JSON array of patches:
```json
[
    {{
        "old_text": "exact text to find in this section only",
        "new_text": "replacement text",
        "reason": "why this change is needed"
    }}
]
```

Rules:
- old_text must be an EXACT substring of the section shown above (not the full document)
- Do not use overlapping old_text values within a single response
- Keep patches minimal — only change what is needed to fix the issues
- Do NOT modify YAML frontmatter"""
```

- [x] **Step 2: Verify existing tests still pass (prompts are tested via integration)** _(done: 37d6290)_

```bash
uv run pytest validator/tests/ -v
```

Expected: All pass. No new prompt unit tests needed — prompt correctness is verified in Task 5 integration tests.

- [x] **Step 3: Commit** _(done: 37d6290)_

```bash
git add validator/src/validator/content/prompts.py
git commit -m "feat(prompts): add build_section_reviewer_prompt and build_section_writer_prompt"
```

---

### Task 5: Implement chunked.py

**Files:**
- Modify: `validator/src/validator/content/chunked.py` (replace stub)
- Create: `validator/tests/test_content_chunked.py`

- [x] **Step 1: Write failing integration tests** _(done: 5d8bfdf)_

```python
# validator/tests/test_content_chunked.py
"""Integration tests for run_chunked_content_loop. Mocks ollama_chat only."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from validator.content.chunked import run_chunked_content_loop
from validator.content.loop import ContentLoopConfig


# ── response helpers ─────────────────────────────────────────────────────────

def _approved():
    body = json.dumps({"approved": True, "issues": [], "suggestions": []})
    return {"message": {"content": body}}


def _rejected(issues: list[str]):
    body = json.dumps({"approved": False, "issues": issues, "suggestions": []})
    return {"message": {"content": body}}


def _patches(old_text: str, new_text: str):
    body = json.dumps([{"old_text": old_text, "new_text": new_text, "reason": "fix"}])
    return {"message": {"content": body}}


def _no_patches():
    return {"message": {"content": "[]"}}


# ── fixtures ─────────────────────────────────────────────────────────────────

SIMPLE_MD = "---\ntitle: Test\n---\n## Functions\n`GetOwner()` returns owner.\n"
SIMPLE_LUA = "function GetOwner() return self.owner end\n"


def _write_fixtures(tmp_path, md_content=SIMPLE_MD, lua_content=SIMPLE_LUA):
    md = tmp_path / "test.md"
    lua = tmp_path / "test.lua"
    md.write_text(md_content, encoding="utf-8")
    lua.write_text(lua_content, encoding="utf-8")
    return str(md), str(lua)


def _config(**kwargs):
    return ContentLoopConfig(max_iterations=3, writer_model="m", reviewer_model="m", **kwargs)


# ── tests ────────────────────────────────────────────────────────────────────

def test_all_sections_approved(tmp_path):
    """Reviewer approves every section → result.approved True."""
    md, lua = _write_fixtures(tmp_path)
    with patch("validator.content.chunked.ollama_chat", return_value=_approved()):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True
    assert result.final_issues == []
    assert result.iterations >= 1


def test_section_fails_no_patches(tmp_path):
    """Reviewer rejects + writer returns no patches → section marked failed."""
    md, lua = _write_fixtures(tmp_path)
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[_rejected(["Wrong return type"]), _no_patches()],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is False
    assert "Wrong return type" in result.final_issues


def test_patches_applied_and_written_to_disk(tmp_path):
    """Writer patches are applied to the section and persisted to disk."""
    md, lua = _write_fixtures(tmp_path)
    old = "`GetOwner()` returns owner."
    new = "`GetOwner()` returns the owner entity."
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[_rejected(["Wrong text"]), _patches(old, new), _approved()],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True
    written = Path(md).read_text(encoding="utf-8")
    assert new in written


def test_stop_check_fires_before_first_review(tmp_path):
    """stop_check() True on entry → approved=False, no LLM calls."""
    md, lua = _write_fixtures(tmp_path)
    with patch("validator.content.chunked.ollama_chat") as mock_chat:
        result = run_chunked_content_loop(md, lua, _config(stop_check=lambda: True))
    assert result.approved is False
    assert result.final_issues == ["Interrupted by user"]
    mock_chat.assert_not_called()


def test_max_iterations_triggers_final_review(tmp_path):
    """max_iterations exhausted → extra final review called; issues from final review used."""
    md, lua = _write_fixtures(tmp_path)
    # max_iterations=1: review→rejected, writer returns patch, loop exhausts → final review
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected(["Initial issue"]),
            _patches("`GetOwner()` returns owner.", "`GetOwner()` returns owner entity."),
            _rejected(["Post-patch issue"]),
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config(max_iterations=1))
    assert result.approved is False
    assert "Post-patch issue" in result.final_issues
    assert "Initial issue" not in result.final_issues


def test_lua_unreadable_returns_failed(tmp_path):
    """Missing Lua file → approved=False with descriptive message."""
    md = tmp_path / "test.md"
    md.write_text(SIMPLE_MD, encoding="utf-8")
    result = run_chunked_content_loop(
        str(md), str(tmp_path / "missing.lua"), _config()
    )
    assert result.approved is False
    assert any("Cannot read Lua source" in issue for issue in result.final_issues)


def test_empty_sections_approved(tmp_path):
    """Markdown with no content after frontmatter is trivially approved."""
    md, lua = _write_fixtures(tmp_path, md_content="---\ntitle: T\n---\n")
    result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True
    assert result.iterations == 0
    assert result.final_issues == []


def test_multiple_sections_partial_failure(tmp_path):
    """Two sections: first approved, second failed → overall approved=False."""
    md_content = (
        "---\ntitle: T\n---\n"
        "## SectionA\n`Alpha()` docs.\n"
        "## SectionB\n`Beta()` docs.\n"
    )
    lua_content = (
        "function Alpha() return 1 end\n"
        "function Beta() return 2 end\n"
    )
    md, lua = _write_fixtures(tmp_path, md_content, lua_content)
    # SectionA: approved. SectionB: rejected, no patches → failed.
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[_approved(), _rejected(["Beta wrong"]), _no_patches()],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is False
    assert "Beta wrong" in result.final_issues
```

- [x] **Step 2: Run tests to verify they fail** _(done: 5d8bfdf)_

```bash
uv run pytest validator/tests/test_content_chunked.py -v
```

Expected: `ImportError: cannot import name 'run_chunked_content_loop'` (stub has no exports)

- [x] **Step 3: Implement chunked.py** _(done: 5d8bfdf)_

```python
# validator/src/validator/content/chunked.py
"""Section-by-section content validation for large Lua files (≥32K tokens)."""

from pathlib import Path

from llm.client import ollama_chat
from llm.tokens import count_tokens
from rag.docs import safe_read_lua
from validator.content.loop import ContentLoopConfig, ContentLoopResult
from validator.content.prompts import (
    build_section_reviewer_prompt,
    build_section_writer_prompt,
)
from validator.content.reviewer import ReviewResult, parse_review_response
from validator.content.sections import (
    DocSection,
    extract_function_names,
    extract_lua_context,
    join_md_sections,
    split_md_sections,
)
from validator.content.writer import Patch, apply_patches, parse_writer_response


def review_section(section_text: str, lua_context: str, model: str) -> ReviewResult:
    """Send one markdown section to the reviewer LLM."""
    prompt = build_section_reviewer_prompt(section_text, lua_context)
    print(f"  [content/chunked] Reviewer prompt: {count_tokens(prompt):,} tokens")
    response = ollama_chat(model=model, messages=[{"role": "user", "content": prompt}])
    return parse_review_response(response["message"]["content"])


def write_section_patches(
    section_text: str,
    lua_context: str,
    review: ReviewResult,
    model: str,
) -> list[Patch]:
    """Ask the writer LLM to patch one section based on review feedback."""
    prompt = build_section_writer_prompt(
        section_text, lua_context, review.issues, review.suggestions
    )
    print(f"  [content/chunked] Writer prompt: {count_tokens(prompt):,} tokens")
    response = ollama_chat(model=model, messages=[{"role": "user", "content": prompt}])
    patches = parse_writer_response(response["message"]["content"])
    if not patches:
        print("  [content/chunked] Writer returned no patches")
    else:
        print(f"  [content/chunked] {len(patches)} patch(es) generated")
    return patches


def run_chunked_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
    """Full content validation for large-Lua files, processed section-by-section.

    Same signature and return contract as run_content_loop.
    approved=True means every section passed its final review.
    """
    md_content = Path(md_filepath).read_text(encoding="utf-8")
    lua_source = safe_read_lua(lua_filepath)
    if lua_source is None:
        return ContentLoopResult(
            approved=False,
            iterations=0,
            final_issues=[f"Cannot read Lua source: {lua_filepath}"],
        )

    frontmatter, sections = split_md_sections(md_content)
    if not sections:
        return ContentLoopResult(approved=True, iterations=0, final_issues=[])

    print(f"  [content/chunked] {len(sections)} section(s) found")
    total_iterations = 0
    all_failed_issues: list[str] = []

    for idx, section in enumerate(sections, 1):
        fn_names = extract_function_names(section.text)
        lua_ctx = extract_lua_context(lua_source, fn_names)
        fn_desc = f"{len(fn_names)} fn(s)" if fn_names else "0 fn(s) — structure only"
        print(
            f"  [content/chunked] Section {idx}/{len(sections)} "
            f"{section.heading!r} — {fn_desc} found"
        )

        section_approved = False
        last_review: ReviewResult | None = None

        for i in range(config.max_iterations):
            if config.stop_check():
                return ContentLoopResult(
                    approved=False,
                    iterations=total_iterations,
                    final_issues=["Interrupted by user"],
                )

            total_iterations += 1
            print(
                f"  [content/chunked] Section {idx}/{len(sections)} — "
                f"reviewing... (iter {i + 1}/{config.max_iterations})"
            )
            last_review = review_section(section.text, lua_ctx, config.reviewer_model)

            if last_review.approved:
                section_approved = True
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    f"approved at iteration {i + 1}"
                )
                break

            patches = write_section_patches(
                section.text, lua_ctx, last_review, config.writer_model
            )
            if not patches:
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    "writer gave up, section stays failed"
                )
                break

            section.text, failed = apply_patches(section.text, patches)
            applied = len(patches) - failed
            print(
                f"  [content/chunked] Section {idx}/{len(sections)} — "
                f"patches: {applied} applied, {failed} failed"
            )
            Path(md_filepath).write_text(
                join_md_sections(frontmatter, sections), encoding="utf-8"
            )

        else:
            # max_iterations exhausted — final review on post-patch text
            # mirrors loop.py lines 110–120 so final_issues reflect current state
            print(
                f"  [content/chunked] Section {idx}/{len(sections)} — "
                "max iterations reached, running final review"
            )
            total_iterations += 1
            last_review = review_section(section.text, lua_ctx, config.reviewer_model)
            section_approved = last_review.approved

        if not section_approved and last_review is not None:
            all_failed_issues.extend(last_review.issues)

    print(
        f"  [content/chunked] Final: "
        f"{'all approved' if not all_failed_issues else f'{len(all_failed_issues)} issue(s) across failed sections'}, "
        f"total {total_iterations} iterations"
    )
    return ContentLoopResult(
        approved=len(all_failed_issues) == 0,
        iterations=total_iterations,
        final_issues=all_failed_issues,
    )
```

- [x] **Step 4: Run chunked tests** _(done: 5d8bfdf)_

```bash
uv run pytest validator/tests/test_content_chunked.py -v
```

Expected: All 8 tests pass.

- [x] **Step 5: Run full validator suite** _(done: 5d8bfdf)_

```bash
uv run pytest validator/tests/ -v
```

Expected: All tests pass.

- [x] **Step 6: Commit** _(done: 5d8bfdf)_

```bash
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(chunked): implement run_chunked_content_loop with per-section review loop"
```

---

## Chunk 4: Pipeline Integration

### Task 6: Route chunked files to per-section loop; retire skipped_chunked

**Files:**
- Modify: `validator/src/validator/pipeline.py`
- Modify: `validator/tests/test_pipeline.py`

- [x] **Step 1: Update test_pipeline.py — add regression test, remove skipped_chunked from valid statuses** _(done: ff2f24a)_

In `validator/tests/test_pipeline.py`:

**Replace** `test_file_result_statuses` (removes `"skipped_chunked"` from valid set):
```python
def test_file_result_statuses():
    for status in ["ok", "content_failed", "format_failed"]:
        result = FileResult(
            filepath="test.md",
            content_result=None,
            format_result=None,
            final_status=status,
        )
        assert result.final_status == status
```

**Append** a new regression test:
```python
from unittest.mock import patch
from validator.content.loop import ContentLoopResult
from validator.pipeline import process_file, CHUNKED_TOKEN_THRESHOLD


def test_chunked_file_runs_content_validation(tmp_path):
    """Files with large Lua source now run run_chunked_content_loop, not skip."""
    md = tmp_path / "test.md"
    md.write_text("---\ntitle: T\n---\n## Sec\ncontent\n", encoding="utf-8")

    approved = ContentLoopResult(approved=True, iterations=1, final_issues=[])
    config = PipelineConfig(skip_format=True)

    with (
        patch("validator.pipeline.resolve_lua_path", return_value=str(tmp_path / "test.lua")),
        patch("validator.pipeline.safe_read_lua", return_value="-- large lua\n"),
        patch("validator.pipeline.count_tokens", return_value=CHUNKED_TOKEN_THRESHOLD),
        patch("validator.pipeline.run_chunked_content_loop", return_value=approved) as mock_chunked,
    ):
        result = process_file(str(md), config)

    mock_chunked.assert_called_once()
    assert result.final_status == "ok"
    assert result.final_status != "skipped_chunked"
```

- [x] **Step 2: Run tests to verify the new test fails** _(done: confirmed ImportError on run_chunked_content_loop)_

```bash
uv run pytest validator/tests/test_pipeline.py -v
```

Expected: `test_chunked_file_runs_content_validation` fails — pipeline still skips.

- [x] **Step 3: Update pipeline.py** _(done: ff2f24a)_

**Add import** after the existing `run_content_loop` import line:
```python
from validator.content.chunked import run_chunked_content_loop
```

**Refactor the content block** inside `process_file` (replace lines ~54–72):

```python
        else:
            content_config = ContentLoopConfig(
                max_iterations=config.content_max_iterations,
                writer_model=config.writer_model,
                reviewer_model=config.reviewer_model,
                stop_check=config.stop_check,
            )
            lua_code = safe_read_lua(lua_filepath)
            if lua_code and count_tokens(lua_code) >= CHUNKED_TOKEN_THRESHOLD:
                print(
                    f"  [pipeline] File is chunked (>={CHUNKED_TOKEN_THRESHOLD} tokens), "
                    "running per-section validation..."
                )
                content_result = run_chunked_content_loop(
                    md_filepath, lua_filepath, content_config
                )
                # falls through — format validation also runs for chunked files
            else:
                content_result = run_content_loop(md_filepath, lua_filepath, content_config)

            if content_result and not content_result.approved:
                print(
                    f"  [pipeline] Content not approved after {content_result.iterations} iterations"
                )
```

**Update `FileResult` docstring** — remove `"skipped_chunked"`:
```python
    final_status: str   # "ok", "content_failed", "format_failed"
```

**Update `process_batch` summary** — remove the `skipped` counter:
```python
    ok     = sum(1 for r in results if r.final_status == "ok")
    failed = sum(1 for r in results if "failed" in r.final_status)

    print(f"\n{'='*40}")
    print(f"  OK: {ok} | Failed: {failed}")
    print(f"{'='*40}")
```

- [x] **Step 4: Run all tests** _(done: 124/124 passed)_

```bash
uv run pytest validator/tests/ -v
```

Expected: All tests pass including `test_chunked_file_runs_content_validation`.

- [x] **Step 5: Commit** _(done: ff2f24a)_

```bash
git add validator/src/validator/pipeline.py validator/tests/test_pipeline.py
git commit -m "feat(pipeline): route chunked files to per-section validation, retire skipped_chunked"
```

---

## Final Verification

- [x] **Run the complete test suite one last time** _(done: 124/124 passed)_

```bash
uv run pytest validator/tests/ -v --tb=short
```

Expected: All tests green, no warnings about missing modules.

- [x] **Smoke check — ensure the module graph is importable** _(done: OK)_

```bash
uv run python -c "from validator.content.chunked import run_chunked_content_loop; print('OK')"
```

Expected: `OK`
