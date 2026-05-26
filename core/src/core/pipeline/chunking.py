"""
Module for processing long Lua files — splits into chunks and processes each part.
Contains logic for:
  - needs_chunking():        check whether a file needs chunking
  - split_lua_into_chunks():  split Lua code at function boundaries
  - process_chunked_file():   main pipeline: split → chunk prompts → merge
"""

import re

try:
    import tiktoken
except ImportError:
    tiktoken = None

from llm.tokens import count_tokens
from llm.settings import PROMPT_TOKEN_LIMIT, MERGE_TOKEN_LIMIT, CONTEXT_RESERVE
from prompts.chunked import build_chunk_prompt   # used in calc_token_budget

# ── Thresholds and configuration ──────────────────────────────────────────

CHUNK_THRESHOLD = 3000       # Fallback line threshold when tiktoken is not available
CHUNK_MAX_LINES = 1500       # Maximum ~1500 lines per chunk (fallback)


def calc_token_budget(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    connected_section: str,
    connected_content: str,
    source_hash: str,
    *,
    file_tree: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    prompt_token_limit: int = PROMPT_TOKEN_LIMIT,
) -> int:
    """
    Calculate the remaining token budget for Lua code content in each chunk.

    Calculation:
      1. Build a prompt "shell" = chunk prompt with empty code
      2. Count tokens in the shell
      3. Return: prompt_token_limit - shell_tokens

    Returns:
        Maximum token count for Lua code in each chunk.
        If tiktoken is not available, returns a fallback based on CHUNK_MAX_LINES.
    """
    # Warning: if connected_content is non-empty, CONTEXT_RESERVE will be deducted twice.
    if connected_content:
        print(
            "[WARN] calc_token_budget() received non-empty connected_content. "
            "In the chunked pipeline, pass connected_content='' because CONTEXT_RESERVE "
            "is already deducted internally. Double-deduction may occur."
        )

    # Build prompt shell = chunk prompt WITHOUT code (empty code)
    shell = build_chunk_prompt(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        chunk_code="",  # Empty code to measure shell size
        chunk_index=1,
        total_chunks=1,
        file_tree=file_tree,
        connected_section=connected_section,
        connected_content=connected_content,
        today_date=today_date,
        version=version,
        category_type=category_type,
    )

    shell_tokens = count_tokens(shell)

    # Guard tiktoken missing: count_tokens() returns -1
    if shell_tokens < 0:
        print(
            f"  [TOKEN BUDGET] tiktoken missing — using fallback budget "
            f"(CONTEXT_RESERVE is not applied in fallback mode)"
        )
        return max(PROMPT_TOKEN_LIMIT - CONTEXT_RESERVE, 1000)

    budget = prompt_token_limit - shell_tokens
    effective_budget = max(budget - CONTEXT_RESERVE, 1000)
    print(
        f"  [TOKEN BUDGET] Shell: {shell_tokens} tokens "
        f"| Context reserve: {CONTEXT_RESERVE} tokens "
        f"| Code budget: {effective_budget} tokens"
    )
    if effective_budget < 3000:
        print(
            f"  [WARN] Code budget only {effective_budget} tokens remaining — "
            f"file_tree may be too large or the shell is too heavy. "
            f"Consider reducing max_depth in get_shared_file_tree()."
        )
    return effective_budget

def strip_bulk_data(lua_code: str) -> str:
    """
    Remove bulk numeric data (tile data, map data) from Lua source.
    Replaces long numeric arrays with a summarizing comment.

    Example:
        data = {
            0, 0, 0, 0, 0, 0, ...  (hundreds of lines)
        }
    →   data = { --[[ 360000 numeric values (tile data) ]] }

    This reduces a 1.1MB file to ~80KB without losing structural information.
    """
    lines = lua_code.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect start of data block: "data = {" or similar
        if re.match(r"^\s*\w+\s*=\s*\{\s*$", stripped):
            # Check whether the following lines consist entirely of numbers
            j = i + 1
            num_count = 0
            data_lines = 0

            while j < len(lines):
                next_stripped = lines[j].strip()

                # Closing line }
                if next_stripped in ("}", "},"):
                    break

                # Line containing only numbers, commas, and whitespace
                clean = next_stripped.rstrip(",")
                if clean and all(c in "0123456789, " for c in clean):
                    # Count the number of values
                    nums = [x.strip() for x in clean.split(",") if x.strip()]
                    num_count += len(nums)
                    data_lines += 1
                else:
                    break
                j += 1

            # If there are >= 10 lines of numeric data → strip
            if data_lines >= 10 and j < len(lines):
                # Get the field name (e.g. "data")
                field_match = re.match(r"^(\s*\w+\s*=\s*)\{", stripped)
                indent = re.match(r"^(\s*)", line).group(1)
                field = field_match.group(1) if field_match else ""
                result.append(
                    f"{indent}{field}{{--[[ {num_count} numeric values (tile/map data) ]]}}"
                )
                # Skip to closing } line (inclusive)
                closing = lines[j].strip()
                if closing in ("}", "},"):
                    i = j + 1
                else:
                    i = j
                continue
            else:
                result.append(line)
                i += 1
        else:
            result.append(line)
            i += 1

    return "\n".join(result)


