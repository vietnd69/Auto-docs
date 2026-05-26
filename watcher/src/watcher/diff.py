"""
Script phát hiện file .lua thay đổi giữa các times cập nhật dst-scripts.

Cách dùng:
    mod-watcher

Flow:
    1. Đọc version_log.txt để lấy version hiện tại và version trước
    2. Quét dst-scripts/ -> tính SHA-256 và nén content_z cho mỗi file
    3. So sánh với snapshot cũ (diff_tracker.json)
       - Auto-migrate data format cũ nếu cần
    4. Phân loại: ADDED / MODIFIED / DELETED / MOVED
    5. Tính unified diff cho các file bị thay đổi (MODIFIED / MOVED có đổi nội dung)
    6. Ghi kết quả vào diff_report.json (và diff_log.txt để con người dễ đọc)
    7. Lưu snapshot mới cho times after

Lưu ý:
    - version_log.txt được cập nhật THỦ CÔNG trước khi chạy script
    - Script dùng diff_tracker.json riêng để lưu snapshot (hash + content_z)
"""

import os
import json
import hashlib
import base64
import zlib
import difflib
from datetime import datetime
from pathlib import Path

# === CONSTANTS ===
_WORKSPACE_ROOT = Path(__file__).parents[3]
_DATA_DIR = _WORKSPACE_ROOT / "data"
DIFF_TRACKER = str(_DATA_DIR / "diff_tracker.json")
DIFF_LOG = str(_DATA_DIR / "diff_log.txt")
DIFF_REPORT = str(_DATA_DIR / "diff_report.json")
VERSION_LOG = str(_DATA_DIR / "version_log.txt")
SCRIPTS_DIR = str(_WORKSPACE_ROOT / "dst-scripts")

EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".agent"}

