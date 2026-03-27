"""
Script tự động cập nhật / thêm mới / đánh dấu xóa Docs dựa trên báo cáo diff.

Cách dùng:
    py update_docs.py [--dry-run] [--filter <action>] [--limit <n>]
"""

import os
import sys
import json
import argparse
import signal
import re
from datetime import datetime
from pathlib import Path

from core.utils.tree import generate_slim_tree
from rag.content import extract_connected_content
from rag.docs import (
    extract_lua_references,
    safe_read_lua,
    compute_source_hash,
    format_connected_section,
)
from prompts.update import build_update_prompt
from core.pipeline.standard import generate_doc
from validator.update.validate_update import validate_update, validate_batch, append_to_validation_log

from llm.paths import BASE_LUA_DIR, BASE_DOCS_DIR
from llm.settings import MODEL_UPDATE as MODEL_NAME

# Lấy chung constant format để parse paths
_WORKSPACE_ROOT = Path(__file__).parents[4]
DOCS_DIR = BASE_DOCS_DIR
SCRIPTS_DIR = BASE_LUA_DIR
DIFF_REPORT = str(_WORKSPACE_ROOT / "data" / "diff_report.json")
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")

stop_requested = False

def handle_sigint(signum, frame):
    global stop_requested
    if not stop_requested:
        print("\n\n[Hệ thống] Đã nhận Ctrl+C! Đang dừng an toàn...")
        stop_requested = True
    else:
        print("\n\n[Hệ thống] Ép buộc dừng ngay!")
        sys.exit(1)

signal.signal(signal.SIGINT, handle_sigint)

def parse_args():
    parser = argparse.ArgumentParser(description="Update Docs with LLM")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only, do not write files or call LLM")
    parser.add_argument("--filter", type=str, choices=["added", "modified", "deleted", "moved"], help="Only process this action type")
    parser.add_argument("--limit", type=int, default=0, help="Max number of files to process")
    return parser.parse_args()

def get_md_path(lua_rel_path: str) -> str:
    """Chuyển path Lua thành path MD tương ứng trong docs/"""
    rel_no_ext = lua_rel_path.replace(".lua", "")
    return os.path.join(DOCS_DIR, f"{rel_no_ext}.md").replace("\\", "/")

def get_category_type(lua_rel_path: str) -> str:
    """Lấy category type (thư mục gốc) từ lua_rel_path"""
    parts = lua_rel_path.split("/")
    return parts[0] if parts else "components"

