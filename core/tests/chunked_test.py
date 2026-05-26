"""
Test script for the chunked pipeline — runs on a single long file to inspect the prompt.
Similar to test.py but uses chunked_prompt instead of prompt.py.
Writes multiple files: test_chunk_1.md, test_chunk_2.md, ..., test_merge.md
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

# === TEST CONFIGURATION ===
TEST_FILE = "maxwellhome.lua"
LUA_DIR = "./dst-scripts/map/static_layouts"
VERSION = "714014"
CATEGORY_TYPE = "map"
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")
FILE_TREE = generate_slim_tree("./dst-scripts", max_depth=3)

# --- Read file ---
filepath = os.path.join(LUA_DIR, TEST_FILE)
display_filepath = filepath.replace("./dst-scripts", ".").replace("\\", "/")

lua_code = safe_read_lua(filepath)
if lua_code is None:
    print(f"[Error] Could not read file: {filepath}")
    sys.exit(1)

total_lines = lua_code.count("\n") + 1
comp_name = TEST_FILE.replace(".lua", "")
comp_title = comp_name.replace("_", " ").title()
source_hash = compute_source_hash(lua_code)

print(f"File: {TEST_FILE} ({total_lines} lines)")
print(f"Needs chunking: {needs_chunking(lua_code)}")

# --- Extract references ---
lua_refs = extract_lua_references(lua_code, TEST_FILE)
connected_section = format_connected_section(lua_refs)

if lua_refs:
    print(f"[REF] {len(lua_refs)} connected files")
else:
    print(f"[REF] No references")

connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
if connected_content:
    print(f"[FNC] {connected_content.count(chr(10)) + 1} lines of source code")

# --- Split into chunks ---
if not needs_chunking(lua_code):
    print(f"\n[Notice] File only has {total_lines} lines — chunking not needed.")
    print("Use test.py for short files.")
    sys.exit(0)

chunks = split_lua_into_chunks(lua_code)
total_chunks = len(chunks)
print(f"\nSplit into {total_chunks} chunks:")

for i, chunk in enumerate(chunks, 1):
    chunk_lines = chunk.count("\n") + 1
    print(f"  Chunk {i}: {chunk_lines} lines")

# --- Build prompt for each chunk ---
print("\n" + "=" * 60)
print("Building prompt for each chunk...")

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

    # Write to test file
    filename = f"test_chunk_{i}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"  Wrote {filename} ({len(prompt)} chars)")

# --- Build merge prompt (using a fake PreSynthesisResult) ---
print("\nBuilding merge prompt (with fake PreSynthesisResult)...")

# Create a fake PreSynthesisResult to test the merge prompt structure
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
print(f"  Wrote test_merge.md ({len(merge_prompt)} chars)")

# --- Stats ---
print("\n" + "=" * 60)
print(f"[OK] Done!")
print(f"  Chunk prompts: test_chunk_1.md → test_chunk_{total_chunks}.md")
print(f"  Merge prompt:  test_merge.md")
total_chars = sum(len(p) for p in chunk_prompts) + len(merge_prompt)
print(f"  Total prompt:  {total_chars:,} chars")
