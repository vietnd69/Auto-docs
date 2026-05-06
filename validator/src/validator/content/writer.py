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
from validator.content.prompts import build_writer_prompt, build_writer_system_prompt, build_writer_slim_user
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


def apply_patches(content: str, patches: list[Patch]) -> tuple[str, int, list["Patch"], list[tuple["Patch", frozenset[str]]]]:
    """Apply patches to content via str.replace(). Returns (new_content, failed_count, ambiguous_patches, guard_blocked).

    Regression guard: each patch is applied to a temporary copy first. If applying
    it would reduce the number of ### function headings, the patch is rejected —
    this prevents writer from silently dropping functions when old_text spans
    multiple ### blocks and new_text omits some of them.

    guard_blocked is a list of (blocked_patch, lost_fn_names) for patches rejected by
    the regression guard. These can be used to request a multi-turn correction.
    """
    failed = 0
    ambiguous: list[Patch] = []
    guard_blocked_list: list[tuple[Patch, frozenset[str]]] = []
    total = len(patches)
    for idx, patch in enumerate(patches, 1):
        count = content.count(patch.old_text)
        if count == 0:
            # Fallback: LLM sometimes double-escapes characters in old_text
            # (e.g. \\n instead of \n, \\" instead of "). Try normalized version.
            normalized = patch.old_text.replace('\\"', '"').replace('\\n', '\n')
            if normalized != patch.old_text:
                norm_count = content.count(normalized)
                if norm_count == 1:
                    first_line = normalized.split("\n")[0][:80]
                    print(f"  [content/writer] Patch {idx}/{total} NORMALIZED (escape fix): {first_line!r}")
                    old_fn_count = len(_FN_HEADING_RE.findall(normalized))
                    if old_fn_count >= 2:
                        candidate = content.replace(normalized, patch.new_text, 1)
                        lost = _fn_names(content) - _fn_names(candidate)
                        if lost and not patch.allow_drops:
                            print(f"  [content/writer] Patch {idx}/{total} GUARD BLOCKED (normalized, drops: {', '.join(sorted(lost))}): {first_line!r}")
                            guard_blocked_list.append((patch, frozenset(lost)))
                            failed += 1
                            continue
                    content = content.replace(normalized, patch.new_text, 1)
                    continue
            first_line = patch.old_text.split("\n")[0][:80]
            print(f"  [content/writer] Patch {idx}/{total} NOT FOUND: {first_line!r}")
            failed += 1
        elif count > 1:
            print(f"  [content/writer] Patch {idx}/{total} AMBIGUOUS ({count}x): {patch.old_text[:80]!r}")
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
                    print(f"  [content/writer] Patch {idx}/{total} GUARD BLOCKED (drops: {', '.join(sorted(lost))}): {patch.old_text[:60]!r}")
                    guard_blocked_list.append((patch, frozenset(lost)))
                    failed += 1
                else:
                    if lost:
                        print(f"  [content/writer] Patch {idx}/{total} GUARD ALLOWED (allow_drops, drops: {', '.join(sorted(lost))})")
                    content = candidate
            else:
                content = content.replace(patch.old_text, patch.new_text, 1)
    return content, failed, ambiguous, guard_blocked_list


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
    prior_turns: list[dict] | None = None,
    user_prefix: str = "",
    slim_context: bool = False,
) -> tuple[list[Patch], str, str]:
    """Ask LLM1 to generate patches based on reviewer feedback.

    Returns (patches, raw_response, user_content). raw_response is needed by callers that
    want to do a multi-turn correction when patches fail to apply. user_content is needed
    to reconstruct the original request for multi-turn inner loop passes.

    prior_turns: optional [user, assistant] pair from the previous writer iteration,
    enabling multi-turn context so the writer can see what it tried before and
    the patch outcome. Format: [{"role": "user", ...}, {"role": "assistant", ...}]

    user_prefix: optional text prepended to user_content before sending.

    slim_context: when True and prior_turns is set, omit lua_source/connected_content from
    user_content — they are already available in the prior_turns conversation history.
    """
    system_prompt, user_content = build_writer_prompt(
        md_content, lua_source, connected_content,
        review_feedback.issues, review_feedback.suggestions,
    )
    if slim_context and prior_turns:
        user_content = build_writer_slim_user(
            md_content, review_feedback.issues, review_feedback.suggestions,
            user_prefix=user_prefix,
        )
    elif user_prefix:
        user_content = user_prefix + user_content
    token_count = count_tokens(system_prompt + user_content)
    prior_info = f" (+{len(prior_turns)} prior turn(s))" if prior_turns else ""
    print(f"  [content/writer] Write prompt: {token_count:,} tokens{prior_info}")
    if DEBUG_PROMPTS:
        _dump_prompt("writer", system_prompt + "\n\n" + user_content)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if prior_turns:
        messages.extend(prior_turns)
    messages.append({"role": "user", "content": user_content})
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
    return patches, raw, user_content


