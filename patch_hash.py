"""
Script patch: Thêm source_hash vào YAML frontmatter của các file .md đã tồn tại.
Chạy 1 lần duy nhất để migrate docs cũ.

Cách dùng: py patch_hash.py
"""

import os
import re
import hashlib

# Cấu hình các cặp thư mục (docs_dir, lua_dir)
PATCH_CONFIGS = [
    ("./dst-api-webdocs/docs/components", "./dst-scripts/components"),
    ("./dst-api-webdocs/docs/behaviours", "./dst-scripts/behaviours"),
]


def compute_source_hash(lua_code: str) -> str:
    """Tính hash MD5 (8 ký tự đầu) của nội dung file Lua."""
    return hashlib.md5(lua_code.encode("utf-8")).hexdigest()[:8]


def patch_md_file(md_path: str, source_hash: str) -> bool:
    """
    Thêm source_hash vào YAML frontmatter của file .md.
    Trả về True nếu đã patch, False nếu đã có hoặc lỗi.
    """
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  [Lỗi] Không đọc được {md_path}: {e}")
        return False

    # Kiểm tra nếu đã có source_hash
    if "source_hash:" in content:
        return False

    # Tìm YAML frontmatter: --- ... ---
    match = re.match(r'^(---\n.*?\n)(---)', content, re.DOTALL)
    if not match:
        print(f"  [Lỗi] Không tìm thấy YAML frontmatter trong {md_path}")
        return False

    frontmatter = match.group(1)
    closing = match.group(2)
    rest = content[match.end():]

    # Chèn source_hash trước dấu --- đóng
    new_content = f"{frontmatter}source_hash: {source_hash}\n{closing}{rest}"

    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception as e:
        print(f"  [Lỗi] Không ghi được {md_path}: {e}")
        return False


def main():
    total_patched = 0
    total_skipped = 0
    total_missing = 0

    for docs_dir, lua_dir in PATCH_CONFIGS:
        if not os.path.isdir(docs_dir):
            print(f"[Bỏ qua] Thư mục docs không tồn tại: {docs_dir}")
            continue

        print(f"\n=== Đang patch: {docs_dir} ===")

        for md_filename in sorted(os.listdir(docs_dir)):
            if not md_filename.endswith(".md"):
                continue

            lua_filename = md_filename.replace(".md", ".lua")
            lua_path = os.path.join(lua_dir, lua_filename)
            md_path = os.path.join(docs_dir, md_filename)

            # Tìm file .lua tương ứng
            if not os.path.isfile(lua_path):
                print(f"  [?] Không tìm thấy {lua_filename} → bỏ qua")
                total_missing += 1
                continue

            # Đọc lua và tính hash
            try:
                with open(lua_path, "r", encoding="utf-8", errors="ignore") as f:
                    lua_code = f.read()
            except Exception:
                total_missing += 1
                continue

            source_hash = compute_source_hash(lua_code)

            # Patch file .md
            if patch_md_file(md_path, source_hash):
                print(f"  ✔ {md_filename} → hash: {source_hash}")
                total_patched += 1
            else:
                total_skipped += 1

    print("\n" + "=" * 50)
    print(f"[Kết quả]")
    print(f"  ✔ Đã patch : {total_patched} file")
    print(f"  ⏭ Đã có hash: {total_skipped} file")
    print(f"  ? Thiếu .lua: {total_missing} file")
    print("=" * 50)


if __name__ == "__main__":
    main()
