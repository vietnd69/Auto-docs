# Design: Stategraph Validator Gaps — Approach C (Hybrid)

**Date:** 2026-05-07  
**Scope:** All validator paths (chunked ≥32K tokens + standard <32K tokens)  
**Status:** Approved

---

## Problem Statement

Three distinct failures were discovered when validating `SGwx78_possessedbody.md` (2262-line Lua source, chunked path):

| # | Problem | Impact |
|---|---|---|
| 1 | `## Events & listeners` approved with "Listens to: None" despite 15 `EventHandler(...)` entries in source | Completely wrong events section ships undetected |
| 2 | `## Properties` state reference table missing all states injected by `CommonStates.AddXxxStates(...)` and `SGWX78Common.AddWX78XxxStates(...)` | Stategraph capability surface invisibly incomplete |
| 3 | `## Action Handlers` section entirely absent — 15 `ActionHandler(ACTIONS.XXX, fn)` entries undocumented | Major behavioral section missing from doc |

---

## Root Cause Analysis

### Chunked path (primary failure site)

`extract_section_lua_context` returns focused Lua excerpts per section heading. Three gaps:

**Gap 1 — Events extraction misses stategraph pattern:**
```python
# Current: only searches ListenForEvent / PushEvent
if re.search(r'ListenForEvent|PushEvent', line):
```
Stategraph events are defined as `EventHandler("death", fn)` in the `events = {...}` table — a completely different pattern. With no Lua context, the reviewer cannot verify the section content and defaults to approving "None".

**Gap 2 — Properties extraction has no stategraph branch:**
```python
# Current: Class() constructor → or utility module fallback
class_match = re.search(r'\bClass\s*\(', lua_source)
if class_match:   # Component path
    ...
else:             # Utility fallback: local UPPER = ... and table.field = ...
    ...
```
Stategraph files have no `Class()` constructor, so they fall to the utility fallback which matches `local UPPER_CONST = ...` and `table.field = ...` assignments. `CommonStates.AddSinkAndWashAshoreStates(states, ...)` is a function **call**, not an assignment — completely missed.

**Gap 3 — `## Action Handlers` unknown to validator:**
- Not in `_STRUCTURAL_HEADINGS` → never processed
- Not in `_RULE_IDS_BY_SECTION` → no rule IDs for reviewer to emit
- Not in MISSING SECTION RULE in `validator_reviewer.md` → standard path reviewer doesn't flag absence

### Standard path (secondary)
Standard path receives full Lua source so the LLM can see EventHandlers and ActionHandlers — but `validator_reviewer.md` stategraph rules are not explicit enough. The reviewer has no instruction to enumerate EventHandlers and verify each one appears in the doc.

---

## Solution: Approach C (Targeted context fixes + deterministic safety net)

### Design principles
- Fix the root cause (bad context extraction) so the LLM gets the right information
- Add one deterministic guard for the most egregious failure mode (approving "None" events)
- Improve skill rules so the standard path's full-context reviewer catches these patterns

---

## Component 1: `sections.py` — Stategraph-aware context extraction

**File:** `validator/src/validator/content/sections.py`

### New helper functions

```python
def _is_stategraph(lua_source: str) -> bool:
    """Return True if lua_source defines a StateGraph."""
    return bool(re.search(r'\bStateGraph\s*\(', lua_source))

def extract_stategraph_event_names(lua_source: str) -> list[str]:
    """Return all event names from EventHandler(...) entries."""
    return re.findall(r'EventHandler\s*\(\s*"([^"]+)"', lua_source)

def check_stategraph_events_null(section_text: str, lua_source: str) -> bool:
    """True if doc claims no events but source has EventHandler entries.
    
    Detects: section says 'Listens to: None' (or **None.**) 
    but Lua source has ≥1 EventHandler entry.
    Only applies to stategraph files.
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

### Changes to `extract_section_lua_context`

**`## Events & listeners` branch** — add `EventHandler\s*\(` to detection pattern:
```python
elif section_heading == "## Events & listeners":
    ctx_parts: list[str] = []
    for i, line in enumerate(lines):
        if re.search(r'ListenForEvent|PushEvent|EventHandler\s*\(', line):
            start = max(0, i - 2)
            end = min(len(lines), i + 3)
            ctx_parts.extend(l.rstrip("\n") for l in lines[start:end])
            ctx_parts.append("---")
    blocks = ["\n".join(ctx_parts)] if ctx_parts else []
```

