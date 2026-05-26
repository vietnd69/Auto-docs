"""
Module chứa các hàm xử lý file Lua dùng chung cho prompt.py và test.py.
- Tìm file .lua trong thư mục
- Đọc file Lua an toàn
- Extract references (require, components)
- Format connected section
- Hash source code
- Làm sạch output từ model
"""

import os
import re
import hashlib


def extract_lua_references(lua_code: str, own_filename: str) -> list[tuple[str, list[str]]]:
    """
    Trích xuất các tham chiếu từ mã Lua:
    - require("path/to/module") → file path
    - components.X:FuncName() → file path + function names
    Trả về list[(file_path, [func_names]), ...] (bỏ chính file đang xử lý).
    """
    refs: dict[str, set[str]] = {}
    own_name = own_filename.replace(".lua", "")

    # 1. Tìm require("...") → giữ nguyên path gốc
    for match in re.finditer(r'require\s*\(\s*["\']([^"\']+)["\']\s*\)', lua_code):
        module_path = match.group(1)
        file_path = f"./{module_path}.lua"
        if module_path.split("/")[-1] != own_name:
            refs.setdefault(file_path, set())

    # 2. Tìm components.X → map thành ./components/X.lua
    for match in re.finditer(r'(?<!self\.)components\.(\w+)', lua_code):
        comp_name = match.group(1)
        if comp_name != own_name:
            file_path = f"./components/{comp_name}.lua"
            refs.setdefault(file_path, set())

    # 3. Tìm components.X:FuncName() hoặc components.X.FuncName → trích function name
    for match in re.finditer(r'(?<!self\.)components\.(\w+)[:\.](\w+)', lua_code):
        comp_name = match.group(1)
        func_name = match.group(2)
        if comp_name != own_name:
            file_path = f"./components/{comp_name}.lua"
            refs.setdefault(file_path, set()).add(func_name)

    return [(path, sorted(funcs)) for path, funcs in sorted(refs.items())]


def safe_read_lua(filepath: str) -> str | None:
    """
    Đọc file Lua, bỏ qua lỗi encoding thay vì crash.
    Trả về None nếu không đọc được hoặc là file binary (bytecode, data, etc.).
    """
    try:
        # Detect binary file: đọc 8KB đầu, nếu chứa null byte → binary
        with open(filepath, "rb") as bf:
            chunk = bf.read(8192)
        if b'\x00' in chunk:
            print(f"  [SKIP] {filepath} — file binary (không phải source code), bỏ qua.")
            return None

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        print(f"[Error] Không thể đọc file {filepath}: {e}")
        return None


def compute_source_hash(lua_code: str) -> str:
    """
    Tính hash MD5 (8 ký tự đầu) của nội dung file Lua.
    Dùng để so sánh khi code update, nhận biết file nào đã thay đổi.
    """
    return hashlib.md5(lua_code.encode("utf-8")).hexdigest()[:8]


def inject_frontmatter_field(text: str, field: str, value: str) -> str:
    """Insert a missing field into YAML frontmatter. No-op if already present or no frontmatter."""
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text
    if re.search(rf'^{re.escape(field)}:', fm_match.group(1), re.MULTILINE):
        return text
    # Insert after the last frontmatter key, before the closing ---
    insert_pos = fm_match.start() + 4 + len(fm_match.group(1))
    return text[:insert_pos] + f"\n{field}: {value}" + text[insert_pos:]


def format_connected_section(lua_refs: list[tuple[str, list[str]]]) -> str:
    """
    Format danh sách tham chiếu Lua thành chuỗi cho prompt.
    Trả về chuỗi rỗng nếu không có tham chiếu.
    """
    if not lua_refs:
        return ""

    ref_items = []
    for path, funcs in lua_refs:
        if funcs:
            ref_items.append(f'("{path}", [{", ".join(funcs)}])')
        else:
            ref_items.append(f'("{path}", [])')
    return "Connected files and functions:\n[" + ",\n".join(ref_items) + "]"


def clean_model_output(text: str) -> str:
    """
    Làm sạch output từ model:
    1. Xóa thinking block <think>...</think> của qwen3
    2. Xóa markdown code fence nếu model vẫn bọc output
    """
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    if '</think>' in text:
        text = text[text.index('</think>') + len('</think>'):]
    text = text.strip()
    text = re.sub(r'^```\w*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    return text.strip()


def get_lua_files(lua_dir: str, deep: bool = False) -> list[str]:
    """
    Lấy danh sách file .lua trong thư mục, sắp xếp theo abc.
    Nếu deep=True, duyệt đệ quy vào các thư mục con.
    Trả về list đường dẫn tương đối so với lua_dir (dùng forward slash).
    """
    if not os.path.isdir(lua_dir):
        print(f"[Error] Thư mục không tồn tại: {lua_dir}")
        return []

    results = []
    if deep:
        for root, _, files in os.walk(lua_dir):
            for f in files:
                if f.endswith(".lua"):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, lua_dir)
                    results.append(rel_path.replace(os.sep, "/"))
    else:
        for f in os.listdir(lua_dir):
            if f.endswith(".lua") and os.path.isfile(os.path.join(lua_dir, f)):
                results.append(f)

    return sorted(results)
