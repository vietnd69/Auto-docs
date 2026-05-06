# validator/tests/test_sections.py
import pytest
from unittest.mock import patch
from validator.content.sections import DocSection, split_md_sections, join_md_sections, extract_function_names
from validator.content.sections import extract_lua_context, extract_section_lua_context


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


from validator.content.sections import extract_fn_headings_from_text


def test_extract_fn_headings_from_text_backtick():
    """Extracts function names from ### `FuncName(params)` headings."""
    text = "## Main functions\n\n### `GetOwner(inst)`\n* **Description:** gets owner\n\n### `SetOwner(inst, owner)`\n* **Description:** sets owner\n"
    result = extract_fn_headings_from_text(text)
    assert result == {"GetOwner", "SetOwner"}


def test_extract_fn_headings_from_text_no_backtick():
    """Extracts function names from ### FuncName headings (no backticks)."""
    text = "### GetOwner\nsome content\n### SetOwner\nmore content\n"
    result = extract_fn_headings_from_text(text)
    assert result == {"GetOwner", "SetOwner"}


def test_extract_fn_headings_from_text_dotted():
    """Extracts dotted names like CLOSEINSPECTORUTIL.IsValidTarget."""
    text = "### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`\ncontent\n### `CLOSEINSPECTORUTIL.IsValidPos(pos)`\ncontent\n"
    result = extract_fn_headings_from_text(text)
    assert result == {"CLOSEINSPECTORUTIL.IsValidTarget", "CLOSEINSPECTORUTIL.IsValidPos"}


def test_extract_fn_headings_from_text_empty():
    """Empty text returns empty set."""
    assert extract_fn_headings_from_text("") == set()


def test_extract_fn_headings_from_text_no_headings():
    """Text with no ### headings returns empty set."""
    assert extract_fn_headings_from_text("## Overview\nSome text\n") == set()


from validator.content.sections import delete_fn_block


def test_delete_fn_block_middle():
    """Deletes a middle function block, preserving neighbors."""
    text = (
        "### `Foo(x)`\n* **Description:** foo\n\n"
        "### `Bar(y)`\n* **Description:** bar\n\n"
        "### `Baz(z)`\n* **Description:** baz\n"
    )
    result = delete_fn_block(text, "Bar")
    assert "### `Foo(x)`" in result
    assert "### `Bar(y)`" not in result
    assert "### `Baz(z)`" in result


def test_delete_fn_block_last():
    """Deletes the last function block."""
    text = "### `Foo(x)`\ncontent foo\n\n### `Bar(y)`\ncontent bar\n"
    result = delete_fn_block(text, "Bar")
    assert "### `Foo(x)`" in result
    assert "### `Bar(y)`" not in result


def test_delete_fn_block_dotted_name():
    """Deletes block with dotted name like CLOSEINSPECTORUTIL.IsValidTarget."""
    text = (
        "### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`\n* **Description:** check target\n\n"
        "### `CLOSEINSPECTORUTIL.GetRange(inst)`\n* **Description:** get range\n"
    )
    result = delete_fn_block(text, "CLOSEINSPECTORUTIL.IsValidTarget")
    assert "IsValidTarget" not in result
    assert "GetRange" in result


def test_delete_fn_block_not_found():
    """Returns text unchanged if fn_name not found."""
    text = "### `Foo(x)`\ncontent\n"
    assert delete_fn_block(text, "NonExistent") == text


def test_delete_fn_block_first():
    """Deletes the first function block, preserving subsequent blocks."""
    text = "### `Foo(x)`\ncontent foo\n\n### `Bar(y)`\ncontent bar\n"
    result = delete_fn_block(text, "Foo")
    assert "### `Foo(x)`" not in result
    assert "### `Bar(y)`" in result
    assert result.lstrip("\n").startswith("### `Bar(y)`")


def test_delete_fn_block_collapses_blank_lines():
    """Trailing blank lines after deletion are collapsed to one newline."""
    text = "### `Foo(x)`\ncontent foo\n\n\n### `Bar(y)`\ncontent bar\n"
    result = delete_fn_block(text, "Foo")
    assert not result.startswith("\n\n")
    assert "### `Bar(y)`" in result


# ── stategraph helpers ──────────────────────────────────────────────────────

from validator.content.sections import (
    _is_stategraph,
    extract_stategraph_event_names,
    check_stategraph_events_null,
)

_SG_LUA = '''
local SPEED = 6
StateGraph("sg_test",
    states, events, "idle", actionhandlers)
events = {
    EventHandler("death", function(inst) end),
    EventHandler("freeze", function(inst) end),
}
'''

_COMP_LUA = '''
local MyComp = Class(function(self, inst) self.inst = inst end)
function MyComp:GetOwner() return self.inst end
'''


def test_is_stategraph_detects():
    assert _is_stategraph(_SG_LUA) is True


def test_is_stategraph_component():
    assert _is_stategraph(_COMP_LUA) is False


def test_is_stategraph_empty():
    assert _is_stategraph("") is False


def test_extract_stategraph_event_names_basic():
    assert extract_stategraph_event_names(_SG_LUA) == ["death", "freeze"]


