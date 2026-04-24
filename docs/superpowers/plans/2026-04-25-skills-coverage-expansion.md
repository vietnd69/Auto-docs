# Skills Coverage Expansion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mở rộng `skills/` để cover đủ 10+ file types trong `dst-scripts/`, fix inconsistencies giữa các skill hiện hữu, và enrich validation rules cho non-component file types.

**Architecture:** Skills là Markdown files với YAML frontmatter. `skills_loader.py` build registry từ `skills/{roles,knowledge,rules}/*.md` và `combine_skills(target)` concatenate theo thứ tự `roles → knowledge → rules`. Plan này thêm 6 skill files mới (5 few-shot + 1 replica pattern) và edit 5 skill files hiện có. Không sửa Python code.

**Tech Stack:** Markdown skill files với YAML frontmatter; Python 3.11 + uv workspace (`.venv/Scripts/python`); pytest; `prompts/src/prompts/skills_loader.py` đã có sẵn cơ chế registry.

---

## Background

Đánh giá hiện trạng (2026-04-25):

| File type trong `dst-scripts/` | Coverage | Status |
|--------------------------------|----------|--------|
| components/ (~110 files) | few_shot.md + dst_conventions.md + rules | ✅ |
| Data config root (~50 files) | few_shot_data.md + content_rules.md | ✅ |
| stategraphs/ (~150 files) | dst_conventions.md (rules only, no few-shot) | ⚠️ |
| brains/ (~80 files) | writing_guide.md (rules only, no few-shot) | ⚠️ |
| behaviours/ (~30 files) | nothing | ❌ |
| widgets/ (~150 files) | nothing | ❌ |
| screens/ (~80 files) | nothing | ❌ |
| prefabs/ | nothing | ❌ |
| `*_replica.lua` (~15 files) | nothing | ❌ |

Inconsistencies hiện hữu:
- `few_shot.md` viết `Returns: Nothing.` — `function_format.md` quy định `nil`.
- `format_rules.md` mandate `## Properties` luôn xuất hiện — `dst_conventions.md` (mục Stategraph Documentation Rules) cho phép Properties trống/skip cho stategraph.
- `function_format.md` không quy định: heading dùng `Foo()` hay `self:Foo()`, constructor có document như function entry không.

---

## Quick reference — files affected

| File | Action | Skill name | inject_into |
|------|--------|-----------|-------------|
| `skills/knowledge/few_shot.md` | Edit | `few_shot` | (unchanged) |
| `skills/rules/format_rules.md` | Edit | `format_rules` | (unchanged) |
| `skills/knowledge/few_shot_stategraph.md` | Create | `few_shot_stategraph` | `analyst, analyst_chunk` |
| `skills/knowledge/few_shot_brain.md` | Create | `few_shot_brain` | `analyst, analyst_chunk` |
| `skills/rules/content_rules.md` | Edit | `content_rules` | (unchanged) |
| `skills/knowledge/few_shot_behaviour.md` | Create | `few_shot_behaviour` | `analyst, analyst_chunk` |
| `skills/knowledge/few_shot_widget.md` | Create | `few_shot_widget` | `analyst, analyst_chunk` |
| `skills/knowledge/few_shot_screen.md` | Create | `few_shot_screen` | `analyst, analyst_chunk` |
| `skills/knowledge/few_shot_prefab.md` | Create | `few_shot_prefab` | `analyst, analyst_chunk` |
| `skills/rules/writing_guide.md` | Edit | `writing_guide` | (unchanged) |
| `skills/knowledge/function_format.md` | Edit | `function_format` | (unchanged) |
| `skills/knowledge/dst_conventions.md` | Edit | `dst_conventions` | (unchanged) |
| `skills/knowledge/replica_pattern.md` | Create | `replica_pattern` | `analyst, analyst_chunk, analyst_merge, reviewer_full, reviewer_typed` |
| `skills/roles/validator_reviewer.md` | Edit | `validator_reviewer` | (unchanged) |

Test command (chạy sau mỗi task tạo/edit skill):
```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
```
Expected: tất cả tests PASS, registry build sạch không có duplicate-name lỗi.

---

## Chunk 1: Quick fixes + stategraph & brain few-shots

Mục tiêu: dọn inconsistency trong skills hiện hữu, thêm 2 few-shot cao ROI nhất.

### Task 1: Fix `Returns: Nothing.` → `nil` trong few_shot.md

**Files:**
- Modify: `skills/knowledge/few_shot.md`

- [ ] **Step 1: Locate inconsistency**

Đọc `skills/knowledge/few_shot.md` lines 56-65. Hiện viết `*   **Returns:** Nothing.` ở 2 chỗ (function `SetDuration`, `Activate`).

- [ ] **Step 2: Replace with `nil`**

Thay tất cả 2 instance của `*   **Returns:** Nothing.` thành `*   **Returns:** nil`.

Lý do: `function_format.md` line 18 quy định `nil` cho không return value. Few-shot phải nhất quán với format spec để LLM không bị trùng tín hiệu trái ngược.

- [ ] **Step 3: Run skills_loader tests**

Run: `.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v`
Expected: PASS — frontmatter chưa thay đổi nên registry build OK.

- [ ] **Step 4: Commit**

```bash
git add skills/knowledge/few_shot.md
git commit -m "fix(skills): align few_shot.md Returns convention with function_format spec"
```

---

### Task 2: Resolve Properties section conflict cho stategraph trong format_rules.md

**Files:**
- Modify: `skills/rules/format_rules.md:11-15`

- [ ] **Step 1: Locate Section Order block**

`format_rules.md` lines 11-15 hiện chỉ cho phép omit `## Events & listeners`. Cần thêm exception cho `## Properties` khi file là stategraph và không có file-scope local tables.

- [ ] **Step 2: Replace Section Order block**

Replace text từ "## Section Order" tới "no `ListenForEvent` or `PushEvent` calls)." bằng:

```markdown
## Section Order

Never change this order:
`## Overview` → `## Usage example` → `## Dependencies & tags` → `## Properties` → `## Main functions` → `## Events & listeners`

Do NOT omit, reorder, or rename these sections.

**Allowed omissions:**
- `## Events & listeners` may be omitted when the source file has no events (no `ListenForEvent` or `PushEvent` calls).
- `## Properties` may be omitted ONLY for stategraph files with no file-scope local tables/constants. If any file-scope local exists (e.g., `ATTACK_PROP_MUST_TAGS`, `START_FACE_DIST`), Properties section is REQUIRED.

For all other file types, the Properties section is mandatory — use the `| None | | | No properties are defined. |` row when no properties exist.
```

- [ ] **Step 3: Run skills_loader tests + verify combine_skills output**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
.venv/Scripts/python -c "from prompts.skills_loader import combine_skills; print(combine_skills('analyst')[:2000])"
```
Expected: tests PASS; output chứa block "Allowed omissions:".

- [ ] **Step 4: Commit**

