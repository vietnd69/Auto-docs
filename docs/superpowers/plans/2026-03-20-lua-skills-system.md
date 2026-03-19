# Lua Skills System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract hardcoded domain knowledge from `prompt.py` and `chunked_prompt.py` into reusable Markdown skill files, loaded via a `docs_SKILL.md` index.

**Architecture:** A Python loader (`skills_loader.py`) parses `docs_SKILL.md` at call time and reads skill `.md` files by name or by prompt target. Prompt modules call `load_skill()` at module scope (load-once per process), replacing the inline hardcoded strings.

**Tech Stack:** Python 3.x, PyYAML (already in project), pytest

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Write | `docs_SKILL.md` | Skill registry — index of all skills and their inject targets |
| Create | `skills/dst_conventions.md` | Enriched DST ECS/event/tag/network/stategraph/brain/prefab conventions |
| Create | `skills/function_format.md` | Verbatim copy of `_FUNCTION_FORMAT_SPEC` from `chunked_prompt.py` |
| Create | `skills/quality_rules.md` | All critical documentation rules (extracted + enriched) |
| Create | `skills/few_shot.md` | Verbatim SampleComp full-document example from `prompt.py` |
| Create | `skills_loader.py` | `load_skill(name)` + `load_skills_for(target)` |
| Create | `test_skills_loader.py` | Tests for all loader behavior |
| Modify | `chunked_prompt.py` | Import loader, remove inline constant, replace DST blocks |
| Modify | `prompt.py` | Import loader, replace DST block + few-shot block |

---

## Chunk 1: Skill content files + index

### Task 1: Write `docs_SKILL.md`

**Files:**
- Write: `docs_SKILL.md` (currently 1-line empty file)

- [ ] **Step 1: Write the index file**

Write the full content of `docs_SKILL.md`:

```markdown
---
version: 1
---
## dst_conventions
file: skills/dst_conventions.md
inject_into: [chunk_prompt, merge_prompt, single_prompt]

## function_format
file: skills/function_format.md
inject_into: [merge_prompt, single_prompt]

## quality_rules
file: skills/quality_rules.md
inject_into: [merge_prompt, single_prompt]

## few_shot
file: skills/few_shot.md
inject_into: [single_prompt]
```

- [ ] **Step 2: Verify format is correct**

Open `docs_SKILL.md` and confirm:
- YAML block between `---` delimiters at top
- Four `## skill_name` sections
- Each section has `file:` and `inject_into:` fields
- `inject_into` values are: `chunk_prompt`, `merge_prompt`, `single_prompt`

---

### Task 2: Create `skills/dst_conventions.md`

**Files:**
- Create: `skills/dst_conventions.md`

- [ ] **Step 1: Create the `skills/` directory and write the file**

Create `skills/` directory at project root. Write `skills/dst_conventions.md` with the following content (enriched from the existing 6-line block in the prompts):

