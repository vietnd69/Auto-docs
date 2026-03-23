# Skill: validator_writer

=== FORMAT RULES — NEVER VIOLATE ===
- NEVER rename or reformat ### headings (lines starting with "### `")
- NEVER change "* **Description:**", "* **Parameters:**",
  "* **Returns:**", "* **Error states:**" bullet labels
- NEVER convert bullet lists to numbered lists or tables
- Do NOT add or remove ### function entries UNLESS reviewer feedback explicitly says
  a function is missing or should be removed
- When adding a missing function entry, use the last line of the preceding ### block
  as old_text anchor, then append the new entry after it
- ONLY modify the TEXT CONTENT within the existing structure (unless adding/removing
  is explicitly required by reviewer feedback)
- old_text in each patch must be a MINIMAL substring (a single line or short phrase) —
  never use an entire function block as old_text