```bash
git add skills/rules/format_rules.md
git commit -m "fix(skills): allow Properties omission for stategraphs without file-scope locals"
```

---

### Task 3: Create few_shot_stategraph.md

**Files:**
- Create: `skills/knowledge/few_shot_stategraph.md`

- [ ] **Step 1: Verify target name không trùng**

```bash
grep -l "name: few_shot_stategraph" skills/ -r
```
Expected: no output (file chưa tồn tại).

- [ ] **Step 2: Write the file**

Nội dung đầy đủ:

````markdown
---
name: few_shot_stategraph
description: Stategraph file few-shot example — expected output for animation state machine documentation
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Stategraph File

HOW TO DETECT: source file calls `StateGraph(name, states, events, defaultstate, actionhandlers)` at top level
and defines `State{...}` entries → use this example.

Stategraphs are NOT components. Do NOT use `CreateEntity()` + `AddComponent()` patterns.
Mirror the structure below — do NOT copy the content.

```md
---
id: sgsample
title: SGSample
description: Animation state machine for the sample creature, defining locomotion, combat, and death states.
tags: [stategraph, ai, animation]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: stategraphs
source_hash: abc123
system_scope: entity
---

# SGSample

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SGSample` is an animation state machine attached to the `sample` prefab. It governs idle, walk, attack, and death animations and reacts to engine events such as `attacked`, `death`, and `locomote`. Stategraphs are accessed via `StartStateGraph()` on the entity, not called as utility functions. Major state categories: locomotion (idle, walk, run), combat (attack, hit), and lifecycle (death, taunt).

## Usage example
```lua
-- Stategraphs are attached to a prefab during construction:
inst:SetStateGraph("SGsample")

-- Trigger a state from external code:
inst.sg:GoToState("attack")

-- Query state-tag membership:
if inst.sg:HasStateTag("busy") then
    return
end

-- Listen for stategraph events from a component:
inst:ListenForEvent("attacked", function(inst, data)
    inst.sg:GoToState("hit")
end)
```

## Dependencies & tags
**External dependencies:**
- `stategraphs/commonstates` -- shared locomotion/death state factories

**Components used:**
- `combat` -- read attack damage and target
- `locomotor` -- queried for movement state during transitions
- `health` -- checked in `death` onenter to play final animation

**Tags:**
- `busy` -- added in attack/hit states to block other transitions
- `attack` -- added on attack onenter, removed on attack onexit

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `ATTACK_PROP_MUST_TAGS` | constant (local) | `{"_combat"}` | Tag filter passed to FindEntities when searching for attack targets. |
| `START_FACE_DIST` | constant (local) | `20` | Maximum distance at which the entity begins facing a player. |
| `KEEP_FACE_DIST` | constant (local) | `25` | Distance threshold beyond which face-tracking stops. |

## Main functions
### `onenter (attack)`
*   **Description:** Plays the attack animation, adds `busy` and `attack` tags, and locks the entity facing toward `inst.components.combat.target` for the duration of the swing.
*   **Parameters:** `inst` -- entity owning the stategraph
*   **Returns:** nil
*   **Error states:** Errors if `inst.components.combat` is nil — no nil guard before `inst.components.combat.target` access.

### `ontimeout (attack)`
*   **Description:** Triggered after the attack timer expires. Transitions to `idle` if the target is still alive, or `taunt` if the target was killed by the swing.
*   **Parameters:** `inst` -- entity owning the stategraph
*   **Returns:** nil
*   **Error states:** None.

### `onexit (death)`
*   **Description:** Removes the `busy` tag and clears any pending DoTaskInTime callbacks scheduled in onenter.
*   **Parameters:** `inst` -- entity owning the stategraph
*   **Returns:** nil
*   **Error states:** None.

## Events & listeners
- **Listens to:** `attacked` -- transition to `hit` state if not already busy.
- **Listens to:** `death` -- transition to `death` state.
- **Listens to:** `locomote` -- transition to `walk` or `idle` based on the locomotor's `wantstomove` flag.
```
````

- [ ] **Step 3: Verify registry picks it up**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
.venv/Scripts/python -c "from prompts.skills_loader import load_skill; print(load_skill('few_shot_stategraph')[:300])"
```
Expected: tests PASS; output prints the first 300 chars of the new skill body.

- [ ] **Step 4: Commit**

```bash
git add skills/knowledge/few_shot_stategraph.md
git commit -m "feat(skills): add few-shot example for stategraph file documentation"
```

---

### Task 4: Create few_shot_brain.md

**Files:**
- Create: `skills/knowledge/few_shot_brain.md`

- [ ] **Step 1: Write the file**

Nội dung đầy đủ:

````markdown
---
name: few_shot_brain
description: Brain file few-shot example — expected output for AI behavior tree documentation with local helper functions and file-scope constants
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Brain File

HOW TO DETECT: source file extends `Brain` class via `Class(Brain, ...)` or defines a Brain subclass that overrides `OnStart()` to return a `BehaviourTree`.

Brain files differ from components: they have NO Class(function(self, inst) ...) constructor that
defines self.X properties. Instead they have a small constructor + `OnStart()` returning a behaviour tree.
Local helper functions passed to behaviour nodes ARE part of the documented API — they encode AI logic.
File-scope constants ARE properties — they gate behaviour thresholds.

Mirror the structure below — do NOT copy the content.

```md
---
id: samplebrain
title: SampleBrain
description: AI brain for the sample creature, choosing between flee, eat, and idle behaviours based on player proximity and hunger state.
tags: [brain, ai, behaviour-tree]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: brains
source_hash: abc123
system_scope: brain
---

# SampleBrain

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleBrain` is the AI behaviour tree for the `sample` prefab. It selects between fleeing players within `SEE_PLAYER_DIST`, eating from nearby food sources, and idle wandering. Brains are paused when the entity is far from any player and resume automatically on player proximity. Brain trees are attached via `RunBrain(inst, SampleBrain)`.

## Usage example
```lua
-- Brains are attached during prefab construction:
local brain = require("brains/samplebrain")
inst:SetBrain(brain)

-- The framework calls OnStart() to obtain the behaviour tree.
-- Manual access to the running tree:
if inst.brain ~= nil and inst.brain.bt ~= nil then
    -- inspect or reset the running behaviour tree
end
```

## Dependencies & tags
**External dependencies:**
- `behaviourtree` -- BehaviourTree, SequenceNode, SelectorNode, etc.
- `behaviours/wander` -- Wander behaviour node factory
- `behaviours/runaway` -- RunAway behaviour node factory

**Components used:**
- `combat` -- read current target via `inst.components.combat.target`
- `hunger` -- queried for hunger threshold in EatFood node
- `locomotor` -- driven indirectly by Wander/RunAway nodes

