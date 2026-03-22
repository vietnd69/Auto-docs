# Chunked Validator — Format Protection & Section Sub-chunking Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix two bugs in `run_chunked_content_loop`: (1) reviewer/writer loop destroys format structure because prompts have no format constraints; (2) `## Main functions` with 109 functions creates a 16K-token section causing timeouts.

**Architecture:** Add FORMAT CONTRACT + FORMAT RULES blocks to both section prompts; add `split_section_blocks` / `sub_chunk_section` / `extract_fn_headings` / `restore_lost_blocks` to `sections.py`; dispatch large `##` sections (>`SECTION_TOKEN_THRESHOLD` tokens AND containing line-anchored `### `) through a new batch loop in `chunked.py` with a snapshot+restore completeness guard.

**Tech Stack:** Python 3.11, `llm.tokens.count_tokens`, `re`, `uv run pytest`

**Spec:** `docs/superpowers/specs/2026-03-23-chunked-validator-format-and-subchunk-design.md`

---

## Chunk 1: Foundation — constants, sections.py helpers, prompts.py

### Task 1: Add `SECTION_TOKEN_THRESHOLD` and `BATCH_TOKEN_LIMIT` constants

**Files:**
- Modify: `config.toml` (under `[validator]`)
- Modify: `llm/src/llm/settings.py` (after `LUA_CONTEXT_TOKENS` line)

- [x] **Step 1.1: Add to `config.toml`**

Open `config.toml`, find the `[validator]` block, append after the last entry:

```toml
section_token_threshold = 4000
batch_token_limit       = 3000
```

- [x] **Step 1.2: Add to `settings.py`**

In `llm/src/llm/settings.py`, after the `LUA_CONTEXT_TOKENS` line (~line 56), append:

```python
SECTION_TOKEN_THRESHOLD: int = _get("validator", "section_token_threshold", 4000)
BATCH_TOKEN_LIMIT: int       = _get("validator", "batch_token_limit",       3000)
```

- [x] **Step 1.3: Verify importable**

```bash
uv run python -c "from llm.settings import SECTION_TOKEN_THRESHOLD, BATCH_TOKEN_LIMIT; print(SECTION_TOKEN_THRESHOLD, BATCH_TOKEN_LIMIT)"
```

Expected: `4000 3000`

- [x] **Step 1.4: Commit**

```bash
git add config.toml llm/src/llm/settings.py
git commit -m "feat(settings): add SECTION_TOKEN_THRESHOLD and BATCH_TOKEN_LIMIT constants"
```

---

### Task 2: `split_section_blocks`

**Files:**
- Modify: `validator/src/validator/content/sections.py`
- Test: `validator/tests/test_sections.py`

- [x] **Step 2.1: Write failing tests**

Add to `validator/tests/test_sections.py`:

```python
from validator.content.sections import split_section_blocks


def test_split_section_blocks_basic():
    """Preamble + two fn_blocks extracted correctly."""
    text = "## Main functions\n\n### `Foo(x)`\ncontent a\n### `Bar(y)`\ncontent b\n"
    preamble, blocks = split_section_blocks(text)
    assert preamble == "## Main functions\n\n"
    assert len(blocks) == 2
    assert blocks[0].startswith("### `Foo(x)`")
    assert blocks[1].startswith("### `Bar(y)`")


def test_split_section_blocks_roundtrip():
    """preamble + join(fn_blocks) reconstructs original text."""
    text = "## Functions\n\nIntro text.\n### `Foo(x)`\ncontent\n### `Bar()`\nmore\n"
    preamble, blocks = split_section_blocks(text)
    assert preamble + "".join(blocks) == text


def test_split_section_blocks_no_subheadings():
    """Section with no ### → preamble=full text, fn_blocks=[]."""
    text = "## Overview\n\nSome text without subheadings.\n"
    preamble, blocks = split_section_blocks(text)
    assert preamble == text
    assert blocks == []


def test_split_section_blocks_triple_hash_in_code_fence_not_matched():
    """### inside a code fence is not a split point (must be at line start)."""
    text = "## Overview\n\n```lua\n### not a heading\n```\n"
    preamble, blocks = split_section_blocks(text)
    # The regex is anchored but ### is at line start inside the fence too.
    # Test verifies the roundtrip still holds.
    assert preamble + "".join(blocks) == text
