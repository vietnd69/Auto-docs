"""Source-reading tools: let agents pull exactly the Lua they need (goal G3)."""

from __future__ import annotations

from harness.codeindex import FileIndex, index_codebase, index_file
from harness.lua_tables import call_histogram, table_shape
from harness.safepath import normalize_rel
from harness.textutil import estimate_tokens, truncate
from harness.workspace import Workspace


def _limit(ws: Workspace, text: str, hint: str = "") -> str:
    return truncate(text, ws.settings.get_int("tool_output_max_chars"), hint)


def _numbered(lines: list[str], first_line: int) -> str:
    width = len(str(first_line + len(lines)))
    return "\n".join(f"{first_line + i:>{width}}| {line}" for i, line in enumerate(lines))


def lua_outline(ws: Workspace, file: str, rev: str | None = None) -> str:
    """Symbol table of one file: kind, qualname, line range, size and signature."""
    fi = index_file(ws, normalize_rel(file), rev)
    header = (
        f"{fi.path} domain={fi.domain} lines={fi.lines} tokens≈{fi.tokens} "
        f"data={fi.is_data} public={len(fi.public)}"
    )
    rows = [header]
    public = set(fi.public)
    for sym in fi.symbols:
        size = sym.line_end - sym.line_start + 1
        flag = "*" if sym.qualname in public else " "
        rows.append(
            f"{flag} {sym.kind:<13} {sym.qualname:<48} L{sym.line_start}-{sym.line_end} "
            f"({size} lines) {sym.signature}"
        )
    extras = _facts_lines(fi)
    return _limit(ws, "\n".join(rows + extras), "(* = public; use lua_symbol for bodies)")


def _facts_lines(fi: FileIndex) -> list[str]:
    pairs = [
        ("requires", fi.requires),
        ("events listened", fi.events_listened),
        ("events pushed", fi.events_pushed),
        ("components used", fi.components),
        ("tags", fi.tags),
    ]
    return [f"{label}: {', '.join(values)}" for label, values in pairs if values]


def lua_symbol(ws: Workspace, file: str, qualname: str, rev: str | None = None) -> str:
    """Source of one symbol with line numbers."""
    path = normalize_rel(file)
    fi = index_file(ws, path, rev)
    sym = fi.symbol(qualname)
    if sym is None:
        needle = qualname.rsplit(":", maxsplit=1)[-1].lower()
        close = [s.qualname for s in fi.symbols if needle in s.qualname.lower()]
        return f"symbol {qualname!r} not found in {path}. Similar: {', '.join(close[:10]) or 'none'}"
    lines = ws.git.show(rev or ws.rev, path).splitlines()[sym.line_start - 1 : sym.line_end]
    return _limit(
        ws,
        f"-- {path} {sym.kind} {sym.qualname} L{sym.line_start}-{sym.line_end}\n"
        + _numbered(lines, sym.line_start),
        f"(symbol is large; continue with lua_read({path!r}, from_line, to_line))",
    )


def lua_read(ws: Workspace, file: str, from_line: int, to_line: int, rev: str | None = None) -> str:
    """Line range of a file, capped at ``read_max_tokens``."""
    path = normalize_rel(file)
    lines = ws.git.show(rev or ws.rev, path).splitlines()
    start = max(1, from_line)
    budget = ws.settings.get_int("read_max_tokens")
    chosen: list[str] = []
    used = 0
    for line in lines[start - 1 : max(start, to_line)]:
        used += estimate_tokens(line) + 1
        if used > budget:
            break
        chosen.append(line)
    end = start + len(chosen) - 1
    more = (
        f"\n…[stopped at L{end} of {len(lines)}; call lua_read again from {end + 1}]"
        if end < min(to_line, len(lines))
        else ""
    )
    return f"-- {path} L{start}-{end} of {len(lines)}\n" + _numbered(chosen, start) + more


def lua_grep(ws: Workspace, pattern: str, path_glob: str = "*.lua", rev: str | None = None) -> str:
    """Extended-regex search across the codebase at ``rev``."""
    rows = ws.git.grep(rev or ws.rev, pattern, path_glob)
    return _limit(ws, "\n".join(rows) or "no matches", "(narrow the pattern or path_glob)")


def lua_refs(ws: Workspace, name: str, rev: str | None = None) -> str:
    """Where ``name`` is defined (index) and referenced (grep) across the codebase."""
    index = index_codebase(ws, rev)
    short = name.rsplit(":", maxsplit=1)[-1].rsplit(".", maxsplit=1)[-1]
    defs = [
        f"{fi.path}:{sym.line_start} {sym.kind} {sym.qualname}"
        for fi in index.values()
        for sym in fi.symbols
        if sym.name == short or sym.qualname == name
    ]
    uses = ws.git.grep(rev or ws.rev, rf"[:.]{short}\(|\b{short}\(", "*.lua", max_count=60)
    body = (
        "definitions:\n"
        + ("\n".join(defs[:40]) or "none")
        + "\n\nreferences:\n"
        + ("\n".join(uses) or "none")
    )
    return _limit(ws, body)


def lua_deps(ws: Workspace, file: str, rev: str | None = None) -> str:
    """Public API stubs of the modules/components a file depends on."""
    fi = index_file(ws, normalize_rel(file), rev)
    index = index_codebase(ws, rev)
    targets = [f"{r}.lua" for r in fi.requires] + [f"components/{c}.lua" for c in fi.components]
    blocks: list[str] = []
    for target in dict.fromkeys(targets):
        dep = index.get(target)
        if dep is None:
            continue
        sigs = [s.signature or s.qualname for s in dep.symbols if s.qualname in set(dep.public)]
        blocks.append(f"## {target} ({dep.domain})\n" + "\n".join(sigs[:40]))
    return _limit(ws, "\n\n".join(blocks) or "no indexed dependencies")


def lua_table_schema(ws: Workspace, file: str, table: str = "", rev: str | None = None) -> str:
    """Structure of a data table (keys, value kinds, samples) or of a generated file."""
    path = normalize_rel(file)
    fi = index_file(ws, path, rev)
    source = ws.git.show(rev or ws.rev, path)
    tables = [s for s in fi.symbols if s.kind == "table" and (not table or s.qualname == table)]
    parts: list[str] = []
    for sym in tables[:12]:
        shape = table_shape(source, sym.line_start, sym.line_end)
        if shape is not None:
            parts.append(f"L{sym.line_start}-{sym.line_end}\n" + shape.render(sym.qualname))
    calls = call_histogram(source)
    if calls:
        parts.append("most repeated calls:\n" + "\n".join(f"{n}× {name}  e.g. {ex}" for name, n, ex in calls))
    return _limit(ws, "\n\n".join(parts) or f"no tables found in {path}")
