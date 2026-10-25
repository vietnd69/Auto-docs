"""Apply a source diff to the documentation plan (new/removed/renamed files and symbols)."""

from __future__ import annotations

from collections import Counter

from harness.autoplan import auto_plan
from harness.codeindex import FileIndex
from harness.diffing import FileDiff, Impact
from harness.plan import DocPlan, Page


def _rename_refs(plan: DocPlan, diffs: list[FileDiff]) -> set[str]:
    touched: set[str] = set()
    renames = {fd.old_path: fd.path for fd in diffs if fd.status == "R" and fd.old_path}
    for page in plan.pages:
        for ref in page.sources:
            if ref.file in renames:
                ref.file = renames[ref.file]
                touched.add(page.id)
    return touched


def _drop_removed(plan: DocPlan, index: dict[str, FileIndex]) -> set[str]:
    touched: set[str] = set()
    for page in plan.pages:
        kept = []
        for ref in page.sources:
            if ref.file not in index:
                touched.add(page.id)
                continue
            fi = index[ref.file]
            alive = [q for q in ref.symbols if fi.symbol(q) is not None]
            if len(alive) != len(ref.symbols):
                touched.add(page.id)
                if not alive:
                    continue
            ref.symbols = alive
            kept.append(ref)
        page.sources = kept
    plan.pages = [p for p in plan.pages if p.sources]
    return touched


def _home_for(plan: DocPlan, fi: FileIndex, qual: str) -> Page | None:
    """Page of the same file holding most symbols of the same kind."""
    sym = fi.symbol(qual)
    kind = sym.kind if sym else ""
    votes: Counter[str] = Counter()
    by_id: dict[str, Page] = {}
    for page in plan.pages_for_file(fi.path):
        by_id[page.id] = page
        for ref in page.sources:
            if ref.file == fi.path:
                votes[page.id] += sum(1 for q in ref.symbols if (s := fi.symbol(q)) and s.kind == kind) + 1
    best = votes.most_common(1)
    return by_id[best[0][0]] if best else None


def apply_impact(
    plan: DocPlan, index: dict[str, FileIndex], diffs: list[FileDiff], impact: Impact, budget: int
) -> set[str]:
    """Mutate ``plan`` for a source update; return ids of pages that must be (re)written."""
    touched = _rename_refs(plan, diffs) | _drop_removed(plan, index) | set(impact.pages)
    covered = {ref.file for p in plan.pages for ref in p.sources}
    new_files = {fd.path: index[fd.path] for fd in diffs if fd.path in index and fd.path not in covered}
    if new_files:
        fresh = auto_plan(new_files, plan.baseline, budget)
        plan.pages.extend(fresh.pages)
        touched |= {p.id for p in fresh.pages}
    for file, qual in impact.unassigned:
        fi = index.get(file)
        if fi is None or file in new_files:
            continue
        home = _home_for(plan, fi, qual)
        if home is None:
            continue
        ref = next(r for r in home.sources if r.file == file)
        if ref.symbols and qual not in ref.symbols:
            ref.symbols.append(qual)
        touched.add(home.id)
    known = {p.id for p in plan.pages}
    return {t for t in touched if t in known}
