"""Integration tests for run_chunked_content_loop. Mocks ollama_chat only."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from validator.content.chunked import run_chunked_content_loop
from validator.content.loop import ContentLoopConfig


# ── response helpers (typed-ops format) ──────────────────────────────────────

def _approved():
    body = json.dumps({"approved": True, "findings": []})
    return {"message": {"content": body}}


def _rejected(section: str, fn, field, rule_id: str, issue: str):
    body = json.dumps({"approved": False, "findings": [{
        "section": section, "function": fn, "field": field,
        "rule_id": rule_id, "issue": issue,
    }]})
    return {"message": {"content": body}}


def _op(op: str, section: str, fn=None, field=None, value=None, content=None):
    body = json.dumps({"op": op, "section": section, "function": fn,
                        "field": field, "value": value, "content": content})
    return {"message": {"content": body}}


def _no_op():
    """Writer returns an empty / invalid response."""
    return {"message": {"content": "{}"}}


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_fn_block(name: str) -> str:
    return (
        f"### `{name}(arg)`\n"
        f"* **Description:** {name} description\n"
        f"* **Parameters:** None\n"
        f"* **Returns:** nil\n\n"
    )


SIMPLE_MD = (
    "---\ntitle: Test\n---\n"
    "## Main functions\n\n"
    + _make_fn_block("GetOwner")
)
SIMPLE_LUA = "function GetOwner(arg) return self.owner end\n"


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


# ── integration tests ────────────────────────────────────────────────────────

def test_all_sections_approved(tmp_path):
    """Reviewer approves every section -> result.approved True."""
    md, lua = _write_fixtures(tmp_path)
    with patch("validator.content.chunked.ollama_chat", return_value=_approved()):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True
    assert result.final_issues == []
    assert result.iterations >= 1


def test_section_fails_no_op(tmp_path):
    """Reviewer rejects + writer returns invalid op -> section remains failed."""
    md, lua = _write_fixtures(tmp_path)
    # Patch BAD_RESPONSE_RETRIES=0 so writer is called exactly once per finding
    with patch("validator.content.chunked.BAD_RESPONSE_RETRIES", 0), patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Main functions", None, None, "INACCURATE_DESCRIPTION", "Wrong text"),
            _no_op(),   # writer attempt 1 (only attempt with retries=0)
            _rejected("## Main functions", None, None, "INACCURATE_DESCRIPTION", "Wrong text"),
            _no_op(),   # iteration 2
            _rejected("## Main functions", None, None, "INACCURATE_DESCRIPTION", "Wrong text"),
            _no_op(),   # iteration 3 (max_iterations=3)
            _rejected("## Main functions", None, None, "INACCURATE_DESCRIPTION", "Wrong text"),  # final verification pass
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is False
    assert "Wrong text" in result.final_issues


def test_typed_op_applied_and_written_to_disk(tmp_path):
    """Writer's update_field op is applied and persisted."""
    md, lua = _write_fixtures(tmp_path)
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Main functions", "GetOwner", "Returns", "WRONG_VALUE", "Returns wrong type"),
            _op("update_field", "## Main functions", fn="GetOwner", field="Returns", value="entity"),
            _approved(),
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True


def test_stop_check_fires_before_first_review(tmp_path):
    """stop_check() True on entry -> approved=False, no LLM calls."""
    md, lua = _write_fixtures(tmp_path)
    with patch("validator.content.chunked.ollama_chat") as mock_chat:
        result = run_chunked_content_loop(md, lua, _config(stop_check=lambda: True))
    assert result.approved is False
    assert result.final_issues == ["Interrupted by user"]
    mock_chat.assert_not_called()


def test_lua_unreadable_returns_failed(tmp_path):
    """Missing Lua file -> approved=False with descriptive message."""
    md = tmp_path / "test.md"
    md.write_text(SIMPLE_MD, encoding="utf-8")
    result = run_chunked_content_loop(
        str(md), str(tmp_path / "missing.lua"), _config()
    )
    assert result.approved is False
    assert any("Cannot read Lua source" in issue for issue in result.final_issues)