def _find_doc_snippet(md_content: str, old_text: str, context_lines: int = 6) -> str:
    """Find the nearest matching region in the document for a failed old_text.

    Uses the first line of old_text (usually a ### heading) to locate the region,
    then returns the following lines so the writer can see the exact formatting.
    """
    first_line = old_text.split("\n")[0]
    idx = md_content.find(first_line)
    if idx != -1:
        snippet = "\n".join(md_content[idx:].split("\n")[:context_lines])
        return snippet

    # Fuzzy fallback: extract the core function name (strip ### backticks and parameters)
    # e.g. "### `onenter (dance)(inst)`" → "onenter (dance)"
    name_match = re.search(r'###\s*`?([^`(\n]+)', first_line)
    if name_match:
        core = name_match.group(1).strip().lower()
        # Try to find any ### heading in the document that contains the core name
        for line in md_content.splitlines():
            if line.startswith("### ") and core in line.lower():
                idx = md_content.find(line)
                if idx != -1:
                    snippet = "\n".join(md_content[idx:].split("\n")[:context_lines])
                    return f"(approximate match — heading format differs)\n{snippet}"
    return ""


def _extract_fn_headings(md_content: str) -> str:
    """Extract all ### function headings from the document as a reference list."""
    headings = re.findall(r'^(### .+)$', md_content, re.MULTILINE)
    return "\n".join(headings) if headings else "(no ### headings found)"


def _extract_section_headings(md_content: str) -> str:
    """Extract all ## section headings from the document."""
    headings = re.findall(r'^(## .+)$', md_content, re.MULTILINE)
    return "\n".join(headings) if headings else "(no ## headings found)"


def _build_correction_feedback(
    md_content: str,
    failed_patches: list[Patch],
    failure_reasons: list[str],
) -> str:
    """Correction user message for multi-turn NOT-FOUND correction (4th turn).
    Does not include reviewer feedback or previous writer response — those are in history.
    """
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
    section_headings = _extract_section_headings(md_content)
    fn_headings = _extract_fn_headings(md_content)
    return (
        f"The following {len(failed_patches)} patch(es) from your previous response failed to apply:\n\n"
        + "\n\n".join(parts)
        + f"\n\n=== ## SECTION HEADINGS IN DOCUMENT ===\n{section_headings}"
        + f"\n\n=== ### FUNCTION HEADINGS IN DOCUMENT (use for old_text anchors) ===\n{fn_headings or '(none)'}"
        + f"\n\n=== CURRENT DOCUMENT ===\n{md_content}"
    )


