"""Prompt templates for content validation writer and reviewer."""

import re
from prompts.skills_loader import load_skill

# Doc-writing skills reused by validator
_QUALITY_RULES = load_skill("quality_rules")
_FN_FORMAT = load_skill("function_format")

# Validator-specific skills (separate from doc generation)
_REVIEWER_SKILL = load_skill("validator_reviewer")
_WRITER_SKILL = load_skill("validator_writer")


def _parse_section_requirements(skill_text: str) -> dict[str, str]:
    """Parse '=== SECTION ## Heading ===' blocks from the reviewer skill file."""
    pattern = r"=== SECTION (## .+?) ===\n(.*?)(?==== SECTION|$)"
    return {
        m.group(1).strip(): m.group(2).strip()
        for m in re.finditer(pattern, skill_text, re.DOTALL)
    }


# Section requirements sourced from validator_reviewer.md — edit there to tune
_SECTION_REQUIREMENTS: dict[str, str] = _parse_section_requirements(_REVIEWER_SKILL)


def _section_context(heading: str) -> str:
    """Return focused requirement block for a given ## heading."""
    req = _SECTION_REQUIREMENTS.get(heading)
    if not req:
        return ""
    return f"=== SECTION REQUIREMENTS: {heading} ===\n{req}\n\n"


def build_reviewer_prompt(
    md_content: str,
    lua_source: str,
    connected_content: str,
    previous_issues: list[str] | None = None,
    previous_suggestions: list[str] | None = None,
) -> str:
    """Build prompt for LLM2 (reviewer) to review documentation accuracy."""
    connected_block = connected_content if connected_content else "(none)"

    if previous_issues:
        prev_lines = []
        for i, issue in enumerate(previous_issues, 1):
            suggestion = previous_suggestions[i - 1] if previous_suggestions and i - 1 < len(previous_suggestions) else ""
            prev_lines.append(f"{i}. Issue: {issue}")
            if suggestion:
                prev_lines.append(f"   Was fixed with: {suggestion}")
        prev_block = "\n".join(prev_lines)
        previous_section = f"\n=== PREVIOUS ITERATION ISSUES (now patched — verify if resolved) ===\n{prev_block}\n"
    else:
        previous_section = ""

    return f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.
Your task: verify the documentation is accurate and complete against the Lua source.

=== CONTEXT ===

1. LUA SOURCE CODE (ground truth)
```lua
{lua_source}
```

2. CONNECTED CONTENT (referenced files)
{connected_block}
{previous_section}
3. DOCUMENTATION TO REVIEW
{md_content}

=== REVIEW CHECKLIST ===
Check for:
1. Function signatures and parameters match the Lua source — detect hallucination
2. Code examples match actual API usage
3. Descriptions are accurate and complete
4. Connected references are mentioned correctly

=== RESPONSE FORMAT ===
Respond in JSON only:
```json
{{
    "approved": true/false,
    "findings": [
        {{"issue": "specific problem found", "suggestion": "specific fix suggestion"}}
    ]
}}
```

