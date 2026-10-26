import json
from types import SimpleNamespace

import pytest

from harness import session, subscription
from harness.jobqueue import Job


def test_subscription_env_drops_paid_credentials_and_preserves_login_home():
    env = {"ANTHROPIC_API_KEY": "secret", "OPENAI_API_KEY": "secret",
           "ANTHROPIC_AUTH_TOKEN": "secret", "CLAUDE_CODE_USE_BEDROCK": "1",
           "DEEPSEEK_API_KEY": "secret", "OLLAMA_API_KEY": "secret", "ACCOUNT_1": "secret",
           "OPENAI_BASE_URL": "https://proxy", "CODEX_HOME": "native-login",
           "HARNESS_JOB": "review", "PATH": "bin", "CLAUDECODE": "1"}
    safe = subscription.clean_env(env)
    assert safe == {"CODEX_HOME": "native-login", "HARNESS_JOB": "review", "PATH": "bin"}


@pytest.mark.parametrize("backend", ["claude-code", "codex"])
def test_native_commands_only_expose_review_mcp(ws, tmp_path, monkeypatch, backend):
    monkeypatch.setattr(subscription, "executable", lambda *args: "native-cli")
    env = session.session_env(ws, Job("j", "resume-review", "components/health"))
    command = subscription.command(ws.settings, backend, subscription.clean_env(env), tmp_path)
    assert "--model" not in command  # Do not hardcode an unsupported subscription model.
    assert "dangerously" not in " ".join(command)
    if backend == "claude-code":
        config = json.loads((tmp_path / "mcp.json").read_text())
        assert config["mcpServers"]["dst_tools"]["env"]["HARNESS_REVIEW_ONLY"] == "1"
        assert "mcp__dst_tools__doc_read" in " ".join(command)
        assert "mcp__dst_tools__doc_write_section" not in " ".join(command)
        assert command[command.index("--tools") + 1] == ""
        assert "--strict-mcp-config" in command
    else:
        assert 'forced_login_method="chatgpt"' in command
        assert "features.shell_tool=false" in command
        assert "--ignore-user-config" in command
        assert "read-only" in command
        assert 'mcp_servers.dst_tools.tools.doc_read.approval_mode="approve"' in command
        assert not any("doc_write_section.approval_mode" in item for item in command)
        assert any('enabled_tools=' in item and 'doc_read' in item for item in command)


def test_requested_subscription_efforts(ws, tmp_path, monkeypatch):
    monkeypatch.setattr(subscription, "executable", lambda *args: "native-cli")
    env = session.session_env(ws, Job("j", "resume-review", "components/health"))
    ws.settings.values.update(codex_subscription_model="gpt-6.1-sol", codex_subscription_effort="medium",
                              claude_subscription_model="sonnet", claude_subscription_effort="high")
    codex = subscription.command(ws.settings, "codex", env, tmp_path)
    claude = subscription.command(ws.settings, "claude-code", env, tmp_path)
    assert 'model_reasoning_effort="medium"' in codex
    assert codex[codex.index("--model") + 1] == "gpt-6.1-sol"
    assert claude[claude.index("--effort") + 1] == "high"
    assert claude[claude.index("--model") + 1] == "sonnet"


@pytest.mark.parametrize("backend,stdout,stderr,ready", [
    ("claude-code", '{"loggedIn":true,"authMethod":"claude.ai","subscriptionType":"max"}', "", True),
    ("claude-code", '{"loggedIn":true,"authMethod":"api_key"}', "", False),
    ("claude-code", '{"loggedIn":false}', "", False),
    ("codex", "", "Logged in using ChatGPT", True),
    ("codex", "", "Logged in using an API key", False),
])
def test_auth_requires_subscription(ws, monkeypatch, backend, stdout, stderr, ready):
    monkeypatch.setattr(subscription, "executable", lambda *args: "native-cli")
    monkeypatch.setattr(subscription.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr))
    assert subscription.auth_status(ws.settings, backend)["subscription_login"] is ready


@pytest.mark.parametrize("backend,event,ok", [
    ("claude-code", {"type": "result", "subtype": "success", "is_error": False,
                     "total_cost_usd": 0.1, "usage": {"input_tokens": 10}}, True),
    ("claude-code", {"type": "result", "subtype": "error_max_turns", "is_error": True}, False),
    ("codex", {"type": "turn.completed", "usage": {"input_tokens": 10}}, True),
    ("codex", {"type": "turn.failed", "error": {"message": "quota exceeded"}}, False),
    ("codex", {"type": "thread.started"}, False),
])
def test_terminal_event_and_subscription_usage(tmp_path, backend, event, ok):
    raw, log = tmp_path / "raw.jsonl", tmp_path / "events.jsonl"
    raw.write_text(json.dumps(event), encoding="utf-8")
    record = subscription.normalize(raw, log, backend, 0, False)
    assert record["completed"] is ok
    assert record["cost_usd"] is None
    assert record["billing_mode"] == "subscription"
    assert session.has_error_event(log) is not ok
    assert not subscription.normalize(raw, log, backend, -1, True)["completed"]


