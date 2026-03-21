"""Shared utilities for validator package.

Provides path resolution between .md docs and .lua source files,
and connected content extraction for the content validation loop.
"""

import os
from pathlib import Path

from llm.paths import BASE_LUA_DIR, BASE_DOCS_DIR
from rag.docs import extract_lua_references, format_connected_section, safe_read_lua
from rag.content import extract_connected_content

DOCS_DIR = Path(BASE_DOCS_DIR)
LUA_DIR = Path(BASE_LUA_DIR)


def resolve_lua_path(md_filepath: str) -> str | None:
    """
    Map .md doc path to corresponding .lua source path.
    e.g. dst-api-webdocs/docs/map/rooms/four.md -> dst-scripts/map/rooms/four.lua
    Returns None if Lua file doesn't exist or path can't be resolved.
    """
    path = Path(md_filepath)
    try:
        docs_parts = path.parts
        docs_idx = docs_parts.index("docs")
        rel_parts = docs_parts[docs_idx + 1:]
        lua_rel_path = "/".join(rel_parts).replace(".md", ".lua")
        lua_filepath = os.path.join(str(LUA_DIR), lua_rel_path)
        if os.path.exists(lua_filepath):
            return lua_filepath
        return None
    except ValueError:
        return None


def resolve_connected_content(lua_filepath: str) -> tuple[str, str]:
    """
    Extract connected section + connected content from Lua source.
    Calls rag.docs.extract_lua_references() + rag.docs.format_connected_section()
    + rag.content.extract_connected_content()
    Returns (connected_section, connected_content).
    """
    lua_code = safe_read_lua(lua_filepath)
    if lua_code is None:
        return "", ""
    comp_name = Path(lua_filepath).stem
    lua_refs = extract_lua_references(lua_code, comp_name + ".lua")
    connected_section = format_connected_section(lua_refs)
    connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
    return connected_section, connected_content
