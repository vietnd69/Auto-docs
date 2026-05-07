# Response Validation Guards Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3-layer validation guards to all structured LLM calls so bad/runaway responses never contaminate multi-turn conversation context.

**Architecture:** New `guards.py` provides `is_runaway`, `validate_*_schema`, and `compact_bad_response`. The retry loops in `reviewer.py`, `writer.py`, and `jury.py` are refactored to run these guards between layers (runaway → json.loads → schema), appending `assistant(compact_bad)+user(correction)` turns on failure instead of blindly repeating the same messages. `raw_response` is only set on fully valid results.

**Tech Stack:** Python 3.11, pytest, no new runtime dependencies.

---

## Chunk 1: guards.py

### Task 1: Create `validator/src/validator/content/guards.py`

**Files:**
- Create: `validator/src/validator/content/guards.py`
- Create: `validator/tests/test_guards.py`

- [ ] **Step 1: Write failing tests for `is_runaway`**

```python
# validator/tests/test_guards.py
from validator.content.guards import is_runaway, validate_review_schema, validate_patches_schema, validate_jury_schema, compact_bad_response


def test_is_runaway_short_response():
    assert is_runaway("small response") is False


def test_is_runaway_non_repetitive():
    raw = "\n".join(f"Line {i}: unique content here" for i in range(50))
    assert is_runaway(raw) is False


def test_is_runaway_detects_repeated_lines():
    line = "| onenter (frozen) |  |  |"
    raw = "\n".join([line] * 20 + ["other line"] * 5)
    assert is_runaway(raw) is True


def test_is_runaway_threshold():
    # 7 repeats → not runaway, 8 → runaway
    line = "| some repeated table row |  |  |"
    padding = "\n".join(f"unique line {i}" for i in range(20))
    raw_7 = padding + "\n" + "\n".join([line] * 7)
    raw_8 = padding + "\n" + "\n".join([line] * 8)
    assert is_runaway(raw_7) is False
    assert is_runaway(raw_8) is True


def test_is_runaway_ignores_short_lines():
    # Short lines (≤10 chars) not counted
    raw = "\n".join(["ok"] * 50 + [f"unique {i}" for i in range(20)])
    assert is_runaway(raw) is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```
.venv/Scripts/pytest validator/tests/test_guards.py -v
```
Expected: `ModuleNotFoundError` or `ImportError` (file doesn't exist yet).

- [ ] **Step 3: Write failing tests for schema validators**

```python
# append to validator/tests/test_guards.py

def test_validate_review_schema_valid():
    data = {"approved": True, "findings": []}
    assert validate_review_schema(data) is True


def test_validate_review_schema_with_findings():
    data = {"approved": False, "findings": [{"issue": "x", "suggestion": "y"}]}
    assert validate_review_schema(data) is True


def test_validate_review_schema_missing_approved():
    assert validate_review_schema({"findings": []}) is False


def test_validate_review_schema_wrong_approved_type():
    assert validate_review_schema({"approved": "true", "findings": []}) is False


def test_validate_review_schema_missing_findings():
    assert validate_review_schema({"approved": True}) is False


def test_validate_review_schema_finding_missing_field():
    data = {"approved": False, "findings": [{"issue": "x"}]}  # missing suggestion
    assert validate_review_schema(data) is False


def test_validate_patches_schema_valid():
    data = [{"old_text": "a", "new_text": "b", "reason": "r"}]
    assert validate_patches_schema(data) is True


def test_validate_patches_schema_empty_list():
    assert validate_patches_schema([]) is True


def test_validate_patches_schema_not_list():
    assert validate_patches_schema({"old_text": "a"}) is False


def test_validate_patches_schema_missing_field():
    data = [{"old_text": "a", "new_text": "b"}]  # missing reason
    assert validate_patches_schema(data) is False


def test_validate_jury_schema_yes():
    assert validate_jury_schema({"vote": "yes", "reason": "r"}) is True


def test_validate_jury_schema_no():
    assert validate_jury_schema({"vote": "no", "reason": "r"}) is True


def test_validate_jury_schema_invalid_vote():
    assert validate_jury_schema({"vote": "maybe", "reason": "r"}) is False


def test_validate_jury_schema_missing_reason():
    assert validate_jury_schema({"vote": "yes"}) is False
