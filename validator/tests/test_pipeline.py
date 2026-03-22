import pytest
from unittest.mock import patch

from validator.content.loop import ContentLoopResult
from validator.pipeline import PipelineConfig, FileResult, process_file, CHUNKED_TOKEN_THRESHOLD


def test_pipeline_config_defaults():
    config = PipelineConfig()
    assert config.content_max_iterations == 3
    assert config.writer_model == "qwen3.5:cloud"
    assert config.reviewer_model == "qwen3.5:cloud"
    assert config.skip_content is False
    assert config.skip_format is False


def test_pipeline_config_custom():
    config = PipelineConfig(
        content_max_iterations=5,
        writer_model="model-a",
        reviewer_model="model-b",
        skip_content=True,
    )
    assert config.content_max_iterations == 5
    assert config.skip_content is True


def test_file_result_ok():
    result = FileResult(
        filepath="test.md",
        content_result=None,
        format_result=None,
        final_status="ok",
    )
    assert result.final_status == "ok"


def test_file_result_statuses():
    for status in ["ok", "content_failed", "format_failed"]:
        result = FileResult(
            filepath="test.md",
            content_result=None,
            format_result=None,
            final_status=status,
        )
        assert result.final_status == status


def test_chunked_file_runs_content_validation(tmp_path):
    """Files with large Lua source now run run_chunked_content_loop, not skip."""
    md = tmp_path / "test.md"
    md.write_text("---\ntitle: T\n---\n## Sec\ncontent\n", encoding="utf-8")

    approved = ContentLoopResult(approved=True, iterations=1, final_issues=[])
    config = PipelineConfig(skip_format=True)

    with (
        patch("validator.pipeline.resolve_lua_path", return_value=str(tmp_path / "test.lua")),
        patch("validator.pipeline.safe_read_lua", return_value="-- large lua\n"),
        patch("validator.pipeline.count_tokens", return_value=CHUNKED_TOKEN_THRESHOLD),
        patch("validator.pipeline.run_chunked_content_loop", return_value=approved) as mock_chunked,
        patch("validator.pipeline.run_content_loop") as mock_standard,
    ):
        result = process_file(str(md), config)

    mock_chunked.assert_called_once()
    mock_standard.assert_not_called()
    assert result.final_status == "ok"
    assert result.final_status != "skipped_chunked"


def test_small_file_runs_standard_content_loop(tmp_path):
    """Files below CHUNKED_TOKEN_THRESHOLD route to run_content_loop."""
    md = tmp_path / "test.md"
    md.write_text("---\ntitle: T\n---\n## Sec\ncontent\n", encoding="utf-8")

    approved = ContentLoopResult(approved=True, iterations=1, final_issues=[])
    config = PipelineConfig(skip_format=True)

    with (
        patch("validator.pipeline.resolve_lua_path", return_value=str(tmp_path / "test.lua")),
        patch("validator.pipeline.safe_read_lua", return_value="-- small lua\n"),
        patch("validator.pipeline.count_tokens", return_value=1000),
        patch("validator.pipeline.run_content_loop", return_value=approved) as mock_standard,
        patch("validator.pipeline.run_chunked_content_loop") as mock_chunked,
    ):
        result = process_file(str(md), config)

    mock_standard.assert_called_once()
    mock_chunked.assert_not_called()
    assert result.final_status == "ok"
