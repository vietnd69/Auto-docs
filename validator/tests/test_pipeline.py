import pytest
from validator.pipeline import PipelineConfig, FileResult


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
    for status in ["ok", "content_failed", "format_failed", "skipped_chunked"]:
        result = FileResult(
            filepath="test.md",
            content_result=None,
            format_result=None,
            final_status=status,
        )
        assert result.final_status == status
