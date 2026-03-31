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
    defaults = dict(max_iterations=3, writer_model="m", reviewer_model="m")
    defaults.update(kwargs)
    return ContentLoopConfig(**defaults)


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


from validator.content.prompts import (
    build_section_reviewer_prompt,
    build_section_writer_prompt,
)


def test_section_reviewer_prompt_returns_tuple():
    """build_section_reviewer_prompt should return (system, user) tuple."""
    result = build_section_reviewer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n", "function Foo(x) end"
    )
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2
    system_prompt, user_content = result
    assert isinstance(system_prompt, str)
    assert isinstance(user_content, str)
    # System should contain rules, user should contain section + lua
    assert "reviewer" in system_prompt.lower() or "review" in system_prompt.lower()
    assert "Foo" in user_content


def test_section_reviewer_prompt_content_only():
    """Reviewer prompt focuses on content accuracy, not format."""
    system, user = build_section_reviewer_prompt("## Functions\n### `Foo(x)`\n* **Description:** x\n", "")
    assert "CONTENT ACCURACY ONLY" in system
    assert "FORMAT CONTRACT" not in system
    assert "FUNCTION FORMAT REFERENCE" not in system
    assert "QUALITY RULES" in system
    assert "IGNORE format rules" in system
    assert "* **Description:**" in user


def test_section_writer_prompt_returns_tuple():
    """build_section_writer_prompt should return (system, user) tuple."""
    result = build_section_writer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n",
        "function Foo(x) end",
        ["Wrong description"],
        ["Fix the description"],
    )
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2
    system_prompt, user_content = result
    assert "writer" in system_prompt.lower() or "patch" in system_prompt.lower()
    assert "Wrong description" in user_content


def test_section_writer_prompt_contains_format_rules():
    system, user = build_section_writer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n", "", [], []
    )
    combined = system + user
    assert "FORMAT RULES" in combined
    assert "NEVER" in combined or "Do NOT" in combined


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


# ── Task 7: _fingerprint_issues ───────────────────────────────────────────────

def test_fingerprint_issues_normalizes():
    from validator.content.chunked import _fingerprint_issues
    issues = ["  Wrong Param  ", "wrong param", "Missing return"]
    fp = _fingerprint_issues(issues)
    assert len(fp) == 2
    assert "wrong param" in fp
    assert "missing return" in fp


def test_fingerprint_issues_empty():
    from validator.content.chunked import _fingerprint_issues
    fp = _fingerprint_issues([])
    assert fp == set()


def test_oscillation_detected():
    """When overlap exceeds threshold, oscillation should be detected."""
    from validator.content.chunked import _fingerprint_issues
    prev = _fingerprint_issues(["issue a", "issue b", "issue c"])
    curr = _fingerprint_issues(["issue a", "issue b", "issue d"])
    overlap = len(curr & prev) / max(len(curr), 1)
    assert overlap > 0.5


# ── Task 8: _compact_messages ─────────────────────────────────────────────────

def test_compact_messages_under_budget():
    """Messages under token budget and turn limit should not be compacted."""
    from validator.content.chunked import _compact_messages
    msgs = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "section1"},
        {"role": "assistant", "content": "review1"},
        {"role": "user", "content": "section2"},
    ]
    result = _compact_messages(msgs, max_turns=6, token_budget=3000)
    assert len(result) == 4


def test_compact_messages_over_token_budget():
    """Messages exceeding token budget should compact to system + last 2 non-system."""
    from validator.content.chunked import _compact_messages
    msgs = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "word " * 600},
        {"role": "assistant", "content": "word " * 600},
        {"role": "user", "content": "word " * 600},
        {"role": "assistant", "content": "word " * 600},
        {"role": "user", "content": "latest"},
        {"role": "assistant", "content": "latest_resp"},
    ]
    result = _compact_messages(msgs, max_turns=10, token_budget=500)
    assert result[0]["role"] == "system"
    assert len(result) == 3
    assert result[-1]["content"] == "latest_resp"
    assert result[-2]["content"] == "latest"


