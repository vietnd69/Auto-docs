# Pre-Synthesis — Full JSON Chunk Pipeline: Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text-based chunk analysis with structured JSON output, then use Python pre-processing to pre-fill structured fields before merge LLM, so merge LLM can focus entirely on semantic prose.

**Architecture:** Chunk LLM outputs JSON matching a fixed schema. `pre_synthesis.py` aggregates all chunk JSONs deterministically (union tags/deps, majority vote scope, flatten functions). Merge LLM receives pre-filled frontmatter + structured data and only writes Overview, Usage example, and prose sections.

**Tech Stack:** Python 3.11+, existing `ollama_chat()` via `config.py`, no new dependencies.

**Spec:** `spec_doc/2026-03-13-pre-synthesis-design.md`

---

## Chunk 1: `pre_synthesis.py` — New Aggregation Module

**Files:**
- Create: `pre_synthesis.py`
- Create: `test_pre_synthesis.py`

---

### Task 1: `PreSynthesisResult` dataclass + `_empty_result()`

- [ ] **Step 1: Create `test_pre_synthesis.py` với test harness**

```python
# test_pre_synthesis.py
"""Unit tests cho pre_synthesis.py — chạy: python test_pre_synthesis.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0

def test(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} — {msg}")
        failed += 1
```

- [ ] **Step 2: Viết test cho `_empty_result()`**

```python
print("\n=== TEST: _empty_result() ===")
from pre_synthesis import _empty_result, PreSynthesisResult

r = _empty_result()
test("_empty_result trả về PreSynthesisResult", isinstance(r, PreSynthesisResult))
test("tags rỗng", r.tags == [])
test("system_scope fallback là entity", r.system_scope == "entity")
test("functions rỗng", r.functions == [])
test("dependencies rỗng", r.dependencies == [])
```

- [ ] **Step 3: Run test, xác nhận FAIL**

```bash
cd d:/code/mod-document && python test_pre_synthesis.py
```
Expected: `ModuleNotFoundError: No module named 'pre_synthesis'`

- [ ] **Step 4: Tạo `pre_synthesis.py` với dataclass và `_empty_result()`**

```python
# pre_synthesis.py
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass

SCOPE_PATTERN = re.compile(r'^[a-z_]+$')


@dataclass
class PreSynthesisResult:
    tags: list[str]                    # dedup, sorted
    system_scope: str                  # majority vote, format-validated
    dependencies: list[dict]           # dedup by "component"
    partial_descriptions: list[str]    # 1 per chunk, for merge LLM
    functions: list[dict]              # flat, incomplete=False only
    events_listens: list[dict]         # dedup by "event"
    events_pushes: list[dict]          # dedup by "event"
    constructor_properties: list[dict] # dedup by "name"


def _empty_result() -> PreSynthesisResult:
    return PreSynthesisResult(
        tags=[], system_scope="entity", dependencies=[],
        partial_descriptions=[], functions=[],
        events_listens=[], events_pushes=[], constructor_properties=[]
    )
```

- [ ] **Step 5: Run test, xác nhận PASS**

```bash
python test_pre_synthesis.py
```
Expected: `[PASS] _empty_result trả về PreSynthesisResult` (và 4 tests khác)

---

### Task 2: `_dedup_by_key()` và `_majority_vote()`

- [ ] **Step 1: Thêm tests cho 2 helpers**

```python
print("\n=== TEST: _dedup_by_key() ===")
from pre_synthesis import _dedup_by_key

items = [
    {"component": "health", "usage": "DoDelta"},
    {"component": "combat", "usage": "Attack"},
    {"component": "health", "usage": "duplicate — should be skipped"},
]
result = _dedup_by_key(items, "component")
test("dedup loại bỏ trùng lặp", len(result) == 2)
test("giữ first-seen", result[0]["usage"] == "DoDelta")
test("empty key bị skip", _dedup_by_key([{"component": ""}], "component") == [])
test("missing key bị skip", _dedup_by_key([{"other": "x"}], "component") == [])

print("\n=== TEST: _majority_vote() ===")
from pre_synthesis import _majority_vote

test("majority vote đúng", _majority_vote(["player","player","entity"], "entity") == "player")
test("tie-break first-seen", _majority_vote(["combat","player","combat","player"], "entity") == "combat")
test("format invalid bị loại", _majority_vote(["PLAYER","Combat"], "entity") == "entity")
test("empty list → fallback", _majority_vote([], "entity") == "entity")
test("underscore hợp lệ", _majority_vote(["combat_ai","combat_ai"], "entity") == "combat_ai")
```