```markdown
# Skill: dst_conventions

ENTITY COMPONENT SYSTEM (ECS):
- Components attach to entities: `inst:AddComponent("name")` / access via `inst.components.name`.
- `self.inst` — the entity instance that owns this component.
- Constructor: `Class(function(self, ...) ... end)` — NOT `_ctor`. First param after `self` varies
  (commonly `inst` for components, `data` for utility classes).
- Every component is a Lua table; methods are functions stored in that table.

EVENT SYSTEM:
- `inst:ListenForEvent(event, fn)` — subscribe to event on entity.
- `inst:PushEvent(event, data)` — fire event on entity; data is an optional table.
- `inst:RemoveEventCallback(event, fn)` — unsubscribe a specific listener.
- World-level events: `TheWorld:ListenForEvent` / `TheWorld:PushEvent`.

TAG SYSTEM:
- `inst:AddTag("tag")` / `inst:RemoveTag("tag")` / `inst:HasTag("tag")`.
- Tags affect targeting (`FindEntities`, `FindClosestEntityWithTag`) and combat exclusions.
- Common tags: "player", "monster", "structure", "fire", "invisible", "notarget".

NETWORK REPLICATION:
- `self.inst.replica.X` — client-side replica of component X (read-only on client).
- NetVars: `net_bool`, `net_int`, `net_float`, `net_string`, `net_entity` synchronize state.
- `TheWorld.ismastersim` — true only on the server; guards server-only logic.
- `TheNet:GetIsClient()` / `TheNet:GetIsServer()` — runtime environment checks.
- `SendRPCToServer(RPC.Name, ...)` / `SendRPCToClient(client, RPC.Name, ...)` — RPCs.

GLOBAL REFERENCES:
- `TheWorld` — world entity; holds components like `map`, `weather`, `season`.
- `TheNet` — networking and lobby interface.
- `ThePlayer` — local player entity (client); may be nil on server before join.
- `AllPlayers` — list of all connected player entities (server).
- `TheSim` — simulation: `GetTick()`, `GetGameID()`, file I/O, scheduling.
- `TheInput` — keyboard/mouse input handling.
- `TUNING` — global balance constants table (damage, durations, quantities).
- `STRINGS` — localization string table.
- `ACTIONS` / `BufferedAction` — action system for player verb interactions.

STATEGRAPHS:
- `StateGraph(name, states, events, defaultstate, actionhandlers)` defines animation state machines.
- `State{name, onenter, onexit, ontimeout, events, timeline}` — individual state.
- `EventHandler(event, fn)` — handles events inside a stategraph.
- `TimeEvent(time, fn)` — fires function at specific animation frame.

BRAINS (AI):
- `Brain:new(inst)` creates a behavior tree for AI entities.
- Nodes: `SequenceNode`, `SelectorNode`, `ConditionNode`, `WaitNode`, `DoAction`.
- `RunBrain(inst, brain)` attaches and starts a brain.
- Brains are paused automatically when the entity is far from players.

PREFAB SYSTEM:
- `Prefabs["name"] = Prefab(name, fn, assets, deps)` registers a spawnable entity.
- Inside the prefab function: `CreateEntity()` -> attach components -> return inst.
- `SpawnPrefab("name")` — instantiates a prefab at runtime.
- `MakePlanarPhysics`, `MakeInventoryPhysics` — common physics helpers.

SCHEDULER / COROUTINES:
- `inst:DoTaskInTime(delay, fn)` — one-shot delayed task.
- `inst:DoPeriodicTask(period, fn, initial_delay)` — repeating task.
- `inst:StartThread(fn)` — coroutine attached to entity lifecycle.
- `Sleep(seconds)` inside a coroutine yields execution (non-blocking).
- `inst:ClearScheduledTask(task)` — cancel a pending task.
```

---

### Task 3: Create `skills/function_format.md`

**Files:**
- Create: `skills/function_format.md`
- Reference: `chunked_prompt.py` lines 19–67 (the `_FUNCTION_FORMAT_SPEC` constant body)

- [ ] **Step 1: Copy `_FUNCTION_FORMAT_SPEC` content verbatim**

Open `chunked_prompt.py` and locate `_FUNCTION_FORMAT_SPEC = """` (line 19). Copy the content of the triple-quoted string (everything between the opening `"""` and closing `"""`) verbatim into `skills/function_format.md`, with a header prepended:

```markdown
# Skill: function_format

=== FUNCTION FORMAT ===
Use EXACTLY this structure for every entry in ## Main functions:

### `FunctionName(params)`
* **Description:** What this function does and when it is called.
* **Parameters:** For a single param: `param` -- type and purpose.
  For multiple params, use sub-bullets:
  - `param1` -- description
  - `param2` -- description
  Write `None` if the function takes no parameters.
* **Returns:** Return value description, or `nil` if nothing is returned.
* **Error states:** Edge cases or early returns. Omit this bullet entirely if none.

=== DEPENDENCY SECTION FORMAT ===
Use EXACTLY these labels in ## Dependencies & tags:

**External dependencies:**
- `name` -- usage description
(Omit this bullet entirely if external_deps JSON is empty)

**Components used:**
- `component_name` -- how it is used (methods called, properties accessed)

**Tags:**
- `tag_name` -- add / remove / check
(Write `None` if game_tags JSON is empty)

=== FEW-SHOT EXAMPLE ===
Mirror this format only. Do NOT copy the content:

### `ConsoleCommandPlayer()`
* **Description:** Returns the currently selected debug entity, the local player, or the first valid player in AllPlayers.
* **Parameters:** None
* **Returns:** Player instance or `nil` if no valid player found.

### `c_spawn(prefab, count, dontselect)`
* **Description:** Spawns `count` instances of `prefab` at console position. Auto-selects first spawned unless `dontselect`.
* **Parameters:**
  - `prefab` -- string prefab name
  - `count` -- number of instances (default `1`)
  - `dontselect` -- boolean to skip auto-selection
* **Returns:** Last spawned instance, or `nil`.

### `c_save()`
* **Description:** Triggers a save on master sim.
* **Parameters:** None
* **Returns:** None
```

