"""Prompt templates for content validation writer and reviewer."""


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


def build_section_reviewer_prompt(section_text: str, lua_context: str) -> str:
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

    return f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.

{lua_instruction}

## Lua Context (functions referenced in this section)
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
) -> str:
    """Prompt for patching one markdown section based on review feedback."""
    feedback = ""
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback += f"{i}. Issue: {issue}\n"
        if suggestion:
            feedback += f"   Suggestion: {suggestion}\n"

    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"

    return f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.

Fix the following documentation section based on reviewer feedback.

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
