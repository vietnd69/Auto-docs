"""
Re-render docs cho các file có thay đổi theo danh sách từ diff_report.json.
Sử dụng pipeline render chuẩn (build_prompt → generate_doc/chunked → validator),
giống hệt main.py nhưng chỉ xử lý các file trong diff.

Cách dùng:
    uv run python -m core.update.docs [--dry-run] [--filter <action>] [--limit <n>] [--no-validate]
"""

import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import core.config as config
from core.pipeline.chunked import process_chunked_file
from core.pipeline.chunking import needs_chunking
from core.pipeline.standard import generate_doc
from core.utils import shutdown
from llm.paths import BASE_DOCS_DIR, BASE_LUA_DIR, DATA_DIR, PROJECT_ROOT
from llm.settings import DEBUG_PROMPTS, MODEL_MAIN as MODEL_NAME
from llm.tokens import count_tokens
from prompts.standard import build_prompt
from rag.content import extract_connected_content
from rag.docs import (
    compute_source_hash,
    extract_lua_references,
    format_connected_section,
    safe_read_lua,
)
from validator.pipeline import PipelineConfig, process_file

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"

# File data-only không có function: re-render không có giá trị (chỉ liệt kê keys).
# Threshold: nếu token Lua >= giá trị này VÀ không có function → patch frontmatter thay vì render.
DATA_ONLY_TOKEN_THRESHOLD = 50_000

_WORKSPACE_ROOT = Path(__file__).parents[4]
DOCS_DIR = BASE_DOCS_DIR
SCRIPTS_DIR = BASE_LUA_DIR
DIFF_REPORT = str(_WORKSPACE_ROOT / "data" / "diff_report.json")
FILE_TRACKER = str(_WORKSPACE_ROOT / "data" / "file_tracker.json")
DIFF_TRACKER = str(_WORKSPACE_ROOT / "data" / "diff_tracker.json")


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Re-render docs for changed files")
    parser.add_argument("--dry-run", action="store_true", help="In prompt, không gọi LLM hay ghi file")
    parser.add_argument("--filter", type=str, choices=["added", "modified", "deleted", "moved"],
                        help="Chỉ xử lý action type này")
    parser.add_argument("--limit", type=int, default=0, help="Số file tối đa cần xử lý")
    parser.add_argument("--no-validate", action="store_true", help="Bỏ qua bước validation")
    parser.add_argument("--force", action="store_true", help="Xử lý lại kể cả file đã gen thành công")
    return parser.parse_args()


def get_md_path(lua_rel_path: str) -> str:
    rel_no_ext = lua_rel_path.replace(".lua", "")
    return os.path.join(DOCS_DIR, f"{rel_no_ext}.md").replace("\\", "/")


def get_category_type(lua_rel_path: str) -> str:
    parts = lua_rel_path.split("/")
    return parts[0] if len(parts) > 1 else "root"


def load_diff_report() -> dict | None:
    if not os.path.exists(DIFF_REPORT):
        print(f"[Lỗi] Không tìm thấy {DIFF_REPORT}. Hãy chạy get_diff_update.py trước.")
        return None
    with open(DIFF_REPORT, "r", encoding="utf-8") as f:
        return json.load(f)