- [ ] **Step 2: Run test, xác nhận FAIL**

```bash
python test_pre_synthesis.py
```
Expected: `ImportError` hoặc `AttributeError` cho 2 functions chưa có.

- [ ] **Step 3: Thêm `_dedup_by_key()` và `_majority_vote()` vào `pre_synthesis.py`**

```python
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


def _majority_vote(values: list[str], fallback: str) -> str:
    """
    Majority vote từ list values.
    Validate format: lowercase letters và underscores only.
    Tie-break: chọn giá trị xuất hiện đầu tiên trong list.
    Nếu không có value nào đúng format, trả về fallback.
    """
    valid_values = [v for v in values if v and SCOPE_PATTERN.match(v)]
    if not valid_values:
        return fallback
    counts = Counter(valid_values)
    max_count = max(counts.values())
    for v in valid_values:
        if counts[v] == max_count:
            return v
    return fallback
```

- [ ] **Step 4: Run test, xác nhận PASS**

```bash
python test_pre_synthesis.py
```
Expected: tất cả tests PASS.

---

### Task 3: `_aggregate()` và `pre_synthesize()`

- [ ] **Step 1: Thêm tests cho `pre_synthesize()`**

```python
import json as _json

print("\n=== TEST: pre_synthesize() — happy path ===")
from pre_synthesis import pre_synthesize

chunk1 = _json.dumps({
    "partial_description": "Handles combat logic",
    "suggested_scope": "combat",
    "constructor_properties": [{"name": "damage", "type": "number", "default": "10", "description": "Base damage"}],
    "functions": [
        {"name": "Attack", "params": "inst, target", "description": "Performs attack", "returns": "nil", "error_states": "", "incomplete": False},
        {"name": "GetDamage", "params": "inst", "description": "Returns damage", "returns": "number", "error_states": "", "incomplete": True},
    ],
    "events": {
        "listens_to": [{"event": "attacked", "description": "On hit received"}],
        "pushes": [{"event": "onattack", "description": "When attacking"}],
    },
    "dependencies": [{"component": "health", "usage": "DoDelta"}],
    "tags": [{"name": "combat", "operation": "add"}, {"name": "None", "operation": "check"}],
})
chunk2 = _json.dumps({
    "partial_description": "Manages ranged attacks",
    "suggested_scope": "combat",
    "constructor_properties": [{"name": "range", "type": "number", "default": "5", "description": "Attack range"}],
    "functions": [
        {"name": "SetRange", "params": "inst, r", "description": "Sets range", "returns": "nil", "error_states": "", "incomplete": False},
    ],
    "events": {
        "listens_to": [{"event": "attacked", "description": "duplicate — should dedup"}],
        "pushes": [],
    },
    "dependencies": [{"component": "health", "usage": "duplicate — should dedup"}],
    "tags": [{"name": "ranged", "operation": "add"}],
})

result, malformed = pre_synthesize({1: chunk1, 2: chunk2})

test("không có malformed", malformed == [])
test("tags dedup và sorted", result.tags == ["combat", "ranged"])
test("'None' tag bị filter", "None" not in result.tags)
test("system_scope majority vote", result.system_scope == "combat")
test("dependencies dedup by component", len(result.dependencies) == 1)
test("constructor_properties từ 2 chunks", len(result.constructor_properties) == 2)
test("incomplete=True bị exclude", len(result.functions) == 2)  # Attack + SetRange
test("functions names", {f["name"] for f in result.functions} == {"Attack", "SetRange"})
test("events listens dedup", len(result.events_listens) == 1)
test("partial_descriptions collected", len(result.partial_descriptions) == 2)

print("\n=== TEST: pre_synthesize() — malformed chunks ===")

result2, malformed2 = pre_synthesize({1: chunk1, 2: "not valid json {{"})
test("malformed_indices chứa index chunk lỗi", 2 in malformed2)
test("malformed không chứa index hợp lệ", 1 not in malformed2)
test("malformed trả về empty result — tags", result2.tags == [])
test("malformed trả về empty result — valid data bị discard", result2.functions == [])
test("malformed trả về empty result — scope fallback", result2.system_scope == "entity")

result3, malformed3 = pre_synthesize({1: "bad", 2: "also bad"})
test("tất cả malformed", len(malformed3) == 2)
```

