from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.config import load_settings
from harness.tools import api
from harness.workspace import Workspace


def test_settings_toml_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config.toml").write_text('[harness]\nmodel = "x:cloud"\nmax_steps = 5\n', encoding="utf-8")
    monkeypatch.setenv("MOD_DOC_HARNESS_MAX_STEPS", "9")
    cfg = load_settings(tmp_path)
    assert cfg.get_str("model") == "x:cloud" and cfg.get_int("max_steps") == 9
    assert cfg.get_float("request_timeout") > 0 and cfg.docs_dir == tmp_path / "dst-api-webdocs" / "docs"


def test_source_tools(ws: Workspace) -> None:
    outline = api.lua_outline("components/health.lua")
    assert "* method        Health:DoDelta" in outline and "events pushed: healthdelta" in outline
    assert "21| " in api.lua_symbol("components/health.lua", "Health:DoDelta")
    assert "Similar: Health:DoDelta" in api.lua_symbol("components/health.lua", "DoDelta")
    assert api.lua_read("components/health.lua", 1, 2).startswith("-- components/health.lua L1-2")
    assert "DoDelta" in api.lua_grep("DoDelta")
    assert "definitions:" in api.lua_refs("Health:GetPercent")
    assert "no indexed dependencies" in api.lua_deps("components/health.lua")
    assert "table STRINGS" in api.lua_table_schema("strings_small.lua")


def test_lua_read_stops_at_budget(ws: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    ws.settings.values["read_max_tokens"] = 20
    assert "call lua_read again from" in api.lua_read("components/health.lua", 1, 999)


def test_plan_and_page_tools(planned: Workspace, no_mdx: None) -> None:
    assert "Lua files" in api.index_summary()
    assert "components/health" in api.plan_get(prefix="components/")
    page_json = api.plan_get("components/health")
    assert json.loads(page_json)["kind"] == "api"
    assert api.validate_plan_tool() == "plan valid"
    checklist = api.page_checklist("components/health")
    assert "[ ] ### `DoDelta(amount, overtime, cause)`" in checklist
    assert api.doc_write_section("components/health", "Bad", "x").startswith("heading must")
    api.doc_write_section("components/health", "### `DoDelta(amount, overtime, cause)`", "Body.")
    assert "[x] ### `DoDelta" in api.page_checklist("components/health")
    assert "Body." in api.doc_read("components/health", "### `DoDelta(amount, overtime, cause)`")
    assert "not found" in api.doc_read("components/health", "## Nope")
    assert api.doc_set_meta("components/health", "Health.", "a, b") == "frontmatter updated"
    assert "COVERAGE" in api.run_checks_tool("components/health")
    assert "FAIL" in api.verdict("components/health")
    assert api.notes_read("components/health") == "(no notes yet)"
    api.notes_write("components/health", "progress")
    assert api.notes_read("components/health") == "progress"
    msg = api.ledger_add(
        "components/health",
        "Health:DoDelta",
        "returns",
        "c",
        "components/health.lua",
        24,
        24,
        "return amount",
    )
    assert msg.startswith("opened")
    assert "open" in api.ledger_list("components/health")
    fid = msg.split()[-1]
    assert api.ledger_resolve("components/health", fid, "fixed").endswith("resolved")
    changed = json.loads(page_json)
    changed["title"] = "Health component"
    assert api.plan_put(json.dumps(changed)).startswith("saved components/health")
    assert "removed" in api.plan_remove("components/health")
    assert "UNCOVERED_FILE" in api.validate_plan_tool()


def test_build_memory_tools(planned: Workspace) -> None:
    assert api.build_list().startswith("759671")
    assert api.patch_notes("759671").startswith("Patch notes")
    head = planned.git.rev_parse("HEAD")
    assert "0 files changed" in api.diff_overview(head, head)
    assert "0 pages affected" in api.impact_map(head, head)
    assert api.memory_add("component", "cue words here", "lesson", "ev").startswith("added")
    assert "WHEN cue words" in api.memory_search("component", "cue words")
