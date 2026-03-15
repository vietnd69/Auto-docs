"""Tests for require-only stub extraction pipeline."""
import importlib


def test_stub_full_threshold_exists():
    import config
    assert hasattr(config, "STUB_FULL_THRESHOLD")
    assert isinstance(config.STUB_FULL_THRESHOLD, int)
    assert config.STUB_FULL_THRESHOLD == 400


def test_context_reserve_raised():
    import chunked
    assert chunked.CONTEXT_RESERVE == 8000


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
    from rag_get_fnc_content import _compress_module_stub

    lua_code = "BufferedAction = Class(function(self) end)"
    ref_path = "./bufferedaction.lua"

    llm_raw = "-- MODULE: BufferedAction\n-- exports: DoAction\n-- purpose: wraps actions"

    with patch("config.ollama_chat") as mock_chat, \
         patch("rag_get_fnc_content._load_compression_cache", return_value=None), \
         patch("rag_get_fnc_content._save_compression_cache"):
        mock_chat.return_value = {"message": {"content": llm_raw}}
        result = _compress_module_stub(lua_code, ref_path)

    assert result is not None
    assert "-- [REQUIRE MODULE: ./bufferedaction.lua] ---" in result
    assert "-- MODULE: BufferedAction" in result


def test_compress_module_stub_missing_marker():
    """LLM returns output without -- MODULE: → return None, log warning."""
    from rag_get_fnc_content import _compress_module_stub

    with patch("config.ollama_chat") as mock_chat, \
         patch("rag_get_fnc_content._load_compression_cache", return_value=None), \
         patch("rag_get_fnc_content._save_compression_cache"), \
         patch("builtins.print") as mock_print:
        mock_chat.return_value = {"message": {"content": "some garbage output"}}
        result = _compress_module_stub("local x = 1", "./util.lua")

    assert result is None
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "STUB" in printed and "MODULE" in printed


def test_compress_module_stub_llm_exception():
    """LLM raises exception → return None, log warning."""
    from rag_get_fnc_content import _compress_module_stub

    with patch("config.ollama_chat", side_effect=Exception("network error")), \
         patch("rag_get_fnc_content._load_compression_cache", return_value=None), \
         patch("builtins.print") as mock_print:
        result = _compress_module_stub("local x = 1", "./class.lua")

    assert result is None
    printed = " ".join(str(c) for c in mock_print.call_args_list)
    assert "STUB" in printed


def test_compress_module_stub_cache_hit():
    """Cache hit → return cached value without calling LLM."""
    from rag_get_fnc_content import _compress_module_stub

    cached = "-- [REQUIRE MODULE: ./class.lua] ---\n-- MODULE: Class\n-- purpose: OOP base"

    with patch("config.ollama_chat") as mock_chat, \
         patch("rag_get_fnc_content._load_compression_cache", return_value=cached):
        result = _compress_module_stub("anything", "./class.lua")

    mock_chat.assert_not_called()
    assert result == cached


def test_compress_module_stub_lenient_validation():
    """Output with -- MODULE: but missing -- exports: is still accepted."""
    from rag_get_fnc_content import _compress_module_stub

    llm_raw = "-- MODULE: SomeModule\n-- purpose: does something"

    with patch("config.ollama_chat") as mock_chat, \
         patch("rag_get_fnc_content._load_compression_cache", return_value=None), \
         patch("rag_get_fnc_content._save_compression_cache"):
        mock_chat.return_value = {"message": {"content": llm_raw}}
        result = _compress_module_stub("local x = 1", "./somemodule.lua")

    assert result is not None
    assert "-- MODULE: SomeModule" in result
