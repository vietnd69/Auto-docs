"""Drive jobs: session, independent verdict, publish/escalate, then reflect."""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from harness import checkpoint, final_review, session
from harness.config import Settings
from harness.jobqueue import Job, JobQueue
from harness.opencode_sync import materialise, tree_dir
from harness.pages import get_plan
from harness.plan import require_executable
from harness.verdict import BUDGET_EXHAUSTED, PASS, Verdict, evaluate, publish
from harness.workspace import Workspace, make_workspace


@dataclass
class RunOptions:
    build: str
    publish: bool = True
    reflect: bool = True
    escalate: bool = False
    project_dir: Path | None = None


def _reflect(ws: Workspace, job: Job, verdict: Verdict) -> None:
    prompt = (
        f"Reflect on job {job.id} ({job.kind} {job.page_id}). Final verdict:\n{verdict.render()}\n"
        "Read the page ledger and notes, then record at most 3 reusable lessons with memory_add."
    )
    reason = "session failed or returned an error event"
    try:
        result = session.run_agent(ws, job, "reflector", prompt, f"{job.id}-reflect")
        text = result.log_path.read_text(encoding="utf-8", errors="replace")
        if not result.timed_out and result.returncode == 0 and '"type":"error"' not in text.replace(" ", ""):
            return
    except Exception as exc:  # reflection must not turn an already published PASS into ERROR
        reason = type(exc).__name__  # do not persist provider errors that might contain credentials
    ws.report_path(f"deferred-reflections/{job.id}.json").write_text(
        json.dumps({"job": job.id, "page_id": job.page_id, "prompt": prompt, "reason": reason}),
        encoding="utf-8",
    )


def run_job(ws: Workspace, job: Job, opts: RunOptions) -> tuple[str, str]:
    """Execute one job and return (status, message)."""
    job_ws = make_workspace(ws.settings, job.to_rev or ws.rev)
    plan = get_plan(job_ws)
    require_executable(plan)
    page = plan.page(job.page_id)
    prompt = session.job_prompt(job, page)
    execution_path = job_ws.report_path(f"execution/{job.id}.json")
    execution = {"completed": False, "reason": "running"}
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    try:
        role = "reviewer" if job.kind == "resume-review" else "orchestrator"
        result = session.run_agent(job_ws, job, role, prompt, job.id, opts.project_dir)
    except Exception:
        execution_path.write_text(
            json.dumps({"completed": False, "reason": "launch_or_runtime_exception"}), encoding="utf-8"
        )
        raise
    marker = job_ws.settings.root / ".harness" / "reports" / "budget" / f"{job.id.replace('/', '__')}.json"
    budget_stop = session.budget_hit(result.log_path, marker)
    error_event = session.has_error_event(result.log_path)
    reason = (
        "timeout" if result.timed_out else
        "budget_stop" if budget_stop else
        "process_error" if result.returncode != 0 else
        "error_event_or_missing_log" if error_event else "completed"
    )
    execution = {
        "completed": reason == "completed", "reason": reason,
        "returncode": result.returncode, "timed_out": result.timed_out,
        "budget_stop": budget_stop, "error_event_or_missing_log": error_event,
    }
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    verdict = evaluate(job_ws, plan, page)
    status = verdict.status
    if result.timed_out or budget_stop:
        status = BUDGET_EXHAUSTED
    elif not execution["completed"]:
        status = "ERROR"
    if status == PASS and job.kind == "resume-review" and not final_review.completed(job_ws, page.id, job.id):
        status = "REVIEW_INCOMPLETE"
    if status == PASS and opts.publish:
        publish(job_ws, page, opts.build)
    elif status != PASS and opts.escalate:
        from harness.improve import escalate

        if escalate(job_ws, page):
            status = "ESCALATED"
    if opts.reflect and status not in (BUDGET_EXHAUSTED, "ERROR"):
        _reflect(job_ws, job, verdict)
    report = (
        verdict.render()
        if status == verdict.status
        else (f"{page.id}: {status}\nRuntime or final-review completion requirement was not met.\n"
              f"{verdict.render()}")
    )
    return status, report


def isolated_workspace(ws: Workspace, state_dir: Path) -> Workspace:
    """Same source and docs, separate state (drafts, ledger, notes); plan copied in."""
    values = dict(ws.settings.values, state_dir=str(state_dir.resolve()))
    iso = make_workspace(Settings(root=ws.settings.root, values=values), ws.rev)
    if not iso.plan_path.exists() and ws.plan_path.exists():
        shutil.copyfile(ws.plan_path, iso.plan_path)
    return iso


def candidate_project(ws: Workspace, tree: Path, target: Path) -> Path:
    """Copy of the OpenCode project whose editable harness tree is ``tree``."""
    source = ws.settings.root / ".opencode"
    if tree.resolve() == tree_dir(source).resolve():
        return ws.settings.root
    project = target / "oc-project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(source, project / ".opencode", ignore=shutil.ignore_patterns("node_modules", "harness"))
    shutil.copytree(tree, tree_dir(project / ".opencode"))
    materialise(project / ".opencode")
    return project


def run_page(
    ws: Workspace,
    page_id: str,
    *,
    tree: Path | None,
    result_path: Path | None,
    events_path: Path | None,
    publish_page: bool,
    resume_review: bool = False,
) -> tuple[str, str]:
    """One-off page job (``mod-harness run-page``), optionally with a candidate harness tree."""
    active_tree = tree or tree_dir(ws.settings.root / ".opencode")
    previous = checkpoint.validate_resume(ws, page_id, active_tree) if resume_review else None
    project = candidate_project(ws, tree, ws.settings.state_dir) if tree else None
    job = Job(
        id=f"page-{page_id.replace('/', '__')}-{uuid4().hex[:12]}",
        kind="resume-review" if resume_review else "generate", page_id=page_id, to_rev=ws.rev,
    )
    opts = RunOptions(ws.settings.get_str("baseline_build"), publish_page, False, False, project)
    try:
        status, report = run_job(ws, job, opts)
    finally:
        checkpoint.save_checkpoint(ws, page_id, active_tree, job.id)
    plan = get_plan(ws)
    verdict = evaluate(ws, plan, plan.page(page_id))
    if result_path is not None:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "page_id": page_id,
                    "job_id": job.id,
                    "resumed_from": previous["job_id"] if previous else None,
                    "checkpoint": str(checkpoint.checkpoint_path(ws, page_id)),
                    "execution": json.loads(
                        ws.report_path(f"execution/{job.id}.json").read_text(encoding="utf-8")
                    ),
                    "status": status,
                    "issues": len(verdict.issues),
                    "open_findings": len(verdict.open_findings),
                    "report": report,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        shutil.copyfile(result_path, ws.report_path(f"attempts/{job.id}/result.json"))
    log = ws.report_path(f"sessions/{job.id}.jsonl")
    if events_path is not None and log.exists():
        events_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(log, events_path)
    return status, report


def run_queue(ws: Workspace, queue: JobQueue, opts: RunOptions, parallel: int) -> dict[str, int]:
    """Run pending jobs with ``parallel`` workers until the queue is drained."""

    def worker() -> None:
        while (job := queue.claim()) is not None:
            try:
                status, message = run_job(ws, job, opts)
            except Exception as exc:  # one broken page must not stop the batch
                status, message = "ERROR", f"{type(exc).__name__}: {exc}"
            queue.finish(job.id, status, message)

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        for _ in range(max(1, parallel)):
            pool.submit(worker)
    return queue.counts()