def test_oscillation_breaks_loop(tmp_path):
    """When reviewer returns same issues repeatedly, the loop should stop early."""
    md_content = "---\ntitle: T\n---\n## Functions\n`Alpha()` docs.\n"
    lua_content = "function Alpha() return 1 end\n"
    md, lua = _write_fixtures(tmp_path, md_content, lua_content)

    call_count = 0
    def _oscillating(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 1:
            return _rejected(["Same issue every time"])
        return _patches("`Alpha()` docs.", "`Alpha()` fixed docs.")

    with patch("validator.content.chunked.ollama_chat", side_effect=_oscillating):
        result = run_chunked_content_loop(md, lua, _config(max_iterations=10))

    assert result.iterations < 10


def test_compact_messages_over_turn_limit():
    """When over turn limit, compact to system + last 2."""
    from validator.content.chunked import _compact_messages
    msgs = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "old1"},
        {"role": "assistant", "content": "resp1"},
        {"role": "user", "content": "old2"},
        {"role": "assistant", "content": "resp2"},
        {"role": "user", "content": "latest1"},
        {"role": "assistant", "content": "latest_resp"},
        {"role": "user", "content": "latest2"},
    ]
    result = _compact_messages(msgs, max_turns=4, token_budget=3000)
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "rules"
    assert result[-1]["content"] == "latest2"


# ── Task 2: classify_lua_functions ───────────────────────────────────────────

from validator.content.sections import (
    classify_lua_functions,
    prefilter_fn_blocks,
    ensure_required_fields,
)


def test_classify_local_function_keyword():
    lua = "local function _ispassable(x, y) return true end\n"
    result = classify_lua_functions(lua)
    assert result["_ispassable"] == "local"


def test_classify_local_assignment():
    lua = "local MyFn = function(x) return x end\n"
    result = classify_lua_functions(lua)
    assert result["MyFn"] == "local"


def test_classify_global_function():
    lua = "function GetOwner(inst) return inst.owner end\n"
    result = classify_lua_functions(lua)
    assert result["GetOwner"] == "global"


def test_classify_last_definition_wins():
    """Local closure followed by global wrapper → last definition (global) wins."""
    lua = (
        "local function GetOwner(inst) return nil end\n"
        "function GetOwner(inst) return inst.owner end\n"
    )
    result = classify_lua_functions(lua)
    assert result["GetOwner"] == "global"


def test_classify_empty_source():
    assert classify_lua_functions("") == {}


# ── Task 2: prefilter_fn_blocks ──────────────────────────────────────────────

def test_prefilter_removes_local_fn():
    lua = "local function _helper() end\nfunction RealFn(x) end\n"
    blocks = [
        "### `_helper()`\n* **Description:** internal\n",
        "### `RealFn(x)`\n* **Description:** public\n",
    ]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert len(kept) == 1
    assert kept[0].startswith("### `RealFn")
    assert "_helper" in stripped


def test_prefilter_removes_hallucinated():
    lua = "function RealFn(x) end\n"
    blocks = [
        "### `FakeFunc(x)`\n* **Description:** fake\n",
        "### `RealFn(x)`\n* **Description:** real\n",
    ]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert len(kept) == 1
    assert "FakeFunc" in stripped


def test_prefilter_backtick_stripping_snake_case():
    """Backtick-quoted snake_case name extracted correctly before lookup."""
    lua = "local function _ispassable(x, y, sim) return true end\n"
    blocks = ["### `_ispassable(x, y, sim)`\n* **Description:** check\n"]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert kept == []
    assert "_ispassable" in stripped


def test_prefilter_all_local_returns_empty_kept():
    """All functions local → kept_blocks empty, loop should skip review."""
    lua = "local function Foo() end\nlocal function Bar() end\n"
    blocks = ["### `Foo()`\n...", "### `Bar()`\n..."]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert kept == []
    assert len(stripped) == 2


def test_prefilter_unrecognized_heading_kept():
    """Block with unparseable ### heading is kept (fail-safe)."""
    blocks = ["### (no name here)\ncontent\n"]
    kept, stripped = prefilter_fn_blocks(blocks, "function Foo() end\n")
    assert len(kept) == 1
    assert stripped == []


