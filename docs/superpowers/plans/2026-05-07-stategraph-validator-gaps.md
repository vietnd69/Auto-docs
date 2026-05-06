# Stategraph Validator Gaps Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three validator gaps that caused stategraph `## Events & listeners` to ship as "Listens to: None", injected states to be missing from `## Properties`, and `## Action Handlers` to be completely invisible to the validator.

**Architecture:** Four targeted changes — (1) extend `extract_section_lua_context` in `sections.py` with stategraph-specific extraction patterns and three guard helpers; (2) add a deterministic events pre-correction guard in `chunked.py` before the LLM loop; (3) add `## Action Handlers` to `_RULE_IDS_BY_SECTION` in `prompts.py` and `_STRUCTURAL_HEADINGS` in `chunked.py`; (4) sharpen stategraph rules in `skills/roles/validator_reviewer.md`.

**Tech Stack:** Python 3.11, pytest, `re` module, existing `Finding`/`DocSection`/`apply_typed_ops` from `validator.content`, `ollama_chat` mock pattern from `test_content_chunked.py`.

**Spec:** `docs/superpowers/specs/2026-05-07-stategraph-validator-gaps-design.md`

---

## File map

| File | Change |
|---|---|
| `validator/src/validator/content/sections.py` | Add 3 helper functions; update `extract_section_lua_context` events/properties/action-handlers branches |
| `validator/src/validator/content/chunked.py` | Add `## Action Handlers` to `_STRUCTURAL_HEADINGS`; add events guard pre-pass in `run_chunked_content_loop` |
| `validator/src/validator/content/prompts.py` | Add `## Action Handlers` entry to `_RULE_IDS_BY_SECTION` |
| `skills/roles/validator_reviewer.md` | Add STATEGRAPH EVENTS RULE, INJECTED STATES RULE, ACTION HANDLERS SECTION RULE under `### Stategraph file checks` |
| `validator/tests/test_sections.py` | Tests for 3 helpers + 3 updated `extract_section_lua_context` branches |
| `validator/tests/test_content_chunked.py` | Tests for events guard behaviour in `run_chunked_content_loop` |

---

## Chunk 1: `sections.py` — helpers + all three context extraction fixes

### Task 1: Helper functions (`_is_stategraph`, `extract_stategraph_event_names`, `check_stategraph_events_null`)

**Files:**
- Modify: `validator/tests/test_sections.py`
- Modify: `validator/src/validator/content/sections.py`

- [ ] **Step 1: Write failing tests for the three helpers**

Append to `validator/tests/test_sections.py`:

```python
# ── stategraph helpers ──────────────────────────────────────────────────────

from validator.content.sections import (
    _is_stategraph,
    extract_stategraph_event_names,
    check_stategraph_events_null,
)

_SG_LUA = '''
local SPEED = 6
StateGraph("sg_test",
    states, events, "idle", actionhandlers)
events = {
    EventHandler("death", function(inst) end),
    EventHandler("freeze", function(inst) end),
}
'''

_COMP_LUA = '''
local MyComp = Class(function(self, inst) self.inst = inst end)
function MyComp:GetOwner() return self.inst end
'''


def test_is_stategraph_detects():
    assert _is_stategraph(_SG_LUA) is True


def test_is_stategraph_component():
    assert _is_stategraph(_COMP_LUA) is False


def test_is_stategraph_empty():
    assert _is_stategraph("") is False


def test_extract_stategraph_event_names_basic():
    assert extract_stategraph_event_names(_SG_LUA) == ["death", "freeze"]


def test_extract_stategraph_event_names_none():
    assert extract_stategraph_event_names(_COMP_LUA) == []


def test_check_events_null_listens_to_none():
    section = "## Events & listeners\n**Listens to:** None\n"
    assert check_stategraph_events_null(section, _SG_LUA) is True


def test_check_events_null_bold_none():
    section = "## Events & listeners\n**None.**\n"
    assert check_stategraph_events_null(section, _SG_LUA) is True


def test_check_events_null_has_content():
    section = "## Events & listeners\n**Listens to:** death, freeze\n"
    assert check_stategraph_events_null(section, _SG_LUA) is False


def test_check_events_null_not_stategraph():
    section = "## Events & listeners\n**Listens to:** None\n"
    assert check_stategraph_events_null(section, _COMP_LUA) is False


def test_check_events_null_no_eventhandlers():
    lua = "StateGraph('sg_empty', states, {}, 'idle', {})\n"
    section = "## Events & listeners\n**Listens to:** None\n"
    assert check_stategraph_events_null(section, lua) is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```
