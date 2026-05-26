# Multi-turn Validator with Convergence Guard — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the infinite oscillation loop in chunked content validation by adding multi-turn LLM conversations, convergence detection, and forced structured JSON output.

**Architecture:** Replace single-shot reviewer/writer prompts with multi-turn conversations using `system`/`user`/`assistant` roles. Add convergence guard via issue fingerprinting. Use Ollama's `format` parameter to force valid JSON output, eliminating parse failures.

**Tech Stack:** Python 3.11, Ollama Cloud API (`ollama` library), `uv` workspace

**Spec:** [2026-03-27-multi-turn-validator-design.md](../specs/2026-03-27-multi-turn-validator-design.md)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `llm/src/llm/client.py` | Modify | Add `think`, `temperature`, `format` params to `ollama_chat()` |
| `llm/src/llm/settings.py` | Modify | Add 6 new validator settings |
| `config.toml` | Modify | Add new `[validator]` keys |
| `validator/src/validator/content/schemas.py` | Create | `REVIEW_SCHEMA`, `PATCHES_SCHEMA` JSON schema dicts |
| `validator/src/validator/content/prompts.py` | Modify | Split `build_section_*_prompt()` → return `(system, user)` tuples |
| `validator/src/validator/content/reviewer.py` | Modify | Add `parse_review_json()` for pre-parsed JSON (when `format` used) |
| `validator/src/validator/content/writer.py` | Modify | Add `parse_writer_json()` for pre-parsed JSON |
| `validator/src/validator/content/chunked.py` | Modify | Multi-turn conversation, convergence guard, memory compaction |
| `llm/tests/test_client.py` | Modify | Tests for new `ollama_chat` params |
| `validator/tests/test_schemas.py` | Create | Schema structure tests |
| `validator/tests/test_content_reviewer.py` | Modify | Tests for `parse_review_json()` |
| `validator/tests/test_content_writer.py` | Modify | Tests for `parse_writer_json()` |
| `validator/tests/test_content_chunked.py` | Modify | Tests for convergence guard + multi-turn |

**Files NOT touched:** `loop.py`, `sections.py`, `format/`, `skills/*.md`, `core/`

---

## Chunk 1: Foundation Layer (client.py, settings, schemas)

### Task 1: Add new parameters to `ollama_chat()`

**Files:**
- Modify: `llm/src/llm/client.py:75-131`
- Test: `llm/tests/test_client.py`

- [ ] **Step 1: Write failing tests for new parameters**

Add to `llm/tests/test_client.py`:

```python
from unittest.mock import patch, MagicMock


def test_ollama_chat_forwards_think_false():
    """think=False should be forwarded to client.chat()."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "ok"}}
    with patch("llm.client._make_client", return_value=mock_client), \
         patch("llm.client.OLLAMA_API_KEYS", ["key1"]):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}], think=False)
    mock_client.chat.assert_called_once()
    call_kwargs = mock_client.chat.call_args
    assert call_kwargs.kwargs.get("think") is False or call_kwargs[1].get("think") is False


def test_ollama_chat_forwards_temperature():
    """temperature should be injected into options dict."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "ok"}}
    with patch("llm.client._make_client", return_value=mock_client), \
         patch("llm.client.OLLAMA_API_KEYS", ["key1"]):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}], temperature=0.3)
    call_kwargs = mock_client.chat.call_args
    opts = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options", {})
    assert opts.get("temperature") == 0.3


def test_ollama_chat_forwards_format_schema():
    """format dict should be forwarded to client.chat()."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "{}"}}
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    with patch("llm.client._make_client", return_value=mock_client), \
         patch("llm.client.OLLAMA_API_KEYS", ["key1"]):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}], format=schema)
    call_kwargs = mock_client.chat.call_args
    assert call_kwargs.kwargs.get("format") == schema or call_kwargs[1].get("format") == schema


def test_ollama_chat_defaults_think_true():
    """Default behavior: think=True when not specified."""
    mock_client = MagicMock()
    mock_client.chat.return_value = {"message": {"content": "ok"}}
    with patch("llm.client._make_client", return_value=mock_client), \
         patch("llm.client.OLLAMA_API_KEYS", ["key1"]):
        from llm.client import ollama_chat
        ollama_chat(model="test", messages=[{"role": "user", "content": "hi"}])
    call_kwargs = mock_client.chat.call_args
    assert call_kwargs.kwargs.get("think") is True or call_kwargs[1].get("think") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest llm/tests/test_client.py -v -k "forwards_think or forwards_temperature or forwards_format or defaults_think"`
Expected: FAIL — current `ollama_chat` doesn't accept these keyword args

- [ ] **Step 3: Implement new parameters in `ollama_chat()`**

In `llm/src/llm/client.py`, change the function signature and both call sites:

