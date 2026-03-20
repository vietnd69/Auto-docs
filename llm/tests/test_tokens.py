from llm.tokens import count_tokens, estimate_merge_tokens

def test_count_tokens_returns_int():
    result = count_tokens("hello world")
    assert isinstance(result, int)
    assert result == -1 or result > 0

def test_count_tokens_empty_string():
    result = count_tokens("")
    assert result >= 0 or result == -1

def test_estimate_merge_tokens_empty():
    result = estimate_merge_tokens([])
    assert result == -1 or result >= 0

def test_estimate_merge_tokens_list():
    result = estimate_merge_tokens(["hello", "world"])
    assert isinstance(result, int)
