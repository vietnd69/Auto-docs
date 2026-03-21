import sys
import os
import re
from pathlib import Path
from datetime import datetime

# Thêm path để import các file ở root và validator đúng
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

from get_tree import generate_slim_tree
from rag_get_fnc_content import extract_connected_content
from get_docs import (
    extract_lua_references,
    safe_read_lua,
    compute_source_hash,
    format_connected_section
)
from prompt import build_prompt
from chunked import needs_chunking
from chunked_olm import process_chunked_file
from olm import generate_doc
from validator.validator import validate_full
from validator.autofix_mdx import autofix_file

import time

# Lấy lại các hằng số từ config.py
LUA_DIR = config.BASE_LUA_DIR
VERSION = config.VERSION
CATEGORY_TYPE = "map" # Mặc định cho fix_format
TODAY_DATE = config.TODAY_DATE
MODEL_NAME = config.MODEL_NAME
FILE_TREE = config.get_shared_file_tree()

def fix_markdown_with_llm(filepath: str, max_retries: int = 3):
    """
    Sửa file markdown bị lỗi format bằng cách chạy lại pipeline tạo prompt chuẩn,
    nhưng giữ lại YAML frontmatter cũ.
    """
    path = Path(filepath)
    if not path.exists():
        print(f"[fix_format] File không tồn tại: {filepath}")
        return False

    # Chạy pre-validation kiểm tra định dạng
    print(f"Kiểm tra lại content file: {path.name} ... ", end="")
    results = validate_full(str(path))
    
    if results == ["OK"]:
        print("ĐÃ HỢP LỆ, bỏ qua.")
        return True

    # Phân loại lỗi
    format_errors = [e for e in results if "[format]" in e or "[yaml]" in e or "[frontmatter]" in e]
    mdx_errors = [e for e in results if any(tag in e for tag in ["[mdx]", "ReferenceError", "acorn"])]
    
    # 1. Nếu CHỈ có lỗi MDX -> thử dùng autofix_file (vì autofix_mdx xử lý mdx_errors)
    if not format_errors and mdx_errors:
        print("CÓ LỖI MDX, ĐANG THỬ AUTO-FIX...")
        changes = autofix_file(str(path))
        if changes:
            print(f"  -> Đã auto-fix thành công ({len(changes)} thay đổi).")
            # Kiểm tra lại xem còn lỗi không
            if validate_full(str(path)) == ["OK"]:
                print("  -> Đã sạch lỗi. Bỏ qua LLM.")
                return True
        print("  -> Auto-fix không hết lỗi MDX, cần LLM.")

    # 2. Nếu có lỗi format/yaml -> kiểm tra xem có autofix được không
    needs_llm = False
    if format_errors:
        autofixable_only = True
        for err in format_errors:
            # Các lỗi format/yaml mà autofix_file xử lý được
            is_autofixable = any(msg in err for msg in [
                "Chứa text rác", 
                "Extra '---' divider", 
                "Missing or malformed frontmatter delimiters",
                "YAML keys outside frontmatter",
                "description chứa dấu hai chấm",
                "tags is empty",
                "placeholder"
            ])
            if not is_autofixable:
                autofixable_only = False
                break
        
        if autofixable_only:
            print("CÓ LỖI FORMAT CÓ THỂ AUTO-FIX, ĐANG THỬ...")
            autofix_file(str(path))
            if validate_full(str(path)) == ["OK"]:
                print("  -> Đã auto-fix thành công. Bỏ qua LLM.")
                return True
            print("  -> Auto-fix không hết lỗi format, cần LLM.")
            needs_llm = True
        else:
            print("CÓ LỖI FORMAT NẶNG (THIẾU HEADING...), CẦN LLM.")
            needs_llm = True
    else:
        # Nếu đã đến đây tức là không có format_errors nhưng mdx_errors vẫn còn
        needs_llm = True

    if not needs_llm:
        # Dự phòng
        return True

    raw_text = path.read_text(encoding="utf-8")

    # Lấy frontmatter để parse category_type (không cần throw error nếu không có)
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n', raw_text)
    frontmatter_block = fm_match.group(0) if fm_match else ""
    
    # Tìm lại file Lua gốc dựa trên đường dẫn docs
    # VD: d:\code\mod-document\dst-api-webdocs\docs\map\static_layouts\rooms\hallway_residential_two\four.md
    # -> ./dst-scripts/map/static_layouts/rooms/hallway_residential_two\four.lua
    try:
        # Lấy phần path sau 'docs/'
        docs_parts = path.parts
        docs_idx = docs_parts.index("docs")
        rel_parts = docs_parts[docs_idx + 1:]
        
        lua_rel_path = "/".join(rel_parts).replace(".md", ".lua")
        lua_filepath = os.path.join(LUA_DIR, lua_rel_path)
    except ValueError:
        print(f"[fix_format] Không thể suy ra đường dẫn Lua từ {path}")
        return False

    if not os.path.exists(lua_filepath):
        print(f"[fix_format] Không tìm thấy file Lua gốc: {lua_filepath}")
        return False

    # Đọc thông tin y hệt main.py
    comp_name = path.stem
    comp_title = comp_name.replace("_", " ").title()
    display_filepath = lua_filepath.replace("./dst-scripts", ".").replace("\\", "/")
    
    lua_code = safe_read_lua(lua_filepath)
    if lua_code is None:
        print(f"[fix_format] Không thể đọc file Lua: {lua_filepath}")
        return False

    source_hash = compute_source_hash(lua_code)
    lua_refs = extract_lua_references(lua_code, comp_name + ".lua")
    connected_section = format_connected_section(lua_refs)
    connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
    
    # Lấy category_type từ frontmatter nếu có
    cat_match = re.search(r'^category_type:\s*(\w+)', frontmatter_block, re.MULTILINE)
    category = cat_match.group(1) if cat_match else CATEGORY_TYPE

    # Save to temporary file to avoid altering original if it fails
    tmp_filepath = path.with_name(path.name + ".tmp")
    
    try:
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
            category_type=category,
        )

        # Đếm token toàn bộ prompt
        from chunked import count_tokens
        token_count = count_tokens(prompt_text)
        if token_count >= 0:
            print(f"  [PROMPT] Độ dài: {token_count} tokens")

        print(f"[fix_format] Đang chạy lại prompt cho {path.name}...")

        # Chạy pipeline sinh docs
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
                md_filepath=str(tmp_filepath),
                file_tree=FILE_TREE,
                today_date=TODAY_DATE,
                version=VERSION,
                category_type=category,
                model_name=MODEL_NAME,
                chunk_sleep=10,
                merge_sleep=0,  # Sleep = 0 để sửa file ngay lập tức
            )
        else:
            # === PIPELINE BÌNH THƯỜNG — prompt vừa vặn ===
            result = generate_doc(
                prompt=prompt_text,
                md_filepath=str(tmp_filepath),
                model_name=MODEL_NAME,
                sleep_time=0,  # Sleep = 0 để sửa file ngay lập tức
            )
        
        if result and tmp_filepath.exists():
            # Lấy nội dung LLM sinh ra
            new_content = tmp_filepath.read_text(encoding="utf-8")
            
            # Ghi đè file gốc bằng toàn bộ nội dung mới từ LLM (bao gồm cả yaml frontmatter mới)
            path.write_text(new_content.strip() + "\n", encoding="utf-8")
            
            print(f"[fix_format] Sửa file {path.name} THÀNH CÔNG")
            print(f"  Đã áp dụng và dọn dẹp file tmp. Đang nghỉ 20s chờ LLM...")
            time.sleep(20)
            
            return True
        else:
            print(f"[fix_format] Sửa file {path.name} THẤT BẠI: LLM không trả về kết quả hợp lệ.")
            return False
            
    finally:
        if tmp_filepath.exists():
            tmp_filepath.unlink()

