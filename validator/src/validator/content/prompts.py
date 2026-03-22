"""Prompt templates for content validation writer and reviewer."""

from prompts.skills_loader import load_skill

# Skills loaded once at module import — same knowledge base as generation prompts
_QUALITY_RULES = load_skill("quality_rules")
_DST_CONV = load_skill("dst_conventions")
_FN_FORMAT = load_skill("function_format")

_SECTION_ORDER = (
    "## Overview → ## Usage example → ## Dependencies & tags "
    "→ ## Properties → ## Main functions → ## Events & listeners"
)

# Focused per-section requirements (what this section MUST contain)
_SECTION_REQUIREMENTS: dict[str, str] = {
    "## Overview": (
        "[Component] 2-5 sentences: what this component does + its role in ECS. "
        "Mention key relationships with other components.\n"
        "[Data config] 2-5 sentences: what static data this file defines, how it is structured, "
        "and how other systems access it via require(). Do NOT reference ECS or AddComponent."
    ),
    "## Usage example": (
        "5-15 lines of realistic Lua using actual function names from this file.\n"
        "[Component] Show CreateEntity(), AddComponent(), then call 2-3 primary functions.\n"
        "[Data config] Show require() followed by table index access (e.g. Table[1]). "
        "No CreateEntity(), AddComponent(), or inst.components."
    ),
    "## Dependencies & tags": (
        "Must contain EXACTLY these labels (in order):\n"
        "**External dependencies:** — list each `name` -- usage, or omit if none\n"
        "**Components used:** — list each `component_name` -- methods/properties accessed\n"
        "**Tags:** — list each `tag_name` -- add/remove/check, or 'None' if no game tags"
    ),
    "## Properties": (
        "Table with columns: Property | Type | Default Value | Description.\n"
        "If no properties exist, write header + separator row only (no data rows).\n"
        "Do NOT invent properties not in the constructor. "
        "Data config files: document the top-level container + each record field."
    ),
    "## Main functions": (
        "Each entry MUST use this EXACT structure:\n"
        "### `FunctionName(params)`\n"
        "* **Description:** one-line summary\n"
        "* **Parameters:** `param` -- type and purpose, or None\n"
        "* **Returns:** return value description, or nil\n"
        "* **Error states:** edge cases (omit this bullet entirely if none)\n"
        "Keep ALL functions — never drop trivial getters/setters."
    ),
    "## Events & listeners": (
        "- **Listens to:** events registered via inst:ListenForEvent(event, fn)\n"
        "- **Pushes:** events fired via inst:PushEvent(event, data)\n"
        "Omit this section entirely if the component has no events."
    ),
}


def _section_context(heading: str) -> str:
    """Return focused requirement block for a given ## heading."""
    req = _SECTION_REQUIREMENTS.get(heading)
    if not req:
        return ""
    return f"## This section — {heading}\n{req}\n\n"


_FORMAT_CONTRACT = """\
## FORMAT CONTRACT (## Main functions entries)
Each function entry MUST follow this exact structure:
### `FunctionName(params)`
* **Description:** one-line summary
* **Parameters:**
  - `name` (type) -- description
* **Returns:** description
* **Error states:** description  (only if applicable)

CHECK BOTH:
1. Content accuracy — params match Lua source, descriptions correct, no hallucinated APIs
2. Format compliance — structure matches FORMAT CONTRACT above

Flag format violations as issues just like content errors.
"""

_FORMAT_RULES = """\
## FORMAT RULES — NEVER VIOLATE
- NEVER rename or reformat ### headings (lines starting with "### `")
- NEVER change "* **Description:**", "* **Parameters:**",
  "* **Returns:**", "* **Error states:**" bullet labels
- NEVER convert bullet lists to numbered lists or tables
- NEVER add or remove ### function entries
- ONLY modify the TEXT CONTENT within the existing structure
- old_text in each patch must be a MINIMAL substring (a single line or short phrase) —
  never use an entire function block as old_text
"""


def build_reviewer_prompt(
    md_content: str,
    lua_source: str,
    connected_content: str,
) -> str:
    """Build prompt for LLM2 (reviewer) to review documentation accuracy."""
    connected_block = connected_content if connected_content else "(none)"
    return f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.

Review the following markdown documentation against its Lua source code. Check for:
1. Function signatures and parameters match the Lua source — detect hallucination
2. Code examples match actual API usage
3. Descriptions are accurate and complete
4. Connected references are mentioned correctly

## Lua Source Code
```lua
{lua_source}
```

## Connected Content (referenced files)
{connected_block}

## Documentation to Review
{md_content}

