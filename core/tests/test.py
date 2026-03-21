"""
Test script — chạy prompt trên 1 file duy nhất để kiểm tra.
Dùng chung build_prompt() từ prompt.py, config riêng cho test.
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

# === CẤU HÌNH TEST ===
TEST_FILE = "combat.lua"
LUA_DIR = "./dst-scripts/components"
DOCS_DIR = "./dst-api-webdocs/docs/components"
VERSION = "714014"
CATEGORY_TYPE = "component"
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")
FILE_TREE = generate_slim_tree("./dst-scripts", max_depth=6)

os.makedirs(DOCS_DIR, exist_ok=True)

# --- Tìm và đọc file ---
filepath = os.path.join(LUA_DIR, TEST_FILE)
display_filepath = filepath.replace("./dst-scripts", ".").replace("\\", "/")

lua_code = safe_read_lua(filepath)
if lua_code is None:
    print(f"[Lỗi] Không đọc được file: {filepath}")
    exit(1)

comp_name = TEST_FILE.replace(".lua", "")
comp_title = comp_name.replace("_", " ").title()
source_hash = compute_source_hash(lua_code)

# --- Trích xuất tham chiếu ---
lua_refs = extract_lua_references(lua_code, TEST_FILE)

if lua_refs:
    print(f"[REF] Tìm thấy {len(lua_refs)} file liên quan")
else:
    print(f"[REF] Không tìm thấy tham chiếu nào")

connected_section = format_connected_section(lua_refs)

# --- Trích xuất nội dung function/property từ file liên quan ---
connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
if connected_content:
    content_lines = connected_content.count('\n') + 1
    print(f"[FNC] Đã trích xuất {content_lines} dòng source code từ file liên quan")
else:
    print(f"[FNC] Không trích xuất được nội dung function nào")

# --- Tạo prompt ---
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

# --- Ghi ra file test.md ---
with open("test.md", "w", encoding="utf-8") as f:
    f.write(prompt)

print(f"\n[OK] Đã xuất prompt cho '{TEST_FILE}' ra file test.md ({len(prompt)} ký tự)")
