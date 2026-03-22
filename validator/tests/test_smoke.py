"""Smoke test: verify all new modules import correctly."""


def test_import_format_checks():
    from validator.format.checks import ValidationError, validate_all
    assert ValidationError is not None


def test_import_format_mdx():
    from validator.format.mdx import validate_mdx
    assert validate_mdx is not None


def test_import_format_autofix():
    from validator.format.autofix import FixResult, autofix_file
    assert FixResult is not None


def test_import_content_reviewer():
    from validator.content.reviewer import ReviewResult, parse_review_response
    assert ReviewResult is not None


def test_import_content_writer():
    from validator.content.writer import Patch, apply_patches, parse_writer_response
    assert Patch is not None


def test_import_content_loop():
    from validator.content.loop import ContentLoopConfig, ContentLoopResult
    assert ContentLoopConfig is not None


def test_import_pipeline():
    from validator.pipeline import PipelineConfig, FileResult, process_file
    assert PipelineConfig is not None


def test_import_utils():
    from validator.utils import resolve_lua_path, DOCS_DIR, LUA_DIR
    assert resolve_lua_path is not None


def test_import_update():
    from validator.update.validate_update import validate_update
    assert validate_update is not None


def test_import_settings():
    from llm.settings import MDX_NODE_TIMEOUT, VALIDATOR_MAX_ITERATIONS
    assert MDX_NODE_TIMEOUT == 20
    assert VALIDATOR_MAX_ITERATIONS == 10
