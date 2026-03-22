# core/tests/test_main_validate_routing.py
"""
Unit tests for the post-generate validation routing in main.py.
Uses unittest.mock to avoid any LLM or filesystem calls.
"""
import argparse
from dataclasses import dataclass
from unittest.mock import MagicMock, patch
import pytest


@dataclass
class FakeFileResult:
    final_status: str


# Shared patch targets — all module-level names in core.main that touch I/O or LLM.
# process_chunked_file is always patched to prevent real chunked pipeline calls.
COMMON_PATCHES = [
    "core.main.generate_doc",
    "core.main.process_chunked_file",
    "core.main.needs_chunking",
    "core.main.get_lua_files",
    "core.main.safe_read_lua",
    "core.main.extract_lua_references",
    "core.main.format_connected_section",
    "core.main.extract_connected_content",
    "core.main.build_prompt",
    "core.main.count_tokens",
    "core.main.compute_source_hash",
]


def apply_common_patches(tmp_path, extra_patches=None):
    """Return a list of patch context managers with sensible defaults."""
    patches = {
        "core.main.generate_doc": MagicMock(return_value="out.md"),
        "core.main.process_chunked_file": MagicMock(return_value="out.md"),
        "core.main.needs_chunking": MagicMock(return_value=False),
        "core.main.get_lua_files": MagicMock(return_value=["combat.lua"]),
        "core.main.safe_read_lua": MagicMock(return_value="lua code"),
        "core.main.extract_lua_references": MagicMock(return_value=[]),
        "core.main.format_connected_section": MagicMock(return_value=""),
        "core.main.extract_connected_content": MagicMock(return_value=""),
        "core.main.build_prompt": MagicMock(return_value="prompt"),
        "core.main.count_tokens": MagicMock(return_value=100),
        "core.main.compute_source_hash": MagicMock(return_value="abc"),
        "core.main.BASE_DOCS_DIR": str(tmp_path),
        "core.main.BASE_LUA_DIR": str(tmp_path),
    }
    if extra_patches:
        patches.update(extra_patches)
    return patches


class TestNoValidateFlag:
    """--no-validate: process_file is never called; successful generate → processed."""

    def test_process_file_not_called(self, tmp_path):
        patches = apply_common_patches(tmp_path)
        patch_objs = [patch(k, v) for k, v in patches.items()]
        with patch("core.main.process_file") as mock_pf, \
             patch("sys.argv", ["mod-document", "--no-validate"]), \
             patch("core.main.generate_doc"), \
             patch("core.main.process_chunked_file"), \
             patch("core.main.needs_chunking"), \
             patch("core.main.get_lua_files"), \
             patch("core.main.safe_read_lua"), \
             patch("core.main.extract_lua_references"), \
             patch("core.main.format_connected_section"), \
             patch("core.main.extract_connected_content"), \
             patch("core.main.build_prompt"), \
             patch("core.main.count_tokens"), \
             patch("core.main.compute_source_hash"):
            from core.main import main
            main()
        mock_pf.assert_not_called()


class TestValidationRouting:
    """With validation enabled (default), test all four final_status paths."""

    def _run(self, tmp_path, final_status):
        md_file = tmp_path / "out.md"
        md_file.write_text("content")
        fake_result = FakeFileResult(final_status=final_status)
        patches = apply_common_patches(tmp_path)

        # Build context managers manually to avoid unpacking syntax
        with patch("core.main.process_file", return_value=fake_result), \
             patch("core.main.generate_doc", patches["core.main.generate_doc"]), \
             patch("core.main.process_chunked_file", patches["core.main.process_chunked_file"]), \
             patch("core.main.needs_chunking", patches["core.main.needs_chunking"]), \
             patch("core.main.get_lua_files", patches["core.main.get_lua_files"]), \
             patch("core.main.safe_read_lua", patches["core.main.safe_read_lua"]), \
             patch("core.main.extract_lua_references", patches["core.main.extract_lua_references"]), \
             patch("core.main.format_connected_section", patches["core.main.format_connected_section"]), \
             patch("core.main.extract_connected_content", patches["core.main.extract_connected_content"]), \
             patch("core.main.build_prompt", patches["core.main.build_prompt"]), \
             patch("core.main.count_tokens", patches["core.main.count_tokens"]), \
             patch("core.main.compute_source_hash", patches["core.main.compute_source_hash"]), \
             patch("core.main.BASE_DOCS_DIR", patches["core.main.BASE_DOCS_DIR"]), \
             patch("core.main.BASE_LUA_DIR", patches["core.main.BASE_LUA_DIR"]), \
             patch("sys.argv", ["mod-document"]):
            from core.main import main
            main()
        return md_file

    def test_ok_file_survives(self, tmp_path):
        md_file = self._run(tmp_path, "ok")
        assert md_file.exists()

    def test_skipped_chunked_file_survives(self, tmp_path):
        md_file = self._run(tmp_path, "skipped_chunked")
        assert md_file.exists()

    def test_content_failed_deletes_md_file(self, tmp_path):
        md_file = self._run(tmp_path, "content_failed")
        assert not md_file.exists(), "content_failed must delete the .md file"

    def test_format_failed_keeps_md_file(self, tmp_path):
        md_file = self._run(tmp_path, "format_failed")
        assert md_file.exists(), "format_failed must keep the .md file on disk"


