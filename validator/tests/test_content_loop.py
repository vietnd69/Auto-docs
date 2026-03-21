import pytest
from validator.content.loop import ContentLoopConfig, ContentLoopResult


def test_content_loop_config_defaults():
    config = ContentLoopConfig()
    assert config.max_iterations == 3
    assert config.writer_model == "qwen3.5:cloud"
    assert config.reviewer_model == "qwen3.5:cloud"


def test_content_loop_config_custom():
    config = ContentLoopConfig(max_iterations=5, writer_model="a", reviewer_model="b")
    assert config.max_iterations == 5
    assert config.writer_model == "a"
    assert config.reviewer_model == "b"


def test_content_loop_result_approved():
    result = ContentLoopResult(approved=True, iterations=1, final_issues=[])
    assert result.approved is True
    assert result.iterations == 1
    assert result.final_issues == []


def test_content_loop_result_rejected():
    result = ContentLoopResult(approved=False, iterations=3, final_issues=["issue"])
    assert result.approved is False
    assert result.final_issues == ["issue"]
