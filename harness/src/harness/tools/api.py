"""Agent-facing tool functions (plain Python; ``mcp_server`` registers them over MCP).

Each returns text sized for a model context. Paths are confined to the source and docs
trees; nothing here runs shell commands or reaches the network.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict

from harness import memory, pages, review_evidence
from harness.builds import list_builds, resolve_build
from harness.checks import run_checks
from harness.codeindex import index_codebase
from harness.diffing import diff_overview as _diff_overview
from harness.diffing import impact_map as _impact_map
from harness.diffing import render_overview
from harness.diffing import symbol_diff as _symbol_diff
from harness.ledger import Evidence, Ledger
from harness.markdown import headings, normalize_heading, section_text, split_frontmatter
from harness.plan import Page, save_plan, validate_plan
from harness.tools import lua_tools
from harness.verdict import evaluate
from harness.workspace import Workspace, workspace

_override: Workspace | None = None


def use_workspace(ws: Workspace | None) -> None:
    """Point every tool at ``ws`` (tests, sessions pinned to a revision)."""
    global _override  # noqa: PLW0603 - single process-wide switch
    _override = ws


def _ws() -> Workspace:
    return _override or workspace()


# ---- source --------------------------------------------------------------------------
def lua_outline(file: str, rev: str = "") -> str:
    """Symbol table of a Lua file (kind, name, line range, signature); start here for long files."""
    return lua_tools.lua_outline(_ws(), file, rev or None)


def lua_symbol(file: str, qualname: str, rev: str = "") -> str:
    """Source of one symbol (e.g. 'Combat:GetAttacked', 'State:idle') with line numbers."""
    output = lua_tools.lua_symbol(_ws(), file, qualname, rev or None)
    review_evidence.record(_ws(), file=file, output=output, rev=rev)
    return output


def lua_read(file: str, from_line: int, to_line: int, rev: str = "") -> str:
    """Read a line range of a Lua file (token-capped; call again to continue)."""
    output = lua_tools.lua_read(_ws(), file, from_line, to_line, rev or None)
    review_evidence.record(_ws(), file=file, output=output, rev=rev)
    return output


def lua_grep(pattern: str, path_glob: str = "*.lua", rev: str = "") -> str:
    """Extended-regex search over the Lua codebase; returns path:line:text rows."""
    return lua_tools.lua_grep(_ws(), pattern, path_glob, rev or None)


def lua_refs(name: str, rev: str = "") -> str:
    """Definitions and call sites of a function/method name across the codebase."""
    return lua_tools.lua_refs(_ws(), name, rev or None)


def lua_deps(file: str, rev: str = "") -> str:
    """Public API signatures of modules/components a file requires or uses."""
    return lua_tools.lua_deps(_ws(), file, rev or None)


def lua_table_schema(file: str, table: str = "", rev: str = "") -> str:
    """Structure of data tables (keys, value kinds, samples) and repeated calls; use for data files."""
    return lua_tools.lua_table_schema(_ws(), file, table, rev or None)


# ---- plan ------------------------------------------------------------------------------
def index_summary() -> str:
    """Codebase statistics: files per domain, data files, largest files."""
    index = index_codebase(_ws())
    domains = Counter(fi.domain for fi in index.values())
    largest = sorted(index.values(), key=lambda f: f.tokens, reverse=True)[:15]
    lines = [f"{len(index)} Lua files, {sum(len(f.public) for f in index.values())} public symbols"]
    lines += [f"  {d}: {n}" for d, n in domains.most_common()]
    lines += ["largest:"] + [f"  {f.path} ≈{f.tokens} tokens data={f.is_data}" for f in largest]
    return "\n".join(lines)


def plan_get(page_id: str = "", prefix: str = "") -> str:
    """One page as JSON, or the list of page ids (optionally filtered by prefix)."""
    plan = pages.get_plan(_ws())
    if page_id:
        return json.dumps(asdict(plan.page(page_id)), indent=1, ensure_ascii=False)
    ids = [p.id for p in plan.pages if p.id.startswith(prefix)]
    return f"{len(ids)} pages\n" + "\n".join(ids[:400]) + ("\n…" if len(ids) > 400 else "")


def plan_put(page_json: str) -> str:
    """Insert or replace one page definition, then re-validate the plan."""
    ws = _ws()
    plan = pages.get_plan(ws)
    page = Page.from_json(json.loads(page_json))
    plan.pages = [p for p in plan.pages if p.id != page.id] + [page]
    save_plan(plan, ws.plan_path)
    return f"saved {page.id}\n" + validate_plan_tool()


def plan_remove(page_id: str) -> str:
    """Remove a page from the plan, then re-validate."""
    ws = _ws()
    plan = pages.get_plan(ws)
    plan.pages = [p for p in plan.pages if p.id != page_id]
    save_plan(plan, ws.plan_path)
    return f"removed {page_id}\n" + validate_plan_tool()


def validate_plan_tool() -> str:
    """Validate the plan: every public symbol on exactly one page, budgets, paths."""
    ws = _ws()
    issues = validate_plan(pages.get_plan(ws), index_codebase(ws))
    if not issues:
        return "plan valid"
    counts = Counter(i.code for i in issues)
    return f"{len(issues)} issues {dict(counts)}\n" + "\n".join(
        f"[{i.code}] {i.message}" for i in issues[:60]
    )


# ---- pages -----------------------------------------------------------------------------
def _page(page_id: str) -> Page:
    repair_page = os.environ.get("HARNESS_REPAIR_PAGE")
    if repair_page and page_id != repair_page:
        raise ValueError(f"Repair is confined to page {repair_page!r}")
    active = os.environ.get("HARNESS_REVIEW_PAGE")
    if os.environ.get("HARNESS_REVIEW_ONLY") == "1" and page_id != active:
        raise ValueError(f"Use canonical page_id {active!r}, not a job ID or filename")
    return pages.get_plan(_ws()).page(page_id)


def page_checklist(page_id: str) -> str:
    """Symbols the page must cover, with exact heading, parent section and done flag."""
    ws = _ws()
    page = _page(page_id)
    items = pages.checklist(page, index_codebase(ws))
    _, body = split_frontmatter(pages.ensure_draft(ws, page))
    done = {normalize_heading(h.text) for h in headings(body) if h.level == 3}
    rows = [f"page {page.id} ({page.kind}, domain {page.domain}) — {len(items)} symbols"]
    rows.append("sections: " + " | ".join(pages.page_sections(page, items)))
    rows.append("Properties table must cover: " + ", ".join(sorted(pages.property_names(ws, page))))
    for item in items:
        mark = "x" if normalize_heading(item.heading) in done else " "
        sym = item.symbol
        rows.append(
            f"[{mark}] {item.heading}  under {item.section}  ({item.file} L{sym.line_start}-{sym.line_end})"
        )
    return "\n".join(rows)


def doc_read(page_id: str, heading: str = "") -> str:
    """Read the page draft, or one section of it when heading is given."""
    ws = _ws()
    text = pages.ensure_draft(ws, _page(page_id))
    if not heading:
        review_evidence.record(ws, document=page_id, output=text)
        return text
    _, body = split_frontmatter(text)
    return section_text(body, heading) or f"section {heading!r} not found"


def doc_write_section(page_id: str, heading: str, markdown: str, parent: str = "") -> str:
    """Write one section: heading='### `F()`', markdown=body without heading.

    Omit parent for checklist entries (inferred automatically), or use its exact '## X' heading.
    Unknown/wrong parents are rejected without changing the draft.
    """
    if os.environ.get("HARNESS_REVIEW_ONLY") == "1":
        return "Read-only final review: record a finding instead of changing the draft"
    ws = _ws()
    if not heading.startswith(("## ", "### ")):
        return "heading must start with '## ' or '### '"
    page = _page(page_id)
    pages.write_section(ws, page, heading, markdown, parent or None)
    return f"wrote {heading} ({len(markdown)} chars)"


def doc_set_meta(page_id: str, description: str, tags: str = "") -> str:
    """Set frontmatter ``description`` and comma-separated ``tags``."""
    import frontmatter

    if os.environ.get("HARNESS_REVIEW_ONLY") == "1":
        return "Read-only final review: record a finding instead of changing metadata"
    ws = _ws()
    page = _page(page_id)
    with pages.draft_transaction(ws, page):
        post = frontmatter.loads(pages.ensure_draft(ws, page))
        post.metadata["description"] = description.strip()
        post.metadata["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        build = pages.source_build(ws)
        post.metadata.update(
            build_version=build, source_sha=ws.git.rev_parse(ws.rev), sources=[s.file for s in page.sources]
        )
        import re

        post.content = re.sub(
            r"^> Based on game build .*?$",
            f"> Based on game build **{build}**",
            post.content,
            flags=re.MULTILINE,
        )
        pages.write_draft(ws, page, frontmatter.dumps(post) + "\n")
    return "frontmatter updated"


def notes_read(page_id: str) -> str:
    """Read the page's working notes (progress, decisions) to resume work."""
    _page(page_id)
    return pages.read_notes(_ws(), page_id) or "(no notes yet)"