- [ ] **Step 2: Run test, xác nhận FAIL**

```bash
python test_pre_synthesis.py
```
Expected: `AttributeError: module 'pre_synthesis' has no attribute 'pre_synthesize'`

- [ ] **Step 3: Thêm `_aggregate()` và `pre_synthesize()` vào `pre_synthesis.py`**

```python
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
    tags = sorted({
        t["name"] for c in chunks
        for t in c.get("tags", [])
        if t.get("name") and t["name"] != "None"
    })
    deps = _dedup_by_key(
        [d for c in chunks for d in c.get("dependencies", []) if d.get("component") != "None"],
        "component"
    )
    props = _dedup_by_key(
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
    scope = _majority_vote(
        [c.get("suggested_scope", "") for c in chunks],
        fallback="entity",
    )
    descs = [
        c["partial_description"] for c in chunks
        if c.get("partial_description") and c["partial_description"] != "None"
    ]
    # Functions: flatten, exclude incomplete.
    # Name-level dedup là trách nhiệm của merge LLM (semantic dedup).
    # Python chỉ loại bỏ functions bị cắt tại chunk boundary.
    funcs = [
        f for c in chunks
        for f in c.get("functions", [])
        if not f.get("incomplete")
    ]

    return PreSynthesisResult(tags, scope, deps, descs, funcs, listens, pushes, props)
```

- [ ] **Step 4: Run tất cả tests, xác nhận PASS**

```bash
python test_pre_synthesis.py
```
Expected: tất cả tests PASS, summary cuối hiển thị `0 failed`.

Thêm summary ở cuối `test_pre_synthesis.py`:
```python
print(f"\n{'='*40}")
print(f"Kết quả: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
```

- [ ] **Step 5: Commit**

```bash
git add pre_synthesis.py test_pre_synthesis.py
git commit -m "feat: add pre_synthesis module with PreSynthesisResult and aggregation logic"
```

---

## Chunk 2: `chunked_prompt.py` — Rewrite Chunk & Merge Prompts

**Files:**
- Modify: `chunked_prompt.py`

---

### Task 4: Rewrite `build_chunk_prompt()` → JSON output

Prompt hiện tại yêu cầu LLM output text markdown với `## Constructor analysis`, `## Functions found`, v.v. Thay thế bằng JSON schema instructions.

- [ ] **Step 1: Đọc `chunked_prompt.py` hiện tại để hiểu structure**

```bash
# Đọc file chunked_prompt.py — đã quen với structure từ spec
```

Lưu ý: hàm hiện tại nhận các params: `comp_name`, `comp_title`, `display_filepath`, `chunk_code`, `chunk_index`, `total_chunks`, cùng keyword args `file_tree`, `connected_section`, `connected_content`, `today_date`, `version`, `category_type`. **Giữ nguyên signature** — chỉ thay phần output format instructions.

- [ ] **Step 2: Rewrite `build_chunk_prompt()` trong `chunked_prompt.py`**

Giữ nguyên phần `=== CONTEXT ===` (file_tree, connected files, DST conventions). Thay phần `=== OUTPUT FORMAT ===` và `=== CRITICAL INSTRUCTIONS ===` thành:

```python
    return f"""You are an expert technical writer and a veteran mod developer for the game Don't Starve Together (DST).
You are analyzing CHUNK {chunk_index} of {total_chunks} from the Lua source file: {display_filepath}

This is NOT the full file. You are only seeing a portion of the code.
Your task is to extract and document ALL functions, properties, events, dependencies, and tags found in THIS CHUNK ONLY.

=== CONTEXT ===

1. PROJECT FILE TREE
{file_tree}

2. TARGET FILE: {display_filepath} (chunk {chunk_index}/{total_chunks})

3. CONNECTED FILES AND FUNCTIONS
   {connected_section if connected_section else "No external references found."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
   {connected_content if connected_content else "No function source code available."}

5. DST CODING CONVENTIONS
   - DST uses an Entity Component System (ECS). Components are attached via `inst:AddComponent("name")`.
   - `self.inst` refers to the entity that owns this component.
   - Constructor: `Class(function(self, inst) ... end)`.
   - `inst:ListenForEvent(event, fn)` / `inst:PushEvent(event, data)`.
   - Tags: `inst:AddTag("tag")` / `inst:RemoveTag("tag")` / `inst:HasTag("tag")`.

=== OUTPUT FORMAT ===

Output ONLY a single valid JSON object. No markdown, no code fences, no commentary before or after.
The JSON must strictly match this schema:

{{
  "partial_description": "<ONE complete sentence summarizing what this chunk does>",
  "suggested_scope": "<lowercase_scope e.g. player, combat, inventory>",
  "constructor_properties": [
    {{"name": "<prop>", "type": "<type>", "default": "<default value or 'nil'>", "description": "<what it stores>"}}
  ],
  "functions": [
    {{
      "name": "<FunctionName>",
      "params": "<param1, param2>",
      "description": "<what it does>",
      "returns": "<return type or 'nil'>",
      "error_states": "<edge cases or empty string>",
      "incomplete": <true if function is cut off at chunk boundary, false otherwise>
    }}
  ],
  "events": {{
    "listens_to": [{{"event": "<name>", "description": "<what triggers this>"}}],
    "pushes":     [{{"event": "<name>", "description": "<when it fires>"}}]
  }},
  "dependencies": [{{"component": "<name>", "usage": "<how used>"}}],
  "tags": [{{"name": "<tag>", "operation": "<add|remove|check>"}}]
}}

=== RULES ===
- All array fields are REQUIRED. Use [] if nothing found — do NOT write "None".
- "partial_description": exactly 1 complete English sentence about this chunk's content.
- "suggested_scope": lowercase letters and underscores only.
- "incomplete": true ONLY if a function body is visibly cut off at the start or end of this chunk.
- Do NOT invent APIs not present in this chunk.
- Do NOT include functions from other chunks — only what is in THIS chunk.

=== SOURCE CODE (CHUNK {chunk_index}/{total_chunks}) ===
{chunk_code}
"""
```

- [ ] **Step 3: Chạy `chunked_test.py` để kiểm tra prompt output thủ công**

```bash
python chunked_test.py 2>&1 | head -50
```
Expected: script chạy, in ra prompt cho chunk 1, không crash.

Nếu `chunked_test.py` gọi LLM thực, dừng trước khi gọi LLM bằng cách thêm `sys.exit(0)` tạm thời sau khi print prompt. Kiểm tra JSON schema instructions có xuất hiện đúng trong prompt output.

---

### Task 5: Rewrite `build_merge_prompt()` → nhận `PreSynthesisResult`

- [ ] **Step 1: Update import trong `chunked_prompt.py`**

Thêm ở đầu file:
```python
import json as _json
from pre_synthesis import PreSynthesisResult
```

- [ ] **Step 2: Rewrite `build_merge_prompt()` với new signature**