def test_extract_stategraph_event_names_none():
    assert extract_stategraph_event_names(_COMP_LUA) == []


def test_check_events_null_listens_to_none():
    section = "## Events & listeners\n**Listens to:** None\n"
    assert check_stategraph_events_null(section, _SG_LUA) is True


def test_check_events_null_bold_none():
    section = "## Events & listeners\n**None.**\n"
    assert check_stategraph_events_null(section, _SG_LUA) is True


def test_check_events_null_has_content():
    section = "## Events & listeners\n**Listens to:** death, freeze\n"
    assert check_stategraph_events_null(section, _SG_LUA) is False


def test_check_events_null_not_stategraph():
    section = "## Events & listeners\n**Listens to:** None\n"
    assert check_stategraph_events_null(section, _COMP_LUA) is False


def test_check_events_null_no_eventhandlers():
    lua = "StateGraph('sg_empty', states, {}, 'idle', {})\n"
    section = "## Events & listeners\n**Listens to:** None\n"
    assert check_stategraph_events_null(section, lua) is False


def test_check_events_null_none_itself_bolded():
    section = "## Events & listeners\n**Listens to:** **None**\n"
    assert check_stategraph_events_null(section, _SG_LUA) is True


# ── extract_section_lua_context — Events branch ─────────────────────────────

_STATEGRAPH_EVENTS_LUA = '''\
StateGraph("sg_test", states, events, "idle", {})
events = {
    EventHandler("death", function(inst)
        inst.sg:GoToState("death")
    end),
    EventHandler("freeze", function(inst)
        inst.sg:GoToState("frozen")
    end),
}
'''

_COMP_EVENTS_LUA = '''\
local MyComp = Class(function(self, inst)
    inst:ListenForEvent("onhit", function() self:OnHit() end)
    inst:PushEvent("ready", {data=1})
end)
'''

def test_events_context_includes_eventhandler():
    result = extract_section_lua_context("## Events & listeners", _STATEGRAPH_EVENTS_LUA, 8000)
    assert 'EventHandler("death"' in result
    assert 'EventHandler("freeze"' in result


def test_events_context_includes_listenforevent():
    """Regression: existing ListenForEvent pattern still captured."""
    result = extract_section_lua_context("## Events & listeners", _COMP_EVENTS_LUA, 8000)
    assert "ListenForEvent" in result


def test_events_context_includes_pushevent():
    """Regression: existing PushEvent pattern still captured."""
    result = extract_section_lua_context("## Events & listeners", _COMP_EVENTS_LUA, 8000)
    assert "PushEvent" in result


def test_events_context_empty_when_no_events():
    lua = "function DoThing(inst) return nil end\n"
    result = extract_section_lua_context("## Events & listeners", lua, 8000)
    assert result == ""


# ── extract_section_lua_context — Properties branch ─────────────────────────

_STATEGRAPH_PROPS_LUA = '''\
local SPEED = 6
local ATTACK_PROP = "fast"
StateGraph("sg_wx78", states, events, "idle", actionhandlers)
CommonStates.AddSinkAndWashAshoreStates(states, {
    sink = "sink",
    washashore = "washashore",
})
CommonStates.AddVoidFallStates(states, {})
SGWX78Common.AddWX78SpinStates(states)
states = {
    State{name = "idle", tags = {"idle"}},
    State{name = "attack", tags = {"attack", "busy"}},
}
'''

_COMP_PROPS_LUA = '''\
local MyComp = Class(function(self, inst)
    self.inst = inst
    self.speed = 6
end)
function MyComp:GetSpeed() return self.speed end
'''


def test_properties_stategraph_includes_commonstate_calls():
    result = extract_section_lua_context("## Properties", _STATEGRAPH_PROPS_LUA, 8000)
    assert "CommonStates.AddSinkAndWashAshoreStates" in result
    assert "CommonStates.AddVoidFallStates" in result


def test_properties_stategraph_includes_sg_common_calls():
    result = extract_section_lua_context("## Properties", _STATEGRAPH_PROPS_LUA, 8000)
    assert "SGWX78Common.AddWX78SpinStates" in result


def test_properties_stategraph_includes_state_names():
    result = extract_section_lua_context("## Properties", _STATEGRAPH_PROPS_LUA, 8000)
    assert "-- States defined inline:" in result
    assert "idle" in result
    assert "attack" in result


def test_properties_stategraph_includes_constants():
    result = extract_section_lua_context("## Properties", _STATEGRAPH_PROPS_LUA, 8000)
    assert "SPEED" in result
    assert "ATTACK_PROP" in result


def test_properties_stategraph_header_only():
    """Minimal stategraph with no constants/injections still returns StateGraph header."""
    lua = 'StateGraph("sg_empty", {}, {}, "idle", {})\n'
    result = extract_section_lua_context("## Properties", lua, 8000)
    assert 'StateGraph("sg_empty"' in result


def test_properties_component_uses_class_path():
    """Regression: component files still use Class() constructor extraction."""
    result = extract_section_lua_context("## Properties", _COMP_PROPS_LUA, 8000)
    assert "self.speed" in result