def notes_write(page_id: str, text: str) -> str:
    """Replace the page's working notes."""
    _page(page_id)
    pages.write_notes(_ws(), page_id, text)
    return "notes saved"


# ---- verdict ---------------------------------------------------------------------------
def run_checks_tool(page_id: str) -> str:
    """Run deterministic checks (frontmatter, MDX, sections, coverage, signatures, phantoms, links)."""
    _page(page_id)
    ws = _ws()
    plan = pages.get_plan(ws)
    page = plan.page(page_id)
    issues = run_checks(ws, plan, page, pages.ensure_draft(ws, page))
    return "\n".join(i.render() for i in issues) or "all deterministic checks pass"


def verdict(page_id: str) -> str:
    """Final status: PASS only if checks are clean and no evidenced finding is open."""
    _page(page_id)
    ws = _ws()
    plan = pages.get_plan(ws)
    return evaluate(ws, plan, plan.page(page_id)).render()


def review_finish(page_id: str, summary: str) -> str:
    """Record final review completion only for a clean, unchanged page; then stop."""
    from harness.final_review import finish

    if os.environ.get("HARNESS_REVIEW_ONLY") != "1" or page_id != os.environ.get("HARNESS_REVIEW_PAGE"):
        return "review_finish is only available for the controller's active final-review page"
    job_id = os.environ.get("HARNESS_JOB", "")
    if not job_id or any(c in job_id for c in "/\\") or ".." in job_id:
        return "Invalid final-review job identity"
    return finish(_ws(), page_id, job_id, summary)