def update_frontmatter_in_moved_doc(md_path: str, old_path: str, new_path: str, new_hash: str, new_ver: str):
    """Cập nhật source_hash, build_version, change_status cho file MOVED nội dung giống hệt."""
    if not os.path.exists(md_path):
        return

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    in_frontmatter = False
    frontmatter_end_idx = -1

    updated_fields = set()
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
            else:
                frontmatter_end_idx = i
                break

        if in_frontmatter and line.strip() != "---":
            if line.startswith("last_updated:"):
                lines[i] = f"last_updated: {TODAY_DATE}"
                updated_fields.add("last_updated")
            elif line.startswith("build_version:"):
                lines[i] = f"build_version: {new_ver}"
                updated_fields.add("build_version")
            elif line.startswith("change_status:"):
                lines[i] = "change_status: moved"
                updated_fields.add("change_status")
            elif line.startswith("source_hash:"):
                lines[i] = f"source_hash: {new_hash}"
                updated_fields.add("source_hash")
            elif line.startswith("moved_from:"):
                lines[i] = f"moved_from: {old_path}"
                updated_fields.add("moved_from")
            elif line.startswith("moved_in:"):
                lines[i] = f"moved_in: {new_ver}"
                updated_fields.add("moved_in")

    if frontmatter_end_idx > 0:
        # Inject missing fields before closing ---
        missing_fields = []
        if "moved_from" not in updated_fields:
            missing_fields.append(f"moved_from: {old_path}")
        if "moved_in" not in updated_fields:
            missing_fields.append(f"moved_in: {new_ver}")

        if missing_fields:
            for field in reversed(missing_fields):
                lines.insert(frontmatter_end_idx, field)
            frontmatter_end_idx += len(missing_fields)

        # Thêm notice sau ## Overview
        for i, line in enumerate(lines[frontmatter_end_idx:]):
            idx = frontmatter_end_idx + i
            if line.startswith("# "):
                # Chèn moved notice sau title
                notice = f"\n> [!NOTE]\n> **Moved in build {new_ver}** — Source file relocated from `{old_path}` → `{new_path}`. No logic changes.\n"
                lines.insert(idx + 1, notice)
                break

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def main():
    args = parse_args()

    if not os.path.exists(DIFF_REPORT):
        print(f"[Lỗi] Không tìm thấy {DIFF_REPORT}. Hãy chạy get_diff_update.py trước.")
        return

    with open(DIFF_REPORT, "r", encoding="utf-8") as f:
        report = json.load(f)

    old_ver = report["version"]["old"]
    new_ver = report["version"]["new"]
    changes = report["changes"]

    if args.filter:
        changes = [c for c in changes if c["action"] == args.filter]

    # Lọc chỉ giữ file .lua
    def _is_lua(c):
        p = c.get("path") or c.get("new_path") or c.get("old_path") or ""
        return p.endswith(".lua")

    non_lua = [c for c in changes if not _is_lua(c)]
    if non_lua:
        print(f"[update_docs] Bỏ qua {len(non_lua)} file không phải .lua")
    changes = [c for c in changes if _is_lua(c)]

    # Ưu tiên: MOVED(false) -> MOVED(true) -> ADDED -> MODIFIED -> DELETED
    def sort_key(c):
        priority = {"moved": 1 if not c.get("content_changed", False) else 2, "added": 3, "modified": 4, "deleted": 5}
        return priority.get(c["action"], 9)

    changes.sort(key=sort_key)

    if args.limit > 0:
        changes = changes[:args.limit]

    print("=" * 60)
    print(f"[update_docs] Chạy update docs pipeline cho build {new_ver}")
    print(f"  Chế độ: {'Dry-run' if args.dry_run else 'Thực thi'}")
    print(f"  File cần xử lý: {len(changes)}")
    print("=" * 60)

    file_tree = generate_slim_tree(SCRIPTS_DIR, max_depth=3)

    stats = {"added": 0, "modified": 0, "deleted": 0, "moved": 0, "failed": 0}

    for idx, c in enumerate(changes):
        if stop_requested:
            break

        action = c["action"]
        print(f"\n[{idx+1}/{len(changes)}] Xử lý {action.upper()}: ", end="")

        path = c.get("path") or c.get("new_path") or c.get("old_path")
        if not path:
            print(f"  - Lỗi: Không xác định được đường dẫn cho thay đổi này")
            stats["failed"] += 1
            continue

        old_path = c.get("old_path", "")
        new_path = c.get("new_path", path)
        print(path)

        rel_no_ext = path.replace(".lua", "")
        comp_name = os.path.basename(rel_no_ext)
        comp_title = comp_name.replace("_", " ").title()

        display_filepath = f"./{path}"
        category_type = get_category_type(path)
        md_filepath = get_md_path(path)

        # 1. MOVED (content_changed: false)
        if action == "moved" and not c.get("content_changed", False):
            old_md = get_md_path(old_path)
            if not os.path.exists(old_md):
                print(f"  - Bỏ qua: Không tìm thấy doc cũ {old_md}")
                stats["failed"] += 1
                continue

            if not args.dry_run:
                dirname = os.path.dirname(md_filepath)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                if old_md != md_filepath:
                    os.rename(old_md, md_filepath)

                # Fetch new hash directly
                lua_path = os.path.join(SCRIPTS_DIR, new_path)
                lua_code = safe_read_lua(lua_path)
                new_hash = compute_source_hash(lua_code) if lua_code else c.get("new_hash", "")

                update_frontmatter_in_moved_doc(md_filepath, old_path, new_path, new_hash, new_ver)
                print(f"  - Đã đổi tên và cập nhật doc ({old_md} -> {md_filepath})")

                # Validation for MOVED (no content change)
                errors = validate_update(
                    filepath=md_filepath,
                    action=action,
                    meta={
                        "build_version": new_ver,
                        "old_path": old_path,
                        "new_path": new_path,
                        "source_hash": new_hash,
                        "content_changed": False,
                        "unified_diff": ""
                    }
                )
                if errors:
                    hard_errors = [e for e in errors if not e.startswith("[warning")]
                    warnings = [e for e in errors if e.startswith("[warning")]
                    if hard_errors:
                        print(f"  - Validation FAILED ({len(hard_errors)} errors):")
                        for e in hard_errors: print(f"    {e}")
                        append_to_validation_log(md_filepath, action, errors)
                    if warnings:
                        for w in warnings: print(f"    ⚠ {w}")
            else:
                print(f"  - (Dry-run) Rename {old_md} -> {md_filepath} & Update Frontmatter")
            stats[action] += 1
            continue

        # Đọc dữ liệu Lua cho các thay đổi truy xuất LLM
        lua_code = ""
        connected_section = ""
        connected_content = ""
        source_hash = ""

        if action in ["added", "modified", "moved"]:
            lua_path = os.path.join(SCRIPTS_DIR, path)
            lua_code = safe_read_lua(lua_path)
            if lua_code is None:
                print(f"  - Lỗi: Không thể đọc source {lua_path}")
                stats["failed"] += 1
                continue

            source_hash = compute_source_hash(lua_code)
            lua_refs = extract_lua_references(lua_code, path)
            connected_section = format_connected_section(lua_refs)
            connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)

        existing_doc = ""
        if action in ["modified", "deleted"] or (action == "moved" and c.get("content_changed", True)):
            old_md = get_md_path(old_path if old_path else path)
            try:
                with open(old_md, "r", encoding="utf-8") as f:
                    existing_doc = f.read()
            except FileNotFoundError:
                print(f"  - Cảnh báo: Không thể đọc existing doc tại {old_md}")
                if action in ["modified", "moved"]:
                    print(f"    Sẽ fallback sang action 'added'.")
                    action = "added"

        # Bug 4: Extract source_hash for DELETED
        if action == "deleted" and existing_doc:
            m = re.search(r'^source_hash:\s*(.+)$', existing_doc, re.MULTILINE)
            source_hash = m.group(1).strip() if m else ""

        # Extract unified diff
        unified_diff = c.get("unified_diff", "")

        # Build prompt
        prompt = build_update_prompt(
            action=action,
            comp_name=comp_name,
            comp_title=comp_title,
            display_filepath=display_filepath,
            lua_code=lua_code,
            connected_section=connected_section,
            connected_content=connected_content,
            source_hash=source_hash,
            existing_doc=existing_doc,
            unified_diff=unified_diff,
            old_path=old_path,
            new_path=new_path,
            file_tree=file_tree,
            today_date=TODAY_DATE,
            build_version=new_ver,
            old_version=old_ver,
            category_type=category_type,
            content_changed=c.get("content_changed", True),
        )

        if args.dry_run:
            print("  --- PROMPT PREVIEW ---")
            print(prompt[:1000] + "\n...[TRUNCATED]")
            stats[action] += 1
        else:
            print("  - Đang gọi LLM...")

            # Nếu là file moved, cần rename doc trước khi ghi đè
            if action == "moved" or (c["action"] == "moved" and action == "added"):
                old_md = get_md_path(old_path)
                dirname = os.path.dirname(md_filepath)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                if old_md != md_filepath and os.path.exists(old_md):
                    os.rename(old_md, md_filepath)

            if action == "added":
                dirname = os.path.dirname(md_filepath)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)

            result = generate_doc(
                prompt=prompt,
                md_filepath=md_filepath,
                model_name=MODEL_NAME,
                sleep_time=20,
            )
            if result:
                # Validation for LLM generation
                errors = validate_update(
                    filepath=md_filepath,
                    action=action,
                    meta={
                        "build_version": new_ver,
                        "old_path": old_path,
                        "new_path": new_path,
                        "source_hash": source_hash,
                        "content_changed": c.get("content_changed", True),
                        "unified_diff": unified_diff
                    }
                )

                if errors:
                    hard_errors = [e for e in errors if not e.startswith("[warning")]
                    warnings = [e for e in errors if e.startswith("[warning")]
                    if hard_errors:
                        print(f"  - Validation FAILED ({len(hard_errors)} errors):")
                        for e in hard_errors: print(f"    {e}")
                        append_to_validation_log(md_filepath, action, errors)
                    if warnings:
                        for w in warnings: print(f"    ⚠ {w}")

                stats[action] += 1
                print(f"  - Thành công: {md_filepath}")
            else:
                stats["failed"] += 1

    print("\n" + "=" * 60)
    print(f"[Thống kê] Hoàn tất!")
    print(f"  Added    : {stats['added']} file")
    print(f"  Modified : {stats['modified']} file")
    print(f"  Deleted  : {stats['deleted']} file")
    print(f"  Moved    : {stats['moved']} file")
    print(f"  Failed   : {stats['failed']} file")
    print("=" * 60)

    # Level B: Batch Validation
    print("\n[update_docs] Chạy Batch Validation...")
    batch_errors = validate_batch(DIFF_REPORT, DOCS_DIR)
    if batch_errors:
        print(f"  - Batch validation FAILED with {len(batch_errors)} errors (Check log).")
    else:
        print("  - Batch validation PASSED.")
    print("=" * 60)

if __name__ == "__main__":
    main()
