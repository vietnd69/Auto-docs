import sys
from pathlib import Path

from validator.validator import validate_full
from validator.autofix_mdx import autofix_file

# Đường dẫn tuyệt đối từ script (__main__.py nằm trong validator/)
# Nơi chứa docs: d:\code\mod-document\dst-api-webdocs\docs
DOCS_DIR = Path(__file__).parent.parent / "dst-api-webdocs" / "docs" 
def main():
    try:
        target = sys.argv[1] if len(sys.argv) > 1 else DOCS_DIR
        target_path = Path(target)
        
        if target_path.is_file():
            files_to_check = [target_path]
        else:
            # Lấy tất cả các file .md và .mdx trong thư mục target
            files_to_check = list(target_path.rglob("*.md")) + list(target_path.rglob("*.mdx"))
        
        print(f"Bắt đầu kiểm tra {len(files_to_check)} file(s)...")
        
        files_with_errors = []
        files_with_warnings = []
        format_errors_log = Path(__file__).parent / "format_errors.txt"
        
        # Reset log file
        format_errors_log.write_text("", encoding="utf-8")
        
        # 1. Chạy validator để lấy danh sách file lỗi
        for filepath in files_to_check:
            print(f"Đang kiểm tra: {filepath.name} ... ", end="")
            results = validate_full(str(filepath))
            # Nếu có lỗi thì đưa vào danh sách
            if results != ["OK"]:
                # Tách warnings ra khỏi errors
                warnings = [r for r in results if "[warning" in r]
                errors = [r for r in results if "[warning" not in r]
                
                if errors:
                    print("LỖI:")
                    has_format_error = False
                    for r in errors:
                        print(f"    - {r}")
                        if "[format]" in r or "[yaml]" in r or "[frontmatter]" in r:
                            has_format_error = True
                    for r in warnings:
                        print(f"    ⚠ {r}")
                    files_with_errors.append(filepath)
                    
                    # Lưu đường dẫn các file bị lỗi format
                    if has_format_error:
                        with open(format_errors_log, "a", encoding="utf-8") as f:
                            f.write(str(filepath) + "\n")
                elif warnings:
                    print("CẢNH BÁO:")
                    for r in warnings:
                        print(f"    ⚠ {r}")
                    files_with_warnings.append(filepath)
            else:
                print("OK")
                
        print(f"Phát hiện {len(files_with_errors)} file có lỗi và {len(files_with_warnings)} file có cảnh báo.")
        
        # Gom lỗi và cảnh báo vào danh sách cần fix
        files_to_fix = list(set(files_with_errors + files_with_warnings))
        
        if not files_to_fix:
            print("Tất cả các file đều hợp lệ!")
            return
            
        # 2. Chạy qua 1 vòng autofix_mdx.py cho các file cần fix
        print("\n--- Đang chạy autofix cho các file lỗi/cảnh báo ---")
        files_fixed = 0
        for filepath in files_to_fix:
            print(f"Đang sửa: {filepath.name}")
            changes = autofix_file(str(filepath))
            if changes:
                files_fixed += 1
                print(f"  Đã tự động sửa {len(changes)} vị trí.")
            else:
                print("  Không có sửa đổi nào được thêm." )
                
        # 3. Chạy lại validator
        print("\n--- Kiểm tra lại sau khi fix ---")
        still_errors = 0
        resolved = 0
        still_error_files = []
        for filepath in files_to_fix:
            results = validate_full(str(filepath))
            if results == ["OK"]:
                print(f"[{filepath.name}] ĐÃ SỬA THÀNH CÔNG")
                resolved += 1
            else:
                print(f"[{filepath.name}] VẪN CÒN LỖI/CẢNH BÁO:")
                for r in results:
                    print(f"  {r}")
                still_errors += 1
                still_error_files.append(filepath)
        
        # Cập nhật format_errors.txt: chỉ giữ file vẫn còn lỗi
        with open(format_errors_log, "w", encoding="utf-8") as f:
            for fp in still_error_files:
                f.write(str(fp) + "\n")
                
        # 4. Log summary
        print("\n" + "="*40)
        print("                  TỔNG KẾT")
        print("="*40)
        print(f"Tổng số file đã kiểm tra:        {len(files_to_check)}")
        print(f"Số file bị lỗi ban đầu:          {len(files_with_errors)}")
        print(f"Số file có cảnh báo:              {len(files_with_warnings)}")
        print(f"Số file đã được sửa tự động:     {resolved}")
        print(f"Số file vẫn cần sửa thủ công:    {still_errors}")
        print("="*40)
        
    except KeyboardInterrupt:
        print("\n\n[Hệ thống] Đã dừng script (Ctrl+C). Thoát an toàn.")
        sys.exit(0)

if __name__ == "__main__":
    main()