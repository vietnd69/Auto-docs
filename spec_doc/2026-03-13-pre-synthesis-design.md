# Design: Pre-Synthesis — Full JSON Chunk Pipeline

**Date:** 2026-03-13
**Status:** Approved

---

## Problem

LLM merge hiện tại nhận toàn bộ chunk results (~1,000 dòng text) và phải làm tất cả trong 1 lần:
- Dedup và chọn lọc `tags` — từ hàng trăm tags lặp lại qua nhiều chunks
- Quyết định `system_scope` — chọn 1 trong 14 giá trị hợp lệ
- Tổng hợp `dependencies` và `constructor_properties`
- Format `## Properties` table
- Viết `## Main functions` — cần hiểu semantic sâu
- Viết `## Overview` và `## Usage example`

**Root cause:** Attention budget bị phân tán vào những việc có thể làm bằng code, khiến phần quan trọng (semantic prose) bị ảnh hưởng.

---

## Approach: Full JSON Replacement

Chunk LLM không còn output text analysis. Thay vào đó, output **JSON thuần** với schema cố định. Python `pre_synthesize()` aggregate tất cả JSON chunks (pure Python, không gọi LLM). Merge LLM nhận `PreSynthesisResult` đã pre-filled và chỉ viết semantic prose.

**Lưu ý quan trọng:** `pre_synthesize()` là pure Python aggregation — không có LLM call, không có token cost. Vì vậy, nó luôn chạy trên **toàn bộ N chunks** trước khi quyết định merge strategy. Output `PreSynthesisResult` nhỏ hơn nhiều so với raw chunk text, nên **hierarchical merge và rolling merge không còn cần thiết** cho JSON pipeline — `build_merge_prompt()` luôn được gọi trực tiếp một lần.

---

## Architecture & Data Flow

```
Lua source file
      │
      ▼
split_lua_into_chunks()              [chunked.py — unchanged]
      │
      ▼ (N chunks)
build_chunk_prompt()                 [chunked_prompt.py — REWRITTEN]
      │  instructs LLM: output ONLY JSON matching schema
      ▼
LLM → JSON string per chunk          [chunked_olm.py]
      │
      ├─► save_checkpoint() v2       [chunk result = JSON string, version=2]
      │
      ▼ (all N chunks done)
pre_synthesize(chunk_results)        [NEW: pre_synthesis.py — pure Python, no LLM]
      │  - union tags, dependencies
      │  - majority vote system_scope
      │  - flatten functions list (exclude incomplete=True)
      │  - dedup constructor_properties, events by key
      │  - collect partial_descriptions
      │  - returns (PreSynthesisResult, malformed_indices)
      │
      ├─► if malformed_indices:
      │     save_checkpoint(failed_indices=malformed, version=2)
      │     return None  ← block merge, retry on next run
      │
      ▼ (all chunks clean)
build_merge_prompt(presynthesis, …)  [chunked_prompt.py — REWRITTEN]
      │  - YAML frontmatter pre-filled (tags, scope, deps)
      │  - properties injected as JSON → LLM formats to table
      │  - functions injected as JSON → LLM dedup by name + formats to prose
      │  - events injected as JSON → LLM formats
      │  - LLM task: description, Overview, Usage example only
      ▼
LLM → final markdown doc
```

`hierarchical_merge()` và `rolling_merge_to_one()` **không được gọi** trong JSON pipeline. Các functions này được giữ lại trong code cho backward compat nhưng không tham gia vào luồng mới.

---

## JSON Schema — Chunk Output

```json
{
  "partial_description": "Handles player stamina depletion during sprint actions",
  "suggested_scope": "player",
  "constructor_properties": [
    {
      "name": "stamina",
      "type": "number",
      "default": "100",
      "description": "Current stamina value"
    }
  ],
  "functions": [
    {
      "name": "DoSprint",
      "params": "inst, speed_mult",
      "description": "Initiates sprint, consuming stamina per tick",
      "returns": "nil",
      "error_states": "Returns early if stamina <= 0",
      "incomplete": false
    }
  ],
  "events": {
    "listens_to": [{"event": "onsprintstart", "description": "Triggers stamina drain loop"}],
    "pushes":     [{"event": "onstaminaempty", "description": "Fired when stamina hits 0"}]
  },
  "dependencies": [
    {"component": "health", "usage": "Read current health before allowing sprint"}
  ],
  "tags": [
    {"name": "sprinting", "operation": "add"},
    {"name": "sprinting", "operation": "remove"}
  ]
}
```

