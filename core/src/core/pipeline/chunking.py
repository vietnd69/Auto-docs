"""
Module xử lý file Lua dài — chia thành chunks và xử lý từng phần.
Chứa logic:
  - needs_chunking():        kiểm tra file có cần chunking không
  - split_lua_into_chunks():  chia Lua code tại ranh giới function
  - process_chunked_file():   pipeline chính: split → chunk prompts → merge
"""

import re

try:
    import tiktoken
except ImportError:
    tiktoken = None

from llm.tokens import count_tokens
from prompts.chunked import build_chunk_prompt   # used in calc_token_budget

# ── Ngưỡng và cấu hình ──────────────────────────────────────────

CHUNK_THRESHOLD = 3000       # Ngưỡng dòng fallback nếu không có tiktoken
CHUNK_MAX_LINES = 1500       # Mỗi chunk tối đa ~1500 dòng (fallback)

# Ngưỡng token cho TOÀN BỘ PROMPT (bao gồm system instruction + context + code)
PROMPT_TOKEN_LIMIT = 16000   # Nếu full prompt > 16K token thì phải chunk

# Ngưỡng token cho MERGE (tổng chunk results)
MERGE_TOKEN_LIMIT = 20000

# Token reserve dành cho per-chunk connected context (signatures hoặc full bodies).
# calc_token_budget() sẽ tự trừ khoản này khỏi code budget.
# CALIBRATION: Full bodies 3–5 refs ~2000–3000 tokens; signatures 30 refs ~1500 tokens.
CONTEXT_RESERVE = 7000    # Nếu tổng chunk results > ngưỡng này → dùng hierarchical


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
    Tính số token còn lại dành cho nội dung Lua code trong mỗi chunk.

    Cách tính:
      1. Build prompt "vỏ" (shell) = chunk prompt với code rỗng
      2. Đếm token của shell
      3. Trả về: prompt_token_limit - shell_tokens

    Returns:
        Số token tối đa cho code Lua trong mỗi chunk.
        Nếu không có tiktoken, trả về fallback dựa trên CHUNK_MAX_LINES.
    """
    # Warning: nếu connected_content non-empty, CONTEXT_RESERVE sẽ bị trừ 2 lần.
    if connected_content:
        print(
            "[WARN] calc_token_budget() nhận connected_content non-empty. "
            "Trong chunked pipeline phải truyền connected_content='' vì CONTEXT_RESERVE "
            "đã được trừ nội bộ. Double-deduction có thể xảy ra."
        )

    # Build prompt shell = chunk prompt KHÔNG CÓ code (code rỗng)
    shell = build_chunk_prompt(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        chunk_code="",  # Code rỗng để đo vỏ
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

    # Guard tiktoken missing: count_tokens() trả về -1
    if shell_tokens < 0:
        print(
            f"  [TOKEN BUDGET] tiktoken missing — dùng fallback budget "
            f"(CONTEXT_RESERVE không được áp dụng trong fallback mode)"
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
            f"  [WARN] Code budget chỉ còn {effective_budget} tokens — "
            f"file_tree có thể quá lớn hoặc shell quá nặng. "
            f"Xem xét giảm max_depth của get_shared_file_tree()."
        )
    return effective_budget

def strip_bulk_data(lua_code: str) -> str:
    """
    Loại bỏ dữ liệu số hàng loạt (tile data, map data) khỏi source Lua.
    Thay thế mảng số dài bằng comment tóm tắt.

    Ví dụ:
        data = {
            0, 0, 0, 0, 0, 0, ...  (hàng trăm dòng)
        }
    →   data = { --[[ 360000 numeric values (tile data) ]] }

    Điều này giảm file 1.1MB xuống ~80KB mà không mất thông tin cấu trúc.
    """
    lines = lua_code.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Phát hiện bắt đầu block data: "data = {" hoặc tương tự
        if re.match(r"^\s*\w+\s*=\s*\{\s*$", stripped):
            # Kiểm tra xem các dòng tiếp theo có phải toàn số không
            j = i + 1
            num_count = 0
            data_lines = 0

            while j < len(lines):
                next_stripped = lines[j].strip()

                # Dòng đóng }
                if next_stripped in ("}", "},"):
                    break

                # Dòng chỉ chứa số, phẩy, khoảng trắng
                clean = next_stripped.rstrip(",")
                if clean and all(c in "0123456789, " for c in clean):
                    # Đếm số lượng giá trị
                    nums = [x.strip() for x in clean.split(",") if x.strip()]
                    num_count += len(nums)
                    data_lines += 1
                else:
                    break
                j += 1

            # Nếu có >= 10 dòng data số → strip
            if data_lines >= 10 and j < len(lines):
                # Lấy tên field (vd: "data")
                field_match = re.match(r"^(\s*\w+\s*=\s*)\{", stripped)
                indent = re.match(r"^(\s*)", line).group(1)
                field = field_match.group(1) if field_match else ""
                result.append(
                    f"{indent}{field}{{--[[ {num_count} numeric values (tile/map data) ]]}}"
                )
                # Skip đến dòng đóng } (bao gồm)
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
    Kiểm tra xem text (full prompt hoặc lua code) có vượt ngưỡng token không.

    Khuyên dùng: truyền full prompt text (từ build_prompt) để đo chính xác nhất.
    Nếu truyền lua_code thô thì fallback về đếm dòng.

    Returns:
        True nếu cần chunking (text quá dài).
    """
    token_count = count_tokens(text)
    if token_count >= 0:
        return token_count > token_limit

    return text.count("\n") + 1 > CHUNK_THRESHOLD


