"""Tests for require-only stub extraction pipeline."""
import importlib


def test_stub_full_threshold_exists():
    from llm.settings import STUB_FULL_THRESHOLD
    assert isinstance(STUB_FULL_THRESHOLD, int)
    assert STUB_FULL_THRESHOLD == 400


from unittest.mock import patch, MagicMock


def _make_valid_stub_response(ref_path: str) -> str:
    return (
        f"-- [REQUIRE MODULE: {ref_path}] ---\n"
        "-- MODULE: BufferedAction\n"
        "-- exports: DoAction, Fail, Succeed\n"
        "-- purpose: Wraps deferred action execution with success/fail callbacks\n"
    )


def test_compress_module_stub_success():
    """LLM returns valid output with -- MODULE: marker → return formatted string."""
    from rag.content import _compress_module_stub

    lua_code = "BufferedAction = Class(function(self) end)"
    ref_path = "./bufferedaction.lua"

    llm_raw = "-- MODULE: BufferedAction\n-- exports: DoAction\n-- purpose: wraps actions"

    with patch("rag.content.ollama_chat") as mock_chat, \
         patch("rag.content._load_compression_cache", return_value=None), \
         patch("rag.content._save_compression_cache"):
        mock_chat.return_value = {"message": {"content": llm_raw}}
        result = _compress_module_stub(lua_code, ref_path)

    assert result is not None
    assert "-- [REQUIRE MODULE: ./bufferedaction.lua] ---" in result
    assert "-- MODULE: BufferedAction" in result


def test_compress_module_stub_missing_marker():
    """LLM returns output without -- MODULE: → return None, log warning."""
    from rag.content import _compress_module_stub

    with patch("rag.content.ollama_chat") as mock_chat, \
         patch("rag.content._load_compression_cache", return_value=None), \
         patch("rag.content._save_compression_cache"), \
         patch("builtins.print") as mock_print:
        mock_chat.return_value = {"message": {"content": "some garbage output"}}
        result = _compress_module_stub("local x = 1", "./util.lua")

    assert result is None
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "STUB" in printed and "MODULE" in printed


def test_compress_module_stub_llm_exception():
    """LLM raises exception → return None, log warning."""
    from rag.content import _compress_module_stub

    with patch("rag.content.ollama_chat", side_effect=Exception("network error")), \
         patch("rag.content._load_compression_cache", return_value=None), \
         patch("builtins.print") as mock_print:
        result = _compress_module_stub("local x = 1", "./class.lua")

    assert result is None
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "STUB" in printed


def test_compress_module_stub_cache_hit():
    """Cache hit → return cached value without calling LLM."""
    from rag.content import _compress_module_stub

    cached = "-- [REQUIRE MODULE: ./class.lua] ---\n-- MODULE: Class\n-- purpose: OOP base"

    with patch("rag.content.ollama_chat") as mock_chat, \
         patch("rag.content._load_compression_cache", return_value=cached):
        result = _compress_module_stub("anything", "./class.lua")

    mock_chat.assert_not_called()
    assert result == cached


def test_compress_module_stub_lenient_validation():
    """Output with -- MODULE: but missing -- exports: is still accepted."""
    from rag.content import _compress_module_stub

    llm_raw = "-- MODULE: SomeModule\n-- purpose: does something"

    with patch("rag.content.ollama_chat") as mock_chat, \
         patch("rag.content._load_compression_cache", return_value=None), \
         patch("rag.content._save_compression_cache"):
        mock_chat.return_value = {"message": {"content": llm_raw}}
        result = _compress_module_stub("local x = 1", "./somemodule.lua")

    assert result is not None
    assert "-- MODULE: SomeModule" in result


import tempfile
import os


