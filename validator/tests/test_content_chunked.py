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


def test_section_reviewer_prompt_contains_format_contract():
    system, user = build_section_reviewer_prompt("## Functions\n### `Foo(x)`\n* **Description:** x\n", "")
    combined = system + user
    assert "FORMAT CONTRACT" in combined or "REVIEW RULES" in combined
    assert "* **Description:**" in user


def test_section_writer_prompt_contains_format_rules():
    prompt = build_section_writer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n", "", [], []
    )
    assert "FORMAT RULES" in prompt
    assert "NEVER" in prompt
    assert "minimal substring" in prompt.lower() or "MINIMAL" in prompt


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