def _build_targeted_correction_prompt(
    md_content: str,
    failed_patches: list[Patch],
    failure_reasons: list[str],
    review_issues: list[str] | None = None,
    review_suggestions: list[str] | None = None,
    previous_writer_raw: str = "",
    previous_patches: list[Patch] | None = None,
) -> tuple[str, str]:
    """Build a targeted prompt for correcting only the failed patches.

    Does NOT include the full reviewer feedback or previous patch history —
    those caused the writer to re-generate all patches (most already applied)
    instead of fixing only the failed ones.
    """
    n = len(failed_patches)
    system_prompt = (
        "You are a documentation writer fixing failed patch applications.\n\n"
        "Some patches could not be applied because old_text was not found verbatim in the document.\n"
        f"Your ONLY task: return EXACTLY {n} corrected patch(es) — one per failed patch listed below.\n"
        "Do NOT generate patches for anything else. Do NOT re-patch sections already applied.\n\n"
        "Return a JSON array:\n"
        '[{"old_text": "exact text from document", "new_text": "replacement", "reason": "why"}]\n\n'
        "Rules:\n"
        "- old_text MUST be an EXACT substring of the CURRENT DOCUMENT shown below\n"
        "- Copy old_text character-by-character from the document — never reconstruct from memory\n"
        "- Most common cause of failure: whitespace — '*   **Description:**' (3 spaces) vs "
        "'* **Description:**' (1 space). Match exactly.\n"
        "- CRITICAL: old_text must stay within a SINGLE ### function block — never let it span two "
        "or more ### headings. If you need a broader change, split into multiple patches (one per ### block).\n"
        "- AMBIGUOUS fix: if the failure reason says 'appears N times', the old_text is not unique. "
        "Start old_text with the exact `### heading line` from the '### HEADINGS IN DOCUMENT' list below, "
        "then include the field content. This guarantees uniqueness.\n"
        "- NOT FOUND fix: use the '### HEADINGS IN DOCUMENT' list to find the correct heading spelling. "
        "Copy it verbatim as the first line of old_text.\n"
        "- Do NOT generate patches for anything not listed as a failed patch below\n"
        "- Do NOT re-patch sections that were already successfully applied"
    )

    review_issues = review_issues or []
    review_suggestions = review_suggestions or []
    previous_patches = previous_patches or []

    feedback_lines = []
    for i, issue in enumerate(review_issues, 1):
        suggestion = review_suggestions[i - 1] if i - 1 < len(review_suggestions) else ""
        feedback_lines.append(f"{i}. Issue: {issue}")
        if suggestion:
            feedback_lines.append(f"   Suggestion: {suggestion}")
    feedback_block = "\n".join(feedback_lines) if feedback_lines else "(none)"

    patch_status_lines = []
    if previous_patches:
        failed_reason_by_patch = {id(p): r for p, r in zip(failed_patches, failure_reasons)}
        failed_idx = 0
        success_idx = 0
        for p in previous_patches:
            reason = failed_reason_by_patch.get(id(p))
            if reason is not None:
                failed_idx += 1
                patch_status_lines.append(
                    f"F{failed_idx}. FAILED — reason: {reason}; old_text preview: {p.old_text[:120]!r}"
                )
            else:
                success_idx += 1
                patch_status_lines.append(
                    f"S{success_idx}. APPLIED — old_text preview: {p.old_text[:120]!r}"
                )
    patch_status_block = "\n".join(patch_status_lines) if patch_status_lines else "(no prior patch status)"

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
        "=== PREVIOUS REVIEWER FEEDBACK (from the same iteration) ===\n"
        f"{feedback_block}\n\n"
        "=== PREVIOUS WRITER RESPONSE (raw JSON text) ===\n"
        f"{previous_writer_raw or '(none)'}\n\n"
        "=== PATCH APPLY STATUS FROM PREVIOUS WRITER RESPONSE ===\n"
        f"{patch_status_block}\n\n"
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
    review_issues: list[str] | None = None,
    review_suggestions: list[str] | None = None,
    previous_writer_raw: str = "",
    previous_patches: list[Patch] | None = None,
    original_md_content: str = "",
    lua_source: str = "",
    connected_content: str = "",
) -> list[Patch]:
    """Targeted correction: ask writer to fix only the failed patches.

    When original_md_content, lua_source, and previous_writer_raw are all provided,
    uses multi-turn structure:
        system:    writer system prompt
        user:      original write request (built from original_md_content)
        assistant: previous_writer_raw (what the writer tried)
        user:      correction feedback (what failed + section headings + current doc)

    Otherwise falls back to single-turn behavior using _build_targeted_correction_prompt.
    """
    use_multi_turn = bool(original_md_content and previous_writer_raw)

    if use_multi_turn:
        _issues = review_issues or []
        _suggestions = review_suggestions or []
        # Focused system prompt for correction — no writer skills needed, just find old_text
        system_prompt, _ = _build_targeted_correction_prompt(
            md_content, failed_patches, failure_reasons,
            review_issues=_issues, review_suggestions=_suggestions,
        )
        # Lightweight first user turn — reviewer feedback + original doc, no lua/connected
        feedback_lines = []
        for i, issue in enumerate(_issues, 1):
            suggestion = _suggestions[i - 1] if i - 1 < len(_suggestions) else ""
            feedback_lines.append(f"{i}. Issue: {issue}")
            if suggestion:
                feedback_lines.append(f"   Suggestion: {suggestion}")
        feedback_block = "\n".join(feedback_lines) if feedback_lines else "(none)"
        first_user = (
            f"=== REVIEWER FEEDBACK ===\n{feedback_block}\n\n"
            f"=== ORIGINAL DOCUMENT ===\n{original_md_content}"
        )
        correction_user = _build_correction_feedback(md_content, failed_patches, failure_reasons)
        token_count = count_tokens(system_prompt + first_user + previous_writer_raw + correction_user)
        print(f"  [content/writer] Not-found correction prompt: {token_count:,} tokens (multi-turn)")
        if DEBUG_PROMPTS:
            full = system_prompt + "\n\n" + first_user + "\n\n[ASSISTANT]\n" + previous_writer_raw + "\n\n[USER]\n" + correction_user
            _dump_prompt("writer_correction", full)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": first_user},
            {"role": "assistant", "content": previous_writer_raw},
            {"role": "user", "content": correction_user},
        ]
    else:
        system_prompt, user_content = _build_targeted_correction_prompt(
            md_content,
            failed_patches,
            failure_reasons,
            review_issues=review_issues,
            review_suggestions=review_suggestions,
            previous_writer_raw=previous_writer_raw,
            previous_patches=previous_patches,
        )
        token_count = count_tokens(system_prompt + user_content)
        print(f"  [content/writer] Not-found correction prompt: {token_count:,} tokens")
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
        expected = len(failed_patches)
        if len(patches) > expected:
            print(f"  [content/writer] Correction: {len(patches)} patch(es) generated (expected {expected}) — trimming to {expected}")
            patches = patches[:expected]
        else:
            print(f"  [content/writer] Correction: {len(patches)} patch(es) generated")
    else:
        print(f"  [content/writer] Correction returned no patches")
    return patches