def _write_temp_lua(content: str) -> str:
    """Write a temp .lua file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_extract_require_stubs_empty_refs():
    """Empty req_refs → return empty string immediately."""
    from rag.content import extract_require_stubs
    assert extract_require_stubs([], max_tokens=5000) == ""


def test_extract_require_stubs_zero_budget():
    """max_tokens <= 0 → return empty string without reading files, no log emitted."""
    from rag.content import extract_require_stubs
    with patch("builtins.print") as mock_print:
        result = extract_require_stubs([("./class.lua", [])], max_tokens=0)
    assert result == ""
    mock_print.assert_not_called()


def test_extract_require_stubs_small_file_full():
    """File with token count <= STUB_FULL_THRESHOLD → included in full with REQUIRE FULL marker."""
    from rag.content import extract_require_stubs

    small_lua = "-- tiny module\nlocal M = {}\nreturn M\n"
    tmp = _write_temp_lua(small_lua)

    try:
        with patch("rag.content._resolve_lua_path", return_value=tmp):
            result = extract_require_stubs([("./tiny.lua", [])], max_tokens=5000)
    finally:
        os.unlink(tmp)

    assert "-- [REQUIRE FULL: ./tiny.lua]" in result
    assert small_lua.strip() in result


def test_extract_require_stubs_large_file_stub():
    """File larger than STUB_FULL_THRESHOLD → calls _compress_module_stub, uses its output."""
    from rag.content import extract_require_stubs

    # 401+ tokens of Lua — we mock count_tokens to return 401
    large_lua = "x = 1\n" * 200
    tmp = _write_temp_lua(large_lua)
    stub_output = "-- [REQUIRE MODULE: ./big.lua] ---\n-- MODULE: Big\n-- purpose: big module"

    try:
        with patch("rag.content._resolve_lua_path", return_value=tmp), \
             patch("rag.content._compress_module_stub", return_value=stub_output) as mock_stub, \
             patch("rag.content.count_tokens", return_value=401):
            result = extract_require_stubs([("./big.lua", [])], max_tokens=5000)
    finally:
        os.unlink(tmp)

    mock_stub.assert_called_once()
    assert stub_output in result


def test_extract_require_stubs_file_not_found():
    """File not found (_resolve_lua_path returns None) → skip silently."""
    from rag.content import extract_require_stubs

    with patch("rag.content._resolve_lua_path", return_value=None):
        result = extract_require_stubs([("./missing.lua", [])], max_tokens=5000)

    assert result == ""


def test_extract_require_stubs_budget_exhausted():
    """Budget runs out after first ref → second ref skipped, log printed."""
    from rag.content import extract_require_stubs

    small_lua = "-- mod\nlocal M = {}\n"
    tmp = _write_temp_lua(small_lua)

    try:
        with patch("rag.content._resolve_lua_path", return_value=tmp), \
             patch("rag.content.count_tokens", return_value=300), \
             patch("builtins.print") as mock_print:
            # budget=350 — first ref uses 300, second would exceed
            result = extract_require_stubs(
                [("./a.lua", []), ("./b.lua", [])],
                max_tokens=350,
            )
    finally:
        os.unlink(tmp)

    assert "-- [REQUIRE FULL: ./a.lua]" in result
    assert "-- [REQUIRE FULL: ./b.lua]" not in result
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "Require-stub" in printed and "budget exhausted" in printed.lower()


def test_extract_require_stubs_stub_failure_skipped():
    """_compress_module_stub returns None → ref skipped, no crash."""
    from rag.content import extract_require_stubs

    large_lua = "x = 1\n" * 200
    tmp = _write_temp_lua(large_lua)

    try:
        with patch("rag.content._resolve_lua_path", return_value=tmp), \
             patch("rag.content._compress_module_stub", return_value=None), \
             patch("rag.content.count_tokens", return_value=401):
            result = extract_require_stubs([("./big.lua", [])], max_tokens=5000)
    finally:
        os.unlink(tmp)

    assert result == ""


def test_extract_connected_for_chunk_req_stubs_appended():
    """
    Chunk with require-only refs → extract_require_stubs() output appended to connected_content.
    Fallback path (chunk_refs empty) is NOT triggered.
    """
    from rag.content import extract_connected_for_chunk

    # Chunk that require()s a module but makes no component.X calls
    chunk_code = 'require "util"\nlocal x = util.DoSomething()'
    stub_output = "-- [REQUIRE FULL: ./util.lua] ---\n-- tiny util"

    with patch("rag.content.extract_connected_content", return_value="") as mock_func, \
         patch("rag.content.extract_require_stubs", return_value=stub_output) as mock_stubs:
        section, content, ref_count = extract_connected_for_chunk(
            chunk_code=chunk_code,
            own_filename="actions.lua",
            max_total_tokens=8000,
        )

    mock_stubs.assert_called_once()
    assert stub_output in content
    # ref_count counts only func_refs; chunk has no components.X calls → 0
    assert ref_count == 0


def test_extract_connected_for_chunk_func_refs_use_full_budget():
    """
    func_refs use the full budget; remaining_budget passed to extract_require_stubs.
    """
    from rag.content import extract_connected_for_chunk

    chunk_code = (
        'require "util"\n'
        'components.health:DoDelta(-10)\n'
    )
    func_content = "-- [full bodies content]"

    # count_tokens is imported at top level in content.py, so patch the binding in rag.content
    with patch("rag.content.extract_connected_content", return_value=func_content), \
         patch("rag.content.extract_require_stubs", return_value="") as mock_stubs, \
         patch("rag.content.count_tokens", return_value=100):
        extract_connected_for_chunk(
            chunk_code=chunk_code,
            own_filename="actions.lua",
            max_total_tokens=8000,
        )

    # remaining_budget should be 8000 - 100 = 7900
    call_kwargs = mock_stubs.call_args
    assert call_kwargs is not None
    passed_budget = call_kwargs[1].get("max_tokens") or call_kwargs[0][1]
    assert passed_budget == 7900


def test_extract_connected_for_chunk_fallback_path_unchanged():
    """
    Fallback path (chunk_refs empty, full_refs provided) still returns early
    without calling extract_require_stubs.
    """
    from rag.content import extract_connected_for_chunk

    # chunk with no refs at all
    chunk_code = "local x = 1"
    full_refs = [("./components/health.lua", ["DoDelta"])]

    with patch("rag.content.extract_require_stubs") as mock_stubs, \
         patch("rag.content.extract_signatures_only", return_value=("", [])):
        extract_connected_for_chunk(
            chunk_code=chunk_code,
            own_filename="actions.lua",
            full_refs=full_refs,
            max_total_tokens=8000,
        )

    mock_stubs.assert_not_called()
