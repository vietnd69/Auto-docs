from __future__ import annotations

import json
from pathlib import Path

from harness.jobqueue import Job, JobQueue
from harness.ledger import Evidence, Ledger
from harness.pages import get_plan
from harness.syncstate import SyncState
from harness.verdict import FAIL, PASS, evaluate, publish, remove_stale_pages, write_categories
from harness.workspace import Workspace
from test_pages_checks import fill


def test_evaluate_publish_and_categories(planned: Workspace, no_mdx: None) -> None:
    plan = get_plan(planned)
    page = plan.page("components/health")
    assert evaluate(planned, plan, page).status == FAIL  # no draft yet
    fill(planned)
    assert evaluate(planned, plan, page).status == PASS
    Ledger(planned, page.id).add(
        "Health:DoDelta", "returns", "x", Evidence("components/health.lua", 24, 24, "return amount")
    )
    verdict = evaluate(planned, plan, page)
    assert verdict.status == FAIL and "FINDING" in verdict.render()
    target = publish(planned, page, "759671")
    assert "build_version: '759671'" in target.read_text(encoding="utf-8")
    state = SyncState(planned)
    assert state.pages[page.id].path == "components/health.md"
    assert any(k.endswith("Health:DoDelta") for k in state.pages[page.id].symbols)
    assert write_categories(planned, plan) >= 2
    category = json.loads((planned.settings.docs_dir / "components" / "_category_.json").read_text())
    assert category["label"] == "Components"


def test_remove_stale_only_touches_harness_pages(planned: Workspace, no_mdx: None) -> None:
    plan = get_plan(planned)
    page = plan.page("components/health")
    fill(planned)
    publish(planned, page, "1")
    handwritten = planned.settings.docs_dir / "getting-started" / "intro.md"
    handwritten.parent.mkdir(parents=True)
    handwritten.write_text("# hi", encoding="utf-8")
    plan.pages = [p for p in plan.pages if p.id != page.id]
    assert remove_stale_pages(planned, plan) == ["components/health.md"]
    assert handwritten.exists()
    assert page.id not in SyncState(planned).pages


def test_job_queue_resume(tmp_path: Path) -> None:
    queue = JobQueue(tmp_path / "q.jsonl")
    assert queue.add(Job("a", "generate", "p1")) and not queue.add(Job("a", "generate", "p1"))
    queue.add(Job("b", "generate", "p2"))
    first = queue.claim()
    assert first is not None and first.status == "running"
    reloaded = JobQueue(tmp_path / "q.jsonl")  # crash while running → back to pending
    assert reloaded.counts() == {"pending": 2}
    job = reloaded.claim()
    assert job is not None
    reloaded.finish(job.id, "PASS", "ok")
    assert reloaded.counts() == {"PASS": 1, "pending": 1}