# ── Task 2: ensure_required_fields ───────────────────────────────────────────

def test_ensure_required_fields_adds_missing():
    block = "### `Foo(x)`\n* **Description:** does stuff\n"
    result = ensure_required_fields([block])
    assert "* **Parameters:**" in result[0]
    assert "* **Returns:**" in result[0]


def test_ensure_required_fields_no_duplicate():
    block = (
        "### `Foo(x)`\n"
        "* **Description:** x\n"
        "* **Parameters:** None\n"
        "* **Returns:** nil\n"
    )
    result = ensure_required_fields([block])
    assert result[0].count("* **Parameters:**") == 1


def test_ensure_required_fields_pure_function():
    """ensure_required_fields must not mutate its input."""
    block = "### `Foo()`\n* **Description:** x\n"
    original = block
    ensure_required_fields([block])
    assert block == original


# ── Task 3: apply_typed_ops ──────────────────────────────────────────────────

from validator.content.sections import apply_typed_ops, DocSection
from validator.content.writer import TypedOp


def _section(heading: str, text: str) -> DocSection:
    return DocSection(heading=heading, text=text)


def test_apply_update_section():
    sections = [_section("## Overview", "## Overview\nOld text.\n")]
    op = TypedOp(op="update_section", section="## Overview", content="## Overview\nNew text.\n")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert result[0].text == "## Overview\nNew text.\n"


def test_apply_update_field_in_section():
    sections = [_section("## Overview", "## Overview\n* **Description:** wrong\n")]
    op = TypedOp(op="update_field", section="## Overview", field="Description", value="correct")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "* **Description:** correct" in result[0].text
    assert "wrong" not in result[0].text


def test_apply_update_field_in_function():
    fn_block = "### `Foo(x)`\n* **Returns:** wrong\n"
    sections = [_section("## Main functions", "## Main functions\n" + fn_block)]
    op = TypedOp(op="update_field", section="## Main functions", function="Foo", field="Returns", value="entity")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "* **Returns:** entity" in result[0].text
    assert "wrong" not in result[0].text


def test_apply_rewrite_function():
    fn_block = "### `Foo(x)`\n* **Description:** old\n"
    sections = [_section("## Main functions", "## Main functions\n" + fn_block)]
    new_block = "### `Foo(x)`\n* **Description:** new\n"
    op = TypedOp(op="rewrite_function", section="## Main functions", function="Foo", content=new_block)
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "new" in result[0].text
    assert "old" not in result[0].text


def test_apply_rewrite_function_not_found_no_exception():
    """Rewrite op for non-existent function → silent no-op, no exception."""
    sections = [_section("## Main functions", "## Main functions\n### `Bar()`\ncontent\n")]
    op = TypedOp(op="rewrite_function", section="## Main functions", function="NonExistent", content="x")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "Bar" in result[0].text  # original preserved


def test_apply_delete_function():
    sections = [_section("## Main functions",
        "## Main functions\n### `Foo()`\nfoo\n\n### `Bar()`\nbar\n")]
    op = TypedOp(op="delete_function", section="## Main functions", function="Foo")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "### `Foo()`" not in result[0].text
    assert "### `Bar()`" in result[0].text


def test_apply_delete_function_intentionally_removed_noop():
    """delete_function for already-stripped name → silent no-op."""
    sections = [_section("## Main functions",
        "## Main functions\n### `Bar()`\nbar\n")]
    op = TypedOp(op="delete_function", section="## Main functions", function="_helper")
    result = apply_typed_ops(
        sections, [op], frontmatter="",
        intentionally_removed={"_helper"}
    )
    assert result[0].text == sections[0].text  # unchanged


def test_apply_section_not_found_noop():
    """Op targeting missing section → no exception, other sections unchanged."""
    sections = [_section("## Overview", "## Overview\ncontent\n")]
    op = TypedOp(op="update_section", section="## NonExistent", content="new")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert result[0].text == "## Overview\ncontent\n"


