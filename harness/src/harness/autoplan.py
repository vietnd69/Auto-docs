"""Deterministic default plan; the planner agent refines it with ``plan_put``.

Rules (spec §5.4): small code file → 1 page; large code file → overview page plus
pages grouped by symbol kind within the token budget; small data files sharing a
directory → merged collection pages; other data files → 1 data-reference page.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from harness.codeindex import FileIndex
from harness.plan import DocPlan, Page, SourceRef

MERGE_MAX_TOKENS = 2000
MERGE_MIN_FILES = 3
_KIND_LABEL = {
    "state": "States",
    "event_handler": "Events",
    "action": "Action handlers",
    "method": "Methods",
    "function": "Functions",
    "class": "Class",
    "prefab": "Prefabs",
    "table": "Tables",
}


def _title(path: str) -> str:
    stem = path.rsplit("/", 1)[-1].removesuffix(".lua")
    return stem[:1].upper() + stem[1:]


def _category(path: str) -> list[str]:
    return [part.replace("_", " ").title() for part in path.split("/")[:-1]]


def _single_page(fi: FileIndex, budget: int) -> Page:
    base = fi.path.removesuffix(".lua")
    return Page(
        id=base,
        path=f"{base}.md",
        title=_title(fi.path),
        domain=fi.domain,
        kind="data" if fi.is_data else "api",
        category=_category(fi.path),
        sources=[SourceRef(fi.path)],
        budget_tokens=budget,
    )


def _symbol_cost(fi: FileIndex, qual: str) -> int:
    sym = fi.symbol(qual)
    if sym is None or not fi.lines:
        return 0
    return (sym.line_end - sym.line_start + 1) * fi.tokens // fi.lines


def _chunks(fi: FileIndex, quals: list[str], budget: int) -> Iterable[list[str]]:
    chunk: list[str] = []
    used = 0
    for qual in quals:
        cost = _symbol_cost(fi, qual)
        if chunk and used + cost > budget:
            yield chunk
            chunk, used = [], 0
        chunk.append(qual)
        used += cost
    if chunk:
        yield chunk


def _split_pages(fi: FileIndex, budget: int) -> list[Page]:
    base = fi.path.removesuffix(".lua")
    title = _title(fi.path)
    category = [*_category(fi.path), title]
    overview = Page(
        id=f"{base}/index",
        path=f"{base}/index.md",
        title=title,
        domain=fi.domain,
        kind="overview",
        category=category,
        sources=[SourceRef(fi.path, [])],
        budget_tokens=budget,
        sidebar_position=1,
    )
    by_kind: dict[str, list[str]] = defaultdict(list)
    for qual in fi.public:
        sym = fi.symbol(qual)
        by_kind[sym.kind if sym else "function"].append(qual)
    pages = [overview]
    for kind, quals in by_kind.items():
        label = _KIND_LABEL.get(kind, kind)
        groups = list(_chunks(fi, quals, budget))
        for n, group in enumerate(groups, start=1):
            suffix = f"-{n}" if len(groups) > 1 else ""
            slug = label.lower().replace(" ", "-") + suffix
            pages.append(
                Page(
                    id=f"{base}/{slug}",
                    path=f"{base}/{slug}.md",
                    title=f"{title} — {label}{f' ({n}/{len(groups)})' if len(groups) > 1 else ''}",
                    domain=fi.domain,
                    kind="api",
                    category=category,
                    sources=[SourceRef(fi.path, group)],
                    budget_tokens=budget,
                    sidebar_position=1 + len(pages),
                )
            )
    return pages


def _merge_pages(directory: str, files: list[FileIndex], budget: int) -> list[Page]:
    pages: list[Page] = []
    group: list[FileIndex] = []
    used = 0
    pending: list[FileIndex | None] = [*files, None]
    for fi in pending:
        if fi is None or (group and used + fi.tokens > budget):
            n = len(pages) + 1
            pages.append(
                Page(
                    id=f"{directory}/collection-{n}",
                    path=f"{directory}/collection-{n}.md",
                    title=f"{_title(directory + '.lua')} collection {n}",
                    domain=group[0].domain,
                    kind="data",
                    category=_category(f"{directory}/x"),
                    sources=[SourceRef(g.path) for g in group],
                    budget_tokens=budget,
                )
            )
            group, used = [], 0
        if fi is not None:
            group.append(fi)
            used += fi.tokens
    return pages


def auto_plan(index: dict[str, FileIndex], baseline: dict[str, str], budget: int) -> DocPlan:
    """Build the default plan for every indexed file."""
    small_data: dict[str, list[FileIndex]] = defaultdict(list)
    for fi in index.values():
        if fi.is_data and fi.tokens <= MERGE_MAX_TOKENS and "/" in fi.path:
            small_data[fi.path.rsplit("/", 1)[0]].append(fi)
    merged = {fi.path for files in small_data.values() if len(files) >= MERGE_MIN_FILES for fi in files}
    pages: list[Page] = []
    for directory, files in sorted(small_data.items()):
        if len(files) >= MERGE_MIN_FILES:
            pages.extend(_merge_pages(directory, sorted(files, key=lambda f: f.path), budget))
    for fi in sorted(index.values(), key=lambda f: f.path):
        if fi.path in merged:
            continue
        cost = sum(_symbol_cost(fi, q) for q in fi.public)
        if not fi.is_data and cost > budget:
            pages.extend(_split_pages(fi, budget))
        else:
            pages.append(_single_page(fi, budget))
    return DocPlan(baseline=baseline, pages=pages)
