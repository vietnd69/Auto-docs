"""Interrupted final review must preserve the draft and original attempt evidence."""

import json

import pytest

from harness import checkpoint, final_review, session
from harness.pages import get_plan
from harness.runner import run_page
from harness.tools import api
from test_opencode_runner import make_opencode
from test_pages_checks import fill


def record_reads(ws, page_id, job_id):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HARNESS_REVIEW_ONLY", "1")
        patch.setenv("HARNESS_REVIEW_PAGE", page_id)
        patch.setenv("HARNESS_JOB", job_id)
        api.doc_read(page_id)
        for source in get_plan(ws).page(page_id).sources:
            api.lua_read(source.file, 1, 10000)


def interrupt(planned, monkeypatch, tmp_path):
    make_opencode(planned.settings.root)
    page = fill(planned)

    def agent(ws, job, role, prompt, log_name, project):
        log = ws.report_path(f"sessions/{log_name}.jsonl")
        log.write_text('{"type":"step"}', encoding="utf-8")
        return session.SessionResult(-1, True, log)

    monkeypatch.setattr(session, "run_agent", agent)
    result = tmp_path / "first.json"
    run_page(planned, page.id, tree=None, result_path=result, events_path=None, publish_page=False)
    return page, result


def test_resume_reviews_existing_draft_and_preserves_attempt(planned, no_mdx, monkeypatch, tmp_path):
    page, original_result = interrupt(planned, monkeypatch, tmp_path)
    original = original_result.read_bytes()
    before = planned.draft_path(page.path).read_bytes()
    first = json.loads(original)

    def review(ws, job, role, prompt, log_name, project):
        assert role == "reviewer"
        assert job.kind == "resume-review"
        assert "do not restart doc-job" in prompt
        assert "ledger_list" in prompt and "current draft" in prompt
        assert ws.draft_path(page.path).read_bytes() == before
        record_reads(ws, page.id, job.id)
        receipt = final_review.finish(ws, page.id, job.id, "Checked current draft and source")
        assert "REVIEW_COMPLETE" in receipt
        log = ws.report_path(f"sessions/{log_name}.jsonl")
        log.write_text('{"type":"step"}', encoding="utf-8")
        return session.SessionResult(0, False, log)

    monkeypatch.setattr(session, "run_agent", review)
    result = tmp_path / "resumed.json"
    status, _ = run_page(planned, page.id, tree=None, result_path=result,
                         events_path=None, publish_page=False, resume_review=True)
    assert status == "PASS"
    resumed = json.loads(result.read_text())
    assert resumed["resumed_from"] == first["job_id"]
    assert resumed["job_id"] != first["job_id"]
    assert original_result.read_bytes() == original
    assert planned.draft_path(page.path).read_bytes() == before
    old_execution = planned.report_path(f"attempts/{first['job_id']}/execution.json")
    assert json.loads(old_execution.read_text())["reason"] == "timeout"


@pytest.mark.parametrize("changed", ["draft", "ledger", "plan", "skill", "missing"])
def test_resume_rejects_changed_state_before_model_call(
    planned, no_mdx, monkeypatch, tmp_path, changed
):
    page, _ = interrupt(planned, monkeypatch, tmp_path)
    paths = {
        "draft": planned.draft_path(page.path),
        "ledger": planned.ledger_path(page.id),
        "plan": planned.plan_path,
        "skill": planned.settings.root / ".opencode/harness/systemprompt.md",
    }
    if changed == "missing":
        checkpoint.checkpoint_path(planned, page.id).unlink()
    else:
        path = paths[changed]
        path.write_bytes((path.read_bytes() if path.exists() else b"") + b"\n")

    def forbidden(*args):
        pytest.fail("Resume validation must fail before model calls")

    monkeypatch.setattr(session, "run_agent", forbidden)
    with pytest.raises(ValueError, match="checkpoint"):
        run_page(planned, page.id, tree=None, result_path=None,
                 events_path=None, publish_page=False, resume_review=True)


def test_failed_resume_keeps_open_findings(planned, no_mdx, monkeypatch, tmp_path):
    page, _ = interrupt(planned, monkeypatch, tmp_path)
    # A clean draft alone must not auto-close an evidenced finding.
    from harness.ledger import Evidence, Ledger

    source = get_plan(planned).page(page.id).sources[0].file
    quote = planned.git.show(planned.rev, source).splitlines()[0]
    ledger = Ledger(planned, page.id)
    ledger.add("example", "example", "Needs manual verification", Evidence(source, 1, 1, quote))
    checkpoint.save_checkpoint(
        planned, page.id, planned.settings.root / ".opencode/harness", "with-finding"
    )
    status, _ = run_page(planned, page.id, tree=None, result_path=None,
                         events_path=None, publish_page=False, resume_review=True)
    assert status == "BUDGET_EXHAUSTED"
    assert any(f.status == "open" for f in Ledger(planned, page.id).items.values())


def test_clean_exit_without_review_receipt_is_not_pass(planned, no_mdx, monkeypatch, tmp_path):
    page, _ = interrupt(planned, monkeypatch, tmp_path)
    def agent(ws, job, role, prompt, log_name, project):
        log = ws.report_path(f"sessions/{log_name}.jsonl")
        log.write_text('{"type":"step"}', encoding="utf-8")
        return session.SessionResult(0, False, log)
    monkeypatch.setattr(session, "run_agent", agent)
    status, _ = run_page(planned, page.id, tree=None, result_path=None,
                         events_path=None, publish_page=False, resume_review=True)
    assert status == "REVIEW_INCOMPLETE"