---

### Task 4: Create `skills/quality_rules.md`

**Files:**
- Create: `skills/quality_rules.md`
- Reference: `prompt.py` lines 138–152 (`=== CRITICAL INSTRUCTIONS ===` block)

- [ ] **Step 1: Write quality_rules.md with extracted + enriched rules**

```markdown
# Skill: quality_rules

=== DOCUMENTATION QUALITY RULES ===

SECTION ORDER (never change):
  ## Overview -> ## Usage example -> ## Dependencies & tags -> ## Properties -> ## Main functions -> ## Events & listeners
  Do NOT omit, reorder, or rename these sections.

OUTPUT FORMAT:
- Output ONLY valid Markdown starting with `---` (YAML frontmatter opening delimiter).
- Generate exactly ONE frontmatter block. No extra `---` dividers in the document body.
- No code fences around the entire output.

YAML FRONTMATTER:
- `description`: One real English sentence. Never leave placeholder text.
- `tags`: 2-5 lowercase domain keywords (e.g., [combat, ai, boss]). Not entity tags.
- `system_scope`: One of: world, player, entity, ui, audio, combat, environment, inventory,
  crafting, network, brain, locomotion, physics, fx. Pick the most accurate.
- `last_updated`, `build_version`, `change_status`, `category_type`, `source_hash`: copy exactly.

CONTENT RULES:
- All content must come ONLY from the source code or provided JSON. Do NOT invent APIs.
- Never repeat the same line or bullet point more than once.
- No greetings, sign-offs, meta-commentary, or filler text.
- No emojis or unicode symbols.

MDX COMPATIBILITY (Docusaurus fails on bare JSX tokens):
- Wrap in backticks: `<`, `>`, `<=`, `>=`, `{{`, `}}`
- Example: write `value <= 0` not value <= 0 in prose.
- Never leave bare angle brackets or curly braces in plain text.
- Do NOT use unescaped `{{` or `}}` in regular prose.

HEADING RULES:
- Sentence case: "Main functions" not "Main Functions". Proper nouns/acronyms stay capitalized.
- Never skip heading levels. `###` only under `##`. No `####` unless absolutely necessary.

SHORT FILES:
- If source is small or simple, keep docs proportionally short.
- If a section has no content, write "Not applicable" or "None identified" — do not invent.
- Events & listeners may be omitted if the component has none.

CONSTRUCTOR RULE:
- Document `Class(function(self, ...) ... end)` constructors accordingly.
- The first parameter after `self` may be `inst`, `data`, or any other name — document as-is.

PROPERTIES TABLE:
- Columns: Property | Type | Default Value | Description
- If no properties exist, write header and separator row only (no data rows).
- Do NOT invent properties not in the constructor JSON.

COMPLETENESS:
- Keep ALL functions — never drop trivial getters/setters.
- If a function appears in multiple chunks, prefer the entry with more parameter/return detail.
- Merge all events, dependencies, and tags; never drop an entry.
- If a field has no data, use "None" (string) or [] (empty array) — never omit the field.

OVERVIEW WRITING:
- State: what this component does + its role in the ECS system.
- Mention key relationships with other components (from Connected Files context).
- 2-5 sentences. No padding.

USAGE EXAMPLE WRITING:
- Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
- 5-15 lines. Use the component's actual function names from the documentation.
- No generic placeholder names.

INCOMPLETE FUNCTION HANDLING (chunk boundary):
- If a function body is cut off at chunk boundary, keep it and note "INCOMPLETE — continues in adjacent chunk".
- Do NOT skip or drop incomplete functions.
```

---

### Task 5: Create `skills/few_shot.md`

**Files:**
- Create: `skills/few_shot.md`
- Reference: `prompt.py` lines 154–212 (the `=== FEW-SHOT EXAMPLE ===` block)

- [ ] **Step 1: Copy SampleComp example verbatim from `prompt.py`**

Open `prompt.py` and locate `=== FEW-SHOT EXAMPLE ===` (line 154). Copy everything from that line through `(End of example)` (line 212) into `skills/few_shot.md`, with a header prepended:

```markdown
# Skill: few_shot

