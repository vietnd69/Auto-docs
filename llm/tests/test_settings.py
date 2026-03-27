"""Tests for llm.settings — config loading and typed constants."""
import os


def test_model_constants_exist():
    from llm.settings import MODEL_MAIN, MODEL_UPDATE, MODEL_EMBED, MODEL_COMPRESS
    assert isinstance(MODEL_MAIN, str) and MODEL_MAIN
    assert isinstance(MODEL_UPDATE, str) and MODEL_UPDATE
    assert isinstance(MODEL_EMBED, str) and MODEL_EMBED
    assert isinstance(MODEL_COMPRESS, str) and MODEL_COMPRESS


def test_token_constants_are_positive_ints():
    from llm.settings import (
        PROMPT_TOKEN_LIMIT, MERGE_TOKEN_LIMIT, CONTEXT_RESERVE,
        STUB_FULL_THRESHOLD, CHUNKED_TOKEN_THRESHOLD, OLLAMA_NUM_CTX,
    )
    for val in [PROMPT_TOKEN_LIMIT, MERGE_TOKEN_LIMIT, CONTEXT_RESERVE,
                STUB_FULL_THRESHOLD, CHUNKED_TOKEN_THRESHOLD, OLLAMA_NUM_CTX]:
        assert isinstance(val, int) and val > 0


def test_timing_constants_are_positive_ints():
    from llm.settings import CHUNK_SLEEP, MERGE_SLEEP, NORMAL_SLEEP
    for val in [CHUNK_SLEEP, MERGE_SLEEP, NORMAL_SLEEP]:
        assert isinstance(val, int) and val > 0


def test_validator_constants_are_positive_ints():
    from llm.settings import (
        VALIDATOR_MAX_ITERATIONS, VALIDATOR_LOOP_MAX_ITERATIONS,
        MDX_NODE_TIMEOUT, LUA_CONTEXT_TOKENS,
    )
    assert VALIDATOR_MAX_ITERATIONS == 12
    assert VALIDATOR_LOOP_MAX_ITERATIONS == 12
    assert MDX_NODE_TIMEOUT == 20
    assert LUA_CONTEXT_TOKENS == 7000


def test_env_override_for_int(monkeypatch):
    """MOD_DOC_TOKENS_PROMPT_LIMIT env var overrides the TOML/default value."""
    monkeypatch.setenv("MOD_DOC_TOKENS_PROMPT_LIMIT", "9999")
    import importlib
    import llm.settings as s
    importlib.reload(s)
    assert s.PROMPT_TOKEN_LIMIT == 9999
    importlib.reload(s)  # restore module state to match restored env


def test_env_override_for_str(monkeypatch):
    """MOD_DOC_MODEL_MAIN env var overrides the TOML/default value."""
    monkeypatch.setenv("MOD_DOC_MODEL_MAIN", "test-model:local")
    import importlib
    import llm.settings as s
    importlib.reload(s)
    assert s.MODEL_MAIN == "test-model:local"
    importlib.reload(s)  # restore module state to match restored env


def test_graceful_fallback_without_config_toml(tmp_path, monkeypatch):
    """If config.toml is missing, defaults are used (no exception raised)."""
    monkeypatch.setattr("llm.settings._CONFIG_PATH", tmp_path / "nonexistent.toml")
    import importlib
    import llm.settings as s
    importlib.reload(s)
    assert s.PROMPT_TOKEN_LIMIT == 16000
    assert s.MODEL_MAIN == "qwen3.5:cloud"
    importlib.reload(s)  # restore module state to match restored _CONFIG_PATH


def test_validator_reviewer_temperature():
    from llm.settings import REVIEWER_TEMPERATURE
    assert isinstance(REVIEWER_TEMPERATURE, float)
    assert 0.0 <= REVIEWER_TEMPERATURE <= 2.0


def test_validator_writer_temperature():
    from llm.settings import WRITER_TEMPERATURE
    assert isinstance(WRITER_TEMPERATURE, float)
    assert 0.0 <= WRITER_TEMPERATURE <= 2.0


def test_validator_writer_think():
    from llm.settings import WRITER_THINK
    assert isinstance(WRITER_THINK, int)
    assert WRITER_THINK in (0, 1)


def test_validator_max_conversation_turns():
    from llm.settings import MAX_CONVERSATION_TURNS
    assert isinstance(MAX_CONVERSATION_TURNS, int)
    assert MAX_CONVERSATION_TURNS >= 2


def test_validator_conversation_token_budget():
    from llm.settings import CONVERSATION_TOKEN_BUDGET
    assert isinstance(CONVERSATION_TOKEN_BUDGET, int)
    assert CONVERSATION_TOKEN_BUDGET >= 500


def test_validator_oscillation_threshold():
    from llm.settings import OSCILLATION_THRESHOLD
    assert isinstance(OSCILLATION_THRESHOLD, int)
    assert 0 <= OSCILLATION_THRESHOLD <= 100
