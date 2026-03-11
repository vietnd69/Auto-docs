# Implementation Plan: Hierarchical Merge cho Chunked Pipeline

> **Vấn đề gốc:** `SGwilson.lua` → 100 chunks → `build_merge_prompt()` gộp tất cả vào 1 prompt → 
> `ollama.chat()` timeout 504. Toàn bộ 100 chunk results đã xử lý xong nhưng bước merge thất bại.

---

## Phân tích nguyên nhân

```
[Hiện tại]
100 chunk_results (~5000 dòng text)
         ↓
build_merge_prompt() → merged_chunks string (quá lớn)
         ↓
ollama.chat() → 504 timeout ❌
```

**3 điểm yếu trong code hiện tại:**

| Vị trí | Vấn đề |
|---|---|
| `process_chunked_file()` | Không có checkpoint → mất hết nếu crash ở bất kỳ bước nào |
| `build_merge_prompt()` | Ghép toàn bộ `chunk_results` thành 1 string không kiểm tra size |
| `generate_merged_doc()` | Không có retry, không có fallback khi timeout |

---

## Kiến trúc giải pháp: 3 tầng bảo vệ

```
Tầng 1 — CHECKPOINT     : Lưu chunk results ra disk, không bao giờ mất work
Tầng 2 — BUDGET CHECK   : Kiểm tra tổng token trước khi merge, chọn strategy
Tầng 3 — HIERARCHICAL   : Nếu quá lớn → merge theo nhóm (10×10 → 10 → 1)

Fallback cuối: ROLLING MERGE (tích lũy từng cặp)
```

---

## Chi tiết thay đổi theo từng file

### File 1: `chunked_prompt.py` — Thêm 1 function mới

**Thêm `build_intermediate_merge_prompt()`** — dùng riêng cho merge trung gian 
(gọn hơn `build_merge_prompt()`, không có YAML frontmatter, không có context đầy đủ):

```python
def build_intermediate_merge_prompt(
    comp_name: str,
    display_filepath: str,
    group_results: list[str],
    group_index: int,
    total_groups: int,
) -> str:
    """
    Prompt gọn cho merge trung gian (tầng 1 của hierarchical merge).
    KHÔNG cần file_tree, connected_content, YAML frontmatter.
    Chỉ yêu cầu LLM tổng hợp các chunk analyses thành 1 intermediate summary.
    """
    combined = ""
    for i, r in enumerate(group_results, 1):
        combined += f"\n--- ANALYSIS {i}/{len(group_results)} ---\n{r}\n"

    return f"""You are merging partial analyses of a Lua file: {display_filepath}
This is intermediate merge group {group_index}/{total_groups}.

Below are {len(group_results)} chunk analyses. Merge them into ONE structured summary.

RULES:
- Deduplicate functions and properties.
- Keep ALL functions found. Do NOT drop any.
- Keep the same section structure: Constructor / Functions / Events / Dependencies / Tags.
- Do NOT produce YAML frontmatter.
- Be concise but complete.

=== ANALYSES TO MERGE ===
{combined}
"""
```

**Không thay đổi** `build_chunk_prompt()` và `build_merge_prompt()`.

---

### File 2: `chunked.py` — Thêm 1 utility function

**Thêm `estimate_merge_tokens()`** — kiểm tra tổng size trước khi merge:

```python
def estimate_merge_tokens(chunk_results: list[str]) -> int:
    """
    Ước tính tổng số token của tất cả chunk results.
    Dùng để quyết định strategy trước khi gọi LLM merge.
    
    Returns:
        Số token ước tính. -1 nếu không có tiktoken.
    """
    combined = "\n".join(chunk_results)
    return count_tokens(combined)  # count_tokens() đã có sẵn trong chunked.py


# Thêm hằng số:
MERGE_TOKEN_LIMIT = 12000  # Nếu tổng chunk results > 12K token → dùng hierarchical
```

---

### File 3: `chunked_olm.py` — Các thay đổi chính

#### 3a. Thêm checkpoint system