**`## Properties` branch** — add stategraph path before existing `Class()` check:
```python
elif section_heading == "## Properties":
    if _is_stategraph(lua_source):
        # Stategraph: extract file-scope constants + injected state calls + state names
        sg_lines: list[str] = []
        for line in lines:
            stripped = line.rstrip("\n")
            if (re.match(r'^local\s+[A-Z_]+\s*=', stripped)           # file-scope constants
                    or re.search(r'CommonStates\.\w+\s*\(', stripped)  # CommonStates injections
                    or re.search(r'SG\w+Common\.\w+\s*\(', stripped)   # character-specific injections
                    or re.search(r'\bStateGraph\s*\(', stripped)):      # StateGraph call header
                sg_lines.append(stripped)
        # Synthesize state name list from State{name="..."} entries
        state_names = re.findall(r'\bState\s*\{\s*name\s*=\s*"([^"]+)"', lua_source)
        if state_names:
            sg_lines.append(f"-- States defined inline: {', '.join(state_names)}")
        blocks = ["\n".join(sg_lines)] if sg_lines else []
    else:
        # Existing Class() constructor + utility fallback (unchanged)
        ...
```

**New `## Action Handlers` branch** (new `elif` added before the final `else: return ""`):
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
```

---

## Component 2: `chunked.py` — Structural headings + events guard

**File:** `validator/src/validator/content/chunked.py`

### Add `## Action Handlers` to structural headings

```python
_STRUCTURAL_HEADINGS = {
    "## Dependencies & tags",
    "## Properties",
    "## Main functions",
    "## Events & listeners",
    "## Action Handlers",    # NEW — stategraph-specific
}
```

Adding it to `_STRUCTURAL_HEADINGS` means: if the section exists in the doc, it is processed early (before narrative sections). For non-stategraph docs that lack this section, it is a no-op.

### Stategraph events guard pre-pass

In `run_chunked_content_loop`, for the `## Events & listeners` section, **before** the cache is created and **before** `_run_typed_loop` is called, inject a deterministic correction.

**CRITICAL ordering constraint:** The guard must update `section.text` BEFORE `cache.create(sec_cache_id, section.text)` is called. `_run_typed_loop` reads from cache, not from `section.text` — if the cache is created first with the broken "None" text and then `section.text` is updated, the loop sees the old broken content.

```
if section.heading == "## Events & listeners":
    if check_stategraph_events_null(section.text, lua_source):
        event_names = extract_stategraph_event_names(lua_source)
        forced_finding = Finding(
            section=section.heading,    # MUST be exact heading string e.g. "## Events & listeners"
            function=None,
            field=None,
            rule_id="MISSING_EVENT",
            issue=f"Section claims no events but source defines {len(event_names)} "
                  f"EventHandler(s): {', '.join(event_names)}. "
                  "Rewrite Events & listeners to list all EventHandlers.",
        )
        # Call writer with forced finding BEFORE cache.create
        forced_ops = _call_writer_batch(section.text, lua_ctx, [forced_finding], config, file_type)
        if forced_ops:
            dummy = DocSection(heading=section.heading, text=section.text)
            corrected = apply_typed_ops([dummy], forced_ops, frontmatter="")
            # Validate that apply_typed_ops actually changed the text.
            # apply_typed_ops matches ops to sections by heading (case-insensitive).
            # If the LLM returns an op with a mismatched section string (e.g. missing "##"),
            # apply_typed_ops silently no-ops. Check for change before accepting.
            if corrected[0].text != section.text:
                section.text = corrected[0].text
                print(f"  [content/chunked] events guard: pre-corrected "
                      f"'None' → {len(event_names)} EventHandler(s)")
            else:
                print(f"  [content/chunked] events guard: writer returned no change "
                      f"— falling through to normal loop")
        # Guard pre-pass done; now proceed to cache.create + _run_typed_loop

# cache.create must come AFTER guard pre-pass
sec_cache_id = f"sec{sec_idx}"
cache.create(sec_cache_id, section.text)
```