def read_version_log(path: str) -> dict:
    """Đọc version_log.txt, trả về dict {now, previous}."""
    result = {"now": "unknown", "previous": "none"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("now version:"):
                    result["now"] = line.split(":", 1)[1].strip()
                elif line.startswith("previous version:"):
                    result["previous"] = line.split(":", 1)[1].strip()
    except FileNotFoundError:
        print(f"[Error] Không tìm thấy {path}")
    return result

def compute_file_hash_and_content(filepath: str) -> tuple:
    """Tính SHA-256 hash và tạo content_z của file."""
    h = hashlib.sha256()
    size = os.path.getsize(filepath)
    with open(filepath, "rb") as f:
        content = f.read()
        h.update(content)

    file_hash = h.hexdigest()
    content_z = base64.b64encode(zlib.compress(content)).decode("ascii")
    return file_hash, content_z, size


def scan_files(root_dir: str) -> dict:
    """
    Quét toàn bộ file trong root_dir (đệ quy).
    Trả về dict {relative_path: {"hash": sha256_hash, "content_z": content_z}}.
    """
    file_data = {}
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
            try:
                file_hash, content_z, size = compute_file_hash_and_content(full_path)
                file_data[rel_path] = {
                    "hash": file_hash,
                    "content_z": content_z,
                    "size": size
                }
            except Exception as e:
                print(f"  [Error] Không đọc được {rel_path}: {e}")
    return file_data

def load_tracker(path: str) -> dict:
    """Load snapshot cũ từ diff_tracker.json và migrate nếu là format cũ."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not data:
                return {}

            # Check for old format: if first value is string (hash)
            first_val = next(iter(data.values()))
            if isinstance(first_val, str):
                print("  [Thông báo] Phát hiện format diff_tracker.json cũ, đang migrate...")
                new_data = scan_files(SCRIPTS_DIR)
                save_tracker(path, new_data)
                return new_data
            else:
                return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_tracker(path: str, data: dict):
    """Lưu snapshot mới vào diff_tracker.json."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def decode_content(content_z: str) -> bytes:
    return zlib.decompress(base64.b64decode(content_z))

def compute_diff(old_data: dict, new_data: dict) -> list:
    """
    So sánh 2 snapshot, phát hiện ADDED, DELETED, MODIFIED, MOVED.
    Trả về list các thay đổi (dùng cho diff_report.json).
    """
    old_keys = set(old_data.keys())
    new_keys = set(new_data.keys())

    candidates_added = set(new_keys - old_keys)
    candidates_deleted = set(old_keys - new_keys)
    modified_keys = [k for k in (old_keys & new_keys) if old_data[k]["hash"] != new_data[k]["hash"]]

    changes = []

    # Process MODIFIED
    for path in modified_keys:
        old_content = decode_content(old_data[path]["content_z"]).decode("utf-8", errors="replace")
        new_content = decode_content(new_data[path]["content_z"]).decode("utf-8", errors="replace")

        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}"
        ))

        plus_lines = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        minus_lines = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

        changes.append({
            "action": "modified",
            "path": path,
            "old_hash": old_data[path]["hash"],
            "new_hash": new_data[path]["hash"],
            "diff_summary": f"+{plus_lines} lines, -{minus_lines} lines",
            "unified_diff": "".join(diff_lines)
        })

    # Move detection
    # 1. Exact match lookup
    hash_to_added_path = {}
    for path in candidates_added:
        file_hash = new_data[path]["hash"]
        if file_hash not in hash_to_added_path:
            hash_to_added_path[file_hash] = []
        hash_to_added_path[file_hash].append(path)

    for old_path in list(candidates_deleted):
        old_hash = old_data[old_path]["hash"]
        if old_hash in hash_to_added_path and hash_to_added_path[old_hash]:
            # Exact match found -> MOVED (content_changed: false)
            new_path = hash_to_added_path[old_hash].pop(0)
            candidates_added.remove(new_path)
            candidates_deleted.remove(old_path)

            changes.append({
                "action": "moved",
                "old_path": old_path,
                "new_path": new_path,
                "content_changed": False
            })

    # 2. Similarity Match & remaining files
    actual_deleted = set(candidates_deleted)
    actual_added = set(candidates_added)

    for old_path in list(actual_deleted):
        old_content = decode_content(old_data[old_path]["content_z"]).decode("utf-8", errors="replace")
        best_match_path = None
        best_ratio = 0.0

        old_size = old_data[old_path].get("size", 0)

        for new_path in actual_added:
            new_size = new_data[new_path].get("size", 0)

            # Skip if size difference is more than 50%
            if old_size > 0 and new_size > 0:
                if abs(old_size - new_size) / max(old_size, new_size) > 0.5:
                    continue

            new_content = decode_content(new_data[new_path]["content_z"]).decode("utf-8", errors="replace")
            ratio = difflib.SequenceMatcher(None, old_content, new_content).quick_ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match_path = new_path

        if best_ratio >= 0.8 and best_match_path:
            # MOVED with content change
            new_content = decode_content(new_data[best_match_path]["content_z"]).decode("utf-8", errors="replace")
            diff_lines = list(difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{old_path}",
                tofile=f"b/{best_match_path}"
            ))
            plus_lines = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
            minus_lines = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

            changes.append({
                "action": "moved",
                "old_path": old_path,
                "new_path": best_match_path,
                "content_changed": True,
                "diff_summary": f"+{plus_lines} lines, -{minus_lines} lines",
                "unified_diff": "".join(diff_lines)
            })

            actual_deleted.remove(old_path)
            actual_added.remove(best_match_path)

    # Process remaining ADDED
    for path in sorted(list(actual_added)):
        changes.append({
            "action": "added",
            "path": path,
            "hash": new_data[path]["hash"]
        })

    # Process remaining DELETED
    for path in sorted(list(actual_deleted)):
        changes.append({
            "action": "deleted",
            "path": path,
            "hash": old_data[path]["hash"]
        })

    return changes