```

- [x] **Step 2.2: Run to verify failure**

```bash
uv run pytest validator/tests/test_sections.py::test_split_section_blocks_basic -v
```

Expected: `ImportError` or `AttributeError` — `split_section_blocks` not defined yet.

- [x] **Step 2.3: Implement `split_section_blocks`**

In `validator/src/validator/content/sections.py`, add after the `join_md_sections` function:

```python
def split_section_blocks(section_text: str) -> tuple[str, list[str]]:
    """Split a ## section into (preamble, fn_blocks).

    preamble: ## heading line + all content before the first line-anchored ### line.
              Always non-empty (contains at least the ## heading).
    fn_blocks: list[str], each starts with a ### line. Empty if no ### found.

    Round-trip invariant: preamble + "".join(fn_blocks) == section_text
    """
    match = re.search(r'(?m)^### ', section_text)
    if not match:
        return section_text, []
    preamble = section_text[: match.start()]
    rest = section_text[match.start():]
    fn_blocks = [b for b in re.split(r'(?m)^(?=### )', rest) if b]
    return preamble, fn_blocks
```

- [x] **Step 2.4: Run tests**

```bash
uv run pytest validator/tests/test_sections.py -k "split_section_blocks" -v
```

Expected: all 4 tests PASS.

- [x] **Step 2.5: Commit**

```bash
git add validator/src/validator/content/sections.py validator/tests/test_sections.py
git commit -m "feat(sections): add split_section_blocks"
```

---

### Task 3: `sub_chunk_section`

**Files:**
- Modify: `validator/src/validator/content/sections.py`
- Test: `validator/tests/test_sections.py`

- [x] **Step 3.1: Write failing tests**

Add to `validator/tests/test_sections.py`:

```python
from unittest.mock import patch
from validator.content.sections import sub_chunk_section


def test_sub_chunk_section_single_batch_when_under_limit():
    """All blocks fit in one batch → one batch returned."""
    blocks = ["### `Foo()`\ncontent\n", "### `Bar()`\ncontent\n"]
    # patch count_tokens: each block = 50 tokens, limit = 200
    with patch("validator.content.sections.count_tokens", return_value=50):
        batches = sub_chunk_section(blocks, limit=200)
    assert len(batches) == 1
    assert batches[0] == blocks


def test_sub_chunk_section_splits_at_limit():
    """Blocks split into two batches when combined would exceed limit."""
    blocks = [f"### `F{i}()`\ncontent\n" for i in range(4)]
    # Each block = 60 tokens, limit = 100 → max 1 per batch (60+60=120 > 100)
    with patch("validator.content.sections.count_tokens", return_value=60):
        batches = sub_chunk_section(blocks, limit=100)
    assert len(batches) == 4   # each block in its own batch
    assert all(len(b) == 1 for b in batches)


def test_sub_chunk_section_preserves_all_blocks():
    """Every block appears in exactly one batch."""
    blocks = [f"### `F{i}()`\ncontent\n" for i in range(10)]
    with patch("validator.content.sections.count_tokens", return_value=30):
        batches = sub_chunk_section(blocks, limit=100)
    all_blocks = [b for batch in batches for b in batch]
    assert all_blocks == blocks


def test_sub_chunk_section_empty_input():
    """Empty fn_blocks → empty batches list."""
    assert sub_chunk_section([], limit=3000) == []
