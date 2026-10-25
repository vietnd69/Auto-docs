"""Drive jobs: session → independent verdict → publish / escalate → reflect."""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from harness import session
from harness.config import Settings
from harness.jobqueue import Job, JobQueue
from harness.opencode_sync import materialise, tree_dir
from harness.pages import get_plan
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
    session.run_agent(ws, job, "reflector", prompt, f"{job.id}-reflect")


def run_job(ws: Workspace, job: Job, opts: RunOptions) -> tuple[str, str]:
    """Execute one job and return (status, message)."""
    job_ws = make_workspace(ws.settings, job.to_rev or ws.rev)
    plan = get_plan(job_ws)
    page = plan.page(job.page_id)
    prompt = session.job_prompt(job, page)
    result = session.run_agent(job_ws, job, "orchestrator", prompt, job.id, opts.project_dir)
    verdict = evaluate(job_ws, plan, page)
    status = verdict.status
    marker = job_ws.settings.root / ".harness" / "reports" / "budget" / f"{job.id.replace('/', '__')}.json"
    if status != PASS and (result.timed_out or session.budget_hit(result.log_path, marker)):
        status = BUDGET_EXHAUSTED
    if status == PASS and opts.publish:
        publish(job_ws, page, opts.build)
    elif status != PASS and opts.escalate:
        from harness.improve import escalate

        if escalate(job_ws, page):
            status = "ESCALATED"
    if opts.reflect:
        _reflect(job_ws, job, verdict)
    return status, verdict.render()


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
) -> tuple[str, str]:
    """One-off page job (``mod-harness run-page``), optionally with a candidate harness tree."""
    project = candidate_project(ws, tree, ws.settings.state_dir) if tree else None
    job = Job(id=f"page-{page_id}".replace("/", "__"), kind="generate", page_id=page_id, to_rev=ws.rev)
    opts = RunOptions(ws.settings.get_str("baseline_build"), publish_page, False, False, project)
    status, report = run_job(ws, job, opts)
    plan = get_plan(ws)
    verdict = evaluate(ws, plan, plan.page(page_id))
    if result_path is not None:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "page_id": page_id,
                    "status": status,
                    "issues": len(verdict.issues),
                    "open_findings": len(verdict.open_findings),
                    "report": report,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
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
