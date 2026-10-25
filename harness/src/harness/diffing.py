"""Symbol-level source diffs and their impact on the plan (goal G5).

Raw diffs never reach the model: changes are reduced to per-symbol events that map onto
plan pages, and an agent fetches the hunk of one symbol at a time.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from harness.codeindex import FileIndex, build_file_index, index_codebase
from harness.lua_parse import LuaSymbol
from harness.plan import DocPlan, owned_symbols
from harness.textutil import truncate
from harness.workspace import Workspace

CHANGE_KINDS = ("added", "removed", "renamed", "signature_changed", "body_changed")


@dataclass
class FileDiff:
    status: str  # A, M, D, R
    path: str
    old_path: str | None = None
    symbols: dict[str, list[str]] = field(default_factory=dict)  # change kind → qualnames

    def total(self) -> int:
        return sum(len(v) for v in self.symbols.values())


def _body(source_lines: list[str], sym: LuaSymbol) -> str:
    return "\n".join(line.strip() for line in source_lines[sym.line_start - 1 : sym.line_end])


def _anonymous(source_lines: list[str], sym: LuaSymbol) -> str:
    """Body with the symbol's own name masked, so a pure rename compares equal."""
    return _body(source_lines, sym).replace(sym.name, "\x00")


def compare_files(old: FileIndex, old_src: str, new: FileIndex, new_src: str) -> dict[str, list[str]]:
    """Per-symbol changes between two versions of one file."""
    old_lines, new_lines = old_src.splitlines(), new_src.splitlines()
    old_syms = {s.qualname: s for s in old.symbols}
    new_syms = {s.qualname: s for s in new.symbols}
    out: dict[str, list[str]] = {k: [] for k in CHANGE_KINDS}
    removed = [q for q in old_syms if q not in new_syms]
    added = [q for q in new_syms if q not in old_syms]
    old_bodies = {_anonymous(old_lines, old_syms[q]): q for q in removed}
    for qual in added:
        key = _anonymous(new_lines, new_syms[qual])
        if key in old_bodies:
            out["renamed"].append(f"{old_bodies.pop(key)} -> {qual}")
        else:
            out["added"].append(qual)
    out["removed"] = list(old_bodies.values())
    for qual in old_syms.keys() & new_syms.keys():
        if old_syms[qual].signature != new_syms[qual].signature:
            out["signature_changed"].append(qual)
        elif _body(old_lines, old_syms[qual]) != _body(new_lines, new_syms[qual]):
            out["body_changed"].append(qual)
    return {k: sorted(v) for k, v in out.items() if v}


def diff_overview(ws: Workspace, old: str, new: str) -> list[FileDiff]:
    """All changed Lua files between two revisions with per-symbol changes."""
    new_index = index_codebase(ws, new)
    old_index = index_codebase(ws, old)
    diffs: list[FileDiff] = []
    for change in ws.git.diff_name_status(old, new):
        fd = FileDiff(change.status, change.path, change.old_path)
        if change.status == "A" and change.path in new_index:
            fd.symbols = {"added": list(new_index[change.path].public)}
        elif change.status == "D":
            fd.symbols = {"removed": list(old_index.get(change.path, _empty(change.path)).public)}
        else:
            before_path = change.old_path or change.path
            old_src, new_src = ws.git.show(old, before_path), ws.git.show(new, change.path)
            fd.symbols = compare_files(
                build_file_index(before_path, old_src),
                old_src,
                build_file_index(change.path, new_src),
                new_src,
            )
        diffs.append(fd)
    return diffs


def _empty(path: str) -> FileIndex:
    return FileIndex(path, "core", 0, 0, False, [], [])


def render_overview(diffs: list[FileDiff], offset: int = 0, limit: int = 80) -> str:
    rows = []
    for fd in diffs[offset : offset + limit]:
        moved = f" (from {fd.old_path})" if fd.old_path else ""
        parts = "; ".join(
            f"{k}: {', '.join(v[:12])}{'…' if len(v) > 12 else ''}" for k, v in fd.symbols.items()
        )
        rows.append(f"{fd.status} {fd.path}{moved} — {parts or 'no symbol changes'}")
    more = (
        f"\n…{len(diffs) - offset - limit} more files (offset={offset + limit})"
        if len(diffs) > offset + limit
        else ""
    )
    summary = f"{len(diffs)} files changed, {sum(fd.total() for fd in diffs)} symbol changes\n"
    return summary + "\n".join(rows) + more


def symbol_diff(ws: Workspace, file: str, qualname: str, old: str, new: str, max_chars: int = 12000) -> str:
    """Unified diff of a single symbol between two revisions."""

    def text_at(rev: str) -> tuple[str, list[str]]:
        try:
            src = ws.git.show(rev, file)
        except Exception:  # file absent at this revision
            return "", []
        sym = build_file_index(file, src).symbol(qualname)
        if sym is None:
            return "", []
        return f"L{sym.line_start}-{sym.line_end}", src.splitlines()[sym.line_start - 1 : sym.line_end]

    old_loc, old_lines = text_at(old)
    new_loc, new_lines = text_at(new)
    diff = difflib.unified_diff(
        old_lines, new_lines, f"{old[:10]} {old_loc}", f"{new[:10]} {new_loc}", lineterm=""
    )
    return truncate("\n".join(diff) or "no changes for this symbol", max_chars)


@dataclass
class Impact:
    pages: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)  # page → (file, qual, change)
    unassigned: list[tuple[str, str]] = field(default_factory=list)  # new public symbols without a page
    removed_files: list[str] = field(default_factory=list)


def impact_map(plan: DocPlan, index: dict[str, FileIndex], diffs: list[FileDiff]) -> Impact:
    """Which pages must change, and which new symbols need a home."""
    owner: dict[tuple[str, str], str] = {}
    for page in plan.pages:
        for key in owned_symbols(page, index):
            owner[key] = page.id
    file_pages = {s.file: p.id for p in plan.pages for s in p.sources}
    impact = Impact()
    for fd in diffs:
        if fd.status == "D":
            impact.removed_files.append(fd.path)
        for kind, quals in fd.symbols.items():
            for qual in quals:
                target = qual.split(" -> ")[-1]
                path = fd.path if kind != "removed" else (fd.old_path or fd.path)
                page_id = (
                    owner.get((path, target)) or file_pages.get(path) or file_pages.get(fd.old_path or "")
                )
                if page_id is None:
                    impact.unassigned.append((fd.path, target))
                else:
                    impact.pages.setdefault(page_id, []).append((path, qual, kind))
    return impact