**Known limitation — `check_stategraph_events_null` pattern coverage:** The guard only detects "listens to: none" and "**none.**" as indicators of a "no events" claim. Other phrasings ("None.", "**None**" without period, "No events.") are not detected. In those cases the guard does not fire and the LLM loop with improved context must catch the issue. This is acceptable — the guard is a safety net for the most common failure pattern, not a complete solution.

**Known limitation — `SG\w+Common` prefix:** The Properties stategraph branch matches character-specific injection modules via `SG\w+Common\.\w+\s*\(`. This requires the module name to start with `SG`. Any character-specific helper module without the `SG` prefix (e.g., a hypothetical `WillowCommon.AddStates(...)`) would be missed by this pattern. This is accepted scope — DST character stategraph common modules consistently use `SGXxxCommon` naming. Document as known limitation if this assumption is violated.

`_run_typed_loop` is **not modified** — the guard is a standalone pre-pass that writes corrected content; the loop then fine-tunes it.

---

## Component 3: `prompts.py` — Rule IDs

**File:** `validator/src/validator/content/prompts.py`

**Scope: chunked path only.** `_RULE_IDS_BY_SECTION` is consumed exclusively by `build_typed_reviewer_prompt`, which is called only from `chunked.py`. The standard path uses `build_reviewer_prompt` (no rule IDs parameter) — for the standard path, `## Action Handlers` detection relies entirely on the skill rules added in Component 4.

```python
_RULE_IDS_BY_SECTION: dict[str, list[str]] = {
    # existing entries ...
    "## Events & listeners":  ["MISSING_EVENT", "WRONG_EVENT_NAME"],  # unchanged — EXTRA_EVENT NOT added
    "## Action Handlers":     ["MISSING_ACTION_HANDLER", "WRONG_ACTION_HANDLER",
                               "EXTRA_ACTION_HANDLER"],  # NEW — chunked path only
}
```

**Note:** `EXTRA_EVENT` is intentionally NOT added to the Events rule IDs. All three gaps are false-negative problems (events missing from doc). Adding `EXTRA_EVENT` could cause spurious findings in cases where events exist in source but outside the truncated lua_ctx window. The existing `WRONG_EVENT_NAME` rule_id covers correction of incorrectly named events.

---

## Component 4: `validator_reviewer.md` — Stategraph rule additions

**File:** `skills/roles/validator_reviewer.md`

Three new explicit rules appended to `### Stategraph file checks`:

### STATEGRAPH EVENTS RULE (replaces implicit check)
```
STATEGRAPH EVENTS RULE: For ## Events & listeners, enumerate ALL EventHandler("event_name", fn)
entries in the events = {...} table of the StateGraph(...) call. Each event name MUST appear
in the doc. The section for a stategraph lists EventHandler entries (engine events that the
stategraph reacts to) — NOT ListenForEvent calls.
If the doc says 'Listens to: None' but source has N EventHandlers, flag each missing event:
{"issue": "EventHandler 'death' is defined in source events table but absent from ## Events & listeners.",
 "suggestion": "Add 'death' under EventHandlers in the Events & listeners section."}
```