If accurate and complete, set approved=true with empty findings.
If there are problems, set approved=false and list each issue paired with its fix suggestion."""


def build_writer_prompt(
    md_content: str,
    lua_source: str,
    connected_content: str,
    issues: list[str],
    suggestions: list[str],
) -> str:
    """Build prompt for LLM1 (writer) to fix documentation based on review feedback."""
    feedback_lines = []
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback_lines.append(f"{i}. Issue: {issue}")
        if suggestion:
            feedback_lines.append(f"   Suggestion: {suggestion}")
    feedback = "\n".join(feedback_lines)

    connected_block = connected_content if connected_content else "(none)"
    return f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.
Your task: fix the documentation based on reviewer feedback. Return ONLY targeted patches, not the entire document.

=== CONTEXT ===

1. LUA SOURCE CODE (ground truth)
```lua
{lua_source}
```

2. CONNECTED CONTENT (referenced files)
{connected_block}

3. CURRENT DOCUMENTATION
{md_content}

=== REVIEWER FEEDBACK ===
{feedback}

=== PATCH FORMAT ===
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
) -> tuple[str, str]:
    """Prompt for reviewing one markdown section against its focused Lua context.

    Returns (system_prompt, user_content) for multi-turn conversation.
    """
    section_ctx = _section_context(section_heading)
    is_main_fns = section_heading == "## Main functions"
    fn_format_block = (
        f"\n=== FUNCTION FORMAT REFERENCE ===\n{_FN_FORMAT}\n"
    ) if is_main_fns else ""

    _FILE_DESC = {
        "component": "component with Class() constructor and self.inst",
        "data_config": "data config — returns a plain table/array, no Class() constructor",
        "utility": (
            "utility module — standalone functions accessed via require('modulename'), "
            "NOT via inst.components.X"
        ),
    }
    file_desc = _FILE_DESC.get(file_type, _FILE_DESC["component"])

    if lua_context:
        lua_block = f"```lua\n{lua_context}\n```"
        lua_instruction = "Review the section against the Lua functions below."
    else:
        lua_block = "(none — no Lua functions referenced in this section)"
        lua_instruction = (
            "No Lua context available — review structural accuracy "
            "and internal consistency only."
        )

    batch_scope_note = (
        "\n=== SCOPE NOTE ===\n"
        f"You are reviewing a BATCH of ### function entries from within '{section_heading}' — "
        "NOT the full document. Do NOT flag missing sections (## Overview, ## Usage example, "
        "## Dependencies & tags, ## Properties, etc.) — they exist elsewhere in the document "
        "and are out of scope for this review.\n"
        if is_main_fns else ""
    )

    system_prompt = f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API docs.

=== TARGET ===
File type: {file_type} ({file_desc})
Section:   {section_heading or "(preamble)"}

=== LUA CONTEXT (ground truth) ===
{lua_instruction}
{lua_block}
{batch_scope_note}
=== REVIEW RULES ===
{section_ctx}{_REVIEWER_SKILL}

=== QUALITY RULES ===
{_QUALITY_RULES}
{fn_format_block}
=== RESPONSE FORMAT ===
Respond in JSON only with keys "approved" (boolean) and "findings" (array of objects with "issue" and "suggestion").
approved=true with empty findings if accurate. approved=false with paired issue+suggestion for each problem."""

    user_content = f"""=== SECTION TO REVIEW ===
{section_text}"""

    return system_prompt, user_content


def build_section_writer_prompt(
    section_text: str,
    lua_context: str,
    issues: list[str],
    suggestions: list[str],
    section_heading: str = "",
    file_type: str = "component",
) -> tuple[str, str]:
    """Prompt for patching one markdown section based on review feedback.

    Returns (system_prompt, user_content) for multi-turn conversation.
    """
    system_prompt = f"""You are a documentation writer for Don't Starve Together (DST) Lua API docs.
Your task: fix the section using Lua source as ground truth. Return targeted patches only.
Do NOT undo previous patches. Only fix the new issues listed in the feedback.

=== TARGET ===
Section: {section_heading or "(preamble)"}

=== FORMAT RULES ===
{_WRITER_SKILL}

=== RESPONSE FORMAT ===
Return a JSON array of patches. Each patch has "old_text", "new_text", "reason".
old_text must be an EXACT substring of the section. Keep patches minimal."""

    feedback_lines = []
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback_lines.append(f"{i}. Issue: {issue}")
        if suggestion:
            feedback_lines.append(f"   Suggestion: {suggestion}")
    feedback = "\n".join(feedback_lines)

    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"

    user_content = f"""=== LUA CONTEXT (ground truth) ===
{lua_block}

=== CURRENT SECTION ===
{section_text}

=== REVIEWER FEEDBACK ===
{feedback}"""

    return system_prompt, user_content