Thay toàn bộ `build_merge_prompt()`:

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
    """
    Tạo merge prompt với pre-filled frontmatter từ PreSynthesisResult.
    LLM chỉ cần viết description, Overview, Usage example, và format các sections.
    """
    tags_str = "[" + ", ".join(f'"{t}"' for t in presynthesis.tags) + "]"
    descs_numbered = "\n".join(
        f"{i}. {d}" for i, d in enumerate(presynthesis.partial_descriptions, 1)
    )

    return f"""You are an expert technical writer for Don't Starve Together (DST) modding documentation.

All structured data (tags, scope, dependencies, properties, functions, events) has been pre-extracted from the source file.
Your task is to write the prose sections and format the pre-extracted data into a complete API reference document.

=== CONTEXT ===

1. PROJECT FILE TREE
{file_tree}

2. TARGET FILE: {display_filepath}

3. CONNECTED FILES AND FUNCTIONS
   {connected_section if connected_section else "No external references found."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
   {connected_content if connected_content else "No function source code available."}

5. DST CODING CONVENTIONS
   - ECS: components attached via `inst:AddComponent("name")`.
   - `self.inst` = the owning entity.
   - Constructor: `Class(function(self, inst) ... end)`.
   - Events: `inst:ListenForEvent` / `inst:PushEvent`.
   - Tags: `inst:AddTag` / `inst:RemoveTag` / `inst:HasTag`.

=== PRE-EXTRACTED DATA ===

PARTIAL DESCRIPTIONS (one sentence per chunk — synthesize into 1 description sentence):
{descs_numbered}

DEPENDENCIES:
{_json.dumps(presynthesis.dependencies, indent=2, ensure_ascii=False)}

PROPERTIES:
{_json.dumps(presynthesis.constructor_properties, indent=2, ensure_ascii=False)}

FUNCTIONS (deduplicate by name — prefer longer description; format into ### headings):
{_json.dumps(presynthesis.functions, indent=2, ensure_ascii=False)}

EVENTS:
{_json.dumps({{"listens_to": presynthesis.events_listens, "pushes": presynthesis.events_pushes}}, indent=2, ensure_ascii=False)}

=== YOUR TASKS ===

1. Write `description` in the YAML frontmatter: 1 complete English sentence synthesized from the partial descriptions above.
2. Write `## Overview`: clear explanation of what this component does in DST's ECS.
3. Write `## Usage example`: 5-15 line Lua snippet showing typical usage.
4. Format `## Dependencies & tags` from pre-extracted data.
5. Format `## Properties` table from PROPERTIES above.
6. Format `## Main functions` from FUNCTIONS above. Deduplicate by name (prefer longer description). Use standard ### heading format.
7. Format `## Events & listeners` from EVENTS above.

=== OUTPUT FORMAT ===

Start output with `---` (YAML frontmatter). No preamble, no commentary.

---
id: {comp_name}
title: {comp_title}
description:
tags: {tags_str}
sidebar_position: {sidebar_position}

last_updated: {today_date}
build_version: {version}
change_status: stable
category_type: {category_type}
source_hash: {source_hash}
system_scope: {presynthesis.system_scope}
---

# {comp_title}

> Based on game build **{version}** | Last updated: {today_date}

## Overview
[Write here]

## Usage example
[Write here]

## Dependencies & tags
**Components used:** [from dependencies above]
**Tags:** [from tags above — list all tag names]

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
[Format from PROPERTIES above]

## Main functions
[Format from FUNCTIONS above — deduplicate by name]

## Events & listeners
[Format from EVENTS above]

=== CRITICAL RULES ===
- Output ONLY valid Markdown starting with `---`.
- Do NOT invent APIs not present in the pre-extracted data.
- Do NOT omit any function or property.
- HEADING STYLE: Sentence case.
- MDX COMPATIBILITY: Wrap `<`, `>`, `<=`, `>=`, `{{`, `}}` in backticks.
- NO code fences around the output.
- NO filler text, greetings, or sign-offs.
- NEVER repeat the same line or bullet point more than once.
"""
```

- [ ] **Step 3: Commit**

```bash
git add chunked_prompt.py
git commit -m "feat: rewrite build_chunk_prompt to JSON output and build_merge_prompt to accept PreSynthesisResult"
```

---

## Chunk 3: `chunked_olm.py` — Checkpoint v2 + Pipeline Integration

**Files:**
- Modify: `chunked_olm.py`

---

### Task 6: Checkpoint v2 — `save_checkpoint()` và `load_checkpoint()`

- [ ] **Step 1: Update `save_checkpoint()` — thêm `"version": 2`**

Trong `chunked_olm.py`, tìm `save_checkpoint()`. Trong `json.dump({...})`, thêm `"version": 2` làm key đầu tiên:

```python
# Before:
json.dump({
    "comp_name": comp_name,
    ...
}, f, ensure_ascii=False)

