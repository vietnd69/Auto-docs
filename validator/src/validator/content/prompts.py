"""Prompt templates for content validation writer and reviewer."""

import re
from prompts.skills_loader import load_skill, combine_skills


def extract_lua_exported_names(lua_source: str) -> str:
    """Extract the module-level return table from a Lua file and return a formatted name list.

    Returns a compact string like:
        Exported API (return table keys): ShouldKnockout, ConfigurePlayerLocomotor, ...
    or empty string if no module-level return table is found.

    Uses the LAST `return { ... }` match to avoid matching early return-inside-function bodies.
    Handles one level of nested tables (sufficient for DST utility modules).
    """
    # Find ALL `return { ... }` blocks; take the LAST one (module-level export, not inner returns)
    matches = re.findall(r'\breturn\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', lua_source, re.DOTALL)
    if not matches:
        return ""
    body = matches[-1]
    # Each entry is like "    FuncName = FuncName," — we want the KEY (exported name)
    names = re.findall(r'^\s+(\w+)\s*=', body, re.MULTILINE)
    if not names:
        return ""
    return "Exported API (return table keys): " + ", ".join(names)

# Module-level constants -- used by dead code functions (build_section_reviewer_prompt,
# build_section_writer_prompt). These functions are NOT refactored in this restructure.
_QUALITY_RULES = load_skill("content_rules")   # was "quality_rules" -- split in restructure
_REVIEWER_SKILL = load_skill("validator_reviewer")
_WRITER_SKILL = load_skill("validator_writer")
_JURY_SKILL = load_skill("validator_jury")


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
) -> tuple[str, str]:
    """Build (system_prompt, user_content) for LLM2 (reviewer) to review documentation accuracy."""
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

    system_prompt = f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.
Your task: verify the documentation is accurate and complete against the Lua source.

=== SKILLS ===
{combine_skills("reviewer_full")}

=== RESPONSE FORMAT ===
Respond in JSON only:
```json
{{
    "approved": true/false,
    "need_special_case": false,
    "special_case_standard_heading": "",
    "special_case_reason": "",
    "findings": [
        {{"issue": "specific problem found", "suggestion": "specific fix suggestion"}}
    ]
}}
```

Valid states — only these 4 are allowed:
- approved=true,  need_special_case=false, findings=[]     → fully approved
- approved=true,  need_special_case=true,  findings=[]     → content ok, section name disputed (jury will decide)
- approved=false, need_special_case=false, findings=[..]   → content issues only
- approved=false, need_special_case=true,  findings=[..]   → content issues + section name disputed
INVARIANT: approved=false requires findings to be non-empty. Never return approved=false with findings=[].
When need_special_case=true: special_case_standard_heading MUST be the exact standard heading being
replaced (e.g. "## Main functions"). This tells the system which specific heading check to bypass."""

    exported_names = extract_lua_exported_names(lua_source)
    if exported_names:
        exported_block = f"\n3. {exported_names}\n"
        doc_label = "4."
    else:
        exported_block = ""
        doc_label = "3."

    user_content = f"""=== CONTEXT ===

1. LUA SOURCE CODE (ground truth)
```lua
{lua_source}
```

2. CONNECTED CONTENT (referenced files)
{connected_block}
{exported_block}{previous_section}
{doc_label} DOCUMENTATION TO REVIEW
{md_content}"""

    return system_prompt, user_content


def build_writer_prompt(
    md_content: str,
    lua_source: str,
    connected_content: str,
    issues: list[str],
    suggestions: list[str],
) -> tuple[str, str]:
    """Build (system_prompt, user_content) for LLM1 (writer) to fix documentation based on review feedback."""
    feedback_lines = []
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback_lines.append(f"{i}. Issue: {issue}")
        if suggestion:
            feedback_lines.append(f"   Suggestion: {suggestion}")
    feedback = "\n".join(feedback_lines)

    connected_block = connected_content if connected_content else "(none)"

    system_prompt = f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.
Your task: fix the documentation based on reviewer feedback. Return ONLY targeted patches, not the entire document.

=== SKILLS ===
{combine_skills("writer_full")}

=== PATCH FORMAT ===
Return a JSON array of patches. Each patch replaces a specific text segment:
```json
[
    {{
        "old_text": "exact text to find in the document",
        "new_text": "replacement text",
        "reason": "why this change is needed",
        "allow_drops": false
    }}
]
```

Rules:
- old_text must be an EXACT substring of the current document
- CRITICAL: Copy old_text VERBATIM character-by-character from the CURRENT DOCUMENTATION section.
  The document may use "*   **Description:**" (3 spaces after *) or "* **Description:**" (1 space).
  You MUST match exactly what the document has — never reconstruct from memory or skill examples.
- Keep patches minimal — only change what's needed to fix the issues
- Do NOT modify YAML frontmatter
- Preserve markdown formatting and structure
- old_text should target ONE ### function block — prefer one patch per function
- To DELETE a single function: old_text = that function's block only, new_text = ""
- To DELETE multiple contiguous functions at once (e.g., a group of local helpers): span all their ### blocks in old_text, set "allow_drops": true, new_text = "" to remove all of them. Only use allow_drops when the reviewer explicitly asks to remove functions (e.g., local/private functions not in public API).
- To ADD a new ### function: use the last 1-2 lines of an adjacent function as the anchor, then include those lines plus the new function block in new_text
- NEVER delete a ## section — never use empty new_text for a ## heading or its content. To rename a ## heading: old_text = the heading line only (e.g. "## OldName"), new_text = the new heading line (e.g. "## NewName")"""

    exported_names = extract_lua_exported_names(lua_source)
    if exported_names:
        exported_block = f"\n3. {exported_names}\n"
        doc_label = "4."
    else:
        exported_block = ""
        doc_label = "3."

    user_content = f"""=== CONTEXT ===

1. LUA SOURCE CODE (ground truth)
```lua
{lua_source}
```

2. CONNECTED CONTENT (referenced files)
{connected_block}
{exported_block}
{doc_label} CURRENT DOCUMENTATION
{md_content}

=== REVIEWER FEEDBACK ===
{feedback}"""

    return system_prompt, user_content


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
        "CRITICAL: Only report findings for functions that appear as ### headings in the "
        "section text provided. Do NOT report findings for functions visible in the Lua context "
        "but absent from the section — those belong to other batches.\n"
        if is_main_fns else ""
    )

    system_prompt = f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API docs.
