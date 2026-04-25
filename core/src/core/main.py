import argparse
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
import core.config as config
from core.utils import shutdown
from llm.settings import MODEL_MAIN as MODEL_NAME
from llm.paths import BASE_LUA_DIR, BASE_DOCS_DIR, PROJECT_ROOT
from rag.content import extract_connected_content
from rag.docs import (
    extract_lua_references,
    safe_read_lua,
    compute_source_hash,
    format_connected_section,
    get_lua_files,
)
from prompts.standard import build_prompt
from prompts.type_detect import detect_lua_type
from core.pipeline.standard import generate_doc
from core.pipeline.chunking import needs_chunking
from core.pipeline.chunked import process_chunked_file
from llm.tokens import count_tokens
from validator.pipeline import process_file, PipelineConfig


class _TeeWriter:
    """Mirrors writes to both the original stdout and a log file."""

    def __init__(self, log_path: str):
        self._stdout = sys.stdout
        self._log = open(log_path, "w", encoding="utf-8", buffering=1)

    def write(self, data: str) -> int:
        self._stdout.write(data)
        self._log.write(data)
        self._log.flush()  # real-time: flush after every write
        return len(data)

    def flush(self):
        self._stdout.flush()
        self._log.flush()

    def close(self):
        sys.stdout = self._stdout
        self._log.close()

    # Delegate attribute access so code that checks sys.stdout.fileno() etc. still works
    def __getattr__(self, name):
        return getattr(self._stdout, name)


def main():
    # === SESSION LOG — mirror all stdout to .cache/logs/run_<timestamp>.log ===
    logs_dir = PROJECT_ROOT / ".cache" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_filename = datetime.now().strftime("run_%Y-%m-%d_%H-%M-%S.log")
    log_path = str(logs_dir / log_filename)
    tee = _TeeWriter(log_path)
    sys.stdout = tee
    print(f"[Log] Session log: {log_path}")

    try:
        _main_impl()
    finally:
        tee.close()


