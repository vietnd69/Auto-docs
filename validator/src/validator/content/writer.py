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
from validator.content.schemas import PATCHES_SCHEMA

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
    allow_drops: bool = False  # skip function-drop guard for intentional deletions


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
            first_line = patch.old_text.split("\n")[0][:80]
            print(f"  [content/writer] Patch not found: {first_line!r}")
            failed += 1
        elif count > 1:
            print(f"  [content/writer] Ambiguous patch skipped (old_text appears {count}x): {patch.old_text[:80]!r}")
            failed += 1
            ambiguous.append(patch)
        else:
            old_fn_count = len(_FN_HEADING_RE.findall(patch.old_text))
            if old_fn_count >= 2:
                # Multi-block patch: compare function names before/after to catch accidental drops.
                # allow_drops=True bypasses this guard for intentional bulk deletions.
                candidate = content.replace(patch.old_text, patch.new_text, 1)
                lost = _fn_names(content) - _fn_names(candidate)
                if lost and not patch.allow_drops:
                    print(f"  [content/writer] Patch blocked — multi-block patch drops: {', '.join(sorted(lost))}: {patch.old_text[:60]!r}")
                    failed += 1
                else:
                    if lost:
                        print(f"  [content/writer] Patch allowed (allow_drops) — intentionally drops: {', '.join(sorted(lost))}")
                    content = candidate
            else:
                content = content.replace(patch.old_text, patch.new_text, 1)
    return content, failed, ambiguous


def _parse_patch_list(data: object) -> list[Patch]:
    """Convert a parsed JSON list into Patch objects. Returns [] if data is not a valid list."""
    if not isinstance(data, list):
        return []
    return [
        Patch(
            old_text=str(item.get("old_text", "")),
            new_text=str(item.get("new_text", "")),
            reason=str(item.get("reason", "")),
            allow_drops=bool(item.get("allow_drops", False)),
        )
        for item in data
        if isinstance(item, dict) and item.get("old_text")
    ]


def parse_writer_response(raw: str) -> list[Patch]:
    """Parse LLM1 response into list of Patch objects.

    Handles three cases:
    - Direct JSON array (ideal)
    - JSON array inside a markdown code fence
    - JSON array preceded by explanatory text (assistant prefill continuation)
    """
    # Strip markdown code fence and think blocks
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()

    # Primary: direct parse
    try:
        return _parse_patch_list(json.loads(cleaned))
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: extract first JSON array from anywhere in the response.
    # Model may prefix the array with explanatory text (e.g. after assistant prefill).
    start = cleaned.find('[')
    end = cleaned.rfind(']')
    if start != -1 and end > start:
        try:
            return _parse_patch_list(json.loads(cleaned[start:end + 1]))
        except (json.JSONDecodeError, TypeError):
            pass

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
            allow_drops=bool(item.get("allow_drops", False)),
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


def parse_typed_ops_json(data: list) -> "list[TypedOp]":
    """Parse pre-validated JSON array into a list of TypedOp objects."""
    if not isinstance(data, list):
        return []
    ops: list[TypedOp] = []
    for item in data:
        op = parse_typed_op_json(item)
        if op and op.op:
            ops.append(op)
    return ops


def rewrite_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    review_feedback: ReviewResult,
    model: str,
) -> tuple[list[Patch], str]:
    """Ask LLM1 to generate patches based on reviewer feedback.

    Returns (patches, raw_response). raw_response is needed by callers that
    want to do a multi-turn correction when patches fail to apply.
    """
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
    patches: list[Patch] = []
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages, format=PATCHES_SCHEMA)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("writer_response", raw)
        remaining = BAD_RESPONSE_RETRIES - attempt
        if not raw.strip():
            if remaining > 0:
                print(f"  [content/writer] Empty response → retrying ({remaining} left)")
                continue
            print(f"  [content/writer] Empty response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")
            break
        patches = parse_writer_response(raw)
        if patches:
            break
        if remaining > 0:
            print(f"  [content/writer] No patches parsed → retrying ({remaining} left) — raw: {raw[:80]!r}")
        else:
            print(f"  [content/writer] No patches parsed after {BAD_RESPONSE_RETRIES + 1} attempts — raw: {raw[:120]!r}")

    if patches:
        print(f"  [content/writer] {len(patches)} patch(es) generated")
    return patches, raw


