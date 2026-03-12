# Implementation Plan: LLM Compression cho Connected Context

> Thay thế signature-only fallback bằng LLM-compressed summaries

---

## Vấn đề hiện tại

```
[CONTEXT] Full content ~15247 tokens > ngưỡng 3500 → chuyển sang signature-only mode
[CTX] Chunk 2: 50 refs, mode=signatures
```

Khi full body vượt `CONTEXT_RESERVE`, toàn bộ function body bị bỏ — chỉ còn 1 dòng
signature không có return, không có error states. LLM chunk analysis mất context quan trọng.

---

## Giải pháp

Thêm **LLM compression step** giữa full body và signature-only fallback:

```
Full body extraction
       ↓ > CONTEXT_RESERVE
LLM compress → 3–5 dòng/function (sig + returns + errors)
       ↓ LLM fail hoặc format sai
COMPACT static extraction → sig + returns + errors (không cần LLM)
       ↓ vẫn > CONTEXT_RESERVE (hiếm — chỉ khi 50+ refs)
signature-only (last resort)
```

---

## Spec chi tiết

### Compression output format

```lua
-- Trước (full body ~20 dòng):
function Health:DoDelta(amount, overtime, cause, redirect)
    if self.invincible then return end
    if amount < 0 and self.absorb > 0 then
        amount = amount * (1 - self.absorb)
    end
    ...20 dòng...
end

-- Sau (compressed ~4 dòng):
-- COMPRESSED: Health:DoDelta(amount, overtime, cause, redirect)
-- returns: nil (early exit), currenthealth value
-- errors: self.invincible → return nil | amount == 0 → return false
-- notes: clamps health, fires "healthdelta" event
```

### COMPACT output format (static fallback)

```lua
-- COMPACT: Health:DoDelta(amount, overtime, cause, redirect)
-- returns: nil (early exit), currenthealth value
-- errors: self.invincible → return nil | amount == 0 → return false
```

Không cần LLM — parse trực tiếp từ AST đơn giản: dòng khai báo + `return` statements
+ `if ... then return nil/false` patterns. Mỗi function: **3 dòng cố định**.

---

## Files cần sửa

| File | Thay đổi |
|------|----------|
| `rag_get_fnc_content.py` | Thêm `_extract_compact_signature()` + `extract_compact_content()` + `compress_connected_content()` + cache helpers + sửa `extract_connected_content()` |
| `config.py` | Thêm `COMPRESSION_MODEL`, `COMPRESSION_CACHE_DIR` constants |

---

## Implementation

### 1. `config.py` — thêm constants

```python
# Thêm sau MODEL_NAME
COMPRESSION_MODEL = MODEL_NAME   # dùng cùng model, có thể override sang model nhỏ hơn
COMPRESSION_CACHE_DIR = str(PROJECT_ROOT / ".cache" / "compression_cache")
```

### 2. `rag_get_fnc_content.py` — thêm cache helpers

Cache dùng **content-addressed key** = MD5 của `full_content` — cùng tập refs +
cùng function bodies → cùng hash → hit cache, không gọi LLM lại.

Cache **không tự xóa** khác với chunked checkpoint (xóa sau khi merge xong).
Lý do: compressed result của `health.lua`, `combat.lua` vẫn có giá trị cho
mọi file khác reference chúng trong tương lai. Chỉ invalid khi source Lua thay đổi
(hash thay đổi → cache miss tự nhiên).

Thêm 3 functions này trước `compress_connected_content()`:

```python
import hashlib
import json
from pathlib import Path


def _compression_cache_key(full_content: str) -> str:
    """Content-addressed key: MD5 của full_content."""
    return hashlib.md5(full_content.encode("utf-8")).hexdigest()


def _load_compression_cache(cache_key: str) -> str | None:
    """
    Load compressed result từ cache nếu tồn tại.
    Trả về None nếu cache miss.
    """
    import config as _config
    cache_path = Path(_config.COMPRESSION_CACHE_DIR) / f"{cache_key}.json"
    if not cache_path.exists():
        return None
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
    import config as _config
    cache_dir = Path(_config.COMPRESSION_CACHE_DIR)
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
```

### 3. `rag_get_fnc_content.py` — thêm COMPACT static extraction

Thêm 2 functions này sau cache helpers, trước `compress_connected_content()`:

```python
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
        parts.append(f"-- returns: {', '.join(dict.fromkeys(returns))[:3]}")
    if errors:
        parts.append(f"-- errors: {' | '.join(dict.fromkeys(errors))[:3]}")

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

    # Truncation nếu có giới hạn token
    if max_output_tokens > 0:
        from chunked import count_tokens
        kept_sections, kept_refs = [], []
        for section, ref in zip(sections, resolved_refs):
            candidate = "\n\n".join(kept_sections + [section])
            total = count_tokens(candidate)
            if total == -1:
                total = len(candidate) // 4
            if total > max_output_tokens:
                break
            kept_sections.append(section)
            kept_refs.append(ref)
        sections, resolved_refs = kept_sections, kept_refs

    return "\n\n".join(sections), resolved_refs
```

### 4. `rag_get_fnc_content.py` — thêm `compress_connected_content()` với cache

```python
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
        model_name: Model name. None = dùng config.COMPRESSION_MODEL.
    
    Returns:
        Compressed string nếu thành công và nằm trong budget.
        None nếu LLM call thất bại.
    """
    import config as _config
    _model = model_name or _config.COMPRESSION_MODEL

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

    try:
        response = _config.ollama_chat(
            model=_model,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response["message"]["content"].strip()

        # Sanity check: output phải chứa ít nhất 1 COMPRESSED marker
        if "-- COMPRESSED:" not in result:
            print("  [COMPRESS] Output không đúng format, fallback về signatures")
            return None

        # Lưu cache trước khi trả về
        _save_compression_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"  [COMPRESS] LLM call thất bại: {e}")
        return None
```

