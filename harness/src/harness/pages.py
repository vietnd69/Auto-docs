"""Page drafts: checklist, section-wise writing, working notes (goals G1, G3)."""

from __future__ import annotations

from dataclasses import dataclass

import frontmatter

from harness import markdown as md
from harness.codeindex import FileIndex, index_codebase
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
        section = (
            "## Structure" if page.kind == "data" else SECTION_BY_KIND.get(sym.kind, "## Main functions")
        )
        items.append(ChecklistItem(file, sym, canonical_heading(sym), section))
    return items


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


def read_draft(ws: Workspace, page: Page) -> str | None:
    path = ws.draft_path(page.path)
    return path.read_text(encoding="utf-8") if path.exists() else None


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
        text = skeleton(page, checklist(page, index), build or ws.settings.get_str("baseline_build"), sha)
    write_draft(ws, page, text)
    return text


def write_draft(ws: Workspace, page: Page, text: str) -> None:
    path = ws.draft_path(page.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_section(ws: Workspace, page: Page, heading: str, content: str, parent: str | None = None) -> str:
    """Insert/replace one section of the draft and return the new draft text."""
    front, body = md.split_frontmatter(ensure_draft(ws, page))
    if parent is None and heading.startswith("### "):
        parent = _default_parent(ws, page, heading)
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