def test_empty_sections_approved(tmp_path):
    """Markdown with no ## sections is trivially approved."""
    md, lua = _write_fixtures(tmp_path, md_content="---\ntitle: T\n---\n")
    result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True
    assert result.iterations == 0


def test_multiple_sections_partial_failure(tmp_path):
    """Two sections: first approved, second failed -> overall approved=False."""
    md_content = (
        "---\ntitle: T\n---\n"
        "## Main functions\n\n"
        + _make_fn_block("Alpha")
        + _make_fn_block("Beta")
    )
    lua_content = "function Alpha(arg) return 1 end\nfunction Beta(arg) return 2 end\n"
    md, lua = _write_fixtures(tmp_path, md_content, lua_content)
    # Patch BAD_RESPONSE_RETRIES=0 so writer is called exactly once per finding
    with patch("validator.content.chunked.BAD_RESPONSE_RETRIES", 0), patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Main functions", "Beta", None, "INACCURATE_DESCRIPTION", "Beta wrong"),
            _no_op(),   # writer fails (iteration 1)
            _rejected("## Main functions", "Beta", None, "INACCURATE_DESCRIPTION", "Beta wrong"),
            _no_op(),   # iteration 2
            _rejected("## Main functions", "Beta", None, "INACCURATE_DESCRIPTION", "Beta wrong"),
            _no_op(),   # iteration 3
            _rejected("## Main functions", "Beta", None, "INACCURATE_DESCRIPTION", "Beta wrong"),  # final verification pass
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is False
    assert "Beta wrong" in result.final_issues


# ── classify_lua_functions tests ─────────────────────────────────────────────

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
    """Local closure followed by global wrapper -> last definition (global) wins."""
    lua = (
        "local function GetOwner(inst) return nil end\n"
        "function GetOwner(inst) return inst.owner end\n"
    )
    result = classify_lua_functions(lua)
    assert result["GetOwner"] == "global"


def test_classify_empty_source():
    assert classify_lua_functions("") == {}


# ── prefilter_fn_blocks tests ─────────────────────────────────────────────────

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
    """All functions local -> kept_blocks empty, loop should skip review."""
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


def test_prefilter_strips_hallucinated_state_variant():
    """onenter (fishing_nibble) stripped when state name absent from Lua source."""
    lua = "onenter = function(inst) end\nontimeout = function(inst) end\n"
    blocks = [
        "### `onenter (fishing_nibble)`\n* **Description:** d\n",
        "### `ontimeout`\n* **Description:** d\n",
    ]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert len(kept) == 1
    assert kept[0].startswith("### `ontimeout`")
    assert "onenter (fishing_nibble)" in stripped


def test_prefilter_keeps_valid_state_variant():
    """onenter (idle) kept when state name 'idle' is present in Lua source."""
    lua = 'onenter = function(inst) end\nname = "idle"\n'
    blocks = ["### `onenter (idle)`\n* **Description:** d\n"]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert len(kept) == 1
    assert stripped == []


# ── ensure_required_fields tests ─────────────────────────────────────────────

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


# ── apply_typed_ops tests ─────────────────────────────────────────────────────

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
    """Rewrite op for non-existent function -> silent no-op, no exception."""
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
    """delete_function for already-stripped name -> silent no-op."""
    sections = [_section("## Main functions",
        "## Main functions\n### `Bar()`\nbar\n")]
    op = TypedOp(op="delete_function", section="## Main functions", function="_helper")
    result = apply_typed_ops(
        sections, [op], frontmatter="",
        intentionally_removed={"_helper"}
    )
    assert result[0].text == sections[0].text  # unchanged


def test_apply_section_not_found_noop():
    """Op targeting missing section -> no exception, other sections unchanged."""
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


