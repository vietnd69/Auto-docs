"""
Shared Lua file processing utilities used by prompt.py and test.py.
- Find .lua files in a directory
- Safe Lua file reading
- Extract references (require, components)
- Format connected section
- Hash source code
- Clean model output
"""

import os
import re
import hashlib


def extract_lua_references(lua_code: str, own_filename: str) -> list[tuple[str, list[str]]]:
    """
    Extract references from Lua code:
    - require("path/to/module") → file path
    - components.X:FuncName() → file path + function names
    Returns list[(file_path, [func_names]), ...] (excluding the file being processed).
    """
    refs: dict[str, set[str]] = {}
    own_name = own_filename.replace(".lua", "")

    # 1. Find require("...") → preserve original path
    for match in re.finditer(r'require\s*\(\s*["\']([^"\']+)["\']\s*\)', lua_code):
        module_path = match.group(1)
        file_path = f"./{module_path}.lua"
        if module_path.split("/")[-1] != own_name:
            refs.setdefault(file_path, set())

    # 2. Find components.X → map to ./components/X.lua
    for match in re.finditer(r'(?<!self\.)components\.(\w+)', lua_code):
        comp_name = match.group(1)
        if comp_name != own_name:
            file_path = f"./components/{comp_name}.lua"
            refs.setdefault(file_path, set())

    # 3. Find components.X:FuncName() or components.X.FuncName → extract function name
    for match in re.finditer(r'(?<!self\.)components\.(\w+)[:\.](\w+)', lua_code):
        comp_name = match.group(1)
        func_name = match.group(2)
        if comp_name != own_name:
            file_path = f"./components/{comp_name}.lua"
            refs.setdefault(file_path, set()).add(func_name)

    return [(path, sorted(funcs)) for path, funcs in sorted(refs.items())]


def safe_read_lua(filepath: str) -> str | None:
    """
    Read a Lua file, ignoring encoding errors instead of crashing.
    Returns None if the file cannot be read or is binary (bytecode, data, etc.).
    """
    try:
        # Detect binary file: read first 8KB, if it contains a null byte → binary
        with open(filepath, "rb") as bf:
            chunk = bf.read(8192)
        if b'\x00' in chunk:
            print(f"  [SKIP] {filepath} — binary file (not source code), skipping.")
            return None

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        print(f"[Error] Cannot read file {filepath}: {e}")
        return None


def compute_source_hash(lua_code: str) -> str:
    """
    Compute MD5 hash (first 8 characters) of Lua file contents.
    Used for comparison during code updates to identify changed files.
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
    Format a list of Lua references into a string for use in prompts.
    Returns an empty string if there are no references.
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
    Clean model output:
    1. Remove qwen3 thinking blocks <think>...</think>
    2. Strip markdown code fences if the model wraps its output in them
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
    Get a sorted list of .lua files in a directory.
    If deep=True, recurse into subdirectories.
    Returns a list of paths relative to lua_dir (using forward slashes).
    """
    if not os.path.isdir(lua_dir):
        print(f"[Error] Directory does not exist: {lua_dir}")
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