**Tags:**
- `busy` -- checked before triggering the eat sequence (skip if entity is busy)

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `SEE_PLAYER_DIST` | constant (local) | `8` | Range in tiles within which the brain triggers the flee branch. |
| `WANDER_DIST` | constant (local) | `20` | Maximum wander radius from the entity's current home position. |
| `MIN_FOLLOW_DIST` | constant (local) | `3` | Minimum follow distance used by the FollowLeader node. |

## Main functions
### `OnStart()` (Brain method)
*   **Description:** Constructs the root SelectorNode of the behaviour tree: prioritises flee over eat over wander. Called once when the brain is attached and on resume after pause.
*   **Parameters:** `self` -- the brain instance (implicit via method syntax)
*   **Returns:** BehaviourTree root node
*   **Error states:** Errors if `self.inst` is nil at the moment OnStart fires (engine guarantees non-nil; included for completeness).

### `GetWanderPoint(inst)` (local)
*   **Description:** Helper passed to the Wander node. Returns the entity's home position table `{x, y, z}` so wandering recenters around its spawn point instead of drifting.
*   **Parameters:** `inst` -- entity owning the brain
*   **Returns:** position table `{x, y, z}` or `nil` if the entity has no recorded home
*   **Error states:** None.

### `ShouldRunAway(target)` (local)
*   **Description:** Helper passed to the RunAway node. Returns true if `target` is a player within `SEE_PLAYER_DIST` and the entity is not currently in a `busy` state.
*   **Parameters:** `target` -- candidate threat entity
*   **Returns:** boolean
*   **Error states:** None — guards `target == nil` and `target.HasTag` access internally.

## Events & listeners
None — brain trees react to component state, not engine events directly. Event handling is done in the brain's host stategraph or via component subscriptions.
```
````

- [ ] **Step 2: Verify registry**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
.venv/Scripts/python -c "from prompts.skills_loader import load_skill; print(load_skill('few_shot_brain')[:300])"
```
Expected: PASS; output prints body.

- [ ] **Step 3: Commit**

```bash
git add skills/knowledge/few_shot_brain.md
git commit -m "feat(skills): add few-shot example for brain file documentation"
```

---

### Task 5: End-to-end verification — Chunk 1

- [ ] **Step 1: Render full analyst prompt** for a sample brain file:

```bash
.venv/Scripts/python -c "from prompts.standard import build_prompt; from llm.paths import BASE_LUA_DIR; import sys; print(build_prompt(BASE_LUA_DIR / 'brains' / 'pigbrain.lua', dry_run=True)[:5000])" 2>&1 | head -100
```
Expected: prompt chứa block `## Few-Shot Example: Brain File` từ `few_shot_brain.md`.

- [ ] **Step 2: Re-run sample doc generation in dry-run mode**

```bash
MOD_DOC_DEBUG_PROMPTS=1 .venv/Scripts/mod-document dst-scripts/brains/pigbrain.lua --dry-run 2>&1 | tail -20
```
Expected: prompt được dump vào `.cache/debug_prompts/`. Manual check: file chứa cả `few_shot.md` + `few_shot_brain.md` trong skills block.

> Nếu `--dry-run` flag chưa tồn tại trong CLI thì chạy thực với 1 file nhỏ và dùng env `MOD_DOC_DEBUG_PROMPTS=1` để chỉ inspect prompt.

---

## Chunk 2: File type expansion (behaviour, widget, screen, prefab)

Mục tiêu: cover 4 file types còn lại với detection rules + few-shot riêng.

### Task 6: Mở rộng `content_rules.md` — File Type Classification

**Files:**
- Modify: `skills/rules/content_rules.md:16-34`

- [ ] **Step 1: Replace File Type Classification block**

Replace từ "## File Type Classification" tới hết phần "If yes → DATA CONFIG FILE." bằng:

```markdown
## File Type Classification

Determine before writing any section:

- **DATA CONFIG FILE**: no Class() constructor, no self.inst, returns a plain table/array.
  HOW TO DETECT: source file has NO `Class()` constructor, no `self.inst`, and returns
  a plain table/array at top level → DATA CONFIG FILE.
  → MUST apply ALL [Data config] rules. Use few_shot_data.

- **COMPONENT FILE**: has `Class(function(self, ...) ... end)` constructor and is in `components/` or attaches via `inst:AddComponent`.
  → MUST apply ALL [Component] rules. Use few_shot.

- **REPLICA FILE**: filename ends in `_replica.lua`, defines a Class with `net_*` netvar properties and `SetupRPCs`-style RPC registration.
  HOW TO DETECT: file in `components/` ends with `_replica.lua` AND constructor declares `self.X = net_bool(...)` or similar netvars.
  → Treat like a Component but document the master/replica relationship explicitly. See replica_pattern skill.

- **STATEGRAPH FILE**: calls `StateGraph(name, states, events, defaultstate, actionhandlers)`.
  HOW TO DETECT: file contains `StateGraph(` at top level and defines `State{...}` entries.
  → MUST apply STATEGRAPH rules (see dst_conventions). Use few_shot_stategraph.

- **BRAIN FILE**: defines a Brain class or returns a BehaviourTree via `Brain:new()` / `Class(Brain, ...)`.
  HOW TO DETECT: file in `brains/` extends `Brain` or imports `behaviourtree`.
  → Treat like a Component but with no constructor Properties; document local helper functions
  and file-scope constants. Use few_shot_brain.

- **BEHAVIOUR FILE**: file in `behaviours/` defines a single behavior node by extending `BehaviourNode`.
  HOW TO DETECT: file in `behaviours/` declares `MyBehaviour = Class(BehaviourNode, ...)`.
  → Document `Visit()`, `Reset()`, `DBString()` as Main functions. Usage example shows the node
  embedded in a SelectorNode/SequenceNode tree, not standalone. Use few_shot_behaviour.

- **WIDGET FILE**: file in `widgets/` extends `Widget` via `Class(Widget, ...)`.
  HOW TO DETECT: file imports `Widget` from `widgets/widget` and constructor calls `Widget._ctor(self, ...)`.
  → Document `_ctor`, `AddChild`-built children, event handlers (`OnGainFocus`, `OnLoseFocus`,
  `OnControl`). Usage example shows `screen:AddChild(MyWidget(...))`. Use few_shot_widget.

- **SCREEN FILE**: file in `screens/` extends `Screen` via `Class(Screen, ...)`.
  HOW TO DETECT: file imports `Screen` and is in `screens/` (or root-level screen file).
  → Document `_ctor`, `OnControl`, `OnUpdate`, navigation methods. Usage example shows
  `TheFrontEnd:PushScreen(MyScreen(...))`. Use few_shot_screen.

- **PREFAB FILE**: file in `prefabs/` calls `return Prefab(name, fn, assets, deps)` (or `MakePlayerCharacter`).
  HOW TO DETECT: top-level `return Prefab(...)` or wrapper macro returning a Prefab table.
  → Document `fn()` (the constructor entry point), `master_postinit`, the assets table,
  and the prefab table itself. Usage example: `SpawnPrefab("name")`. Use few_shot_prefab.

When signals are mixed (e.g., a brain file that also defines a local Widget), classify by the
file's primary export — what does the top-level `return` produce?

When in doubt, prefer the more specific classification (REPLICA over COMPONENT, BEHAVIOUR over
BRAIN) since their few-shots/rules are stricter subsets.
```

- [ ] **Step 2: Run tests**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add skills/rules/content_rules.md
git commit -m "feat(skills): expand file-type classification to behaviour/widget/screen/prefab/replica"
```

---

### Task 7: Create few_shot_behaviour.md

**Files:**
- Create: `skills/knowledge/few_shot_behaviour.md`

- [ ] **Step 1: Write the file**

````markdown
---
name: few_shot_behaviour
description: Behaviour node few-shot example — expected output for files in behaviours/ that extend BehaviourNode
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Behaviour File

HOW TO DETECT: file in `behaviours/` declares `MyBehaviour = Class(BehaviourNode, ...)`.
Behaviour files define a single AI node, not a full tree. They expose `Visit()`, `Reset()`,
`DBString()` and are consumed by Brain files via SelectorNode/SequenceNode composition.

Mirror the structure — do NOT copy the content.

```md
---
id: samplenode
title: SampleNode
description: BehaviourNode that runs a custom action while a predicate holds; reports SUCCESS once the action completes.
tags: [behaviour, ai, behaviour-tree]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: behaviours
source_hash: abc123
system_scope: brain
---

# SampleNode

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleNode` is a custom BehaviourNode that runs a target-driven action while a user-supplied predicate returns true. Returns READY/RUNNING/SUCCESS/FAILED in the standard BehaviourNode contract. Used by brains as a reusable subtree fragment composed inside SelectorNode/SequenceNode.

## Usage example
```lua
-- Embed inside a brain's behaviour tree:
local SampleNode = require("behaviours/samplenode")

local function ShouldRun(inst)
    return inst.components.hunger:GetPercent() < 0.5
end

local root = SelectorNode{
    SampleNode(self.inst, ShouldRun, 5),  -- run while predicate true, max 5s
    Wander(self.inst, GetHomePos, WANDER_DIST),
}
```

## Dependencies & tags
**External dependencies:**
- `behaviourtree` -- BehaviourNode base class, status constants (READY, RUNNING, SUCCESS, FAILED)

**Components used:**
- `combat` -- queried in Visit() for current target

**Tags:** None.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `inst` | entity | --- | Entity owning the behaviour. Set by constructor. |
| `predicate` | function | --- | Function `(inst) -> boolean`; node runs only while it returns true. |
| `maxtime` | number | `nil` | Optional time-out in seconds; node returns FAILED if exceeded. |
| `starttime` | number | `nil` | Internal: timestamp when Visit() first transitioned to RUNNING. |

## Main functions
### `_ctor(inst, predicate, maxtime)`
*   **Description:** Initialises a SampleNode bound to `inst`, gated by `predicate`, with optional `maxtime`. Calls `BehaviourNode._ctor(self, "SampleNode")`.
*   **Parameters:**
    - `inst` -- entity owning the behaviour
    - `predicate` -- function `(inst) -> boolean`
    - `maxtime` -- optional number, seconds before forced FAILED
*   **Returns:** nil
*   **Error states:** None — accepts nil maxtime and nil predicate (treats nil predicate as always-true).

### `Visit()`
*   **Description:** Called each tick by the parent node. Transitions status: READY → RUNNING when predicate true; RUNNING → SUCCESS when predicate goes false; RUNNING → FAILED when maxtime exceeded.
*   **Parameters:** None (uses self.inst, self.predicate, self.maxtime)
*   **Returns:** nil — sets self.status as side effect
*   **Error states:** Errors if `self.inst` is nil — no nil guard before predicate invocation.

### `Reset()`
*   **Description:** Called by the parent when the node is preempted. Clears `self.starttime` so the next Visit() starts fresh.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None.

### `DBString()`
*   **Description:** Debug string used by the brain debugger overlay; returns predicate state and elapsed time.
*   **Parameters:** None
*   **Returns:** string
*   **Error states:** None.

## Events & listeners
None.
```
````

- [ ] **Step 2: Verify + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
git add skills/knowledge/few_shot_behaviour.md
git commit -m "feat(skills): add few-shot example for behaviour node files"
```

---

### Task 8: Create few_shot_widget.md

**Files:**
- Create: `skills/knowledge/few_shot_widget.md`

- [ ] **Step 1: Write the file**

````markdown
---
name: few_shot_widget
description: Widget file few-shot example — expected output for UI widgets extending Widget class
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Widget File

HOW TO DETECT: file imports `Widget` from `widgets/widget` and constructor calls
`Widget._ctor(self, "MyWidget")`. Widgets are UI containers, not gameplay components.

Mirror the structure — do NOT copy the content.

```md
---
id: samplewidget
title: SampleWidget
description: A reusable label widget that displays a numeric value with an icon and updates on a periodic timer.
tags: [widget, ui]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: widgets
source_hash: abc123
system_scope: ui
---

# SampleWidget

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleWidget` is a UI widget extending `Widget`. It composes an icon `Image` and a `Text` label, exposes `SetValue()` for parents to push updates, and refreshes itself on a 0.5s tick. Embedded inside HUD screens via `screen:AddChild(SampleWidget())`.

## Usage example
```lua
local SampleWidget = require("widgets/samplewidget")

-- Inside a screen's _ctor:
self.sample = self:AddChild(SampleWidget("images/icon.tex", "icon_default"))
self.sample:SetPosition(0, 100, 0)
self.sample:SetValue(42)
```

## Dependencies & tags
**External dependencies:**
- `widgets/widget` -- Widget base class
- `widgets/text` -- Text child widget
- `widgets/image` -- Image child widget

**Components used:** None — widgets do not interact with ECS components directly.

**Tags:** None.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `icon` | Image | --- | Child image widget; created in `_ctor`. |
| `label` | Text | --- | Child text widget showing the current numeric value. |
| `value` | number | `0` | Current displayed value, updated via SetValue. |
| `update_task` | task | `nil` | Periodic refresh task scheduled in OnGainFocus, cancelled in OnLoseFocus. |

## Main functions
### `_ctor(atlas, tex)`
*   **Description:** Initialises the widget, calls `Widget._ctor(self, "SampleWidget")`, creates icon and label children, applies default styling.
*   **Parameters:**
    - `atlas` -- string atlas path for the icon
    - `tex` -- string texture name within the atlas
*   **Returns:** nil
*   **Error states:** None — Widget._ctor handles nil internally.

### `SetValue(value)`
*   **Description:** Updates `self.value` and rewrites the label text via `self.label:SetString(tostring(value))`.
*   **Parameters:** `value` -- number to display
*   **Returns:** nil
*   **Error states:** Errors if `self.label` is nil (would only occur if widget construction failed; no guard).

### `OnGainFocus()`
*   **Description:** Override of Widget:OnGainFocus(). Starts the periodic refresh task that polls source state every 0.5s.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None.

### `OnLoseFocus()`
*   **Description:** Override of Widget:OnLoseFocus(). Cancels the periodic refresh task to free resources.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None.

## Events & listeners
None — widgets typically expose callbacks via parent screens, not engine events.
```
````

- [ ] **Step 2: Verify + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
git add skills/knowledge/few_shot_widget.md
git commit -m "feat(skills): add few-shot example for widget UI files"
```

---

### Task 9: Create few_shot_screen.md

**Files:**
- Create: `skills/knowledge/few_shot_screen.md`

- [ ] **Step 1: Write the file**

````markdown
---
name: few_shot_screen
description: Screen file few-shot example — expected output for full-screen UI surfaces extending Screen class
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Screen File

HOW TO DETECT: file extends `Screen` via `Class(Screen, ...)`, lives in `screens/` (or root),
and is pushed onto the FrontEnd stack via `TheFrontEnd:PushScreen(MyScreen())`.

Mirror the structure — do NOT copy the content.

```md
---
id: samplescreen
title: SampleScreen
description: Modal popup screen presenting a confirm/cancel choice with keyboard and gamepad navigation.
tags: [screen, ui, modal]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: screens
source_hash: abc123
system_scope: ui
---

# SampleScreen

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleScreen` is a modal popup extending `Screen`. It darkens the underlying gameplay, presents a centered card with confirm and cancel buttons, and handles `CONTROL_ACCEPT` / `CONTROL_CANCEL` input. The screen invokes the supplied callback before popping itself off the FrontEnd stack.

## Usage example
```lua
local SampleScreen = require("screens/samplescreen")

local function OnConfirm()
    print("user confirmed")
end

TheFrontEnd:PushScreen(SampleScreen("Are you sure?", OnConfirm))
```

## Dependencies & tags
**External dependencies:**
- `widgets/screen` -- Screen base class
- `widgets/templates` -- StandardButton, StandardDialog factories
- `widgets/text` -- title/body text widgets

**Components used:** None.

**Tags:** None.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `prompt` | string | --- | The prompt text shown in the dialog body. |
| `on_confirm` | function | `nil` | Optional callback invoked when the user accepts. |
| `dialog` | Widget | --- | The StandardDialog child, parent of the buttons and text. |
| `confirm_btn` | Widget | --- | Confirm button child; bound to `OnConfirm`. |
| `cancel_btn` | Widget | --- | Cancel button child; bound to `OnCancel`. |

## Main functions
### `_ctor(prompt, on_confirm)`
*   **Description:** Initialises the screen, calls `Screen._ctor(self, "SampleScreen")`, builds the dialog widget tree, focuses the confirm button, and stores the callback.
*   **Parameters:**
    - `prompt` -- string shown in the dialog body
    - `on_confirm` -- optional function `()` invoked on accept
*   **Returns:** nil
*   **Error states:** None — accepts nil on_confirm.

### `OnControl(control, down)`
*   **Description:** Handles input. ACCEPT triggers `OnConfirm`, CANCEL triggers `OnCancel`. Returns true if the input was handled to suppress further propagation.
*   **Parameters:**
    - `control` -- one of CONTROL_* constants
    - `down` -- boolean (true on press, false on release)
*   **Returns:** boolean — true if handled
*   **Error states:** None.

### `OnConfirm()` (instance method)
*   **Description:** Invokes `self.on_confirm` if set, then pops this screen from the FrontEnd stack via `TheFrontEnd:PopScreen(self)`.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None — guards `on_confirm == nil`.

### `OnCancel()` (instance method)
*   **Description:** Pops this screen without invoking the callback.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None.

## Events & listeners
None — screens consume input via OnControl, not engine event subscriptions.
```
````

- [ ] **Step 2: Verify + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
git add skills/knowledge/few_shot_screen.md
git commit -m "feat(skills): add few-shot example for screen UI files"
```

---

### Task 10: Create few_shot_prefab.md

**Files:**
- Create: `skills/knowledge/few_shot_prefab.md`

- [ ] **Step 1: Write the file**

````markdown
---
name: few_shot_prefab
description: Prefab file few-shot example — expected output for entity prefab definitions returning Prefab(...)
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Prefab File

HOW TO DETECT: top-level `return Prefab(name, fn, assets, deps)` (or wrapper macro). The file
defines a spawnable entity, attaching components inside `fn()` and (on master) `master_postinit`.

Mirror the structure — do NOT copy the content.

```md
---
id: sampleprefab
title: SamplePrefab
description: Spawnable creature entity that combines combat, inventory, and locomotor components, attached to SGSample stategraph and samplebrain.
tags: [prefab, creature, entity]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: prefabs
source_hash: abc123
system_scope: entity
---

# SamplePrefab

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`sampleprefab.lua` registers a spawnable creature entity. The prefab's `fn()` constructor builds the physics body and attaches client-side components; `master_postinit` runs only on the server and attaches gameplay components (combat, health, inventory). The prefab is referenced by its name `"sampleprefab"` and instantiated with `SpawnPrefab("sampleprefab")`.

## Usage example
```lua
-- Spawn at world origin:
local inst = SpawnPrefab("sampleprefab")
inst.Transform:SetPosition(0, 0, 0)

-- Reference assets at load time:
local assets = {
    Asset("ANIM", "anim/sampleprefab.zip"),
    Asset("SOUND", "sound/sampleprefab.fsb"),
}
```

## Dependencies & tags
**External dependencies:**
- `stategraphs/SGsample` -- attached via `inst:SetStateGraph("SGsample")`
- `brains/samplebrain` -- attached via `inst:SetBrain(brain)`
- `prefabs/skinutils` -- skin-handling helpers

**Components used:**
- `combat` -- attack damage and target tracking
- `health` -- HP and death handling
- `inventory` -- carried items
- `locomotor` -- movement
- `eater` -- consume food items

**Tags:**
- `monster` -- added in fn() for combat targeting
- `character` -- added in fn() for AI selection

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `assets` | table | --- | Array of `Asset(...)` entries listing animation, sound, and texture files loaded with this prefab. |
| `prefabs` | table | `{...}` | Array of dependent prefab names (e.g., spawned drops) that must be loaded with this entity. |
| `TUNING.SAMPLE_HEALTH` | constant | `200` | Max HP applied to `health` component in master_postinit. |
| `TUNING.SAMPLE_DAMAGE` | constant | `25` | Damage value applied to `combat` component. |

## Main functions
### `fn()`
*   **Description:** Client-side prefab constructor. Creates the entity, builds physics, attaches AnimState, sets default animation, and adds tags. Returns `inst` so the framework can branch into master_postinit on the server.
*   **Parameters:** None
*   **Returns:** entity instance
*   **Error states:** None — runs on every host (client and server).

### `master_postinit(inst)`
*   **Description:** Server-only initialisation. Attaches gameplay components, sets stats from TUNING, attaches stategraph and brain. Skipped on clients (master_postinit is only invoked when `TheWorld.ismastersim` is true).
*   **Parameters:** `inst` -- entity returned from fn()
*   **Returns:** nil
*   **Error states:** Errors if `inst` is nil (engine guarantees non-nil; included for completeness).

## Events & listeners
- **Listens to (set up in master_postinit):** `attacked` -- triggers brain re-evaluation by clearing target.
- **Listens to:** `death` -- spawns loot via `inst.components.lootdropper:DropLoot()`.
```
````

- [ ] **Step 2: Verify + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
git add skills/knowledge/few_shot_prefab.md
git commit -m "feat(skills): add few-shot example for prefab definition files"
```

---

### Task 11: Update writing_guide.md với section guidance cho 4 file types mới

**Files:**
- Modify: `skills/rules/writing_guide.md` — append after "Brain Files — Main Functions" subsection.

- [ ] **Step 1: Append new sections**

Thêm sau line 60 (cuối của "Brain Files — Main Functions" block) các section sau:

```markdown
### Behaviour Files — Main Functions

For files in `behaviours/` extending `BehaviourNode`:
- Document `_ctor`, `Visit`, `Reset`, `DBString` as the primary functions.
- Properties section MUST list the constructor parameters as widget-style state (e.g., `inst`, `predicate`, `maxtime`)
  AND any internal cursor state (`starttime`, `running_action`).
- Usage example shows the node embedded inside a SelectorNode/SequenceNode tree, NOT instantiated standalone.
- Do NOT use `CreateEntity()` + `AddComponent()` patterns.

### Widget Files — Main Functions

For files in `widgets/` extending `Widget`:
- Document `_ctor` first, then layout/state methods (`SetValue`, `SetEnabled`, etc.), then lifecycle hooks
  (`OnGainFocus`, `OnLoseFocus`, `OnHide`, `OnShow`, `OnUpdate`, `OnControl`).
- Properties section lists child widgets created in `_ctor` (e.g., `icon`, `label`, `bg`) PLUS state values.
- Usage example shows `screen:AddChild(MyWidget(...))` followed by 1-2 method calls.
- Do NOT mention `inst.components` or ECS — widgets are pure UI.

### Screen Files — Main Functions

For files in `screens/` extending `Screen`:
- Document `_ctor`, `OnControl`, `OnUpdate`, plus user-facing methods (`OnConfirm`, `OnCancel`, navigation).
- Properties section lists child widgets and screen-state values (selection index, mode flags).
- Usage example shows `TheFrontEnd:PushScreen(MyScreen(...))`.
- Mention modal vs non-modal behaviour and which controls the screen captures.

### Prefab Files — Main Functions

For files in `prefabs/` returning `Prefab(...)`:
- Document `fn()` (client-side constructor) and `master_postinit(inst)` (server-only init) as primary functions.
- If the file defines `OnSave`, `OnLoad`, `OnEntityWake`, `OnEntitySleep`, document them as separate entries.
- Properties section lists `assets`, `prefabs` arrays + key `TUNING.*` constants the prefab consumes.
- Usage example shows `SpawnPrefab("name")` and the assets array.
- Dependencies & tags MUST list every component attached, every stategraph/brain set, every tag added.

### Replica Files — Main Functions

For files matching `*_replica.lua`:
- Document the constructor (declares netvars), each `Get*` accessor (read-only on client), and any
  `Set*` methods that route to the master via netvar assignment.
- Properties section lists every netvar (`net_bool`, `net_int`, `net_string`, etc.) with its default
  value and what state it mirrors from the master component.
- Usage example shows client-side access: `if inst.replica.combat:CanTarget(other) then ... end`.
- Mark methods that ONLY run on master with `(master only)` and methods that ONLY run on client with `(client only)`.
```

- [ ] **Step 2: Run tests + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
git add skills/rules/writing_guide.md
git commit -m "feat(skills): add writing guide sections for behaviour/widget/screen/prefab/replica"
```

---

### Task 12: End-to-end verification — Chunk 2

- [ ] **Step 1: Pick one file per new type and inspect generated prompt**

```bash
# Behaviour
MOD_DOC_DEBUG_PROMPTS=1 .venv/Scripts/python -c "from prompts.standard import build_prompt; from llm.paths import BASE_LUA_DIR; print(build_prompt(BASE_LUA_DIR / 'behaviours' / 'chaseandattack.lua', dry_run=True)[:500])"

# Widget
MOD_DOC_DEBUG_PROMPTS=1 .venv/Scripts/python -c "from prompts.standard import build_prompt; from llm.paths import BASE_LUA_DIR; print(build_prompt(BASE_LUA_DIR / 'widgets' / 'badge.lua', dry_run=True)[:500])"
```

> Nếu `build_prompt` không có `dry_run` flag, dùng `combine_skills('analyst')` để verify skills block.

Expected: prompt chứa block `## Few-Shot Example: <type>` cho từng loại.

- [ ] **Step 2: Optional — sinh thử 1 file mỗi loại** (chỉ chạy nếu cần verify quality)

```bash
.venv/Scripts/mod-document dst-scripts/behaviours/chaseandattack.lua
.venv/Scripts/mod-document dst-scripts/widgets/badge.lua
```

Manual review: output có dùng đúng pattern (ví dụ widget không có `CreateEntity()`).

---

## Chunk 3: Convention enrichment + replica + reviewer typed checks

Mục tiêu: lấp gap conventions còn lại và mở rộng reviewer per file type.

### Task 13: Enrich function_format.md với constructor + receiver + async conventions

**Files:**
- Modify: `skills/knowledge/function_format.md` — append before "## Few-Shot Example" (around line 67).

- [ ] **Step 1: Insert new conventions section**

Thêm trước "## Few-Shot Example":

```markdown
## Heading & Receiver Convention

- Function entry heading uses `### \`Name(params)\`` regardless of whether the function is
  declared as `function MyClass:Method(...)` or `function MyClass.Method(...)` in source.
- Do NOT include `self:` or `MyClass:` in the heading. The owning class is implied by the
  document's `## Main functions` section.
- For local helper functions in brain files, include the `(local)` marker AFTER the parens:
  `### \`GetWanderPoint(inst)\` (local)`.
- For functions named exactly `_ctor` (Widget/Screen/Behaviour constructors), keep the
  underscore: `### \`_ctor(prompt, on_confirm)\``.

## Constructors

- Component constructors are passed to `Class(function(self, inst) ... end)` — they are
  documented as Properties (the `self.X = value` assignments), NOT as a function entry.
- Widget/Screen/Behaviour constructors are explicit `_ctor` methods — they ARE documented as
  function entries in `## Main functions` with the parameter list.
- Brain constructors are typically empty/inherited — do NOT document them.

## Async / Coroutine Functions

- If a function is started via `inst:StartThread(...)` or contains `Sleep(...)` calls, prefix
  the Description with "**Coroutine.**" so readers know the function yields:
  `* **Description:** **Coroutine.** Periodically polls X and yields via Sleep(0.5)...`
- DoTaskInTime / DoPeriodicTask callbacks are NOT coroutines — do not mark them.
```

- [ ] **Step 2: Run tests + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
git add skills/knowledge/function_format.md
git commit -m "feat(skills): add heading/receiver/constructor/coroutine conventions to function_format"
```

---

### Task 14: Enrich dst_conventions.md với Save/Load + AnimState + SoundEmitter

**Files:**
- Modify: `skills/knowledge/dst_conventions.md` — append after "## Scheduler / Coroutines" section (around line 100).

- [ ] **Step 1: Append new convention sections**

```markdown
## Save / Load Lifecycle

- `OnSave(self)` — return a table of state to persist; called when world saves.
- `OnLoad(self, data)` — restore state from the saved table on world load.
- `OnEntityWake(self)` — called when entity becomes active (player nearby).
- `OnEntitySleep(self)` — called when entity goes idle (no players nearby).
- `OnRemoveEntity(self)` / `OnRemoveFromEntity(self)` — cleanup when entity is removed.

These are component-level hooks. Document them as Main functions when present.

## AnimState

- `inst.AnimState:PlayAnimation(name, loop)` — start an animation (single play unless loop=true).
- `inst.AnimState:PushAnimation(name, loop)` — queue after current animation finishes.
- `inst.AnimState:SetBank(bank)` / `SetBuild(build)` — switch animation bank/build at runtime.
- `inst.AnimState:OverrideSymbol(symbol, build, src)` — swap a single symbol for skin/customisation.
- Heavily used in stategraphs (`onenter`/`ontimeout`) and prefab fn().

## SoundEmitter

- `inst.SoundEmitter:PlaySound(path, name, volume, ...)` — play a one-shot or looping sound.
- `inst.SoundEmitter:KillSound(name)` — stop a named looping sound.
- `inst.SoundEmitter:SetParameter(name, param, value)` — adjust a live FMOD parameter.
- Common in stategraphs and combat reactions.

## Action System

- `ACTIONS.X` — action enum entries; consumed by ActionHandler.
- `ActionHandler(ACTIONS.X, "statename")` — stategraph action binding; routes a player verb to a state.
- `BufferedAction(doer, target, action, invobject)` — runtime instantiation of an action.
- `inst.components.X:GetValidActions(target, right)` — component hook returning available actions.

## Skin System

- `inst.skinname` — string identifier for the active skin.
- `inst.AnimState:OverrideSymbol(...)` driven by skin data is the typical render path.
- `Prefabs[name].SkinFn` — function applied during prefab construction to apply a skin.

## Replica / Master

- Replica filename pattern: `<componentname>_replica.lua`.
- Replicas mirror master state via netvars (`net_*`) and expose read-only Get*/Has* accessors on the client.
- Master-only methods MUST guard with `if not TheWorld.ismastersim then return end`.
- See `replica_pattern` skill for full replica file documentation conventions.
```

- [ ] **Step 2: Run tests + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
git add skills/knowledge/dst_conventions.md
git commit -m "feat(skills): add save/load, AnimState, SoundEmitter, action, skin, replica conventions"
```

---

### Task 15: Create replica_pattern.md

**Files:**
- Create: `skills/knowledge/replica_pattern.md`

- [ ] **Step 1: Write the file**

````markdown
---
name: replica_pattern
description: Replica component pattern — netvar mirroring, master/client routing, RPC registration, and documentation rules for *_replica.lua files
inject_into: [analyst, analyst_chunk, analyst_merge, reviewer_full, reviewer_typed]
---

## Replica Components

Files matching `components/*_replica.lua` are CLIENT-SIDE mirrors of master components. They
expose read-only state to the client via netvars and forward player-initiated actions back to
the master via RPCs.

### Detection

- Filename ends in `_replica.lua`.
- Constructor declares one or more `self.X = net_bool(self.inst.GUID, "ns.field", "ns.field_dirty")`-style netvars.
- Class name typically matches the master with `_replica` suffix (e.g., `Combat_Replica`).

### Document the master/replica relationship explicitly

The Overview MUST mention:
1. The corresponding master component (e.g., "mirrors `combat` master state to clients").
2. Which fields are mirrored via netvars.
3. Whether the replica forwards any RPCs back to the master.

### Properties section

List EVERY netvar with this format:

| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `_target` | net_entity | --- | Mirrors `Combat.target` from the master. Read via `GetTarget()`. |
| `_canattack` | net_bool | `true` | Mirrors `Combat.canattack`; gated by `Combat:CanAttackable()` on master. |

Default Value:
- For netvars, write the literal default (e.g., `true`, `0`, `""`) when source initialises it.
- If the netvar is initialised by an external setter rather than constructor literal, write `---`.

### Main functions

Group methods by execution context:

- **Constructor / `_ctor`**: declare netvars, register dirty event listeners.
- **Getters (client-readable)**: `GetTarget()`, `IsAttacker()` — mark `(client read)`.
- **Setters (master-only)**: `SetTarget(target)`, `SetCanAttack(b)` — mark `(master only)`.
- **RPC handlers**: methods registered via `AddRPCHandler(...)` — mark `(RPC handler)`.

Format example:

```md
### `GetTarget()` (client read)
*   **Description:** Returns the entity currently mirrored from `master.combat.target`. Safe to call on both client and master.
*   **Parameters:** None
*   **Returns:** entity or `nil`
*   **Error states:** None.

### `SetTarget(target)` (master only)
*   **Description:** Updates `_target` netvar and propagates to clients on next network tick. No-op on client.
*   **Parameters:** `target` -- entity instance or `nil` to clear
*   **Returns:** nil
*   **Error states:** Errors if called on client without master guard. Source typically guards with `if not TheWorld.ismastersim then return end`; if absent, list as error state.
```

### Usage example

Show client-side query first, then optional master-side mutation:

```lua
-- Client-side read:
if inst.replica.combat ~= nil then
    local target = inst.replica.combat:GetTarget()
end

-- Master-side mutation (only valid on server):
if TheWorld.ismastersim then
    inst.replica.combat:SetTarget(some_entity)
end
```

### Reviewer note

The reviewer MUST check that:
- Each netvar declared in source appears in the Properties table.
- Methods with master-only guards are correctly marked `(master only)`.
- The replica's relationship to its master component is stated in Overview.
````

- [ ] **Step 2: Verify + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
.venv/Scripts/python -c "from prompts.skills_loader import load_skill; print(load_skill('replica_pattern')[:300])"
git add skills/knowledge/replica_pattern.md
git commit -m "feat(skills): add replica component pattern skill for *_replica.lua files"
```

---

### Task 16: Add typed reviewer checks per file type to validator_reviewer.md

**Files:**
- Modify: `skills/roles/validator_reviewer.md` — append before "## Special Case: need_special_case" (around line 128).

- [ ] **Step 1: Insert new section**

```markdown
## Typed Checks per File Type

Apply these AFTER the generic checklist. The file type is determined by the rules in
`content_rules` (DATA CONFIG / COMPONENT / REPLICA / STATEGRAPH / BRAIN / BEHAVIOUR / WIDGET /
SCREEN / PREFAB).

### Stategraph file checks
- Main functions headings follow `### \`onenter (statename)\`` / `### \`ontimeout (statename)\`` /
  `### \`onexit (statename)\``. Flag if a state's onenter contains non-trivial logic but no entry exists.
- Properties section lists ONLY file-scope locals (e.g., `ATTACK_PROP_MUST_TAGS`). State-local
  variables MUST NOT appear.
- Events & listeners lists EventHandler entries that react to ENGINE events, not state-internal handlers.
- Usage example uses `inst.sg:GoToState(...)` / `inst.sg:HasStateTag(...)`, NOT `CreateEntity()` + `AddComponent()`.

### Brain file checks
- `OnStart()` is documented and the description names the root SelectorNode/SequenceNode children.
- Local helper functions passed as callbacks to behaviour nodes are documented with `(local)` marker.
- File-scope constants gating behaviour (e.g., `START_FACE_DIST = 20`) appear in the Properties table.
- Events & listeners section is typically `None` — flag only if source actually has ListenForEvent.

### Behaviour file checks
- `Visit`, `Reset`, `DBString` are documented (they form the BehaviourNode contract).
- `_ctor` is documented as a function entry with parameter list.
- Usage example shows the node embedded inside a SelectorNode/SequenceNode tree, not a standalone
  call.

### Widget file checks
- `_ctor` is documented and lists every constructor parameter.
- Child widgets created via `self:AddChild(...)` appear in the Properties table.
- Usage example uses `screen:AddChild(MyWidget(...))`. NEVER `CreateEntity` or `AddComponent`.
- No mention of `inst.components` (widgets do not interact with ECS).

### Screen file checks
- `_ctor`, `OnControl` documented; `OnUpdate` documented if present.
- Usage example shows `TheFrontEnd:PushScreen(MyScreen(...))`.
- Properties section lists child widgets and screen state.

### Prefab file checks
- `fn()` and `master_postinit(inst)` documented as separate function entries.
- Properties table lists `assets`, `prefabs` arrays + key TUNING constants consumed by the prefab.
- Dependencies & tags lists every component attached, the stategraph set, the brain set,
  and every tag added in fn() or master_postinit.
- Usage example uses `SpawnPrefab("name")`.

### Replica file checks (per replica_pattern skill)
- Every netvar declared in source appears in the Properties table.
- Methods are marked `(master only)` / `(client read)` / `(RPC handler)` as applicable.
- Overview states the corresponding master component name and what fields are mirrored.
```

- [ ] **Step 2: Run tests + Commit**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
git add skills/roles/validator_reviewer.md
git commit -m "feat(skills): add typed reviewer checks for stategraph/brain/behaviour/widget/screen/prefab/replica"
```

---

### Task 17: End-to-end verification — Chunk 3

- [ ] **Step 1: Smoke-test the full registry**

```bash
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
.venv/Scripts/python -c "from prompts.skills_loader import _build_registry; r = _build_registry(); print(f'Registry has {len(r)} skills:'); [print(f'  {n}: inject_into={e[\"inject_into\"]}') for n, e in sorted(r.items())]"
```
Expected: 6 new skills in registry (few_shot_stategraph, few_shot_brain, few_shot_behaviour, few_shot_widget, few_shot_screen, few_shot_prefab, replica_pattern). All `inject_into` targets resolve.

- [ ] **Step 2: Verify combine_skills output for each role**

```bash
.venv/Scripts/python -c "
from prompts.skills_loader import combine_skills
for target in ['analyst', 'analyst_chunk', 'analyst_merge', 'reviewer_full', 'writer_full']:
    out = combine_skills(target)
    print(f'\n=== {target} ({len(out)} chars) ===')
    # List skill section headers
    for line in out.split('\n'):
        if line.startswith('## ') or (line.startswith('---') and line.strip() == '---'):
            print(line[:80])
"
```
Expected: each role's combined output includes the relevant new skills.

- [ ] **Step 3: Run a real generation against one file per type**

```bash
# Pick small representative files
.venv/Scripts/mod-document dst-scripts/behaviours/chaseandattack.lua
.venv/Scripts/mod-document dst-scripts/components/combat_replica.lua
```

Manual review: outputs follow the new few-shots and writing-guide rules.

- [ ] **Step 4: Run validator on the regenerated docs**

```bash
.venv/Scripts/python -m validator dst-api-webdocs/docs/behaviours/chaseandattack.md
.venv/Scripts/python -m validator dst-api-webdocs/docs/components/combat_replica.md
```
Expected: validator passes (or surfaces only known content issues, not format/structural failures).

---

## Final commit message log (for reference)

After all chunks, the branch should have ~12-15 commits with this prefix pattern:
- `fix(skills): ...` — for inconsistency fixes (Tasks 1, 2)
- `feat(skills): ...` — for new few-shot files and content rules expansion (Tasks 3-15)

---

## Risk notes

1. **Few-shot pollution**: each new few-shot file injected into `analyst, analyst_chunk` adds
   ~80 lines to the prompt. With 6 new few-shots, the analyst prompt grows by ~500 lines.
   This may push some files over `PROMPT_TOKEN_LIMIT = 16,000` and trigger chunked pipeline
   for files that previously used standard. If observed, narrow `inject_into` to only the
   types actually generated (e.g., `few_shot_widget` only when file is in `widgets/`).
   This requires extending `skills_loader` to support file-path-conditional injection — out
   of scope for this plan; track as follow-up.

2. **Reviewer over-flagging**: typed checks (Task 16) may flag existing docs as missing
   `(master only)` markers etc. Existing docs were not generated under these rules, so
   first-run validator may produce many findings. Mitigation: run validator on a sample of
   5-10 newly-regenerated docs first to confirm the rules work, then sweep the rest.

3. **Properties section omission for stategraph (Task 2)**: the `format_rules.md` change is
   permissive — it ALLOWS omission, doesn't require it. If the analyst already writes
   `| None | | | ... |` rows, no behavioural change. Test with one stategraph that has
   file-scope locals and one that doesn't.

---

## Out of scope (track as follow-ups)

- File-path-conditional skill injection (mention in Risk #1) — would let us inject only the
  matching few-shot per file type rather than all 8.
- Bullet style normalisation across all skills (`*` vs `-` vs `*   `) — purely cosmetic; defer.
- Scenario/NIS/map/util/tools file types — these have very few files and inconsistent patterns;
  defer until specific quality issues surface.
- A `changelog` entry summarising the skills coverage expansion — generate via
  `.venv/Scripts/python -m core.changelog` after the plan ships.