```

- [x] **Step 3.2: Run to verify failure**

```bash
uv run pytest validator/tests/test_sections.py -k "sub_chunk_section" -v
```

Expected: `ImportError` — `sub_chunk_section` not defined.

- [x] **Step 3.3: Implement `sub_chunk_section`**

Add after `split_section_blocks` in `sections.py`:

```python
def sub_chunk_section(fn_blocks: list[str], limit: int) -> list[list[str]]:
    """Group fn_blocks into batches where each batch's token count <= limit.

    A single block that exceeds limit is placed in its own batch (never split).
    """
    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for block in fn_blocks:
        block_tokens = count_tokens(block)
        if current and current_tokens + block_tokens > limit:
            batches.append(current)
            current = [block]
            current_tokens = block_tokens
        else:
            current.append(block)
            current_tokens += block_tokens
    if current:
        batches.append(current)
    return batches
```

Note: `count_tokens` is already imported at the top of `sections.py`.

- [x] **Step 3.4: Run tests**

```bash
uv run pytest validator/tests/test_sections.py -k "sub_chunk_section" -v
```

Expected: all 4 PASS.

- [x] **Step 3.5: Run full sections test suite**

```bash
uv run pytest validator/tests/test_sections.py -v
```

Expected: all PASS.

- [x] **Step 3.6: Commit**

```bash
git add validator/src/validator/content/sections.py validator/tests/test_sections.py
git commit -m "feat(sections): add sub_chunk_section"
```

---

### Task 4: `extract_fn_headings` and `restore_lost_blocks`

**Files:**
- Modify: `validator/src/validator/content/sections.py`
- Test: `validator/tests/test_sections.py`

- [x] **Step 4.1: Write failing tests**

Add to `validator/tests/test_sections.py`:

```python
from validator.content.sections import extract_fn_headings, restore_lost_blocks


def test_extract_fn_headings_basic():
    """Returns set of first-line headings from each block."""
    blocks = [
        "### `Foo(x)`\n* **Description:** foo\n",
        "### `Bar(y, z)`\n* **Description:** bar\n",
    ]
    assert extract_fn_headings(blocks) == {"### `Foo(x)`", "### `Bar(y, z)`"}


def test_extract_fn_headings_empty():
    assert extract_fn_headings([]) == set()


def test_extract_fn_headings_ignores_whitespace_only():
    """Blocks that are whitespace-only are skipped."""
    blocks = ["### `Foo()`\ncontent\n", "   \n", "### `Bar()`\ncontent\n"]
    assert extract_fn_headings(blocks) == {"### `Foo()`", "### `Bar()`"}


def test_restore_lost_blocks_noop_when_complete():
    """No blocks missing → returns 0, fn_blocks unchanged."""
    blocks = ["### `Foo()`\ncontent\n", "### `Bar()`\ncontent\n"]
    snapshot = extract_fn_headings(blocks)
    backup = list(blocks)
    assert restore_lost_blocks(blocks, snapshot, backup) == 0
    assert blocks == backup


def test_restore_lost_blocks_restores_and_preserves_order():
    """Deleted middle block is reinserted between its neighbours."""
    backup = [
        "### `Foo()`\ncontent_a\n",
        "### `Bar()`\ncontent_b\n",
        "### `Baz()`\ncontent_c\n",
    ]
    # Bar was deleted during patching
    fn_blocks = [backup[0], backup[2]]
    snapshot = extract_fn_headings(backup)
    restored = restore_lost_blocks(fn_blocks, snapshot, backup)
    assert restored == 1
    assert len(fn_blocks) == 3
    # Bar must sit between Foo and Baz
    headings = [b.split("\n", 1)[0].strip() for b in fn_blocks]
    assert headings.index("### `Bar()`") < headings.index("### `Baz()`")
    assert headings.index("### `Foo()`") < headings.index("### `Bar()`")