```python
import json
from pathlib import Path

CHECKPOINT_DIR = ".cache/chunked_checkpoints"

def save_checkpoint(comp_name: str, chunk_results: list[str], last_index: int) -> None:
    """Lưu tiến độ sau mỗi chunk thành công (atomic write)."""
    Path(CHECKPOINT_DIR).mkdir(parents=True, exist_ok=True)
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.json"
    temp_path = f"{checkpoint_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump({
            "comp_name": comp_name,
            "last_index": last_index,
            "chunk_results": chunk_results,
        }, f, ensure_ascii=False)
    os.replace(temp_path, checkpoint_path)


def load_checkpoint(comp_name: str) -> tuple[list[str], int] | None:
    """
    Load checkpoint nếu tồn tại.
    Returns (chunk_results, last_index) hoặc None nếu không có.
    """
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.json"
    if not Path(checkpoint_path).exists():
        return None
    try:
        with open(checkpoint_path, encoding="utf-8") as f:
            state = json.load(f)
        print(f"  [CHECKPOINT] Resume từ chunk {state['last_index'] + 1}")
        return state["chunk_results"], state["last_index"]
    except Exception as e:
        print(f"  [CHECKPOINT] Không load được: {e}")
        return None


def clear_checkpoint(comp_name: str) -> None:
    """Xoá checkpoint sau khi merge thành công."""
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.json"
    if Path(checkpoint_path).exists():
        Path(checkpoint_path).unlink()
```

#### 3b. Thêm `hierarchical_merge()`

```python
from chunked import estimate_merge_tokens, MERGE_TOKEN_LIMIT
from chunked_prompt import build_intermediate_merge_prompt

def hierarchical_merge(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    chunk_results: list[str],
    source_hash: str,
    md_filepath: str,
    *,
    file_tree: str = "",
    connected_section: str = "",
    connected_content: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    sidebar_position: int = 10,
    model_name: str = "qwen3-coder-next:cloud",
    group_size: int = 10,
    sleep_time: int = 10,
) -> str | None:
    """
    Merge hierarchical 2 tầng:
      Tầng 1: Chia chunk_results thành nhóm group_size, merge mỗi nhóm → intermediate summary
      Tầng 2: Merge tất cả intermediate summaries → final document

    Được gọi khi estimate_merge_tokens(chunk_results) > MERGE_TOKEN_LIMIT.
    """
    total = len(chunk_results)
    groups = [chunk_results[i:i + group_size] for i in range(0, total, group_size)]
    total_groups = len(groups)

    print(f"  [HIERARCHICAL] {total} chunks → {total_groups} nhóm × {group_size}")

    # Tầng 1: merge từng nhóm
    intermediate_results: list[str] = []

    for g_idx, group in enumerate(groups, 1):
        print(f"  [HIERARCHICAL] Nhóm {g_idx}/{total_groups} ({len(group)} chunks)...")

        prompt = build_intermediate_merge_prompt(
            comp_name=comp_name,
            display_filepath=display_filepath,
            group_results=group,
            group_index=g_idx,
            total_groups=total_groups,
        )

        result = generate_chunk_analysis(  # Tái dùng hàm có sẵn
            prompt=prompt,
            chunk_index=g_idx,
            total_chunks=total_groups,
            model_name=model_name,
            sleep_time=sleep_time,
        )

        if result:
            intermediate_results.append(result)
        else:
            print(f"  [HIERARCHICAL] Nhóm {g_idx} thất bại, bỏ qua.")

    if not intermediate_results:
        print("  [HIERARCHICAL] Tất cả nhóm trung gian đều thất bại!")
        return None

    print(f"  [HIERARCHICAL] Tầng 1 xong: {len(intermediate_results)} intermediate summaries")

    # Kiểm tra: tầng 2 có vượt ngưỡng không?
    # Nếu vẫn lớn (hiếm, nhưng có thể với file cực lớn) → rolling merge tầng 2
    if estimate_merge_tokens(intermediate_results) > MERGE_TOKEN_LIMIT:
        print("  [HIERARCHICAL] Intermediate results vẫn lớn → rolling merge tầng 2")
        intermediate_results = [rolling_merge_to_one(
            comp_name=comp_name,
            display_filepath=display_filepath,
            results=intermediate_results,
            model_name=model_name,
            sleep_time=sleep_time,
        )]

    # Tầng 2: final merge
    merge_prompt = build_merge_prompt(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        chunk_results=intermediate_results,  # Chỉ còn ~10 summaries ngắn gọn
        source_hash=source_hash,
        file_tree=file_tree,
        connected_section=connected_section,
        connected_content=connected_content,
        today_date=today_date,
        version=version,
        category_type=category_type,
        sidebar_position=sidebar_position,
    )

    return generate_merged_doc(
        prompt=merge_prompt,
        md_filepath=md_filepath,
        model_name=model_name,
        sleep_time=sleep_time,
    )
```

