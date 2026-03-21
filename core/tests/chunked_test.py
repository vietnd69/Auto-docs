"""
Test script cho chunked pipeline — chạy trên 1 file dài để kiểm tra prompt.
Giống test.py nhưng dùng chunked_prompt thay vì prompt.py.
Ghi ra nhiều file: test_chunk_1.md, test_chunk_2.md, ..., test_merge.md
"""

import os
import sys
from datetime import datetime
from core.utils.tree import generate_slim_tree
from rag.content import extract_connected_content
from rag.docs import (
    extract_lua_references,
    safe_read_lua,
    compute_source_hash,
    format_connected_section,
)
from core.pipeline.chunking import needs_chunking, split_lua_into_chunks
from prompts.chunked import build_chunk_prompt, build_merge_prompt
from prompts.pre_synthesis import PreSynthesisResult

# === CẤU HÌNH TEST ===
TEST_FILE = "maxwellhome.lua"
LUA_DIR = "./dst-scripts/map/static_layouts"
VERSION = "714014"
CATEGORY_TYPE = "map"
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")
FILE_TREE = generate_slim_tree("./dst-scripts", max_depth=3)

# --- Đọc file ---
filepath = os.path.join(LUA_DIR, TEST_FILE)
display_filepath = filepath.replace("./dst-scripts", ".").replace("\\", "/")

lua_code = safe_read_lua(filepath)
if lua_code is None:
    print(f"[Lỗi] Không đọc được file: {filepath}")
    sys.exit(1)

total_lines = lua_code.count("\n") + 1
comp_name = TEST_FILE.replace(".lua", "")
comp_title = comp_name.replace("_", " ").title()
source_hash = compute_source_hash(lua_code)

print(f"File: {TEST_FILE} ({total_lines} dòng)")
print(f"Cần chunking: {needs_chunking(lua_code)}")

# --- Trích xuất tham chiếu ---
lua_refs = extract_lua_references(lua_code, TEST_FILE)
connected_section = format_connected_section(lua_refs)

if lua_refs:
    print(f"[REF] {len(lua_refs)} file liên quan")
else:
    print(f"[REF] Không có tham chiếu")

connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
if connected_content:
    print(f"[FNC] {connected_content.count(chr(10)) + 1} dòng source code")

# --- Chia chunks ---
if not needs_chunking(lua_code):
    print(f"\n[Thông báo] File chỉ có {total_lines} dòng, không cần chunking.")
    print("Dùng test.py cho file ngắn.")
    sys.exit(0)

chunks = split_lua_into_chunks(lua_code)
total_chunks = len(chunks)
print(f"\nĐã chia thành {total_chunks} chunks:")

for i, chunk in enumerate(chunks, 1):
    chunk_lines = chunk.count("\n") + 1
    print(f"  Chunk {i}: {chunk_lines} dòng")

# --- Tạo prompt cho từng chunk ---
print("\n" + "=" * 60)
print("Đang tạo prompt cho từng chunk...")

chunk_prompts = []
for i, chunk_code in enumerate(chunks, 1):
    prompt = build_chunk_prompt(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        chunk_code=chunk_code,
        chunk_index=i,
        total_chunks=total_chunks,
        today_date=TODAY_DATE,
        version=VERSION,
        category_type=CATEGORY_TYPE,
    )
    chunk_prompts.append(prompt)

    # Ghi ra file test
    filename = f"test_chunk_{i}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"  Đã ghi {filename} ({len(prompt)} ký tự)")

# --- Tạo merge prompt (dùng fake PreSynthesisResult) ---
print("\nĐang tạo merge prompt (với fake PreSynthesisResult)...")

# Tạo fake PreSynthesisResult để test cấu trúc merge prompt
fake_presynthesis = PreSynthesisResult(
    tags=["map", "layout", "static"],
    system_scope="world",
    dependencies=[],
    partial_descriptions=[f"Chunk {i} placeholder description." for i in range(1, total_chunks + 1)],
    functions=[{"name": f"ExampleFunc_{i}", "params": "", "description": f"Placeholder for chunk {i}", "returns": "nil", "error_states": "None"} for i in range(1, total_chunks + 1)],
    events_listens=[],
    events_pushes=[],
    constructor_properties=[],
)

merge_prompt = build_merge_prompt(
    comp_name=comp_name,
    comp_title=comp_title,
    display_filepath=display_filepath,
    presynthesis=fake_presynthesis,
    source_hash=source_hash,
    today_date=TODAY_DATE,
    version=VERSION,
    category_type=CATEGORY_TYPE,
)

with open("test_merge.md", "w", encoding="utf-8") as f:
    f.write(merge_prompt)
print(f"  Đã ghi test_merge.md ({len(merge_prompt)} ký tự)")

# --- Thống kê ---
print("\n" + "=" * 60)
print(f"[OK] Xuất xong!")
print(f"  Chunk prompts: test_chunk_1.md → test_chunk_{total_chunks}.md")
print(f"  Merge prompt:  test_merge.md")
total_chars = sum(len(p) for p in chunk_prompts) + len(merge_prompt)
print(f"  Tổng prompt:   {total_chars:,} ký tự")