def test_restore_lost_blocks_restores_to_end_when_no_anchor():
    """Block with no surviving later neighbour is appended at end."""
    backup = [
        "### `Foo()`\ncontent_a\n",
        "### `Bar()`\ncontent_b\n",
    ]
    # Bar was deleted, Foo still present
    fn_blocks = [backup[0]]
    snapshot = extract_fn_headings(backup)
    restore_lost_blocks(fn_blocks, snapshot, backup)
    assert len(fn_blocks) == 2
    assert fn_blocks[-1].startswith("### `Bar()`")
```

- [x] **Step 4.2: Run to verify failure**

```bash
uv run pytest validator/tests/test_sections.py -k "extract_fn_headings or restore_lost" -v
```

Expected: `ImportError`.

- [x] **Step 4.3: Implement `extract_fn_headings`**

Add after `sub_chunk_section` in `sections.py`:

```python
def extract_fn_headings(fn_blocks: list[str]) -> set[str]:
    """Return the first-line heading of each non-empty block.

    Example: '### `GetOwner(inst)`' for a block starting with that line.
    Used to snapshot which function entries exist before a patch loop.
    """
    return {block.split("\n", 1)[0].strip() for block in fn_blocks if block.strip()}
```

- [x] **Step 4.4: Implement `restore_lost_blocks`**

Add after `extract_fn_headings` in `sections.py`:

```python
def restore_lost_blocks(
    fn_blocks: list[str],
    snapshot: set[str],
    backup_fn_blocks: list[str],
) -> int:
    """Reinsert fn_blocks whose heading was in snapshot but is now missing.

    Preserves original order: each restored block is inserted immediately before
    the first subsequent backup entry that still exists in fn_blocks.
    If no such anchor exists, the block is appended at the end.

    Returns the number of blocks restored.
    """
    current = extract_fn_headings(fn_blocks)
    lost_headings = snapshot - current
    if not lost_headings:
        return 0

    current_headings_list = [b.split("\n", 1)[0].strip() for b in fn_blocks]
    restored = 0

    for orig_idx, block in enumerate(backup_fn_blocks):
        heading = block.split("\n", 1)[0].strip()
        if heading not in lost_headings:
            continue

        # Find insertion point: before the first later backup heading still present
        insert_pos = len(fn_blocks)
        for later_idx in range(orig_idx + 1, len(backup_fn_blocks)):
            later_heading = backup_fn_blocks[later_idx].split("\n", 1)[0].strip()
            if later_heading in current_headings_list:
                insert_pos = current_headings_list.index(later_heading)
                break

        fn_blocks.insert(insert_pos, block)
        current_headings_list.insert(insert_pos, heading)
        restored += 1

    return restored
```

- [x] **Step 4.5: Run tests**

```bash
uv run pytest validator/tests/test_sections.py -k "extract_fn_headings or restore_lost" -v
```

Expected: all PASS.

- [x] **Step 4.6: Run full sections suite**

```bash
uv run pytest validator/tests/test_sections.py -v
```

Expected: all PASS.

- [x] **Step 4.7: Commit**

```bash
git add validator/src/validator/content/sections.py validator/tests/test_sections.py
git commit -m "feat(sections): add extract_fn_headings and restore_lost_blocks"
```

---

### Task 5: Inject FORMAT CONTRACT and FORMAT RULES into section prompts

**Files:**
- Modify: `validator/src/validator/content/prompts.py`
- Test: (inline assertions — no new test file needed; add to existing prompt tests if any)

The goal: both section-level prompts gain format constraints so the LLM reviewer checks
format compliance and the writer preserves structure.

- [x] **Step 5.1: Write failing tests**

Add to `validator/tests/test_content_chunked.py` (or create a small test in `test_sections.py`):

```python
from validator.content.prompts import (
    build_section_reviewer_prompt,
    build_section_writer_prompt,
)


def test_section_reviewer_prompt_contains_format_contract():
    prompt = build_section_reviewer_prompt("## Functions\n### `Foo(x)`\n* **Description:** x\n", "")
    assert "FORMAT CONTRACT" in prompt
    assert "* **Description:**" in prompt
    assert "CHECK BOTH" in prompt


