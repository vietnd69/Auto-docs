"""Deterministic page checks — the only authority on PASS/FAIL (goals G1, G4, G7)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import frontmatter

from harness import markdown as md
from harness import mdx
from harness.codeindex import FileIndex, index_codebase
from harness.pages import checklist, page_sections
from harness.plan import DocPlan, Page
from harness.workspace import Workspace

REQUIRED_FM = (
    "id",
    "title",
    "description",
    "tags",
    "sidebar_position",
    "last_updated",
    "build_version",
    "source_sha",
    "sources",
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
_CLASS_CALL_RE = re.compile(r"`[^`]*?\b([A-Z]\w*):(\w+)\(")
_FN_HEADING_RE = re.compile(r"^`(\w+)\((.*)\)`$")
_PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b|\[to be written\]", re.IGNORECASE)


@dataclass(frozen=True)
class CheckIssue:
    code: str
    message: str

    def render(self) -> str:
        return f"[{self.code}] {self.message}"


def _frontmatter_issues(text: str) -> list[CheckIssue]:
    try:
        meta = frontmatter.loads(text).metadata
    except Exception as exc:  # malformed YAML of any kind
        return [CheckIssue("FM_SCHEMA", f"frontmatter does not parse: {exc}")]
    issues = [CheckIssue("FM_SCHEMA", f"missing field {k!r}") for k in REQUIRED_FM if k not in meta]
    if not str(meta.get("description", "")).strip():
        issues.append(CheckIssue("FM_SCHEMA", "description is empty"))
    if "last_updated" in meta and not _DATE_RE.match(str(meta["last_updated"])):
        issues.append(CheckIssue("FM_SCHEMA", "last_updated must be ISO 8601 YYYY-MM-DD"))
    return issues


def _section_issues(page: Page, body: str, required: list[str]) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    for section in required:
        text = md.section_text(body, section)
        if text is None:
            issues.append(CheckIssue("HEADINGS", f"missing section {section!r}"))
        elif len(text.strip().splitlines()) <= 1:
            issues.append(CheckIssue("EMPTY_SECTION", f"section {section!r} has no content"))
    titles = [h for h in md.headings(body) if h.level == 1]
    if len(titles) != 1:
        issues.append(CheckIssue("HEADINGS", f"expected exactly one H1 title, found {len(titles)}"))
    if _PLACEHOLDER_RE.search(body):
        issues.append(CheckIssue("PLACEHOLDER", "page contains TODO/TBD/FIXME placeholders"))
    return issues


def _coverage_issues(page: Page, body: str, index: dict[str, FileIndex]) -> list[CheckIssue]:
    items = checklist(page, index)
    present = {md.normalize_heading(h.text) for h in md.headings(body) if h.level == 3}
    wanted = {md.normalize_heading(i.heading): i for i in items}
    issues = [
        CheckIssue("COVERAGE", f"missing {item.heading} ({item.file} L{item.symbol.line_start})")
        for key, item in wanted.items()
        if key not in present
    ]
    names = {i.symbol.name: i for i in items}
    for heading in present - set(wanted):
        match = _FN_HEADING_RE.match(heading)
        if match and match.group(1) in names:
            expected = names[match.group(1)].heading
            issues.append(CheckIssue("SIGNATURE", f"`{heading}` should be {expected}"))
    return issues


def _phantom_issues(body: str, index: dict[str, FileIndex]) -> list[CheckIssue]:
    classes: dict[str, set[str]] = {}
    for fi in index.values():
        for sym in fi.symbols:
            if sym.kind == "method":
                owner = sym.qualname.split(":")[0]
                classes.setdefault(owner, set()).add(sym.name)
            elif sym.kind == "class":
                classes.setdefault(sym.qualname, set())
    issues: list[CheckIssue] = []
    for owner, method in sorted(set(_CLASS_CALL_RE.findall(body))):
        if owner in classes and method not in classes[owner]:
            issues.append(CheckIssue("PHANTOM", f"`{owner}:{method}` does not exist in the source"))
    return issues


def _link_issues(page: Page, body: str, plan: DocPlan) -> list[CheckIssue]:
    known = {p.path.removesuffix(".md").lower() for p in plan.pages}
    base = page.path.rsplit("/", 1)[0] if "/" in page.path else ""
    issues: list[CheckIssue] = []
    for target in _LINK_RE.findall(body):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean = target.split("#", 1)[0].removesuffix(".md").removesuffix(".mdx")
        resolved = _resolve(base, clean).lower()
        if resolved and resolved not in known:
            issues.append(CheckIssue("LINKS", f"broken internal link {target!r}"))
    return issues


def _resolve(base: str, target: str) -> str:
    parts = [] if target.startswith("/") else [p for p in base.split("/") if p]
    for part in target.strip("/").split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def run_checks(ws: Workspace, plan: DocPlan, page: Page, text: str) -> list[CheckIssue]:
    """All deterministic checks for one page draft; empty list = clean."""
    index = index_codebase(ws)
    _, body = md.split_frontmatter(text)
    issues = _frontmatter_issues(text)
    issues += _section_issues(page, body, page_sections(page, checklist(page, index)))
    issues += _coverage_issues(page, body, index)
    issues += _phantom_issues(body, index)
    issues += _link_issues(page, body, plan)
    issues += _mdx_issues(ws, page)
    return issues


def _mdx_issues(ws: Workspace, page: Page) -> list[CheckIssue]:
    try:
        errors = mdx.compile_errors(ws.draft_path(page.path), ws.settings.get_int("mdx_timeout"))
    except mdx.MdxUnavailableError as exc:
        return [CheckIssue("MDX_UNAVAILABLE", str(exc))]
    return [CheckIssue("MDX_COMPILE", e) for e in errors]
