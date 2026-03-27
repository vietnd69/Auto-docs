# Multi-turn Validator with Convergence Guard

**Date**: 2026-03-27
**Status**: Approved
**Problem**: Chunked content validation loop oscillates infinitely — reviewer and writer contradict each other across iterations because of single-shot prompts (no memory), contradictory reviewer rules, and Qwen3.5's tendency to over-correct.

---

## Root Cause

Three factors combine to create the infinite loop:

1. **No conversation memory** — `review_section()` and `write_section_patches()` build fresh single-shot prompts each iteration. The writer doesn't know what it already fixed; the reviewer doesn't know what it already flagged.
2. **Contradictory reviewer rules** — "EXACTLY these labels" vs "no hallucinated content" causes oscillation: writer adds content → reviewer flags hallucination → writer deletes → reviewer flags "section empty" → repeat.
3. **Qwen3.5 over-correction** — writer nukes entire sections instead of surgical edits. Extended thinking (`think=True`) wastes tokens and encourages "creative" fixes.

## Solution Overview

Replace single-shot calls with multi-turn conversations using `system`/`user`/`assistant` roles, add convergence detection via issue fingerprinting, and use Ollama's `format` parameter to force structured JSON output.

---

## 1. `ollama_chat` New Parameters

**File**: `llm/src/llm/client.py`

Current line 104 hardcodes `think=True`. Change to accept caller-controlled parameters:

```python
def ollama_chat(model: str, messages: list[dict], *, think: bool = True,
                temperature: float | None = None, format: dict | str | None = None,
                **kwargs) -> dict:
```

- `think` — passed to `client.chat(think=...)`. Default `True` (current behavior). Writer calls will pass `think=False`.
- `temperature` — injected into `options` dict. `None` = model default.
- `format` — passed to `client.chat(format=...)`. Accepts `"json"` or a JSON schema dict. When set, the model is forced to output valid JSON matching the schema.

Both the no-API-key path (line 83) and the failover path (line 104) must forward these parameters.

## 2. JSON Schemas for Forced Structured Output

**File**: `validator/src/validator/content/schemas.py` (new)

Two schemas used with Ollama's `format` parameter:

```python
REVIEW_SCHEMA = {
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

PATCHES_SCHEMA = {
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

With `format=REVIEW_SCHEMA`, `parse_review_response()` no longer needs to strip markdown fences or `<think>` blocks. Same simplification for `parse_writer_response()`.

## 3. Multi-turn Reviewer Conversation

**File**: `validator/src/validator/content/prompts.py` + `validator/src/validator/content/chunked.py`

### Prompt Structure Change

`build_section_reviewer_prompt()` currently returns a single string. Refactor to return `(system_prompt, user_content)` tuple:

- **`system` role**: All rules (reviewer skill, quality rules, function format, section requirements). This is the "hard rules" channel — Qwen3.5 follows `system` role instructions more reliably than `user` role.
- **`user` role**: Section text + Lua context (the content to review).

### Conversation Accumulation

In `chunked.py`, maintain a `reviewer_messages: list[dict]` per batch:

```
Iteration 1:
  [system: rules]
  [user: "Section:\n{text}\n\nLua context:\n{lua}"]

Iteration 2:
  [system: rules]                          # same
  [user: "Section:\n{text}\n\nLua context:\n{lua}"]   # from iter 1
  [assistant: {prior review JSON}]         # iter 1 response (prefill)
  [user: "Section after fixes:\n{patched_text}"]       # new content
```

Lua context is only included in the first `user` message. Subsequent messages only carry the updated section text, saving tokens.

## 4. Multi-turn Writer Conversation

**File**: `validator/src/validator/content/prompts.py` + `validator/src/validator/content/chunked.py`

Same refactor: `build_section_writer_prompt()` returns `(system_prompt, user_content)`.

- **`system` role**: Writer skill, format rules, explicit instruction: "Do NOT undo previous patches. Only fix the new issues."
- **`user` role**: Section text + feedback + Lua context.

Conversation accumulation:

```
Iteration 2:
  [system: rules + "Do NOT undo previous patches"]
  [user: "Section:\n{text}\nFeedback:\n{issues}\nLua:\n{lua}"]  # iter 1
  [assistant: {prior patches JSON}]                              # iter 1 response
  [user: "Updated section:\n{patched}\nNew feedback:\n{issues2}"]  # iter 2