**Schema notes:**
- `incomplete: true` — function bị cắt tại chunk boundary. Python exclude khỏi flat list; merge LLM không nhận data không đầy đủ.
- `partial_description` — 1 câu hoàn chỉnh mô tả nội dung chunk này.
- `suggested_scope` — string tự do, Python validate bằng allowlist, fallback `"entity"` nếu invalid.
- `tags[].operation` — `"add"` | `"remove"` | `"check"`, giữ lại vì có giá trị cho docs.
- Tất cả fields là required. LLM được instruct viết `"None"` string nếu không tìm thấy (Python sẽ filter out `"None"` strings khi aggregate).

---

## `pre_synthesis.py` — New Module

```python
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

VALID_SCOPES = {
    "world", "player", "entity", "ui", "audio", "combat",
    "environment", "inventory", "crafting", "network",
    "brain", "locomotion", "physics", "fx"
}


@dataclass
class PreSynthesisResult:
    tags: list[str]                    # dedup, sorted
    system_scope: str                  # majority vote, validated
    dependencies: list[dict]           # dedup by "component"
    partial_descriptions: list[str]    # 1 per chunk, for merge LLM
    functions: list[dict]              # flat, incomplete=False only
    events_listens: list[dict]         # dedup by "event"
    events_pushes: list[dict]          # dedup by "event"
    constructor_properties: list[dict] # dedup by "name"


def pre_synthesize(
    chunk_results: dict[int, str],     # {chunk_index (1-based): json_string}
) -> tuple[PreSynthesisResult, list[int]]:
    """
    Parse và aggregate JSON từ tất cả chunks.
    Returns (PreSynthesisResult, malformed_indices).
    malformed_indices != [] → caller phải block merge và retry.
    Khi có malformed chunks, valid data bị discard — hàm luôn cần
    tất cả chunks clean để đảm bảo aggregate đầy đủ (idempotent by design).
    """
    valid_chunks: list[dict] = []
    malformed_indices: list[int] = []

    for idx in sorted(chunk_results.keys()):
        raw = chunk_results[idx]
        try:
            parsed = json.loads(raw)
            valid_chunks.append(parsed)
        except (json.JSONDecodeError, ValueError):
            malformed_indices.append(idx)

    if malformed_indices:
        return _empty_result(), malformed_indices

    return _aggregate(valid_chunks), []


def _aggregate(chunks: list[dict]) -> PreSynthesisResult:
    tags   = sorted({
        t["name"] for c in chunks
        for t in c.get("tags", [])
        if t.get("name") and t["name"] != "None"
    })
    deps   = _dedup_by_key(
        [d for c in chunks for d in c.get("dependencies", []) if d.get("component") != "None"],
        "component"
    )
    props  = _dedup_by_key(
        [p for c in chunks for p in c.get("constructor_properties", [])],
        "name"
    )
    listens = _dedup_by_key(
        [e for c in chunks for e in c.get("events", {}).get("listens_to", [])],
        "event"
    )
    pushes = _dedup_by_key(
        [e for c in chunks for e in c.get("events", {}).get("pushes", [])],
        "event"
    )
    scope  = _majority_vote(
        [c.get("suggested_scope", "") for c in chunks],
        valid=VALID_SCOPES,
        fallback="entity",
    )
    descs  = [
        c["partial_description"] for c in chunks
        if c.get("partial_description") and c["partial_description"] != "None"
    ]
    # Functions: flatten, exclude incomplete.
    # Name-level dedup là trách nhiệm của merge LLM (semantic dedup).
    # Python chỉ loại bỏ functions bị cắt tại chunk boundary.
    funcs  = [
        f for c in chunks
        for f in c.get("functions", [])
        if not f.get("incomplete")
    ]

    return PreSynthesisResult(tags, scope, deps, descs, funcs, listens, pushes, props)


def _empty_result() -> PreSynthesisResult:
    return PreSynthesisResult(
        tags=[], system_scope="entity", dependencies=[],
        partial_descriptions=[], functions=[],
        events_listens=[], events_pushes=[], constructor_properties=[]
    )


def _dedup_by_key(items: list[dict], key: str) -> list[dict]:
    """Giữ first-seen entry cho mỗi giá trị của key."""
    seen: set[str] = set()
    result: list[dict] = []
    for item in items:
        k = item.get(key, "")
        if k and k not in seen:
            seen.add(k)
            result.append(item)
    return result


def _majority_vote(values: list[str], valid: set[str], fallback: str) -> str:
    """
    Majority vote từ list values.
    Chỉ đếm values nằm trong valid set.
    Tie-break: chọn giá trị xuất hiện đầu tiên trong list.
    Nếu không có value nào valid, trả về fallback.
    """
    valid_values = [v for v in values if v in valid]
    if not valid_values:
        return fallback
    counts = Counter(valid_values)
    max_count = max(counts.values())
    # Tie-break: first-seen order
    for v in valid_values:
        if counts[v] == max_count:
            return v
    return fallback
```

