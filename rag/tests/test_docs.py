from rag.docs import safe_read_lua, extract_lua_references
import os


def test_safe_read_lua_nonexistent():
    result = safe_read_lua("nonexistent_file.lua")
    assert result is None


def test_extract_lua_references_empty():
    result = extract_lua_references("", "test.lua")
    assert isinstance(result, (list, set, dict))