You are reviewing CONTENT ACCURACY ONLY. Do not flag formatting, bullet style, or structural notation issues.

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
From the quality rules below, apply ONLY content accuracy rules (CONTENT RULES, COMPLETENESS, FILE TYPE CLASSIFICATION, CONSTRUCTOR RULE). IGNORE format rules (OUTPUT FORMAT, YAML FRONTMATTER, HEADING RULES, PROPERTIES TABLE column structure, MDX COMPATIBILITY).
{_QUALITY_RULES}

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
old_text must be an EXACT substring of the section. Keep patches minimal.
old_text must NOT span more than one ### function block — never include two or more ### headings in the same old_text.
To ADD a new ### function: use the last 1-2 lines of an adjacent function as anchor, then include those lines plus the new function in new_text."""

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


def build_jury_prompt(
    md_content: str,
    lua_source: str,
    connected_content: str,
    special_case_reason: str,
) -> tuple[str, str]:
    """Build (system_prompt, user_content) for a single jury member voting on a format special case request."""
    connected_block = connected_content if connected_content else "(none)"

    system_prompt = f"""=== SKILLS ===
{combine_skills("jury")}

=== YOUR VOTE ===
Based on the Lua source and the reviewer's argument above, cast your vote.
Respond in JSON only — no other text:
{{"vote": "yes/no", "reason": "one or two sentences citing specific Lua evidence"}}"""

    user_content = f"""=== REVIEWER'S ARGUMENT ===
{special_case_reason}

=== LUA SOURCE (ground truth) ===
```lua
{lua_source}
```

=== CONNECTED CONTENT ===
{connected_block}

=== DOCUMENTATION UNDER REVIEW ===
{md_content}"""

    return system_prompt, user_content


# ── Typed prompt builders (used by chunked.py typed-ops path) ─────────────────

# rule_id sets per section heading — controls what rule_ids the reviewer emits
_RULE_IDS_BY_SECTION: dict[str, list[str]] = {
    "## Overview":             ["WRONG_FILE_TYPE", "INACCURATE_DESCRIPTION", "MISSING_KEY_INFO"],
    "## Usage example":        ["WRONG_FUNCTION_CALL", "USES_INVALID_API", "UNREALISTIC_EXAMPLE"],
    "## Dependencies & tags":  ["MISSING_ENTRY", "EXTRA_ENTRY", "WRONG_USAGE_DESC"],
    "## Properties":           ["WRONG_TYPE", "WRONG_DEFAULT", "MISSING_PROPERTY", "EXTRA_PROPERTY"],
    "## Main functions":       ["WRONG_VALUE", "MISSING_PARAM", "EXTRA_PARAM", "WRONG_DESCRIPTION",
                               "WRONG_ERROR_STATE", "MISPLACED_ERROR_STATE"],
    "## Events & listeners":   ["MISSING_EVENT", "WRONG_EVENT_NAME"],
}


_FILE_TYPE_DESC = {
    "component": "component with Class() constructor and self.inst",
    "data_config": "data config — returns a plain table/array, no Class() constructor",
    "utility": (
        "utility module — standalone functions accessed via require('modulename'), "
        "NOT via inst.components.X"
    ),
}