def _find_doc_snippet(md_content: str, old_text: str, context_lines: int = 6) -> str:
    """Find the nearest matching region in the document for a failed old_text.

    Uses the first line of old_text (usually a ### heading) to locate the region,
    then returns the following lines so the writer can see the exact formatting.
    """
    first_line = old_text.split("\n")[0]
    idx = md_content.find(first_line)
    if idx == -1:
        return ""
    snippet = "\n".join(md_content[idx:].split("\n")[:context_lines])
    return snippet


def _extract_fn_headings(md_content: str) -> str:
    """Extract all ### function headings from the document as a reference list."""
    headings = re.findall(r'^(### .+)$', md_content, re.MULTILINE)
    return "\n".join(headings) if headings else "(no ### headings found)"


def _build_targeted_correction_prompt(
    md_content: str,
    failed_patches: list[Patch],
    failure_reasons: list[str],
) -> tuple[str, str]:
    """Build a targeted prompt for correcting only the failed patches.

    Does NOT include the full reviewer feedback or previous patch history —
    those caused the writer to re-generate all patches (most already applied)
    instead of fixing only the failed ones.
    """
    system_prompt = (
        "You are a documentation writer fixing failed patch applications.\n\n"
        "Some patches could not be applied because old_text was not found verbatim in the document.\n"
        "Your ONLY task: for each failed patch, return a corrected version with an exact old_text.\n\n"
        "Return a JSON array — one corrected patch per failed patch:\n"
        '[{"old_text": "exact text from document", "new_text": "replacement", "reason": "why"}]\n\n'
        "Rules:\n"
        "- old_text MUST be an EXACT substring of the CURRENT DOCUMENT shown below\n"
        "- Copy old_text character-by-character from the document — never reconstruct from memory\n"
        "- Most common cause of failure: whitespace — '*   **Description:**' (3 spaces) vs "
        "'* **Description:**' (1 space). Match exactly.\n"
        "- Do NOT generate patches for anything not listed as a failed patch below\n"
        "- Do NOT re-patch sections that were already successfully applied"
    )

    parts = []
    for i, (p, reason) in enumerate(zip(failed_patches, failure_reasons), 1):
        snippet = _find_doc_snippet(md_content, p.old_text, context_lines=10)
        part = (
            f"--- Failed patch {i} ---\n"
            f"Attempted old_text: {p.old_text[:300]!r}\n"
            f"Failure reason: {reason}\n"
            f"Intended new_text: {p.new_text[:300]!r}"
        )
        if snippet:
            part += f"\nDocument region near target (EXACT whitespace):\n{snippet!r}"
        parts.append(part)

    fn_headings = _extract_fn_headings(md_content)
    user_content = (
        f"=== FAILED PATCHES TO CORRECT ({len(failed_patches)} total) ===\n\n"
        + "\n\n".join(parts)
        + f"\n\n=== ### HEADINGS IN DOCUMENT (use these for old_text anchors) ===\n{fn_headings}"
        + f"\n\n=== CURRENT DOCUMENT ===\n{md_content}"
    )
    return system_prompt, user_content


def correct_failed_patches(
    md_content: str,
    failed_patches: list[Patch],
    failure_reasons: list[str],
    model: str,
) -> list[Patch]:
    """Targeted correction: ask writer to fix only the failed patches.

    Uses a simple single-turn prompt showing only the failed patches and the
    current document. Avoids the multi-turn + previous_raw structure, which
    caused the writer to re-generate all patches (targeting the pre-patch document)
    instead of correcting just the failed ones.
    """
    system_prompt, user_content = _build_targeted_correction_prompt(
        md_content, failed_patches, failure_reasons,
    )
    token_count = count_tokens(system_prompt + user_content)
    print(f"  [content/writer] Correction prompt: {token_count:,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("writer_correction", system_prompt + "\n\n" + user_content)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    raw = ""
    patches: list[Patch] = []
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages, format=PATCHES_SCHEMA)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("writer_correction_response", raw)
        remaining = BAD_RESPONSE_RETRIES - attempt
        if not raw.strip():
            if remaining > 0:
                print(f"  [content/writer] Correction empty → retrying ({remaining} left)")
                continue
            break
        patches = parse_writer_response(raw)
        if patches:
            break
        if remaining > 0:
            print(f"  [content/writer] Correction no patches → retrying ({remaining} left)")
        else:
            print(f"  [content/writer] Correction no patches after {BAD_RESPONSE_RETRIES + 1} attempts")

    if patches:
        print(f"  [content/writer] Correction: {len(patches)} patch(es) generated")
    else:
        print(f"  [content/writer] Correction returned no patches")
    return patches