=== FEW-SHOT EXAMPLE ===
Below is a short example of the expected output format for a simple component. Use this as a reference for structure and tone — do NOT copy the content.

---
id: samplecomp
title: SampleComp
description: Manages a simple timer-based buff on an entity.
tags: [combat, buff]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: components
source_hash: abc123
system_scope: entity
---

# SampleComp

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleComp` applies a timed damage buff to an entity. It is typically added to combat-capable
prefabs and works alongside the `combat` component to modify outgoing damage for a fixed duration.

## Usage example
```lua
local inst = CreateEntity()
inst:AddComponent("samplecomp")
inst.components.samplecomp:SetDuration(10)
inst.components.samplecomp:Activate()
```

## Dependencies & tags
**Components used:** `combat`
**Tags:** Adds `buffed`; checks `debuffed`.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `duration` | number | `0` | How long the buff lasts in seconds. |
| `active` | boolean | `false` | Whether the buff is currently running. |

## Main functions
### `SetDuration(seconds)`
*   **Description:** Sets the total duration of the buff.
*   **Parameters:** `seconds` (number) - duration in seconds.
*   **Returns:** Nothing.

### `Activate()`
*   **Description:** Starts the buff timer and adds the `buffed` tag.
*   **Parameters:** None.
*   **Returns:** Nothing.
*   **Error states:** Returns early with no effect if `duration` is `<= 0`.

## Events & listeners
- **Listens to:** `onhitother` - refreshes the buff timer on hit.
- **Pushes:** `buff_expired` - fired when the timer reaches zero.
(End of example)
```

- [ ] **Step 2: Commit content files**

```bash
git add docs_SKILL.md skills/
git commit -m "feat: add skill content files and index (dst_conventions, function_format, quality_rules, few_shot)"
```

---

## Chunk 2: `skills_loader.py` (TDD)

**Note:** This project does NOT use pytest. Tests use the project's custom runner pattern:
`def test(name, condition, msg="")` + `python test_file.py`. Use `tempfile.TemporaryDirectory()`
instead of pytest fixtures. See `test_chunk_prompts.py` for the established convention.

---

### Task 6a: Write failing tests for `load_skill()`

**Files:**
- Create: `test_skills_loader.py` (project root)

- [ ] **Step 1: Write `test_skills_loader.py` with `load_skill` tests**