def _update_moved_frontmatter(md_path: str, old_path: str, new_path: str, new_hash: str, new_ver: str):
    """Cập nhật frontmatter cho file moved (không thay đổi nội dung)."""
    if not os.path.exists(md_path):
        return

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    lines = content.splitlines()
    in_fm = False
    fm_end = -1
    updated = set()

    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
            else:
                fm_end = i
                break
        if in_fm and line.strip() != "---":
            if line.startswith("last_updated:"):
                lines[i] = f"last_updated: {today}"
                updated.add("last_updated")
            elif line.startswith("build_version:"):
                lines[i] = f"build_version: {new_ver}"
                updated.add("build_version")
            elif line.startswith("change_status:"):
                lines[i] = "change_status: moved"
                updated.add("change_status")
            elif line.startswith("source_hash:"):
                lines[i] = f"source_hash: {new_hash}"
                updated.add("source_hash")
            elif line.startswith("moved_from:"):
                lines[i] = f"moved_from: {old_path}"
                updated.add("moved_from")
            elif line.startswith("moved_in:"):
                lines[i] = f"moved_in: {new_ver}"
                updated.add("moved_in")

    if fm_end > 0:
        missing = []
        if "moved_from" not in updated:
            missing.append(f"moved_from: {old_path}")
        if "moved_in" not in updated:
            missing.append(f"moved_in: {new_ver}")
        for field in reversed(missing):
            lines.insert(fm_end, field)
            fm_end += 1

        for i, line in enumerate(lines[fm_end:]):
            idx = fm_end + i
            if line.startswith("# "):
                notice = (
                    f"\n> [!NOTE]\n> **Moved in build {new_ver}** — "
                    f"Source file relocated from `{old_path}` → `{new_path}`. No logic changes.\n"
                )
                lines.insert(idx + 1, notice)
                break

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _is_data_only(lua_code: str) -> bool:
    """
    True nếu file Lua là data-dominated — không nên re-render bằng chunked pipeline.

    Bao gồm:
      - Pure-data: strings.lua, map data, config tables (0 functions)
      - Autogenerated registries: skinprefabs.lua — hàng nghìn CreatePrefabSkin()
        với vài helper functions nhỏ rải rác (function density rất thấp)

    Threshold: < 0.1 named functions per 1000 tokens.
    Ví dụ: skinprefabs.lua có 2 functions / 196K tokens = 0.01/kloc → data-only.
    File code thực sự: 50 functions / 5K tokens = 10/kloc → không phải data-only.
    """
    import re
    token_count = count_tokens(lua_code)
    if token_count < DATA_ONLY_TOKEN_THRESHOLD:
        return False

    matches = re.findall(r'^\s*(local\s+)?function\s+\w', lua_code, re.MULTILINE)
    func_count = len(matches)

    # Density: số function / 1000 tokens
    func_density = func_count / (token_count / 1000)
    return func_density < 0.1


def _patch_frontmatter_only(
    md_path: str,
    new_hash: str,
    new_ver: str,
    diff_summary: str,
) -> bool:
    """
    Cập nhật source_hash, last_updated, build_version, change_status trong frontmatter.
    Không re-render nội dung doc. Dùng cho data-only files.
    Returns True nếu thành công.
    """
    if not os.path.exists(md_path):
        print(f"  - Bỏ qua patch frontmatter: doc chưa tồn tại ({md_path})")
        return False

    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    in_fm = False
    fm_end = -1
    updated = set()

    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
            else:
                fm_end = i
                break
        if in_fm and line.strip() != "---":
            if line.startswith("source_hash:"):
                lines[i] = f"source_hash: {new_hash}"
                updated.add("source_hash")
            elif line.startswith("last_updated:"):
                lines[i] = f"last_updated: {today}"
                updated.add("last_updated")
            elif line.startswith("build_version:"):
                lines[i] = f"build_version: {new_ver}"
                updated.add("build_version")
            elif line.startswith("change_status:"):
                lines[i] = "change_status: data_patched"
                updated.add("change_status")

    if fm_end < 0:
        print(f"  - Cảnh báo: Không tìm thấy frontmatter trong {md_path}")
        return False

    # Inject change_status nếu chưa có
    if "change_status" not in updated:
        lines.insert(fm_end, "change_status: data_patched")
        fm_end += 1

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  - Patched frontmatter (data-only, no re-render): {diff_summary}")
    return True