def test_native_dispatch_preserves_controller_skill_and_existing_guards(planned, monkeypatch):
    policy = planned.settings.root / ".opencode/harness/skills/review-symbols/SKILL.md"
    policy.parent.mkdir(parents=True)
    policy.write_text("Frozen subscription policy", encoding="utf-8")
    planned.settings.values["final_review_backend"] = "codex"
    seen = []
    def run(ws, job, prompt, log, env, backend):
        seen.append(backend)
        assert "Frozen subscription policy" in prompt
        assert env["HARNESS_REVIEW_ONLY"] == "1"
        assert env["HARNESS_REVIEW_PAGE"] == job.page_id
        return session.SessionResult(0, False, log)
    monkeypatch.setattr(subscription, "run_review", run)
    session.run_agent(planned, Job("j", "resume-review", "components/health"),
                      "reviewer", "Review", "j")
    assert seen == ["codex"]


def test_missing_login_fails_before_model_or_fallback(ws, monkeypatch):
    monkeypatch.setattr(subscription, "auth_status", lambda *a:
                        {"subscription_login": False, "login_command": "codex login"})
    monkeypatch.setattr(subscription, "command", lambda *a: pytest.fail("No model call allowed"))
    with pytest.raises(ValueError, match="No API fallback"):
        subscription.run_review(ws, Job("j", "resume-review", "components/health"),
                                "review", ws.report_path("sessions/j.jsonl"), {}, "codex")


def test_native_mcp_has_no_document_mutators(monkeypatch):
    import asyncio

    from harness.mcp_server import build_server

    monkeypatch.setenv("HARNESS_NATIVE_REVIEW", "1")
    with pytest.raises(ValueError, match="read-only"):
        build_server()
    monkeypatch.setenv("HARNESS_REVIEW_ONLY", "1")
    names = {tool.name for tool in asyncio.run(build_server().list_tools())}
    assert names == set(subscription.REVIEW_TOOLS)
    assert "review_finish" in names and "doc_read" in names
    assert "doc_write_section" not in names and "plan_put" not in names


def test_repair_writer_is_scoped_and_cannot_close_findings(planned, monkeypatch):
    from harness.tools import api

    monkeypatch.setenv("HARNESS_NATIVE_MODE", "repair")
    monkeypatch.setenv("HARNESS_REPAIR_PAGE", "components/health")
    allowed = subscription.native_tools(dict(__import__("os").environ))
    assert "doc_write_section" in allowed
    assert not {"ledger_resolve", "ledger_add", "review_finish", "plan_put"} & set(allowed)
    with pytest.raises(ValueError, match="independent review"):
        api.ledger_resolve("components/health", "finding", "fixed")
    with pytest.raises(ValueError, match="confined"):
        api.doc_write_section("components/other", "## Overview", "changed")
    for check in (api.run_checks_tool, api.verdict):
        with pytest.raises(ValueError, match="confined"):
            check("components/other")


def test_native_modes_fail_closed():
    with pytest.raises(ValueError, match="Unknown"):
        subscription.native_tools({"HARNESS_NATIVE_MODE": "anything"})
    with pytest.raises(ValueError, match="scoped"):
        subscription.native_tools({"HARNESS_NATIVE_MODE": "repair"})
    tools = subscription.native_tools({"HARNESS_NATIVE_MODE": "proposal", "HARNESS_REVIEW_ONLY": "1"})
    assert not {"doc_write_section", "ledger_resolve", "review_finish"} & set(tools)


@pytest.mark.parametrize("timed_out", [False, True])
def test_native_process_streams_prompt_and_records_outcome(ws, monkeypatch, timed_out):
    import subprocess

    monkeypatch.setattr(subscription, "auth_status", lambda *a: {"subscription_login": True})
    monkeypatch.setattr(subscription, "command", lambda *a: ["native-cli"])
    def run(argv, **kwargs):
        assert argv == ["native-cli"]
        assert kwargs["input"] == "mcp__dst_tools__doc_read"
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert kwargs["timeout"] == 120
        if timed_out:
            raise subprocess.TimeoutExpired(argv, 120)
        kwargs["stdout"].write('{"type":"turn.completed","usage":{"input_tokens":12}}\n')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subscription.subprocess, "run", run)
    result = subscription.run_review(ws, Job("j", "resume-review", "components/health"),
                                     "dst-tools_doc_read", ws.report_path("sessions/j.jsonl"),
                                     {"OPENAI_API_KEY": "do-not-use"}, "codex")
    assert result.timed_out is timed_out
    assert session.has_error_event(result.log_path) is timed_out