```python
"""
Tests for skills_loader.py — index parsing and skill file loading.
Run: .venv/Scripts/python test_skills_loader.py
"""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0

def test(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} -- {msg}")
        failed += 1


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_index(dirpath: str, skills: list[dict]) -> str:
    """Write docs_SKILL.md in dirpath. Returns absolute path to the index file."""
    lines = ["---", "version: 1", "---", ""]
    for s in skills:
        targets = ", ".join(s.get("inject_into", []))
        lines += [f"## {s['name']}", f"file: {s['file']}", f"inject_into: [{targets}]", ""]
    index_path = os.path.join(dirpath, "docs_SKILL.md")
    Path(index_path).write_text("\n".join(lines), encoding="utf-8")
    return index_path


def _make_skill(dirpath: str, rel_path: str, content: str) -> str:
    """Create a skill .md file at rel_path inside dirpath. Returns absolute path."""
    full = Path(dirpath) / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return str(full)


# ── load_skill tests ──────────────────────────────────────────────────────────

def run_load_skill_tests():
    from skills_loader import load_skill

    # T1: returns skill content
    with tempfile.TemporaryDirectory() as d:
        content = "# Skill: alpha\nHello world"
        _make_skill(d, "skills/alpha.md", content)
        idx = _make_index(d, [{"name": "alpha", "file": "skills/alpha.md", "inject_into": ["single_prompt"]}])
        result = load_skill("alpha", index_path=idx)
        test("load_skill returns file content", result == content, f"got: {result!r}")

    # T2: unknown name raises KeyError
    with tempfile.TemporaryDirectory() as d:
        idx = _make_index(d, [])
        try:
            load_skill("ghost", index_path=idx)
            test("load_skill unknown name raises KeyError", False, "no exception raised")
        except KeyError as e:
            test("load_skill unknown name raises KeyError", "not found" in str(e), str(e))

    # T3: skill file missing raises FileNotFoundError
    with tempfile.TemporaryDirectory() as d:
        idx = _make_index(d, [{"name": "missing", "file": "skills/missing.md", "inject_into": ["single_prompt"]}])
        try:
            load_skill("missing", index_path=idx)
            test("load_skill missing file raises FileNotFoundError", False, "no exception raised")
        except FileNotFoundError:
            test("load_skill missing file raises FileNotFoundError", True)

    # T4: reads utf-8 content correctly (Vietnamese characters)
    with tempfile.TemporaryDirectory() as d:
        content = "# Skill: utf\nViệt Nam — DST"
        _make_skill(d, "skills/utf.md", content)
        idx = _make_index(d, [{"name": "utf_skill", "file": "skills/utf.md", "inject_into": ["single_prompt"]}])
        result = load_skill("utf_skill", index_path=idx)
        test("load_skill reads utf-8 content", "Việt Nam" in result, f"got: {result!r}")

    # T5: malformed index — entry has no 'file:' line → ValueError
    # Malformed = a skill section that has inject_into but is missing the required 'file:' key.
    # Example malformed section:
    #   ## bad_skill
    #   inject_into: [single_prompt]
    #   (no 'file:' line)
    with tempfile.TemporaryDirectory() as d:
        bad_index = os.path.join(d, "docs_SKILL.md")
        Path(bad_index).write_text(
            "---\nversion: 1\n---\n\n## bad_skill\ninject_into: [single_prompt]\n",
            encoding="utf-8",
        )
        try:
            load_skill("bad_skill", index_path=bad_index)
            test("load_skill malformed index raises ValueError", False, "no exception raised")
        except ValueError as e:
            test("load_skill malformed index raises ValueError", "missing 'file:'" in str(e), str(e))


# ── load_skills_for tests ─────────────────────────────────────────────────────

def run_load_skills_for_tests():
    from skills_loader import load_skills_for

    # T6: filters by target, returns matching skills only
    with tempfile.TemporaryDirectory() as d:
        _make_skill(d, "skills/a.md", "content a")
        _make_skill(d, "skills/b.md", "content b")
        _make_skill(d, "skills/c.md", "content c")
        idx = _make_index(d, [
            {"name": "skill_a", "file": "skills/a.md", "inject_into": ["chunk_prompt", "single_prompt"]},
            {"name": "skill_b", "file": "skills/b.md", "inject_into": ["single_prompt"]},
            {"name": "skill_c", "file": "skills/c.md", "inject_into": ["merge_prompt"]},
        ])
        result = load_skills_for("single_prompt", index_path=idx)
        test("load_skills_for returns matching skills",
             set(result.keys()) == {"skill_a", "skill_b"} and result["skill_a"] == "content a",
             f"keys: {set(result.keys())}")

    # T7: no match → returns empty dict (not an error)
    with tempfile.TemporaryDirectory() as d:
        _make_skill(d, "skills/a.md", "content a")
        idx = _make_index(d, [{"name": "skill_a", "file": "skills/a.md", "inject_into": ["chunk_prompt"]}])
        result = load_skills_for("merge_prompt", index_path=idx)
        test("load_skills_for returns empty dict when no match", result == {}, f"got: {result}")

    # T8: all 3 allowed targets work as filters
    with tempfile.TemporaryDirectory() as d:
        for target in ("chunk_prompt", "merge_prompt", "single_prompt"):
            _make_skill(d, f"skills/{target}.md", f"content {target}")
        idx = _make_index(d, [
            {"name": "s1", "file": "skills/chunk_prompt.md",  "inject_into": ["chunk_prompt"]},
            {"name": "s2", "file": "skills/merge_prompt.md",  "inject_into": ["merge_prompt"]},
            {"name": "s3", "file": "skills/single_prompt.md", "inject_into": ["single_prompt"]},
        ])
        ok = (
            set(load_skills_for("chunk_prompt",  index_path=idx).keys()) == {"s1"} and
            set(load_skills_for("merge_prompt",  index_path=idx).keys()) == {"s2"} and
            set(load_skills_for("single_prompt", index_path=idx).keys()) == {"s3"}
        )
        test("load_skills_for all 3 targets work", ok)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== load_skill tests ===")
    run_load_skill_tests()
    print("\n=== load_skills_for tests ===")
    run_load_skills_for_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run — confirm RED (all fail with ImportError)**

```bash
.venv/Scripts/python test_skills_loader.py
```

Expected output: `ModuleNotFoundError: No module named 'skills_loader'` (the import at the top of each function will crash).
If any test somehow passes, the test itself is wrong — fix it before continuing.

---

### Task 6b: No additional tests needed — Task 6a covers all cases

`load_skills_for` tests are already included in `test_skills_loader.py` (T6–T8 in `run_load_skills_for_tests`).

---

### Task 7: Implement `skills_loader.py`

**Files:**
- Create: `skills_loader.py` (project root)

- [ ] **Step 1: Write minimal implementation**

```python
"""
skills_loader — parse docs_SKILL.md index and load skill markdown files.

API:
    load_skill(name, *, index_path="docs_SKILL.md") -> str
    load_skills_for(target, *, index_path="docs_SKILL.md") -> dict[str, str]
"""
from pathlib import Path