def _find_safe_cut_points(lines: list[str]) -> list[int]:
    """
    Quét toàn bộ file Lua, theo dõi block depth (function/if/for/while/repeat ↔ end).
    Trả về danh sách các line index (0-based) mà tại đó depth == 0 — đây là
    những điểm an toàn để cắt chunk mà KHÔNG bao giờ cắt giữa function body.

    Chỉ đánh dấu safe tại dòng trống hoặc dòng bắt đầu function/local function
    ở depth 0 để chunk bắt đầu gọn gàng.
    """
    block_open = re.compile(r"\b(?:function|if|for|while|repeat)\b")
    block_close = re.compile(r"\bend\b")

    depth = 0
    safe_points: list[int] = []

    for i, line in enumerate(lines):
        # Bỏ comment và string literals trước khi đếm keyword
        code = re.sub(r"--.*$", "", line)
        code = re.sub(r'"[^"]*"', '""', code)
        code = re.sub(r"'[^']*'", "''", code)

        depth += len(block_open.findall(code))
        depth -= len(block_close.findall(code))

        # Depth == 0 → nằm ngoài mọi block
        if depth == 0:
            stripped = line.strip()
            # Đánh dấu safe tại: dòng trống, hoặc dòng bắt đầu function
            if stripped == "" or re.match(r"^(local\s+)?function\s+", stripped):
                safe_points.append(i)

    return safe_points


def split_lua_into_chunks(
    lua_code: str,
    max_tokens: int = -1,
    fallback_max_lines: int = CHUNK_MAX_LINES
) -> list[str]:
    """
    Chia source Lua thành các chunk, ĐẢM BẢO không cắt giữa function body.
    Cố gắng gói tối đa code vào mỗi chunk dựa trên giới hạn tokens.

    Chiến lược:
    - File có function (component): dùng depth-tracking, cắt tại depth==0
      → 100% không bao giờ cắt giữa function body.
    - File dạng data/config (wrapped trong return {}): depth không bao giờ
      về 0 → fallback cắt tại dòng trống (file data không có function nên OK).

    Returns:
        list[str] — danh sách các chunk.
    """
    lines = lua_code.split("\n")
    total = len(lines)

    # 1. Hàm helper để tính length/limit linh động
    def _is_over_limit(start_idx: int, end_idx: int, limit: int = max_tokens) -> bool:
        chunk_str = "\n".join(lines[start_idx:end_idx])
        if tiktoken:
            try:
                enc = tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(chunk_str)) > limit
            except Exception:
                pass
        return (end_idx - start_idx) > fallback_max_lines

    # Nếu toàn bộ file đã an toàn theo TOKEN_MAX_PER_CHUNK
    if not _is_over_limit(0, total):
        return [lua_code]

    # Tìm safe cut points (depth == 0)
    safe_points = _find_safe_cut_points(lines)

    # Kiểm tra: safe_points có đủ để split không?
    # Nếu không có safe point nào ở giữa file → file dạng data,
    # fallback sang blank-line splitting.
    usable_points = [sp for sp in safe_points if sp > 0 and sp < total - 1]
    if len(usable_points) < 2:
        # File dạng data (return { ... }) hoặc quá ít function
        return _split_data_file(lines, max_tokens, fallback_max_lines)

    # Lọc chunk bằng thuật toán greedy dựa trên token/dòng
    chunks: list[str] = []
    chunk_start = 0
    last_safe = 0

    for sp in usable_points:
        # Nhép thử thêm block code kế tiếp vào chunk xem có bị quá tải không
        if _is_over_limit(chunk_start, sp) and sp > chunk_start:
            # Nếu thêm sp hiện tại vào thì QUÁ GIỚI HẠN
            # => Chốt chunk tại last_safe (điểm an toàn liền trước)

            # Cạnh tranh biên: nếu last_safe vẫn là chunk_start (tức 1 function quá béo bự vượt limit)
            # Không thể làm gì khác, đành phải cắt đại tại split point hiện tại (sp)
            cut_point = last_safe if last_safe > chunk_start else sp

            chunk_text = "\n".join(lines[chunk_start:cut_point])
            chunks.append(chunk_text)

            chunk_start = cut_point

        last_safe = sp

    # Chunk cuối cùng
    if chunk_start < total:
        chunk_text = "\n".join(lines[chunk_start:total])
        chunks.append(chunk_text)

    # Nếu kết quả chỉ có 1 chunk (tất cả function nằm liền nhau nhưng code béo),
    # fallback cắt tại dòng trống
    if len(chunks) <= 1:
        return _split_data_file(lines, max_tokens, fallback_max_lines)

    return chunks


