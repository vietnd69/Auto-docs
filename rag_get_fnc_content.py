"""
Trích xuất nội dung function/property từ file Lua dựa trên danh sách tham chiếu.
Chỉ lấy đúng các function và property được yêu cầu, không lấy cả file.
"""

import re
import os

# Thư mục gốc chứa source Lua
LUA_BASE_DIR = "./dst-scripts"


def _resolve_lua_path(ref_path: str) -> str | None:
    """
    Chuyển đường dẫn tham chiếu (vd: ./components/health.lua)
    thành đường dẫn thực trên ổ đĩa (vd: ./dst-scripts/components/health.lua).
    Trả về None nếu file không tồn tại.
    """
    # ref_path dạng "./components/health.lua" hoặc "./util/sourcemodifierlist.lua"
    # Bỏ "./" ở đầu rồi ghép với LUA_BASE_DIR
    clean = ref_path.lstrip("./")
    full_path = os.path.join(LUA_BASE_DIR, clean)
    if os.path.isfile(full_path):
        return full_path
    return None


def _extract_class_name(lua_code: str) -> str | None:
    """
    Tìm tên class chính trong file Lua.
    Pattern: local ClassName = Class(function(self, inst) ...)
    Trả về tên class (vd: "Health", "Combat") hoặc None.
    """
    match = re.search(r'local\s+(\w+)\s*=\s*Class\(', lua_code)
    return match.group(1) if match else None


def _extract_function_body(lua_code: str, class_name: str, func_name: str) -> str | None:
    """
    Trích xuất nội dung một function từ file Lua.
    Tìm pattern: function ClassName:FuncName(...)  ...  end
    Trả về toàn bộ nội dung function (bao gồm dòng khai báo và end).
    """
    # Escape tên để dùng trong regex
    escaped_class = re.escape(class_name)
    escaped_func = re.escape(func_name)
    
    # Pattern: function Health:DoDelta(params)
    pattern = rf'^(function\s+{escaped_class}[.:]{escaped_func}\s*\(.*?\))'
    
    lines = lua_code.split('\n')
    start_idx = None
    
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            start_idx = i
            break
    
    if start_idx is None:
        return None
    
    # Đếm cặp block (function/if/for/while/do ... end) để tìm end tương ứng
    depth = 0
    end_idx = start_idx
    
    # Keywords mở block trong Lua
    block_openers = re.compile(
        r'\b(?:function|if|for|while|repeat)\b'
    )
    block_closers = re.compile(r'\bend\b')
    
    for i in range(start_idx, len(lines)):
        line = lines[i]
        
        # Bỏ qua comment (-- ...)
        code_part = re.sub(r'--.*$', '', line)
        # Bỏ qua string literals đơn giản
        code_part = re.sub(r'"[^"]*"', '""', code_part)
        code_part = re.sub(r"'[^']*'", "''", code_part)
        
        # Đếm openers và closers
        depth += len(block_openers.findall(code_part))
        depth -= len(block_closers.findall(code_part))
        
        if depth <= 0:
            end_idx = i
            break
    
    return '\n'.join(lines[start_idx:end_idx + 1])


def _extract_property_info(lua_code: str, prop_name: str) -> str | None:
    """
    Tìm property trong constructor hoặc khai báo biến.
    Pattern: self.propName = value
    Trả về dòng chứa property hoặc None.
    """
    pattern = rf'^\s*self\.{re.escape(prop_name)}\s*='
    
    for line in lua_code.split('\n'):
        if re.match(pattern, line.strip()):
            return line.strip()
    
    return None


def extract_connected_content(
    lua_refs: list[tuple[str, list[str]]],
    max_lines_per_file: int = 100
) -> str:
    """
    Trích xuất nội dung function/property từ danh sách tham chiếu.
    
    Args:
        lua_refs: Danh sách [(file_path, [func_names]), ...] từ extract_lua_references()
        max_lines_per_file: Giới hạn số dòng tối đa cho mỗi file liên quan
    
    Returns:
        Chuỗi formatted chứa nội dung các function liên quan, hoặc "" nếu không có gì.
    """
    if not lua_refs:
        return ""
    
    sections = []
    
    for ref_path, func_names in lua_refs:
        # Bỏ qua nếu không có function cụ thể cần trích xuất
        if not func_names:
            continue
        
        real_path = _resolve_lua_path(ref_path)
        if real_path is None:
            continue
        
        try:
            with open(real_path, "r", encoding="utf-8", errors="ignore") as f:
                lua_code = f.read()
        except Exception:
            continue
        
        class_name = _extract_class_name(lua_code)
        if class_name is None:
            continue
        
        extracted_items = []
        total_lines = 0
        
        for func_name in func_names:
            if total_lines >= max_lines_per_file:
                break
            
            # Thử tìm function trước
            body = _extract_function_body(lua_code, class_name, func_name)
            if body:
                body_lines = body.count('\n') + 1
                if total_lines + body_lines <= max_lines_per_file:
                    extracted_items.append(body)
                    total_lines += body_lines
                continue
            
            # Nếu không phải function, thử tìm property
            prop = _extract_property_info(lua_code, func_name)
            if prop:
                extracted_items.append(f"-- [property] {prop}")
                total_lines += 1
        
        if extracted_items:
            header = f"--- FILE: {ref_path} (class: {class_name}) ---"
            content = '\n\n'.join(extracted_items)
            sections.append(f"{header}\n{content}")
    
    if not sections:
        return ""
    
    return "\n\n".join(sections)


# === Cho phép chạy độc lập để test ===
if __name__ == "__main__":
    # Test nhanh với một vài ref giả
    test_refs = [
        ("./components/health.lua", ["DoDelta", "GetPercent", "IsDead", "IsInvincible", "minhealth"]),
        ("./components/weapon.lua", ["GetDamage", "CanRangedAttack", "LaunchProjectile", "OnAttack"]),
        ("./components/inventory.lua", ["ApplyDamage", "GetEquippedItem"]),
    ]
    
    result = extract_connected_content(test_refs)
    
    if result:
        print("=== KẾT QUẢ TRÍCH XUẤT ===")
        print(result)
        print(f"\n=== Tổng: {result.count(chr(10)) + 1} dòng ===")
    else:
        print("Không trích xuất được gì!")
