"""
Test script — runs the prompt on a single file for inspection.
Shares build_prompt() from prompt.py, with test-specific configuration.
"""

import os
from datetime import datetime
from core.utils.tree import generate_slim_tree
from rag.content import extract_connected_content
from rag.docs import (
    extract_lua_references,
    safe_read_lua,
    compute_source_hash,
    format_connected_section,
)
from prompts.standard import build_prompt

# === TEST CONFIGURATION ===
TEST_FILE = "combat.lua"
LUA_DIR = "./dst-scripts/components"
DOCS_DIR = "./dst-api-webdocs/docs/components"
VERSION = "714014"
CATEGORY_TYPE = "component"
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")
FILE_TREE = generate_slim_tree("./dst-scripts", max_depth=6)

os.makedirs(DOCS_DIR, exist_ok=True)

# --- Find and read file ---
filepath = os.path.join(LUA_DIR, TEST_FILE)
display_filepath = filepath.replace("./dst-scripts", ".").replace("\\", "/")

lua_code = safe_read_lua(filepath)
if lua_code is None:
    print(f"[Error] Could not read file: {filepath}")
    exit(1)

comp_name = TEST_FILE.replace(".lua", "")
comp_title = comp_name.replace("_", " ").title()
source_hash = compute_source_hash(lua_code)

# --- Extract references ---
lua_refs = extract_lua_references(lua_code, TEST_FILE)

if lua_refs:
    print(f"[REF] Found {len(lua_refs)} connected files")
else:
    print(f"[REF] No references found")

connected_section = format_connected_section(lua_refs)

# --- Extract function/property content from connected files ---
connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
if connected_content:
    content_lines = connected_content.count('\n') + 1
    print(f"[FNC] Extracted {content_lines} lines of source code from connected files")
else:
    print(f"[FNC] No function content extracted")

# --- Build prompt ---
prompt = build_prompt(
    comp_name=comp_name,
    comp_title=comp_title,
    display_filepath=display_filepath,
    lua_code=lua_code,
    connected_section=connected_section,
    connected_content=connected_content,
    source_hash=source_hash,
    file_tree=FILE_TREE,
    today_date=TODAY_DATE,
    version=VERSION,
    category_type=CATEGORY_TYPE,
)

# --- Write to test.md ---
with open("test.md", "w", encoding="utf-8") as f:
    f.write(prompt)

print(f"\n[OK] Wrote prompt for '{TEST_FILE}' to test.md ({len(prompt)} chars)")