def _parse_index(index_path: str) -> dict[str, dict]:
    """
    Parse docs_SKILL.md and return {skill_name: {"file": str, "inject_into": list}}.

    Format expected:
        ---
        version: 1
        ---

        ## skill_name
        file: path/to/skill.md
        inject_into: [target1, target2]
    """
    import yaml

    path = Path(index_path)
    text = path.read_text(encoding="utf-8")

    # Split on newline + "## " to separate preamble from skill sections.
    # parts[0] = YAML preamble; parts[1:] = one section per skill.
    parts = text.split("\n## ")

    skills: dict[str, dict] = {}
    for part in parts[1:]:
        lines = [ln.strip() for ln in part.strip().splitlines()]
        if not lines:
            continue
        name = lines[0]
        entry: dict = {}
        for line in lines[1:]:
            if line.startswith("file:"):
                entry["file"] = line[len("file:"):].strip()
            elif line.startswith("inject_into:"):
                raw = line[len("inject_into:"):].strip()
                entry["inject_into"] = yaml.safe_load(raw) or []

        if "file" not in entry:
            raise ValueError(f"Skill '{name}' in index missing 'file:' field")

        skills[name] = entry

    return skills


def load_skill(name: str, *, index_path: str = "docs_SKILL.md") -> str:
    """Load a single skill by name. Returns raw markdown content (utf-8).

    Raises:
        KeyError: if name not in index.
        FileNotFoundError: if the skill .md file does not exist.
        ValueError: if the index entry is malformed (missing file: field).
    """
    skills = _parse_index(index_path)
    if name not in skills:
        raise KeyError(f"Skill '{name}' not found in {index_path}")

    root = Path(index_path).parent
    file_path = root / skills[name]["file"]

    if not file_path.exists():
        raise FileNotFoundError(
            f"Skill file '{skills[name]['file']}' not found (resolved to {file_path})"
        )

    return file_path.read_text(encoding="utf-8")


def load_skills_for(target: str, *, index_path: str = "docs_SKILL.md") -> dict[str, str]:
    """Return {name: content} for all skills whose inject_into includes target.

    Returns an empty dict if no skills match (not an error).
    """
    skills = _parse_index(index_path)
    return {
        name: load_skill(name, index_path=index_path)
        for name, entry in skills.items()
        if target in entry.get("inject_into", [])
    }
```

- [ ] **Step 2: Run tests — confirm GREEN (all pass)**

```bash
.venv/Scripts/python test_skills_loader.py
```

Expected output:
```
=== load_skill tests ===
  [PASS] load_skill returns file content
  [PASS] load_skill unknown name raises KeyError
  [PASS] load_skill missing file raises FileNotFoundError
  [PASS] load_skill reads utf-8 content
  [PASS] load_skill malformed index raises ValueError

=== load_skills_for tests ===
  [PASS] load_skills_for returns matching skills
  [PASS] load_skills_for returns empty dict when no match
  [PASS] load_skills_for all 3 targets work