```

- [ ] **Step 4: Write failing tests for `compact_bad_response`**

```python
# append to validator/tests/test_guards.py

def test_compact_short_response_unchanged():
    raw = "short"
    assert compact_bad_response(raw, max_chars=500) == raw


def test_compact_runaway_response():
    line = "| onenter (frozen) |  |  |"
    raw = "\n".join([line] * 30 + [f"unique {i}" for i in range(20)])
    result = compact_bad_response(raw, max_chars=500)
    assert "runaway" in result.lower()
    assert "30" in result  # repeat count


def test_compact_large_non_runaway():
    raw = " ".join(f"word{i}" for i in range(1000))  # large but not repetitive
    result = compact_bad_response(raw, max_chars=100)
    assert len(result) < len(raw)
    assert "TRUNCATED" in result
```

- [ ] **Step 5: Implement `guards.py`**

```python
# validator/src/validator/content/guards.py
"""Response validation guards for LLM structured outputs."""


def is_runaway(raw: str) -> bool:
    """Detect repetitive/looping LLM output (e.g. repeated markdown table rows).

    Returns True if any non-trivial line repeats >=8 times in a sufficiently
    large response. Checked before json.loads to catch format-enforcement failures.
    """
    if len(raw) < 3000:
        return False
    lines = [l.strip() for l in raw.splitlines() if l.strip() and len(l.strip()) > 10]
    if len(lines) < 20:
        return False
    counts: dict[str, int] = {}
    for line in lines:
        counts[line] = counts.get(line, 0) + 1
    return max(counts.values(), default=0) >= 8


def validate_review_schema(data: object) -> bool:
    """Validate parsed JSON against REVIEW_SCHEMA structure.

    Required: approved (bool), findings (list of {issue: str, suggestion: str}).
    """
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("approved"), bool):
        return False
    findings = data.get("findings")
    if not isinstance(findings, list):
        return False
    for f in findings:
        if not isinstance(f, dict):
            return False
        if not isinstance(f.get("issue"), str) or not isinstance(f.get("suggestion"), str):
            return False
    return True


def validate_patches_schema(data: object) -> bool:
    """Validate parsed JSON against PATCHES_SCHEMA structure.

    Required: list of {old_text: str, new_text: str, reason: str}.
    """
    if not isinstance(data, list):
        return False
    for p in data:
        if not isinstance(p, dict):
            return False
        for key in ("old_text", "new_text", "reason"):
            if not isinstance(p.get(key), str):
                return False
    return True


def validate_jury_schema(data: object) -> bool:
    """Validate parsed JSON against JURY_VOTE_SCHEMA structure.

    Required: vote in {"yes", "no"}, reason (str).
    """
    if not isinstance(data, dict):
        return False
    if data.get("vote") not in ("yes", "no"):
        return False
    if not isinstance(data.get("reason"), str):
        return False
    return True


def compact_bad_response(raw: str, max_chars: int = 500) -> str:
    """Compact a large/bad LLM response for safe injection as assistant turn in retry.

    For runaway responses: summarizes the repeated pattern.
    For other large responses: truncates with size prefix.
    Always much smaller than the original, preventing prompt bloat on retry.
    """
    if len(raw) <= max_chars:
        return raw

    lines = [l.strip() for l in raw.splitlines() if l.strip() and len(l.strip()) > 10]
    if lines:
        counts: dict[str, int] = {}
        for line in lines:
            counts[line] = counts.get(line, 0) + 1
        max_count = max(counts.values(), default=0)
        if max_count >= 8:
            most_repeated = max(counts, key=lambda k: counts[k])
            return (
                f"[RESPONSE TRUNCATED — {len(raw):,} chars / {len(lines):,} lines — runaway detected]\n"
                f"Most repeated line ({max_count}×): {most_repeated[:100]!r}\n"
                f"First 200 chars: {raw[:200]!r}"
            )

    return f"[RESPONSE TRUNCATED — {len(raw):,} chars]\n{raw[:max_chars]}..."