### INJECTED STATES RULE (new)
```
INJECTED STATES RULE: Calls like CommonStates.AddSinkAndWashAshoreStates(states, ...),
CommonStates.AddVoidFallStates(states, ...), SGWX78Common.AddWX78SpinStates(states) inject
additional states not defined inline in the StateGraph call. The state reference table in
## Properties MUST include these injected states. Common injection mappings (for reference):
  - AddSinkAndWashAshoreStates → sink, washashore
  - AddVoidFallStates          → abyss_fall, voiddrop
  - AddRowStates               → rowing states (hop variants)
  - AddHopStates               → hop_pre, hop_loop, hop_pst
  - AddWX78SpinStates          → wx_spin_start, wx_spin
  - AddWX78ShieldStates        → wx_shield_pre, wx_shield_pst
  - AddWX78ScreechStates       → wx_screech_pre, wx_screech_pst
  - AddWX78BakeState           → wx bake state
If any injection call exists in source but the resulting states are absent from the Properties
state table, flag each missing state group:
{"issue": "CommonStates.AddVoidFallStates injects 'abyss_fall' and 'voiddrop' states but
           neither appears in the ## Properties state reference table.",
 "suggestion": "Add abyss_fall and voiddrop rows to the state reference table in ## Properties."}
```

### ACTION HANDLERS SECTION RULE (new)
```
ACTION HANDLERS SECTION RULE: If the stategraph defines ActionHandler(ACTIONS.XXX, fn) entries
in the actionhandlers = {} argument to StateGraph(...), the doc MUST have a ## Action Handlers
section listing each ACTIONS constant and what state it transitions to or what behavior it triggers.
If ActionHandler entries exist in source but ## Action Handlers is absent:
{"issue": "Stategraph defines N ActionHandler entries (ACTIONS.TOGGLEWXSCREECH, ...) but
           ## Action Handlers section is absent from the document.",
 "suggestion": "Add ## Action Handlers section listing each ACTIONS constant and its handler behavior."}
```

---

## Data flow summary

### Chunked path (≥32K tokens)

```
run_chunked_content_loop
  ├─ file_type = _detect_file_type(...)        # existing
  │
  ├─ ## Events & listeners
  │   ├─ lua_ctx = extract_section_lua_context(...)  # NOW includes EventHandler( pattern
  │   ├─ [NEW] if check_stategraph_events_null(...)
  │   │       → _call_writer_batch([forced_finding])
  │   │       → update section.text
  │   └─ _run_typed_loop(...)                   # reviewer gets EventHandler Lua context
  │
  ├─ ## Properties
  │   ├─ lua_ctx = extract_section_lua_context(...)  # NOW includes CommonStates calls + state names
  │   └─ _run_typed_loop(...)
  │
  └─ ## Action Handlers                         # NOW in _STRUCTURAL_HEADINGS
      ├─ lua_ctx = extract_section_lua_context(...)  # NEW branch: ActionHandler lines
      └─ _run_typed_loop(...)
```

### Standard path (<32K tokens)

```
review_document(full_lua_source)
  └─ reviewer sees full Lua source (existing)
     + improved validator_reviewer.md stategraph rules (NEW)
       → STATEGRAPH EVENTS RULE: enumerate EventHandlers explicitly
       → INJECTED STATES RULE: check CommonStates injections
       → ACTION HANDLERS SECTION RULE: require ## Action Handlers
```

---

## Out of scope

- Approach B (full deterministic Lua parsing) — not needed; targeted fixes + guard sufficient
- Modifying `_run_typed_loop` — guard is a pre-pass; loop unchanged
- Adding `## Action Handlers` to the universal MISSING SECTION RULE — it is stategraph-specific; the explicit skill rule handles it per file type
- Standard path deterministic guard — standard path has full Lua source; skill rules sufficient

---

## Testing notes

- Run chunked validator on `SGwx78_possessedbody.md` — events guard should pre-correct "None" → EventHandler list; state table should include injected states; Action Handlers section should be reviewed
- Run standard validator on a small stategraph file — reviewer should flag missing EventHandlers/injected states/Action Handlers based on updated skill rules
- Non-stategraph files: regression check that existing behavior is unchanged (stategraph branch is gated by `_is_stategraph()`)