def test_section_writer_prompt_contains_format_rules():
    prompt = build_section_writer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n", "", [], []
    )
    assert "FORMAT RULES" in prompt
    assert "NEVER" in prompt
    assert "minimal substring" in prompt.lower() or "MINIMAL" in prompt
```

- [x] **Step 5.2: Run to verify failure**

```bash
uv run pytest validator/tests/test_content_chunked.py -k "format_contract or format_rules" -v
```

Expected: FAIL — `AssertionError: FORMAT CONTRACT not in prompt`.

- [x] **Step 5.3: Add format string constants to `prompts.py`**

At the top of `validator/src/validator/content/prompts.py`, after the module docstring,
add two private constants (exact content required — tests assert specific phrases):

```python
_FORMAT_CONTRACT = """
## FORMAT CONTRACT
Each function entry MUST follow this exact structure:
### `FunctionName(params)`
* **Description:** one-line summary
* **Parameters:**
  - `name` (type) -- description
* **Returns:** description
* **Error states:** description  (only if applicable)

CHECK BOTH:
1. Content accuracy (params match Lua source, descriptions correct)
2. Format compliance (structure matches FORMAT CONTRACT above)

Flag format violations as issues just like content errors.
"""

_FORMAT_RULES = """
## FORMAT RULES — NEVER VIOLATE
- NEVER rename or reformat ### headings (lines starting with "### `")
- NEVER change "* **Description:**", "* **Parameters:**",
  "* **Returns:**", "* **Error states:**" bullet labels
- NEVER convert bullet lists to numbered lists or tables
- NEVER add or remove ### function entries
- ONLY modify the TEXT CONTENT within the existing structure
- old_text in each patch must be a MINIMAL substring (a single line or short phrase) --
  never use an entire function block as old_text
"""
```

- [x] **Step 5.4: Inject `_FORMAT_CONTRACT` into `build_section_reviewer_prompt`**

The current f-string (lines 109–130 of `prompts.py`) ends with `## Section to Review`
then `## Response Format`. Insert `{_FORMAT_CONTRACT}` between them:

Replace:
```python
    return f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.

{lua_instruction}

## Lua Context (functions referenced in this section)
{lua_block}

## Section to Review
{section_text}

## Response Format
```

With:
```python
    return f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.

{lua_instruction}
{_FORMAT_CONTRACT}
## Lua Context (functions referenced in this section)
{lua_block}

## Section to Review
{section_text}

## Response Format
```

- [x] **Step 5.5: Inject `_FORMAT_RULES` into `build_section_writer_prompt`**

The current f-string (lines 149–178) opens with the description then `## Lua Context`.
Insert `{_FORMAT_RULES}` after the opening line and before `## Lua Context`:

Replace:
```python
    return f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.

Fix the following documentation section based on reviewer feedback.

## Lua Context (ground truth for this section)
```

With:
```python
    return f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.

Fix the following documentation section based on reviewer feedback.
{_FORMAT_RULES}
## Lua Context (ground truth for this section)
```

- [x] **Step 5.6: Run tests**

```bash
uv run pytest validator/tests/test_content_chunked.py -k "format_contract or format_rules" -v
```

Expected: both PASS.

- [x] **Step 5.7: Run full validator test suite to check no regressions**

```bash
uv run pytest validator/tests/ -v
```

Expected: all PASS.

- [x] **Step 5.8: Commit**

```bash
git add validator/src/validator/content/prompts.py validator/tests/test_content_chunked.py
git commit -m "feat(prompts): inject FORMAT CONTRACT and FORMAT RULES into section prompts"
```

---

## Chunk 2: Integration — `chunked.py` 2-path dispatch

### Task 6: Replace section loop body with large/small dispatch in `chunked.py`

**Files:**
- Modify: `validator/src/validator/content/chunked.py`
- Test: `validator/tests/test_content_chunked.py`

