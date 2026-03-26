from unittest.mock import patch, MagicMock

from llm.client import (
    OLLAMA_HOST,
    OLLAMA_API_KEYS, get_ollama_client,
    _is_rate_limit_error,
)
from llm.settings import OLLAMA_NUM_CTX
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


def test_ollama_chat_forwards_think_false():
    """think=False should be forwarded to client.chat()."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "ok"}}
    with patch("llm.client._make_client", return_value=mock_client), \
         patch("llm.client.OLLAMA_API_KEYS", ["key1"]):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}], think=False)
    mock_client.chat.assert_called_once()
    call_kwargs = mock_client.chat.call_args
    assert call_kwargs.kwargs.get("think") is False or call_kwargs[1].get("think") is False


def test_ollama_chat_forwards_temperature():
    """temperature should be injected into options dict."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "ok"}}
    with patch("llm.client._make_client", return_value=mock_client), \
         patch("llm.client.OLLAMA_API_KEYS", ["key1"]):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}], temperature=0.3)
    call_kwargs = mock_client.chat.call_args
    opts = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options", {})
    assert opts.get("temperature") == 0.3


def test_ollama_chat_forwards_format_schema():
    """format dict should be forwarded to client.chat()."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "{}"}}
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    with patch("llm.client._make_client", return_value=mock_client), \
         patch("llm.client.OLLAMA_API_KEYS", ["key1"]):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}], format=schema)
    call_kwargs = mock_client.chat.call_args
    assert call_kwargs.kwargs.get("format") == schema or call_kwargs[1].get("format") == schema


def test_ollama_chat_defaults_think_true():
    """Default behavior: think=True when not specified."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "ok"}}
    with patch("llm.client._make_client", return_value=mock_client), \
         patch("llm.client.OLLAMA_API_KEYS", ["key1"]):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}])
    call_kwargs = mock_client.chat.call_args
    assert call_kwargs.kwargs.get("think") is True or call_kwargs[1].get("think") is True


def test_ollama_chat_no_api_key_forwards_temperature():
    """No-API-key path: temperature should be forwarded via options dict."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "ok"}}
    with patch("llm.client.OLLAMA_API_KEYS", []), \
         patch("ollama.Client", return_value=mock_client):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}], temperature=0.7)
    call_kwargs = mock_client.chat.call_args
    opts = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options", {})
    assert opts.get("temperature") == 0.7
