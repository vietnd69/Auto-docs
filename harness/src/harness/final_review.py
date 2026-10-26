"""Explicit completion receipt for a bounded, read-only final review."""

from __future__ import annotations

import hashlib
import json

from harness import review_evidence
from harness.file_transaction import atomic_write, file_transaction
from harness.pages import get_plan
from harness.verdict import evaluate
from harness.workspace import Workspace


def _snapshot(ws: Workspace, page_id: str) -> dict[str, str]:
    page = get_plan(ws).page(page_id)
    draft = ws.draft_path(page.path)
    ledger = ws.ledger_path(page_id)
    return {
        "page_id": page_id,
        "source_sha": ws.git.rev_parse(ws.rev),
        "draft_sha256": hashlib.sha256(draft.read_bytes()).hexdigest(),
        "ledger_sha256": hashlib.sha256(ledger.read_bytes() if ledger.exists() else b"").hexdigest(),
    }


def finish(ws: Workspace, page_id: str, job_id: str, summary: str) -> str:
    page = get_plan(ws).page(page_id)
    with file_transaction(ws.draft_path(page.path)), file_transaction(ws.ledger_path(page_id)):
        if not summary.strip():
            return "Review summary must state what was checked and any limits."
        missing = review_evidence.missing(ws, page_id, job_id)
        if missing:
            return "Review coverage incomplete:\n" + "\n".join(missing)
        plan = get_plan(ws)
        verdict = evaluate(ws, plan, plan.page(page_id))
        if verdict.status != "PASS":
            return "Review is not complete:\n" + verdict.render()
        receipt = dict(_snapshot(ws, page_id), job_id=job_id, summary=summary.strip(),
                       coverage_version=1)
        atomic_write(ws.report_path(f"review-completion/{job_id}.json"), json.dumps(receipt, indent=2))
        return "REVIEW_COMPLETE: receipt saved for the current draft and ledger. Stop now."


def completed(ws: Workspace, page_id: str, job_id: str) -> bool:
    try:
        receipt = json.loads(ws.report_path(f"review-completion/{job_id}.json").read_text(encoding="utf-8"))
        return (
            isinstance(receipt, dict)
            and receipt.get("job_id") == job_id
            and bool(receipt.get("summary"))
            and receipt.get("coverage_version") == 1
            and not review_evidence.missing(ws, page_id, job_id)
            and all(receipt.get(key) == value for key, value in _snapshot(ws, page_id).items())
        )
    except (OSError, ValueError):
        return False
