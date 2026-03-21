"""LLM2 reviewer: reviews documentation against Lua source code."""

import json
import re
from dataclasses import dataclass

from llm.client import ollama_chat
from validator.content.prompts import build_reviewer_prompt


@dataclass
class ReviewResult:
    """Structured result from LLM2 review."""
    approved: bool
    issues: list[str]
    suggestions: list[str]


def parse_review_response(raw: str) -> ReviewResult:
    """Parse LLM2 response into ReviewResult. Handles JSON in markdown fences."""
    # Strip markdown code fence if present
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    # Remove <think>...</think> blocks (Qwen model)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()

    try:
        data = json.loads(cleaned)
        return ReviewResult(
            approved=bool(data.get("approved", False)),
            issues=list(data.get("issues", [])),
            suggestions=list(data.get("suggestions", [])),
        )
    except (json.JSONDecodeError, TypeError):
        return ReviewResult(
            approved=False,
            issues=[f"Failed to parse reviewer response: {raw[:200]}"],
            suggestions=[],
        )


def review_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    model: str,
) -> ReviewResult:
    """Send document to LLM2 for review. Returns structured ReviewResult."""
    prompt = build_reviewer_prompt(md_content, lua_source, connected_content)
    response = ollama_chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response["message"]["content"]
    return parse_review_response(raw)
