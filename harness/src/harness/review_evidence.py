"""Controller-owned read coverage, scoped to one review job and draft revision.

This proves source exposure, not model comprehension. Grep, outlines, errors and
partially returned lines are deliberately not accepted as source coverage.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from harness.file_transaction import atomic_write, file_transaction
from harness.pages import get_plan
from harness.safepath import normalize_rel
from harness.workspace import Workspace


def identity(ws: Workspace, page_id: str) -> dict:
    page = get_plan(ws).page(page_id)
    return {
        "page_id": page_id,
        "source_sha": ws.git.rev_parse(ws.rev),
        "draft_sha256": hashlib.sha256(ws.draft_path(page.path).read_bytes()).hexdigest(),
        "sources": sorted(s.file for s in page.sources),
    }


def evidence_path(ws: Workspace, job_id: str):
    if not job_id or any(c in job_id for c in "/\\") or ".." in job_id:
        raise ValueError("Invalid review job identity")
    return ws.report_path(f"review-evidence/{job_id}.json")


def record(ws: Workspace, *, document: str = "", file: str = "", output: str = "", rev: str = "") -> None:
    if os.environ.get("HARNESS_REVIEW_ONLY") != "1":
        return
    page_id = os.environ["HARNESS_REVIEW_PAGE"]
    job_id = os.environ["HARNESS_JOB"]
    current = identity(ws, page_id)
    if document and document != page_id:
        raise ValueError(f"Use canonical page_id {page_id!r}")
    if document:
        page = get_plan(ws).page(page_id)
        if output != ws.draft_path(page.path).read_text(encoding="utf-8"):
            return
    else:
        file = normalize_rel(file)
        if ws.git.rev_parse(rev or ws.rev) != current["source_sha"]:
            return
        if file not in current["sources"]:
            return
    path = evidence_path(ws, job_id)
    with file_transaction(path):
        saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if saved.get("identity") != current:
            saved = {"identity": current, "document_read": False, "lines": {}}
        if document:
            saved["document_read"] = True
        else:
            seen = set(saved["lines"].get(file, []))
            seen.update(_returned_lines(ws.git.show(ws.rev, file).splitlines(), output))
            saved["lines"][file] = sorted(seen)
        atomic_write(path, json.dumps(saved, indent=2))


def _returned_lines(source: list[str], output: str) -> set[int]:
    seen = set()
    for row in output.splitlines():
        match = re.fullmatch(r"\s*(\d+)\| (.*)", row)
        if match:
            number = int(match[1])
            if 1 <= number <= len(source) and source[number - 1] == match[2]:
                seen.add(number)
    return seen


def missing(ws: Workspace, page_id: str, job_id: str) -> list[str]:
    current = identity(ws, page_id)
    path = evidence_path(ws, job_id)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if saved.get("identity") != current:
        saved = {}
    problems = []
    if not saved.get("document_read"):
        problems.append(
            f"dst-tools_doc_read(page_id={page_id!r}, heading='') must read the full current draft"
        )
    for file in current["sources"]:
        count = len(ws.git.show(ws.rev, file).splitlines())
        unseen = sorted(set(range(1, count + 1)) - set(saved.get("lines", {}).get(file, [])))
        if unseen:
            problems.append(
                f"dst-tools_lua_read({file!r}, {unseen[0]}, {unseen[-1]}) at pinned revision; "
                f"{len(unseen)} unread lines"
            )
    return problems
