"""OpenCode tree materialisation, session wiring, runner and improvement gate (no real LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import improve, session
from harness.jobqueue import Job, JobQueue
from harness.opencode_sync import materialise, replace_tree, restore_tree
from harness.pages import get_plan
from harness.runner import RunOptions, candidate_project, isolated_workspace, run_job, run_page, run_queue
from harness.syncstate import SyncState
from harness.workspace import Workspace
from test_pages_checks import fill


def make_opencode(root: Path) -> Path:
    oc = root / ".opencode"
    tree = oc / "harness"
    for rel, text in {
        "systemprompt.md": "sys",
        "guardrails.md": "- When x, load the `doc-job` skill.",
        "LongTermMEMORY.md": "memory",
        "tool_descriptions/tool_guidance.md": "tools",
        "skills/doc-job/SKILL.md": "---\nname: doc-job\ndescription: d\n---\n",
        "sub_agents/writer/AGENT.md": "---\nmode: subagent\ndescription: w\n---\n",
        "plugin/budget.ts": "export default async () => ({})",
        "scripts/README.md": "stub",
    }.items():
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (tree / rel).write_text(text, encoding="utf-8")
    (oc / "opencode.json").write_text(json.dumps({"instructions": []}), encoding="utf-8")
    return oc


def test_materialise_replace_restore(tmp_path: Path) -> None:
    oc = make_opencode(tmp_path)
    written = materialise(oc)
    assert sorted(written) == ["agent/writer.md", "plugin/budget.ts", "skills/doc-job/SKILL.md"]
    assert len(json.loads((oc / "opencode.json").read_text())["instructions"]) == 4
    candidate = tmp_path / "cand"
    candidate.mkdir()
    (candidate / "systemprompt.md").write_text("better", encoding="utf-8")
    (candidate / "LongTermMEMORY.md").write_text("candidate memory", encoding="utf-8")
    backup = replace_tree(oc, candidate)
    assert (oc / "harness" / "LongTermMEMORY.md").read_text() == "memory"  # memory is never replaced
    assert not (oc / "agent" / "writer.md").exists()  # stale generated file removed
    restore_tree(oc, backup)
    assert (oc / "agent" / "writer.md").exists()


def test_session_prompt_env_and_binaries(planned: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    page = get_plan(planned).page("components/health")
    job = Job("j1", "update", page.id, "aaa", "bbb")
    prompt = session.job_prompt(job, page)
    assert "components/health.lua" in prompt and "from `aaa` to `bbb`" in prompt
    env = session.session_env(planned, job)
    assert env["HARNESS_JOB"] == "j1" and env["MOD_DOC_HARNESS_REV"] == "bbb"
    assert env["MOD_DOC_HARNESS_STATE_DIR"] == str(planned.settings.state_dir)
    assert env["HARNESS_MCP_BIN"].endswith(("dst-tools-mcp", "dst-tools-mcp.exe"))
    monkeypatch.setattr(session.shutil, "which", lambda name: None)
    with pytest.raises(session.OpenCodeMissingError):
        session.opencode_bin(planned)
    log = planned.report_path("x.log")
    log.write_text("proxy said BUDGET_EXHAUSTED", encoding="utf-8")
    assert session.budget_hit(log) and not session.budget_hit(log.with_name("none.log"))


def fake_agent(
    ws: Workspace, job: Job, agent: str, prompt: str, log_name: str, project_dir: Path | None = None
) -> session.SessionResult:
    if agent == "orchestrator" and "health" in job.page_id:
        fill(ws, job.page_id)
    log = ws.report_path(f"sessions/{log_name}.jsonl")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('{"type":"step"}\n', encoding="utf-8")
    return session.SessionResult(0, False, log)


def test_run_queue_publishes_pass_and_records_fail(
    planned: Workspace, no_mdx: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session, "run_agent", fake_agent)
    queue = JobQueue(planned.queue_path("t"))
    queue.add(Job("ok", "generate", "components/health"))
    queue.add(Job("bad", "generate", "stategraphs/SGpig"))
    counts = run_queue(planned, queue, RunOptions("759671", reflect=True), parallel=2)
    assert counts == {"PASS": 1, "FAIL": 1}
    assert (planned.settings.docs_dir / "components" / "health.md").exists()
    assert "components/health" in SyncState(planned).pages


def test_budget_marker_turns_fail_into_budget_exhausted(
    planned: Workspace, no_mdx: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session, "run_agent", fake_agent)
    marker = planned.settings.root / ".harness" / "reports" / "budget" / "b.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")
    status, _ = run_job(planned, Job("b", "generate", "stategraphs/SGpig"), RunOptions("1", reflect=False))
    assert status == "BUDGET_EXHAUSTED"


def test_run_page_isolated_with_candidate_tree(
    planned: Workspace, no_mdx: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    make_opencode(planned.settings.root)
    seen: dict[str, Path | None] = {}

    def spy(
        ws: Workspace, job: Job, agent: str, prompt: str, log_name: str, project_dir: Path | None = None
    ) -> session.SessionResult:
        seen["project"] = project_dir
        return fake_agent(ws, job, agent, prompt, log_name, project_dir)

    monkeypatch.setattr(session, "run_agent", spy)
    iso = isolated_workspace(planned, tmp_path / "state")
    cand = tmp_path / "cand"
    (cand / "skills" / "doc-job").mkdir(parents=True)
    (cand / "systemprompt.md").write_text("x", encoding="utf-8")
    result, events = tmp_path / "out" / "result.json", tmp_path / "out" / "events.jsonl"
    status, _ = run_page(
        iso, "components/health", tree=cand, result_path=result, events_path=events, publish_page=False
    )
    assert status == "PASS" and json.loads(result.read_text())["status"] == "PASS"
    assert events.exists() and seen["project"] is not None
    assert (seen["project"] / ".opencode" / "harness" / "systemprompt.md").read_text() == "x"
    assert not (planned.settings.docs_dir / "components" / "health.md").exists()
    assert (
        candidate_project(planned, planned.settings.root / ".opencode" / "harness", tmp_path)
        == planned.settings.root
    )


def test_regression_gate_promotes_or_restores(
    planned: Workspace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    oc = make_opencode(planned.settings.root)
    materialise(oc)
    plan = get_plan(planned)
    assert improve.regression_pages(planned, plan, "component")
    cand = tmp_path / "cand"
    cand.mkdir()
    (cand / "systemprompt.md").write_text("candidate", encoding="utf-8")
    scores = iter([improve.Score(1, 3, 2), improve.Score(2, 1, 2)])
    monkeypatch.setattr(improve, "score_harness", lambda ws, pages, label: next(scores))
    assert improve.promote(planned, "component", str(cand)) == 0
    assert (oc / "harness" / "systemprompt.md").read_text() == "candidate"
    worse = iter([improve.Score(2, 0, 2), improve.Score(1, 0, 2)])
    monkeypatch.setattr(improve, "score_harness", lambda ws, pages, label: next(worse))
    other = tmp_path / "other"
    other.mkdir()
    (other / "systemprompt.md").write_text("worse", encoding="utf-8")
    assert improve.promote(planned, "component", str(other)) == 2
    assert (oc / "harness" / "systemprompt.md").read_text() == "candidate"
    assert len(planned.report_path("promotions.jsonl").read_text().splitlines()) == 2
    assert improve.promote(planned, "brain", "") == 1  # no candidate in library


def test_escalate_without_harness2_and_harvest(planned: Workspace, tmp_path: Path) -> None:
    page = get_plan(planned).page("components/health")
    assert improve.escalate(planned, page) is False  # harness2-dst venv missing
    adopted = (
        planned.settings.root / "harness2-dst" / "runs" / "x" / "harnesses" / "components__health" / "harness"
    )
    adopted.mkdir(parents=True)
    (adopted / "systemprompt.md").write_text("won", encoding="utf-8")
    target = improve.harvest(planned, page)
    assert target is not None and (target / "harness" / "systemprompt.md").exists()
