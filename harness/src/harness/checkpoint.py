"""Local page checkpoints: preserve evidence and resume only the final review."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import frontmatter

from harness.file_transaction import atomic_write
from harness.pages import get_plan, read_draft
from harness.workspace import Workspace


def checkpoint_path(ws: Workspace, page_id: str) -> Path:
    return ws.report_path(f"checkpoints/{page_id.replace('/', '__')}.json")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def _identity(ws: Workspace, page_id: str, tree: Path) -> dict[str, str]:
    page = get_plan(ws).page(page_id)
    digest = hashlib.sha256()
    for path in sorted(tree.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(tree).as_posix().encode())
            digest.update(path.read_bytes())
    return {
        "page_id": page_id,
        "source_sha": ws.git.rev_parse(ws.rev),
        "plan_sha256": _hash(ws.plan_path),
        "tree_sha256": digest.hexdigest(),
        "draft_sha256": _hash(ws.draft_path(page.path)),
        "ledger_sha256": _hash(ws.ledger_path(page_id)),
    }


def save_checkpoint(ws: Workspace, page_id: str, tree: Path, job_id: str) -> Path:
    """Snapshot draft, ledger and runtime evidence without declaring quality PASS."""
    identity = _identity(ws, page_id, tree)
    page = get_plan(ws).page(page_id)
    directory = ws.report_path(f"attempts/{job_id}/manifest.json").parent
    files = {
        "draft.md": ws.draft_path(page.path),
        "ledger.jsonl": ws.ledger_path(page_id),
        "notes.md": ws.notes_path(page_id),
        "execution.json": ws.report_path(f"execution/{job_id}.json"),
        "events.jsonl": ws.report_path(f"sessions/{job_id}.jsonl"),
    }
    for name, source in files.items():
        if source.is_file():
            shutil.copyfile(source, directory / name)
    record = dict(identity, schema_version=1, job_id=job_id)
    atomic_write(directory / "manifest.json", json.dumps(record, indent=2))
    target = checkpoint_path(ws, page_id)
    atomic_write(target, json.dumps(record, indent=2))
    return target


def validate_resume(ws: Workspace, page_id: str, tree: Path) -> dict:
    """Fail before model IO if saved source, plan, draft, ledger or skills changed."""
    path = checkpoint_path(ws, page_id)
    if not path.exists():
        raise ValueError("No review checkpoint; do not regenerate or infer completion from an old draft")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema_version") != 1:
        raise ValueError("Unsupported review checkpoint")
    for key, value in _identity(ws, page_id, tree).items():
        if record.get(key) != value:
            raise ValueError(f"Review checkpoint mismatch: {key}")
    page = get_plan(ws).page(page_id)
    text = read_draft(ws, page)
    if not text or frontmatter.loads(text).get("source_sha") != record["source_sha"]:
        raise ValueError("Review checkpoint needs a draft from the pinned source revision")
    return record