```python
def ollama_chat(model: str, messages: list[dict], *, think: bool = True,
                temperature: float | None = None,
                format: dict | str | None = None,
                **kwargs) -> dict:
    """
    Wrapper for ollama chat with automatic failover on rate limit,
    and retry on timeout.
    """
    global _account_counter
    if not OLLAMA_API_KEYS:
        client = ollama.Client()
        chat_kwargs: dict = dict(model=model, messages=messages, think=think, stream=False)
        if format is not None:
            chat_kwargs["format"] = format
        return client.chat(**chat_kwargs, **kwargs)

    opts = kwargs.pop("options", {}) or {}
    opts["num_ctx"] = OLLAMA_NUM_CTX
    if temperature is not None:
        opts["temperature"] = temperature

    # Build chat kwargs once
    chat_extra: dict = {}
    if format is not None:
        chat_extra["format"] = format

    n = len(OLLAMA_API_KEYS)
    errors: list[str] = []

    for timeout_attempt in range(OLLAMA_TIMEOUT_RETRIES + 1):
        for attempt in range(n):
            idx = (_account_counter + attempt) % n
            if idx in _rate_limited:
                errors.append(f"Account {idx + 1}: rate limited")
                continue
            try:
                client = _make_client(idx)
                response = client.chat(
                    model=model, messages=messages, options=opts,
                    think=think, stream=False, **chat_extra, **kwargs
                )
                _account_counter = idx + 1
                return response
            except Exception as e:
                # ... existing error handling unchanged ...
```

The key changes:
1. `think` is now a keyword-only parameter with default `True` (backward compatible)
2. `temperature` is injected into `opts` dict when provided
3. `format` is forwarded as a separate kwarg to `client.chat()` when not `None`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest llm/tests/test_client.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add llm/src/llm/client.py llm/tests/test_client.py
git commit -m "feat(client): add think, temperature, format params to ollama_chat()"
```

---

### Task 2: Add new settings to config

**Files:**
- Modify: `llm/src/llm/settings.py:53-62`
- Modify: `config.toml:25-34`
- Test: `llm/tests/test_settings.py`

- [ ] **Step 1: Write failing test for new settings**

Add to `llm/tests/test_settings.py`:

```python
def test_validator_reviewer_temperature():
    from llm.settings import REVIEWER_TEMPERATURE
    assert isinstance(REVIEWER_TEMPERATURE, float)
    assert 0.0 <= REVIEWER_TEMPERATURE <= 2.0


def test_validator_writer_temperature():
    from llm.settings import WRITER_TEMPERATURE
    assert isinstance(WRITER_TEMPERATURE, float)
    assert 0.0 <= WRITER_TEMPERATURE <= 2.0


def test_validator_writer_think():
    from llm.settings import WRITER_THINK
    assert isinstance(WRITER_THINK, int)
    assert WRITER_THINK in (0, 1)


def test_validator_max_conversation_turns():
    from llm.settings import MAX_CONVERSATION_TURNS
    assert isinstance(MAX_CONVERSATION_TURNS, int)
    assert MAX_CONVERSATION_TURNS >= 2


def test_validator_conversation_token_budget():
    from llm.settings import CONVERSATION_TOKEN_BUDGET
    assert isinstance(CONVERSATION_TOKEN_BUDGET, int)
    assert CONVERSATION_TOKEN_BUDGET >= 500


def test_validator_oscillation_threshold():
    from llm.settings import OSCILLATION_THRESHOLD
    assert isinstance(OSCILLATION_THRESHOLD, int)
    assert 0 <= OSCILLATION_THRESHOLD <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest llm/tests/test_settings.py -v -k "reviewer_temperature or writer_temperature or writer_think or max_conversation or conversation_token_budget or oscillation"`
Expected: FAIL — `ImportError: cannot import name 'REVIEWER_TEMPERATURE'`

- [ ] **Step 3: Add settings to `settings.py` and `config.toml`**

Append to `llm/src/llm/settings.py` after line 62 (`BAD_RESPONSE_RETRIES`):

```python
REVIEWER_TEMPERATURE: float       = _get("validator", "reviewer_temperature",    0.4)
WRITER_TEMPERATURE: float         = _get("validator", "writer_temperature",       0.3)
WRITER_THINK: int                 = _get("validator", "writer_think",             0)
MAX_CONVERSATION_TURNS: int       = _get("validator", "max_conversation_turns",   6)
CONVERSATION_TOKEN_BUDGET: int    = _get("validator", "conversation_token_budget", 3000)
OSCILLATION_THRESHOLD: int        = _get("validator", "oscillation_threshold",    50)
```

Append to `config.toml` `[validator]` section:

```toml
reviewer_temperature       = 0.4
writer_temperature         = 0.3
writer_think               = 0
max_conversation_turns     = 6
conversation_token_budget  = 3000
oscillation_threshold      = 50
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest llm/tests/test_settings.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add llm/src/llm/settings.py config.toml llm/tests/test_settings.py
git commit -m "feat(settings): add validator temperature, think, conversation, oscillation settings"
```

---

### Task 3: Create JSON schemas

**Files:**
- Create: `validator/src/validator/content/schemas.py`
- Create: `validator/tests/test_schemas.py`

- [ ] **Step 1: Write failing test for schemas**

Create `validator/tests/test_schemas.py`:

```python
"""Tests for JSON schemas used with Ollama format parameter."""

import json
import jsonschema  # may need: uv add jsonschema --dev
import pytest


def test_review_schema_importable():
    from validator.content.schemas import REVIEW_SCHEMA
    assert isinstance(REVIEW_SCHEMA, dict)
    assert REVIEW_SCHEMA["type"] == "object"


def test_patches_schema_importable():
    from validator.content.schemas import PATCHES_SCHEMA
    assert isinstance(PATCHES_SCHEMA, dict)
    assert PATCHES_SCHEMA["type"] == "array"


def test_review_schema_validates_approved():
    from validator.content.schemas import REVIEW_SCHEMA
    valid = {"approved": True, "findings": []}
    jsonschema.validate(valid, REVIEW_SCHEMA)