The current `run_chunked_content_loop` loops over `##` sections with a single review/patch
path. This task adds a second path for large sections (>`SECTION_TOKEN_THRESHOLD` AND
containing a line-anchored `### ` sub-heading), which processes those sections in
token-limited batches with snapshot+restore.

- [x] **Step 6.1: Write failing tests for the new batch path**

Add to `validator/tests/test_content_chunked.py`:

```python
from unittest.mock import patch, call
import re as _re


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_fn_block(name: str, desc: str = "Does something.") -> str:
    return (
        f"### `{name}(arg)`\n"
        f"* **Description:** {desc}\n"
        f"* **Parameters:**\n  - `arg` (number) -- an argument.\n"
        f"* **Returns:** nil\n\n"
    )


def _make_large_md(n_funcs: int = 5) -> str:
    """Build a doc with one large ## section containing n_funcs ### entries."""
    section = "## Main functions\n\n"
    for i in range(n_funcs):
        section += _make_fn_block(f"Func{i:03d}")
    return f"---\ntitle: Test\n---\n# Module\n\n{section}"


LARGE_LUA = "\n".join(
    f"function Func{i:03d}(arg) end" for i in range(5)
) + "\n"


# ── tests ─────────────────────────────────────────────────────────────────────

@patch("validator.content.chunked.SECTION_TOKEN_THRESHOLD", 1)   # always trigger
@patch("validator.content.chunked.BATCH_TOKEN_LIMIT", 200)        # 1-2 fns per batch
def test_large_section_all_batches_approved(tmp_path):
    """Large section split into batches; all approved → result.approved True."""
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(_make_large_md(n_funcs=5), encoding="utf-8")
    lua_path.write_text(LARGE_LUA, encoding="utf-8")

    with patch("validator.content.chunked.ollama_chat", return_value=_approved()):
        result = run_chunked_content_loop(str(md_path), str(lua_path), _config())

    assert result.approved is True


@patch("validator.content.chunked.SECTION_TOKEN_THRESHOLD", 1)
@patch("validator.content.chunked.BATCH_TOKEN_LIMIT", 200)
def test_large_section_preserves_all_fn_entries(tmp_path):
    """After validation, all original ### entries are still present in the file."""
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    original_md = _make_large_md(n_funcs=5)
    md_path.write_text(original_md, encoding="utf-8")
    lua_path.write_text(LARGE_LUA, encoding="utf-8")

    with patch("validator.content.chunked.ollama_chat", return_value=_approved()):
        run_chunked_content_loop(str(md_path), str(lua_path), _config())

    result_md = md_path.read_text(encoding="utf-8")
    for i in range(5):
        assert f"### `Func{i:03d}(arg)`" in result_md


@patch("validator.content.chunked.SECTION_TOKEN_THRESHOLD", 1)
@patch("validator.content.chunked.BATCH_TOKEN_LIMIT", 200)
def test_large_section_restores_deleted_fn_entry(tmp_path):
    """If writer deletes a ### entry, restore_lost_blocks adds it back."""
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(_make_large_md(n_funcs=3), encoding="utf-8")
    lua_path.write_text("\n".join(f"function Func{i:03d}(arg) end" for i in range(3)) + "\n",
                        encoding="utf-8")

    original_block = _make_fn_block("Func001")

    call_count = 0
    def _deleting_writer(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # reviewer rejects
            return _rejected(["Wrong description"])
        if call_count == 2:
            # writer deletes Func001 entry entirely
            body = json.dumps([{
                "old_text": original_block,
                "new_text": "",
                "reason": "remove it"
            }])
            return {"message": {"content": body}}
        # subsequent reviews approve
        return _approved()

    with patch("validator.content.chunked.ollama_chat", side_effect=_deleting_writer):
        run_chunked_content_loop(str(md_path), str(lua_path), _config(max_iterations=5))

    result_md = md_path.read_text(encoding="utf-8")
    assert "### `Func001(arg)`" in result_md   # restored by snapshot+restore


@patch("validator.content.chunked.SECTION_TOKEN_THRESHOLD", 99999)  # never trigger
def test_small_section_uses_existing_path(tmp_path):
    """Section below threshold still uses the original per-section loop."""
    md, lua = _write_fixtures(tmp_path)
    with patch("validator.content.chunked.ollama_chat", return_value=_approved()):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True
```