---

## Error Handling — Malformed Chunks

Nếu bất kỳ chunk nào output JSON không hợp lệ:

```python
# Trong process_chunked_file(), sau khi collect đủ chunk_results:
presynthesis, malformed = pre_synthesize(chunk_results)

if malformed:
    save_checkpoint(comp_name, chunk_results, last_index, failed_indices=malformed)
    print(f"  [PRE-SYNTHESIS] {len(malformed)} chunk malformed JSON: {malformed}")
    print(f"  [PRE-SYNTHESIS] Retry các chunk trên rồi chạy lại.")
    return None  # block merge hoàn toàn
```

**Retry flow:**
```
Lần 1: chunk 3 malformed → checkpoint saved với failed_indices=[3] → exit
Lần 2: load checkpoint → retry chunk 3 → nếu clean → pre_synthesize all chunks → merge
Lần 3+: chunk 3 vẫn fail → failed_indices=[3] lại → user cần debug prompt/model
```

Merge chỉ chạy khi **tất cả chunks** đều parse thành công. Valid data bị discard khi có malformed — điều này là intentional: `pre_synthesize()` cần tất cả chunks để aggregate đầy đủ. Khi retry thành công, toàn bộ `chunk_results` (đã có chunk 3 mới) được aggregate lại.

---

## `build_merge_prompt()` — New Signature & Changes

**New function signature:**
```python
def build_merge_prompt(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    presynthesis: PreSynthesisResult,
    source_hash: str = "",
    *,
    file_tree: str = "",
    connected_section: str = "",
    connected_content: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    sidebar_position: int = 10,
) -> str:
```

**YAML frontmatter — pre-filled:**
```yaml
---
id: {comp_name}
title: {comp_title}
description:                                           ← LLM viết (từ partial_descriptions)
tags: [{", ".join(f'"{t}"' for t in presynthesis.tags)}]  ← pre-filled
system_scope: {presynthesis.system_scope}              ← pre-filled
...
---
```

**Injected sections — LLM chỉ format, không tự tìm:**
```
=== PARTIAL DESCRIPTIONS (one per chunk) ===
Synthesize these into a single description sentence for the YAML frontmatter.
1. {desc_1}
2. {desc_2}
...

=== DEPENDENCIES (pre-extracted) ===
{json.dumps(presynthesis.dependencies, indent=2)}

=== PROPERTIES ===
Format into a markdown table. Do not invent or omit entries.
{json.dumps(presynthesis.constructor_properties, indent=2)}

=== FUNCTIONS ===
Deduplicate by name (prefer longer description). Format into ### headings.
{json.dumps(presynthesis.functions, indent=2)}

=== EVENTS ===
{json.dumps({"listens_to": presynthesis.events_listens, "pushes": presynthesis.events_pushes}, indent=2)}
```