### 4. `rag_get_fnc_content.py` — sửa `extract_connected_content()`

Thay khối fallback hiện tại:

```python
# TRƯỚC:
if total_tokens > max_total_tokens:
    print(f"  [CONTEXT] Full content ~{total_tokens} tokens "
          f"> ngưỡng {max_total_tokens} → chuyển sang signature-only mode")
    sig_content, _ = extract_signatures_only(lua_refs, max_output_tokens=max_total_tokens)
    return sig_content

# SAU:
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
            compressed_tokens = len(compressed) // 4   # char-count fallback
        
        if compressed_tokens <= max_total_tokens:
            print(
                f"  [CONTEXT] Compressed: {total_tokens} → {compressed_tokens} tokens "
                f"({100 - compressed_tokens * 100 // total_tokens}% reduction)"
            )
            return compressed
        else:
            print(
                f"  [CONTEXT] Compressed vẫn còn {compressed_tokens} tokens "
                f"> ngưỡng → fallback signature-only"
            )
    
### 5. `rag_get_fnc_content.py` — sửa `extract_connected_content()`

Thay khối fallback hiện tại:

```python
# TRƯỚC:
if total_tokens > max_total_tokens:
    print(f"  [CONTEXT] Full content ~{total_tokens} tokens "
          f"> ngưỡng {max_total_tokens} → chuyển sang signature-only mode")
    sig_content, _ = extract_signatures_only(lua_refs, max_output_tokens=max_total_tokens)
    return sig_content

# SAU:
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
```

---

## Thứ tự thực hiện

```
1. config.py                   ← thêm COMPRESSION_MODEL + COMPRESSION_CACHE_DIR
2. rag_get_fnc_content.py      ← thêm 3 cache helpers (_key, _load, _save)
3. rag_get_fnc_content.py      ← thêm _extract_compact_signature() + extract_compact_content()
4. rag_get_fnc_content.py      ← thêm compress_connected_content() với cache tích hợp
5. rag_get_fnc_content.py      ← sửa extract_connected_content() fallback (3-tier)
6. chunked_olm.py              ← di chuyển clear_merge_checkpoint (Fix P3)
```

---

## Kết quả kỳ vọng

```
-- Happy path (cache miss lần đầu):
[CONTEXT] Full content ~15247 tokens > ngưỡng 3500 → LLM compression
[COMPRESS CACHE] Saved: a3f9b2c1...
[CONTEXT] Compressed: 15247 → 2840 tokens (81% reduction)
[CTX] Chunk 2: 50 refs, mode=compressed

-- Happy path (cache hit):
[CONTEXT] Full content ~15247 tokens > ngưỡng 3500 → LLM compression
[COMPRESS CACHE] Hit: a3f9b2c1...
[CONTEXT] Compressed: 15247 → 2840 tokens (81% reduction)
[CTX] Chunk 2: 50 refs, mode=compressed

-- LLM fail:
[CONTEXT] Full content ~15247 tokens > ngưỡng 3500 → LLM compression
[COMPRESS] LLM call thất bại: ...
[CONTEXT] LLM thất bại → COMPACT fallback
[CONTEXT] COMPACT: 1840 tokens
[CTX] Chunk 2: 50 refs, mode=compact

-- COMPACT vẫn quá lớn (last resort):
[CONTEXT] Fallback → signature-only mode
[CTX] Chunk 2: 50 refs, mode=signatures
```

LLM chunk analysis nhận đủ return values và error states. Từ lần chạy thứ 2 trở đi
(hoặc khi file khác cùng reference `health.lua`) — không tốn thêm LLM call cho compression.

---

## Fix P3 — `clear_merge_checkpoint` sau khi confirm thành công

**Nguyên nhân:** `hierarchical_merge()` xóa checkpoint tầng 1 trước khi gọi
`generate_merged_doc()`. Nếu merge thất bại (rate limit, mất kết nối) → intermediate
results của tầng 1 đã mất → phải chạy lại 100% từ đầu.

### `chunked_olm.py` — trong `hierarchical_merge()`

```python
# TRƯỚC (sai):
clear_merge_checkpoint(comp_name)       # ← xóa TRƯỚC khi merge
merge_prompt = build_merge_prompt(...)
return generate_merged_doc(...)

# SAU (đúng):
merge_prompt = build_merge_prompt(...)
result = generate_merged_doc(
    prompt=merge_prompt,
    md_filepath=md_filepath,
    model_name=model_name,
    sleep_time=sleep_time,
)
if result:
    clear_merge_checkpoint(comp_name)   # ← chỉ xóa khi chắc chắn thành công
return result
```

---

## Lưu ý

- **Fallback chain:** LLM compress → COMPACT static → signature-only. Pipeline không bao giờ break.
- **Cache location:** `.cache/compression_cache/` — tách riêng khỏi `.cache/chunked_checkpoints/` vì vòng đời khác nhau (checkpoint tạm thời, compression cache vĩnh viễn).
- **Cache invalidation tự nhiên:** Source Lua thay đổi → function body thay đổi → `full_content` thay đổi → MD5 khác → cache miss → LLM compress lại.
- **Không có TTL, không tự xóa:** DST source code ổn định, hàng trăm file reference cùng `health.lua`, `combat.lua`. Cache chỉ cần xóa thủ công khi muốn force refresh.
- **COMPRESSION_MODEL:** Có thể đổi sang model nhỏ hơn (vd: `qwen3:8b`) để giảm latency nếu cần.
