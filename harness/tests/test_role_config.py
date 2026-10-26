from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import session
from harness.config import load_settings
from harness.jobqueue import Job
from harness.role_config import credentials, role_models
from harness.runner import _reflect
from harness.verdict import Verdict
from harness.workspace import Workspace, make_workspace


def test_session_routes_all_roles_and_loads_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    (tmp_path / ".env").write_text("CLAUDE_API_KEY=test-secret\n", encoding="utf-8")
    cfg = load_settings(tmp_path)
    env = session.session_env(make_workspace(cfg), Job("j", "generate", "components/health"))
    assert env["ANTHROPIC_API_KEY"] == "test-secret"
    config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert config["agent"]["writer"]["model"] == "deepseek/deepseek-flash"
    assert config["agent"]["reviewer"]["model"] == "dst-proxy/reviewer"
    assert config["agent"]["orchestrator"]["model"] == "deepseek/deepseek-flash"
    assert role_models(cfg)["writer-escalation"].startswith("anthropic/")
    assert config["agent"]["planner"]["model"] == "dst-proxy/planner"
    assert "test-secret" not in env["OPENCODE_CONFIG_CONTENT"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "environment-wins")
    assert credentials(cfg)["ANTHROPIC_API_KEY"] == "environment-wins"


def test_reflection_error_event_is_deferred_even_with_exit_zero(
    planned: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = planned.report_path("reflection.jsonl")
    log.write_text('{"type": "error", "error": {"message": "quota"}}\n', encoding="utf-8")
    monkeypatch.setattr(session, "run_agent", lambda *a: session.SessionResult(0, False, log))
    _reflect(planned, Job("j", "generate", "components/health"), Verdict("components/health", "PASS"))
    assert planned.report_path("deferred-reflections/j.json").exists()


def test_reflection_exception_does_not_escape(planned: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object) -> None:
        raise OSError("cannot start")

    monkeypatch.setattr(session, "run_agent", broken)
    _reflect(planned, Job("j", "generate", "components/health"), Verdict("components/health", "PASS"))
    assert planned.report_path("deferred-reflections/j.json").exists()