def build_typed_reviewer_prompt(
    section_text: str,
    lua_context: str,
    section_heading: str = "",
    rule_ids: list[str] | None = None,
    file_type: str = "component",
    reviewed_context: str = "",
) -> tuple[str, str]:
    """Reviewer prompt that emits typed Finding objects.

    Returns (system_prompt, user_content) for multi-role conversation.
    """
    section_ctx = _section_context(section_heading)  # returns "" for unknown headings
    effective_rule_ids = rule_ids or _RULE_IDS_BY_SECTION.get(section_heading, [])
    rule_ids_str = ", ".join(effective_rule_ids) if effective_rule_ids else "WRONG_VALUE"
    file_desc = _FILE_TYPE_DESC.get(file_type, _FILE_TYPE_DESC["component"])

    is_main_fns = section_heading == "## Main functions"
    if is_main_fns:
        fn_names = re.findall(r'^### `([^`\n]+)`', section_text, re.MULTILINE)
        if not fn_names:
            fn_names = re.findall(r'^### (.+)', section_text, re.MULTILINE)
        fn_list = "\n".join(f"  - {fn.strip()}" for fn in fn_names)
        batch_scope_note = (
            "\n=== SCOPE NOTE ===\n"
            f"You are reviewing a BATCH of ### function entries from '{section_heading}'. "
            "Do NOT flag missing ## sections (## Overview, ## Usage example, etc.) — "
            "they exist elsewhere in the document and are out of scope here.\n"
            f"IN-SCOPE FUNCTIONS — only report findings for these exact names:\n{fn_list}\n"
            "CRITICAL: Do NOT report findings for any function not listed above, even if "
            "you see it in the Lua context — those belong to other batches.\n"
        )
    else:
        batch_scope_note = ""

    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"

    system_prompt = f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API docs.
Review CONTENT ACCURACY ONLY. Do not flag formatting or structural notation issues.

=== TARGET ===
Section:   {section_heading or "(preamble)"}
File type: {file_type} ({file_desc})

=== LUA CONTEXT (ground truth) ===
{lua_block}
{batch_scope_note}
=== SECTION REQUIREMENTS ===
{section_ctx}
=== SKILLS ===
{combine_skills("reviewer_typed")}

=== ALLOWED rule_id VALUES ===
{rule_ids_str}

=== RESPONSE FORMAT ===
Respond in JSON only:
{{
    "approved": true/false,
    "findings": [
        {{
            "section": "{section_heading}",
            "function": "FunctionName or null",
            "field": "FieldName or null",
            "rule_id": "one of the allowed rule_ids above",
            "issue": "specific problem description"
        }}
    ]
}}
approved=true with empty findings if accurate. One Finding per (function, field) problem.

IMPORTANT: Report ALL issues you find in this single pass. Do not limit or defer findings — every content error must appear now, not in a later round."""

    if reviewed_context:
        user_content = (
            f"=== REVIEWED SECTIONS (already validated against Lua source) ===\n"
            f"{reviewed_context}\n\n"
            f"=== SECTION TO REVIEW ===\n{section_text}"
        )
    else:
        user_content = f"=== SECTION TO REVIEW ===\n{section_text}"
    return system_prompt, user_content


def build_typed_writer_prompt(
    target_text: str,
    lua_context: str,
    finding: object,  # Finding — forward ref to avoid import cycle
    section_heading: str = "",
    file_type: str = "component",
) -> tuple[str, str]:
    """Writer prompt that fixes ONE Finding and returns ONE TypedOp.

    Returns (system_prompt, user_content) for multi-role conversation.
    """
    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"

    system_prompt = f"""You are a documentation writer for Don't Starve Together (DST) Lua API docs.
Fix ONE specific issue by returning ONE typed operation. Return JSON only.

=== SKILLS ===
{combine_skills("writer_typed")}

=== OPERATION TYPES ===
- update_section:   replace the full section text (Overview, Usage example rewrites)
- update_field:     replace one field's inline value (single-line field label only)
- rewrite_function: replace the entire ### function block for the named function
- delete_function:  remove the ### function block (use for hallucinated functions)

=== RESPONSE FORMAT ===
Return a single JSON object:
{{
    "op": "update_section | update_field | rewrite_function | delete_function",
    "section": "## Section heading",
    "function": "FunctionName or null",
    "field": "FieldName or null",
    "value": "new single-line field value or null",
    "content": "full replacement content or null"
}}"""

    # finding may be a Finding dataclass — access via attribute
    fn_val = getattr(finding, "function", None)
    fld_val = getattr(finding, "field", None)
    rule_val = getattr(finding, "rule_id", "")
    issue_val = getattr(finding, "issue", "")
    section_val = getattr(finding, "section", section_heading)

    user_content = f"""=== LUA CONTEXT (ground truth) ===
{lua_block}

=== ISSUE TO FIX ===
section:  {section_val}
function: {fn_val or "(none)"}
field:    {fld_val or "(none)"}
rule_id:  {rule_val}
issue:    {issue_val}

=== TARGET TEXT ===
{target_text}"""

    return system_prompt, user_content