#### 3c. Thêm `rolling_merge_to_one()` — fallback cuối

```python
def rolling_merge_to_one(
    comp_name: str,
    display_filepath: str,
    results: list[str],
    model_name: str,
    sleep_time: int,
) -> str:
    """
    Fallback: merge tuần tự từng cặp.
    Dùng khi hierarchical tầng 2 vẫn bị overflow.
    Trả về 1 string tổng hợp (KHÔNG ghi file).
    """
    accumulated = results[0]
    for i, result in enumerate(results[1:], 2):
        print(f"  [ROLLING] Merge {i}/{len(results)}...")
        prompt = build_intermediate_merge_prompt(
            comp_name=comp_name,
            display_filepath=display_filepath,
            group_results=[accumulated, result],
            group_index=i,
            total_groups=len(results),
        )
        merged = generate_chunk_analysis(
            prompt=prompt,
            chunk_index=i,
            total_chunks=len(results),
            model_name=model_name,
            sleep_time=sleep_time,
        )
        if merged:
            accumulated = merged
    return accumulated
```

#### 3d. Sửa `process_chunked_file()` — tích hợp tất cả

Các thay đổi trong hàm `process_chunked_file()` hiện có:

```python
def process_chunked_file(...) -> str | None:
    
    # ... (giữ nguyên Bước 1, 2, 3 hiện có) ...

    # ── THAY ĐỔI: Bổ sung checkpoint resume ────────────────────────
    
    # Bước 2 (sửa): Phân tích từng chunk, hỗ trợ resume từ checkpoint
    resume = load_checkpoint(comp_name)
    if resume:
        chunk_results, resume_from = resume
        print(f"  [CHECKPOINT] Đã có {len(chunk_results)} chunk, tiếp tục từ chunk {resume_from + 1}")
    else:
        chunk_results: list[str] = []
        resume_from = -1

    failed_chunks = 0

    for i, chunk_code in enumerate(chunks, 1):
        # Skip các chunk đã xử lý
        if i - 1 <= resume_from:
            continue

        prompt = build_chunk_prompt(...)

        result = generate_chunk_analysis(
            prompt=prompt,
            chunk_index=i,
            total_chunks=total_chunks,
            model_name=model_name,
            sleep_time=chunk_sleep,
        )

        if result:
            chunk_results.append(result)
            save_checkpoint(comp_name, chunk_results, i - 1)  # ← LƯU SAU MỖI CHUNK
        else:
            failed_chunks += 1
            print(f"    [Cảnh báo] Chunk {i} thất bại, bỏ qua.")

    # ... (kiểm tra failed_chunks như cũ) ...

    # ── THAY ĐỔI: Chọn merge strategy theo size ────────────────────

    # Bước 3 (sửa): Merge thông minh
    total_merge_tokens = estimate_merge_tokens(chunk_results)
    use_hierarchical = (total_merge_tokens > MERGE_TOKEN_LIMIT) or (len(chunk_results) > 30)

    if use_hierarchical:
        token_info = f"{total_merge_tokens} tokens" if total_merge_tokens > 0 else f"{len(chunk_results)} chunks"
        print(f"  [MERGE STRATEGY] Hierarchical ({token_info} > ngưỡng)")
        result = hierarchical_merge(
            comp_name=comp_name,
            comp_title=comp_title,
            display_filepath=display_filepath,
            chunk_results=chunk_results,
            source_hash=source_hash,
            md_filepath=md_filepath,
            file_tree=file_tree,
            connected_section=connected_section,
            connected_content=connected_content,
            today_date=today_date,
            version=version,
            category_type=category_type,
            model_name=model_name,
            sleep_time=merge_sleep,
        )
    else:
        print(f"  [MERGE STRATEGY] Direct merge ({total_merge_tokens} tokens ≤ ngưỡng)")
        merge_prompt = build_merge_prompt(...)  # Như cũ
        result = generate_merged_doc(
            prompt=merge_prompt,
            md_filepath=md_filepath,
            model_name=model_name,
            sleep_time=merge_sleep,
        )

    # Xoá checkpoint nếu thành công
    if result:
        clear_checkpoint(comp_name)

    return result
```

