"""
Trích xuất nội dung function/property từ file Lua dựa trên danh sách tham chiếu.
Chỉ lấy đúng các function và property được yêu cầu, không lấy cả file.
"""

import re
import os

from get_docs import extract_lua_references, format_connected_section

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


def extract_signatures_only(
    lua_refs: list[tuple[str, list[str]]],
    max_output_tokens: int = 0,   # 0 = không giới hạn
) -> tuple[str, list[tuple[str, list[str]]]]:
    """
    Fallback mode: chỉ lấy dòng khai báo function (signature), không lấy body.

    Nếu max_output_tokens > 0 và output vượt ngưỡng, refs cuối danh sách sẽ bị
    bỏ qua (truncate by ref, không truncate giữa chừng một ref).

    Returns:
        (content, kept_refs)
        content:    chuỗi signatures; empty string nếu không tìm được gì.
        kept_refs:  list các ref tuple thực sự xuất hiện trong output.
    """
    sections = []
    resolved_refs = []   # track refs đã resolve được ít nhất 1 sig

    for ref_path, func_names in lua_refs:
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

        sigs = []
        for func_name in func_names:
            escaped_class = re.escape(class_name)
            escaped_func  = re.escape(func_name)
            pattern = rf'^function\s+{escaped_class}[.:]{escaped_func}\s*\(.*?\)'
            for line in lua_code.split("\n"):
                if re.match(pattern, line.strip()):
                    sigs.append(f"--[SIGONLY: {line.strip()}]")
                    break

        if sigs:
            header = f"--- FILE: {ref_path} (class: {class_name}) ---"
            sections.append(header + "\n" + "\n".join(sigs))
            resolved_refs.append((ref_path, func_names))

    if not sections:
        return "", []

    # Truncation: cắt bớt refs cuối nếu vượt max_output_tokens
    if max_output_tokens > 0:
        # Lazy import để tránh circular dependency
        from chunked import count_tokens
        kept_sections = []
        kept_refs = []
        for section, ref in zip(sections, resolved_refs):
            candidate = "\n\n".join(kept_sections + [section])
            total = count_tokens(candidate)
            if total == -1:
                total = len(candidate) // 4   # char-count fallback
            if total > max_output_tokens:
                print(
                    f"  [SIG] Truncated: giữ {len(kept_sections)}/{len(sections)} refs "
                    f"để fit trong {max_output_tokens} tokens"
                )
                break
            kept_sections.append(section)
            kept_refs.append(ref)
        sections = kept_sections
        resolved_refs = kept_refs

    if not sections:
        return "", []

    return "\n\n".join(sections), resolved_refs


def extract_connected_content(
    lua_refs: list[tuple[str, list[str]]],
    max_lines_per_file: int = 100,
    max_total_tokens: int = 0,    # 0 = không giới hạn
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

    full_result = "\n\n".join(sections)

    # Kiểm tra token budget nếu có giới hạn
    if max_total_tokens > 0:
        # Lazy import để tránh circular dependency
        from chunked import count_tokens
        total_tokens = count_tokens(full_result)

        if total_tokens == -1:
            # Fallback khi tiktoken không có: ước tính bằng char count (1 token ≈ 4 chars)
            total_tokens = len(full_result) // 4

        if total_tokens > max_total_tokens:
            print(
                f"  [CONTEXT] Full content ~{total_tokens} tokens "
                f"> ngưỡng {max_total_tokens} → chuyển sang signature-only mode"
            )
            sig_content, _ = extract_signatures_only(lua_refs, max_output_tokens=max_total_tokens)
            return sig_content

    return full_result


def extract_connected_for_chunk(
    chunk_code: str,
    own_filename: str,
    full_refs: list[tuple[str, list[str]]] | None = None,
    max_lines_per_file: int = 100,
    max_total_tokens: int = 3500,
) -> tuple[str, str, int]:
    """
    Trích xuất connected_section + connected_content + ref_count cho 1 chunk cụ thể.

    Smart fallback (khi chunk_refs rỗng):
        Chỉ kích hoạt cho 2 trường hợp biên:
        - Cross-chunk require: require() ở chunk trước, chunk này dùng module nhưng không re-import.
        - self.components.X: bị negative lookbehind của extract_lua_references bỏ qua.

    Known limitation:
        Require-based cross-chunk KHÔNG bị bắt bởi filter `components.<name>`.
        Chunk đó nhận ("", "", 0) — graceful degrade.

    Returns:
        (connected_section, connected_content, ref_count)
    """
    chunk_refs = extract_lua_references(chunk_code, own_filename)

    # Fallback: chunk không có ref cục bộ nhưng full file có refs.
    if not chunk_refs and full_refs:
        # Filter full_refs xuống chỉ còn refs mà chunk thực sự reference
        filtered_refs = [
            (ref_path, funcs)
            for ref_path, funcs in full_refs
            if re.search(
                rf'\bcomponents\.{re.escape(ref_path.split("/")[-1].replace(".lua", ""))}',
                chunk_code,
            )
        ]

        if not filtered_refs:
            return "", "", 0

        print(f"    [CTX] Chunk không có local refs nhưng có external call → fallback signatures từ filtered_refs ({len(filtered_refs)} refs)")
        fallback_content, fallback_kept_refs = extract_signatures_only(filtered_refs, max_output_tokens=max_total_tokens)

        if not fallback_content:
            return "", "", 0

        fallback_section = format_connected_section(fallback_kept_refs)
        return fallback_section, fallback_content, len(fallback_kept_refs)

    connected_content = extract_connected_content(
        chunk_refs,
        max_lines_per_file=max_lines_per_file,
        max_total_tokens=max_total_tokens,
    )

    if not connected_content:
        return "", "", len(chunk_refs)

    # Rebuild section từ kept_refs thực tế
    if "--[SIGONLY:" in connected_content:
        _, kept_refs = extract_signatures_only(chunk_refs, max_output_tokens=max_total_tokens)
    else:
        kept_refs = chunk_refs

    connected_section = format_connected_section(kept_refs)
    return connected_section, connected_content, len(kept_refs)


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