## Response Format
Respond in JSON only:
```json
{{
    "approved": true/false,
    "issues": ["list of specific problems found"],
    "suggestions": ["list of specific fix suggestions"]
}}
```

If the documentation is accurate and complete, set approved=true with empty lists.
If there are problems, set approved=false and list each issue with a specific suggestion to fix it."""


def build_writer_prompt(
    md_content: str,
    lua_source: str,
    connected_content: str,
    issues: list[str],
    suggestions: list[str],
) -> str:
    """Build prompt for LLM1 (writer) to fix documentation based on review feedback."""
    feedback = ""
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback += f"{i}. Issue: {issue}\n"
        if suggestion:
            feedback += f"   Suggestion: {suggestion}\n"

    connected_block = connected_content if connected_content else "(none)"
    return f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.

Fix the following documentation based on reviewer feedback. Return ONLY targeted patches, not the entire document.

## Lua Source Code (ground truth)
```lua
{lua_source}
```

## Connected Content
{connected_block}

## Current Documentation
{md_content}

## Reviewer Feedback
{feedback}

## Response Format
Return a JSON array of patches. Each patch replaces a specific text segment:
```json
[
    {{
        "old_text": "exact text to find in the document",
        "new_text": "replacement text",
        "reason": "why this change is needed"
    }}
]
```

Rules:
- old_text must be an EXACT substring of the current document
- Keep patches minimal — only change what's needed to fix the issues
- Do NOT modify YAML frontmatter
- Preserve markdown formatting and structure"""


def build_section_reviewer_prompt(
    section_text: str,
    lua_context: str,
    section_heading: str = "",
    file_type: str = "component",
) -> str:
    """Prompt for reviewing one markdown section against its focused Lua context."""
    if lua_context:
        lua_block = f"```lua\n{lua_context}\n```"
        lua_instruction = "Review the section against the Lua functions below."
    else:
        lua_block = "(none — no Lua functions referenced in this section)"
        lua_instruction = (
            "No Lua context available — review structural accuracy "
            "and internal consistency only."
        )

    section_ctx = _section_context(section_heading)
    # FORMAT CONTRACT only relevant for ## Main functions
    format_block = _FORMAT_CONTRACT if section_heading == "## Main functions" else ""

    return f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.

{lua_instruction}

## File type
This file is a **{file_type}** ({"component with Class() constructor and self.inst" if file_type == "component" else "data config — returns a plain table/array, no Class() constructor"}).

## Document structure
Full section order: {_SECTION_ORDER}
You are reviewing: **{section_heading or "(preamble)"}**

{section_ctx}## DST coding conventions
{_DST_CONV}

## Quality rules
{_QUALITY_RULES}

{format_block}## Lua Context (functions referenced in this section)
{lua_block}

## Section to Review
{section_text}

## Response Format
Respond in JSON only:
```json
{{
    "approved": true/false,
    "issues": ["list of specific problems found"],
    "suggestions": ["list of specific fix suggestions"]
}}
```

If the section is accurate and complete, set approved=true with empty lists.
If there are problems, set approved=false and list each issue with a specific suggestion."""


def build_section_writer_prompt(
    section_text: str,
    lua_context: str,
    issues: list[str],
    suggestions: list[str],
    section_heading: str = "",
    file_type: str = "component",
) -> str:
    """Prompt for patching one markdown section based on review feedback."""
    feedback = ""
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback += f"{i}. Issue: {issue}\n"
        if suggestion:
            feedback += f"   Suggestion: {suggestion}\n"

    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"
    section_ctx = _section_context(section_heading)

    return f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.

Fix the following documentation section based on reviewer feedback.

## File type
This file is a **{file_type}** ({"component with Class() constructor and self.inst" if file_type == "component" else "data config — returns a plain table/array, no Class() constructor"}).

## Document structure
Full section order: {_SECTION_ORDER}
You are fixing: **{section_heading or "(preamble)"}**

{section_ctx}## DST coding conventions
{_DST_CONV}

## Quality rules
{_QUALITY_RULES}

{_FORMAT_RULES}
## Lua Context (ground truth for this section)
{lua_block}

## Current Section
{section_text}

## Reviewer Feedback
{feedback}

## Response Format
Return a JSON array of patches:
```json
[
    {{
        "old_text": "exact text to find in this section only",
        "new_text": "replacement text",
        "reason": "why this change is needed"
    }}
]
```

Rules:
- old_text must be an EXACT substring of the section shown above (not the full document)
- Do not use overlapping old_text values within a single response
- Keep patches minimal — only change what is needed to fix the issues
- Do NOT modify YAML frontmatter"""
