from llm.client import (
    OLLAMA_HOST, OLLAMA_NUM_CTX,
    OLLAMA_API_KEYS, get_ollama_client,
    _is_rate_limit_error,
)
import ollama

def test_ollama_host_is_string():
    assert isinstance(OLLAMA_HOST, str)
    assert OLLAMA_HOST.startswith("http")

def test_num_ctx_is_large_int():
    assert isinstance(OLLAMA_NUM_CTX, int)
    assert OLLAMA_NUM_CTX >= 32_000

def test_api_keys_is_list():
    assert isinstance(OLLAMA_API_KEYS, list)

def test_get_ollama_client_returns_client():
    client = get_ollama_client()
    assert isinstance(client, ollama.Client)

def test_rate_limit_detection_negative():
    assert _is_rate_limit_error(ValueError("not rate limit")) is False