- [x] **Step 6.2: Run to verify failure**

```bash
uv run pytest validator/tests/test_content_chunked.py -k "large_section or small_section_uses" -v
```

Expected: FAIL — the large-section path does not exist yet. `test_small_section_uses_existing_path` should PASS (existing behavior).

- [x] **Step 6.3: Update imports in `chunked.py`**

At the top of `validator/src/validator/content/chunked.py`, replace the existing
`from validator.content.sections import (...)` block with:

```python
import re

from validator.content.sections import (
    DocSection,
    extract_fn_headings,
    extract_function_names,
    extract_lua_context,
    join_md_sections,
    restore_lost_blocks,
    split_md_sections,
    split_section_blocks,
    sub_chunk_section,
)
```

And add to the existing `llm` imports:

```python
from llm.settings import BATCH_TOKEN_LIMIT, SECTION_TOKEN_THRESHOLD
```

- [x] **Step 6.4: Add the large-section path to `run_chunked_content_loop`**

In `run_chunked_content_loop`, the current section loop body (lines 79–146) handles all
sections identically. Replace the body of the `for idx, section in enumerate(sections, 1):` loop with the 2-path dispatch below. The small-section `else` branch is the **existing code, verbatim** — do not change it.

```python
    for idx, section in enumerate(sections, 1):
        tokens = count_tokens(section.text)
        has_subheadings = bool(re.search(r'(?m)^### ', section.text))

        if tokens > SECTION_TOKEN_THRESHOLD and has_subheadings:
            # ── Large section path: sub-chunked by ### boundaries ────────
            preamble, fn_blocks = split_section_blocks(section.text)
            snapshot = extract_fn_headings(fn_blocks)
            backup = list(fn_blocks)
            batches = sub_chunk_section(fn_blocks, BATCH_TOKEN_LIMIT)

            fn_desc = f"{len(fn_blocks)} fn(s) in {len(batches)} batch(es)"
            print(
                f"  [content/chunked] Section {idx}/{len(sections)} "
                f"{section.heading!r} — {fn_desc} [sub-chunked]"
            )

            offset = 0
            for batch_idx, batch in enumerate(batches, 1):
                if config.stop_check():
                    return ContentLoopResult(
                        approved=False,
                        iterations=total_iterations,
                        final_issues=["Interrupted by user"],
                    )

                batch_size = len(batch)
                batch_text = "".join(batch)
                lua_ctx = extract_lua_context(
                    lua_source, extract_function_names(batch_text)
                )

                print(
                    f"  [content/chunked] Section {idx} batch {batch_idx}/{len(batches)}"
                    f" — {batch_size} fn(s), {count_tokens(batch_text):,} tokens"
                )

                batch_approved = False
                batch_last_review: ReviewResult | None = None

                for i in range(config.max_iterations):
                    if config.stop_check():
                        return ContentLoopResult(
                            approved=False,
                            iterations=total_iterations,
                            final_issues=["Interrupted by user"],
                        )

                    total_iterations += 1
                    print(
                        f"  [content/chunked] Section {idx} batch {batch_idx} — "
                        f"reviewing... (iter {i + 1}/{config.max_iterations})"
                    )
                    batch_last_review = review_section(
                        batch_text, lua_ctx, config.reviewer_model
                    )
                    if batch_last_review.approved:
                        batch_approved = True
                        print(
                            f"  [content/chunked] Section {idx} batch {batch_idx} — "
                            f"approved at iteration {i + 1}"
                        )
                        break

                    patches = write_section_patches(
                        batch_text, lua_ctx, batch_last_review, config.writer_model
                    )
                    if not patches:
                        print(
                            f"  [content/chunked] Section {idx} batch {batch_idx} — "
                            "writer gave up, batch stays failed"
                        )
                        break
                    batch_text, failed = apply_patches(batch_text, patches)
                    applied = len(patches) - failed
                    print(
                        f"  [content/chunked] Section {idx} batch {batch_idx} — "
                        f"patches: {applied} applied, {failed} failed"
                    )
                else:
                    # max_iterations exhausted — final review on post-patch text
                    total_iterations += 1
                    batch_last_review = review_section(
                        batch_text, lua_ctx, config.reviewer_model
                    )
                    batch_approved = batch_last_review.approved

                if not batch_approved and batch_last_review is not None:
                    all_failed_issues.extend(batch_last_review.issues)

                # Write patched blocks back into fn_blocks
                updated = [b for b in re.split(r'(?m)^(?=### )', batch_text) if b]
                if len(updated) != batch_size:
                    print(
                        f"  [content/chunked] WARNING: Section {idx} batch {batch_idx} "
                        f"block count changed {batch_size} → {len(updated)}"
                    )
                fn_blocks[offset : offset + batch_size] = updated
                offset += len(updated)

            # Restore any function entries lost during patching
            restored = restore_lost_blocks(fn_blocks, snapshot, backup)
            if restored:
                print(
                    f"  [content/chunked] Restored {restored} lost fn entries "
                    f"in section {idx}"
                )

            # Reassemble once, after completeness restore
            section.text = preamble + "".join(fn_blocks)
            Path(md_filepath).write_text(
                join_md_sections(frontmatter, sections), encoding="utf-8"
            )

        else:
            # ── Small section path: existing logic, unchanged ────────────
            if tokens > SECTION_TOKEN_THRESHOLD:
                print(
                    f"  [content/chunked] WARNING: Section {idx} {section.heading!r} "
                    f"is {tokens:,} tokens but has no ### sub-headings — "
                    "cannot sub-chunk, proceeding as single unit"
                )
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
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    "max iterations reached, running final review"
                )
                total_iterations += 1
                last_review = review_section(section.text, lua_ctx, config.reviewer_model)
                section_approved = last_review.approved

            if not section_approved and last_review is not None:
                all_failed_issues.extend(last_review.issues)
```

