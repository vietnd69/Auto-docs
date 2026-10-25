# Guardrails

- Only `dst-tools` may read source or change documents. Do not try shell, edit or web tools.
- Never invent functions, parameters, events, tags or return values.
- Never remove a checklist heading to make checks pass.
- A review finding must cite a source line range and a verbatim quote (`ledger_add`);
  findings without evidence are rejected by the tool — do not retry them reworded.
- Do not reopen a resolved finding unless you have new evidence.
- If the same check fails twice after your fix, stop changing that section and record the
  problem in the notes; do not loop.

# Skills

- When you start any documentation job, load the `doc-job` skill.
- When you write a `###` entry for a function, method, state, handler or prefab, load the `function-format` skill.
- When you review a page or a group of symbols, load the `review-symbols` skill.
- When the job is an update after a source change, load the `update-page` skill.
- When the page kind is `data` or the file is mostly tables, load the `data-reference` skill.
- When you change the page plan (split, merge, move pages), load the `plan-pages` skill.
- When you need DST engine background (ECS, events, replicas, stategraphs, brains), load the `dst-conventions` skill.
- When documenting a `*_replica.lua` file, load the `replica-pattern` skill.
- When writing prose sections (Overview, Usage example), load the `writing-guide` skill.
- When documenting a component file and you need a model page, load the `example-component` skill.
- When documenting a prefab file and you need a model page, load the `example-prefab` skill.
- When documenting a stategraph file and you need a model page, load the `example-stategraph` skill.
- When documenting a brain file and you need a model page, load the `example-brain` skill.
- When documenting a behaviour file and you need a model page, load the `example-behaviour` skill.
- When documenting a widget file and you need a model page, load the `example-widget` skill.
- When documenting a screen file and you need a model page, load the `example-screen` skill.
- When documenting a data file and you need a model page, load the `example-data` skill.