class TestValidationException:
    """process_file raises unexpected exception → failed+validate_failed, loop continues."""

    def test_exception_does_not_crash_loop(self, tmp_path):
        """Two files: first triggers exception, second succeeds. Loop must not crash."""
        call_count = 0
        def flaky(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("disk error")
            return FakeFileResult(final_status="ok")

        patches = apply_common_patches(
            tmp_path,
            {"core.main.get_lua_files": MagicMock(return_value=["a.lua", "b.lua"])}
        )
        with patch("core.main.process_file", side_effect=flaky), \
             patch("core.main.generate_doc", patches["core.main.generate_doc"]), \
             patch("core.main.process_chunked_file", patches["core.main.process_chunked_file"]), \
             patch("core.main.needs_chunking", patches["core.main.needs_chunking"]), \
             patch("core.main.get_lua_files", patches["core.main.get_lua_files"]), \
             patch("core.main.safe_read_lua", patches["core.main.safe_read_lua"]), \
             patch("core.main.extract_lua_references", patches["core.main.extract_lua_references"]), \
             patch("core.main.format_connected_section", patches["core.main.format_connected_section"]), \
             patch("core.main.extract_connected_content", patches["core.main.extract_connected_content"]), \
             patch("core.main.build_prompt", patches["core.main.build_prompt"]), \
             patch("core.main.count_tokens", patches["core.main.count_tokens"]), \
             patch("core.main.compute_source_hash", patches["core.main.compute_source_hash"]), \
             patch("core.main.BASE_DOCS_DIR", patches["core.main.BASE_DOCS_DIR"]), \
             patch("core.main.BASE_LUA_DIR", patches["core.main.BASE_LUA_DIR"]), \
             patch("sys.argv", ["mod-document"]):
            from core.main import main
            main()  # must not raise


class TestGenerateFailSkipsValidation:
    """generate returns None → process_file never called."""

    def test_generate_fail_skips_validate(self, tmp_path):
        patches = apply_common_patches(
            tmp_path,
            {"core.main.generate_doc": MagicMock(return_value=None)}
        )
        with patch("core.main.process_file") as mock_pf, \
             patch("core.main.generate_doc", patches["core.main.generate_doc"]), \
             patch("core.main.process_chunked_file", patches["core.main.process_chunked_file"]), \
             patch("core.main.needs_chunking", patches["core.main.needs_chunking"]), \
             patch("core.main.get_lua_files", patches["core.main.get_lua_files"]), \
             patch("core.main.safe_read_lua", patches["core.main.safe_read_lua"]), \
             patch("core.main.extract_lua_references", patches["core.main.extract_lua_references"]), \
             patch("core.main.format_connected_section", patches["core.main.format_connected_section"]), \
             patch("core.main.extract_connected_content", patches["core.main.extract_connected_content"]), \
             patch("core.main.build_prompt", patches["core.main.build_prompt"]), \
             patch("core.main.count_tokens", patches["core.main.count_tokens"]), \
             patch("core.main.compute_source_hash", patches["core.main.compute_source_hash"]), \
             patch("core.main.BASE_DOCS_DIR", patches["core.main.BASE_DOCS_DIR"]), \
             patch("core.main.BASE_LUA_DIR", patches["core.main.BASE_LUA_DIR"]), \
             patch("sys.argv", ["mod-document"]):
            from core.main import main
            main()
        mock_pf.assert_not_called()