def main():
    log_file = Path("validator/format_errors.txt")
    if not log_file.exists():
        print("Không tìm thấy file format_errors.txt. Hãy chạy `py validator` trước.")
        return
        
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    filepaths = [line.strip() for line in lines if line.strip()]
    if not filepaths:
        print("Không có file lỗi định dạng nào cần sửa.")
        return
        
    print(f"Bắt đầu sửa {len(filepaths)} file bị lỗi định dạng bằng LLM...")
    success_count = 0
    failed_filepaths = []
    pending_filepaths = filepaths.copy()
    
    current_processing = None
    try:
        for filepath in filepaths:
            # Lưu vết file đang xử lý để nếu Ctrl+C thì nó vẫn nằm trong pending
            current_processing = filepath
            
            if fix_markdown_with_llm(filepath):
                success_count += 1
                pending_filepaths.remove(filepath)
            else:
                failed_filepaths.append(filepath)
                pending_filepaths.remove(filepath)
            
            current_processing = None
            
    except KeyboardInterrupt:
        print("\n\n[Hệ thống] Đã nhận lệnh dừng (Ctrl+C).")
        if current_processing:
            print(f"  Đang dừng khi xử lý: {current_processing}")
        print("  Đang lưu lại tiến trình...")
    finally:
        # Cập nhật lại log file: lưu những file lỗi chưa sửa được + những file chưa kịp chạy
        remaining_files = failed_filepaths + pending_filepaths
        
        with open(log_file, "w", encoding="utf-8") as f:
            for remaining_path in remaining_files:
                f.write(remaining_path + "\n")
                
        print(f"\nĐã thao tác xong hoặc bị dừng.")
        print(f"  Thành công: {success_count} file.")
        
        if remaining_files:
            print(f"  Còn {len(remaining_files)} file cần xử lý sau. Danh sách đã được bảo toàn trong format_errors.txt.")
        else:
            print("  Hoàn tất 100%! format_errors.txt đã được dọn sạch.")
            
        print("Vui lòng chạy lại `py validator` để kiểm tra kết quả.")

if __name__ == "__main__":
    main()
