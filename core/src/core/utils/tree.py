import os

def generate_slim_tree(start_path, max_depth=3):
    result = []
    start_path = start_path.rstrip(os.sep)

    for root, dirs, files in os.walk(start_path):
        dirs[:] = [d for d in dirs if not d.startswith(('.', '__'))]
        path = root.replace(start_path, '').lstrip(os.sep)
        level = path.count(os.sep)

        if level >= max_depth:
            continue

        indent = ' ' * 4 * level
        result.append(f"{indent}{os.path.basename(root)}/")

        sub_indent = ' ' * 4 * (level + 1)
        # Sửa error: hiển thị tối đa 5 file, after đó mới hiện ... (N files)
        lua_files = [f for f in files if f.endswith('.lua')]

        for i, f in enumerate(lua_files):
            if i < 3:
                result.append(f"{sub_indent}- {f}")
            elif i == 3:
                result.append(f"{sub_indent}- ... ({len(files)} files)")
                break

    return "\n".join(result)