# After:
json.dump({
    "version": 2,          # ← THÊM
    "comp_name": comp_name,
    "last_index": last_index,
    "chunk_results": {str(k): v for k, v in chunk_results.items()},
    "failed_indices": failed_indices or [],
}, f, ensure_ascii=False)
```

- [ ] **Step 2: Update `load_checkpoint()` — detect v1 và clear**

Sau dòng `state = json.load(f)`, thêm version check ngay trước khi parse fields:

```python
# Thêm sau `state = json.load(f)`:
version = state.get("version", 1)
if version == 1:
    print("  [CHECKPOINT] v1 checkpoint (text format) detected — clearing, restart from scratch")
    clear_checkpoint(comp_name)
    return None
```

- [ ] **Step 3: Verify bằng cách tạo fake v1 checkpoint và load**

```bash
# Tạo fake v1 checkpoint
python -c "
import json, os
os.makedirs('checkpoints', exist_ok=True)
with open('checkpoints/test_v1.json', 'w') as f:
    json.dump({'comp_name': 'test_v1', 'last_index': 2, 'chunk_results': {'1': 'some text'}, 'failed_indices': []}, f)
"

# Test load
python -c "
from chunked_olm import load_checkpoint
result = load_checkpoint('test_v1')
print('Result:', result)  # Expected: None (v1 cleared)
import os
print('File exists:', os.path.exists('checkpoints/test_v1.json'))  # Expected: False
"
```

Expected output:
```
  [CHECKPOINT] v1 checkpoint (text format) detected — clearing, restart from scratch
Result: None
File exists: False
```

---

### Task 7: `process_chunked_file()` — Wire In `pre_synthesize()`

Đây là bước thay đổi lớn nhất. Hiện tại sau retry loop, code quyết định hierarchical vs direct merge. Thay thế toàn bộ merge decision block bằng: gọi `pre_synthesize()`, block on malformed, gọi `build_merge_prompt(presynthesis, ...)` trực tiếp.

- [ ] **Step 1: Thêm import `pre_synthesize` vào đầu `chunked_olm.py`**

```python
from pre_synthesis import pre_synthesize
```

- [ ] **Step 2: Tìm đoạn `# ── MERGE ──` trong `process_chunked_file()`**

Đoạn này bắt đầu khoảng line 684:
```python
# ── MERGE ──
# Sắp xếp kết quả theo thứ tự chunk gốc
ordered_results = [chunk_results[i] for i in sorted(chunk_results.keys())]
...
total_merge_tokens = estimate_merge_tokens(ordered_results)
use_hierarchical = ...
```

- [ ] **Step 3: Thay thế toàn bộ `# ── MERGE ──` block**

Xóa từ `# ── MERGE ──` đến hết `if use_hierarchical: ... else: ...` block (đến dòng `result_filename = generate_merged_doc(...)`).

Thay bằng:

```python
    # ── PRE-SYNTHESIS ──
    presynthesis, malformed_json = pre_synthesize(chunk_results)

    if malformed_json:
        save_checkpoint(comp_name, chunk_results, total_chunks - 1, failed_indices=malformed_json)
        print(f"\n  [PRE-SYNTHESIS] {len(malformed_json)} chunk output JSON không hợp lệ: {malformed_json}")
        print(f"  [PRE-SYNTHESIS] Không thể merge. Retry các chunk trên rồi chạy lại.")
        return None

    print(f"  [PRE-SYNTHESIS] OK — {len(presynthesis.functions)} functions, "
          f"{len(presynthesis.tags)} tags, scope={presynthesis.system_scope}")

    # ── MERGE ──
    merge_prompt = build_merge_prompt(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        presynthesis=presynthesis,
        source_hash=source_hash,
        today_date=today_date,
        version=version,
        category_type=category_type,
        sidebar_position=sidebar_position,
        file_tree=file_tree,
        connected_section=connected_section,
        connected_content=connected_content,
    )
    result_filename = generate_merged_doc(
        prompt=merge_prompt,
        md_filepath=md_filepath,
        model_name=model_name,
        sleep_time=merge_sleep,
    )
```

