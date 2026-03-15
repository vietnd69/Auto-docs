import re

text = """---
id: upgrademoduleremover
title: Upgrademoduleremover
description: A placeholder component with no functional behavior
tags: []
sidebar_position: 10
something: <replace_this>
another: []
---

# Upgrademoduleremover
"""

def fix_empty_tags_and_placeholders(text: str) -> tuple[str, list[str]]:
    """
    Sửa lỗi frontmatter:
    - `tags: []` -> `tags: [stub]`
    - Các giá trị placeholder kiểu `<...>` hoặc `[]` sẽ bị remove hoặc thay bằng "TODO".
    """
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n', text)
    if not fm_match:
        return text, []
        
    fm = fm_match.group(1)
    new_lines = []
    applied = []
    
    for line in fm.splitlines():
        original = line
        
        # 1. tags: []
        if re.match(r'^tags:\s*\[\s*\]\s*$', line):
            line = "tags: [stub]"
            applied.append("Thay thế `tags: []` thành `tags: [stub]`")
            
        # 2. Xóa hoặc thay thế placeholder <...> (cẩn thận không dính vào các key hợp lệ)
        elif bool(re.search(r'<[^>]+>|\[\]', line)):
            # Tạm thời thay placeholder thành "TODO" (với ngoặc kép cho an toàn YAML)
            line = re.sub(r'<[^>]+>|\[\]', '"TODO"', line)
            applied.append("Thay thế placeholder `<...>` hoặc `[]` thành `\"TODO\"`")
            
        new_lines.append(line)
        
    if applied:
        new_fm = "\n".join(new_lines)
        new_text = f"---\n{new_fm}\n---\n" + text[fm_match.end():]
        return new_text, list(set(applied))
        
    return text, []

new_text, applied = fix_empty_tags_and_placeholders(text)
print(applied)
print(new_text)
