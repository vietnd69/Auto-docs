from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from harness import cli, mcp_server, session
from harness.syncstate import SyncState
from harness.workspace import Workspace
from helpers import git
from test_opencode_runner import fake_agent, make_opencode
from test_update_flow import make_update


@pytest.fixture()
def run_cli(ws: Workspace, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    real = cli.make_workspace
    monkeypatch.setattr(cli, "make_workspace", lambda *args, **kw: real(*args, **kw) if args else ws)

    def call(*argv: str) -> int:
        return cli.main(list(argv))

    return call


def test_plan_index_status_builds_page(run_cli, ws: Workspace, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("index") == 0
    assert run_cli("plan") == 0 and "0 issues" in capsys.readouterr().out
    assert run_cli("plan") == 1  # refuses to overwrite without --force
    assert run_cli("plan", "--force") == 0
    assert run_cli("status") == 0 and "(baseline)" in capsys.readouterr().out
    assert run_cli("builds") == 0 and "759671" in capsys.readouterr().out
    assert run_cli("page", "checklist", "components/health") == 0
    make_opencode(ws.settings.root)
    assert run_cli("memory") == 0
    assert run_cli("sync-opencode") == 0


def test_generate_and_update(
    run_cli, ws: Workspace, no_mdx: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(session, "run_agent", fake_agent)
    ws.settings.values["reflect"] = 0
    assert run_cli("plan") == 0
    assert run_cli("generate", "--prefix", "components/health", "--parallel", "1") == 0
    assert "components/health" in SyncState(ws).pages
    old, new = make_update(ws)
    assert run_cli("update", "--dry-run") == 0 and "files changed" in capsys.readouterr().out
    code = run_cli("update", "--parallel", "1")
    assert code == 2  # some updated pages FAIL with the fake agent
    changelog = ws.settings.path("changelog_file")
    assert "## Build 760500" in changelog.read_text(encoding="utf-8")
    assert run_cli("update") == 0 or SyncState(ws).head == new
    assert git(ws.settings.scripts_dir, "rev-parse", "HEAD") == new and old != new


def test_run_page_and_improve(
    run_cli, ws: Workspace, no_mdx: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(session, "run_agent", fake_agent)
    assert run_cli("plan") == 0
    assert (
        run_cli(
            "run-page",
            "components/health",
            "--state-dir",
            str(tmp_path / "s"),
            "--result",
            str(tmp_path / "r.json"),
        )
        == 0
    )
    assert (tmp_path / "r.json").exists()
    assert run_cli("improve", "components/health") == 1  # harness2 not installed
    assert run_cli("improve", "--promote", "brain") == 1


def test_mcp_server_registers_tools_and_reports_errors(ws: Workspace) -> None:
    server = mcp_server.build_server()
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == set(mcp_server.TOOLS)
    assert all(t.description for t in tools)
    wrapped = mcp_server._safe(lambda: (_ for _ in ()).throw(ValueError("boom")))
    assert wrapped() == "ERROR ValueError: boom"
