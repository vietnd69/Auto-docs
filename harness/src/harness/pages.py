"""Page drafts: checklist, section-wise writing, working notes (goals G1, G3)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar

import frontmatter

from harness import markdown as md
from harness.builds import parse_build_number
from harness.codeindex import FileIndex, index_codebase
from harness.file_transaction import atomic_write, file_transaction
from harness.lua_lexer import tokenize
from harness.lua_parse import LuaSymbol
from harness.plan import DocPlan, Page, load_plan, owned_symbols
from harness.symbols import SECTION_BY_KIND, canonical_heading, required_sections
from harness.timeutil import today_iso
from harness.workspace import Workspace


@dataclass(frozen=True)
class ChecklistItem:
    file: str
    symbol: LuaSymbol
    heading: str
    section: str


class PlanMissingError(FileNotFoundError):
    """No ``doc-plan.json`` yet; run ``mod-harness plan`` first."""


def get_plan(ws: Workspace) -> DocPlan:
    if not ws.plan_path.exists():
        raise PlanMissingError(f"{ws.plan_path} not found; run `mod-harness plan`")
    return load_plan(ws.plan_path)


def checklist(page: Page, index: dict[str, FileIndex]) -> list[ChecklistItem]:
    """Symbols the page must document, each with its exact heading and parent section."""
    items: list[ChecklistItem] = []
    for file, qual in owned_symbols(page, index):
        sym = index[file].symbol(qual)
        if sym is None:
            continue
        if file.startswith("components/") and sym.kind == "class":
            continue  # Component constructor state belongs in Properties, not a callable entry.
        section = (
            "## Structure" if page.kind == "data" else SECTION_BY_KIND.get(sym.kind, "## Main functions")
        )
        items.append(ChecklistItem(file, sym, canonical_heading(sym), section))
    return items


def source_build(ws: Workspace) -> str:
    """Prefer the pinned source commit's build over process-local defaults."""
    return parse_build_number(ws.git.message(ws.rev).subject) or ws.settings.get_str("baseline_build")


def property_names(ws: Workspace, page: Page) -> set[str]:
    """Literal self.field assignments in component constructors, excluding comments/strings."""
    names: set[str] = set()
    index = index_codebase(ws)
    for ref in page.sources:
        if not ref.file.startswith("components/"):
            continue
        ranges = [(s.line_start, s.line_end) for s in index[ref.file].symbols if s.kind == "class"]
        tokens = list(tokenize(ws.git.show(ws.rev, ref.file)))
        for a, b, c, d in zip(tokens, tokens[1:], tokens[2:], tokens[3:], strict=False):
            if (
                (a.value, b.value, d.value) == ("self", ".", "=")
                and a.kind == c.kind == "name"
                and any(start <= a.line <= end for start, end in ranges)
            ):
                names.add(c.value)
    return names


def page_sections(page: Page, items: list[ChecklistItem]) -> list[str]:
    return required_sections(page.kind, {i.symbol.kind for i in items})


def _frontmatter(page: Page, build: str, source_sha: str) -> dict[str, object]:
    return {
        "id": page.id.rsplit("/", 1)[-1],
        "title": page.title,
        "description": "",
        "tags": [],
        "sidebar_position": page.sidebar_position,
        "last_updated": today_iso(),
        "build_version": build,
        "source_sha": source_sha,
        "sources": [s.file for s in page.sources],
    }


def skeleton(page: Page, items: list[ChecklistItem], build: str, source_sha: str) -> str:
    """Empty page with frontmatter, title and every required section."""
    body = [f"# {page.title}", "", f"> Based on game build **{build}**", ""]
    for section in page_sections(page, items):
        body.extend([section, "", "", ""])
    post = frontmatter.Post("\n".join(body), **_frontmatter(page, build, source_sha))
    return str(frontmatter.dumps(post)) + "\n"


def draft_transaction(ws: Workspace, page: Page) -> AbstractContextManager[None]:
    return file_transaction(ws.draft_path(page.path))


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _transactional(
    function: Callable[Concatenate[Workspace, Page, _P], _R],
) -> Callable[Concatenate[Workspace, Page, _P], _R]:
    @wraps(function)
    def wrapped(ws: Workspace, page: Page, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        with draft_transaction(ws, page):
            return function(ws, page, *args, **kwargs)
    return wrapped


@_transactional
def read_draft(ws: Workspace, page: Page) -> str | None:
    path = ws.draft_path(page.path)
    return path.read_text(encoding="utf-8") if path.exists() else None


@_transactional
def ensure_draft(ws: Workspace, page: Page, build: str = "") -> str:
    """Return the current draft, creating it (from the published page or a skeleton)."""
    existing = read_draft(ws, page)
    if existing is not None:
        return existing
    published = ws.settings.docs_dir / page.path
    if published.exists():
        text = published.read_text(encoding="utf-8")
    else:
        index = index_codebase(ws)
        sha = ws.git.rev_parse(ws.rev)
        text = skeleton(page, checklist(page, index), build or source_build(ws), sha)
    write_draft(ws, page, text)
    return text


@_transactional
def write_draft(ws: Workspace, page: Page, text: str) -> None:
    path = ws.draft_path(page.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, text)


@_transactional
def write_section(ws: Workspace, page: Page, heading: str, content: str, parent: str | None = None) -> str:
    """Insert/replace one section of the draft and return the new draft text."""
    front, body = md.split_frontmatter(ensure_draft(ws, page))
    if heading.startswith("### "):
        expected = _default_parent(ws, page, heading)
        if expected and parent and md.normalize_heading(parent) != md.normalize_heading(expected):
            raise ValueError(f"parent for {heading} must be {expected!r}")
        parent = expected or parent
    new_body = md.upsert_section(body, heading, content, parent)
    text = front + new_body
    write_draft(ws, page, text)
    return text


def _default_parent(ws: Workspace, page: Page, heading: str) -> str | None:
    wanted = md.normalize_heading(heading)
    for item in checklist(page, index_codebase(ws)):
        if md.normalize_heading(item.heading) == wanted:
            return item.section
    return None


def read_notes(ws: Workspace, page_id: str) -> str:
    path = ws.notes_path(page_id)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_notes(ws: Workspace, page_id: str, text: str) -> None:
    ws.notes_path(page_id).write_text(text, encoding="utf-8")