```

- [ ] **Step 6: Run tests to confirm they pass**

```
.venv/Scripts/pytest validator/tests/test_guards.py -v
```
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```
git add validator/src/validator/content/guards.py validator/tests/test_guards.py
git commit -m "feat(validator): add response validation guards module"
```

---

## Chunk 2: reviewer.py

### Task 2: Refactor retry loop in `reviewer.py`

**Files:**
- Modify: `validator/src/validator/content/reviewer.py`
- Modify: `validator/tests/test_content_reviewer.py`

The changes target two functions: `review_document()` and `reviewer_oscillation_correction()`.

**Correction message constants** (add near top of file, after imports):

```python
_GUARD_RUNAWAY = (
    "[BAD RESPONSE GUARD] Your previous response contained repeated non-JSON content "
    "and could not be used.\n"
    "You MUST respond with a single valid JSON object matching the schema:\n"
    '{"approved": <bool>, "findings": [{"issue": "<str>", "suggestion": "<str>"}]}\n'
    "Do NOT generate markdown tables, repeated rows, or any text outside the JSON object."
)
_GUARD_PARSE = (
    "[BAD RESPONSE GUARD] Your previous response could not be parsed as JSON.\n"
    'Respond ONLY with a valid JSON object: {"approved": <bool>, "findings": [...]}'
)
_GUARD_SCHEMA = (
    "[BAD RESPONSE GUARD] Your JSON response is missing required fields.\n"
    "Required: 'approved' (boolean) and 'findings' (array of objects with "
    "'issue' (string) and 'suggestion' (string)).\n"
    "Respond with a correctly structured JSON object."
)
_GUARD_INVARIANT = (
    "[BAD RESPONSE GUARD] Invalid state: 'approved' is false but 'findings' is empty.\n"
    "If there are content issues, list them in 'findings'. "
    "If the document is correct, set 'approved' to true."
)
```

- [ ] **Step 1: Write failing tests for guarded reviewer behavior**

```python
# append to validator/tests/test_content_reviewer.py
import json
from validator.content.reviewer import ReviewResult, parse_review_response, parse_review_json


def test_parse_review_json_valid():
    data = {"approved": False, "findings": [{"issue": "x", "suggestion": "y"}]}
    result = parse_review_json(data)
    assert result.approved is False
    assert result.issues == ["x"]
    assert result.suggestions == ["y"]


def test_raw_response_not_set_on_bad_parse():
    """raw_response must be empty on unparseable responses."""
    result = parse_review_response("not json at all")
    assert result.raw_response == ""


def test_raw_response_not_set_on_empty():
    result = parse_review_response("")
    assert result.raw_response == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```
.venv/Scripts/pytest validator/tests/test_content_reviewer.py::test_raw_response_not_set_on_bad_parse validator/tests/test_content_reviewer.py::test_raw_response_not_set_on_empty -v
```
Expected: FAIL — `raw_response` is currently always set inside `review_document`, not `parse_review_response`.

- [ ] **Step 3: Refactor `review_document()` in `reviewer.py`**

Replace the existing retry loop in `review_document()` (lines ~186–205) with the guarded version. Add imports at top of file:

```python
from validator.content.guards import is_runaway, validate_review_schema, compact_bad_response
```

Replace the `result`/loop block:

```python
    result = ReviewResult(approved=False, issues=["No response"], suggestions=[])
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages, format=REVIEW_SCHEMA)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("reviewer_response", raw)
        remaining = BAD_RESPONSE_RETRIES - attempt

        # Layer 1: runaway detection (before JSON parse)
        if is_runaway(raw):
            print(f"  [content/reviewer] Runaway response ({len(raw):,} chars) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_RUNAWAY})
            continue

        # Layer 2: JSON parse
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            print(f"  [content/reviewer] Bad response (JSON parse) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_PARSE})
            continue

        # Layer 3: schema validation
        if not validate_review_schema(data):
            print(f"  [content/reviewer] Bad response (schema) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_SCHEMA})
            continue

        # Parse validated data
        result = parse_review_json(data)

        # Invariant: approved=false requires non-empty findings
        if not result.approved and not result.issues:
            print(f"  [content/reviewer] INVARIANT violation → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_INVARIANT})
            continue

        # All layers passed — safe to store raw_response
        result.raw_response = raw
        return result

    return result  # exhausted retries; raw_response="" prevents context contamination
```

Apply the same guard pattern to `reviewer_oscillation_correction()` — same 4-layer structure with `_GUARD_*` messages.

- [ ] **Step 4: Run tests**

```
.venv/Scripts/pytest validator/tests/test_content_reviewer.py -v
```
Expected: all tests PASS. Fix any breaks from the refactor.