def test_review_schema_validates_findings():
    from validator.content.schemas import REVIEW_SCHEMA
    valid = {
        "approved": False,
        "findings": [
            {"issue": "Wrong param", "suggestion": "Fix it"},
        ],
    }
    jsonschema.validate(valid, REVIEW_SCHEMA)


def test_review_schema_rejects_missing_approved():
    from validator.content.schemas import REVIEW_SCHEMA
    invalid = {"findings": []}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, REVIEW_SCHEMA)


def test_patches_schema_validates_patch_list():
    from validator.content.schemas import PATCHES_SCHEMA
    valid = [
        {"old_text": "foo", "new_text": "bar", "reason": "fix"},
    ]
    jsonschema.validate(valid, PATCHES_SCHEMA)


def test_patches_schema_validates_empty_list():
    from validator.content.schemas import PATCHES_SCHEMA
    jsonschema.validate([], PATCHES_SCHEMA)


def test_patches_schema_rejects_missing_old_text():
    from validator.content.schemas import PATCHES_SCHEMA
    invalid = [{"new_text": "bar", "reason": "fix"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, PATCHES_SCHEMA)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validator.content.schemas'`

Note: If `jsonschema` is not installed, run `uv add jsonschema --dev` in the validator package first. If adding a dev dependency is not desired, the tests can use `json.loads` + manual assertion instead of `jsonschema.validate`.

- [ ] **Step 3: Create `schemas.py`**

Create `validator/src/validator/content/schemas.py`:

```python
"""JSON schemas for Ollama structured output (format parameter)."""

REVIEW_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["issue", "suggestion"],
            },
        },
    },
    "required": ["approved", "findings"],
}

PATCHES_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["old_text", "new_text", "reason"],
    },
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_schemas.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/schemas.py validator/tests/test_schemas.py
git commit -m "feat(validator): add JSON schemas for reviewer and writer structured output"
```

---

## Chunk 2: Prompt & Parser Refactoring

### Task 4: Refactor `build_section_reviewer_prompt()` to return `(system, user)` tuple

**Files:**
- Modify: `validator/src/validator/content/prompts.py:136-197`
- Test: `validator/tests/test_content_chunked.py` (existing prompt tests)

- [ ] **Step 1: Write failing test for new return type**

Add to `validator/tests/test_content_chunked.py`:

```python
def test_section_reviewer_prompt_returns_tuple():
    """build_section_reviewer_prompt should return (system, user) tuple."""
    result = build_section_reviewer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n", "function Foo(x) end"
    )
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2
    system_prompt, user_content = result
    assert isinstance(system_prompt, str)
    assert isinstance(user_content, str)
    # System should contain rules, user should contain section + lua
    assert "reviewer" in system_prompt.lower() or "review" in system_prompt.lower()
    assert "Foo" in user_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest validator/tests/test_content_chunked.py::test_section_reviewer_prompt_returns_tuple -v`
Expected: FAIL — currently returns `str`, not `tuple`

- [ ] **Step 3: Refactor `build_section_reviewer_prompt()`**

In `validator/src/validator/content/prompts.py`, replace the function (lines 136-197):

```python
def build_section_reviewer_prompt(
    section_text: str,
    lua_context: str,
    section_heading: str = "",
    file_type: str = "component",
) -> tuple[str, str]:
    """Prompt for reviewing one markdown section against its focused Lua context.

    Returns (system_prompt, user_content) for multi-turn conversation.
    """
    section_ctx = _section_context(section_heading)
    is_main_fns = section_heading == "## Main functions"
    fn_format_block = (
        f"\n=== FUNCTION FORMAT REFERENCE ===\n{_FN_FORMAT}\n"
    ) if is_main_fns else ""

    file_desc = (
        "component with Class() constructor and self.inst"
        if file_type == "component"
        else "data config — returns a plain table/array, no Class() constructor"
    )

    system_prompt = f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API docs.

=== TARGET ===
File type: {file_type} ({file_desc})
Section:   {section_heading or "(preamble)"}

=== REVIEW RULES ===
{section_ctx}{_REVIEWER_SKILL}

=== QUALITY RULES ===
{_QUALITY_RULES}
{fn_format_block}
=== RESPONSE FORMAT ===
Respond in JSON only with keys "approved" (boolean) and "findings" (array of objects with "issue" and "suggestion").
approved=true with empty findings if accurate. approved=false with paired issue+suggestion for each problem."""

    if lua_context:
        lua_block = f"```lua\n{lua_context}\n```"
        lua_instruction = "Review the section against the Lua functions below."
    else:
        lua_block = "(none — no Lua functions referenced in this section)"
        lua_instruction = (
            "No Lua context available — review structural accuracy "
            "and internal consistency only."
        )

    user_content = f"""{lua_instruction}

=== LUA CONTEXT (ground truth) ===
{lua_block}

=== SECTION TO REVIEW ===
{section_text}"""

    return system_prompt, user_content
```

- [ ] **Step 4: Update existing tests that depend on old return type**

The two existing tests `test_section_reviewer_prompt_contains_format_contract` and `test_section_writer_prompt_contains_format_rules` currently call `build_section_reviewer_prompt()` and expect a `str`. Update them:

```python
def test_section_reviewer_prompt_contains_format_contract():
    system, user = build_section_reviewer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n", ""
    )
    combined = system + user
    assert "FORMAT CONTRACT" in combined or "REVIEW RULES" in combined
    assert "* **Description:**" in user
```

- [ ] **Step 5: Update `review_section()` in `chunked.py` to use tuple**

In `validator/src/validator/content/chunked.py`, update `review_section()` (lines 73-102):

```python
def review_section(
    section_text: str,
    lua_context: str,
    model: str,
    section_heading: str = "",
    file_type: str = "component",
) -> ReviewResult:
    """Send one markdown section to the reviewer LLM. Retries on bad/empty response."""
    system_prompt, user_content = build_section_reviewer_prompt(
        section_text, lua_context, section_heading, file_type
    )
    prompt_text = system_prompt + "\n" + user_content  # for token counting/debug
    print(f"  [content/chunked] Reviewer prompt: {count_tokens(prompt_text):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_reviewer", prompt_text)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    result = ReviewResult(approved=False, issues=["No response"], suggestions=[])
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_reviewer_response", raw)
        result = parse_review_response(raw)
        if not _is_bad_review(raw, result):
            return result
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/chunked] Bad reviewer response → retrying ({remaining} left)")
        else:
            print(f"  [content/chunked] Bad reviewer response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")
    return result
```

- [ ] **Step 6: Run all tests to verify nothing broke**

Run: `uv run pytest validator/tests/test_content_chunked.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add validator/src/validator/content/prompts.py validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "refactor(prompts): split section reviewer prompt into (system, user) tuple"
```

---

### Task 5: Refactor `build_section_writer_prompt()` to return `(system, user)` tuple

**Files:**
- Modify: `validator/src/validator/content/prompts.py:200-253`
- Test: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing test**

```python
def test_section_writer_prompt_returns_tuple():
    """build_section_writer_prompt should return (system, user) tuple."""
    result = build_section_writer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n",
        "function Foo(x) end",
        ["Wrong description"],
        ["Fix the description"],
    )
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2
    system_prompt, user_content = result
    assert "writer" in system_prompt.lower() or "patch" in system_prompt.lower()
    assert "Wrong description" in user_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest validator/tests/test_content_chunked.py::test_section_writer_prompt_returns_tuple -v`
Expected: FAIL

- [ ] **Step 3: Refactor `build_section_writer_prompt()`**

```python
def build_section_writer_prompt(
    section_text: str,
    lua_context: str,
    issues: list[str],
    suggestions: list[str],
    section_heading: str = "",
    file_type: str = "component",
) -> tuple[str, str]:
    """Prompt for patching one markdown section based on review feedback.

    Returns (system_prompt, user_content) for multi-turn conversation.
    """
    system_prompt = f"""You are a documentation writer for Don't Starve Together (DST) Lua API docs.
Your task: fix the section using Lua source as ground truth. Return targeted patches only.
Do NOT undo previous patches. Only fix the new issues listed in the feedback.

=== TARGET ===
Section: {section_heading or "(preamble)"}

=== FORMAT RULES ===
{_WRITER_SKILL}

=== RESPONSE FORMAT ===
Return a JSON array of patches. Each patch has "old_text", "new_text", "reason".
old_text must be an EXACT substring of the section. Keep patches minimal."""

    feedback_lines = []
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback_lines.append(f"{i}. Issue: {issue}")
        if suggestion:
            feedback_lines.append(f"   Suggestion: {suggestion}")
    feedback = "\n".join(feedback_lines)

    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"

    user_content = f"""=== LUA CONTEXT (ground truth) ===
{lua_block}

=== CURRENT SECTION ===
{section_text}

=== REVIEWER FEEDBACK ===
{feedback}"""

    return system_prompt, user_content
```

- [ ] **Step 4: Update existing test and `write_section_patches()` in `chunked.py`**

Update `test_section_writer_prompt_contains_format_rules`:

```python
def test_section_writer_prompt_contains_format_rules():
    system, user = build_section_writer_prompt(
        "## Functions\n### `Foo(x)`\n* **Description:** x\n", "", [], []
    )
    combined = system + user
    assert "FORMAT RULES" in combined
    assert "NEVER" in combined or "Do NOT" in combined
```

Update `write_section_patches()` in `chunked.py` (lines 105-141):

```python
def write_section_patches(
    section_text: str,
    lua_context: str,
    review: ReviewResult,
    model: str,
    section_heading: str = "",
    file_type: str = "component",
) -> list[Patch]:
    """Ask the writer LLM to patch one section based on review feedback. Retries on empty response."""
    system_prompt, user_content = build_section_writer_prompt(
        section_text, lua_context, review.issues, review.suggestions,
        section_heading, file_type
    )
    prompt_text = system_prompt + "\n" + user_content
    print(f"  [content/chunked] Writer prompt: {count_tokens(prompt_text):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer", prompt_text)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    raw = ""
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages)
        raw = response["message"]["content"]
        if raw.strip():
            break
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/chunked] Empty writer response → retrying ({remaining} left)")
        else:
            print(f"  [content/chunked] Empty writer response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")

    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer_response", raw)
    patches = parse_writer_response(raw)
    if not patches:
        print("  [content/chunked] Writer returned no patches")
    else:
        print(f"  [content/chunked] {len(patches)} patch(es) generated")
    return patches
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest validator/tests/test_content_chunked.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add validator/src/validator/content/prompts.py validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "refactor(prompts): split section writer prompt into (system, user) tuple"
```

---

### Task 6: Add `parse_review_json()` and `parse_writer_json()` for structured output

**Files:**
- Modify: `validator/src/validator/content/reviewer.py`
- Modify: `validator/src/validator/content/writer.py`
- Test: `validator/tests/test_content_reviewer.py`
- Test: `validator/tests/test_content_writer.py`

These new parsers handle the case when Ollama's `format` parameter guarantees valid JSON — no need to strip markdown fences or `<think>` blocks.

- [ ] **Step 1: Write failing tests for `parse_review_json()`**

Add to `validator/tests/test_content_reviewer.py`:

```python
def test_parse_review_json_approved():
    from validator.content.reviewer import parse_review_json
    data = {"approved": True, "findings": []}
    result = parse_review_json(data)
    assert result.approved is True
    assert result.issues == []


def test_parse_review_json_with_findings():
    from validator.content.reviewer import parse_review_json
    data = {
        "approved": False,
        "findings": [
            {"issue": "Wrong param", "suggestion": "Fix it"},
            {"issue": "Missing return", "suggestion": "Add return docs"},
        ],
    }
    result = parse_review_json(data)
    assert result.approved is False
    assert len(result.issues) == 2
    assert result.issues[0] == "Wrong param"
    assert result.suggestions[1] == "Add return docs"


def test_parse_review_json_empty_findings():
    from validator.content.reviewer import parse_review_json
    data = {"approved": False, "findings": []}
    result = parse_review_json(data)
    assert result.approved is False
    assert result.issues == []
```

- [ ] **Step 2: Write failing tests for `parse_writer_json()`**

Add to `validator/tests/test_content_writer.py`:

```python
def test_parse_writer_json_valid():
    from validator.content.writer import parse_writer_json
    data = [
        {"old_text": "foo", "new_text": "bar", "reason": "fix"},
    ]
    patches = parse_writer_json(data)
    assert len(patches) == 1
    assert patches[0].old_text == "foo"


def test_parse_writer_json_empty():
    from validator.content.writer import parse_writer_json
    patches = parse_writer_json([])
    assert patches == []


def test_parse_writer_json_skips_empty_old_text():
    from validator.content.writer import parse_writer_json
    data = [
        {"old_text": "", "new_text": "bar", "reason": "empty"},
        {"old_text": "valid", "new_text": "ok", "reason": "good"},
    ]
    patches = parse_writer_json(data)
    assert len(patches) == 1
    assert patches[0].old_text == "valid"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_reviewer.py -v -k "parse_review_json" && uv run pytest validator/tests/test_content_writer.py -v -k "parse_writer_json"`
Expected: FAIL — functions don't exist yet

- [ ] **Step 4: Implement `parse_review_json()` and `parse_writer_json()`**

Add to `validator/src/validator/content/reviewer.py`:

```python
def parse_review_json(data: dict) -> ReviewResult:
    """Parse pre-validated JSON dict (from Ollama format parameter) into ReviewResult."""
    approved = bool(data.get("approved", False))
    findings = data.get("findings") or []
    issues = [str(f.get("issue", "")) for f in findings if isinstance(f, dict)]
    suggestions = [str(f.get("suggestion", "")) for f in findings if isinstance(f, dict)]
    return ReviewResult(approved=approved, issues=issues, suggestions=suggestions)
```

Add to `validator/src/validator/content/writer.py`:

```python
def parse_writer_json(data: list) -> list[Patch]:
    """Parse pre-validated JSON list (from Ollama format parameter) into Patch list."""
    if not isinstance(data, list):
        return []
    return [
        Patch(
            old_text=str(item.get("old_text", "")),
            new_text=str(item.get("new_text", "")),
            reason=str(item.get("reason", "")),
        )
        for item in data
        if isinstance(item, dict) and item.get("old_text")
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_reviewer.py validator/tests/test_content_writer.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add validator/src/validator/content/reviewer.py validator/src/validator/content/writer.py validator/tests/test_content_reviewer.py validator/tests/test_content_writer.py
git commit -m "feat(validator): add parse_review_json and parse_writer_json for structured output"
```

---

## Chunk 3: Multi-turn Conversation Loop & Convergence Guard

### Task 7: Add convergence guard helper

**Files:**
- Modify: `validator/src/validator/content/chunked.py`
- Test: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing test for `_fingerprint_issues()`**

Add to `validator/tests/test_content_chunked.py`:

```python
def test_fingerprint_issues_normalizes():
    from validator.content.chunked import _fingerprint_issues
    issues = ["  Wrong Param  ", "wrong param", "Missing return"]
    fp = _fingerprint_issues(issues)
    # "Wrong Param" and "wrong param" should deduplicate after lowering/stripping
    assert len(fp) == 2
    assert "wrong param" in fp
    assert "missing return" in fp


def test_fingerprint_issues_empty():
    from validator.content.chunked import _fingerprint_issues
    fp = _fingerprint_issues([])
    assert fp == set()


def test_oscillation_detected():
    """When overlap exceeds threshold, oscillation should be detected."""
    from validator.content.chunked import _fingerprint_issues
    prev = _fingerprint_issues(["issue a", "issue b", "issue c"])
    curr = _fingerprint_issues(["issue a", "issue b", "issue d"])
    overlap = len(curr & prev) / max(len(curr), 1)
    # 2 out of 3 overlap = 66.7% > 50% default threshold
    assert overlap > 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_chunked.py -v -k "fingerprint or oscillation"`
Expected: FAIL — `_fingerprint_issues` doesn't exist

- [ ] **Step 3: Implement `_fingerprint_issues()`**

Add to `validator/src/validator/content/chunked.py` (near top, after imports):

```python
def _fingerprint_issues(issues: list[str]) -> set[str]:
    """Normalize and deduplicate issues for convergence comparison."""
    return {issue.strip().lower() for issue in issues if issue.strip()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_chunked.py -v -k "fingerprint or oscillation"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(validator): add issue fingerprinting for convergence detection"
```

---

### Task 8: Add `_compact_messages()` helper for memory management

**Files:**
- Modify: `validator/src/validator/content/chunked.py`
- Test: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing test**

```python
def test_compact_messages_under_budget():
    """Messages under token budget and turn limit should not be compacted."""
    from validator.content.chunked import _compact_messages
    msgs = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "section1"},
        {"role": "assistant", "content": "review1"},
        {"role": "user", "content": "section2"},
    ]
    # token_budget high enough that short messages won't trigger compaction
    result = _compact_messages(msgs, max_turns=6, token_budget=3000)
    assert len(result) == 4  # unchanged


def test_compact_messages_over_token_budget():
    """Messages exceeding token budget should compact to system + last 2 non-system."""
    from validator.content.chunked import _compact_messages
    msgs = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "word " * 600},       # ~600 tokens
        {"role": "assistant", "content": "word " * 600},   # ~600 tokens
        {"role": "user", "content": "word " * 600},        # ~600 tokens
        {"role": "assistant", "content": "word " * 600},   # ~600 tokens
        {"role": "user", "content": "latest"},
        {"role": "assistant", "content": "latest_resp"},
    ]
    # token_budget=500 forces compaction (non-system total >> 500)
    result = _compact_messages(msgs, max_turns=10, token_budget=500)
    assert result[0]["role"] == "system"
    # Should keep system + last 2 non-system
    assert len(result) == 3
    assert result[-1]["content"] == "latest_resp"
    assert result[-2]["content"] == "latest"


def test_compact_messages_over_turn_limit():
    """When tiktoken unavailable (returns -1), fall back to turn count."""
    from validator.content.chunked import _compact_messages
    msgs = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "old1"},
        {"role": "assistant", "content": "resp1"},
        {"role": "user", "content": "old2"},
        {"role": "assistant", "content": "resp2"},
        {"role": "user", "content": "latest1"},
        {"role": "assistant", "content": "latest_resp"},
        {"role": "user", "content": "latest2"},
    ]
    result = _compact_messages(msgs, max_turns=4, token_budget=3000)
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "rules"
    assert result[-1]["content"] == "latest2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_chunked.py -v -k "compact_messages"`
Expected: FAIL

- [ ] **Step 3: Implement `_compact_messages()`**

```python
def _compact_messages(messages: list[dict], max_turns: int, token_budget: int) -> list[dict]:
    """Compact conversation history when it exceeds token budget or turn limit.

    Primary trigger: token count of non-system messages > token_budget.
    Fallback trigger: turn count > max_turns (used when tiktoken unavailable).
    When compacting, keeps system message + last 2 non-system messages.
    """
    if not messages:
        return messages
    system_msgs = [m for m in messages if m["role"] == "system"]
    non_system = [m for m in messages if m["role"] != "system"]
    if len(non_system) <= 2:
        return messages
    # Primary: token-based compaction
    total = count_tokens("\n".join(m["content"] for m in non_system))
    if total != -1:
        if total <= token_budget and len(non_system) <= max_turns:
            return messages  # under both limits
    else:
        # tiktoken unavailable — fall back to turn count only
        if len(non_system) <= max_turns:
            return messages
    return system_msgs + non_system[-2:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_chunked.py -v -k "compact_messages"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(validator): add message compaction for multi-turn conversation"
```

---

### Task 9: Rewrite the inner loop in `run_chunked_content_loop()` with multi-turn + convergence + format

This is the main integration task. It rewires the inner review→write loop to:
1. Use multi-turn conversations (accumulate `assistant` prefills)
2. Pass `format` schemas for structured JSON output
3. Pass `think`/`temperature` settings
4. Detect oscillation via fingerprinting
5. Compact messages when they exceed turn cap

**Files:**
- Modify: `validator/src/validator/content/chunked.py:73-142` (review_section, write_section_patches) and lines 144-394 (main loop)
- Test: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing test for convergence guard integration**

```python
def test_oscillation_breaks_loop(tmp_path):
    """When reviewer returns same issues repeatedly, the loop should stop early."""
    md_content = "---\ntitle: T\n---\n## Functions\n`Alpha()` docs.\n"
    lua_content = "function Alpha() return 1 end\n"
    md, lua = _write_fixtures(tmp_path, md_content, lua_content)

    # Reviewer always rejects with same issues, writer always patches
    call_count = 0
    def _oscillating(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        # Odd calls: reviewer rejects with same issue
        if call_count % 2 == 1:
            return _rejected(["Same issue every time"])
        # Even calls: writer patches
        return _patches("`Alpha()` docs.", "`Alpha()` fixed docs.")

    with patch("validator.content.chunked.ollama_chat", side_effect=_oscillating):
        result = run_chunked_content_loop(md, lua, _config(max_iterations=10))

    # Should NOT run all 10 iterations — convergence guard should stop it early
    assert result.iterations < 10
```

- [ ] **Step 2: Run test to verify it fails (or runs all iterations)**

Run: `uv run pytest validator/tests/test_content_chunked.py::test_oscillation_breaks_loop -v`
Expected: FAIL — current code has no convergence detection, runs all iterations

- [ ] **Step 3: Rewrite `review_section()` to support multi-turn**

Replace `review_section()` in `chunked.py`. The new version accepts an optional `messages` parameter for conversation continuation:

```python
from llm.settings import (
    BAD_RESPONSE_RETRIES, BATCH_TOKEN_LIMIT, DEBUG_PROMPTS,
    SECTION_LUA_CONTEXT_TOKENS, SECTION_TOKEN_THRESHOLD,
    VALIDATOR_CALL_SLEEP,
    REVIEWER_TEMPERATURE, WRITER_TEMPERATURE, WRITER_THINK,
    MAX_CONVERSATION_TURNS, CONVERSATION_TOKEN_BUDGET, OSCILLATION_THRESHOLD,
)
from validator.content.schemas import REVIEW_SCHEMA, PATCHES_SCHEMA
from validator.content.reviewer import ReviewResult, parse_review_response, parse_review_json
from validator.content.writer import Patch, apply_patches, parse_writer_response, parse_writer_json
import json


def review_section(
    section_text: str,
    lua_context: str,
    model: str,
    section_heading: str = "",
    file_type: str = "component",
    *,
    messages: list[dict] | None = None,
) -> tuple[ReviewResult, list[dict]]:
    """Send one markdown section to the reviewer LLM.

    If `messages` is provided, appends a new user turn with updated section text
    (multi-turn continuation). Otherwise builds a fresh conversation.

    Returns (ReviewResult, updated_messages) so caller can accumulate turns.
    """
    system_prompt, user_content = build_section_reviewer_prompt(
        section_text, lua_context, section_heading, file_type
    )

    if messages is None:
        # First iteration: fresh conversation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    else:
        # Subsequent iteration: only send updated section (lua already in first user msg)
        messages.append({"role": "user", "content": f"Section after fixes:\n{section_text}"})
        messages = _compact_messages(messages, MAX_CONVERSATION_TURNS, CONVERSATION_TOKEN_BUDGET)

    prompt_text = "\n".join(m["content"] for m in messages)
    print(f"  [content/chunked] Reviewer prompt: {count_tokens(prompt_text):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_reviewer", prompt_text)

    result = ReviewResult(approved=False, issues=["No response"], suggestions=[])
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(
            model=model, messages=messages,
            temperature=REVIEWER_TEMPERATURE,
            format=REVIEW_SCHEMA,
        )
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_reviewer_response", raw)
        try:
            data = json.loads(raw)
            result = parse_review_json(data)
        except (json.JSONDecodeError, TypeError):
            result = parse_review_response(raw)  # fallback
        if not _is_bad_review(raw, result):
            # Add assistant response to conversation for next iteration
            messages.append({"role": "assistant", "content": raw})
            return result, messages
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/chunked] Bad reviewer response → retrying ({remaining} left)")
        else:
            print(f"  [content/chunked] Bad reviewer response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")
    return result, messages
```

- [ ] **Step 4: Rewrite `write_section_patches()` to support multi-turn**

```python
def write_section_patches(
    section_text: str,
    lua_context: str,
    review: ReviewResult,
    model: str,
    section_heading: str = "",
    file_type: str = "component",
    *,
    messages: list[dict] | None = None,
) -> tuple[list[Patch], list[dict]]:
    """Ask the writer LLM to patch one section based on review feedback.

    Returns (patches, updated_messages) so caller can accumulate turns.
    """
    system_prompt, user_content = build_section_writer_prompt(
        section_text, lua_context, review.issues, review.suggestions,
        section_heading, file_type
    )

    if messages is None:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    else:
        # Build follow-up user turn with updated section + new feedback
        feedback_lines = []
        for i, issue in enumerate(review.issues, 1):
            suggestion = review.suggestions[i - 1] if i - 1 < len(review.suggestions) else ""
            feedback_lines.append(f"{i}. Issue: {issue}")
            if suggestion:
                feedback_lines.append(f"   Suggestion: {suggestion}")
        feedback = "\n".join(feedback_lines)
        follow_up = f"Updated section:\n{section_text}\n\nNew feedback:\n{feedback}"
        messages.append({"role": "user", "content": follow_up})
        messages = _compact_messages(messages, MAX_CONVERSATION_TURNS, CONVERSATION_TOKEN_BUDGET)

    prompt_text = "\n".join(m["content"] for m in messages)
    print(f"  [content/chunked] Writer prompt: {count_tokens(prompt_text):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer", prompt_text)

    writer_think = bool(WRITER_THINK)

    raw = ""
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(
            model=model, messages=messages,
            think=writer_think,
            temperature=WRITER_TEMPERATURE,
            format=PATCHES_SCHEMA,
        )
        raw = response["message"]["content"]
        if raw.strip():
            break
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/chunked] Empty writer response → retrying ({remaining} left)")
        else:
            print(f"  [content/chunked] Empty writer response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")

    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer_response", raw)
    try:
        data = json.loads(raw)
        patches = parse_writer_json(data)
    except (json.JSONDecodeError, TypeError):
        patches = parse_writer_response(raw)  # fallback
    if not patches:
        print("  [content/chunked] Writer returned no patches")
    else:
        print(f"  [content/chunked] {len(patches)} patch(es) generated")
        # Add assistant response to conversation for next iteration
        messages.append({"role": "assistant", "content": raw})
    return patches, messages
```

- [ ] **Step 5: Rewrite the inner loops in `run_chunked_content_loop()`**

The main changes to the loop body in `run_chunked_content_loop()`:

1. Initialize `reviewer_msgs = None` and `writer_msgs = None` per batch/section (fresh conversation per section — memory compaction).
2. Track `prev_fingerprint: set[str] = set()` per batch/section for convergence.
3. Pass `messages=reviewer_msgs` to `review_section()` and capture `reviewer_msgs` from return.
4. Pass `messages=writer_msgs` to `write_section_patches()` and capture `writer_msgs` from return.
5. After each review, check fingerprint overlap against `OSCILLATION_THRESHOLD`.

The small-section path (line 293 onward) and the large-section/batch path (line 190 onward) both need these changes. The pattern is identical for both.

For the **small-section inner loop** (currently lines 321-380), replace:

```python
            section_approved = False
            last_review: ReviewResult | None = None
            reviewer_msgs: list[dict] | None = None
            writer_msgs: list[dict] | None = None
            prev_fingerprint: set[str] = set()

            for i in range(config.max_iterations):
                if config.stop_check():
                    return ContentLoopResult(
                        approved=False,
                        iterations=total_iterations,
                        final_issues=["Interrupted by user"],
                    )

                total_iterations += 1
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    f"reviewing... (iter {i + 1}/{config.max_iterations})"
                )
                last_review, reviewer_msgs = review_section(
                    section.text, lua_ctx, config.reviewer_model,
                    section.heading, file_type,
                    messages=reviewer_msgs,
                )
                _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)

                if last_review.approved:
                    section_approved = True
                    print(
                        f"  [content/chunked] Section {idx}/{len(sections)} — "
                        f"approved at iteration {i + 1}"
                    )
                    break

                # Convergence guard
                current_fp = _fingerprint_issues(last_review.issues)
                if prev_fingerprint and current_fp:
                    overlap = len(current_fp & prev_fingerprint) / max(len(current_fp), 1)
                    if overlap >= OSCILLATION_THRESHOLD / 100:
                        print(
                            f"  [content/chunked] Section {idx}/{len(sections)} — "
                            f"oscillation detected ({overlap:.0%} overlap), stopping"
                        )
                        break
                prev_fingerprint = current_fp

                patches, writer_msgs = write_section_patches(
                    section.text, lua_ctx, last_review, config.writer_model,
                    section.heading, file_type,
                    messages=writer_msgs,
                )
                _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)
                if not patches:
                    print(
                        f"  [content/chunked] Section {idx}/{len(sections)} — "
                        "writer gave up, section stays failed"
                    )
                    break

                section.text, failed = apply_patches(section.text, patches)
                applied = len(patches) - failed
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    f"patches: {applied} applied, {failed} failed"
                )
                Path(md_filepath).write_text(
                    join_md_sections(frontmatter, sections), encoding="utf-8"
                )
```

Apply the same pattern to the **large-section batch inner loop** (currently lines 213-255): add `reviewer_msgs`, `writer_msgs`, `prev_fingerprint` per batch, and unpack the tuple returns.

- [ ] **Step 6: Run all tests**

Run: `uv run pytest validator/tests/test_content_chunked.py -v`
Expected: All PASS — including the new `test_oscillation_breaks_loop`

Note: Existing tests that mock `ollama_chat` will need their side effects updated because `review_section()` and `write_section_patches()` now return tuples. The mock responses remain the same format — the functions internally parse the response and return the additional `messages` list. Since the existing test mocks patch `validator.content.chunked.ollama_chat`, the internal return value handling should work transparently. However, verify that no test assertions break due to the changed return types of `review_section` and `write_section_patches` if they are called directly in tests.

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -v`
Expected: All PASS across all packages

- [ ] **Step 8: Commit**

```bash
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(validator): multi-turn conversation loop with convergence guard and structured output"
```

---

## Chunk 4: Integration Testing & Verification

### Task 10: End-to-end smoke test with DEBUG_PROMPTS

- [ ] **Step 1: Run the full test suite one more time**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 2: Verify the validator can run against a real file (optional, requires Ollama API)**

If API access is available:

```bash
MOD_DOC_DEBUG_PROMPTS=1 uv run python -m validator --content-only dst-api-webdocs/docs/prefabs/critters.md
```

Check `.cache/debug_prompts/` for:
- `chunked_reviewer_*.txt` — should show multi-turn messages (system + user + assistant + user...)
- `chunked_writer_*.txt` — should show `think=False` in behavior (no `<think>` blocks in response)
- `chunked_reviewer_response_*.txt` — should be clean JSON (no markdown fences)
- Console output should show `oscillation detected` if issues repeat

- [ ] **Step 3: Commit all remaining changes**

```bash
git add -A
git commit -m "feat(validator): complete multi-turn validator with convergence guard"
```

---

## Summary of Changes

| # | Task | Files | Key Change |
|---|------|-------|------------|
| 1 | `ollama_chat` params | `client.py` | `think`, `temperature`, `format` keyword args |
| 2 | New settings | `settings.py`, `config.toml` | 5 validator settings |
| 3 | JSON schemas | `schemas.py` (new) | `REVIEW_SCHEMA`, `PATCHES_SCHEMA` |
| 4 | Reviewer prompt tuple | `prompts.py`, `chunked.py` | `(system, user)` return |
| 5 | Writer prompt tuple | `prompts.py`, `chunked.py` | `(system, user)` return |
| 6 | JSON parsers | `reviewer.py`, `writer.py` | `parse_review_json()`, `parse_writer_json()` |
| 7 | Convergence guard | `chunked.py` | `_fingerprint_issues()` |
| 8 | Memory compaction | `chunked.py` | `_compact_messages()` |
| 9 | Multi-turn loop | `chunked.py` | Full loop rewrite |
| 10 | Verification | — | Test suite + smoke test |