**LLM tasks — chỉ còn:**
- Viết `description` (1 câu từ partial_descriptions)
- Viết `## Overview`
- Viết `## Usage example`
- Format `## Properties` từ JSON → table
- Dedup by name + format `## Main functions` từ JSON → prose
- Format `## Events & listeners` từ JSON

**Removed từ merge LLM responsibility:**
- ~~Tự quyết định `tags`~~
- ~~Tự quyết định `system_scope`~~
- ~~Tự list `dependencies`~~
- ~~Tự tìm `constructor_properties`~~

---

## Checkpoint Format — v2

`save_checkpoint()` phải thêm `"version": 2` vào JSON output:

```python
json.dump({
    "version": 2,                    # ← THÊM MỚI
    "comp_name": comp_name,
    "last_index": last_index,
    "chunk_results": {str(k): v for k, v in chunk_results.items()},
    "failed_indices": failed_indices or [],
}, f, ensure_ascii=False)
```

**`save_checkpoint()` không thêm `version` vào parameter** — `version` được hardcode bên trong hàm:

```python
def save_checkpoint(
    comp_name: str,
    chunk_results: dict[int, str],
    last_index: int,
    failed_indices: list[int] | None = None,
) -> None:
    ...
    json.dump({
        "version": 2,          # hardcoded, không phải parameter
        "comp_name": comp_name,
        ...
    }, f, ensure_ascii=False)
```

**`load_checkpoint()` trả về `None` trên v1** — caller `process_chunked_file()` xử lý giống như không có checkpoint:

```python
checkpoint = load_checkpoint(comp_name)
if checkpoint is None:
    chunk_results, last_index, failed_indices = {}, -1, []
else:
    chunk_results, last_index, failed_indices = checkpoint
```

Behavior này không thay đổi so với hiện tại — `load_checkpoint()` đã trả về `None` khi file không tồn tại hoặc parse lỗi.

**Checkpoint v2 example** (chunk indices là 1-based, matching `enumerate(chunks, 1)`):
```json
{
  "version": 2,
  "comp_name": "actions",
  "last_index": 5,
  "failed_indices": [],
  "chunk_results": {
    "1": "{\"partial_description\": \"...\", \"functions\": [...], ...}",
    "2": "{\"partial_description\": \"...\", \"functions\": [...], ...}"
  }
}
```

**Backward compatibility trong `load_checkpoint()`:**
```python
version = state.get("version", 1)
if version == 1:
    # v1 = text markdown results, không parse được thành JSON
    print("  [CHECKPOINT] v1 checkpoint detected — clearing, restart from scratch")
    clear_checkpoint(comp_name)
    return None
```

v1 checkpoints bị clear và rerun từ đầu — không có cách migrate text → JSON.

---

## Files Changed

| File | Thay đổi |
|------|----------|
| `chunked_prompt.py` | Rewrite `build_chunk_prompt()` → JSON schema output; rewrite `build_merge_prompt()` → nhận `PreSynthesisResult`, new signature |
| `chunked_olm.py` | `process_chunked_file()` gọi `pre_synthesize()`, block on malformed; `save_checkpoint()` thêm `version=2`; `load_checkpoint()` version detection và clear v1 |
| `pre_synthesis.py` | **New** — `PreSynthesisResult`, `pre_synthesize()`, `_aggregate()`, `_empty_result()`, `_dedup_by_key()`, `_majority_vote()` |
| `chunked.py` | Không đổi |

`hierarchical_merge()` và `rolling_merge_to_one()` trong `chunked_olm.py` được giữ nguyên (không xóa) nhưng không được gọi trong JSON pipeline. Chúng vẫn hoạt động với text chunks nếu cần rollback.

---

## Out of Scope

- Parallel chunk processing (spec riêng)
- Pre-fill `## Usage example` — cần full API context
- Semantic dedup của functions bằng embeddings — LLM dedup đủ tốt với JSON input
- Migration tool cho v1 → v2 checkpoints