- [ ] **Step 5: Commit**

```
git add validator/src/validator/content/reviewer.py validator/tests/test_content_reviewer.py
git commit -m "feat(validator): add 3-layer guards + raw_response isolation to reviewer retry loop"
```

---

## Chunk 3: writer.py

### Task 3: Add guards to `rewrite_document()` in `writer.py`

**Files:**
- Modify: `validator/src/validator/content/writer.py`
- Modify: `validator/tests/test_content_writer.py`

**Correction message constants** (add near top of `writer.py`, after imports):

```python
_GUARD_RUNAWAY = (
    "[BAD RESPONSE GUARD] Your previous response contained repeated non-JSON content.\n"
    "You MUST respond with a JSON array of patch objects:\n"
    '[{"old_text": "<str>", "new_text": "<str>", "reason": "<str>"}]\n'
    "Do NOT generate repeated text or markdown outside the JSON array."
)
_GUARD_PARSE = (
    "[BAD RESPONSE GUARD] Your previous response could not be parsed as JSON.\n"
    'Respond ONLY with a JSON array: [{"old_text": "...", "new_text": "...", "reason": "..."}]'
)
_GUARD_SCHEMA = (
    "[BAD RESPONSE GUARD] Your JSON response has incorrect structure.\n"
    "Required: a JSON array where each item has 'old_text', 'new_text', and 'reason' (all strings)."
)
```

- [ ] **Step 1: Write failing tests**

```python
# append to validator/tests/test_content_writer.py
from validator.content.writer import parse_writer_response


def test_parse_writer_response_valid():
    raw = json.dumps([{"old_text": "a", "new_text": "b", "reason": "r"}])
    patches = parse_writer_response(raw)
    assert len(patches) == 1
    assert patches[0].old_text == "a"


def test_parse_writer_response_runaway_returns_empty():
    """Runaway response: repeated lines → should return empty patches list."""
    line = "| onenter (frozen) |  |  |"
    raw = "\n".join([line] * 30 + [f"unique {i}" for i in range(25)])
    patches = parse_writer_response(raw)
    assert patches == []
```

- [ ] **Step 2: Run tests to confirm behavior**

```
.venv/Scripts/pytest validator/tests/test_content_writer.py -v
```

- [ ] **Step 3: Add imports and guard to `rewrite_document()` in `writer.py`**

Add imports:
```python
from validator.content.guards import is_runaway, validate_patches_schema, compact_bad_response
```

Replace the retry loop in `rewrite_document()` (lines ~275–293):

```python
    raw = ""
    patches: list[Patch] = []
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages, format=PATCHES_SCHEMA, think=bool(WRITER_THINK))
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("writer_response", raw)
        remaining = BAD_RESPONSE_RETRIES - attempt

        # Layer 1: runaway detection
        if is_runaway(raw):
            print(f"  [content/writer] Runaway response ({len(raw):,} chars) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_RUNAWAY})
            raw = ""  # don't propagate bad raw as context
            continue

        # Layer 2: JSON parse
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = _strip_thinking(cleaned)
        # Fallback: find array in text (existing behavior)
        start, end = cleaned.find('['), cleaned.rfind(']')
        try:
            data = json.loads(cleaned) if cleaned.startswith('[') else json.loads(cleaned[start:end + 1]) if start != -1 and end > start else None
            if data is None:
                raise json.JSONDecodeError("no array", "", 0)
        except (json.JSONDecodeError, TypeError):
            print(f"  [content/writer] Bad response (JSON parse) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_PARSE})
            raw = ""
            continue

        # Layer 3: schema validation
        if not validate_patches_schema(data):
            print(f"  [content/writer] Bad response (schema) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_SCHEMA})
            raw = ""
            continue

        patches = _parse_patch_list(data)
        if patches:
            break

        # Valid JSON array but no actionable patches
        if remaining > 0:
            print(f"  [content/writer] No patches parsed → retrying ({remaining} left)")
        else:
            print(f"  [content/writer] No patches after {BAD_RESPONSE_RETRIES + 1} attempts — raw: {raw[:120]!r}")

    if patches:
        print(f"  [content/writer] {len(patches)} patch(es) generated")
    return patches, raw, user_content
```