def _read_frontmatter_hash(md_path: str) -> str | None:
    """Đọc source_hash từ YAML frontmatter của doc file."""
    if not os.path.exists(md_path):
        return None
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        in_fm = False
        for line in content.splitlines():
            if line.strip() == "---":
                if not in_fm:
                    in_fm = True
                    continue
                else:
                    break
            if in_fm and line.startswith("source_hash:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def _already_processed(path: str, md_filepath: str, action: str, old_path: str = "", content_changed: bool = True) -> bool:
    """
    Kiểm tra xem file này đã được xử lý thành công trong lần chạy trước chưa.
    - added/modified/moved(content_changed): so sánh source_hash trong frontmatter với hash của Lua source hiện tại.
    - moved(no content change): kiểm tra doc mới tồn tại và có moved_from field.
    """
    if action == "moved" and not content_changed:
        if not os.path.exists(md_filepath):
            return False
        try:
            with open(md_filepath, "r", encoding="utf-8") as f:
                return f"moved_from: {old_path}" in f.read()
        except Exception:
            return False

    existing_hash = _read_frontmatter_hash(md_filepath)
    if not existing_hash:
        return False

    lua_abs_path = os.path.join(SCRIPTS_DIR, path)
    lua_code = safe_read_lua(lua_abs_path)
    if not lua_code:
        return False

    return existing_hash == compute_source_hash(lua_code)


def _render_file(
    path: str,
    md_filepath: str,
    args,
    file_tree: str,
) -> bool:
    """
    Chạy full render pipeline cho một file Lua: build_prompt → generate_doc/chunked → validate.
    Trả về True nếu thành công.
    """
    rel_no_ext = path.replace(".lua", "")
    comp_name = os.path.basename(rel_no_ext)
    comp_title = comp_name.replace("_", " ").title()
    display_filepath = f"./{path}"
    category_type = get_category_type(path)
    lua_abs_path = os.path.join(SCRIPTS_DIR, path)

    lua_code = safe_read_lua(lua_abs_path)
    if lua_code is None:
        print(f"  - Lỗi: Không thể đọc source {lua_abs_path}")
        return False

    # Data-only files (strings.lua, map tables...): không có function, quá lớn để re-render.
    # Chunked pipeline sẽ tạo 60+ LLM calls mà output không có giá trị API.
    # Chỉ patch frontmatter để tracking build version.
    if _is_data_only(lua_code):
        token_count = count_tokens(lua_code)
        import re as _re
        func_count = len(_re.findall(r'^\s*(local\s+)?function\s+\w', lua_code, _re.MULTILINE))
        density = func_count / (token_count / 1000)
        print(f"  [DATA-ONLY] {token_count} tokens, {func_count} functions (density={density:.3f}/kloc) — skip re-render, patch frontmatter only")
        if args.dry_run:
            print(f"  - (Dry-run) Sẽ patch frontmatter: {md_filepath}")
            return True
        return _patch_frontmatter_only(
            md_path=md_filepath,
            new_hash=compute_source_hash(lua_code),
            new_ver=config.VERSION,
            diff_summary=f"{token_count} tokens, data-only file",
        )

    source_hash = compute_source_hash(lua_code)
    lua_refs = extract_lua_references(lua_code, path)
    connected_section = format_connected_section(lua_refs)
    connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)

    if lua_refs:
        print(f"  [REF] {len(lua_refs)} file liên quan")

    prompt_text = build_prompt(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        lua_code=lua_code,
        connected_section=connected_section,
        connected_content=connected_content,
        source_hash=source_hash,
        file_tree=file_tree,
        today_date=config.TODAY_DATE,
        version=config.VERSION,
        category_type=category_type,
    )

    token_count = count_tokens(prompt_text)
    if token_count >= 0:
        print(f"  [PROMPT] {token_count} tokens")

    if DEBUG_PROMPTS:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        debug_path = _DEBUG_DIR / f"update_{comp_name}_{ts}.txt"
        debug_path.write_text(prompt_text, encoding="utf-8")
        print(f"  [debug] Prompt dumped → {debug_path}")

    if args.dry_run:
        print("  --- PROMPT PREVIEW ---")
        print(prompt_text[:1000] + "\n...[TRUNCATED]")
        return True

    # Tạo thư mục nếu chưa có
    dirname = os.path.dirname(md_filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

    try:
        if needs_chunking(prompt_text):
            print(f"  [CHUNKED] Prompt quá dài ({token_count} tokens), dùng chunked pipeline")
            result = process_chunked_file(
                comp_name=comp_name,
                comp_title=comp_title,
                display_filepath=display_filepath,
                lua_code=lua_code,
                connected_section=connected_section,
                connected_content=connected_content,
                source_hash=source_hash,
                md_filepath=md_filepath,
                full_refs=lua_refs,
                file_tree=file_tree,
                today_date=config.TODAY_DATE,
                version=config.VERSION,
                category_type=category_type,
                model_name=MODEL_NAME,
                chunk_sleep=10,
                merge_sleep=20,
                fresh_start=True,
            )
        else:
            result = generate_doc(
                prompt=prompt_text,
                md_filepath=md_filepath,
                source_hash=source_hash,
                lua_filepath=lua_abs_path,
                model_name=MODEL_NAME,
                sleep_time=20,
            )
    except KeyboardInterrupt:
        result = os.path.basename(md_filepath) if os.path.exists(md_filepath) else None

    if not result:
        return False

    if args.no_validate or shutdown.stop_requested:
        print(f"  - Thành công (no-validate): {md_filepath}")
        return True

    generated_path = os.path.join(os.path.dirname(md_filepath), result)

    try:
        file_result = process_file(generated_path, PipelineConfig(
            writer_model=MODEL_NAME,
            reviewer_model=MODEL_NAME,
            stop_check=lambda: shutdown.stop_requested,
        ))
    except KeyboardInterrupt:
        shutdown.request_stop()
        return False
    except Exception as e:
        print(f"  [Lỗi validate] {e}")
        return False

    if file_result.final_status in ("ok", "skipped_chunked"):
        print(f"  - Thành công: {md_filepath}")
        return True

    if file_result.final_status == "content_failed":
        try:
            p = Path(generated_path)
            p.rename(p.with_name(p.stem + "-false" + p.suffix))
        except OSError as e:
            print(f"  [Cảnh báo] Không thể đổi tên: {e}")

    return False


class _TeeWriter:
    """Mirrors writes to both the original stdout and a log file."""

    def __init__(self, log_path: str):
        self._stdout = sys.stdout
        self._log = open(log_path, "w", encoding="utf-8", buffering=1)

    def write(self, data: str) -> int:
        self._stdout.write(data)
        self._log.write(data)
        self._log.flush()
        return len(data)

    def flush(self):
        self._stdout.flush()
        self._log.flush()

    def close(self):
        sys.stdout = self._stdout
        self._log.close()

    def __getattr__(self, name):
        return getattr(self._stdout, name)


def main():
    logs_dir = PROJECT_ROOT / ".cache" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_filename = datetime.now().strftime("update_%Y-%m-%d_%H-%M-%S.log")
    log_path = str(logs_dir / log_filename)
    tee = _TeeWriter(log_path)
    sys.stdout = tee
    print(f"[Log] Session log: {log_path}")

    try:
        _main_impl()
    finally:
        tee.close()


def _main_impl():
    args = parse_args()

    def handle_sigint(signum, frame):
        if not shutdown.stop_requested:
            print("\n\n[Hệ thống] Đã nhận Ctrl+C! Đang dừng an toàn...")
            shutdown.request_stop()
            raise KeyboardInterrupt
        else:
            print("\n\n[Hệ thống] Ép buộc dừng ngay!")
            sys.exit(1)

    signal.signal(signal.SIGINT, handle_sigint)

    report = load_diff_report()
    if not report:
        return

    old_ver = report["version"]["old"]
    new_ver = report["version"]["new"]
    changes = report["changes"]

    # Lọc chỉ file .lua
    def _is_lua(c):
        p = c.get("path") or c.get("new_path") or c.get("old_path") or ""
        return p.endswith(".lua")

    non_lua = [c for c in changes if not _is_lua(c)]
    if non_lua:
        print(f"[update] Bỏ qua {len(non_lua)} file không phải .lua")
    changes = [c for c in changes if _is_lua(c)]

    if args.filter:
        changes = [c for c in changes if c["action"] == args.filter]

    if args.limit > 0:
        changes = changes[:args.limit]

    print("=" * 60)
    print(f"[update] Re-render pipeline: build {old_ver} → {new_ver}")
    print(f"  Chế độ      : {'Dry-run' if args.dry_run else 'Thực thi'}")
    print(f"  File xử lý  : {len(changes)}")
    print(f"  Validation  : {'Tắt' if args.no_validate else 'Bật'}")
    print(f"  Force rerun : {'Bật' if args.force else 'Tắt (skip file đã xử lý)'}")
    print("=" * 60)

    file_tree = config.get_shared_file_tree()
    stats = {"processed": 0, "skipped": 0, "failed": 0, "failed_list": []}

    for idx, c in enumerate(changes):
        if shutdown.stop_requested:
            break

        action = c["action"]
        path = c.get("path") or c.get("new_path") or c.get("old_path")
        old_path = c.get("old_path", "")
        content_changed = c.get("content_changed", True)

        print(f"\n[{idx+1}/{len(changes)}] {action.upper()}: {path}")

        if not path:
            print("  - Lỗi: Không xác định được đường dẫn")
            stats["failed"] += 1
            continue

        md_filepath = get_md_path(path)

        if not args.dry_run and not args.force and action != "deleted":
            if _already_processed(path, md_filepath, action, old_path, content_changed):
                print(f"  - Skip: Đã xử lý thành công (source_hash match). Dùng --force để xử lý lại.")
                stats["skipped"] += 1
                continue

        # MOVED — không thay đổi nội dung: chỉ rename + cập nhật frontmatter
        if action == "moved" and not content_changed:
            old_md = get_md_path(old_path)
            if not os.path.exists(old_md):
                print(f"  - Bỏ qua: Không tìm thấy doc cũ {old_md}")
                stats["failed"] += 1
                stats["failed_list"].append(path)
                continue

            if not args.dry_run:
                dirname = os.path.dirname(md_filepath)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                if old_md != md_filepath:
                    os.rename(old_md, md_filepath)

                lua_abs = os.path.join(SCRIPTS_DIR, path)
                lua_code = safe_read_lua(lua_abs)
                new_hash = compute_source_hash(lua_code) if lua_code else c.get("new_hash", "")
                _update_moved_frontmatter(md_filepath, old_path, path, new_hash, new_ver)
                print(f"  - Renamed và cập nhật frontmatter: {old_md} → {md_filepath}")
            else:
                print(f"  - (Dry-run) Rename {old_md} → {md_filepath} + Update frontmatter")

            stats["processed"] += 1
            continue

        # DELETED — chỉ ghi chú (không có Lua source để render)
        if action == "deleted":
            print(f"  - Bỏ qua (deleted): doc tại {md_filepath}")
            stats["skipped"] += 1
            continue

        # ADDED / MODIFIED / MOVED(content_changed) — full re-render pipeline
        if action == "moved" and content_changed:
            old_md = get_md_path(old_path)
            dirname = os.path.dirname(md_filepath)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            if old_md != md_filepath and os.path.exists(old_md):
                os.rename(old_md, md_filepath)
                print(f"  [MOVED] Renamed {old_md} → {md_filepath}")

        ok = _render_file(path, md_filepath, args, file_tree)
        if ok:
            stats["processed"] += 1
        else:
            stats["failed"] += 1
            stats["failed_list"].append(path)

    print("\n" + "=" * 60)
    print(f"[Thống kê] Hoàn tất!")
    print(f"  Đã xử lý : {stats['processed']} file")
    print(f"  Đã bỏ qua: {stats['skipped']} file")
    print(f"  Thất bại  : {stats['failed']} file")
    if stats["failed_list"]:
        print(f"  Danh sách lỗi: {', '.join(stats['failed_list'])}")
    print("=" * 60)


if __name__ == "__main__":
    main()
