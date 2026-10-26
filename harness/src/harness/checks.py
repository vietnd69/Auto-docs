"""Deterministic page checks — the only authority on PASS/FAIL (goals G1, G4, G7)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import frontmatter

from harness import markdown as md
from harness import mdx
from harness.codeindex import FileIndex, index_codebase
from harness.pages import checklist, page_sections, property_names, source_build
from harness.plan import DocPlan, Page
from harness.semantic_cases import source_cases
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
_CLASS_CALL_RE = re.compile(r"`[^`\n]*?\b([A-Z]\w*):(\w+)(?=[(`\s])")
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
    issues = _duplicate_headings(body)
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
    actual = [f"## {h.text}" for h in md.headings(body) if h.level == 2 and f"## {h.text}" in required]
    if actual != [s for s in required if s in actual]:
        issues.append(CheckIssue("HEADINGS", "required sections are out of order"))
    return issues


def _provenance_issues(ws: Workspace, page: Page, text: str, body: str) -> list[CheckIssue]:
    try:
        meta = frontmatter.loads(text).metadata
    except Exception:
        return []  # FM_SCHEMA reports malformed YAML.
    expected = {
        "source_sha": ws.git.rev_parse(ws.rev),
        "build_version": source_build(ws),
        "sources": [s.file for s in page.sources],
    }
    issues = [
        CheckIssue("PROVENANCE", f"{key} must equal {value!r}")
        for key, value in expected.items()
        if meta.get(key) != value
    ]
    if f"> Based on game build **{expected['build_version']}**" not in body:
        issues.append(CheckIssue("PROVENANCE", "build banner must match the pinned source build"))
    return issues


def _property_issues(ws: Workspace, page: Page, body: str) -> list[CheckIssue]:
    if page.kind != "api":
        return []
    section = md.section_text(body, "## Properties") or ""
    rows = [line.split("|")[1:-1] for line in section.splitlines() if line.strip().startswith("|")]
    documented = {
        cells[0].strip().strip("`") for cells in rows if len(cells) == 4 and all(c.strip() for c in cells)
    }
    return [
        CheckIssue(
            "PROPERTIES", f"missing complete Property | Type | Default Value | Description row: {name}"
        )
        for name in sorted(property_names(ws, page) - documented)
    ]


def _duplicate_headings(body: str) -> list[CheckIssue]:
    seen: set[tuple[int, str, str]] = set()
    issues: list[CheckIssue] = []
    parent = ""
    for h in md.headings(body):
        if h.level not in (2, 3):
            continue
        name = md.normalize_heading(h.text)
        key = (h.level, parent if h.level == 3 else "", name)
        if key in seen:
            issues.append(CheckIssue("DUPLICATE_HEADING", f"repeated heading {'#' * h.level} {name}"))
        seen.add(key)
        if h.level == 2:
            parent = name
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


def _format_contract_issue(source: str, entry: str) -> bool:
    """Narrow proof: a direct, unguarded numeric format of mutable self fields.

    Deliberately excludes guarded functions and wrappers; this is not a Lua interpreter.
    """
    direct = re.fullmatch(
        r"\s*function[^\n]+\n\s*return\s+string\.format\(\s*([\"\'])(.*?)\1"
        r"\s*,\s*self\.\w+(?:\s*,\s*self\.\w+)*\s*\)\s*end\s*",
        source,
        re.DOTALL,
    )
    return bool(
        direct
        and re.search(r"(?<!%)%(?:[-+ #0]*\d*(?:\.\d+)?)?[defgGioxXu]", direct[2])
        and (
            re.search(r"\*\*Error states:\*\*\s*None\b", entry, re.IGNORECASE)
            or (
                re.search(r"\bnon-number\b|\bfor example a string\b", entry, re.IGNORECASE)
                and not re.search(r"\bnumeric strings?\b", entry, re.IGNORECASE)
            )
        )
    )


def _deferred_transform_issue(source: str, entry: str) -> bool:
    """Exact unguarded callback shape only; guarded/complex callbacks need review."""
    direct = re.fullmatch(
        r"\s*function\s+\w+:\w+\(\w+\)\s*"
        r"self\.inst:DoTaskInTime\(0,\s*function\(inst\)\s*"
        r"inst\.Transform:SetRotation\(\w+\)\s*end\)\s*end\s*",
        source,
    )
    return bool(direct and re.search(r"\*\*Error states:\*\*\s*None\b", entry, re.IGNORECASE))


def _example_coordinate_issues(body: str) -> list[CheckIssue]:
    """Catch literal x/y/z placeholders with no other mention or setup in Usage.

    This is not a Lua free-variable analyzer. Explicitly described preconditions,
    other expressions and nontrivial scope analysis are left to semantic review.
    """
    usage = md.section_text(body, "## Usage example") or ""
    pattern = r":SetPosition\(\s*x\s*,\s*y\s*,\s*z\s*\)"
    code = "\n".join(re.findall(r"```lua\s*\n(.*?)```", usage, re.DOTALL))
    if not re.search(pattern, code):
        return []
    remaining = re.sub(pattern, "", usage)
    if all(not re.search(rf"\b{name}\b", remaining) for name in ("x", "y", "z")):
        return [CheckIssue("EXAMPLE_PRECONDITION", "Usage calls SetPosition(x, y, z) without "
                           "declaring or describing those coordinates. "
                           "Provide values or explicit preconditions.")]
    return []


def _contract_issues(ws: Workspace, page: Page, body: str, index: dict[str, FileIndex]) -> list[CheckIssue]:
    issues = []
    for item in checklist(page, index):
        entry = md.section_text(body, item.heading) or ""
        lines = ws.git.show(ws.rev, item.file).splitlines()
        source = "\n".join(lines[item.symbol.line_start - 1 : item.symbol.line_end])
        if _format_contract_issue(source, entry):
            issues.append(
                CheckIssue(
                    "ERROR_CONTRACT",
                    f"{item.heading}: numeric string.format can raise on incompatible mutable fields; "
                    "numeric strings are accepted. Error states must reflect both facts.",
                )
            )
        if _deferred_transform_issue(source, entry):
            issues.append(CheckIssue(
                "ERROR_CONTRACT", f"{item.heading}: deferred callback uses Transform without a guard; "
                "Error states cannot unconditionally say None."
            ))
    dependencies = md.section_text(body, "## Dependencies & tags") or ""
    if re.search(r"\*\*External dependencies:\*\*\s*None\b", dependencies, re.IGNORECASE):
        for ref in page.sources:
            source = ws.git.show(ws.rev, ref.file)
            if re.search(r"\bClass\s*\(", source) and not re.search(r"\blocal\s+Class\b", source):
                issues.append(
                    CheckIssue(
                        "DEPENDENCY_CONTRACT",
                        f"{ref.file} calls global Class; no require calls does not mean no dependencies",
                    )
                )
                break
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
    issues += _provenance_issues(ws, page, text, body)
    issues += _property_issues(ws, page, body)
    issues += _section_issues(page, body, page_sections(page, checklist(page, index)))
    issues += _coverage_issues(page, body, index)
    issues += _phantom_issues(body, index)
    issues += _contract_issues(ws, page, body, index)
    issues += _example_coordinate_issues(body)
    issues += [CheckIssue(code, message) for code, message in source_cases(ws, page, text)]
    issues += _link_issues(page, body, plan)
    issues += _mdx_issues(ws, page)
    return issues


def _mdx_issues(ws: Workspace, page: Page) -> list[CheckIssue]:
    try:
        errors = mdx.compile_errors(ws.draft_path(page.path), ws.settings.get_int("mdx_timeout"))
    except mdx.MdxUnavailableError as exc:
        return [CheckIssue("MDX_UNAVAILABLE", str(exc))]
    return [CheckIssue("MDX_COMPILE", e) for e in errors]