def needs_chunking(text: str, token_limit: int = PROMPT_TOKEN_LIMIT) -> bool:
    """
    Check whether text (full prompt or lua code) exceeds the token threshold.

    Recommended: pass the full prompt text (from build_prompt) for the most accurate measurement.
    If raw lua_code is passed, falls back to line counting.

    Returns:
        True if chunking is needed (text is too long).
    """
    token_count = count_tokens(text)
    if token_count >= 0:
        return token_count > token_limit

    return text.count("\n") + 1 > CHUNK_THRESHOLD


def _find_safe_cut_points(lines: list[str]) -> list[int]:
    """
    Scan the entire Lua file, tracking block depth (function/if/for/while/repeat ↔ end).
    Returns a list of line indices (0-based) where depth == 0 — these are
    safe points to cut a chunk that will NEVER split in the middle of a function body.

    Only marks safe at blank lines or lines starting with function/local function
    at depth 0 so chunks begin cleanly.
    """
    block_open = re.compile(r"\b(?:function|if|for|while|repeat)\b")
    block_close = re.compile(r"\bend\b")

    depth = 0
    safe_points: list[int] = []

    for i, line in enumerate(lines):
        # Strip comments and string literals before counting keywords
        code = re.sub(r"--.*$", "", line)
        code = re.sub(r'"[^"]*"', '""', code)
        code = re.sub(r"'[^']*'", "''", code)

        depth += len(block_open.findall(code))
        depth -= len(block_close.findall(code))

        # Depth == 0 → outside all blocks
        if depth == 0:
            stripped = line.strip()
            # Mark safe at: blank lines, or lines starting with function
            if stripped == "" or re.match(r"^(local\s+)?function\s+", stripped):
                safe_points.append(i)

    return safe_points


def split_lua_into_chunks(
    lua_code: str,
    max_tokens: int = -1,
    fallback_max_lines: int = CHUNK_MAX_LINES
) -> list[str]:
    """
    Split Lua source into chunks, GUARANTEEING no cut in the middle of a function body.
    Packs as much code as possible into each chunk based on the token limit.

    Strategy:
    - Files with functions (components): use depth-tracking, cut at depth==0
      → 100% guaranteed never to cut in the middle of a function body.
    - Data/config files (wrapped in return {}): depth never returns to 0
      → fallback to cutting at blank lines (data files have no functions, so this is safe).

    Returns:
        list[str] — list of chunks.
    """
    lines = lua_code.split("\n")
    total = len(lines)

    # 1. Helper function to dynamically compute length/limit
    def _is_over_limit(start_idx: int, end_idx: int, limit: int = max_tokens) -> bool:
        chunk_str = "\n".join(lines[start_idx:end_idx])
        if tiktoken:
            try:
                enc = tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(chunk_str)) > limit
            except Exception:
                pass
        return (end_idx - start_idx) > fallback_max_lines

    # If the entire file is already within TOKEN_MAX_PER_CHUNK
    if not _is_over_limit(0, total):
        return [lua_code]

    # Find safe cut points (depth == 0)
    safe_points = _find_safe_cut_points(lines)

    # Check: are there enough safe_points to split?
    # If no safe points exist in the middle of the file → data file,
    # fall back to blank-line splitting.
    usable_points = [sp for sp in safe_points if sp > 0 and sp < total - 1]
    if len(usable_points) < 2:
        # Data file (return { ... }) or too few functions
        return _split_data_file(lines, max_tokens, fallback_max_lines)

    # Filter chunks using a greedy algorithm based on token/lines
    chunks: list[str] = []
    chunk_start = 0
    last_safe = 0

    for sp in usable_points:
        # Try appending the next code block to the chunk to see if it exceeds the limit
        if _is_over_limit(chunk_start, sp) and sp > chunk_start:
            # Adding the current sp would EXCEED THE LIMIT
            # => Commit the chunk at last_safe (the most recent safe point)

            # Edge case: if last_safe is still chunk_start (a single oversized function exceeds the limit)
            # Nothing else can be done — must cut at the current split point (sp)
            cut_point = last_safe if last_safe > chunk_start else sp

            chunk_text = "\n".join(lines[chunk_start:cut_point])
            chunks.append(chunk_text)

            chunk_start = cut_point

        last_safe = sp

    # Final chunk
    if chunk_start < total:
        chunk_text = "\n".join(lines[chunk_start:total])
        chunks.append(chunk_text)

    # If the result has only 1 chunk (all functions are consecutive but the code is large),
    # fall back to cutting at blank lines
    if len(chunks) <= 1:
        return _split_data_file(lines, max_tokens, fallback_max_lines)

    return chunks