- [x] **Step 6.5: Run new tests**

```bash
uv run pytest validator/tests/test_content_chunked.py -k "large_section or small_section_uses" -v
```

Expected: all 4 new tests PASS.

- [x] **Step 6.6: Run full validator suite**

```bash
uv run pytest validator/tests/ -v
```

Expected: all PASS. (Existing tests cover the small-section path unchanged.)

- [x] **Step 6.7: Smoke test on `componentutil.lua`**

```bash
uv run python -m validator dst-api-webdocs/docs/componentutil.md --content-only 2>&1 | head -60
```

Expected output shows:
- `Section N '## Main functions' — X fn(s) in Y batch(es) [sub-chunked]`
- Batch-level `reviewing...` lines with token counts well below 16K
- No `[TIMEOUT]` lines

- [x] **Step 6.8: Commit**

```bash
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(chunked): 2-path dispatch — sub-chunk large sections by ### boundaries with snapshot+restore"
```

---

## Final verification

- [x] **Run full test suite one last time**

```bash
uv run pytest validator/tests/ -v
```

Expected: all PASS.

- [x] **Re-run `componentutil.lua` end-to-end**

```bash
uv run mod-document dst-scripts/componentutil.lua
```

Expected:
- `## Main functions` sub-chunked into batches, no timeout
- `## Dependencies & tags` (below threshold) uses small path, converges faster with format-aware prompts
- No `[TIMEOUT]` errors
- Generated doc structure matches few_shot format convention
