import pytest
from pathlib import Path
from validator.utils import resolve_lua_path, DOCS_DIR, LUA_DIR


def test_docs_dir_exists():
    """DOCS_DIR should point to dst-api-webdocs/docs."""
    assert DOCS_DIR.exists(), f"DOCS_DIR not found: {DOCS_DIR}"
    assert DOCS_DIR.name == "docs"


def test_lua_dir_exists():
    """LUA_DIR should point to dst-scripts."""
    assert LUA_DIR.exists(), f"LUA_DIR not found: {LUA_DIR}"
    assert LUA_DIR.name == "dst-scripts"


def test_resolve_lua_path_valid():
    """Known .md file should resolve to .lua file if it exists."""
    md_files = list(DOCS_DIR.glob("*.md"))
    if not md_files:
        pytest.skip("No .md files in DOCS_DIR")
    for md_file in md_files[:10]:
        result = resolve_lua_path(str(md_file))
        if result is not None:
            assert result.endswith(".lua")
            assert Path(result).exists()
            return
    pytest.skip("No .md files with matching .lua found")


def test_resolve_lua_path_nonexistent():
    """Non-existent file should return None."""
    result = resolve_lua_path("/fake/path/docs/nonexistent_xyz_999.md")
    assert result is None


def test_resolve_lua_path_no_docs_in_path():
    """Path without 'docs' segment should return None."""
    result = resolve_lua_path("/some/random/path/file.md")
    assert result is None
