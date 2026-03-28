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


# ── Task 3: _extract_removal_targets ──────────────────────────────────────────

from validator.content.chunked import _extract_removal_targets


def test_extract_removal_targets_backtick_names():
    """Extracts backtick-quoted names from hallucination issues."""
    issues = [
        "`CLOSEINSPECTORUTIL.IsValidTarget` does not exist in the Lua source",
        "`CLOSEINSPECTORUTIL.IsValidPos` is hallucinated",
    ]
    batch_text = (
        "### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`\ncontent\n"
        "### `CLOSEINSPECTORUTIL.IsValidPos(pos)`\ncontent\n"
        "### `RealFunction(x)`\ncontent\n"
    )
    result = _extract_removal_targets(issues, batch_text)
    assert "CLOSEINSPECTORUTIL.IsValidTarget" in result
    assert "CLOSEINSPECTORUTIL.IsValidPos" in result
    assert "RealFunction" not in result


def test_extract_removal_targets_no_hallucination_phrases():
    """Issues without removal-intent phrases are ignored."""
    issues = ["Wrong parameter type for `GetOwner`"]
    result = _extract_removal_targets(issues, "### `GetOwner(inst)`\ncontent\n")
    assert result == set()


def test_extract_removal_targets_empty_issues():
    """Empty issues list returns empty set."""
    assert _extract_removal_targets([], "") == set()


def test_extract_removal_targets_cross_reference_filters():
    """Names not present as headings in batch_text are excluded."""
    issues = ["`FakeFunc` does not exist in the Lua source"]
    batch_text = "### `RealFunc(x)`\ncontent\n"
    result = _extract_removal_targets(issues, batch_text)
    assert result == set()  # FakeFunc not in headings


def test_extract_removal_targets_dotted_no_backtick():
    """Dotted CamelCase names extracted even without backticks."""
    issues = ["CLOSEINSPECTORUTIL.IsValidTarget is not found in the Lua source"]
    batch_text = "### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`\ncontent\n"
    result = _extract_removal_targets(issues, batch_text)
    assert "CLOSEINSPECTORUTIL.IsValidTarget" in result


def test_extract_removal_targets_camelcase_fallback():
    """CamelCase last-resort fallback when no backtick or dotted names."""
    issues = ["GetOwner is hallucinated"]
    batch_text = "### `GetOwner(inst)`\ncontent\n"
    result = _extract_removal_targets(issues, batch_text)
    assert "GetOwner" in result


# ── Task 4: _enforce_removals ─────────────────────────────────────────────────

from validator.content.chunked import _enforce_removals


def test_enforce_removals_deletes_hallucinated():
    """Removes function blocks flagged as hallucinated."""
    batch_text = (
        "### `RealFunc(x)`\n* **Description:** real\n\n"
        "### `FakeFunc(y)`\n* **Description:** fake\n\n"
        "### `AnotherReal(z)`\n* **Description:** another\n"
    )
    issues = ["`FakeFunc` does not exist in the Lua source"]
    result = _enforce_removals(batch_text, issues)
    assert "### `RealFunc(x)`" in result
    assert "### `FakeFunc(y)`" not in result
    assert "### `AnotherReal(z)`" in result


def test_enforce_removals_no_targets():
    """No hallucination issues → text unchanged."""
    batch_text = "### `Foo(x)`\ncontent\n"
    issues = ["Wrong parameter type"]
    result = _enforce_removals(batch_text, issues)
    assert result == batch_text


def test_enforce_removals_already_removed():
    """Function already absent → text unchanged."""
    batch_text = "### `Foo(x)`\ncontent\n"
    issues = ["`Bar` does not exist in the Lua source"]
    result = _enforce_removals(batch_text, issues)
    assert result == batch_text


# ── Task 5: _validate_patch_scope ─────────────────────────────────────────────

from validator.content.chunked import _validate_patch_scope
from validator.content.writer import Patch


