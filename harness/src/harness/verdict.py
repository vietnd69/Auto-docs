"""Final page verdict and publishing to the Docusaurus docs tree."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from harness.checks import CheckIssue, run_checks
from harness.codeindex import index_codebase
from harness.ledger import Finding, Ledger
from harness.pages import read_draft
from harness.plan import DocPlan, Page, owned_symbols
from harness.syncstate import SyncState
from harness.textutil import short_hash
from harness.timeutil import today_iso
from harness.workspace import Workspace

PASS, FAIL, BUDGET_EXHAUSTED = "PASS", "FAIL", "BUDGET_EXHAUSTED"


@dataclass
class Verdict:
    page_id: str
    status: str
    issues: list[CheckIssue] = field(default_factory=list)
    open_findings: list[Finding] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"{self.page_id}: {self.status}"]
        lines += [f"  {i.render()}" for i in self.issues]
        lines += [f"  [FINDING {f.id}] {f.symbol}.{f.field}: {f.claim}" for f in self.open_findings]
        return "\n".join(lines)


def evaluate(ws: Workspace, plan: DocPlan, page: Page) -> Verdict:
    """PASS only when deterministic checks are clean and no evidenced finding is open."""
    text = read_draft(ws, page)
    if text is None:
        return Verdict(page.id, FAIL, [CheckIssue("NO_DRAFT", "page has no draft yet")])
    issues = run_checks(ws, plan, page, text)
    findings = Ledger(ws, page.id).open_findings()
    return Verdict(page.id, PASS if not issues and not findings else FAIL, issues, findings)


def symbol_hashes(ws: Workspace, page: Page) -> dict[str, str]:
    index = index_codebase(ws)
    hashes: dict[str, str] = {}
    for file, qual in owned_symbols(page, index):
        sym = index[file].symbol(qual)
        if sym is not None:
            lines = ws.git.show(ws.rev, file).splitlines()[sym.line_start - 1 : sym.line_end]
            hashes[f"{file}::{qual}"] = short_hash("\n".join(lines))
    return hashes


def publish(ws: Workspace, page: Page, build: str) -> Path:
    """Copy a PASSing draft into the docs tree and record its source commit."""
    text = read_draft(ws, page)
    if text is None:
        raise FileNotFoundError(page.path)
    post = frontmatter.loads(text)
    sha = ws.git.rev_parse(ws.rev)
    post.metadata.update({"last_updated": today_iso(), "build_version": build, "source_sha": sha})
    target = ws.settings.docs_dir / page.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    state = SyncState(ws)
    state.mark(page.id, sha, build, symbol_hashes(ws, page), page.path)
    state.save()
    return target


def unpublish(ws: Workspace, page_path: str) -> None:
    target = ws.settings.docs_dir / page_path
    if target.exists():
        target.unlink()


def write_categories(ws: Workspace, plan: DocPlan) -> int:
    """Generate ``_category_.json`` for every docs directory used by the plan."""
    dirs: dict[str, str] = {}
    for page in plan.pages:
        parts = page.path.split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            rel = "/".join(parts[:depth])
            label = page.category[depth - 1] if depth - 1 < len(page.category) else parts[depth - 1]
            dirs.setdefault(rel, label)
    for rel, label in dirs.items():
        path = ws.settings.docs_dir / rel / "_category_.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"label": label, "collapsed": True}, indent=2) + "\n", encoding="utf-8")
    return len(dirs)


def remove_stale_pages(ws: Workspace, plan: DocPlan) -> list[str]:
    """Delete pages this harness published earlier that the plan no longer contains.

    Only pages recorded in the sync state are touched; hand-written docs are never removed.
    """
    docs = ws.settings.docs_dir
    keep = {p.id for p in plan.pages}
    state = SyncState(ws)
    removed: list[str] = []
    for page_id, sync in list(state.pages.items()):
        if page_id in keep or not sync.path:
            continue
        target = docs / sync.path
        if target.exists():
            target.unlink()
            removed.append(sync.path)
        state.forget(page_id)
        _prune_empty_dirs(target.parent, docs)
    state.save()
    return removed


def _prune_empty_dirs(directory: Path, stop: Path) -> None:
    while directory != stop and directory.is_dir():
        leftovers = [p for p in directory.iterdir() if p.name != "_category_.json"]
        if leftovers:
            return
        for p in directory.iterdir():
            p.unlink()
        directory.rmdir()
        directory = directory.parent