def write_diff_log(log_path: str, report_path: str, changes: list, version_info: dict):
    """Ghi diff_log.txt và diff_report.json."""
    now_ver = version_info["now"]
    prev_ver = version_info["previous"]
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Generate JSON format
    report = {
        "version": {"old": prev_ver, "new": now_ver},
        "date": datetime.now().strftime("%Y-%m-%d"),
        "changes": changes
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Generate Text Log format
    lines = []
    lines.append(f"=== Update: {prev_ver} -> {now_ver} ===")
    lines.append(f"Date: {today}")
    lines.append("")

    added = [c for c in changes if c["action"] == "added"]
    modified = [c for c in changes if c["action"] == "modified"]
    deleted = [c for c in changes if c["action"] == "deleted"]
    moved = [c for c in changes if c["action"] == "moved"]

    # ADDED
    lines.append(f"[ADDED] {len(added)} files:")
    if added:
        for c in added:
            lines.append(f"  - {c['path']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # MODIFIED
    lines.append(f"[MODIFIED] {len(modified)} files:")
    if modified:
        for c in modified:
            lines.append(f"  - {c['path']} ({c.get('diff_summary', '')})")
    else:
        lines.append("  (none)")
    lines.append("")

    # DELETED
    lines.append(f"[DELETED] {len(deleted)} files:")
    if deleted:
        for c in deleted:
            lines.append(f"  - {c['path']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # MOVED
    lines.append(f"[MOVED] {len(moved)} files:")
    if moved:
        for c in moved:
            if c["content_changed"]:
                lines.append(f"  - {c['old_path']} -> {c['new_path']} ({c.get('diff_summary', '')})")
            else:
                lines.append(f"  - {c['old_path']} -> {c['new_path']} (identical)")
    else:
        lines.append("  (none)")
    lines.append("")

    total = len(changes)
    lines.append(f"Total: {total} changes")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return added, modified, deleted, moved


def main():
    print("=" * 60)
    print("[watcher.diff] Phát hiện thay đổi trong dst-scripts")
    print("=" * 60)

    # 1. Đọc version
    version_info = read_version_log(VERSION_LOG)
    print(f"  Version hiện tại : {version_info['now']}")
    print(f"  Version trước    : {version_info['previous']}")

    # 2. Load snapshot cũ
    old_data = load_tracker(DIFF_TRACKER)
    if old_data:
        print(f"  Snapshot cũ      : {len(old_data)} files")
    else:
        print(f"  Snapshot cũ      : (chưa có — times chạy đầu tiên)")

    # 3. Quét file hiện tại
    print(f"\n  Đang quét {SCRIPTS_DIR}...")
    new_data = scan_files(SCRIPTS_DIR)
    print(f"  Tìm thấy         : {len(new_data)} files")

    # 4. Tính diff
    changes = compute_diff(old_data, new_data)

    # 5. Ghi diff_log.txt & diff_report.json
    added, modified, deleted, moved = write_diff_log(DIFF_LOG, DIFF_REPORT, changes, version_info)

    print(f"\n--- Kết quả ---")
    print(f"  [ADDED]    {len(added)} files")
    print(f"  [MODIFIED] {len(modified)} files")
    print(f"  [DELETED]  {len(deleted)} files")
    print(f"  [MOVED]    {len(moved)} files")

    print(f"  [TOTAL]    {len(changes)} changes")

    print(f"\n  Đã ghi: {DIFF_LOG}")
    print(f"  Đã ghi: {DIFF_REPORT}")

    # 6. Lưu snapshot mới
    save_tracker(DIFF_TRACKER, new_data)
    print(f"  Đã lưu snapshot: {DIFF_TRACKER}")

    # 7. Cập nhật vector store (chỉ khi có thay đổi)
    if changes:
        try:
            from rag.indexer import reindex
            print(f"\n--- Cập nhật vector store ---")
            stats = reindex()
            print(
                f"  Vector store: {stats['processed']} indexed, "
                f"{stats['skipped']} skipped, "
                f"{stats['total_chunks']} chunks"
            )
        except Exception as e:
            print(f"  [WARN] Không thể cập nhật vector store: {e}")

    print("=" * 60)


if __name__ == "__main__":
    main()
