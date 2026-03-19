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

## few_shot_data
file: skills/few_shot_data.md
inject_into: [single_prompt]