Giữ nguyên đoạn sau `result_filename = ...` (warning append, clear checkpoint).

- [ ] **Step 4: Cập nhật `hierarchical_merge()` — loại bỏ broken call tới `build_merge_prompt()`**

`build_merge_prompt()` đã đổi signature: tham số `chunk_results: list[str]` và `input_label` không còn tồn tại. `hierarchical_merge()` không được gọi trong pipeline mới nhưng phải compile clean.

Trong `chunked_olm.py`, tìm trong `hierarchical_merge()` đoạn gọi `build_merge_prompt(chunk_results=..., input_label=...)` (khoảng line 395–408). Xóa toàn bộ block đó (từ `# Tầng 2: final merge` đến hết `if result: clear_merge_checkpoint(...)`) và thay bằng:

```python
    # NOTE: hierarchical_merge is disabled in the JSON pipeline.
    # build_merge_prompt() now requires PreSynthesisResult.
    # Use process_chunked_file() which calls pre_synthesize() first.
    raise NotImplementedError(
        "hierarchical_merge is disabled. Use process_chunked_file() instead."
    )
```

Verify:
```bash
python -c "from chunked_olm import hierarchical_merge; print('Import OK')"
```
Expected: `Import OK` (import thành công, không crash khi import).

- [ ] **Step 5: Smoke test — import check**

```bash
python -c "from chunked_olm import process_chunked_file; print('Import OK')"
```
Expected: `Import OK` (không crash).

- [ ] **Step 6: Commit**

```bash
git add chunked_olm.py
git commit -m "feat: integrate pre_synthesize into process_chunked_file, add checkpoint v2"
```

---

### Task 8: End-to-end Smoke Test

Chạy pipeline trên 1 file Lua ngắn thực tế để xác nhận toàn bộ chain hoạt động. Không cần file dài — cần đủ để trigger chunked pipeline.

- [ ] **Step 1: Tìm file Lua nhỏ phù hợp để test**

```bash
# Tìm file Lua trong dst-scripts có thể chunked (>200 lines)
python -c "
import os
from chunked import needs_chunking
from get_docs import safe_read_lua
base = './dst-scripts/components'
for f in sorted(os.listdir(base))[:20]:
    if f.endswith('.lua'):
        code = safe_read_lua(os.path.join(base, f))
        if code and needs_chunking(code):
            print(f, len(code.splitlines()), 'lines')
            break
"
```

- [ ] **Step 2: Chạy pipeline trên file đó**

```bash
python chunked_test.py
```

Kiểm tra output:
- `[Chunk X/N]` lines xuất hiện (LLM đang xử lý)
- `[PRE-SYNTHESIS] OK —` line xuất hiện sau khi chunks xong
- `[Merge]` line xuất hiện
- File `.md` được tạo

- [ ] **Step 3: Inspect output file**

Mở file `.md` vừa tạo, kiểm tra:
- YAML frontmatter có `tags:`, `system_scope:` được fill đúng (không trống)
- `## Properties` có table rows
- `## Main functions` có content
- Không có JSON raw text lọt vào output

- [ ] **Step 4: Commit final**

```bash
git add .
git commit -m "test: verify pre-synthesis pipeline end-to-end with real Lua file"
```

---

## Summary: Files Changed

| File | Thay đổi |
|------|----------|
| `pre_synthesis.py` | **Tạo mới** — `PreSynthesisResult`, `pre_synthesize()`, helpers |
| `test_pre_synthesis.py` | **Tạo mới** — unit tests cho pre_synthesis module |
| `chunked_prompt.py` | Rewrite `build_chunk_prompt()` → JSON output; rewrite `build_merge_prompt()` → nhận `PreSynthesisResult` |
| `chunked_olm.py` | `save_checkpoint()` thêm version=2; `load_checkpoint()` detect v1; `process_chunked_file()` wire in pre_synthesize |

`hierarchical_merge()`, `rolling_merge_to_one()`, `build_intermediate_merge_prompt()` — **giữ nguyên**, không gọi trong pipeline mới.