def _split_data_file(
    lines: list[str],
    max_tokens: int,
    fallback_max_lines: int
) -> list[str]:
    """
    Cắt file data/config Lua (dạng return { ... } lồng nhau).
    Theo dõi brace depth { / } và chỉ cắt tại dòng kết thúc bằng '},'.
    Đảm bảo mỗi table entry không bị cắt nửa chừng.

    Ưu tiên cắt tại vị trí depth thấp nhất gần ranh giới max_lines.
    """
    total = len(lines)

    # 1. Tương tự như trên, hàm helper check limit
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

    # Tính brace depth cho mỗi dòng
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
        # Thay vì tịnh tiến cộng thêm max_lines tĩnh, ta binary search hoặc đoán line index
        # Ở đây đơn giản nhất: ta dùng line count = fallback_max_lines làm baseline để lùi tìm điểm cắt,
        # vì 1 token thường ứng với linh tinh text, ta có thể dùng fallback + check lại.
        # Nhưng để chuẩn xác nhất (với token), ta tịnh tiến dò dần.
        # Tối ưu: Nếu có tiktoken, thường 25000 tokens ≈ 25000 / 3 ≈ 8000 line, nên dò từ fallback = max_lines sẽ an toàn.

        guess_end = min(chunk_start + fallback_max_lines, total)
        # Nếu có tiktoken, tăng nhịp độ lên nhiều dòng hơn vì 1 dòng rất ít token
        if tiktoken:
             guess_end = min(chunk_start + 5000, total)

        # Dò dần cho tới khi vượt / chạm ngưỡng
        while guess_end < total and not _is_over_limit(chunk_start, guess_end + 10):
            guess_end = min(guess_end + 1000, total)

        # Và lùi lại nếu ngay từ đầu bị trớt quá limit
        while guess_end > chunk_start + 10 and _is_over_limit(chunk_start, guess_end):
             guess_end -= 100

        # Nếu đã hết file, lấy hết
        if guess_end >= total:
            chunks.append("\n".join(lines[chunk_start:total]))
            break

        # Tìm điểm cắt tốt nhất gần guess_end (lùi lại khoảng 300 dòng)
        search_start = max(chunk_start + 50, guess_end - 300)

        best_cut = guess_end
        best_depth = float("inf")

        for i in range(guess_end - 1, search_start - 1, -1):
            stripped = lines[i].strip()
            d = depths[i]

            # Ưu tiên dòng kết thúc bằng "},", "}" hoặc dòng trống
            is_block_end = stripped.endswith("},") or stripped == "}" or stripped == "},"
            is_blank = stripped == ""

            if is_block_end and d < best_depth:
                best_cut = i + 1  # Cắt SAU dòng đóng }
                best_depth = d
            elif is_blank and d <= best_depth:
                best_cut = i + 1
                best_depth = d

        chunk_end = best_cut
        chunks.append("\n".join(lines[chunk_start:chunk_end]))
        chunk_start = chunk_end

    return chunks