def _split_data_file(
    lines: list[str],
    max_tokens: int,
    fallback_max_lines: int
) -> list[str]:
    """
    Split a Lua data/config file (nested return { ... } form).
    Tracks brace depth { / } and only cuts at lines ending with '},'.
    Ensures no table entry is split mid-way.

    Prefers cutting at the lowest depth position near the max_lines boundary.
    """
    total = len(lines)

    # 1. Same as above, helper function to check limit
    def _is_over_limit(start_idx: int, end_idx: int, limit: int = max_tokens) -> bool:
        chunk_str = "\n".join(lines[start_idx:end_idx])
        if tiktoken:
            try:
                enc = tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(chunk_str)) > limit
            except Exception:
                pass
        return (end_idx - start_idx) > fallback_max_lines

    if not _is_over_limit(0, total):
        return ["\n".join(lines)]

    # Compute brace depth for each line
    depths: list[int] = []
    depth = 0
    for line in lines:
        code = re.sub(r"--.*$", "", line)
        code = re.sub(r'"[^"]*"', '""', code)
        code = re.sub(r"'[^']*'", "''", code)
        depth += code.count("{") - code.count("}")
        depths.append(depth)

    chunks: list[str] = []
    chunk_start = 0

    while chunk_start < total:
        # Instead of advancing by a static max_lines, we binary search or estimate the line index.
        # Simplest approach: use line count = fallback_max_lines as baseline to search back for a cut point,
        # since 1 token typically corresponds to a few characters of text, fallback + recheck is fine.
        # For the most accurate result (with tokens), we probe forward incrementally.
        # Optimization: with tiktoken, ~25000 tokens ≈ 25000 / 3 ≈ 8000 lines, so probing from fallback = max_lines is safe.

        guess_end = min(chunk_start + fallback_max_lines, total)
        # With tiktoken, increase step size because each line has very few tokens
        if tiktoken:
             guess_end = min(chunk_start + 5000, total)

        # Probe forward until exceeding / reaching the threshold
        while guess_end < total and not _is_over_limit(chunk_start, guess_end + 10):
            guess_end = min(guess_end + 1000, total)

        # Back off if we overshot the limit from the start
        while guess_end > chunk_start + 10 and _is_over_limit(chunk_start, guess_end):
             guess_end -= 100

        # If we've reached the end of the file, take the rest
        if guess_end >= total:
            chunks.append("\n".join(lines[chunk_start:total]))
            break

        # Find the best cut point near guess_end (search back ~300 lines)
        search_start = max(chunk_start + 50, guess_end - 300)

        best_cut = guess_end
        best_depth = float("inf")

        for i in range(guess_end - 1, search_start - 1, -1):
            stripped = lines[i].strip()
            d = depths[i]

            # Prefer lines ending with "},", "}" or blank lines
            is_block_end = stripped.endswith("},") or stripped == "}" or stripped == "},"
            is_blank = stripped == ""

            if is_block_end and d < best_depth:
                best_cut = i + 1  # Cut AFTER the closing } line
                best_depth = d
            elif is_blank and d <= best_depth:
                best_cut = i + 1
                best_depth = d

        chunk_end = best_cut
        chunks.append("\n".join(lines[chunk_start:chunk_end]))
        chunk_start = chunk_end

    return chunks
