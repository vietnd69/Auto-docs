# core/tests/test_chunked_headless_guard.py
"""Unit tests for the isatty headless guard in process_chunked_file()."""
import sys
from unittest.mock import patch, MagicMock
import pytest


class TestHeadlessGuard:
    """When stdin is not a TTY and chunks fail, return None without calling input()."""

    def test_headless_returns_none_without_input(self, tmp_path):
        """Headless mode: all chunks fail → returns None, never calls input()."""
        md_filepath = str(tmp_path / "test.md")

        # input() is a builtin — track whether it is called via a mock
        mock_input = MagicMock(side_effect=AssertionError("input() must not be called in headless mode"))

        with patch("core.pipeline.chunked.strip_bulk_data", return_value="-- lua code"), \
             patch("core.pipeline.chunked.calc_token_budget", return_value=1000), \
             patch("core.pipeline.chunked.split_lua_into_chunks", return_value=["chunk1"]), \
             patch("core.pipeline.chunked.load_checkpoint", return_value=None), \
             patch("core.pipeline.chunked.save_checkpoint"), \
             patch("core.pipeline.chunked.extract_connected_for_chunk", return_value=("", "", 0)), \
             patch("core.pipeline.chunked.build_chunk_prompt", return_value="prompt text"), \
             patch("core.pipeline.chunked.generate_chunk_analysis", return_value=None), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.input", mock_input):

            mock_stdin.isatty.return_value = False

            from core.pipeline.chunked import process_chunked_file

            result = process_chunked_file(
                comp_name="test_component",
                comp_title="Test Component",
                display_filepath="test.lua",
                lua_code="-- lua",
                connected_section="",
                connected_content="",
                source_hash="abc123",
                md_filepath=md_filepath,
                today_date="2026-04-20",
                version="1.0",
            )

        assert result is None
        mock_stdin.isatty.assert_called()
        mock_input.assert_not_called()

    def test_headless_guard_not_reached_when_no_chunk_failures(self, tmp_path):
        """When all chunks succeed, failed_indices is empty and the headless guard is never entered.

        Verifies the guard condition: `if failed_indices:` must be False when chunks succeed.
        Uses early exit via empty chunk_results to avoid the full merge pipeline.
        """
        md_filepath = str(tmp_path / "test.md")

        # Return a valid chunk analysis JSON so the chunk is accepted (not appended to failed_indices)
        valid_chunk_json = '{"functions": [], "events_listens": [], "events_pushes": [], ' \
                           '"constructor_properties": [], "game_tags": [], "external_deps": [], ' \
                           '"system_scope": "component", "partial_description": "Test."}'

        mock_input = MagicMock(side_effect=AssertionError("input() must not be called"))

        with patch("core.pipeline.chunked.strip_bulk_data", return_value="-- lua code"), \
             patch("core.pipeline.chunked.calc_token_budget", return_value=1000), \
             patch("core.pipeline.chunked.split_lua_into_chunks", return_value=["chunk1"]), \
             patch("core.pipeline.chunked.load_checkpoint", return_value=None), \
             patch("core.pipeline.chunked.save_checkpoint"), \
             patch("core.pipeline.chunked.extract_connected_for_chunk", return_value=("", "", 0)), \
             patch("core.pipeline.chunked.build_chunk_prompt", return_value="prompt text"), \
             patch("core.pipeline.chunked.generate_chunk_analysis", return_value=valid_chunk_json), \
             patch("core.pipeline.chunked.pre_synthesize", return_value=(MagicMock(
                 functions=[],
                 game_tags=[],
                 external_deps=[],
                 system_scope="component",
                 events_listens=[],
                 events_pushes=[],
                 constructor_properties=[],
                 partial_descriptions=[],
             ), [])), \
             patch("core.pipeline.chunked.build_merge_prompt", return_value="merge prompt"), \
             patch("core.pipeline.chunked.generate_merged_doc", return_value=None), \
             patch("builtins.input", mock_input):

            from core.pipeline.chunked import process_chunked_file

            result = process_chunked_file(
                comp_name="test_component",
                comp_title="Test Component",
                display_filepath="test.lua",
                lua_code="-- lua",
                connected_section="",
                connected_content="",
                source_hash="abc123",
                md_filepath=md_filepath,
                today_date="2026-04-20",
                version="1.0",
            )

        # No input() must have been called — headless guard was not triggered
        mock_input.assert_not_called()

    def test_tty_mode_calls_input_when_chunks_fail(self, tmp_path):
        """TTY mode: when chunks fail, input() IS called to ask user to confirm."""
        md_filepath = str(tmp_path / "test.md")

        # Simulate user typing "n" (decline to continue)
        mock_input = MagicMock(return_value="n")

        with patch("core.pipeline.chunked.strip_bulk_data", return_value="-- lua code"), \
             patch("core.pipeline.chunked.calc_token_budget", return_value=1000), \
             patch("core.pipeline.chunked.split_lua_into_chunks", return_value=["chunk1"]), \
             patch("core.pipeline.chunked.load_checkpoint", return_value=None), \
             patch("core.pipeline.chunked.save_checkpoint"), \
             patch("core.pipeline.chunked.extract_connected_for_chunk", return_value=("", "", 0)), \
             patch("core.pipeline.chunked.build_chunk_prompt", return_value="prompt text"), \
             patch("core.pipeline.chunked.generate_chunk_analysis", return_value=None), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.input", mock_input):

            mock_stdin.isatty.return_value = True  # TTY mode

            from core.pipeline.chunked import process_chunked_file

            result = process_chunked_file(
                comp_name="test_component",
                comp_title="Test Component",
                display_filepath="test.lua",
                lua_code="-- lua",
                connected_section="",
                connected_content="",
                source_hash="abc123",
                md_filepath=md_filepath,
                today_date="2026-04-20",
                version="1.0",
            )

        # User said "n" so should return None
        assert result is None
        # input() must have been called in TTY mode
        mock_input.assert_called_once()
