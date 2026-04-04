"""LLM1 writer: applies patch-based fixes based on reviewer feedback."""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

_FN_HEADING_RE = re.compile(r'^### ', re.MULTILINE)
_FN_NAME_RE = re.compile(r'^### `?([^`(\n]+)', re.MULTILINE)


def _fn_names(text: str) -> set[str]:
    return {m.group(1).strip() for m in _FN_NAME_RE.finditer(text)}

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


@dataclass
class TypedOp:
    """A semantically typed operation targeting a structural element by name."""
    op: str                # "update_section" | "update_field" | "rewrite_function" | "delete_function"
    section: str           # target section heading, e.g. "## Main functions"
    function: str | None = None   # target fn name (None for section-level ops)
    field: str | None = None      # target field name (None for whole-section/function ops)
    value: str | None = None      # new inline value (single-line), used by update_field
    content: str | None = None    # full replacement content, used by update_section/rewrite_function


def apply_patches(content: str, patches: list[Patch]) -> tuple[str, int, list["Patch"]]:
    """Apply patches to content via str.replace(). Returns (new_content, failed_count, ambiguous_patches).

    Regression guard: each patch is applied to a temporary copy first. If applying
    it would reduce the number of ### function headings, the patch is rejected —
    this prevents writer from silently dropping functions when old_text spans
    multiple ### blocks and new_text omits some of them.
    """
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
            old_fn_count = len(_FN_HEADING_RE.findall(patch.old_text))
            if old_fn_count >= 2:
                # Multi-block patch: compare function names in accumulated content before/after
                # to catch regressions regardless of count (handles rename and swap cases too)
                candidate = content.replace(patch.old_text, patch.new_text, 1)
                lost = _fn_names(content) - _fn_names(candidate)
                if lost:
                    print(f"  [content/writer] Patch blocked — multi-block patch drops: {', '.join(sorted(lost))}: {patch.old_text[:60]!r}")
                    failed += 1
                else:
                    content = candidate
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


def parse_typed_op_response(raw: str) -> "TypedOp | None":
    """Parse writer response for a single TypedOp. Returns None on failure."""
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
    try:
        data = json.loads(cleaned)
        return parse_typed_op_json(data)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_typed_op_json(data: dict) -> "TypedOp | None":
    """Parse pre-validated JSON dict into TypedOp. Returns None if op field missing."""
    if not isinstance(data, dict) or not data.get("op"):
        return None
    return TypedOp(
        op=str(data["op"]),
        section=str(data.get("section", "")),
        function=data.get("function") or None,
        field=data.get("field") or None,
        value=data.get("value") or None,
        content=data.get("content") or None,
    )


def rewrite_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    review_feedback: ReviewResult,
    model: str,
) -> list[Patch]:
    """Ask LLM1 to generate patches based on reviewer feedback."""
    system_prompt, user_content = build_writer_prompt(
        md_content, lua_source, connected_content,
        review_feedback.issues, review_feedback.suggestions,
    )
    token_count = count_tokens(system_prompt + user_content)
    print(f"  [content/writer] Prompt: {token_count:,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("writer", system_prompt + "\n\n" + user_content)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("writer_response", raw)
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