def _main_impl():
    # === CLI ARGUMENTS ===
    parser = argparse.ArgumentParser(description="Generate API docs for DST Lua mods")
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to a single .lua file to generate docs for (skip full scan)",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force regenerate even if docs already exist",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip validation (generate only, no content loop or format fix)",
    )
    parser.add_argument(
        "--resume-validate",
        action="store_true",
        help="Skip generation, resume validation from last section checkpoint (single-file mode)",
    )
    args = parser.parse_args()

    # === CONFIGURATION — Lấy từ config.py và tuỳ chỉnh ===
    ENTER_DEEP_DIR = True
    LUA_DIR = os.path.join(BASE_LUA_DIR, "")
    DOCS_DIR = os.path.join(BASE_DOCS_DIR, "")
    VERSION = config.VERSION
    TODAY_DATE = config.TODAY_DATE
    FILE_TREE = config.get_shared_file_tree()

    os.makedirs(DOCS_DIR, exist_ok=True)

    # === Ctrl+C handler ===
    def handle_sigint(signum, frame):
        if not shutdown.stop_requested:
            print("\n\n[Hệ thống] Đã nhận Ctrl+C! Checkpoint đã lưu, đang dừng...")
            shutdown.request_stop()
            raise KeyboardInterrupt  # Ngắt blocking HTTP call ngay lập tức
        else:
            print("\n\n[Hệ thống] Ép buộc dừng ngay!")
            sys.exit(1)

    signal.signal(signal.SIGINT, handle_sigint)

    # === Build file list ===
    if args.file:
        # Single file mode: resolve path relative to LUA_DIR
        lua_path = os.path.abspath(args.file)
        if not lua_path.endswith(".lua"):
            print(f"[Lỗi] File phải có đuôi .lua: {lua_path}")
            sys.exit(1)
        if not os.path.isfile(lua_path):
            print(f"[Lỗi] File không tồn tại: {lua_path}")
            sys.exit(1)
        lua_dir_abs = os.path.abspath(LUA_DIR)
        if not lua_path.startswith(lua_dir_abs):
            print(f"[Lỗi] File phải nằm trong thư mục: {lua_dir_abs}")
            sys.exit(1)
        file_list = [os.path.relpath(lua_path, lua_dir_abs).replace("\\", "/")]
        force_regen = True  # Single file mode → always regenerate
    else:
        file_list = get_lua_files(LUA_DIR, deep=ENTER_DEEP_DIR)
        force_regen = args.force

    # === MAIN LOOP ===
    stats = {"processed": 0, "skipped": 0, "failed": 0, "failed_list": [], "validate_failed": 0}

    if args.file:
        print(f"Xử lý file đơn: {file_list[0]}")
    else:
        print(f"Bắt đầu xử lý thư mục: {LUA_DIR}")
    print(f"Output: {DOCS_DIR}")
    print(f"Model: {MODEL_NAME}")
    print("-" * 60)

    for filename in file_list:
        if shutdown.stop_requested:
            print("[Hệ thống] Đã dừng vòng lặp an toàn.")
            break

        rel_no_ext = filename.replace(".lua", "")
        comp_name = os.path.basename(rel_no_ext)
        comp_title = comp_name.replace("_", " ").title()

        md_filename = f"{rel_no_ext}.md"
        md_filepath = os.path.join(DOCS_DIR, md_filename)

        # Đảm bảo thư mục con tồn tại
        os.makedirs(os.path.dirname(md_filepath), exist_ok=True)

        # --resume-validate: bỏ qua generation, chỉ chạy lại validator từ checkpoint
        if args.resume_validate and os.path.exists(md_filepath):
            print(f"  [resume-validate] Bỏ qua generation, validate lại {md_filename}...")
            generated_path = md_filepath
            try:
                file_result = process_file(generated_path, PipelineConfig(
                    writer_model=MODEL_NAME,
                    reviewer_model=MODEL_NAME,
                    stop_check=lambda: shutdown.stop_requested,
                    resume=True,
                ))
            except KeyboardInterrupt:
                stats["failed"] += 1
                stats["validate_failed"] += 1
                stats["failed_list"].append(filename)
                shutdown.request_stop()
                continue
            except Exception as e:
                print(f"  [Lỗi validate] {filename}: {e}")
                stats["failed"] += 1
                stats["validate_failed"] += 1
                stats["failed_list"].append(filename)
                continue
            if file_result.final_status == "ok":
                stats["processed"] += 1
            else:
                stats["failed"] += 1
                stats["validate_failed"] += 1
                stats["failed_list"].append(filename)
            continue

        # Bỏ qua file đã có docs (trừ khi force hoặc single file mode)
        if not force_regen and os.path.exists(md_filepath):
            print(f"  Bỏ qua {md_filename} (đã tồn tại)")
            stats["skipped"] += 1
            continue

        filepath = os.path.join(LUA_DIR, filename)
        display_filepath = filepath.replace("./dst-scripts", ".").replace("\\", "/")
        category_type = detect_lua_type(display_filepath)

        lua_code = safe_read_lua(filepath)
        if lua_code is None:
            stats["failed"] += 1
            stats["failed_list"].append(filename)
            continue

        source_hash = compute_source_hash(lua_code)

        # Trích xuất tham chiếu
        lua_refs = extract_lua_references(lua_code, filename)
        connected_section = format_connected_section(lua_refs)

        print(f"------------------")
        if lua_refs:
            print(f"  [REF] {len(lua_refs)} file liên quan")
        else:
            print(f"  [REF] Không có tham chiếu")

        # Trích xuất nội dung function từ file liên quan
        connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
        if connected_content:
            print(f"  [FNC] {connected_content.count(chr(10)) + 1} dòng source code")

        total_lines = lua_code.count("\n") + 1
        print(f"\n  Đang xử lý {filename} ({total_lines} dòng)...")

        # Build full prompt TRƯỚC để đếm token chính xác
        prompt_text = build_prompt(
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
            category_type=category_type,
        )

        # Đếm token toàn bộ prompt
        token_count = count_tokens(prompt_text)
        if token_count >= 0:
            print(f"  [PROMPT] Độ dài: {token_count} tokens")

        try:
            if needs_chunking(prompt_text):
                # === CHUNKED PIPELINE — full prompt > 32K token ===
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
                    file_tree=FILE_TREE,
                    today_date=TODAY_DATE,
                    version=VERSION,
                    category_type=category_type,
                    lua_type=category_type,
                    model_name=MODEL_NAME,
                    chunk_sleep=10,
                    merge_sleep=20,
                )
            else:
                # === PIPELINE BÌNH THƯỜNG — prompt vừa vặn ===
                result = generate_doc(
                    prompt=prompt_text,
                    md_filepath=md_filepath,
                    source_hash=source_hash,
                    lua_filepath=filepath,
                    model_name=MODEL_NAME,
                    sleep_time=20,
                )
        except KeyboardInterrupt:
            # File có thể đã được ghi thành công trước khi bị ngắt (ví dụ: ngắt trong lúc sleep)
            result = os.path.basename(md_filepath) if os.path.exists(md_filepath) else None

        if not result:
            stats["failed"] += 1
            stats["failed_list"].append(filename)
            continue

        # Resolve actual generated file path from result (basename) + md_filepath's directory.
        generated_path = os.path.join(os.path.dirname(md_filepath), result)

        if args.no_validate or shutdown.stop_requested:
            stats["processed"] += 1
            continue

        # --- Validation ---
        try:
            file_result = process_file(generated_path, PipelineConfig(
                writer_model=MODEL_NAME,
                reviewer_model=MODEL_NAME,
                stop_check=lambda: shutdown.stop_requested,
            ))
        except KeyboardInterrupt:
            # Do NOT re-raise — outer loop exits via shutdown.stop_requested.
            stats["failed"] += 1
            stats["validate_failed"] += 1
            stats["failed_list"].append(filename)
            shutdown.request_stop()
            continue
        except Exception as e:
            # Unexpected validator error (e.g. disk issue) — counts as validate_failed.
            print(f"  [Lỗi validate] {filename}: {e}")
            stats["failed"] += 1
            stats["validate_failed"] += 1
            stats["failed_list"].append(filename)
            continue

        if file_result.final_status in ("ok", "skipped_chunked"):
            stats["processed"] += 1
        elif file_result.final_status == "content_failed":
            try:
                p = Path(generated_path)
                false_path = p.with_name(p.stem + "-false" + p.suffix)
                p.rename(false_path)
            except OSError as e:
                print(f"  [Cảnh báo] Không thể đổi tên {generated_path}: {e}")
            stats["failed"] += 1
            stats["validate_failed"] += 1
            stats["failed_list"].append(filename)
        elif file_result.final_status == "format_failed":
            stats["failed"] += 1
            stats["validate_failed"] += 1
            stats["failed_list"].append(filename)

    # === Thống kê ===
    print("\n" + "=" * 60)
    print(f"[Thống kê] Hoàn tất!")
    print(f"  Đã xử lý : {stats['processed']} file")
    print(f"  Đã bỏ qua: {stats['skipped']} file")
    if stats["failed"] > 0:
        print(f"  Thất bại  : {stats['failed']} file")
        generate_fail = stats["failed"] - stats["validate_failed"]
        if not args.no_validate and stats["validate_failed"] > 0:
            print(f"    → Validation fail: {stats['validate_failed']}")
        if generate_fail > 0:
            print(f"    → Generate fail  : {generate_fail}")
    else:
        print(f"  Thất bại  : 0 file")
    if stats["failed_list"]:
        print(f"  Danh sách file lỗi: {', '.join(stats['failed_list'])}")
    print("=" * 60)


if __name__ == "__main__":
    main()