def test_apply_does_not_mutate_input():
    """apply_typed_ops must return new sections, not modify input."""
    original_text = "## Overview\noriginal\n"
    sections = [_section("## Overview", original_text)]
    op = TypedOp(op="update_section", section="## Overview", content="## Overview\nnew\n")
    apply_typed_ops(sections, [op], frontmatter="")
    assert sections[0].text == original_text  # input unchanged


# ── Task 4: extract_section_lua_context ──────────────────────────────────────

from validator.content.sections import extract_section_lua_context


_LUA_MODULE = """\
local MYCONST = 42
local DEFAULT_VAL = "hello"
require("mymodule")
inst.components.combat:SetHurtSound("dontstarve/creatures/hurt")
inst:AddTag("monster")

function GetOwner(inst)
    return inst.owner
end

function SetTarget(inst, target)
    inst.target = target
end

ListenForEvent("death", inst, OnDeath)
PushEvent("attacked", inst, {attacker = attacker})
"""


def test_extract_overview_stops_at_first_function():
    result = extract_section_lua_context("## Overview", _LUA_MODULE, max_tokens=8000)
    assert "MYCONST" in result
    assert "GetOwner" not in result  # function body not included


def test_extract_usage_example_signatures_only():
    result = extract_section_lua_context("## Usage example", _LUA_MODULE, max_tokens=8000)
    assert "GetOwner" in result
    assert "SetTarget" in result
    # Function bodies not included (only the definition line)
    assert "inst.owner" not in result


def test_extract_dependencies_tags_patterns():
    result = extract_section_lua_context("## Dependencies & tags", _LUA_MODULE, max_tokens=8000)
    assert "require" in result
    assert "AddTag" in result
    assert "combat" in result


def test_extract_properties_class_constructor():
    lua = (
        "local MyClass = Class(function(self, inst)\n"
        "    self.value = 0\n"
        "    self.name = ''\n"
        "end)\n"
        "\n"
        "function MyClass:Method()\n"
        "    return self.value\n"
        "end\n"
    )
    result = extract_section_lua_context("## Properties", lua, max_tokens=8000)
    assert "self.value" in result
    assert "self.name" in result


def test_extract_properties_utility_fallback():
    """Utility module (no Class()) uses constants + table assignments."""
    lua = "local MAX_SIZE = 100\nlocal MIN_VAL = 0\nfunction Foo() end\n"
    result = extract_section_lua_context("## Properties", lua, max_tokens=8000)
    assert "MAX_SIZE" in result


def test_extract_events_listeners():
    result = extract_section_lua_context("## Events & listeners", _LUA_MODULE, max_tokens=8000)
    assert "ListenForEvent" in result
    assert "PushEvent" in result


def test_extract_unknown_section_returns_empty():
    result = extract_section_lua_context("## Unknown Section", _LUA_MODULE, max_tokens=8000)
    assert result == ""


def test_extract_respects_max_tokens():
    """Result token count must not exceed max_tokens limit."""
    from llm.tokens import count_tokens
    lua = "\n".join(f"require('module_{i}')" for i in range(500))
    result = extract_section_lua_context("## Dependencies & tags", lua, max_tokens=100)
    tokens = count_tokens(result)
    if tokens != -1:
        assert tokens <= 110  # allow small margin for truncation marker


# ── Task 6: parse_findings_response / parse_typed_op_response ────────────────

import json as _json

from validator.content.reviewer import Finding, parse_findings_response, parse_findings_json
from validator.content.writer import TypedOp, parse_typed_op_response, parse_typed_op_json


def test_parse_findings_response_approved():
    raw = '{"approved": true, "findings": []}'
    findings = parse_findings_response(raw)
    assert findings == []


def test_parse_findings_response_with_finding():
    raw = _json.dumps({
        "approved": False,
        "findings": [{
            "section": "## Main functions",
            "function": "GetOwner",
            "field": "Returns",
            "rule_id": "WRONG_VALUE",
            "issue": "Returns description is wrong",
        }]
    })
    findings = parse_findings_response(raw)
    assert len(findings) == 1
    assert findings[0].rule_id == "WRONG_VALUE"
    assert findings[0].function == "GetOwner"


