try:
    import tiktoken
except ImportError:
    tiktoken = None

# Token threshold: require-only files nhỏ hơn ngưỡng này được include đầy đủ
STUB_FULL_THRESHOLD = 400


def count_tokens(text: str) -> int:
    """
    Đếm số token của một chuỗi text bằng tiktoken.
    Trả về -1 nếu không có tiktoken (fallback sang đếm dòng).
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
    Ước tính tổng số token của tất cả chunk results.
    Dùng để quyết định strategy trước khi gọi LLM merge.

    Returns:
        Số token ước tính. -1 nếu không có tiktoken.
    """
    combined = "\n".join(chunk_results)
    return count_tokens(combined)
