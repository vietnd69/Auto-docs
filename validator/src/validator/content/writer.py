"""LLM1 writer: applies patch-based fixes based on reviewer feedback."""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from llm.client import ollama_chat
from llm.paths import PROJECT_ROOT
from llm.tokens import count_tokens
from llm.settings import BAD_RESPONSE_RETRIES, DEBUG_PROMPTS
from validator.content.prompts import build_writer_prompt
from validator.content.reviewer import ReviewResult

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _dump_prompt(label: str, prompt: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = _DEBUG_DIR / f"{label}_{ts}.txt"
    path.write_text(prompt, encoding="utf-8")
    print(f"  [debug] Prompt dumped → {path}")


@dataclass
class Patch:
    """A targeted text replacement."""
    old_text: str
    new_text: str
    reason: str


def apply_patches(content: str, patches: list[Patch]) -> tuple[str, int, list["Patch"]]:
    """Apply patches to content via str.replace(). Returns (new_content, failed_count, ambiguous_patches)."""
    failed = 0
    ambiguous: list[Patch] = []
    for patch in patches:
        count = content.count(patch.old_text)
        if count == 0:
            failed += 1
        elif count > 1:
            print(f"  [content/writer] Ambiguous patch skipped (old_text appears {count}x): {patch.old_text[:80]!r}")
            failed += 1
            ambiguous.append(patch)
        else:
            content = content.replace(patch.old_text, patch.new_text, 1)
    return content, failed, ambiguous


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


def parse_writer_json(data: list) -> list[Patch]:
    """Parse pre-validated JSON list (from Ollama format parameter) into Patch list."""
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
    print(f"  [content/writer] Prompt: {count_tokens(prompt):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("writer", prompt)
    raw = ""
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=[{"role": "user", "content": prompt}])
        raw = response["message"]["content"]
        if raw.strip():
            break
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/writer] Empty response → retrying ({remaining} left)")
        else:
            print(f"  [content/writer] Empty response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")

    patches = parse_writer_response(raw)
    if not patches:
        print(f"  [content/writer] No patches parsed — raw response truncated: {raw[:120]!r}")
    else:
        print(f"  [content/writer] {len(patches)} patch(es) generated")
    return patches