def test_validate_patch_scope_rejects_heading_deletion():
    """Patch that deletes a ### heading without removal reason is rejected."""
    patches = [
        Patch(
            old_text="### `Foo(x)`\n* **Description:** foo\n",
            new_text="* **Description:** foo\n",
            reason="reformat entry",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 0


def test_validate_patch_scope_allows_heading_deletion_with_removal_reason():
    """Patch that deletes heading with 'remove' reason is allowed."""
    patches = [
        Patch(
            old_text="### `Foo(x)`\n* **Description:** foo\n",
            new_text="",
            reason="remove hallucinated function",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 1


def test_validate_patch_scope_rejects_nonstandard_fields():
    """Patch introducing non-standard field in Main functions is rejected."""
    patches = [
        Patch(
            old_text="* **Description:** old\n",
            new_text="* **Description:** new\n* **Note:** extra info\n",
            reason="add note",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 0


def test_validate_patch_scope_allows_standard_fields():
    """Patch using standard fields (Description, Parameters, Returns, Error states) is allowed."""
    patches = [
        Patch(
            old_text="* **Description:** old\n",
            new_text="* **Description:** new\n* **Returns:** value\n",
            reason="fix return",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 1


def test_validate_patch_scope_skips_field_check_for_non_main():
    """Non-Main-functions sections do not check for standard fields."""
    patches = [
        Patch(
            old_text="**External dependencies:** none\n",
            new_text="**External dependencies:** math\n* **Components used:** none\n",
            reason="add deps",
        )
    ]
    result = _validate_patch_scope(patches, "## Dependencies & tags")
    assert len(result) == 1


def test_validate_patch_scope_allows_normal_patches():
    """Normal patches that don't touch headings or add fields pass through."""
    patches = [
        Patch(
            old_text="* **Description:** wrong desc\n",
            new_text="* **Description:** correct desc\n",
            reason="fix description",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 1


# ── Task 10: Integration tests for guards in action ───────────────────────────

@patch("validator.content.chunked.SECTION_TOKEN_THRESHOLD", 1)
@patch("validator.content.chunked.BATCH_TOKEN_LIMIT", 5000)
def test_guard2_removes_hallucinated_fn(tmp_path):
    """Guard 2: hallucinated function flagged by reviewer is auto-removed even if writer fails."""
    md_content = (
        "---\ntitle: Test\n---\n## Main functions\n\n"
        + _make_fn_block("RealFunc")
        + _make_fn_block("HallucinatedFunc")
    )
    lua_content = "function RealFunc(arg) end\n"
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(md_content, encoding="utf-8")
    lua_path.write_text(lua_content, encoding="utf-8")

    call_count = 0
    def _mock_chat(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Reviewer flags HallucinatedFunc
            return _rejected(["`HallucinatedFunc` does not exist in the Lua source"])
        if call_count == 2:
            # Writer returns empty patches (fails to delete)
            return _no_patches()
        return _approved()

    with patch("validator.content.chunked.ollama_chat", side_effect=_mock_chat):
        run_chunked_content_loop(str(md_path), str(lua_path), _config(max_iterations=3))

    result_md = md_path.read_text(encoding="utf-8")
    assert "### `RealFunc(arg)`" in result_md
    assert "HallucinatedFunc" not in result_md


@patch("validator.content.chunked.SECTION_TOKEN_THRESHOLD", 1)
@patch("validator.content.chunked.BATCH_TOKEN_LIMIT", 5000)
def test_guard3_rejects_heading_deleting_patch(tmp_path):
    """Guard 3: patch that deletes a heading without removal reason is rejected."""
    md_content = (
        "---\ntitle: Test\n---\n## Main functions\n\n"
        + _make_fn_block("Foo")
        + _make_fn_block("Bar")
    )
    lua_content = "function Foo(arg) end\nfunction Bar(arg) end\n"
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(md_content, encoding="utf-8")
    lua_path.write_text(lua_content, encoding="utf-8")

    original_block = _make_fn_block("Bar")
    call_count = 0
    def _mock_chat(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _rejected(["Wrong description for Bar"])
        if call_count == 2:
            # Writer tries to delete Bar heading (no removal reason)
            body = json.dumps([{
                "old_text": original_block,
                "new_text": "* **Description:** bar fixed\n",
                "reason": "reformat entry",
            }])
            return {"message": {"content": body}}
        return _approved()

    with patch("validator.content.chunked.ollama_chat", side_effect=_mock_chat):
        run_chunked_content_loop(str(md_path), str(lua_path), _config(max_iterations=3))

    result_md = md_path.read_text(encoding="utf-8")
    # Bar heading should still exist (guard rejected the patch)
    assert "### `Bar(arg)`" in result_md