def ledger_add(  # noqa: PLR0913, PLR0917 - flat MCP tool schema is easier for the model
    page_id: str, symbol: str, field: str, claim: str, file: str, line_start: int, line_end: int, quote: str
) -> str:
    """Record a review finding; the quote must appear verbatim in the cited source lines."""
    _page(page_id)
    _, message = Ledger(_ws(), page_id).add(symbol, field, claim, Evidence(file, line_start, line_end, quote))
    return message


def ledger_list(page_id: str, status: str = "") -> str:
    """List review findings for a page (status: open|resolved|rejected)."""
    _page(page_id)
    return Ledger(_ws(), page_id).render(status)


def ledger_resolve(page_id: str, finding_id: str, note: str, status: str = "resolved") -> str:
    """Close a finding after fixing it (status resolved) or dismissing it (rejected)."""
    if os.environ.get("HARNESS_NATIVE_MODE") == "repair" or os.environ.get("HARNESS_REPAIR_PAGE"):
        raise ValueError("Repair writer cannot close findings; an independent review is required")
    _page(page_id)
    return Ledger(_ws(), page_id).resolve(finding_id, note, status)


# ---- builds / diffs --------------------------------------------------------------------
def build_list() -> str:
    """DST builds since the baseline: number, commit, date, title."""
    ws = _ws()
    builds = list_builds(ws.git, ws.settings.get_str("baseline_sha"), ws.settings.get_str("source_branch"))
    return "\n".join(
        f"{b.number} {b.sha[:10]} {b.date} {'hotfix ' if b.is_hotfix else ''}{b.title}" for b in builds
    )


def patch_notes(build: str) -> str:
    ws = _ws()
    builds = list_builds(ws.git, ws.settings.get_str("baseline_sha"), ws.settings.get_str("source_branch"))
    found = resolve_build(builds, build)
    return found.notes or "(no patch notes in commit message)"


def diff_overview(from_rev: str, to_rev: str, offset: int = 0) -> str:
    """Symbol-level summary of Lua changes between two revisions (paged by offset)."""
    return render_overview(_diff_overview(_ws(), from_rev, to_rev), offset)


def symbol_diff(file: str, qualname: str, from_rev: str, to_rev: str) -> str:
    """Unified diff of one symbol between two revisions."""
    return _symbol_diff(_ws(), file, qualname, from_rev, to_rev)


def impact_map(from_rev: str, to_rev: str) -> str:
    """Pages affected by changes between two revisions, plus new symbols without a page."""
    ws = _ws()
    impact = _impact_map(pages.get_plan(ws), index_codebase(ws, to_rev), _diff_overview(ws, from_rev, to_rev))
    rows = [f"{len(impact.pages)} pages affected"]
    for page_id, changes in sorted(impact.pages.items()):
        rows.append(f"{page_id}: " + "; ".join(f"{k} {q}" for _, q, k in changes[:10]))
    if impact.unassigned:
        rows.append(
            "new symbols without a page: " + ", ".join(f"{f}::{q}" for f, q in impact.unassigned[:40])
        )
    if impact.removed_files:
        rows.append("removed files: " + ", ".join(impact.removed_files))
    return "\n".join(rows)


# ---- memory ----------------------------------------------------------------------------
def memory_search(domain: str, query: str) -> str:
    """Lessons learned for a domain (e.g. 'stategraph', 'update-component') relevant to query."""
    ws = _ws()
    return memory.search(ws, domain, query, ws.settings.get_int("memory_top_n") // 3 or 5)


def memory_add(domain: str, cue: str, lesson: str, evidence: str) -> str:
    """Store a lesson: WHEN cue, DO lesson, backed by evidence from this job."""
    return memory.Library(_ws(), domain).add(cue, lesson, evidence)
