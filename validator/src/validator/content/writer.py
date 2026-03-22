"""LLM1 writer: applies patch-based fixes based on reviewer feedback."""

import json
import re
from dataclasses import dataclass

from llm.client import ollama_chat
from validator.content.prompts import build_writer_prompt
from validator.content.reviewer import ReviewResult


@dataclass
class Patch:
    """A targeted text replacement."""
    old_text: str
    new_text: str
    reason: str


def apply_patches(content: str, patches: list[Patch]) -> tuple[str, int]:
    """Apply patches to content via str.replace(). Returns (new_content, failed_count)."""
    failed = 0
    for patch in patches:
        if patch.old_text in content:
            content = content.replace(patch.old_text, patch.new_text, 1)
        else:
            failed += 1
    return content, failed


def parse_writer_response(raw: str) -> list[Patch]:
    """Parse LLM1 response into list of Patch objects."""
    # Strip markdown code fence if present
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    # Remove <think>...</think> blocks (Qwen model)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()

    try:
        data = json.loads(cleaned)
        if not isinstance(data, list):
            return []
        return [
            Patch(
                old_text=str(item.get("old_text", "")),
                new_text=str(item.get("new_text", "")),
                reason=str(item.get("reason", "")),
            )
            for item in data
            if isinstance(item, dict) and item.get("old_text")
        ]
    except (json.JSONDecodeError, TypeError):
        return []


def rewrite_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    review_feedback: ReviewResult,
    model: str,
) -> list[Patch]:
    """Ask LLM1 to generate patches based on reviewer feedback."""
    prompt = build_writer_prompt(
        md_content, lua_source, connected_content,
        review_feedback.issues, review_feedback.suggestions,
    )
    response = ollama_chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response["message"]["content"]
    patches = parse_writer_response(raw)
    if not patches:
        print(f"  [content/writer] No patches parsed — raw response truncated: {raw[:120]!r}")
    else:
        print(f"  [content/writer] {len(patches)} patch(es) generated")
    return patches
