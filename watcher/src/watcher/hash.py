"""
One-time migration script: adds source_hash to the YAML frontmatter of existing .md files.
Run once to migrate legacy docs.

Usage: python -m watcher.hash
"""

import os
import re
import hashlib
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).parents[3]

# Configure directory pairs (docs_dir, lua_dir)
PATCH_CONFIGS = [
    (str(_WORKSPACE_ROOT / "dst-api-webdocs" / "docs" / "components"), str(_WORKSPACE_ROOT / "dst-scripts" / "components")),
    (str(_WORKSPACE_ROOT / "dst-api-webdocs" / "docs" / "behaviours"), str(_WORKSPACE_ROOT / "dst-scripts" / "behaviours")),
]


def compute_source_hash(lua_code: str) -> str:
    """Compute the MD5 hash (first 8 characters) of a Lua file's content."""
    return hashlib.md5(lua_code.encode("utf-8")).hexdigest()[:8]


def patch_md_file(md_path: str, source_hash: str) -> bool:
    """
    Add source_hash to the YAML frontmatter of a .md file.
    Returns True if patched, False if already present or on error.
    """
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  [Error] Could not read {md_path}: {e}")
        return False

    # Check if source_hash is already present
    if "source_hash:" in content:
        return False

    # Find YAML frontmatter block: --- ... ---
    match = re.match(r'^(---\n.*?\n)(---)', content, re.DOTALL)
    if not match:
        print(f"  [Error] No YAML frontmatter found in {md_path}")
        return False

    frontmatter = match.group(1)
    closing = match.group(2)
    rest = content[match.end():]

    # Insert source_hash before the closing ---
    new_content = f"{frontmatter}source_hash: {source_hash}\n{closing}{rest}"

    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception as e:
        print(f"  [Error] Could not write {md_path}: {e}")
        return False


def main():
    total_patched = 0
    total_skipped = 0
    total_missing = 0

    for docs_dir, lua_dir in PATCH_CONFIGS:
        if not os.path.isdir(docs_dir):
            print(f"[Skipping] Docs directory does not exist: {docs_dir}")
            continue

        print(f"\n=== Patching: {docs_dir} ===")

        for md_filename in sorted(os.listdir(docs_dir)):
            if not md_filename.endswith(".md"):
                continue

            lua_filename = md_filename.replace(".md", ".lua")
            lua_path = os.path.join(lua_dir, lua_filename)
            md_path = os.path.join(docs_dir, md_filename)

            # Find the corresponding .lua file
            if not os.path.isfile(lua_path):
                print(f"  [?] Could not find {lua_filename} → skipping")
                total_missing += 1
                continue

            # Read Lua source and compute hash
            try:
                with open(lua_path, "r", encoding="utf-8", errors="ignore") as f:
                    lua_code = f.read()
            except Exception:
                total_missing += 1
                continue

            source_hash = compute_source_hash(lua_code)

            # Patch the .md file
            if patch_md_file(md_path, source_hash):
                print(f"  ✔ {md_filename} → hash: {source_hash}")
                total_patched += 1
            else:
                total_skipped += 1

    print("\n" + "=" * 50)
    print(f"[Results]")
    print(f"  ✔ Patched     : {total_patched} file(s)")
    print(f"  ⏭ Already has hash: {total_skipped} file(s)")
    print(f"  ? Missing .lua: {total_missing} file(s)")
    print("=" * 50)


if __name__ == "__main__":
    main()