.venv/Scripts/pytest validator/tests/test_sections.py -k "stategraph" -v
```

Expected: `ImportError` (functions not yet defined)

- [ ] **Step 3: Implement the three helper functions in `sections.py`**

Add before `extract_section_lua_context` (around line 595):

```python
def _is_stategraph(lua_source: str) -> bool:
    """Return True if lua_source defines a StateGraph."""
    return bool(re.search(r'\bStateGraph\s*\(', lua_source))


def extract_stategraph_event_names(lua_source: str) -> list[str]:
    """Return event names from all EventHandler("name", fn) entries in lua_source."""
    return re.findall(r'EventHandler\s*\(\s*"([^"]+)"', lua_source)


def check_stategraph_events_null(section_text: str, lua_source: str) -> bool:
    """True if doc claims no events but source has EventHandler entries.

    Only applies to stategraph files. Guards against the pattern where the
    validator approves 'Listens to: None' despite N EventHandlers in source.
    Known limitation: does not detect all phrasings — 'None.' or '**None**'
    without period are not caught; the LLM loop with improved context handles those.
    """
    if not _is_stategraph(lua_source):
        return False
    if not extract_stategraph_event_names(lua_source):
        return False
    text_lower = section_text.lower()
    return (
        "listens to: none" in text_lower
        or ("**none.**" in text_lower and "eventhandler" not in text_lower)
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```
.venv/Scripts/pytest validator/tests/test_sections.py -k "stategraph" -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```
git add validator/tests/test_sections.py validator/src/validator/content/sections.py
git commit -m "feat(validator): add stategraph helper functions to sections.py"
```

---

### Task 2: Fix `extract_section_lua_context` — Events branch (add EventHandler pattern)

**Files:**
- Modify: `validator/tests/test_sections.py`
- Modify: `validator/src/validator/content/sections.py`

- [ ] **Step 1: Write failing tests for the Events extraction fix**

Append to `validator/tests/test_sections.py`:

```python
# ── extract_section_lua_context — Events branch ─────────────────────────────

from validator.content.sections import extract_section_lua_context

_STATEGRAPH_EVENTS_LUA = '''\
StateGraph("sg_test", states, events, "idle", {})
events = {
    EventHandler("death", function(inst)
        inst.sg:GoToState("death")
    end),
    EventHandler("freeze", function(inst)
        inst.sg:GoToState("frozen")
    end),
}
'''

_COMP_EVENTS_LUA = '''\
local MyComp = Class(function(self, inst)
    inst:ListenForEvent("onhit", function() self:OnHit() end)
    inst:PushEvent("ready", {data=1})
end)
'''

def test_events_context_includes_eventhandler():
    result = extract_section_lua_context("## Events & listeners", _STATEGRAPH_EVENTS_LUA, 8000)
    assert 'EventHandler("death"' in result
    assert 'EventHandler("freeze"' in result


def test_events_context_includes_listenforevent():
    """Regression: existing ListenForEvent pattern still captured."""
    result = extract_section_lua_context("## Events & listeners", _COMP_EVENTS_LUA, 8000)
    assert "ListenForEvent" in result


def test_events_context_includes_pushevent():
    """Regression: existing PushEvent pattern still captured."""
    result = extract_section_lua_context("## Events & listeners", _COMP_EVENTS_LUA, 8000)
    assert "PushEvent" in result


def test_events_context_empty_when_no_events():
    lua = "function DoThing(inst) return nil end\n"
    result = extract_section_lua_context("## Events & listeners", lua, 8000)
    assert result == ""
```

- [ ] **Step 2: Run to confirm the EventHandler test fails**

```
.venv/Scripts/pytest validator/tests/test_sections.py -k "events_context" -v
```

Expected: `test_events_context_includes_eventhandler` FAILS; ListenForEvent/PushEvent tests PASS (existing behavior)

- [ ] **Step 3: Update the `## Events & listeners` branch in `extract_section_lua_context`**

In `sections.py` around line 662, change:

```python
    elif section_heading == "## Events & listeners":
        ctx_parts: list[str] = []
        for i, line in enumerate(lines):
            if re.search(r'ListenForEvent|PushEvent', line):
```

to:

```python
    elif section_heading == "## Events & listeners":
        ctx_parts: list[str] = []
        for i, line in enumerate(lines):
            if re.search(r'ListenForEvent|PushEvent|EventHandler\s*\(', line):
```

- [ ] **Step 4: Run tests to confirm all 4 pass**

```
.venv/Scripts/pytest validator/tests/test_sections.py -k "events_context" -v
```

Expected: all 4 PASS

- [ ] **Step 5: Commit**

```
git add validator/tests/test_sections.py validator/src/validator/content/sections.py
git commit -m "feat(validator): add EventHandler pattern to events Lua context extraction"
```

---

### Task 3: Fix `extract_section_lua_context` — Properties branch (stategraph path)

**Files:**
- Modify: `validator/tests/test_sections.py`
- Modify: `validator/src/validator/content/sections.py`

- [ ] **Step 1: Write failing tests for the stategraph Properties branch**

Append to `validator/tests/test_sections.py`:

```python
# ── extract_section_lua_context — Properties branch ─────────────────────────

_STATEGRAPH_PROPS_LUA = '''\
local SPEED = 6
local ATTACK_PROP = "fast"
StateGraph("sg_wx78", states, events, "idle", actionhandlers)
CommonStates.AddSinkAndWashAshoreStates(states, {
    sink = "sink",
    washashore = "washashore",
})
CommonStates.AddVoidFallStates(states, {})
SGWX78Common.AddWX78SpinStates(states)
states = {
    State{name = "idle", tags = {"idle"}},
    State{name = "attack", tags = {"attack", "busy"}},
}
'''

_COMP_PROPS_LUA = '''\
local MyComp = Class(function(self, inst)
    self.inst = inst
    self.speed = 6
end)
function MyComp:GetSpeed() return self.speed end
'''


def test_properties_stategraph_includes_commonstate_calls():
    result = extract_section_lua_context("## Properties", _STATEGRAPH_PROPS_LUA, 8000)
    assert "CommonStates.AddSinkAndWashAshoreStates" in result
    assert "CommonStates.AddVoidFallStates" in result


def test_properties_stategraph_includes_sg_common_calls():
    result = extract_section_lua_context("## Properties", _STATEGRAPH_PROPS_LUA, 8000)
    assert "SGWX78Common.AddWX78SpinStates" in result


def test_properties_stategraph_includes_state_names():
    result = extract_section_lua_context("## Properties", _STATEGRAPH_PROPS_LUA, 8000)
    assert "idle" in result
    assert "attack" in result


def test_properties_stategraph_includes_constants():
    result = extract_section_lua_context("## Properties", _STATEGRAPH_PROPS_LUA, 8000)
    assert "SPEED" in result
    assert "ATTACK_PROP" in result


def test_properties_component_uses_class_path():
    """Regression: component files still use Class() constructor extraction."""
    result = extract_section_lua_context("## Properties", _COMP_PROPS_LUA, 8000)
    assert "self.speed" in result
```

- [ ] **Step 2: Run to confirm stategraph properties tests fail**

```
.venv/Scripts/pytest validator/tests/test_sections.py -k "properties_" -v
```

Expected: stategraph tests FAIL; component test PASS

- [ ] **Step 3: Add stategraph branch to `## Properties` in `extract_section_lua_context`**

In `sections.py`, find the `elif section_heading == "## Properties":` block (around line 633) and prepend the stategraph path:

```python
    elif section_heading == "## Properties":
        if _is_stategraph(lua_source):
            # Stategraph: file-scope constants + CommonStates/character-specific injections
            # + StateGraph call header + synthesized state name list.
            # Known limitation: character-specific injection modules without 'SG' prefix
            # (e.g. WillowCommon) are not matched by SG\w+Common pattern.
            sg_lines: list[str] = []
            for line in lines:
                stripped = line.rstrip("\n")
                if (re.match(r'^local\s+[A-Z_]+\s*=', stripped)
                        or re.search(r'CommonStates\.\w+\s*\(', stripped)
                        or re.search(r'SG\w+Common\.\w+\s*\(', stripped)
                        or re.search(r'\bStateGraph\s*\(', stripped)):
                    sg_lines.append(stripped)
            state_names = re.findall(r'\bState\s*\{\s*name\s*=\s*"([^"]+)"', lua_source)
            if state_names:
                sg_lines.append(f"-- States defined inline: {', '.join(state_names)}")
            blocks = ["\n".join(sg_lines)] if sg_lines else []
        else:
            class_match = re.search(r'\bClass\s*\(', lua_source)
            if class_match:
                # existing Class() constructor body extraction (unchanged)
                start = lua_source.rfind("\n", 0, class_match.start()) + 1
                tail = lua_source[class_match.end():]
                end_paren_match = re.search(r'\bend\s*\)', tail)
                if end_paren_match:
                    end = class_match.end() + end_paren_match.end()
                else:
                    after_first_fn = re.sub(r'function\b', '', tail, count=1)
                    end_match = re.search(r'(?m)^(local\s+)?function\b', after_first_fn)
                    end = class_match.end() + end_match.start() if end_match else len(lua_source)
                blocks = [lua_source[start:end]]
            else:
                # Utility module fallback: module-level constants + table assignments
                prop_lines = [
                    line.rstrip("\n")
                    for line in lines
                    if re.match(r'^local\s+[A-Z_]+\s*=', line)
                    or re.match(r'^\w+\.\w+\s*=', line)
                ]
                blocks = ["\n".join(prop_lines)] if prop_lines else []
```

- [ ] **Step 4: Run tests to confirm all 5 pass**

```
.venv/Scripts/pytest validator/tests/test_sections.py -k "properties_" -v
```

Expected: all 5 PASS

- [ ] **Step 5: Commit**

```
git add validator/tests/test_sections.py validator/src/validator/content/sections.py
git commit -m "feat(validator): add stategraph branch to Properties Lua context extraction"
```

---

### Task 4: Add `## Action Handlers` branch to `extract_section_lua_context`

**Files:**
- Modify: `validator/tests/test_sections.py`
- Modify: `validator/src/validator/content/sections.py`

- [ ] **Step 1: Write failing tests**

Append to `validator/tests/test_sections.py`:

```python
# ── extract_section_lua_context — Action Handlers branch ────────────────────

_ACTION_HANDLERS_LUA = '''\
StateGraph("sg_wx78", states, events, "idle",
{
    ActionHandler(ACTIONS.TOGGLEWXSCREECH, function(inst)
        inst.sg:GoToState("wx_screech_pre")
    end),
    ActionHandler(ACTIONS.TOGGLEWXSHIELDING, function(inst)
        inst.sg:GoToState("wx_shield_pre")
    end),
})
'''


def test_action_handlers_context_basic():
    result = extract_section_lua_context("## Action Handlers", _ACTION_HANDLERS_LUA, 8000)
    assert "ActionHandler(ACTIONS.TOGGLEWXSCREECH" in result
    assert "ActionHandler(ACTIONS.TOGGLEWXSHIELDING" in result


def test_action_handlers_context_empty_when_none():
    lua = "function DoThing(inst) return nil end\n"
    result = extract_section_lua_context("## Action Handlers", lua, 8000)
    assert result == ""


def test_action_handlers_context_unknown_section_still_empty():
    """Regression: unknown headings still return ''."""
    result = extract_section_lua_context("## Totally Unknown", _ACTION_HANDLERS_LUA, 8000)
    assert result == ""
```

- [ ] **Step 2: Run to confirm they fail**

```
.venv/Scripts/pytest validator/tests/test_sections.py -k "action_handlers" -v
```

Expected: `test_action_handlers_context_basic` FAILS (returns ""); others PASS or FAIL depending on order

- [ ] **Step 3: Add the `## Action Handlers` elif before the final `else: return ""`**

In `sections.py`, replace the final `else: return ""` block (around line 672) with:

```python
    elif section_heading == "## Action Handlers":
        ctx_parts: list[str] = []
        for i, line in enumerate(lines):
            if re.search(r'ActionHandler\s*\(', line):
                start = max(0, i - 1)
                end = min(len(lines), i + 4)
                ctx_parts.extend(l.rstrip("\n") for l in lines[start:end])
                ctx_parts.append("---")
        blocks = ["\n".join(ctx_parts)] if ctx_parts else []

    else:
        return ""
```

- [ ] **Step 4: Run tests to confirm all 3 pass**

```
.venv/Scripts/pytest validator/tests/test_sections.py -k "action_handlers" -v
```

Expected: all 3 PASS

- [ ] **Step 5: Run full sections test suite to catch regressions**

```
.venv/Scripts/pytest validator/tests/test_sections.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```
git add validator/tests/test_sections.py validator/src/validator/content/sections.py
git commit -m "feat(validator): add Action Handlers branch to Lua context extraction"
```

---

## Chunk 2: `prompts.py` rule IDs + `chunked.py` structural headings + events guard

### Task 5: `prompts.py` — Add `## Action Handlers` rule IDs

**Files:**
- Modify: `validator/src/validator/content/prompts.py`

No separate test task — `_RULE_IDS_BY_SECTION` is a dict lookup; correctness verified in Task 7's integration tests.

- [ ] **Step 1: Add `## Action Handlers` entry to `_RULE_IDS_BY_SECTION`**

In `prompts.py` around line 407, find `_RULE_IDS_BY_SECTION` and add the new entry:

```python
_RULE_IDS_BY_SECTION: dict[str, list[str]] = {
    "## Overview":             ["WRONG_FILE_TYPE", "INACCURATE_DESCRIPTION", "MISSING_KEY_INFO"],
    "## Usage example":        ["WRONG_FUNCTION_CALL", "USES_INVALID_API", "UNREALISTIC_EXAMPLE"],
    "## Dependencies & tags":  ["MISSING_ENTRY", "EXTRA_ENTRY", "WRONG_USAGE_DESC"],
    "## Properties":           ["WRONG_TYPE", "WRONG_DEFAULT", "MISSING_PROPERTY", "EXTRA_PROPERTY"],
    "## Main functions":       ["WRONG_VALUE", "MISSING_PARAM", "EXTRA_PARAM", "WRONG_DESCRIPTION",
                               "WRONG_ERROR_STATE", "MISPLACED_ERROR_STATE"],
    "## Events & listeners":   ["MISSING_EVENT", "WRONG_EVENT_NAME"],
    "## Action Handlers":      ["MISSING_ACTION_HANDLER", "WRONG_ACTION_HANDLER",
                               "EXTRA_ACTION_HANDLER"],
}
```

- [ ] **Step 2: Verify lookup returns correct rule IDs**

```
.venv/Scripts/python -c "from validator.content.prompts import _RULE_IDS_BY_SECTION; print(_RULE_IDS_BY_SECTION.get('## Action Handlers'))"
```

Expected: `['MISSING_ACTION_HANDLER', 'WRONG_ACTION_HANDLER', 'EXTRA_ACTION_HANDLER']`

- [ ] **Step 3: Commit**

```
git add validator/src/validator/content/prompts.py
git commit -m "feat(validator): add Action Handlers rule IDs to _RULE_IDS_BY_SECTION"
```

---

### Task 6: `chunked.py` — `_STRUCTURAL_HEADINGS` + events guard pre-pass

**Files:**
- Modify: `validator/src/validator/content/chunked.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Add `## Action Handlers` to `_STRUCTURAL_HEADINGS`**

In `chunked.py` around line 54, update the set:

```python
_STRUCTURAL_HEADINGS = {
    "## Dependencies & tags",
    "## Properties",
    "## Main functions",
    "## Events & listeners",
    "## Action Handlers",    # stategraph-specific; no-op for docs that lack this section
}
```

- [ ] **Step 2: Add imports for the new helper functions**

In `chunked.py`, update **only** the import from `validator.content.sections` (add the two new names). Do NOT touch the existing `from validator.content.reviewer import Finding, parse_findings_json` line — `Finding` is already imported there and is used by the guard code.

```python
from validator.content.sections import (
    DocSection,
    _canonical_fn_name,
    apply_typed_ops,
    check_stategraph_events_null,       # NEW
    classify_lua_functions,
    ensure_required_fields,
    extract_function_names,
    extract_lua_context,
    extract_section_lua_context,
    extract_stategraph_event_names,     # NEW
    join_md_sections,
    normalize_fn_headings,
    prefilter_fn_blocks,
    split_md_sections,
    split_section_blocks,
    sub_chunk_section_lua_aware,
)
# Leave unchanged: from validator.content.reviewer import Finding, parse_findings_json
```

- [ ] **Step 3: Write failing tests for the events guard**

Append to `validator/tests/test_content_chunked.py`:

```python
# ── stategraph events guard ──────────────────────────────────────────────────

_SG_EVENTS_MD = (
    "---\ntitle: SGTest\n---\n"
    "## Events & listeners\n"
    "**Listens to:** None\n\n"
)

_SG_EVENTS_LUA = (
    'StateGraph("sg_test", states, events, "idle", {})\n'
    'events = {\n'
    '    EventHandler("death", function(inst) end),\n'
    '    EventHandler("freeze", function(inst) end),\n'
    '}\n'
)

_COMP_EVENTS_MD = (
    "---\ntitle: CompTest\n---\n"
    "## Events & listeners\n"
    "**Listens to:** None\n\n"
)

_COMP_EVENTS_LUA = (
    "local MyComp = Class(function(self, inst) self.inst = inst end)\n"
    "function MyComp:GetOwner() return self.inst end\n"
)


def _update_section_op(section, content):
    body = json.dumps([{
        "op": "update_section",
        "section": section,
        "function": None, "field": None, "value": None,
        "content": content,
    }])
    return {"message": {"content": body}}


def test_events_guard_fires_for_stategraph_null(tmp_path):
    """Guard pre-pass calls writer when stategraph doc claims no events."""
    md = tmp_path / "sg.md"
    lua = tmp_path / "sg.lua"
    md.write_text(_SG_EVENTS_MD, encoding="utf-8")
    lua.write_text(_SG_EVENTS_LUA, encoding="utf-8")

    corrected_content = (
        "## Events & listeners\n"
        "**EventHandlers:** death, freeze\n"
    )
    calls = []

    def mock_ollama(model, messages, **kwargs):
        calls.append(messages)
        # First call is the guard writer call; second+ are reviewer/writer for normal loop
        if len(calls) == 1:
            return _update_section_op("## Events & listeners", corrected_content)
        return _approved()

    from validator.content.loop import ContentLoopConfig
    config = ContentLoopConfig(stop_check=lambda: False, max_iterations=3)

    with patch("validator.content.chunked.ollama_chat", side_effect=mock_ollama):
        result = run_chunked_content_loop(str(md), str(lua), config)

    # Guard fired: first call was the forced writer pre-pass
    assert len(calls) >= 1
    # Content no longer says "None"
    final = md.read_text(encoding="utf-8")
    assert "death" in final or "freeze" in final or "EventHandler" in final


def test_events_guard_does_not_fire_for_non_stategraph(tmp_path):
    """Guard must NOT fire for component files even if Events section says None."""
    md = tmp_path / "comp.md"
    lua = tmp_path / "comp.lua"
    md.write_text(_COMP_EVENTS_MD, encoding="utf-8")
    lua.write_text(_COMP_EVENTS_LUA, encoding="utf-8")

    calls = []

    def mock_ollama(model, messages, **kwargs):
        calls.append(messages)
        return _approved()

    from validator.content.loop import ContentLoopConfig
    config = ContentLoopConfig(stop_check=lambda: False, max_iterations=3)

    with patch("validator.content.chunked.ollama_chat", side_effect=mock_ollama):
        result = run_chunked_content_loop(str(md), str(lua), config)

    # Guard must not fire — all mock calls are reviewer calls (approved immediately)
    # The file should be unchanged (events section still says None, which is correct
    # for a component file with no real events)
    assert result.approved is True
    final = md.read_text(encoding="utf-8")
    assert "Listens to:** None" in final  # unchanged — guard correctly did not pre-correct
```

- [ ] **Step 4: Run to confirm the guard test fails**

```
.venv/Scripts/pytest validator/tests/test_content_chunked.py -k "events_guard" -v
```

Expected: `test_events_guard_fires_for_stategraph_null` FAILS (guard not yet implemented)

- [ ] **Step 5: Implement the events guard pre-pass in `run_chunked_content_loop`**

In `chunked.py`, in the `else` branch (non-`## Main functions` sections), insert the guard **before** `cache.create`. The insertion point is after the "skip if no content" check and before `sec_cache_id = ...`. The current code around line 643 looks like:

```python
        else:
            fn_count = len(re.findall(r'(?m)^### ', section.text))
            label = f"{fn_count} fn(s)" if fn_count else "structure only"
            print(f" -- {label} found")

            if fn_count == 0 and not lua_ctx:
                print(f"  [content/chunked] Section {sec_idx} -- skipped (no content to validate)")
                completed_sections.add(sec_idx)
                save_validator_checkpoint(md_filepath, cache.cache_dir, completed_sections, total_iterations, all_issues)
                continue

            # Create cache for this section    ← INSERT GUARD HERE, before this line
            sec_cache_id = f"sec{sec_idx}"
            cache.create(sec_cache_id, section.text)
```

Add the guard block immediately before `sec_cache_id = f"sec{sec_idx}"`:

```python
            # ── Stategraph events guard (pre-pass before LLM loop) ───────────
            # If the events section claims "None" but source has EventHandlers,
            # call the writer directly to pre-correct before the normal loop.
            # CRITICAL: must update section.text BEFORE cache.create so the
            # loop reads the corrected content, not the broken original.
            if (section.heading == "## Events & listeners"
                    and check_stategraph_events_null(section.text, lua_source)):
                event_names = extract_stategraph_event_names(lua_source)
                forced_finding = Finding(
                    section=section.heading,
                    function=None,
                    field=None,
                    rule_id="MISSING_EVENT",
                    issue=(
                        f"Section claims no events but source defines "
                        f"{len(event_names)} EventHandler(s): "
                        f"{', '.join(event_names)}. "
                        "Rewrite Events & listeners to list all EventHandlers."
                    ),
                )
                forced_ops = _call_writer_batch(
                    section.text, lua_ctx, [forced_finding], config, file_type
                )
                if forced_ops:
                    dummy = DocSection(heading=section.heading, text=section.text)
                    corrected = apply_typed_ops([dummy], forced_ops, frontmatter="")
                    if corrected[0].text != section.text:
                        section.text = corrected[0].text
                        print(
                            f"  [content/chunked] events guard: pre-corrected "
                            f"'None' → {len(event_names)} EventHandler(s)"
                        )
                    else:
                        print(
                            "  [content/chunked] events guard: writer returned no change "
                            "— falling through to normal loop"
                        )
            # ── end events guard ─────────────────────────────────────────────

            # Create cache for this section (AFTER guard pre-pass)
            sec_cache_id = f"sec{sec_idx}"
            cache.create(sec_cache_id, section.text)
```

- [ ] **Step 6: Run guard tests**

```
.venv/Scripts/pytest validator/tests/test_content_chunked.py -k "events_guard" -v
```

Expected: both PASS

- [ ] **Step 7: Run full chunked test suite for regressions**

```
.venv/Scripts/pytest validator/tests/test_content_chunked.py -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(validator): add Action Handlers to structural headings + stategraph events guard"
```

---

## Chunk 3: `validator_reviewer.md` — Stategraph rule additions

### Task 7: Add three new explicit rules under `### Stategraph file checks`

**Files:**
- Modify: `skills/roles/validator_reviewer.md`

No automated tests — skill files are LLM prompts. Verify by reading the file after edit.

- [ ] **Step 1: Find the insertion point**

In `skills/roles/validator_reviewer.md`, locate the `### Stategraph file checks` section (around line 169). The current last entry before `### Brain file checks` is the oscillation guard for stategraph built-in error states.

- [ ] **Step 2: Append the three new rules before `### Brain file checks`**

After the `**OSCILLATION GUARD — Stategraph built-in error states:**` paragraph, insert:

```markdown
STATEGRAPH EVENTS RULE: For `## Events & listeners`, enumerate ALL `EventHandler("event_name", fn)` entries in the `events = {...}` table of the `StateGraph(...)` call. Each event name MUST appear in the doc. The section for a stategraph lists EventHandler entries (engine events the stategraph reacts to) — NOT `ListenForEvent` calls.
If the doc says 'Listens to: None' but source has N EventHandlers, flag each missing event:
{"issue": "EventHandler 'death' is defined in source events table but absent from ## Events & listeners.", "suggestion": "Add 'death' under EventHandlers in the Events & listeners section."}

INJECTED STATES RULE: Calls like `CommonStates.AddSinkAndWashAshoreStates(states, ...)`, `CommonStates.AddVoidFallStates(states, ...)`, `SGWX78Common.AddWX78SpinStates(states)` inject additional states not defined inline in the StateGraph call. The state reference table in `## Properties` MUST include these injected states. Common injection mappings:
- `AddSinkAndWashAshoreStates` → sink, washashore
- `AddVoidFallStates`          → abyss_fall, voiddrop
- `AddRowStates`               → rowing states (hop variants)
- `AddHopStates`               → hop_pre, hop_loop, hop_pst
- `AddWX78SpinStates`          → wx_spin_start, wx_spin
- `AddWX78ShieldStates`        → wx_shield_pre, wx_shield_pst
- `AddWX78ScreechStates`       → wx_screech_pre, wx_screech_pst
- `AddWX78BakeState`           → wx bake state
If any injection call exists in source but the resulting states are absent from the Properties state table, flag each missing state group:
{"issue": "CommonStates.AddVoidFallStates injects 'abyss_fall' and 'voiddrop' states but neither appears in the ## Properties state reference table.", "suggestion": "Add abyss_fall and voiddrop rows to the state reference table in ## Properties."}

ACTION HANDLERS SECTION RULE: If the stategraph defines `ActionHandler(ACTIONS.XXX, fn)` entries in the `actionhandlers = {}` argument to `StateGraph(...)`, the doc MUST have a `## Action Handlers` section listing each `ACTIONS` constant and what state it transitions to or behavior it triggers. If ActionHandler entries exist in source but `## Action Handlers` is absent:
{"issue": "Stategraph defines N ActionHandler entries (ACTIONS.TOGGLEWXSCREECH, ...) but ## Action Handlers section is absent from the document.", "suggestion": "Add ## Action Handlers section listing each ACTIONS constant and its handler behavior."}
```

- [ ] **Step 3: Verify the file reads cleanly**

```
.venv/Scripts/python -c "
from prompts.skills_loader import load_skill
skill = load_skill('validator_reviewer')
assert 'STATEGRAPH EVENTS RULE' in skill
assert 'INJECTED STATES RULE' in skill
assert 'ACTION HANDLERS SECTION RULE' in skill
print('OK — all three rules present in loaded skill')
"
```

Expected: `OK — all three rules present in loaded skill`

- [ ] **Step 4: Commit**

```
git add skills/roles/validator_reviewer.md
git commit -m "feat(validator): add EventHandler/injected-states/action-handlers rules to stategraph skill"
```

---

## Final: Full test suite

- [ ] **Run complete validator test suite**

```
.venv/Scripts/pytest validator/tests/ -v
```

Expected: all tests PASS, no regressions

- [ ] **Run all workspace tests**

```
.venv/Scripts/pytest -v
```

Expected: all tests PASS

- [ ] **Final commit if any cleanup needed**

```
git add -p
git commit -m "fix(validator): stategraph validator gaps — events/properties/action-handlers"
```