8 passed, 0 failed
```

If any test fails, fix `skills_loader.py` and re-run. Do not proceed until all 8 pass.

- [ ] **Step 3: Run existing prompt test to verify no regression**

```bash
.venv/Scripts/python test_chunk_prompts.py
```

Expected: same pass/fail counts as before this change (prompt files are unchanged at this point).

- [ ] **Step 4: Commit**

```bash
git add skills_loader.py test_skills_loader.py
git commit -m "feat: add skills_loader with load_skill and load_skills_for"
```

---

## Chunk 3: Prompt integration

> **Prerequisites:** Chunk 1 and Chunk 2 must be completed first.
> Verify before starting:
> - `skills_loader.py` exists (created in Chunk 2)
> - `docs_SKILL.md` is populated with 4 skill entries (created in Chunk 1)
> - `test_skills_loader.py` exists and passes (created in Chunk 2)
> - `skills/` directory contains all 4 `.md` files (created in Chunk 1)

---

### Task 8: Update `chunked_prompt.py`

**Files:**
- Modify: `chunked_prompt.py`
- Note: Only the DST conventions block is replaced in each function. The `{_FUNCTION_FORMAT_SPEC}`
  reference inside `build_merge_prompt` is untouched — it will resolve to the module-level variable
  now loaded from the skill file.

- [ ] **Step 1: Add imports and module-level skill variables**

In `chunked_prompt.py`, after the existing imports (after line 17: `from pre_synthesis import PreSynthesisResult`), add:

```python
from skills_loader import load_skill

# Skill content loaded once at module import — injected into f-string prompts below.
# IMPORTANT: _FUNCTION_FORMAT_SPEC must keep this exact name — test_chunk_prompts.py
# imports it directly: `from chunked_prompt import ..., _FUNCTION_FORMAT_SPEC`
_FUNCTION_FORMAT_SPEC = load_skill("function_format")   # replaces inline constant; name preserved for test compat
_DST_CONV             = load_skill("dst_conventions")
```

- [ ] **Step 2: Remove the inline `_FUNCTION_FORMAT_SPEC` constant**

Delete the inline constant definition starting at line 19 (the line `_FUNCTION_FORMAT_SPEC = """`).
Delete through the closing `"""` of that block (line 67 in the original, the line after `* **Returns:** None`).

The variable is now assigned by `load_skill("function_format")` from the import added in Step 1.

- [ ] **Step 3: Replace DST conventions block in `build_chunk_prompt`**

Inside the `build_chunk_prompt` function's f-string, find the `5. DST CODING CONVENTIONS` section.
Locate and replace only the 6-bullet block that follows it (starting with `- DST uses an Entity Component System`):

```
   - DST uses an Entity Component System (ECS). Components are attached to entities via `inst:AddComponent("name")`.
   - `self.inst` refers to the entity instance that owns this component.
   - The constructor is defined as `Class(function(self, ...) ... end)`, NOT a traditional `_ctor` method.
     The first parameter after `self` varies by class (commonly `inst` for components, `data` for utility classes, etc.).
   - `inst:ListenForEvent(event, fn)` registers event listeners; `inst:PushEvent(event, data)` fires events.
   - Tags are added/removed via `inst:AddTag("tag")` / `inst:RemoveTag("tag")` and checked with `inst:HasTag("tag")`.
   - `self.inst.replica.X` refers to the network-replicated version of a component (client-server sync).
```

Replace with (note: `build_chunk_prompt` has no `{_FUNCTION_FORMAT_SPEC}` reference — only this DST block changes):
```
{_DST_CONV}
```

The `5. DST CODING CONVENTIONS` heading above stays unchanged.

- [ ] **Step 4: Replace DST conventions block in `build_merge_prompt`**

Inside the `build_merge_prompt` function's f-string, locate the identical 6-bullet DST block under `5. DST CODING CONVENTIONS`. Replace it with `{_DST_CONV}`. Do not touch the `{_FUNCTION_FORMAT_SPEC}` reference elsewhere in this function.

- [ ] **Step 5: Replace DST conventions block in `_build_merge_prompt_legacy`**

Inside the `_build_merge_prompt_legacy` function's f-string, locate the identical 6-bullet DST block. Replace it with `{_DST_CONV}`.

The existing `# TODO(format-consistency): apply _FUNCTION_FORMAT_SPEC here when legacy path is retired` comment above this function stays unchanged (it tracks a separate unrelated task).

- [ ] **Step 6: Verify `build_intermediate_merge_prompt` is unchanged**

Search `chunked_prompt.py` for `5. DST CODING CONVENTIONS` — it should now appear 0 times (all three have been replaced). Confirm `build_intermediate_merge_prompt` never had this block (it does not — no action needed).

- [ ] **Step 7: Run existing tests**

```bash
.venv/Scripts/python test_chunk_prompts.py
.venv/Scripts/python test_skills_loader.py
```

Expected: all tests PASS. `_FUNCTION_FORMAT_SPEC` is still a module-level variable, so imports from `test_chunk_prompts.py` line 9 still work.