**Note:** `raw = ""` on guard failures ensures `inner_prev_raw = ""` in `loop.py`, which prevents the `and inner_prev_raw` condition from building multi-turn context with bad data.

- [ ] **Step 4: Run tests**

```
.venv/Scripts/pytest validator/tests/test_content_writer.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add validator/src/validator/content/writer.py validator/tests/test_content_writer.py
git commit -m "feat(validator): add runaway + schema guards to writer retry loop"
```

---

## Chunk 4: jury.py

### Task 4: Add guards to `_vote_once()` in `jury.py`

**Files:**
- Modify: `validator/src/validator/content/jury.py`

Jury votes are stateless (5 independent calls, no cross-vote context), so contamination risk is lower. Still add guards for consistency and robustness. No `raw_response` field on `JuryVerdict` — no isolation issue here.

- [ ] **Step 1: Add imports and refactor `_vote_once()`**

Add imports:
```python
from validator.content.guards import is_runaway, validate_jury_schema, compact_bad_response
```

Replace the body of `_vote_once()`:

```python
def _vote_once(messages: list[dict], model: str, vote_index: int = 0) -> tuple[bool, str]:
    """Call one LLM jury member. Returns (vote_yes, reason)."""
    msgs = list(messages)  # local copy for multi-turn correction
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        try:
            response = ollama_chat(model=model, messages=msgs, temperature=JURY_TEMPERATURE, format=JURY_VOTE_SCHEMA)
        except Exception as e:
            if attempt < BAD_RESPONSE_RETRIES:
                time.sleep(2)
                continue
            return False, f"API error: {e}"
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt(f"jury_response_v{vote_index}", raw)
        remaining = BAD_RESPONSE_RETRIES - attempt

        # Layer 1: runaway
        if is_runaway(raw):
            if remaining > 0:
                msgs.append({"role": "assistant", "content": compact_bad_response(raw)})
                msgs.append({"role": "user", "content": (
                    "[BAD RESPONSE GUARD] Respond ONLY with a JSON object: "
                    '{"vote": "yes" or "no", "reason": "<string>"}'
                )})
                time.sleep(2)
            continue

        # Layer 2: JSON parse
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            if remaining > 0:
                msgs.append({"role": "assistant", "content": compact_bad_response(raw)})
                msgs.append({"role": "user", "content": (
                    "[BAD RESPONSE GUARD] Invalid JSON. Respond ONLY with: "
                    '{"vote": "yes" or "no", "reason": "<string>"}'
                )})
                time.sleep(2)
            continue

        # Layer 3: schema validation
        if not validate_jury_schema(data):
            if remaining > 0:
                msgs.append({"role": "assistant", "content": compact_bad_response(raw)})
                msgs.append({"role": "user", "content": (
                    "[BAD RESPONSE GUARD] Missing required fields. "
                    'Respond with: {"vote": "yes" or "no", "reason": "<string>"}'
                )})
                time.sleep(2)
            continue

        vote = str(data.get("vote", "no")).lower().strip()
        reason = str(data.get("reason", ""))
        return vote == "yes", reason

    return False, "Failed to parse jury response after all attempts"
```

- [ ] **Step 2: Run full validator test suite**

```
.venv/Scripts/pytest validator/tests/ -v
```
Expected: all PASS. No regressions.

- [ ] **Step 3: Commit**

```
git add validator/src/validator/content/jury.py
git commit -m "feat(validator): add runaway + schema guards to jury vote retry"
```

---

## Chunk 5: Smoke Test

### Task 5: Verify end-to-end with existing test files

- [ ] **Step 1: Run full test suite**

```
.venv/Scripts/pytest validator/tests/ -v --tb=short
```
Expected: all existing tests pass + new guard tests pass.

- [ ] **Step 2: Manual smoke check with debug mode**

```
MOD_DOC_DEBUG_PROMPTS=1 .venv/Scripts/python -m validator dst-api-webdocs/docs/stategraphs/SGwx78_possessedbody.md --content-only
```

Verify in output:
- No `[content/reviewer] Bad response → retrying` without a guard prefix (old blind retry)
- Guards produce `[content/reviewer] Runaway response` / `Bad response (JSON parse)` / `Bad response (schema)` messages when triggered

- [ ] **Step 3: Final commit (if any cleanup needed)**

```
git add -p
git commit -m "test(validator): verify guard integration end-to-end"
```
