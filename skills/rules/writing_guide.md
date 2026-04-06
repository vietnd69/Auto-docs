---
name: writing_guide
description: How to write each documentation section — overview, usage examples, constructor rule, section-specific guidance
inject_into: [analyst, analyst_merge, analyst_merge_legacy]
---

# Writing Guide

## Constructor Rule

- Document `Class(function(self, ...) ... end)` constructors accordingly.
- The first parameter after `self` may be `inst`, `data`, or any other name — document as-is.

## Overview Writing

- [Component] State: what this component does + its role in the ECS system.
  Mention key relationships with other components (from Connected Files context).
- [Data config] State: what static data this file defines, how it is structured,
  and how other systems access it via require(). Do NOT describe it as a component
  or reference the ECS system.
- 2-5 sentences. No padding.

## Usage Example Writing

- [Component] Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
- [Data config] Show `require()` followed by index access to the returned table (e.g., `Table[1]`).
  Do NOT use `CreateEntity()`, `AddComponent`, or `inst.components`.
- 5-15 lines. Use a fenced code block with `lua` syntax highlighting.
- Use the component's actual function names from the documentation. No generic placeholder names.

## Dependencies & Tags Section

- **Components used:** List components accessed via `inst.components.X` or added via `inst:AddComponent("X")`.
- **Tags:** List any tags this component adds, removes, or checks (e.g., `inst:AddTag("tag")`).
- If none are apparent, write "None identified."

## Properties Section

- Create a Markdown table of key public variables/properties initialized in the constructor.
- Columns: `Property` | `Type` (infer if possible) | `Default Value` | `Description`.
- If no suitable properties, write "No public properties" instead of inventing content.

## Main Functions Section

- Document the core functional methods using the format defined in the function_format skill.
- For each function: Description, Parameters, Returns, Error states.
- Error states = crash or silent state corruption only. NOT normal conditional returns.

## Events & Listeners Section

- **Listens to:** Events registered via `inst:ListenForEvent(event, fn)`.
- **Pushes:** Events fired via `inst:PushEvent(event, data)`.
- If there are no events or listeners, omit this entire section.