```

Writer calls use `think=False` and low `temperature` (0.3) for deterministic, minimal patches.

## 5. Convergence Guard (Issue Fingerprinting)

**File**: `validator/src/validator/content/chunked.py`

After each review, fingerprint the issue set:

```python
def _fingerprint_issues(issues: list[str]) -> set[str]:
    """Normalize and hash each issue for comparison."""
    return {issue.strip().lower() for issue in issues}
```

Track `prev_fingerprint` across iterations. If overlap with current fingerprint exceeds threshold (default 50%), the loop is oscillating → stop early and accept the current state.

```python
overlap = len(current & previous) / max(len(current), 1)
if overlap >= oscillation_threshold:
    print("  [convergence] Oscillation detected, stopping")
    break
```

## 6. Memory Compaction Between Sections

Each section starts with a fresh `reviewer_messages` and `writer_messages` — no cross-section contamination. Within a section, the conversation accumulates turns subject to two compaction triggers:

1. **Token-based** (primary): Before each iteration, count tokens of all non-system messages using `count_tokens()`. If total exceeds `conversation_token_budget` (default 3000), compact by keeping only the system message + the latest 2 non-system messages.

2. **Turn-count** (fallback): If `count_tokens()` returns `-1` (tiktoken unavailable), fall back to turn-count cap (`max_conversation_turns`, default 6). Old middle turns are dropped, keeping system + latest 2 non-system.

```python
def _compact_messages(messages: list[dict], max_turns: int, token_budget: int) -> list[dict]:
    system_msgs = [m for m in messages if m["role"] == "system"]
    non_system = [m for m in messages if m["role"] != "system"]
    if len(non_system) <= 2:
        return messages
    # Token-based check (primary)
    total = count_tokens("\n".join(m["content"] for m in non_system))
    if total != -1 and total <= token_budget:
        # Under budget — still apply turn-count fallback
        if len(non_system) <= max_turns:
            return messages
    elif total == -1 and len(non_system) <= max_turns:
        # No tiktoken — use turn count only
        return messages
    return system_msgs + non_system[-2:]
```

This prevents token bloat while preserving the most recent context that matters.

## 7. New Settings

**File**: `config.toml` + `llm/src/llm/settings.py`

```toml
[validator]
# ... existing settings ...
reviewer_temperature       = 0.4
writer_temperature         = 0.3
writer_think               = 0       # 0 = False, 1 = True
max_conversation_turns     = 6
conversation_token_budget  = 3000    # compact when non-system messages exceed this
oscillation_threshold      = 50      # percent overlap to detect oscillation
```

Settings loaded via `_get()` with `int` defaults (no `bool` — per the gotcha in CLAUDE.md).

## 8. Files to Modify

| File | Change |
|------|--------|
| `llm/src/llm/client.py` | Add `think`, `temperature`, `format` params to `ollama_chat()` |
| `llm/src/llm/settings.py` | Add 6 new validator settings |
| `config.toml` | Add new `[validator]` keys |
| `validator/src/validator/content/schemas.py` | **New file** — `REVIEW_SCHEMA`, `PATCHES_SCHEMA` |
| `validator/src/validator/content/prompts.py` | Refactor `build_section_reviewer_prompt()` and `build_section_writer_prompt()` to return `(system, user)` tuples |
| `validator/src/validator/content/reviewer.py` | Simplify `parse_review_response()` (no fence/think stripping when `format` is used) |
| `validator/src/validator/content/writer.py` | Simplify `parse_writer_response()` (same reason) |
| `validator/src/validator/content/chunked.py` | Multi-turn conversation loop, convergence guard, memory compaction |

## 9. What Does NOT Change

- `validator/src/validator/content/loop.py` — Standard (non-chunked) path is unaffected
- `validator/src/validator/content/sections.py` — Section splitting logic is unchanged
- `validator/src/validator/format/` — Format validation is unaffected
- `skills/*.md` — Skill files are not modified (but may be refined later based on results)
- `core/` — Document generation pipeline is unaffected

## 10. Expected Behavior After Fix

1. **No more oscillation** — convergence guard detects and breaks the loop
2. **Writer remembers prior patches** — multi-turn conversation prevents regression
3. **Reviewer has context of prior reviews** — doesn't re-flag fixed issues
4. **Structured JSON output** — no more parsing failures from markdown fences or `<think>` blocks
5. **Faster iterations** — `think=False` for writer saves tokens and time
6. **Deterministic patches** — low temperature reduces "creative" fixes
