"""Documentation plan: which pages exist and which symbols each page owns (goal G2)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from harness.codeindex import FileIndex

_VALID_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-./]*\.md$")
PAGE_KINDS = ("api", "data", "overview")


@dataclass
class SourceRef:
    file: str
    symbols: list[str] = field(default_factory=list)  # empty = every public symbol of the file


@dataclass
class Page:
    id: str
    path: str
    title: str
    domain: str
    kind: str
    category: list[str]
    sources: list[SourceRef]
    budget_tokens: int = 12000
    sidebar_position: int = 10

    @classmethod
    def from_json(cls, data: dict[str, object]) -> Page:
        raw = dict(data)
        sources = raw.pop("sources", [])
        if not isinstance(sources, list):
            raise TypeError(f"page {raw.get('id')!r}: sources must be a list")
        return cls(sources=[SourceRef(**s) for s in sources], **raw)  # type: ignore[arg-type]


@dataclass
class DocPlan:
    baseline: dict[str, str]
    pages: list[Page]

    def page(self, page_id: str) -> Page:
        for page in self.pages:
            if page.id == page_id:
                return page
        raise KeyError(f"unknown page {page_id!r}")

    def pages_for_file(self, file: str) -> list[Page]:
        return [p for p in self.pages if any(s.file == file for s in p.sources)]

    def to_json(self) -> dict[str, object]:
        pages = sorted(self.pages, key=lambda p: p.id)
        return {"baseline": self.baseline, "pages": [asdict(p) for p in pages]}


def load_plan(path: Path) -> DocPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    return DocPlan(baseline=data["baseline"], pages=[Page.from_json(p) for p in data["pages"]])


def save_plan(plan: DocPlan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_json(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def owned_symbols(page: Page, index: dict[str, FileIndex]) -> list[tuple[str, str]]:
    """(file, qualname) pairs a page must document."""
    owned: list[tuple[str, str]] = []
    for ref in page.sources:
        fi = index.get(ref.file)
        if fi is None:
            continue
        names = ref.symbols or ([] if page.kind == "overview" else fi.public)
        owned.extend((ref.file, q) for q in names)
    return owned


@dataclass(frozen=True)
class PlanIssue:
    code: str
    message: str


def _assignment_issues(plan: DocPlan, index: dict[str, FileIndex]) -> list[PlanIssue]:
    issues: list[PlanIssue] = []
    owner: dict[tuple[str, str], str] = {}
    for page in plan.pages:
        for key in owned_symbols(page, index):
            fi = index[key[0]]
            if fi.symbol(key[1]) is None:
                issues.append(PlanIssue("UNKNOWN_SYMBOL", f"{page.id}: {key[0]} has no symbol {key[1]}"))
            elif key in owner:
                issues.append(PlanIssue("DUPLICATE", f"{key[0]} {key[1]} in {owner[key]} and {page.id}"))
            else:
                owner[key] = page.id
    for fi in index.values():
        missing = [q for q in fi.public if (fi.path, q) not in owner]
        if missing:
            issues.append(
                PlanIssue(
                    "UNASSIGNED", f"{fi.path}: {len(missing)} public symbols ({', '.join(missing[:5])})"
                )
            )
    return issues


def _page_issues(page: Page, index: dict[str, FileIndex]) -> list[PlanIssue]:
    issues: list[PlanIssue] = []
    if not page.sources:
        issues.append(PlanIssue("EMPTY_PAGE", page.id))
    if not _VALID_PATH.match(page.path) or ".." in page.path:
        issues.append(PlanIssue("BAD_PATH", f"{page.id}: {page.path}"))
    if page.kind not in PAGE_KINDS:
        issues.append(PlanIssue("BAD_KIND", f"{page.id}: {page.kind}"))
    unknown = [s.file for s in page.sources if s.file not in index]
    if unknown:
        issues.append(PlanIssue("UNKNOWN_FILE", f"{page.id}: {', '.join(unknown)}"))
    oversized = page.kind == "api" and symbol_tokens(page, index) > page.budget_tokens
    if oversized and len(owned_symbols(page, index)) > 1:  # one giant symbol cannot be split
        issues.append(
            PlanIssue("OVER_BUDGET", f"{page.id}: {symbol_tokens(page, index)} > {page.budget_tokens} tokens")
        )
    return issues


def symbol_tokens(page: Page, index: dict[str, FileIndex]) -> int:
    """Approximate source tokens of the symbols a page owns."""
    total = 0
    for file, qual in owned_symbols(page, index):
        fi = index[file]
        sym = fi.symbol(qual)
        if sym is not None and fi.lines:
            total += (sym.line_end - sym.line_start + 1) * fi.tokens // fi.lines
    return total


def validate_plan(plan: DocPlan, index: dict[str, FileIndex]) -> list[PlanIssue]:
    """Deterministic plan checks; an empty list means the plan is valid."""
    issues: list[PlanIssue] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for page in plan.pages:
        if page.id in seen_ids or page.path.lower() in seen_paths:
            issues.append(PlanIssue("DUPLICATE_PAGE", page.id))
        seen_ids.add(page.id)
        seen_paths.add(page.path.lower())
        issues.extend(_page_issues(page, index))
    covered = {s.file for p in plan.pages for s in p.sources}
    issues.extend(PlanIssue("UNCOVERED_FILE", f) for f in sorted(set(index) - covered))
    issues.extend(_assignment_issues(plan, index))
    return issues
