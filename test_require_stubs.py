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