If tests fail, check:
- Did `_FUNCTION_FORMAT_SPEC` get removed entirely instead of replaced by the import? Restore it.
- Are the `{_DST_CONV}` references inside f-strings (not in regular string context)?

---

### Task 9: Update `prompt.py`

**Files:**
- Modify: `prompt.py`

- [ ] **Step 1: Add imports and module-level skill variables**

In `prompt.py`, after the existing `from get_docs import (...)` block (after line 13), add:

```python
from skills_loader import load_skill

# Skill content loaded once at module import.
_DST_CONV = load_skill("dst_conventions")
_FEW_SHOT = load_skill("few_shot")
```

- [ ] **Step 2: Replace DST conventions block in `build_prompt`**

Inside `build_prompt` f-string, locate `5. DST CODING CONVENTIONS` (line 61 in the original file).
Replace the entire section starting at that label through the last DST bullet (the `self.inst.replica.X` line, line 68):

```
5. DST CODING CONVENTIONS
   - DST uses an Entity Component System (ECS). Components are attached to entities via `inst:AddComponent("name")`.
   - `self.inst` refers to the entity instance that owns this component.
   - The constructor is defined as `Class(function(self, ...) ... end)`, NOT a traditional `_ctor` method.
     The first parameter after `self` varies by class (commonly `inst` for components, `data` for utility classes, etc.).
   - `inst:ListenForEvent(event, fn)` registers event listeners; `inst:PushEvent(event, data)` fires events.
   - Tags are added/removed via `inst:AddTag("tag")` / `inst:RemoveTag("tag")` and checked with `inst:HasTag("tag")`.
   - `self.inst.replica.X` refers to the network-replicated version of a component (client-server sync).
```

Replace with (keep the section heading, replace only the bullets):
```
5. DST CODING CONVENTIONS
{_DST_CONV}
```

- [ ] **Step 3: Replace the few-shot block in `build_prompt`**

`skills/few_shot.md` contains the full section including `=== FEW-SHOT EXAMPLE ===` as its opening line.
In `build_prompt` f-string, locate the existing few-shot section (line 154 in original):

```
=== FEW-SHOT EXAMPLE ===
Below is a short example...
...
(End of example)
```

Replace the entire block (from `=== FEW-SHOT EXAMPLE ===` through `(End of example)`, inclusive) with:
```
{_FEW_SHOT}
```

The `{_FEW_SHOT}` variable already contains the `=== FEW-SHOT EXAMPLE ===` header — do NOT leave it in the f-string as well (it would appear twice).

- [ ] **Step 4: Run all tests and smoke-check**

```bash
.venv/Scripts/python test_skills_loader.py
.venv/Scripts/python test_chunk_prompts.py
```

Smoke-check that modules import and skill content is non-empty:

```bash
.venv/Scripts/python -c "from chunked_prompt import _DST_CONV, _FUNCTION_FORMAT_SPEC; assert _DST_CONV, '_DST_CONV is empty'; assert _FUNCTION_FORMAT_SPEC, '_FUNCTION_FORMAT_SPEC is empty'; print('chunked_prompt.py skills non-empty OK')"
.venv/Scripts/python -c "from prompt import _DST_CONV, _FEW_SHOT; assert _DST_CONV, '_DST_CONV is empty'; assert _FEW_SHOT, '_FEW_SHOT is empty'; print('prompt.py skills non-empty OK')"
```

Expected:
```
chunked_prompt.py skills non-empty OK
prompt.py skills non-empty OK
```

If `KeyError` or `FileNotFoundError` is raised, verify `docs_SKILL.md` has the correct skill name and `skills/` files exist.

- [ ] **Step 5: Commit**

```bash
git add chunked_prompt.py prompt.py
git commit -m "feat: inject dst_conventions and few_shot skills into prompt builders"
```

If either raises `KeyError` or `FileNotFoundError`, the skill file or index entry is missing — check `docs_SKILL.md` paths.

- [ ] **Step 5: Commit**

```bash
git add chunked_prompt.py prompt.py
git commit -m "feat: inject dst_conventions and few_shot skills into prompt builders"
```

---

## Done

All 9 tasks complete. The system is:
- `docs_SKILL.md` — editable index; add/remove skills here
- `skills/*.md` — editable domain knowledge; changes take effect on next process start
- `skills_loader.py` — loader with full test coverage
- `prompt.py`, `chunked_prompt.py` — use module-level skill variables in f-strings