def test_review_receipt_invalidated_by_draft_or_ledger_change(planned, no_mdx):
    page = fill(planned)
    record_reads(planned, page.id, "review")
    assert "REVIEW_COMPLETE" in final_review.finish(planned, page.id, "review", "Source and example checked")
    assert final_review.completed(planned, page.id, "review")
    assert not final_review.completed(planned, page.id, "different-job")
    planned.ledger_path(page.id).write_text("\n", encoding="utf-8")
    assert not final_review.completed(planned, page.id, "review")
    assert "REVIEW_COMPLETE" in final_review.finish(planned, page.id, "review", "Checked updated ledger")
    path = planned.draft_path(page.path)
    path.write_text(path.read_text(encoding="utf-8") + "\nChanged", encoding="utf-8")
    assert not final_review.completed(planned, page.id, "review")


def test_review_runtime_caps_and_readonly_tools(planned, monkeypatch):
    from harness.jobqueue import Job
    from harness.tools import api

    job = Job("bounded-review", "resume-review", "components/health")
    env = session.session_env(planned, job)
    config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    reviewer = config["agent"]["harness-final-review"]
    assert reviewer["mode"] == "primary"
    assert reviewer["steps"] == 24
    assert env["HARNESS_MAX_STEPS"] == "24"
    assert reviewer["tools"]["*"] is False
    assert reviewer["tools"]["dst-tools_review_finish"] is True
    assert "task" not in reviewer["tools"]
    monkeypatch.setenv("HARNESS_REVIEW_ONLY", "1")
    assert "Read-only" in api.doc_write_section(job.page_id, "## Overview", "overwrite")
    assert "Read-only" in api.doc_set_meta(job.page_id, "overwrite")
    assert "only available" in api.review_finish("wrong/page", "fake")


def test_review_session_has_short_timeout(planned, monkeypatch):
    from types import SimpleNamespace

    from harness.jobqueue import Job

    policy = planned.settings.root / ".opencode/harness/skills/review-symbols/SKILL.md"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("Frozen review policy sentinel", encoding="utf-8")
    monkeypatch.setattr(session, "opencode_bin", lambda ws: "offline-opencode")
    def run(argv, **kwargs):
        assert "Frozen review policy sentinel" in argv[2]
        assert argv[argv.index("--agent") + 1] == "harness-final-review"
        assert kwargs["timeout"] == 120
        assert kwargs["env"]["HARNESS_MAX_STEPS"] == "24"
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(session.subprocess, "run", run)
    result = session.run_agent(planned, Job("review", "resume-review", "components/health"),
                               "reviewer", "review", "review")
    assert result.returncode == 0
    receipt = json.loads(planned.report_path("review-policy/review.json").read_text())
    assert receipt["loaded_by"] == "controller"
    assert len(receipt["skill_sha256"]) == 64


def test_receipt_requires_actual_full_reads(planned, no_mdx, monkeypatch):
    page = fill(planned)
    monkeypatch.setenv("HARNESS_REVIEW_ONLY", "1")
    monkeypatch.setenv("HARNESS_REVIEW_PAGE", page.id)
    monkeypatch.setenv("HARNESS_JOB", "coverage")
    source = page.sources[0].file
    assert "coverage incomplete" in final_review.finish(planned, page.id, "coverage", "All checked")
    api.doc_read(page.id)
    api.lua_outline(source)
    api.lua_grep("Health", source)
    api.lua_symbol(source, "missing-symbol")
    api.lua_read(source, 1, 1)
    assert "unread lines" in final_review.finish(planned, page.id, "coverage", "All checked")
    with pytest.raises(ValueError, match="canonical page_id"):
        api.notes_read("page-components__health-job")
    record_reads(planned, page.id, "coverage")
    assert "REVIEW_COMPLETE" in final_review.finish(planned, page.id, "coverage", "All checked")
    path = planned.draft_path(page.path)
    path.write_text(path.read_text(encoding="utf-8") + "\nChanged", encoding="utf-8")
    assert not final_review.completed(planned, page.id, "coverage")
    assert "full current draft" in final_review.finish(planned, page.id, "coverage", "All checked")


def test_wrong_revision_and_truncated_reads_do_not_complete(planned, no_mdx, monkeypatch):
    from helpers import git
    page = fill(planned)
    monkeypatch.setenv("HARNESS_REVIEW_ONLY", "1")
    monkeypatch.setenv("HARNESS_REVIEW_PAGE", page.id)
    monkeypatch.setenv("HARNESS_JOB", "coverage")
    api.doc_read(page.id)
    pinned = planned.git.rev_parse(planned.rev)
    source = page.sources[0].file
    git(planned.settings.scripts_dir, "commit", "--allow-empty", "-m", "new revision")
    from dataclasses import replace
    planned = replace(planned, rev=pinned)
    api.use_workspace(planned)
    api.lua_read(source, 1, 10000, "HEAD")
    assert "unread lines" in final_review.finish(planned, page.id, "coverage", "All checked")
    planned.settings.values["read_max_tokens"] = 8
    api.lua_read(source, 1, 10000)
    assert "unread lines" in final_review.finish(planned, page.id, "coverage", "All checked")