def test_parse_findings_response_strips_think_tags():
    raw = '<think>thinking...</think>{"approved": true, "findings": []}'
    findings = parse_findings_response(raw)
    assert findings == []


def test_parse_findings_response_malformed_returns_empty():
    assert parse_findings_response("not json") == []


def test_parse_findings_json_missing_rule_id_skipped():
    """Findings without rule_id are silently skipped."""
    data = {"approved": False, "findings": [{"section": "## Overview", "issue": "bad"}]}
    findings = parse_findings_json(data)
    assert findings == []


def test_parse_typed_op_response_update_field():
    raw = _json.dumps({
        "op": "update_field",
        "section": "## Main functions",
        "function": "GetOwner",
        "field": "Returns",
        "value": "entity or nil",
        "content": None,
    })
    op = parse_typed_op_response(raw)
    assert op is not None
    assert op.op == "update_field"
    assert op.value == "entity or nil"


def test_parse_typed_op_response_missing_op_returns_none():
    raw = _json.dumps({"section": "## Overview"})
    assert parse_typed_op_response(raw) is None


def test_parse_typed_op_response_malformed_returns_none():
    assert parse_typed_op_response("broken") is None


# ── Task 7: typed prompt builders ────────────────────────────────────────────

from validator.content.prompts import build_typed_reviewer_prompt, build_typed_writer_prompt


def test_build_typed_reviewer_prompt_returns_tuple():
    system, user = build_typed_reviewer_prompt(
        "## Main functions\n### `Foo(x)`\n* **Description:** x\n",
        "function Foo(x) end",
        section_heading="## Main functions",
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_build_typed_reviewer_prompt_includes_rule_ids():
    system, _ = build_typed_reviewer_prompt(
        "## Main functions\n### `Foo(x)`\n* **Description:** x\n",
        "",
        section_heading="## Main functions",
        rule_ids=["WRONG_VALUE", "MISSING_PARAM"],
    )
    assert "WRONG_VALUE" in system
    assert "MISSING_PARAM" in system


def test_build_typed_reviewer_prompt_scope_note_for_main_functions():
    """Reviewer for Main functions must include scope note to avoid false positives."""
    system, _ = build_typed_reviewer_prompt(
        "### `Foo(x)`\n* **Description:** x\n",
        "",
        section_heading="## Main functions",
    )
    assert "SCOPE" in system or "scope" in system


def test_build_typed_reviewer_prompt_no_scope_note_for_overview():
    system, _ = build_typed_reviewer_prompt("## Overview\nSome text.\n", "", "## Overview")
    # Overview review should NOT include the Main-functions batch restriction
    assert "SCOPE NOTE" not in system


def test_build_typed_writer_prompt_returns_tuple():
    from validator.content.reviewer import Finding
    finding = Finding(
        section="## Main functions",
        function="Foo",
        field="Returns",
        rule_id="WRONG_VALUE",
        issue="Returns nil but should return entity",
    )
    system, user = build_typed_writer_prompt(
        "### `Foo(x)`\n* **Returns:** nil\n",
        "function Foo(x) end",
        finding=finding,
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_build_typed_writer_prompt_includes_issue():
    from validator.content.reviewer import Finding
    finding = Finding(
        section="## Main functions", function="Foo", field="Returns",
        rule_id="WRONG_VALUE", issue="Returns nil but should return entity",
    )
    _, user = build_typed_writer_prompt("### `Foo(x)`\n* **Returns:** nil\n", "", finding=finding)
    assert "Returns nil but should return entity" in user


def test_build_typed_writer_prompt_includes_op_choices():
    from validator.content.reviewer import Finding
    finding = Finding(section="## Overview", function=None, field=None, rule_id="INACCURATE_DESCRIPTION", issue="x")
    system, _ = build_typed_writer_prompt("## Overview\ntext\n", "", finding=finding)
    assert "update_section" in system
    assert "update_field" in system
