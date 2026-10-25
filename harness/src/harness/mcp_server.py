"""``dst-tools`` MCP server (stdio). OpenCode launches it from ``.opencode/opencode.json``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from harness.tools import api

TOOLS: dict[str, Callable[..., str]] = {
    # source (G3)
    "lua_outline": api.lua_outline,
    "lua_symbol": api.lua_symbol,
    "lua_read": api.lua_read,
    "lua_grep": api.lua_grep,
    "lua_refs": api.lua_refs,
    "lua_deps": api.lua_deps,
    "lua_table_schema": api.lua_table_schema,
    # plan (G2)
    "index_summary": api.index_summary,
    "plan_get": api.plan_get,
    "plan_put": api.plan_put,
    "plan_remove": api.plan_remove,
    "validate_plan": api.validate_plan_tool,
    # pages (G1, G3)
    "page_checklist": api.page_checklist,
    "doc_read": api.doc_read,
    "doc_write_section": api.doc_write_section,
    "doc_set_meta": api.doc_set_meta,
    "notes_read": api.notes_read,
    "notes_write": api.notes_write,
    # verdict (G4, G7)
    "run_checks": api.run_checks_tool,
    "verdict": api.verdict,
    "ledger_add": api.ledger_add,
    "ledger_list": api.ledger_list,
    "ledger_resolve": api.ledger_resolve,
    # builds / diffs (G5)
    "build_list": api.build_list,
    "patch_notes": api.patch_notes,
    "diff_overview": api.diff_overview,
    "symbol_diff": api.symbol_diff,
    "impact_map": api.impact_map,
    # memory (G6)
    "memory_search": api.memory_search,
    "memory_add": api.memory_add,
}


def _safe(fn: Callable[..., str]) -> Callable[..., str]:
    """Turn exceptions into tool errors the agent can read instead of crashing the server."""

    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # report every failure back to the model
            return f"ERROR {type(exc).__name__}: {exc}"

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.__signature__ = __import__("inspect").signature(fn)  # type: ignore[attr-defined]
    return wrapper


def build_server() -> Any:
    try:
        from mcp.server.mcpserver import MCPServer as Server  # mcp >= 2
    except ImportError:  # pragma: no cover - mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server  # type: ignore[no-redef,attr-defined,unused-ignore]
    server = Server("dst-tools", instructions="Deterministic tools for documenting DST Lua scripts.")
    for name, fn in TOOLS.items():
        server.tool(name=name, description=(fn.__doc__ or name).strip())(_safe(fn))
    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