---

## Luồng xử lý mới — Toàn cảnh

```
process_chunked_file()
│
├── load_checkpoint(comp_name)         ← Resume nếu có
│
├── for chunk in chunks:
│     generate_chunk_analysis()
│     save_checkpoint()                ← Lưu sau MỖI chunk
│
├── estimate_merge_tokens(chunk_results)
│
├── if tokens ≤ 12K (file nhỏ ≤ ~30 chunks):
│     build_merge_prompt() → generate_merged_doc()   [như cũ]
│
└── if tokens > 12K (file lớn như SGwilson):
      hierarchical_merge()
      │
      ├── Tầng 1: chunk 100 → 10 nhóm × 10
      │   build_intermediate_merge_prompt() × 10
      │   → 10 intermediate summaries (~500 dòng mỗi cái)
      │
      ├── estimate_merge_tokens(intermediate_results)
      │   if vẫn lớn → rolling_merge_to_one() [fallback]
      │
      └── Tầng 2: 10 summaries → build_merge_prompt() → generate_merged_doc()
            ↓
          SGwilson.md ✓
```

---

## Thứ tự implement

| # | Việc | File | Ưu tiên |
|---|---|---|---|
| 1 | Thêm `MERGE_TOKEN_LIMIT` + `estimate_merge_tokens()` | `chunked.py` | Cao |
| 2 | Thêm `build_intermediate_merge_prompt()` | `chunked_prompt.py` | Cao |
| 3 | Thêm `save/load/clear_checkpoint()` | `chunked_olm.py` | Cao |
| 4 | Thêm `hierarchical_merge()` | `chunked_olm.py` | Cao |
| 5 | Thêm `rolling_merge_to_one()` | `chunked_olm.py` | Trung bình |
| 6 | Sửa `process_chunked_file()` — tích hợp | `chunked_olm.py` | Cao |

> Bước 1–2 là prerequisite, làm trước. Bước 3 có thể làm song song với 4.

---

## Lưu ý quan trọng

**Về checkpoint file:**
- Lưu tại `.cache/chunked_checkpoints/{comp_name}.json`
- File này chứa toàn bộ `chunk_results` (có thể lớn ~2–5MB cho 100 chunks) → bình thường
- Nên thêm `.cache/` vào `.gitignore`

**Về `group_size=10`:**
- Với 100 chunks, tầng 1 cho ra 10 intermediate summaries
- Mỗi intermediate summary thường ngắn hơn raw chunk (LLM đã tổng hợp)
- Tầng 2 merge 10 summaries → dễ dàng nằm trong ngưỡng 12K token

**Về backward compatibility:**
- File ngắn (< 30 chunks) vẫn dùng `build_merge_prompt()` như cũ → không ảnh hưởng
- Chỉ activate hierarchical khi `estimate_merge_tokens() > MERGE_TOKEN_LIMIT` hoặc `len > 30`

**Về `generate_chunk_analysis()` được tái dùng:**
- Hàm này chỉ gọi `ollama.chat()` và trả về text
- Dùng cho cả chunk analysis lẫn intermediate merge → không cần viết thêm Ollama caller