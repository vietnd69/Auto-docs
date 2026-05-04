"""
Trích xuất nội dung function/property từ file Lua dựa trên danh sách tham chiếu.
Chỉ lấy đúng các function và property được yêu cầu, không lấy cả file.
"""

import re
import os
import hashlib
import json
import time
from pathlib import Path

from llm.client import ollama_chat, COMPRESSION_MODEL
from llm.paths import BASE_LUA_DIR, COMPRESSION_CACHE_DIR, PROJECT_ROOT
from llm.settings import BAD_RESPONSE_RETRIES, DEBUG_PROMPTS
from llm.tokens import count_tokens, STUB_FULL_THRESHOLD
from rag.docs import extract_lua_references, format_connected_section, clean_model_output

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _dump_debug(label: str, content: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = _DEBUG_DIR / f"{label}_{int(time.time())}.txt"
    path.write_text(content, encoding="utf-8")
    print(f"  [debug] {label} → {path.name}")


def _resolve_lua_path(ref_path: str) -> str | None:
    """
    Chuyển đường dẫn tham chiếu (vd: ./components/health.lua)
    thành đường dẫn thực trên ổ đĩa (vd: ./dst-scripts/components/health.lua).
    Trả về None nếu file không tồn tại.
    """
    # ref_path dạng "./components/health.lua" hoặc "./util/sourcemodifierlist.lua"
    # Bỏ "./" ở đầu rồi ghép với BASE_LUA_DIR
    clean = ref_path.lstrip("./")
    full_path = os.path.join(BASE_LUA_DIR, clean)
    if os.path.isfile(full_path):
        return full_path
    return None


def _extract_class_name(lua_code: str) -> str | None:
    """
    Tìm tên class chính trong file Lua.
    Pattern: local ClassName = Class(function(self, inst) ...)
    Trả về tên class (vd: "Health", "Combat") hoặc None.
    """
    match = re.search(r'local\s+(\w+)\s*=\s*Class\(', lua_code)
    return match.group(1) if match else None


def _extract_function_body(lua_code: str, class_name: str, func_name: str) -> str | None:
    """
    Trích xuất nội dung một function từ file Lua.
    Tìm pattern: function ClassName:FuncName(...)  ...  end
    Trả về toàn bộ nội dung function (bao gồm dòng khai báo và end).
    """
    # Escape tên để dùng trong regex
    escaped_class = re.escape(class_name)
    escaped_func = re.escape(func_name)

    # Pattern: function Health:DoDelta(params)
    pattern = rf'^(function\s+{escaped_class}[.:]{escaped_func}\s*\(.*?\))'

    lines = lua_code.split('\n')
    start_idx = None

    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            start_idx = i
            break

    if start_idx is None:
        return None

    # Đếm cặp block (function/if/for/while/do ... end) để tìm end tương ứng
    depth = 0
    end_idx = start_idx

    # Keywords mở block trong Lua
    block_openers = re.compile(
        r'\b(?:function|if|for|while|repeat)\b'
    )
    block_closers = re.compile(r'\bend\b')

    for i in range(start_idx, len(lines)):
        line = lines[i]

        # Bỏ qua comment (-- ...)
        code_part = re.sub(r'--.*$', '', line)
        # Bỏ qua string literals đơn giản
        code_part = re.sub(r'"[^"]*"', '""', code_part)
        code_part = re.sub(r"'[^']*'", "''", code_part)

        # Đếm openers và closers
        depth += len(block_openers.findall(code_part))
        depth -= len(block_closers.findall(code_part))

        if depth <= 0:
            end_idx = i
            break

    return '\n'.join(lines[start_idx:end_idx + 1])


def _extract_property_info(lua_code: str, prop_name: str) -> str | None:
    """
    Tìm property trong constructor hoặc khai báo biến.
    Pattern: self.propName = value
    Trả về dòng chứa property hoặc None.
    """
    pattern = rf'^\s*self\.{re.escape(prop_name)}\s*='

    for line in lua_code.split('\n'):
        if re.match(pattern, line.strip()):
            return line.strip()

    return None


def _truncate_sections_to_budget(
    sections: list[str],
    refs: list,
    max_tokens: int,
    truncation_label: str = "",
) -> tuple[list[str], list]:
    """
    Trim sections/refs to fit within max_tokens.
    Counts tokens per section incrementally (O(n)) instead of rebuilding the
    full candidate string on every iteration (O(n²)).
    """
    kept_sections: list[str] = []
    kept_refs: list = []
    running_tokens = 0

    for section, ref in zip(sections, refs):
        section_tokens = count_tokens(section)
        if section_tokens == -1:
            section_tokens = len(section) // 4
        running_tokens += section_tokens
        if running_tokens > max_tokens:
            if truncation_label:
                print(
                    f"  {truncation_label} Truncated: giữ {len(kept_sections)}/{len(sections)} refs "
                    f"để fit trong {max_tokens} tokens"
                )
            break
        kept_sections.append(section)
        kept_refs.append(ref)

    return kept_sections, kept_refs


def _compression_cache_key(full_content: str) -> str:
    """Content-addressed key: MD5 của full_content."""
    return hashlib.md5(full_content.encode("utf-8")).hexdigest()


def _load_compression_cache(cache_key: str) -> str | None:
    """
    Load compressed result từ cache nếu tồn tại.
    Trả về None nếu cache miss.
    """
    cache_path = Path(COMPRESSION_CACHE_DIR) / f"{cache_key}.json"
    try:
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  [COMPRESS CACHE] Hit: {cache_key[:8]}...")
        return data.get("compressed")
    except Exception:
        return None


def _save_compression_cache(cache_key: str, compressed: str) -> None:
    """
    Lưu compressed result vào cache (atomic write).
    Không bao giờ tự xóa — cache tồn tại vĩnh viễn cho đến khi source thay đổi.
    """
    cache_dir = Path(COMPRESSION_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.json"
    temp_path = cache_dir / f"{cache_key}.json.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump({"compressed": compressed}, f, ensure_ascii=False)
        temp_path.replace(cache_path)
        print(f"  [COMPRESS CACHE] Saved: {cache_key[:8]}...")
    except Exception as e:
        print(f"  [COMPRESS CACHE] Không lưu được: {e}")


def _extract_compact_signature(lua_code: str, class_name: str, func_name: str) -> str | None:
    """
    Static extraction: sig + return values + error conditions.
    Không cần LLM. Output cố định 1–3 dòng/function.
    """
    body = _extract_function_body(lua_code, class_name, func_name)
    if not body:
        return None

    lines = body.split("\n")
    sig_line = lines[0].strip()

    returns = []
    errors = []
    for idx, line in enumerate(lines[1:], 1):
        stripped = line.strip()
        # return có giá trị thực (bỏ qua "return self" và return đơn thuần)
        if re.match(r'^return\s+\S+', stripped):
            val = stripped[len("return "):].strip().rstrip(",")
            if val not in ("self", "true", "false", "nil", ""):
                returns.append(val[:60])
        # error states: if <cond> then \n return nil/false
        if re.match(r'^if\s+.+\s+then\s*$', stripped):
            lookahead = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            if lookahead.startswith("return nil") or lookahead.startswith("return false"):
                condition = stripped[3:-5].strip()
                errors.append(f"{condition} → {lookahead}")

    parts = [f"-- COMPACT: {sig_line}"]
    if returns:
        parts.append(f"-- returns: {', '.join(dict.fromkeys(returns))}")
    if errors:
        parts.append(f"-- errors: {' | '.join(dict.fromkeys(errors))}")

    return "\n".join(parts)


def extract_compact_content(
    lua_refs: list[tuple[str, list[str]]],
    max_output_tokens: int = 0,
) -> tuple[str, list[tuple[str, list[str]]]]:
    """
    Trích xuất COMPACT summaries (static, không cần LLM) cho tất cả refs.
    Dùng làm fallback khi LLM compression thất bại.

    Returns:
        (content, kept_refs) — tương tự extract_signatures_only().
    """
    sections = []
    resolved_refs = []

    for ref_path, func_names in lua_refs:
        if not func_names:
            continue
        real_path = _resolve_lua_path(ref_path)
        if real_path is None:
            continue
        try:
            with open(real_path, encoding="utf-8", errors="ignore") as f:
                lua_code = f.read()
        except Exception:
            continue

        class_name = _extract_class_name(lua_code)
        if class_name is None:
            continue

        compacts = []
        for func_name in func_names:
            compact = _extract_compact_signature(lua_code, class_name, func_name)
            if compact:
                compacts.append(compact)

        if compacts:
            header = f"--- FILE: {ref_path} (class: {class_name}) ---"
            sections.append(header + "\n" + "\n".join(compacts))
            resolved_refs.append((ref_path, func_names))

    if not sections:
        return "", []

    if max_output_tokens > 0:
        sections, resolved_refs = _truncate_sections_to_budget(
            sections, resolved_refs, max_output_tokens
        )

    return "\n\n".join(sections), resolved_refs


def extract_signatures_only(
    lua_refs: list[tuple[str, list[str]]],
    max_output_tokens: int = 0,   # 0 = không giới hạn
) -> tuple[str, list[tuple[str, list[str]]]]:
    """
    Fallback mode: chỉ lấy dòng khai báo function (signature), không lấy body.

    Nếu max_output_tokens > 0 và output vượt ngưỡng, refs cuối danh sách sẽ bị
    bỏ qua (truncate by ref, không truncate giữa chừng một ref).

    Returns:
        (content, kept_refs)
        content:    chuỗi signatures; empty string nếu không tìm được gì.
        kept_refs:  list các ref tuple thực sự xuất hiện trong output.
    """
    sections = []
    resolved_refs = []   # track refs đã resolve được ít nhất 1 sig

    for ref_path, func_names in lua_refs:
        if not func_names:
            continue
        real_path = _resolve_lua_path(ref_path)
        if real_path is None:
            continue

        try:
            with open(real_path, "r", encoding="utf-8", errors="ignore") as f:
                lua_code = f.read()
        except Exception:
            continue

        class_name = _extract_class_name(lua_code)
        if class_name is None:
            continue

        sigs = []
        for func_name in func_names:
            escaped_class = re.escape(class_name)
            escaped_func  = re.escape(func_name)
            pattern = rf'^function\s+{escaped_class}[.:]{escaped_func}\s*\(.*?\)'
            for line in lua_code.split("\n"):
                if re.match(pattern, line.strip()):
                    sigs.append(f"--[SIGONLY: {line.strip()}]")
                    break

        if sigs:
            header = f"--- FILE: {ref_path} (class: {class_name}) ---"
            sections.append(header + "\n" + "\n".join(sigs))
            resolved_refs.append((ref_path, func_names))

    if not sections:
        return "", []

    if max_output_tokens > 0:
        sections, resolved_refs = _truncate_sections_to_budget(
            sections, resolved_refs, max_output_tokens, truncation_label="[SIG]"
        )

    if not sections:
        return "", []

    return "\n\n".join(sections), resolved_refs


def compress_connected_content(
    full_content: str,
    max_output_tokens: int = 3500,
    model_name: str | None = None,
) -> str | None:
    """
    Dùng LLM để rút gọn full function bodies xuống 3–5 dòng/function.
    Giữ lại: signature, return values, error conditions, side effects quan trọng.

    Args:
        full_content: Output của extract_connected_content() — full function bodies.
        max_output_tokens: Giới hạn token cho output compressed.
        model_name: Model name. None = dùng COMPRESSION_MODEL.

    Returns:
        Compressed string nếu thành công và nằm trong budget.
        None nếu LLM call thất bại.
    """
    _model = model_name or COMPRESSION_MODEL

    # Cache lookup trước khi gọi LLM
    cache_key = _compression_cache_key(full_content)
    cached = _load_compression_cache(cache_key)
    if cached is not None:
        return cached

    prompt = f"""You are compressing Lua function documentation for use as context in a larger prompt.
For each function below, output a 3–5 line summary. Be terse and precise.

OUTPUT FORMAT (repeat for each function):
-- COMPRESSED: ClassName:FuncName(params)
-- returns: <return values or nil/false on failure>
-- errors: <condition → return value> (omit line if no early returns)
-- notes: <side effects, events fired, tags added> (omit line if none)

RULES:
- Keep the --- FILE: ... --- headers between files.
- Never invent behavior not present in the source.
- Output only the compressed summaries, no preamble or sign-off.
- Target: under {max_output_tokens} tokens total output.

SOURCE:
{full_content}"""

    if DEBUG_PROMPTS:
        _dump_debug("compress_prompt", prompt)
    messages = [{"role": "user", "content": prompt}]
    for attempt in range(1, BAD_RESPONSE_RETRIES + 2):
        try:
            response = ollama_chat(model=_model, messages=messages)
        except Exception as e:
            remaining = BAD_RESPONSE_RETRIES + 1 - attempt
            if remaining > 0:
                print(f"  [COMPRESS] LLM call thất bại: {e} → retry ({remaining} left)")
                continue
            print(f"  [COMPRESS] LLM call thất bại sau {attempt} lần: {e}")
            return None

        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_debug(f"compress_response_attempt{attempt}", raw)
        result = clean_model_output(raw)
        if not result:
            remaining = BAD_RESPONSE_RETRIES + 1 - attempt
            if remaining > 0:
                print(f"  [COMPRESS] Model trả về rỗng → retry ({remaining} left)")
                continue
            print("  [COMPRESS] Model trả về rỗng sau nhiều lần thử")
            return None

        if "-- COMPRESSED:" not in result:
            remaining = BAD_RESPONSE_RETRIES + 1 - attempt
            if remaining > 0:
                print(f"  [COMPRESS] Output không đúng format → retry ({remaining} left)")
                continue
            print("  [COMPRESS] Output không đúng format sau nhiều lần thử, fallback về signatures")
            return None

        _save_compression_cache(cache_key, result)
        return result

    return None


def _compress_module_stub(lua_code: str, ref_path: str) -> str | None:
    """
    Dùng LLM để tạo module-level summary (3–5 dòng) cho require-only refs.
    Reuses compression cache system.

    Returns:
        Formatted stub string nếu thành công (contains "-- [REQUIRE MODULE: ...]").
        None nếu LLM thất bại hoặc output không hợp lệ.
    """
    cache_key = _compression_cache_key(lua_code)
    cached = _load_compression_cache(cache_key)
    if cached is not None:
        return cached

    prompt = f"""Summarize this Lua module in 3–5 lines. Output format:
-- MODULE: <ClassName or module name>
-- exports: <key functions/constants, comma-separated>
-- purpose: <one sentence: what this module does>
-- notes: <side effects, globals registered> (omit if none)

Rules: Never invent. Output only the summary, no preamble.
SOURCE:
{lua_code}"""

    if DEBUG_PROMPTS:
        _dump_debug(f"stub_prompt_{Path(ref_path).stem}", prompt)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            response = ollama_chat(
                model=COMPRESSION_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response["message"]["content"]
            if DEBUG_PROMPTS:
                _dump_debug(f"stub_response_{Path(ref_path).stem}_attempt{attempt}", raw)
            raw = clean_model_output(raw)
        except Exception as e:
            print(f"  [STUB] LLM call failed for {ref_path}: {e}")
            return None

        if "-- MODULE:" in raw:
            result = f"-- [REQUIRE MODULE: {ref_path}] ---\n{raw}"
            _save_compression_cache(cache_key, result)
            return result

        if attempt < max_retries:
            print(f"  [STUB] Output missing -- MODULE: marker, retrying {ref_path} ({attempt}/{max_retries})")
            time.sleep(2)
        else:
            print(f"  [STUB] Output missing -- MODULE: marker after {max_retries} attempts, skipping {ref_path}")

    return None


def extract_require_stubs(
    req_refs: list[tuple[str, list[str]]],
    max_tokens: int = 0,
) -> str:
    """
    Trích xuất stub content cho require-only refs (func_names rỗng).

    - File nhỏ (≤ STUB_FULL_THRESHOLD tokens): include toàn bộ nội dung.
    - File lớn: dùng LLM tạo module summary 3–5 dòng.

    Budget được kiểm tra incrementally — dừng khi tổng vượt max_tokens.

    Returns:
        str: nội dung ghép, prefix bởi marker "-- [REQUIRE FULL:" hoặc "-- [REQUIRE MODULE:".
             Trả về "" nếu không có gì.
    """
    if not req_refs or max_tokens <= 0:
        return ""

    sections: list[str] = []
    running_tokens = 0
    total = len(req_refs)

    for idx, (ref_path, _) in enumerate(req_refs):
        real_path = _resolve_lua_path(ref_path)
        if real_path is None:
            continue

        try:
            with open(real_path, encoding="utf-8", errors="ignore") as f:
                lua_code = f.read()
        except Exception:
            continue

        file_tokens = count_tokens(lua_code)
        if file_tokens == -1:
            file_tokens = len(lua_code) // 4

        if file_tokens <= STUB_FULL_THRESHOLD:
            section = f"-- [REQUIRE FULL: {ref_path}] ---\n{lua_code}"
        else:
            section = _compress_module_stub(lua_code, ref_path)
            if section is None:
                continue

        section_tokens = count_tokens(section)
        if section_tokens == -1:
            section_tokens = len(section) // 4

        if running_tokens + section_tokens > max_tokens:
            print(
                f"  [CTX] Require-stub budget exhausted after {len(sections)}/{total} refs"
            )
            break

        sections.append(section)
        running_tokens += section_tokens

    return "\n\n".join(sections)


def extract_connected_content(
    lua_refs: list[tuple[str, list[str]]],
    max_lines_per_file: int = 100,
    max_total_tokens: int = 0,    # 0 = không giới hạn
) -> str:
    """
    Trích xuất nội dung function/property từ danh sách tham chiếu.

    Args:
        lua_refs: Danh sách [(file_path, [func_names]), ...] từ extract_lua_references()
        max_lines_per_file: Giới hạn số dòng tối đa cho mỗi file liên quan

    Returns:
        Chuỗi formatted chứa nội dung các function liên quan, hoặc "" nếu không có gì.
    """
    if not lua_refs:
        return ""

    sections = []

    for ref_path, func_names in lua_refs:
        # Bỏ qua nếu không có function cụ thể cần trích xuất
        if not func_names:
            continue

        real_path = _resolve_lua_path(ref_path)
        if real_path is None:
            continue

        try:
            with open(real_path, "r", encoding="utf-8", errors="ignore") as f:
                lua_code = f.read()
        except Exception:
            continue

        class_name = _extract_class_name(lua_code)
        if class_name is None:
            continue

        extracted_items = []
        total_lines = 0

        for func_name in func_names:
            if total_lines >= max_lines_per_file:
                break

            # Thử tìm function trước
            body = _extract_function_body(lua_code, class_name, func_name)
            if body:
                body_lines = body.count('\n') + 1
                if total_lines + body_lines <= max_lines_per_file:
                    extracted_items.append(body)
                    total_lines += body_lines
                continue

            # Nếu không phải function, thử tìm property
            prop = _extract_property_info(lua_code, func_name)
            if prop:
                extracted_items.append(f"-- [property] {prop}")
                total_lines += 1

        if extracted_items:
            header = f"--- FILE: {ref_path} (class: {class_name}) ---"
            content = '\n\n'.join(extracted_items)
            sections.append(f"{header}\n{content}")

    if not sections:
        return ""

    full_result = "\n\n".join(sections)

    # Kiểm tra token budget nếu có giới hạn
    if max_total_tokens > 0:
        total_tokens = count_tokens(full_result)

        if total_tokens == -1:
            # Fallback khi tiktoken không có: ước tính bằng char count (1 token ≈ 4 chars)
            total_tokens = len(full_result) // 4

        if total_tokens > max_total_tokens:
            print(
                f"  [CONTEXT] Full content ~{total_tokens} tokens "
                f"> ngưỡng {max_total_tokens} → LLM compression"
            )
            compressed = compress_connected_content(
                full_result,
                max_output_tokens=max_total_tokens,
            )
            if compressed is not None:
                compressed_tokens = count_tokens(compressed)
                if compressed_tokens == -1:
                    compressed_tokens = len(compressed) // 4
                if compressed_tokens <= max_total_tokens:
                    print(
                        f"  [CONTEXT] Compressed: {total_tokens} → {compressed_tokens} tokens "
                        f"({100 - compressed_tokens * 100 // total_tokens}% reduction)"
                    )
                    return compressed
                print(f"  [CONTEXT] Compressed vẫn > ngưỡng → COMPACT fallback")
            else:
                print(f"  [CONTEXT] LLM thất bại → COMPACT fallback")

            # Fallback 1: COMPACT static extraction (sig + returns + errors, không cần LLM)
            compact_content, _ = extract_compact_content(
                lua_refs, max_output_tokens=max_total_tokens
            )
            if compact_content:
                compact_tokens = count_tokens(compact_content)
                if compact_tokens == -1:
                    compact_tokens = len(compact_content) // 4
                if compact_tokens <= max_total_tokens:
                    print(f"  [CONTEXT] COMPACT: {compact_tokens} tokens")
                    return compact_content

            # Fallback 2: signature-only (last resort)
            print(f"  [CONTEXT] Fallback → signature-only mode")
            sig_content, _ = extract_signatures_only(lua_refs, max_output_tokens=max_total_tokens)
            return sig_content

    return full_result


def extract_connected_for_chunk(
    chunk_code: str,
    own_filename: str,
    full_refs: list[tuple[str, list[str]]] | None = None,
    max_lines_per_file: int = 100,
    max_total_tokens: int = 8000,
) -> tuple[str, str, int]:
    """
    Trích xuất connected_section + connected_content + ref_count cho 1 chunk cụ thể.

    Smart fallback (khi chunk_refs rỗng):
        Chỉ kích hoạt cho 2 trường hợp biên:
        - Cross-chunk require: require() ở chunk trước, chunk này dùng module nhưng không re-import.
        - self.components.X: bị negative lookbehind của extract_lua_references bỏ qua.

    Known limitation:
        Require-based cross-chunk KHÔNG bị bắt bởi filter `components.<name>`.
        Chunk đó nhận ("", "", 0) — graceful degrade.

    Returns:
        (connected_section, connected_content, ref_count)
    """
    chunk_refs = extract_lua_references(chunk_code, own_filename)

    # Fallback: chunk không có ref cục bộ nhưng full file có refs.
    if not chunk_refs and full_refs:
        # Filter full_refs xuống chỉ còn refs mà chunk thực sự reference
        filtered_refs = [
            (ref_path, funcs)
            for ref_path, funcs in full_refs
            if re.search(
                rf'\bcomponents\.{re.escape(ref_path.split("/")[-1].replace(".lua", ""))}',
                chunk_code,
            )
        ]

        if not filtered_refs:
            return "", "", 0

        print(f"    [CTX] Chunk không có local refs nhưng có external call → fallback signatures từ filtered_refs ({len(filtered_refs)} refs)")
        fallback_content, fallback_kept_refs = extract_signatures_only(filtered_refs, max_output_tokens=max_total_tokens)

        if not fallback_content:
            return "", "", 0

        fallback_section = format_connected_section(fallback_kept_refs)
        return fallback_section, fallback_content, len(fallback_kept_refs)

    # Tách func_refs (có function calls) và req_refs (require-only)
    func_refs = [(path, funcs) for path, funcs in chunk_refs if funcs]
    req_refs  = [(path, funcs) for path, funcs in chunk_refs if not funcs]

    # Pipeline cũ: func_refs với full budget
    func_content = extract_connected_content(
        func_refs,
        max_lines_per_file=max_lines_per_file,
        max_total_tokens=max_total_tokens,
    )

    # Pipeline mới: require-only stubs với budget còn lại
    func_tokens = count_tokens(func_content)
    if func_tokens == -1:
        func_tokens = len(func_content) // 4
    remaining_budget = max_total_tokens - func_tokens
    req_content = extract_require_stubs(req_refs, max_tokens=remaining_budget)

    # Ghép kết quả
    if func_content and req_content:
        connected_content = func_content + "\n\n" + req_content
    elif req_content:
        connected_content = req_content
    else:
        connected_content = func_content

    if not connected_content:
        return "", "", len(func_refs)

    # Rebuild section từ kept_refs thực tế (chỉ func_refs — req_refs không có func_names)
    if "--[SIGONLY:" in func_content:
        _, kept_refs = extract_signatures_only(func_refs, max_output_tokens=max_total_tokens)
    else:
        kept_refs = func_refs

    connected_section = format_connected_section(kept_refs)
    return connected_section, connected_content, len(kept_refs)


# === Cho phép chạy độc lập để test ===
if __name__ == "__main__":
    # Test nhanh với một vài ref giả
    test_refs = [
        ("./components/health.lua", ["DoDelta", "GetPercent", "IsDead", "IsInvincible", "minhealth"]),
        ("./components/weapon.lua", ["GetDamage", "CanRangedAttack", "LaunchProjectile", "OnAttack"]),
        ("./components/inventory.lua", ["ApplyDamage", "GetEquippedItem"]),
    ]

    result = extract_connected_content(test_refs)

    if result:
        print("=== KẾT QUẢ TRÍCH XUẤT ===")
        print(result)
        print(f"\n=== Tổng: {result.count(chr(10)) + 1} dòng ===")
    else:
        print("Không trích xuất được gì!")
