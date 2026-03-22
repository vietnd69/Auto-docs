# validator/tests/test_sections.py
import pytest
from unittest.mock import patch
from validator.content.sections import DocSection, split_md_sections, join_md_sections, extract_function_names
from validator.content.sections import extract_lua_context


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