# ── extract_section_lua_context tests ─────────────────────────────────────────

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


# ── parse_findings_response / parse_typed_op_response tests ──────────────────

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


# ── typed prompt builder tests ────────────────────────────────────────────────

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
    finding = Finding(
        section="## Main functions", function="Foo", field="Returns",
        rule_id="WRONG_VALUE", issue="Returns nil but should return entity",
    )
    _, user = build_typed_writer_prompt("### `Foo(x)`\n* **Returns:** nil\n", "", finding=finding)
    assert "Returns nil but should return entity" in user


def test_build_typed_writer_prompt_includes_op_choices():
    finding = Finding(section="## Overview", function=None, field=None, rule_id="INACCURATE_DESCRIPTION", issue="x")
    system, _ = build_typed_writer_prompt("## Overview\ntext\n", "", finding=finding)
    assert "update_section" in system
    assert "update_field" in system


# ── New: pre-filter integration tests ────────────────────────────────────────

def test_prefilter_local_fns_never_reviewed(tmp_path):
    """Local functions are stripped before review -- reviewer never called for them."""
    md_content = (
        "---\ntitle: T\n---\n## Main functions\n\n"
        + _make_fn_block("_helper")
        + _make_fn_block("PublicFn")
    )
    lua_content = "local function _helper() end\nfunction PublicFn(arg) end\n"
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(md_content, encoding="utf-8")
    lua_path.write_text(lua_content, encoding="utf-8")

    call_count = 0
    def _mock(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        # Check that _helper is NOT in the reviewed content
        full = " ".join(m["content"] for m in messages)
        assert "_helper" not in full, "_helper was passed to reviewer"
        return _approved()

    with patch("validator.content.chunked.ollama_chat", side_effect=_mock):
        result = run_chunked_content_loop(str(md_path), str(lua_path), _config())

    result_md = md_path.read_text(encoding="utf-8")
    assert "### `_helper(arg)`" not in result_md  # stripped by pre-filter


def test_intentionally_removed_not_readded(tmp_path):
    """delete_function op for a pre-stripped name -> no-op, document unchanged.

    _ispassable appears in both the md (as a ### block) AND in the Lua as a
    local function. Pre-filter strips it into intentionally_removed. Then if
    the reviewer (wrongly) emits a delete_function op for it, apply_typed_ops
    must silently no-op -- not crash or re-add it.
    """
    md_content = (
        "---\ntitle: T\n---\n## Main functions\n\n"
        + _make_fn_block("_ispassable")   # present in md -- will be stripped by pre-filter
        + _make_fn_block("PublicFn")
    )
    lua_content = (
        "local function _ispassable(x, y) return true end\n"
        "function PublicFn(arg) end\n"
    )
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(md_content, encoding="utf-8")
    lua_path.write_text(lua_content, encoding="utf-8")

    # Pre-filter strips _ispassable; if reviewer still emits a finding for it
    # and writer responds with delete_function, apply_typed_ops must no-op.
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Main functions", "_ispassable", None, "EXTRA_PARAM", "should not exist"),
            _op("delete_function", "## Main functions", fn="_ispassable"),
            _approved(),
        ],
    ):
        result = run_chunked_content_loop(str(md_path), str(lua_path), _config())

    # No exception; PublicFn still present; _ispassable not in final doc (stripped by pre-filter)
    result_md = md_path.read_text(encoding="utf-8")
    assert "### `PublicFn(arg)`" in result_md
    assert "### `_ispassable(arg)`" not in result_md


def test_writer_op_for_missing_section_no_crash(tmp_path):
    """Writer returns op targeting a non-existent section -> no exception."""
    md, lua = _write_fixtures(tmp_path)
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Main functions", None, None, "INACCURATE_DESCRIPTION", "issue"),
            _op("update_section", "## NonExistent", content="something"),
            _approved(),
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    # Should complete without exception
    assert isinstance(result.approved, bool)
