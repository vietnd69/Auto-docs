"""Rewrite entire document via LLM when required headings are missing after autofix."""

from pathlib import Path

from llm.client import ollama_chat
from llm.settings import MODEL_MAIN
from prompts.skills_loader import combine_skills
from rag.docs import clean_model_output, compute_source_hash, inject_frontmatter_field, safe_read_lua
from validator.utils import resolve_connected_content

_REQUIRED_HEADINGS = [
    "## Overview",
    "## Usage example",
    "## Dependencies & tags",
    "## Properties",
    "## Main functions",
    "## Events & listeners",
]


def build_rewrite_prompt(
    md_text: str,
    lua_code: str,
    missing_headings: list[str],
    connected_section: str = "",
    connected_content: str = "",
) -> str:
    """Build a full rewrite prompt (single user message, same pattern as standard.py)."""
    skills_block = combine_skills("analyst")
    missing_str = ", ".join(f"`{h}`" for h in missing_headings)
    connected_block = connected_section or "No external references found."
    connected_code_block = connected_content or "No function source code available."
    required_list = "\n".join(f"- {h}" for h in _REQUIRED_HEADINGS)

    return f"""=== CONTEXT ===

The following document is INCOMPLETE — missing required sections: {missing_str}.

Your task: rewrite the ENTIRE document, keeping all correct existing content and adding
the missing sections with accurate, complete information from the Lua source code.

=== EXISTING DOCUMENT (incomplete) ===
{md_text}

=== CONNECTED FILES AND FUNCTIONS ===
{connected_block}

=== CONNECTED FILES -- EXTRACTED SOURCE CODE ===
{connected_code_block}

=== SKILLS ===
{skills_block}

=== LUA SOURCE CODE ===
{lua_code}

=== INSTRUCTION ===
Rewrite the complete document. All required sections must be present:
{required_list}

Keep the YAML frontmatter (id, title, description, tags, sidebar_position, last_updated,
build_version, change_status, category_type, source_hash, system_scope) exactly as in the
existing document. Output the full document starting with `---`."""


def rewrite_document(
    md_filepath: str,
    missing_headings: list[str],
    lua_filepath: str,
    model: str = MODEL_MAIN,
) -> bool:
    """
    Call LLM to rewrite the entire document, adding missing sections.
    Overwrites md_filepath on success. Returns True if successful.
    """
    print(f"  [section_filler] Missing: {', '.join(missing_headings)}")
    print(f"  [section_filler] Rewriting full document via LLM...")

    md_text = Path(md_filepath).read_text(encoding="utf-8")
    lua_code = safe_read_lua(lua_filepath) or ""
    connected_section, connected_content = resolve_connected_content(lua_filepath)

    prompt = build_rewrite_prompt(
        md_text, lua_code, missing_headings,
        connected_section, connected_content,
    )

    try:
        response = ollama_chat(model, messages=[{"role": "user", "content": prompt}])
        cleaned = clean_model_output(response.message.content)

        if not cleaned:
            print(f"  [section_filler] LLM returned empty content")
            return False

        if not cleaned.startswith("---"):
            print(f"  [section_filler] Warning: output missing YAML frontmatter")

        # Re-inject source_hash in case LLM dropped it
        if lua_code:
            cleaned = inject_frontmatter_field(cleaned, "source_hash", compute_source_hash(lua_code))

        Path(md_filepath).write_text(cleaned, encoding="utf-8")
        print(f"  [section_filler] Rewrite complete")
        return True

    except Exception as e:
        print(f"  [section_filler] Error: {e}")
        return False
