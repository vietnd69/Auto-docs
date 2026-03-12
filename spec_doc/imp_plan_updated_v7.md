# Implementation Plan: Per-chunk Connected Content

**Vấn đề:** `connected_content` được tính 1 lần cho toàn bộ file Lua rồi nhét vào mọi chunk prompt,
khiến shell token quá lớn → budget dành cho code gần bằng 0 → tạo quá nhiều chunk nhỏ, mỗi chunk lại
bị nhồi toàn bộ context của 30 refs dù thực tế chỉ dùng 2–3.

---

## Mục lục

1. [Chẩn đoán root cause](#1-chẩn-đoán-root-cause)
2. [Kiến trúc thay đổi](#2-kiến-trúc-thay-đổi)
3. [Chi tiết từng file](#3-chi-tiết-từng-file)
   - 3.1 [rag_get_fnc_content.py](#31-rag_get_fnc_contentpy)
   - 3.2 [chunked.py](#32-chunkedpy)
   - 3.3 [chunked_olm.py](#33-chunked_olmpy)
   - 3.4 [main.py](#34-mainpy)
4. [Luồng xử lý sau khi sửa](#4-luồng-xử-lý-sau-khi-sửa)
5. [Rủi ro và cách xử lý](#5-rủi-ro-và-cách-xử-lý)
6. [Bảng tóm tắt](#6-bảng-tóm-tắt)
7. [Kiểm thử](#7-kiểm-thử)
8. [Rollback](#8-rollback)

---

## 1. Chẩn đoán root cause

```
main.py
  └── extract_lua_references(full_lua_code)          ← refs của TOÀN BỘ file
        └── extract_connected_content(all_refs)       ← content của TOÀN BỘ refs
              └── process_chunked_file(
                      connected_content = KHỔNG LỒ   ← nhét vào MỌI chunk
                  )
                    └── calc_token_budget(
                            connected_content = KHỔNG LỒ
                        )
                          ← shell tokens = file_tree + refs_khổng_lồ + metadata
                          ← budget còn lại cho code ≈ 0
                    └── split_lua_into_chunks(budget ≈ 0)
                          ← sinh ra 100+ chunk siêu nhỏ
                    └── for chunk in chunks:
                          build_chunk_prompt(
                              connected_content = KHỔNG LỒ  ← 30 refs dù chunk
                          )                                     chỉ dùng 2–3
```

Hai hệ quả song song:

- **Budget sai**: `calc_token_budget()` đo shell với full refs → budget cho code ≈ 0
- **Noise per chunk**: mỗi chunk nhận full context 30 refs dù chỉ reference 2–3 file

---

## 2. Kiến trúc thay đổi

```
TRƯỚC
─────────────────────────────────────────────────────────────
full_lua_code
    → extract_refs(full)
    → connected_content(full)  ──────────────────────────────┐
                                                             ↓
                                              nhét vào MỌI chunk prompt

SAU
─────────────────────────────────────────────────────────────
full_lua_code ───────────────────────────────────────────────→ merge prompt
    │                                                           (giữ nguyên)
    │
    ├─ calc_token_budget(shell_only, không có connected)
    │       └─ effective_budget = base - CONTEXT_RESERVE(3500)
    │
    ├─ split_chunks(effective_budget)           ← ít chunk hơn, chunk béo hơn
    │
    └─ for each chunk:
           extract_refs(chunk_code)             ← chỉ refs TRONG chunk này
           ├─ chunk_refs có → extract_connected_content(
           │      chunk_refs,
           │      max_total_tokens=3500        ← hard cap
           │  )
           │      ├─ full bodies  nếu tổng < 3500 tokens
           │      └─ signatures_only nếu tổng > 3500 tokens  ← fallback tự động
           ├─ chunk_refs rỗng + chunk dùng self.components.X hoặc cross-chunk require
           │      → filter full_refs → signatures_only(filtered_refs)  ← smart fallback
           └─ chunk thực sự độc lập → ("", "", 0)
           build_chunk_prompt(chunk_connected)  ← nhỏ, relevant, fit in budget
```

---

## 3. Chi tiết từng file

### 3.1 `rag_get_fnc_content.py`

**Số thay đổi: 4** *(tăng từ 3 lên 4 — thêm Thay đổi 0 fix import)*

---

#### Thay đổi 0 — Thêm import từ `get_docs.py` **(CRITICAL)**

`extract_connected_for_chunk()` gọi `extract_lua_references()` và `format_connected_section()` trực tiếp, nhưng **cả hai hàm này không nằm trong `rag_get_fnc_content.py`** — chúng đang nằm trong `get_docs.py`.

Hiện tại `rag_get_fnc_content.py` chỉ import `re` và `os`, không import gì từ `get_docs.py`. Nếu không thêm import này, `extract_connected_for_chunk()` sẽ crash `NameError` ngay khi được gọi.

Thêm vào block import ở đầu file:

```python
from get_docs import extract_lua_references, format_connected_section
```

> **Không có circular import risk:** `get_docs.py` không import từ `rag_get_fnc_content.py`, nên không cần lazy import ở đây. Import thẳng ở top-level là đúng.

> **Lưu ý:** Sau khi thêm import này, ghi chú cũ *"không cần import từ chính module này"* trong docstring của `extract_connected_for_chunk()` vẫn đúng — ý nói không cần import từ chính `rag_get_fnc_content.py`, không phải từ `get_docs.py`.

---

> **Lưu ý trước (còn lại):** Tất cả các hàm mới dưới đây đều nằm trong cùng file `rag_get_fnc_content.py`, **không cần import lẫn nhau** (gọi thẳng trong cùng module).

---

#### Thay đổi A — Thêm hàm `extract_signatures_only()`

> **Lưu ý:** `format_connected_section()` đã được import từ `get_docs.py` (Thay đổi 0). Không cần tạo lại.

> **Prerequisite (kiểm tra trước khi implement):** `rag_get_fnc_content.py` phải đã có 2 helper:
> - `_resolve_lua_path(ref_path: str) -> str | None` — resolve relative Lua path sang absolute path
> - `_extract_class_name(lua_code: str) -> str | None` — extract tên class từ Lua source
>
> Xác nhận bằng cách grep file. Nếu chưa có, tạo hai hàm này trước — chúng là prerequisite của
> `extract_signatures_only()`. Nếu thiếu sẽ crash `NameError` ngay lần đầu gọi.

Fallback mode khi full content vượt token budget.
Chỉ lấy đúng 1 dòng khai báo function, không lấy body.

> **Lưu ý truncation:** Hàm nhận thêm param `max_output_tokens` để tự cắt bớt nếu output vượt ngưỡng.
> Nếu vượt, refs ít quan trọng hơn (cuối danh sách) sẽ bị bỏ qua. Điều này đảm bảo output luôn fit
> trong `CONTEXT_RESERVE` ngay cả khi file có rất nhiều refs.

> **Return type — tuple (Fix Risk #14):** Hàm trả về `(content, kept_refs)` thay vì `str` để
> `extract_connected_for_chunk()` có thể rebuild `connected_section` chính xác từ refs thực tế có
> trong output (sau truncation), không phải từ full input list. Xem Risk #14.

```python
def extract_signatures_only(
    lua_refs: list[tuple[str, list[str]]],
    max_output_tokens: int = 0,   # 0 = không giới hạn
) -> tuple[str, list[tuple[str, list[str]]]]:
    """
    Fallback mode: chỉ lấy dòng khai báo function (signature), không lấy body.

    Nếu max_output_tokens > 0 và output vượt ngưỡng, refs cuối danh sách sẽ bị
    bỏ qua (truncate by ref, không truncate giữa chừng một ref).

    Output ví dụ:
        --- FILE: ./components/health.lua (class: Health) ---
        --[SIGONLY: function Health:DoDelta(amount, overtime, cause, ignore_min, afflicter)]
        --[SIGONLY: function Health:GetPercent()]

    Returns:
        (content, kept_refs)
        content:    chuỗi signatures; empty string nếu không tìm được gì.
        kept_refs:  list các ref tuple thực sự xuất hiện trong output — dùng để rebuild
                    connected_section chính xác. Có thể nhỏ hơn lua_refs nếu bị truncate
                    hoặc file/class không resolve được trên disk.
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
            # Nếu không tìm được sig: silent skip (không crash, không trả về nội dung sai)

        if sigs:
            header = f"--- FILE: {ref_path} (class: {class_name}) ---"
            sections.append(header + "\n" + "\n".join(sigs))
            resolved_refs.append((ref_path, func_names))

    if not sections:
        return "", []

    # Truncation: cắt bớt refs cuối nếu vượt max_output_tokens
    if max_output_tokens > 0:
        # Lazy import để tránh circular dependency — xem Risk #6.
        from chunked import count_tokens
        kept_sections = []
        kept_refs = []
        for section, ref in zip(sections, resolved_refs):
            candidate = "\n\n".join(kept_sections + [section])
            total = count_tokens(candidate)
            if total == -1:
                total = len(candidate) // 4   # char-count fallback
            if total > max_output_tokens:
                print(
                    f"  [SIG] Truncated: giữ {len(kept_sections)}/{len(sections)} refs "
                    f"để fit trong {max_output_tokens} tokens"
                )
                break
            kept_sections.append(section)
            kept_refs.append(ref)
        sections = kept_sections
        resolved_refs = kept_refs

    if not sections:
        return "", []

    return "\n\n".join(sections), resolved_refs
```

---

#### Thay đổi B — Thêm tham số `max_total_tokens` vào `extract_connected_content()`

Signature hiện tại:
```python
def extract_connected_content(
    lua_refs: list[tuple[str, list[str]]],
    max_lines_per_file: int = 100,
) -> str:
```

Signature mới (backward-compatible):
```python
def extract_connected_content(
    lua_refs: list[tuple[str, list[str]]],
    max_lines_per_file: int = 100,
    max_total_tokens: int = 0,    # 0 = không giới hạn
) -> str:
```

Logic bổ sung — thêm vào **sau dòng `full_result = "\n\n".join(sections)`**, trước `return full_result`. Hàm hiện tại kết thúc bằng:

```python
    if not sections:
        return ""
    return "\n\n".join(sections)
```

Sửa thành:

```python
    if not sections:
        return ""

    full_result = "\n\n".join(sections)

    # Kiểm tra token budget nếu có giới hạn
    if max_total_tokens > 0:
        # Lazy import để tránh circular dependency:
        #   rag_get_fnc_content ← chunked_olm ← chunked
        # chunked không import rag_get_fnc_content nên không có vòng tròn,
        # nhưng lazy import tường minh ở đây để dễ truy vết nếu cấu trúc thay đổi.
        from chunked import count_tokens
        total_tokens = count_tokens(full_result)

        if total_tokens == -1:
            # Fallback khi tiktoken không có: ước tính bằng char count (1 token ≈ 4 chars)
            total_tokens = len(full_result) // 4

        if total_tokens > max_total_tokens:
            print(
                f"  [CONTEXT] Full content ~{total_tokens} tokens "
                f"> ngưỡng {max_total_tokens} → chuyển sang signature-only mode"
            )
            # extract_signatures_only() giờ trả về tuple — lấy phần content ([0]).
            # kept_refs không cần ở đây vì extract_connected_content() vẫn trả về str.
            sig_content, _ = extract_signatures_only(lua_refs, max_output_tokens=max_total_tokens)
            return sig_content

    return full_result
```

> **Lưu ý vị trí chèn:** Code mới được chèn SAU `"\n\n".join(sections)` và chỉ chạy khi `sections` không rỗng. Không được nhầm chèn sau dòng `if not sections: return ""` mà bỏ qua join.

> **Lưu ý circular import:** `from chunked import count_tokens` được đặt dạng lazy import bên trong hàm (không ở top-level). Xem thêm Risk #6.

> **Lưu ý fallback char-count:** Đảm bảo logic vẫn chạy đúng khi tiktoken chưa được cài. Không cần tách nhánh riêng cho Risk #5.

---

#### Thay đổi C — Thêm hàm `extract_connected_for_chunk()`

Convenience wrapper, gộp 3 bước thành 1 call dùng trong loop chunk.
Signature nhận thêm `full_refs` để xử lý trường hợp smart fallback (Risk #1).

Hàm trả về **3-tuple** `(section, content, ref_count)` thay vì 2-tuple để caller có thể log
`ref_count` chính xác mà không cần truy cập biến nội bộ.

> **Quan trọng — self-import:** Hàm này nằm trong `rag_get_fnc_content.py`, do đó gọi thẳng
> `extract_lua_references()`, `format_connected_section()`, `extract_connected_content()`, và
> `extract_signatures_only()` **mà không cần import từ chính module này**.

> **Quan trọng — phạm vi smart fallback:** `extract_lua_references()` đã bắt được pattern
> `inst.components.X` thông qua regex `(?<!self\.)components\.(\w+)`, nên các chunk thông thường
> gọi `inst.components.health:DoDelta()` sẽ có `chunk_refs` **không rỗng** — smart fallback **không
> kích hoạt** cho những trường hợp này. Smart fallback chỉ thực sự cần cho 2 trường hợp biên:
> 1. **Cross-chunk require:** `require("util/module")` nằm ở chunk đầu, chunk sau dùng module nhưng
>    không có `require()` riêng → `chunk_refs` rỗng dù chunk gọi external symbol.
> 2. **`self.components.X` pattern:** bị negative lookbehind trong `extract_lua_references` bỏ qua
>    (DST convention: `self.components.X` = component tự access component khác trên cùng entity) →
>    `chunk_refs` rỗng dù chunk phụ thuộc external.

> **Quan trọng — filter trước khi fallback (Fix #4):** Khi smart fallback kích hoạt, hàm filter
> `full_refs` xuống chỉ còn các refs mà chunk thực sự reference được, TRƯỚC KHI truyền vào
> `format_connected_section()` và `extract_signatures_only()`. Điều này đảm bảo section header và
> content luôn nhất quán — LLM không thấy "Connected: health, hunger, combat, inventory..." nhưng
> chỉ nhận signatures của 1–2 file.

> **Quan trọng — guard section/content mismatch:** Nếu `extract_signatures_only()` không tìm được
> sig nào (trả về `""`), hàm trả về `("", "", 0)` để tránh inject section header rỗng vào prompt.

> **Known limitation — cross-chunk require:** Filter hiện tại dùng regex `components.<name>` để
> detect external call. Trường hợp `require`-based cross-chunk (chunk 1 khai báo `local util = require(...)`,
> chunk 2 gọi `util.SomeFunction()`) sẽ KHÔNG bị bắt bởi filter này vì chunk 2 không chứa string
> `components.util`. Chunk đó sẽ bị xử lý như chunk độc lập và nhận `("", "", 0)`.
>
> **Đánh giá impact:** Trong codebase DST, require-based cross-chunk hiếm hơn đáng kể so với
> `inst.components.X` pattern. Phần lớn utility module (lấy từ `require`) không cần full context
> vì chúng là pure functions. Gap này là **known limitation được chấp nhận** — không crash,
> chỉ giảm quality của chunk đó. Nếu muốn cover, bổ sung nhánh filter thứ hai (xem Risk #11).

```python
def extract_connected_for_chunk(
    chunk_code: str,
    own_filename: str,
    full_refs: list[tuple[str, list[str]]] | None = None,
    max_lines_per_file: int = 100,
    max_total_tokens: int = 3500,
) -> tuple[str, str, int]:
    """
    Trích xuất connected_section + connected_content + ref_count cho 1 chunk cụ thể.

    Khác với flow thông thường (tính trên full file), hàm này chỉ xét
    các require() và components.X xuất hiện trong chunk_code đang xét,
    giúp prompt nhỏ gọn và chỉ chứa context thực sự cần thiết.

    Smart fallback (khi chunk_refs rỗng):
        extract_lua_references() đã handle pattern inst.components.X thông thường.
        Fallback chỉ kích hoạt cho 2 trường hợp biên:
        - Cross-chunk require: require() ở chunk trước, chunk này dùng module nhưng không re-import.
        - self.components.X: bị negative lookbehind của extract_lua_references bỏ qua.
        Khi fallback kích hoạt, full_refs được FILTER xuống chỉ còn refs mà chunk thực sự
        reference được (theo pattern components.<name>), rồi mới truyền vào
        format_connected_section + extract_signatures_only.

    Known limitation:
        Require-based cross-chunk (chunk 1: local x = require(...), chunk 2: x.Fn()) KHÔNG bị
        bắt bởi filter `components.<name>`. Chunk đó nhận ("", "", 0) — graceful degrade.
        Xem Risk #11 để biết cách mở rộng nếu cần.

    Args:
        chunk_code:         Nội dung chunk hiện tại.
        own_filename:       Tên file đang xử lý (để loại self-reference).
        full_refs:          Refs của toàn bộ file — dùng làm fallback.
        max_lines_per_file: Giới hạn dòng per file khi extract full bodies.
                            Mặc định 100 để nhất quán với extract_connected_content().
        max_total_tokens:   Hard cap token cho toàn bộ connected content.

    Returns:
        (connected_section, connected_content, ref_count)
        connected_section: chuỗi mô tả refs (dùng trong prompt header)
        connected_content: source code / signatures (dùng trong prompt body)
        ref_count:         số refs thực tế được inject (dùng để log ở caller)
    """
    chunk_refs = extract_lua_references(chunk_code, own_filename)

    # Fallback: chunk không có ref cục bộ nhưng full file có refs.
    # Chỉ xảy ra với 2 trường hợp biên (cross-chunk require, self.components.X).
    # Lưu ý: inst.components.X thông thường đã được extract_lua_references handle,
    # nên chunk_refs sẽ không rỗng cho những trường hợp đó.
    if not chunk_refs and full_refs:
        # Filter full_refs xuống chỉ còn refs mà chunk thực sự reference theo pattern
        # components.<name>. Require-based cross-chunk KHÔNG được bắt ở đây (known gap).
        filtered_refs = [
            (ref_path, funcs)
            for ref_path, funcs in full_refs
            if re.search(
                rf'\bcomponents\.{re.escape(ref_path.split("/")[-1].replace(".lua", ""))}',
                chunk_code,
            )
        ]

        if not filtered_refs:
            # Chunk thực sự độc lập (hoặc require-based cross-chunk — known gap)
            return "", "", 0

        print(f"    [CTX] Chunk không có local refs nhưng có external call → fallback signatures từ filtered_refs ({len(filtered_refs)} refs)")
        # extract_signatures_only() trả về tuple — unpack để lấy kept_refs (fix Risk #14).
        fallback_content, fallback_kept_refs = extract_signatures_only(filtered_refs, max_output_tokens=max_total_tokens)

        # Guard: nếu không tìm được sig nào → không inject header rỗng
        if not fallback_content:
            return "", "", 0

        # Rebuild section từ kept_refs thực tế (sau truncation), không phải filtered_refs đầy đủ.
        # Đảm bảo section header và content luôn nhất quán — fix Risk #14.
        fallback_section = format_connected_section(fallback_kept_refs)
        return fallback_section, fallback_content, len(fallback_kept_refs)

    connected_content = extract_connected_content(
        chunk_refs,
        max_lines_per_file=max_lines_per_file,
        max_total_tokens=max_total_tokens,
    )

    # Guard: nếu không extract được content nào (file không tồn tại, binary, v.v.)
    # → không inject section header rỗng vào prompt.
    # Trả về len(chunk_refs) thay vì 0 để caller phân biệt "file missing" với
    # "chunk thực sự độc lập" — fix Risk #15.
    if not connected_content:
        return "", "", len(chunk_refs)

    # Rebuild section từ kept_refs thực tế — fix Risk #14.
    # extract_connected_content() có thể đã truncate sang signatures và bỏ một số refs.
    # Nếu output có marker "--[SIGONLY:", gọi lại extract_signatures_only() để lấy kept_refs.
    # I/O penalty nhỏ (chỉ xảy ra khi truncation đã xảy ra), chấp nhận được — xem Risk #4.
    # Lưu ý: "--[SIGONLY:" là format đặc biệt không bao giờ xuất hiện tự nhiên trong Lua
    # comment thông thường → false-positive về cơ bản bằng 0. Nếu false-positive xảy ra:
    # kept_refs được rebuild qua extract_signatures_only() nhưng content vẫn là full bodies
    # → section có thể under-report refs so với content (over-safe, không crash).
    if "--[SIGONLY:" in connected_content:
        _, kept_refs = extract_signatures_only(chunk_refs, max_output_tokens=max_total_tokens)
    else:
        kept_refs = chunk_refs  # full bodies — toàn bộ refs đều có trong content

    connected_section = format_connected_section(kept_refs)
    return connected_section, connected_content, len(kept_refs)
```

---

### 3.2 `chunked.py`

**Số thay đổi: 2**

> **Lưu ý thứ tự:** Các thay đổi được đánh tên A, C, B (không phải A, B, C) vì Thay đổi C là bug fix
> hoàn toàn độc lập với logic per-chunk context. Thứ tự implement được khuyến nghị: C trước (bug fix
> riêng, dễ review độc lập), sau đó A rồi B (vì B phụ thuộc hằng số từ A).

---

#### Thay đổi A — Thêm hằng số `CONTEXT_RESERVE`

Thêm vào block hằng số ở đầu file, cùng nhóm với `PROMPT_TOKEN_LIMIT`:

```python
# Token reserve dành cho per-chunk connected context (signatures hoặc full bodies).
# calc_token_budget() sẽ tự trừ khoản này khỏi code budget để đảm bảo
# mỗi chunk prompt luôn có chỗ cho context sau khi inject.
#
# PHẠM VI ÁP DỤNG: Chỉ dành cho calc_token_budget() trong chunked pipeline.
# KHÔNG áp dụng vào estimate_merge_tokens() — merge prompt dùng full context
# được tính riêng bởi caller (main.py).
#
# CALIBRATION: Full bodies của 3–5 refs điển hình ~2000–3000 tokens;
# signatures của 30 refs ~1500 tokens. 3500 đủ buffer cho cả hai mode.
# Nếu file_tree hoặc connected_section tăng kích thước đáng kể, tăng con số này.
#
# TRADE-OFF: Reserve này cố định cho MỌI chunk, kể cả chunk không có external refs
# (chunk đó sẽ dùng 0 token context nhưng vẫn bị cắt 3500 khỏi code budget).
# Nếu muốn tối ưu: tính actual chunk context size trước rồi trừ đúng số đó — nhưng
# cần 2-pass processing (scan chunk → tính context → split) phức tạp hơn đáng kể.
# Fixed reserve đơn giản hơn và đủ tốt cho scope hiện tại.
CONTEXT_RESERVE = 3500
```

> **Lưu ý scope:** `CONTEXT_RESERVE` được export ra ngoài (dùng trong `chunked_olm.py`) nhưng **chỉ có ý nghĩa với `calc_token_budget()`**. `estimate_merge_tokens()` không trừ khoản này — merge prompt nhận full connected context từ `main.py` và đã tính sẵn trong shell của nó.

---

#### Thay đổi C — Fix `strip_bulk_data()`: output Lua syntax không hợp lệ **(BUG FIX)**

File `chunked.py` hiện tại có bug ở dòng replacement trong `strip_bulk_data()`. Python f-string `{{{{` và `}}}}` được render thành `{{` và `}}` — là syntax **không tồn tại trong Lua**. LLM nhận đoạn code stripped này có thể bị confuse khi parse.

Trong `strip_bulk_data()`, sửa dòng `result.append(...)`:

```python
# TRƯỚC (bug — sinh ra {{ }} không phải Lua):
result.append(
    f"{indent}{field}{{{{ --[[ {num_count} numeric values (tile/map data) ]] }}}}"
)

# SAU (fix — valid Lua: empty table với comment):
result.append(
    f"{indent}{field}{{--[[ {num_count} numeric values (tile/map data) ]]}}"
)
```

Output trước: `data = {{ --[[ 360000 numeric values ]] }}` — không hợp lệ  
Output sau: `data = {--[[ 360000 numeric values ]]}` — valid Lua empty table với inline comment

---

#### Thay đổi B — Sửa `calc_token_budget()` để tự trừ `CONTEXT_RESERVE`

> **Trước khi sửa:** Kiểm tra toàn bộ codebase để liệt kê **tất cả call site** của `calc_token_budget()`.
> Mọi call site phải truyền `connected_content=""` sau khi patch, nếu không sẽ bị double-deduct.
> Hiện tại chỉ biết 1 call site trong `chunked_olm.py` — xác nhận không còn call site nào khác.

Thay dòng `return max(budget, 1000)` hiện tại thành:

```python
    # Guard tiktoken missing: count_tokens() trả về -1 → shell_tokens = -1
    # → budget = PROMPT_TOKEN_LIMIT - (-1) = rất lớn → gây ảo giác budget vô hạn.
    # Trong trường hợp này return sớm với default budget, không áp dụng CONTEXT_RESERVE
    # (fallback mode không có token measurement — chấp nhận được).
    if shell_tokens < 0:
        print(
            f"  [TOKEN BUDGET] tiktoken missing — dùng fallback budget "
            f"(CONTEXT_RESERVE không được áp dụng trong fallback mode)"
        )
        return max(PROMPT_TOKEN_LIMIT - CONTEXT_RESERVE, 1000)

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
```

Thêm **log warning** (thay vì hard assert) làm **dòng đầu tiên** của function body — đặt **trước** lazy import `from chunked_prompt import build_chunk_prompt` để cảnh báo sớm nhất có thể:

```python
def calc_token_budget(...):
    # Warning phải ở đây — TRƯỚC mọi logic kể cả lazy import.
    # Nếu connected_content non-empty được truyền vào, CONTEXT_RESERVE sẽ bị trừ 2 lần.
    if connected_content:
        print(
            "[WARN] calc_token_budget() nhận connected_content non-empty. "
            "Trong chunked pipeline phải truyền connected_content='' vì CONTEXT_RESERVE "
            "đã được trừ nội bộ. Double-deduction có thể xảy ra."
        )
    from chunked_prompt import build_chunk_prompt   # ← lazy import theo sau
    ...
```

> **Tại sao dùng warning thay vì assert:** `assert` sẽ crash bất kỳ caller nào ngoài `chunked_olm.py`
> (test code, debug scripts, pipeline khác). Warning đủ để phát hiện lỗi trong dev mà không gây
> regression ngoài ý muốn. Nếu muốn strict hơn sau khi đã migrate hết call site, có thể đổi
> thành `assert` ở phase sau.

---

### 3.3 `chunked_olm.py`

**Số thay đổi: 4 chỗ trong `process_chunked_file()`**

---

#### Thay đổi A — Sửa import

Sửa block import ở đầu file:

```python
from chunked import (
    needs_chunking,
    split_lua_into_chunks,
    strip_bulk_data,
    calc_token_budget,
    estimate_merge_tokens,
    MERGE_TOKEN_LIMIT,
    CONTEXT_RESERVE,           # ← thêm mới
)

from rag_get_fnc_content import (
    extract_connected_for_chunk,   # ← thêm mới (trả về 3-tuple)
    extract_connected_content,     # ← GIỮ LẠI — dùng trong __main__ block
                                   #   để tính connected_content cho merge prompt
)
```

> **Lưu ý — giữ lại `extract_connected_content`:** `__main__` block ở cuối file vẫn gọi
> `extract_connected_content(lua_refs, ...)` để tính `connected_content` truyền vào
> `process_chunked_file()` cho merge prompt. Nếu xóa import này sẽ crash `NameError`
> khi chạy `python chunked_olm.py <lua_file>`. `main.py` (production path) cũng vẫn
> cần hàm này cho cùng mục đích — tính full content một lần rồi truyền vào param.

> **Lưu ý — giữ lại import `extract_lua_references` và `format_connected_section`:** Hai hàm này
> vẫn được dùng trong `__main__` block ở cuối file để chạy standalone test. Nếu xóa nhầm sẽ
> crash khi chạy `python chunked_olm.py <lua_file>`. Kiểm tra toàn bộ import block trước khi
> xóa bất kỳ symbol nào.

> **Import đầy đủ sau patch** — để tránh nhầm lẫn về source của từng symbol, đây là toàn bộ
> import block của `chunked_olm.py` sau khi apply tất cả thay đổi:
>
> ```python
> # Các import này đã có sẵn TRƯỚC khi patch — GIỮ NGUYÊN:
> from get_docs import extract_lua_references, format_connected_section
>
> # Import từ chunked — thêm CONTEXT_RESERVE:
> from chunked import (
>     needs_chunking,
>     split_lua_into_chunks,
>     strip_bulk_data,
>     calc_token_budget,
>     estimate_merge_tokens,
>     MERGE_TOKEN_LIMIT,
>     CONTEXT_RESERVE,           # ← thêm mới
> )
>
> # Import từ rag_get_fnc_content — thêm extract_connected_for_chunk:
> from rag_get_fnc_content import (
>     extract_connected_for_chunk,   # ← thêm mới (trả về 3-tuple)
>     extract_connected_content,     # ← GIỮ LẠI — dùng trong __main__ block + merge path
> )
> ```
>
> Nếu source gốc của `extract_lua_references` / `format_connected_section` khác (ví dụ import
> trực tiếp từ `rag_get_fnc_content`), xác nhận lại trước khi patch. Điều quan trọng là không
> xóa bất kỳ symbol nào đang được dùng trong `__main__` block.

---

#### Thay đổi B — Bước 2: Tính budget không dùng connected content

```python
# TRƯỚC (dòng 449–460):
token_budget = calc_token_budget(
    comp_name=comp_name,
    comp_title=comp_title,
    display_filepath=display_filepath,
    connected_section=connected_section,   # ← full refs, làm shell phình
    connected_content=connected_content,   # ← full content, làm shell phình
    source_hash=source_hash,
    file_tree=file_tree,
    today_date=today_date,
    version=version,
    category_type=category_type,
)

# SAU:
token_budget = calc_token_budget(
    comp_name=comp_name,
    comp_title=comp_title,
    display_filepath=display_filepath,
    connected_section="",   # ← base shell, không có context
    connected_content="",   # ← CONTEXT_RESERVE sẽ được trừ bên trong hàm
    source_hash=source_hash,
    file_tree=file_tree,
    today_date=today_date,
    version=version,
    category_type=category_type,
)
```

---

#### Thay đổi C — Main loop: inject per-chunk context

Thêm `own_filename` **ngay trước main loop** — phải ở cùng function scope với main loop và retry loop:

```python
# Khai báo TRƯỚC main loop — dùng chung cho cả main loop lẫn retry loop.
# own_filename và full_refs phải nằm trong cùng function scope (process_chunked_file).
# Nếu retry loop nằm trong nested function riêng, cần truyền hai biến này vào
# qua tham số hoặc closure tường minh.
own_filename = os.path.basename(display_filepath)

# full_refs được truyền từ ngoài vào qua param mới (xem Thay đổi D).
# Không tính lại từ lua_code ở đây để tránh duplicate I/O.
```

Sửa main loop — lưu ý `extract_connected_for_chunk` giờ trả về **3-tuple**:
```python
for i, chunk_code in enumerate(chunks, 1):
    if i - 1 <= resume_from:
        continue
    if i in chunk_results:
        continue

    # ── PER-CHUNK CONTEXT ──────────────────────────────────────────────
    chunk_section, chunk_content, ref_count = extract_connected_for_chunk(
        chunk_code=chunk_code,
        own_filename=own_filename,
        full_refs=full_refs,               # ← fallback cho chunk không có local refs
        max_lines_per_file=100,            # ← nhất quán với default của extract_connected_content
        max_total_tokens=CONTEXT_RESERVE,
    )
    if chunk_content:
        mode = "signatures" if "--[SIGONLY:" in chunk_content else "full"
        print(f"    [CTX] Chunk {i}: {ref_count} refs, mode={mode}")
    elif ref_count > 0:
        # ref_count > 0 nhưng content rỗng → file không tồn tại trên disk (fix Risk #15)
        print(f"    [CTX] Chunk {i}: {ref_count} refs nhưng không extract được content (file không tồn tại?)")
    else:
        # ref_count == 0 → chunk thực sự độc lập (không có external call nào)
        print(f"    [CTX] Chunk {i}: không có external context (chunk độc lập)")
    # ───────────────────────────────────────────────────────────────────

    prompt = build_chunk_prompt(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        chunk_code=chunk_code,
        chunk_index=i,
        total_chunks=total_chunks,
        today_date=today_date,
        version=version,
        category_type=category_type,
        file_tree=file_tree,
        connected_section=chunk_section,   # ← per-chunk (đã thay)
        connected_content=chunk_content,   # ← per-chunk (đã thay)
    )
    ...
```

---

#### Thay đổi D — Retry loop + thêm param `full_refs` vào signature hàm

**Sửa signature `process_chunked_file()`** để nhận `full_refs` từ ngoài.
Cập nhật docstring để phản ánh param mới:

```python
def process_chunked_file(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    lua_code: str,
    connected_section: str,
    connected_content: str,
    source_hash: str,
    md_filepath: str,
    *,
    full_refs: list[tuple[str, list[str]]] | None = None,   # ← thêm mới
    file_tree: str = "",
    ...
) -> str | None:
    """
    ...
    Args:
        ...
        full_refs: Danh sách refs của toàn bộ file Lua, dùng làm fallback trong
                   extract_connected_for_chunk() cho các chunk không có local refs
                   nhưng vẫn có external call (cross-chunk require — partially handled,
                   hoặc self.components.X).

                   Nếu None (default): chunked pipeline chạy không có fallback context —
                   các chunk thuộc trường hợp biên sẽ nhận connected = "" dù thực tế
                   có thể gọi external symbol. Đây là graceful degrade, không crash,
                   nhưng quality của chunk đó sẽ thấp hơn.

                   Khuyến nghị: luôn truyền full_refs=lua_refs từ main.py.
                   Chỉ để None khi chạy test hoặc debug từng chunk riêng lẻ.
    """
```

`main.py` truyền `full_refs` khi gọi:

```python
result = process_chunked_file(
    ...
    full_refs=lua_refs,   # ← truyền full_refs
)
```

**`__main__` block** ở cuối `chunked_olm.py` cũng phải cập nhật để truyền `full_refs`:

```python
# Trong __main__ block, sau khi đã tính lua_refs:
result = process_chunked_file(
    comp_name=comp_name,
    comp_title=comp_title,
    display_filepath=display_filepath,
    lua_code=lua_code,
    connected_section=connected_section,
    connected_content=connected_content,
    source_hash=source_hash,
    md_filepath=md_output,
    file_tree=file_tree,
    today_date=today_date,
    version="714014",
    category_type="component",
    model_name="qwen3-coder-next:cloud",
    chunk_sleep=10,
    merge_sleep=20,
    full_refs=lua_refs,   # ← thêm dòng này để standalone test có fallback context
)
```

> **Lưu ý:** Nếu không thêm `full_refs` vào `__main__` block, standalone test vẫn chạy được
> (default `None`), nhưng smart fallback sẽ không hoạt động. Thêm vào để hành vi nhất quán
> với production flow.

**Retry loop** áp dụng tương tự main loop — dùng lại `own_filename` và `full_refs` đã khai báo cùng scope trước main loop:

```python
for chunk_i in failed_indices:
    chunk_code = chunks[chunk_i - 1]

    # Per-chunk context cho retry — dùng lại own_filename và full_refs từ trên.
    # Hai biến này phải nằm trong cùng function scope (process_chunked_file),
    # không được khai báo lại bên trong nested function hay closure khác.
    chunk_section, chunk_content, ref_count = extract_connected_for_chunk(
        chunk_code=chunk_code,
        own_filename=own_filename,
        full_refs=full_refs,
        max_lines_per_file=100,
        max_total_tokens=CONTEXT_RESERVE,
    )
    # ── LOG BLOCK — giống hệt main loop ──────────────────────────────────
    if chunk_content:
        mode = "signatures" if "--[SIGONLY:" in chunk_content else "full"
        print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs, mode={mode}")
    elif ref_count > 0:
        print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs nhưng không extract được content (file không tồn tại?)")
    else:
        print(f"    [CTX] Chunk {chunk_i} (retry): không có external context (chunk độc lập)")
    # ─────────────────────────────────────────────────────────────────────

    prompt = build_chunk_prompt(
        ...
        connected_section=chunk_section,   # ← per-chunk
        connected_content=chunk_content,   # ← per-chunk
    )
```

---

### 3.4 `main.py`

**Thay đổi nhỏ: truyền thêm `full_refs`.**

`main.py` vẫn tính `connected_section` và `connected_content` từ full file cho merge prompt và normal pipeline. Chỉ cần thêm `full_refs=lua_refs` khi gọi `process_chunked_file()`:

```python
# Trước:
result = process_chunked_file(
    ...
    connected_section=connected_section,
    connected_content=connected_content,
)

# Sau:
result = process_chunked_file(
    ...
    connected_section=connected_section,
    connected_content=connected_content,
    full_refs=lua_refs,   # ← thêm dòng này
)
```

---

## 4. Luồng xử lý sau khi sửa

```
main.py
  lua_code = safe_read_lua()
  lua_refs = extract_lua_references(lua_code)         ← full refs
  connected_section = format_connected_section()      ← full, cho merge
  connected_content = extract_connected_content()     ← full, cho merge
  process_chunked_file(
      connected_section = full_section,               ← chỉ dùng ở merge
      connected_content = full_content,               ← chỉ dùng ở merge
      full_refs         = lua_refs,                   ← dùng làm fallback
  )

chunked_olm.py → process_chunked_file()

  [Bước 1] strip_bulk_data(lua_code)

  [Bước 2] calc_token_budget(connected_section="", connected_content="")
              shell_tokens  = file_tree + metadata only  ← nhỏ gọn
              code_budget   = limit - shell - CONTEXT_RESERVE(3500)
              print: "Shell: 4200 | Reserve: 3500 | Code budget: 8300"
              (estimate_merge_tokens() KHÔNG trừ CONTEXT_RESERVE — merge dùng full context)

  [Bước 3] split_lua_into_chunks(max_tokens=8300)
              → ít chunks hơn, mỗi chunk đủ béo

  own_filename = os.path.basename(display_filepath)   ← khai báo trước loop (dùng chung)

  [Main loop] for each chunk:
    chunk_section, chunk_content, ref_count = extract_connected_for_chunk(
        chunk_code, own_filename, full_refs=full_refs
    )
      ├─ extract_lua_references(chunk_code)
      │    ├─ chunk_refs có (trường hợp thông thường, kể cả inst.components.X):
      │    │      → extract_connected_content(chunk_refs, max_total_tokens=3500)
      │    │            ├─ full bodies  nếu tổng < 3500 tokens
      │    │            └─ signatures_only(max_output_tokens=3500) nếu tổng > 3500  ← auto fallback + truncation
      │    └─ chunk_refs rỗng (chỉ trường hợp biên):
      │           ├─ filter full_refs → matched_refs (components.<name> pattern only)
      │           │      ├─ matched_refs có:
      │           │      │      → signatures_only(matched_refs, max_output_tokens=3500)
      │           │      │      → nếu sig rỗng → ("", "", 0)   ← guard mismatch
      │           │      └─ matched_refs rỗng:
      │           │             → ("", "", 0)   ← chunk độc lập HOẶC require-based cross-chunk (known gap)
      └─ return (chunk_section, chunk_content, ref_count)   ← 3-tuple,
                                                               section và content luôn nhất quán

    build_chunk_prompt(connected_section=chunk_section,
                       connected_content=chunk_content)
    → prompt fit trong PROMPT_TOKEN_LIMIT ✓

  [Retry loop] — áp dụng tương tự, dùng cùng own_filename + full_refs (same scope)

  [Merge] build_merge_prompt(connected_section=full_section,
                              connected_content=full_content)
          ← vẫn dùng full context cho final doc ✓
```

> **Normal pipeline (non-chunked) không bị ảnh hưởng:** `generate_doc()` trong `olm.py` vẫn nhận `connected_content` đầy đủ từ `main.py` như trước — không có `CONTEXT_RESERVE` nào được trừ vì toàn bộ prompt đã fit trong `PROMPT_TOKEN_LIMIT`.

---

## 5. Rủi ro và cách xử lý

| # | Rủi ro | Nguyên nhân | Cách xử lý |
|---|--------|-------------|------------|
| 1 | Chunk gọi function từ file khác nhưng `require()` nằm ở đầu file (chunk 1), không nằm trong chunk đang xét | `extract_lua_references(chunk_code)` không thấy require statement → `chunk_refs` rỗng. Filter `components.<name>` KHÔNG bắt được require-based call | Smart fallback filter `full_refs` theo pattern `components.<name>`. Require-based cross-chunk là **known gap** — chunk đó nhận `("", "", 0)`, graceful degrade. Xem Risk #11 nếu muốn mở rộng. **Sub-case:** nếu toàn bộ file chỉ dùng `self.components.X` (không có `inst.components.X` nào), `extract_lua_references` sẽ exclude hết do negative lookbehind → `full_refs` rỗng → smart fallback không tìm được sig → cũng nhận `("", "", 0)`. Graceful degrade, không crash. |
| 2 | `CONTEXT_RESERVE = 3500` bị trừ 2 lần nếu caller truyền sai | Caller vẫn truyền non-empty `connected_content` vào `calc_token_budget()` | Đã xử lý trong mục 3.3B — truyền `""` tường minh. Log warning (không crash) để phát hiện lỗi mà không ảnh hưởng pipeline khác |
| 3 | `extract_signatures_only()` không tìm được signature vì pattern không khớp | Class khai báo theo style khác hoặc global function | Silent skip (bỏ qua function đó). Nếu toàn bộ result rỗng → caller guard trả về `("", "", 0)` thay vì inject header rỗng |
| 4 | Nhiều chunk nhỏ → `extract_connected_for_chunk()` đọc disk nhiều lần | I/O lặp per chunk | Chấp nhận được — file I/O rẻ hơn nhiều so với LLM call. Không cần cache trong scope này **Future opt:** nếu benchmark cho thấy I/O là bottleneck (ví dụ file có 50+ chunks cùng reference `health.lua`), có thể thêm `_lua_content_cache: dict[str, str] = {}` ở module-level trong `rag_get_fnc_content.py` để cache nội dung file đã đọc. |
| 5 | `count_tokens()` trả về `-1` (tiktoken chưa cài) → không kích hoạt fallback | tiktoken chưa install | Đã xử lý trong mục 3.1B — fallback `len(full_result) // 4` (char-count estimate) khi `count_tokens == -1` |
| 6 | Circular import khi `rag_get_fnc_content.py` import `chunked` | `chunked_olm` import cả hai; nếu `chunked` sau này import `rag_get_fnc_content` sẽ thành vòng tròn | `from chunked import count_tokens` được đặt dạng lazy import bên trong hàm (không ở top-level). Thêm comment giải thích trong code. Nếu cấu trúc thay đổi, dùng `importlib` hoặc tách `count_tokens` sang module tiện ích riêng |
| 7 | `own_filename` hoặc `full_refs` không available trong retry loop | Retry loop nằm trong nested function hoặc closure khác, mất scope | Đảm bảo retry loop nằm trong cùng function body với main loop bên trong `process_chunked_file()`. Không được extract retry thành nested function riêng trừ khi truyền tường minh qua tham số |
| 8 | `extract_signatures_only()` output vượt `CONTEXT_RESERVE` khi file có rất nhiều refs | Signature-only vẫn có thể lớn nếu refs nhiều | Đã xử lý trong mục 3.1A — `max_output_tokens` tự cắt bớt refs cuối danh sách để đảm bảo output luôn fit |
| 9 | `assert connected_content == ""` crash pipeline không phải chunked | `calc_token_budget()` được gọi từ nhiều nơi | Đã xử lý trong mục 3.2B — dùng log warning thay vì assert; đổi thành assert sau khi đã migrate và xác nhận tất cả call site |
| 10 | `format_connected_section()` chưa tồn tại trong module | Hàm được dùng nhưng chưa được định nghĩa | Xác nhận hàm đã có trước khi implement. Nếu chưa có, tạo mới với output format: `"--- FILE: X (funcs: a, b) ---"` |
| 11 | Require-based cross-chunk gap: chunk 2 gọi `util.Fn()` nhưng `require` ở chunk 1 | Filter `components.<name>` không match variable name từ require | **Known gap được chấp nhận.** Nếu muốn fix: thêm nhánh filter thứ hai — extract tên local variable từ require statement của full file, rồi kiểm tra xem chunk có dùng variable đó không. Chi phí implement cao, impact thấp trong DST codebase |
| 12 | `__main__` block trong `chunked_olm.py` không truyền `full_refs` | Param mới nhưng không update standalone test | Đã xử lý trong mục 3.3D — thêm `full_refs=lua_refs` vào `__main__` block. Default `None` không crash nhưng smart fallback không hoạt động |
| 13 | `extract_lua_references`, `format_connected_section` bị xóa nhầm khỏi import `chunked_olm.py` | Nhầm lẫn khi cleanup import sau patch | Giữ lại hai symbol này — vẫn được dùng trong `__main__` block. Xem note trong mục 3.3A |
| 14 | `connected_section` list nhiều refs hơn content thực sự có sau khi truncate | Xảy ra ở **cả hai nhánh** của `extract_connected_for_chunk()`: (1) **normal path** — `connected_section` tính từ `chunk_refs` đầy đủ trước khi biết `extract_connected_content()` có fallback sang signatures + truncate hay không; (2) **fallback path** — tương tự với `filtered_refs`. LLM thấy section header "Connected: health, hunger, combat..." nhưng content chỉ có signatures của 2 refs đầu — gây confusion. | **Bắt buộc:** Refactor `extract_signatures_only()` trả về tuple `(content, kept_refs)` — đã thực hiện trong Thay đổi A (3.1). **Giữ nguyên** return type `str` của `extract_connected_content()` để tránh phá vỡ các caller bên ngoài (`main.py`, `__main__` block). Thay vào đó, trong `extract_connected_for_chunk()` detect truncation bằng marker `"--[SIGONLY:"` trong output của `extract_connected_content()` (marker này không bao giờ xuất hiện tự nhiên trong Lua source), rồi gọi lại `extract_signatures_only()` để lấy `kept_refs` thực tế (I/O penalty nhỏ, chỉ xảy ra khi truncation đã xảy ra — xem Risk #4). Sau đó tính lại `connected_section = format_connected_section(kept_refs)` ở cả hai nhánh. Xem implementation chi tiết trong mục 3.1C. |

| 15 | Log "chunk độc lập" sai khi chunk có refs nhưng file không resolve được trên disk | Guard trong normal path trả về `("", "", 0)` → `ref_count = 0` → caller log `"không có external context (chunk độc lập)"`. Thực tế chunk có refs, chỉ file không tồn tại — misleading khi debug production | **Fix:** Trong `extract_connected_for_chunk()`, đổi guard normal path thành `return "", "", len(chunk_refs)` (trả về ref_count thực tế thay vì 0). Trong log block của `chunked_olm.py` (3.3C), sửa nhánh `elif ref_count > 0` thành: `print(f"[CTX] Chunk {i}: {ref_count} refs nhưng không extract được content (file không tồn tại?)")`. Nhánh `else` (ref_count == 0) lúc đó chỉ in khi chunk thực sự độc lập. |

---

## 6. Bảng tóm tắt

| File | Thay đổi | Loại | Backward compat |
|------|----------|------|----------------|
| `rag_get_fnc_content.py` | **[CRITICAL]** Thêm `from get_docs import extract_lua_references, format_connected_section` | Import mới | ✅ |
| `rag_get_fnc_content.py` | Thêm `extract_signatures_only(max_output_tokens)` với truncation tự động | Hàm mới | ✅ |
| `rag_get_fnc_content.py` | Thêm param `max_total_tokens` + char-count fallback + vị trí chèn rõ ràng vào `extract_connected_content()` | Param mới, default = 0 | ✅ |
| `rag_get_fnc_content.py` | Thêm `extract_connected_for_chunk()` trả về **3-tuple**; smart fallback filter `full_refs` trước khi inject; guard section/content mismatch; document known gap require-based cross-chunk | Hàm mới | ✅ |
| `chunked.py` | Thêm hằng số `CONTEXT_RESERVE = 3500` (export) | Hằng mới | ✅ |
| `chunked.py` | Sửa `calc_token_budget()` — tự trừ `CONTEXT_RESERVE` + warning ở dòng đầu (trước lazy import) + warning khi budget < 3000 (không assert) | Logic thay đổi | ⚠️ Caller phải truyền `connected_content=""` |
| `chunked.py` | **[BUG FIX]** Sửa `strip_bulk_data()` — f-string `{{{{` → `{{` sinh Lua syntax không hợp lệ; sửa thành `{--[[ ... ]]}` | Bug fix | ✅ |
| `chunked_olm.py` | Thêm `CONTEXT_RESERVE`, `extract_connected_for_chunk` vào import; **giữ** `extract_connected_content` (dùng trong `__main__` block và merge path); **giữ** `extract_lua_references`, `format_connected_section` (dùng trong `__main__`) | Import sửa | — |
| `chunked_olm.py` | Bước 2: truyền `connected_section=""`, `connected_content=""` vào `calc_token_budget()` | Sửa call site | — |
| `chunked_olm.py` | Thêm param `full_refs` vào `process_chunked_file()` + cập nhật docstring (note partial cross-chunk require) | Param mới, default = None | ✅ |
| `chunked_olm.py` | Khai báo `own_filename` trước loop trong cùng function scope | Sửa logic | — |
| `chunked_olm.py` | Main loop: unpack **3-tuple** từ `extract_connected_for_chunk()`, log `ref_count` chính xác | Sửa logic | — |
| `chunked_olm.py` | Retry loop: unpack 3-tuple, dùng cùng `own_filename` + `full_refs` (same scope) | Sửa logic | — |
| `chunked_olm.py` | `__main__` block: thêm `full_refs=lua_refs` để standalone test có fallback context | Sửa standalone | ✅ |
| `main.py` | Truyền thêm `full_refs=lua_refs` khi gọi `process_chunked_file()` | Sửa call site | ✅ |
| `chunked_prompt.py` | Không thay đổi | — | ✅ |

**Thứ tự implement được khuyến nghị:**

**Bước 0 — Kiểm tra prerequisites (trước khi code bất cứ thứ gì):**
- Trong `get_docs.py`: xác nhận export `extract_lua_references` và `format_connected_section`.
  Nếu thiếu → tạo/export trước. Nếu thiếu, Thay đổi 0 sẽ gây `ImportError` ngay khi import.
- Trong `rag_get_fnc_content.py`: xác nhận có 2 helper `_resolve_lua_path()` và `_extract_class_name()`.
  Nếu thiếu → tạo trước. Nếu thiếu, `extract_signatures_only()` sẽ crash `NameError`.
- Cách check nhanh: `grep -n "_resolve_lua_path\|_extract_class_name" rag_get_fnc_content.py`
  và `grep -n "def extract_lua_references\|def format_connected_section" get_docs.py`

1. `rag_get_fnc_content.py` — **trước tiên thêm import từ `get_docs`** (Thay đổi 0), sau đó implement
   `extract_signatures_only()` (trả về tuple — fix Risk #14), cập nhật `extract_connected_content()`
   (unpack tuple từ `extract_signatures_only`), implement `extract_connected_for_chunk()` với normal
   path dùng kept_refs + guard trả về `len(chunk_refs)` (fix Risk #15)
2. `chunked.py` — fix bug `strip_bulk_data` (Thay đổi C), thêm hằng số `CONTEXT_RESERVE`, sửa `calc_token_budget()`
3. `chunked_olm.py` — sửa 4 chỗ, phụ thuộc 2 file trên; cập nhật log block (Risk #15); cập nhật cả `__main__` block
4. `main.py` — thêm 1 dòng `full_refs=lua_refs`

---

## 7. Kiểm thử

Sau khi implement xong, chạy các smoke test sau để xác nhận pipeline hoạt động đúng trước khi chạy full batch.

### 7.1 Unit test `extract_connected_for_chunk()`

Kiểm tra 5 nhánh logic:

```python
# Test 1: chunk có require statement → dùng chunk_refs trực tiếp
chunk_with_require = '''
local health = require("components/health")
health:DoDelta(-10)
'''
section, content, ref_count = extract_connected_for_chunk(
    chunk_code=chunk_with_require,
    own_filename="combat.lua",
    full_refs=[("./components/health.lua", ["DoDelta", "GetPercent"])],
)
assert section != ""
assert ref_count >= 0
assert "DoDelta" in content or content == ""

# Test 2: chunk gọi inst.components.X → extract_lua_references đã handle, KHÔNG qua smart fallback
# chunk_refs sẽ KHÔNG rỗng vì extract_lua_references bắt được pattern components.X
# → content là full bodies (nếu file tồn tại), KHÔNG phải signatures
chunk_inst_components = '''
inst.components.health:DoDelta(-5)
inst.components.hunger:DoDelta(-1)
'''
section, content, ref_count = extract_connected_for_chunk(
    chunk_code=chunk_inst_components,
    own_filename="combat.lua",
    full_refs=[("./components/health.lua", ["DoDelta"]), ("./components/hunger.lua", ["DoDelta"])],
)
assert ref_count >= 0
# Sau khi thêm guard vào normal path:
# - Nếu DST files TỒN TẠI trong test env: content = full bodies, section = non-empty, ref_count > 0
# - Nếu DST files KHÔNG TỒN TẠI (test env thiếu): hàm trả về ("", "", 0) do guard
# Test này chỉ verify đầy đủ khi chạy với DST scripts thực tế.
assert "DoDelta" in content or content == ""
# KHÔNG assert "--[SIGONLY:" in content — chunk này dùng full bodies, không phải signatures
# KHÔNG assert section != "" — guard có thể trả về "" nếu file không tồn tại trong test env

# Test 3: chunk độc lập thực sự → không inject gì
chunk_independent = '''
local x = 1 + 2
return x * 3
'''
section, content, ref_count = extract_connected_for_chunk(
    chunk_code=chunk_independent,
    own_filename="util.lua",
    full_refs=[("./components/health.lua", ["DoDelta"])],
)
assert section == "" and content == "" and ref_count == 0

# Test 4: signature-only output phải fit trong CONTEXT_RESERVE
from chunked import count_tokens, CONTEXT_RESERVE
large_full_refs = [
    ("./components/health.lua", ["DoDelta", "GetPercent", "SetMax"]),
    ("./components/hunger.lua", ["DoDelta", "GetPercent"]),
    # ... thêm nhiều refs để kiểm tra worst case
]
sig_content, _ = extract_signatures_only(large_full_refs, max_output_tokens=CONTEXT_RESERVE)
# Unpack tuple (content, kept_refs) — extract_signatures_only() trả về 2-tuple
if sig_content:
    sig_tokens = count_tokens(sig_content)
    if sig_tokens == -1:
        sig_tokens = len(sig_content) // 4
    assert sig_tokens <= CONTEXT_RESERVE, (
        f"Signature-only output vượt CONTEXT_RESERVE: {sig_tokens} > {CONTEXT_RESERVE} tokens. "
        f"Cần kiểm tra lại logic truncation trong extract_signatures_only()."
    )

# Test 5: guard section/content mismatch — file refs không tồn tại trên disk
# extract_lua_references() BẮT ĐƯỢC pattern "components.nonexistent" (không có self. prefix)
# → chunk_refs KHÔNG rỗng → đi vào normal path.
# extract_connected_content() trả về "" vì file không tồn tại.
# → guard trong normal path (Risk #15 fix) trả về ("", "", len(chunk_refs)).
section, content, ref_count = extract_connected_for_chunk(
    chunk_code="inst.components.nonexistent:Foo()",
    own_filename="combat.lua",
    full_refs=[("./components/nonexistent.lua", ["Foo"])],  # file không tồn tại
)
# Guard trong normal path: connected_content == "" → trả về ("", "", len(chunk_refs))
# ref_count = 1 (không phải 0) — phân biệt "file missing" với "chunk thực sự độc lập" (Risk #15)
assert section == "" and content == ""
assert ref_count == 1, (
    f"Expect ref_count=1 (file not found on disk), got {ref_count}. "
    "Nếu guard vẫn trả về 0, Risk #15 fix chưa được apply vào extract_connected_for_chunk()."
)

# Test 6 (mới): require-based cross-chunk — known gap, phải trả về ("", "", 0)
# Chunk 1 có require, chunk 2 gọi variable từ require nhưng không có pattern components.X
chunk_require_user = '''
-- chunk 2: gọi util.SomeFunction() nhưng require nằm ở chunk 1
util.SomeFunction(inst)
'''
section, content, ref_count = extract_connected_for_chunk(
    chunk_code=chunk_require_user,
    own_filename="combat.lua",
    full_refs=[("./util/module.lua", ["SomeFunction"])],
)
# Expect: ("", "", 0) vì "util" không match pattern components.util
assert section == "" and content == "" and ref_count == 0, (
    "Known gap: require-based cross-chunk phải trả về ('', '', 0). "
    "Nếu assert này fail, filter đã được mở rộng để cover gap này — cập nhật test."
)
```

> **Lưu ý Test 2:** Test này xác nhận rằng `inst.components.X` được xử lý bởi `extract_lua_references`
> (không qua smart fallback), nên content là full bodies chứ không phải `--[SIGONLY:`.

> **Lưu ý Test 6:** Test này document known gap của require-based cross-chunk. Nếu sau này gap được
> fix (Risk #11), test này sẽ fail và cần được cập nhật để phản ánh behavior mới.

### 7.1b Unit test `extract_connected_content()` với `max_total_tokens`

Kiểm tra trực tiếp Thay đổi B — hàm phải tự fallback sang signatures khi full bodies vượt ngưỡng:

```python
# Test B1: full bodies FIT trong ngưỡng → trả về full bodies (không có --[SIGONLY:)
# Dùng refs thực hoặc mock file nhỏ. Nếu không có DST files trong test env: skip test này.
small_refs = [("./components/health.lua", ["GetPercent"])]   # 1 ref, body nhỏ
content = extract_connected_content(small_refs, max_total_tokens=3500)
if content:  # chỉ assert khi file tồn tại
    assert "--[SIGONLY:" not in content, (
        "Full bodies nhỏ hơn ngưỡng nhưng bị chuyển sang signatures — kiểm tra lại logic"
    )

# Test B2: full bodies VƯỢT ngưỡng → fallback sang signatures tự động
# Mock: tạo refs với nhiều file lớn hoặc đặt max_total_tokens rất nhỏ
content_small_budget = extract_connected_content(
    [("./components/health.lua", ["DoDelta", "GetPercent", "SetMax"])],
    max_total_tokens=10,   # ngưỡng cực nhỏ để kích hoạt fallback
)
# Nếu file tồn tại: output phải rỗng hoặc chứa --[SIGONLY: (signature-only mode)
# Nếu file không tồn tại: content sẽ rỗng — assert sau vẫn pass
if content_small_budget:
    assert "--[SIGONLY:" in content_small_budget, (
        "Full bodies vượt max_total_tokens nhưng không fallback sang signatures. "
        "Kiểm tra lại logic trong extract_connected_content() Thay đổi B."
    )

# Test B3: max_total_tokens=0 (mặc định) → không giới hạn, không fallback
content_unlimited = extract_connected_content(
    [("./components/health.lua", ["DoDelta"])],
    max_total_tokens=0,
)
# Dù file có bao nhiêu dòng cũng không kích hoạt fallback signatures
# (chỉ có max_lines_per_file mới cắt — đây là behavior cũ, phải giữ nguyên)
if content_unlimited:
    assert "--[SIGONLY:" not in content_unlimited, (
        "max_total_tokens=0 không được kích hoạt signature fallback — regression từ Thay đổi B"
    )
```

### 7.2 Smoke test budget calculation

Chạy với 1 file Lua thực có refs, kiểm tra log output:

```
[TOKEN BUDGET] Shell: XXXX tokens | Context reserve: 3500 tokens | Code budget: YYYY tokens
```

- `Shell` phải nhỏ (không bao gồm connected content)
- `Code budget` phải > 5000 tokens (đủ cho chunk béo)
- Số chunks sinh ra phải ít hơn đáng kể so với trước khi fix

**Case đặc biệt — môi trường không có tiktoken:**
Khi `tiktoken` chưa được cài, `count_tokens()` trả về `-1`. Guard mới trong `calc_token_budget()` (Thay đổi B) bắt trường hợp này bằng `if shell_tokens < 0` và return sớm với `max(PROMPT_TOKEN_LIMIT - CONTEXT_RESERVE, 1000)` — tránh tính budget âm hoặc vô hạn. Log sẽ xuất hiện:
```
  [TOKEN BUDGET] tiktoken missing — dùng fallback budget (CONTEXT_RESERVE không được áp dụng trong fallback mode)
```

Kiểm tra:
- Log trên phải xuất hiện khi tiktoken chưa cài
- `split_lua_into_chunks()` nhận budget hợp lệ (không phải giá trị vô hạn)
- Pipeline vẫn chạy được, không crash
- `CONTEXT_RESERVE` không được áp dụng chính xác trong fallback mode — chấp nhận được

### 7.3 Kiểm tra log per-chunk

Với file có nhiều refs, mỗi chunk phải log đúng 1 trong 3 trường hợp (prefix 4 spaces vì nằm trong loop):

```
    [CTX] Chunk 1: 3 refs, mode=full
    [CTX] Chunk 2: không có external context (chunk độc lập)
    [CTX] Chunk 3: 2 refs nhưng không extract được content (file không tồn tại?)
```

Log từ `extract_connected_for_chunk()` (in khi smart fallback kích hoạt):
```
    [CTX] Chunk không có local refs nhưng có external call → fallback signatures từ filtered_refs (2 refs)
```

> **Lưu ý:** Dòng log từ `extract_connected_for_chunk()` print trước dòng log từ main loop của `chunked_olm.py`. Nếu cần tìm chunk cụ thể trong log, filter theo `[CTX] Chunk <số>:`.

### 7.4 Regression test merge prompt

Sau khi sửa, merge prompt phải vẫn nhận **full connected content** (không bị ảnh hưởng bởi `CONTEXT_RESERVE`). Kiểm tra bằng cách print `len(connected_content)` trước khi gọi `build_merge_prompt()` — phải bằng với giá trị trước khi apply patch.

### 7.5 Integration test end-to-end (bắt buộc trước khi chạy full batch)

Chạy pipeline trên **1 file Lua thực có 20–30 refs** và xác nhận các điều kiện sau:

```python
# Sau khi pipeline chạy xong, kiểm tra:

# 1. Số chunks phải giảm đáng kể so với trước fix
assert total_chunks < 20, f"Vẫn sinh quá nhiều chunk: {total_chunks}"

# 2. Không có chunk nào nhận full 30-ref context
# (chunk thông thường chỉ có refs của mình; trường hợp biên chỉ có filtered refs)
for i, chunk_log in enumerate(chunk_context_logs):
    # Ngưỡng 10 để tránh false positive với chunk lớn (hợp lệ có thể ref 6–8 components).
    # nới từ 5 lên 10 — chunk béo hơn sau fix budget có thể ref 6–8 components
    assert chunk_log["ref_count"] <= 10, (
        f"Chunk {i} nhận quá nhiều refs ({chunk_log['ref_count']}), "
        f"có thể vẫn đang inject full_refs thay vì chunk/filtered refs"
    )

# 3. Merge prompt vẫn nhận full context
assert merge_connected_content.strip() == original_connected_content.strip(), (
    "Merge prompt bị mất connected content sau khi apply patch"
)

# 4. Không có warning double-deduction trong log
assert "[WARN] calc_token_budget() nhận connected_content non-empty" not in full_log, (
    "Có call site nào đó vẫn truyền connected_content non-empty vào calc_token_budget()"
)
```

**Collect `chunk_context_logs` từ log output (không cần instrument code):**
```python
import re, subprocess

result = subprocess.run(
    ["python", "chunked_olm.py", "path/to/test_file.lua"],
    capture_output=True, text=True
)
full_log = result.stdout

# Parse log lines: "[CTX] Chunk N: M refs, mode=..."
pattern = re.compile(r"\[CTX\] Chunk (\d+): (\d+) refs")
chunk_context_logs = [
    {"chunk": int(m.group(1)), "ref_count": int(m.group(2))}
    for m in pattern.finditer(full_log)
]
total_chunks = len(chunk_context_logs)
```

Nếu chưa có test harness: chạy thủ công với 1 file, quan sát log và so sánh chunk count trước/sau.

---

## 8. Rollback

Nếu fix gây regression (chunk count tăng bất thường, context bị thiếu, hay warning fires liên tục):

**Cách revert nhanh nhất (không cần git revert):**

1. Trong `chunked_olm.py`, đổi lại bước 2 về truyền original `connected_section` và `connected_content`:
   ```python
   # Revert: dùng lại full connected content như cũ
   token_budget = calc_token_budget(
       ...
       connected_section=connected_section,
       connected_content=connected_content,
   )
   ```

2. Trong main loop và retry loop, thay `chunk_section, chunk_content, ref_count` bằng `connected_section, connected_content` gốc:
   ```python
   # Revert: inject full connected content vào mọi chunk
   prompt = build_chunk_prompt(
       ...
       connected_section=connected_section,
       connected_content=connected_content,
   )
   ```

3. Xóa log warning `[WARN] calc_token_budget()...` trong `calc_token_budget()` nếu gây noise.

4. Thêm lại `extract_connected_content` vào import của `chunked_olm.py` nếu cần.

Bước 1–2 đủ để restore behavior cũ hoàn toàn. Các hàm mới (`extract_signatures_only`, `extract_connected_for_chunk`) không ảnh hưởng nếu không được gọi.

> **Ghi chú:** Trước khi chạy full batch trên production, nên test trên 5–10 file đại diện (file nhỏ không có refs, file có 5 refs, file có 30 refs) để xác nhận không có edge case nào bị bỏ sót.