def _build_guard_rejection_message(
    guard_blocked: list[tuple["Patch", frozenset[str]]],
    updated_content: str,
) -> str:
    """Build the user-turn message explaining which patches were blocked by the regression guard.

    updated_content is the document state AFTER all non-guard-blocked patches have been applied.
    It is appended so the writer can use exact old_text values that exist in the real current document,
    rather than the pre-patch snapshot shown in the earlier user turn.
    """
    n = len(guard_blocked)
    lines = [
        "[SYSTEM: REGRESSION GUARD REJECTION]",
        f"{n} patch(es) were blocked because they span multiple ### function blocks and would silently",
        "drop function documentation. The regression guard requires explicit opt-in to remove functions.",
        "",
    ]
    for i, (patch, lost_fns) in enumerate(guard_blocked, 1):
        fn_list = ", ".join(sorted(lost_fns))
        old_preview = patch.old_text[:80]
        lines.append(f"Patch {i} blocked — would drop: {fn_list}")
        lines.append(f"  old_text started with: {old_preview!r}")
        lines.append("")
    lines += [
        "To fix each blocked patch, choose ONE approach:",
        '  (a) Set "allow_drops": true — only if the reviewer EXPLICITLY asked to remove those functions',
        "  (b) Split into per-function patches — one patch per ### function block, with old_text that",
        "      targets ONLY that single function. Use the CURRENT DOCUMENT below for exact old_text",
        "      values (other patches have already been applied — this reflects the real document state).",
        "",
        "Return a JSON array of corrected patches for the blocked items ONLY.",
        "Do NOT re-generate patches for items that were already successfully applied.",
        "",
        "=== CURRENT DOCUMENT (reflects patches already applied) ===",
        updated_content,
    ]
    return "\n".join(lines)


