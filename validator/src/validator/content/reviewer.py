"""LLM2 reviewer: reviews documentation against Lua source code."""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from llm.client import ollama_chat
from llm.paths import PROJECT_ROOT
from llm.tokens import count_tokens
from llm.settings import BAD_RESPONSE_RETRIES, DEBUG_PROMPTS
from validator.content.prompts import build_reviewer_prompt

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _dump_prompt(label: str, prompt: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = _DEBUG_DIR / f"{label}_{ts}.txt"
    path.write_text(prompt, encoding="utf-8")
    print(f"  [debug] Prompt dumped → {path}")


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
        approved = bool(data.get("approved", False))
        # New format: findings=[{"issue": ..., "suggestion": ...}]
        if "findings" in data:
            findings = data["findings"] or []
            issues = [str(f.get("issue", "")) for f in findings if isinstance(f, dict)]
            suggestions = [str(f.get("suggestion", "")) for f in findings if isinstance(f, dict)]
        else:
            # Legacy format: separate issues/suggestions arrays
            issues = list(data.get("issues", []))
            suggestions = list(data.get("suggestions", []))
        return ReviewResult(approved=approved, issues=issues, suggestions=suggestions)
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
    print(f"  [content/reviewer] Prompt: {count_tokens(prompt):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("reviewer", prompt)
    result = ReviewResult(approved=False, issues=["No response"], suggestions=[])
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=[{"role": "user", "content": prompt}])
        raw = response["message"]["content"]
        result = parse_review_response(raw)
        is_bad = not raw.strip() or (result.issues and result.issues[0].startswith("Failed to parse"))
        if not is_bad:
            return result
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/reviewer] Bad response → retrying ({remaining} left)")
        else:
            print(f"  [content/reviewer] Bad response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")
    return result
