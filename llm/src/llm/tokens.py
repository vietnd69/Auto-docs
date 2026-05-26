from llm.settings import STUB_FULL_THRESHOLD

try:
    import tiktoken
except ImportError:
    tiktoken = None


def count_tokens(text: str) -> int:
    """
    Count the number of tokens in a text string using tiktoken.
    Returns -1 if tiktoken is not available (fallback to line counting).
    """
    if tiktoken:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass
    return -1


def estimate_merge_tokens(chunk_results: list[str]) -> int:
    """
    Estimate the total token count across all chunk results.
    Used to decide the merge strategy before calling the LLM merge step.

    Returns:
        Estimated token count. -1 if tiktoken is not available.
    """
    combined = "\n".join(chunk_results)
    return count_tokens(combined)
