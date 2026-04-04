# core/tests/test_changelog_pipeline.py
"""Unit tests for core.changelog.pipeline and core.changelog.prompts."""
import json
import pytest
from unittest.mock import patch, MagicMock


SAMPLE_REPORT = {
    "version": {"old": "714014", "new": "718694"},
    "date": "2026-03-23",
    "changes": [
        {"action": "added", "path": "prefabs/w_radio.lua", "diff_summary": "+102 lines"},
        {"action": "added", "path": "stategraphs/SGcritter_bulbin.lua", "diff_summary": "new file"},
        {"action": "modified", "path": "brains/crittersbrain.lua", "diff_summary": "+2 lines, -0 lines"},
        {"action": "deleted", "path": "old/deprecated.lua"},
        {
            "action": "moved",
            "old_path": "old/path.lua",
            "new_path": "new/path.lua",
            "diff_summary": "+3 lines, -1 lines",
        },
        {
            "action": "moved",
            "old_path": "a.lua",
            "new_path": "b.lua",
            # no diff_summary — content_changed: False
        },
    ],
}


class TestBuildChangelogPrompt:
    def _call(self, report=None):
        from core.changelog.prompts import build_changelog_prompt
        r = report or SAMPLE_REPORT
        return build_changelog_prompt(
            old_ver=r["version"]["old"],
            new_ver=r["version"]["new"],
            date=r["date"],
            changes=r["changes"],
        )

    def test_contains_version_header(self):
        prompt = self._call()
        assert "714014 → 718694" in prompt

    def test_contains_date(self):
        prompt = self._call()
        assert "2026-03-23" in prompt

    def test_statistics_present(self):
        prompt = self._call()
        assert "Added: 2" in prompt
        assert "Modified: 1" in prompt
        assert "Deleted: 1" in prompt
        assert "Moved: 2" in prompt

    def test_added_file_rendered(self):
        prompt = self._call()
        assert "[added]" in prompt
        assert "prefabs/w_radio.lua" in prompt
        assert "+102 lines" in prompt

    def test_deleted_file_rendered(self):
        prompt = self._call()
        assert "[deleted]" in prompt
        assert "old/deprecated.lua" in prompt
        assert "(removed)" in prompt

    def test_moved_with_diff_rendered(self):
        prompt = self._call()
        assert "old/path.lua → new/path.lua" in prompt
        assert "+3 lines, -1 lines" in prompt

    def test_moved_no_diff_uses_fallback(self):
        prompt = self._call()
        assert "(no content changes)" in prompt

    def test_unified_diff_excluded(self):
        """unified_diff key must never appear in prompt."""
        report = {
            "version": {"old": "1", "new": "2"},
            "date": "2026-01-01",
            "changes": [
                {
                    "action": "modified",
                    "path": "foo.lua",
                    "diff_summary": "+1 lines",
                    "unified_diff": "--- a/foo.lua\n+++ b/foo.lua\n@@ secret @@",
                }
            ],
        }
        prompt = self._call(report)
        assert "secret" not in prompt
        assert "unified_diff" not in prompt

    def test_output_format_instruction_present(self):
        prompt = self._call()
        assert "## Build 718694" in prompt


class TestLoadDiffReport:
    def test_returns_dict_when_file_exists(self, tmp_path):
        report_path = tmp_path / "diff_report.json"
        report_path.write_text(json.dumps(SAMPLE_REPORT), encoding="utf-8")
        with patch("core.changelog.pipeline.DATA_DIR", str(tmp_path)):
            from core.changelog.pipeline import load_diff_report
            result = load_diff_report()
        assert result == SAMPLE_REPORT

    def test_returns_none_when_file_missing(self, tmp_path, capsys):
        with patch("core.changelog.pipeline.DATA_DIR", str(tmp_path)):
            from core.changelog.pipeline import load_diff_report
            result = load_diff_report()
        assert result is None
        assert "diff_report.json" in capsys.readouterr().out


class TestPrependToChangelog:
    def test_creates_file_if_not_exists(self, tmp_path):
        from core.changelog.pipeline import prepend_to_changelog
        path = tmp_path / "change-log.md"
        prepend_to_changelog("## Build 2\n\nContent.", path)
        text = path.read_text(encoding="utf-8")
        assert "# DST API Changelog" in text
        assert "## Build 2" in text

    def test_prepends_before_existing_content(self, tmp_path):
        from core.changelog.pipeline import prepend_to_changelog
        path = tmp_path / "change-log.md"
        path.write_text("# DST API Changelog\n\n## Build 1\n\nOld.", encoding="utf-8")
        prepend_to_changelog("## Build 2\n\nNew.", path)
        text = path.read_text(encoding="utf-8")
        assert text.index("## Build 2") < text.index("## Build 1")

    def test_header_written_only_once(self, tmp_path):
        from core.changelog.pipeline import prepend_to_changelog
        path = tmp_path / "change-log.md"
        prepend_to_changelog("## Build 2\n\nContent.", path)
        prepend_to_changelog("## Build 3\n\nNewer.", path)
        text = path.read_text(encoding="utf-8")
        assert text.count("# DST API Changelog") == 1


class TestBuildChangelogEntry:
    def _make_fake_response(self, content: str) -> dict:
        return {"message": {"content": content}}

    def test_returns_markdown_string_on_success(self):
        fake_resp = self._make_fake_response("## Build 718694\n\n### Highlights\nSome changes.")
        with patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp):
            from core.changelog.pipeline import build_changelog_entry
            result = build_changelog_entry(SAMPLE_REPORT)
        assert result is not None
        assert "## Build 718694" in result

    def test_returns_none_on_empty_response(self, capsys):
        fake_resp = self._make_fake_response("")
        with patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp):
            from core.changelog.pipeline import build_changelog_entry
            result = build_changelog_entry(SAMPLE_REPORT)
        assert result is None
        assert "empty" in capsys.readouterr().out.lower()

    def test_calls_ollama_chat_with_think_false(self):
        fake_resp = self._make_fake_response("## Build 718694\n\nContent.")
        with patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp) as mock_chat:
            from core.changelog.pipeline import build_changelog_entry
            build_changelog_entry(SAMPLE_REPORT)
        call_kwargs = mock_chat.call_args
        assert call_kwargs.kwargs.get("think") is False or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] is False
        )

    def test_uses_version_from_report_not_config(self):
        """Ensure old_ver/new_ver come from report dict, not core.config.VERSION."""
        captured_messages = []
        def fake_chat(model, messages, *, think=True, **kwargs):
            captured_messages.extend(messages)
            return {"message": {"content": "## Build 99999\n\nContent."}}
        with patch("core.changelog.pipeline.ollama_chat", side_effect=fake_chat):
            from core.changelog.pipeline import build_changelog_entry
            build_changelog_entry(SAMPLE_REPORT)
        prompt_text = captured_messages[0]["content"]
        assert "714014 → 718694" in prompt_text

    def test_returns_none_on_llm_exception(self, capsys):
        """ollama_chat raises (network/server error) → returns None, does not propagate."""
        with patch("core.changelog.pipeline.ollama_chat", side_effect=Exception("network error")):
            from core.changelog.pipeline import build_changelog_entry
            result = build_changelog_entry(SAMPLE_REPORT)
        assert result is None
        assert capsys.readouterr().out  # some warning printed
