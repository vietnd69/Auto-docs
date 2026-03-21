import argparse
import os
import signal
import sys
import core.config as config
from core.utils import shutdown

from rag.content import extract_connected_content
from rag.docs import (
    extract_lua_references,
    safe_read_lua,
    compute_source_hash,
    format_connected_section,
    get_lua_files,
)
from prompts.standard import build_prompt
from core.pipeline.standard import generate_doc
from core.pipeline.chunking import needs_chunking
from core.pipeline.chunked import process_chunked_file

from llm.paths import BASE_LUA_DIR, BASE_DOCS_DIR


def main():
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
    args = parser.parse_args()

    # === CONFIGURATION — Lấy từ config.py và tuỳ chỉnh ===
    ENTER_DEEP_DIR = True
    LUA_DIR = os.path.join(BASE_LUA_DIR, "")
    DOCS_DIR = os.path.join(BASE_DOCS_DIR, "")
    VERSION = config.VERSION
    CATEGORY_TYPE = "root"
    TODAY_DATE = config.TODAY_DATE
    MODEL_NAME = config.MODEL_NAME
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
    stats = {"processed": 0, "skipped": 0, "failed": 0, "failed_list": []}

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

        # Bỏ qua file đã có docs (trừ khi force hoặc single file mode)
        if not force_regen and os.path.exists(md_filepath):
            print(f"  Bỏ qua {md_filename} (đã tồn tại)")
            stats["skipped"] += 1
            continue

        filepath = os.path.join(LUA_DIR, filename)
        display_filepath = filepath.replace("./dst-scripts", ".").replace("\\", "/")

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
            category_type=CATEGORY_TYPE,
        )

        # Đếm token toàn bộ prompt
        from llm.tokens import count_tokens
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
                    category_type=CATEGORY_TYPE,
                    model_name=MODEL_NAME,
                    chunk_sleep=10,
                    merge_sleep=20,
                )
            else:
                # === PIPELINE BÌNH THƯỜNG — prompt vừa vặn ===
                result = generate_doc(
                    prompt=prompt_text,
                    md_filepath=md_filepath,
                    model_name=MODEL_NAME,
                    sleep_time=20,
                )
        except KeyboardInterrupt:
            # File có thể đã được ghi thành công trước khi bị ngắt (ví dụ: ngắt trong lúc sleep)
            result = os.path.basename(md_filepath) if os.path.exists(md_filepath) else None

        if result:
            stats["processed"] += 1
        else:
            stats["failed"] += 1
            stats["failed_list"].append(filename)

    # === Thống kê ===
    print("\n" + "=" * 60)
    print(f"[Thống kê] Hoàn tất!")
    print(f"  Đã xử lý : {stats['processed']} file")
    print(f"  Đã bỏ qua: {stats['skipped']} file")
    print(f"  Thất bại : {stats['failed']} file")
    if stats["failed_list"]:
        print(f"  Danh sách file lỗi: {', '.join(stats['failed_list'])}")
    print("=" * 60)


if __name__ == "__main__":
    main()