def correct_guard_blocked_patches(
    md_content: str,
    lua_source: str,
    connected_content: str,
    review_feedback: ReviewResult,
    guard_blocked: list[tuple["Patch", frozenset[str]]],
    previous_raw: str,
    updated_content: str,
    model: str,
) -> list[Patch]:
    """Multi-turn correction for patches blocked by the regression guard.

    Uses the multi-turn structure:
        system:    writer system prompt (skills + patch rules)
        user:      lua source + connected content + reviewer feedback (no md_content —
                   the current document state is already in the rejection message)
        assistant: previous_raw (the writer's original JSON response)
        user:      guard rejection message (includes updated_content — real current doc state)

    updated_content must be passed so the correction writer sees the actual document state when
    generating old_text values to split the guard-blocked patches.
    """
    system_prompt = build_writer_system_prompt()
    # Lightweight initial user: lua + connected + reviewer feedback only.
    # The rejection_message already contains updated_content (current document after applied patches),
    # so including md_content here would duplicate the document at a stale pre-patch state.
    feedback_lines = []
    for i, issue in enumerate(review_feedback.issues, 1):
        suggestion = (
            review_feedback.suggestions[i - 1]
            if review_feedback.suggestions and i - 1 < len(review_feedback.suggestions)
            else ""
        )
        feedback_lines.append(f"{i}. Issue: {issue}")
        if suggestion:
            feedback_lines.append(f"   Suggestion: {suggestion}")
    feedback_block = "\n".join(feedback_lines)
    connected_block = connected_content if connected_content else "(none)"
    initial_user = (
        f"1. LUA SOURCE CODE (ground truth)\n```lua\n{lua_source}\n```\n\n"
        f"2. CONNECTED CONTENT (referenced files)\n{connected_block}\n\n"
        f"=== REVIEWER FEEDBACK ===\n{feedback_block}"
    )
    rejection_message = _build_guard_rejection_message(guard_blocked, updated_content)
    token_count = count_tokens(system_prompt + initial_user + previous_raw + rejection_message)
    print(f"  [content/writer] Guard correction prompt: {token_count:,} tokens")
    if DEBUG_PROMPTS:
        full = system_prompt + "\n\n" + initial_user + "\n\n[ASSISTANT]\n" + previous_raw + "\n\n[USER]\n" + rejection_message
        _dump_prompt("writer_guard_correction", full)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user},
        {"role": "assistant", "content": previous_raw},
        {"role": "user", "content": rejection_message},
    ]

    raw = ""
    patches: list[Patch] = []
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages, format=PATCHES_SCHEMA)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("writer_guard_correction_response", raw)
        remaining = BAD_RESPONSE_RETRIES - attempt
        if not raw.strip():
            if remaining > 0:
                print(f"  [content/writer] Guard correction empty → retrying ({remaining} left)")
                continue
            break
        patches = parse_writer_response(raw)
        if patches:
            break
        if remaining > 0:
            print(f"  [content/writer] Guard correction no patches → retrying ({remaining} left)")
        else:
            print(f"  [content/writer] Guard correction no patches after {BAD_RESPONSE_RETRIES + 1} attempts")

    if patches:
        print(f"  [content/writer] Guard correction: {len(patches)} patch(es) generated")
    else:
        print(f"  [content/writer] Guard correction returned no patches")
    return patches
