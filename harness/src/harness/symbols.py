"""How each Lua symbol kind is presented in a documentation page."""

from __future__ import annotations

from harness.lua_parse import LuaSymbol

# symbol kind → parent "##" section that holds its "###" entry
SECTION_BY_KIND = {
    "class": "## Main functions",
    "method": "## Main functions",
    "function": "## Main functions",
    "state": "## States",
    "event_handler": "## Events & listeners",
    "action": "## Action handlers",
    "prefab": "## Prefabs",
    "table": "## Structure",
}

BASE_SECTIONS = ("## Overview", "## Usage example", "## Dependencies & tags")
DATA_SECTIONS = ("## Overview", "## Structure", "## Usage example")
OVERVIEW_SECTIONS = ("## Overview", "## Pages")


def _params(sym: LuaSymbol) -> str:
    if "(" not in sym.signature:
        return "()"
    inner = sym.signature[sym.signature.index("(") :]
    return inner.replace("self, ", "", 1) if sym.kind == "class" else inner


def canonical_heading(sym: LuaSymbol) -> str:
    """Exact ``###`` heading a page must contain for ``sym`` (checked by COVERAGE)."""
    if sym.kind in ("method", "function", "class"):
        return f"### `{sym.name}{_params(sym)}`"
    if sym.kind == "state":
        return f"### `state: {sym.name}`"
    if sym.kind == "event_handler":
        return f"### `event: {sym.name}`"
    if sym.kind == "action":
        return f"### `ACTIONS.{sym.name}`"
    if sym.kind == "prefab":
        return f"### `prefab: {sym.name}`"
    return f"### `{sym.qualname}`"


def required_sections(page_kind: str, kinds: set[str]) -> list[str]:
    """Ordered ``##`` sections for a page given the symbol kinds it documents."""
    if page_kind == "overview":
        return list(OVERVIEW_SECTIONS)
    if page_kind == "data":
        return list(DATA_SECTIONS)
    sections = list(BASE_SECTIONS)
    for kind in ("prefab", "class", "method", "function", "state", "event_handler", "action", "table"):
        section = SECTION_BY_KIND[kind]
        if kind in kinds and section not in sections:
            sections.append(section)
    if "## Events & listeners" not in sections:
        sections.append("## Events & listeners")
    return sections
