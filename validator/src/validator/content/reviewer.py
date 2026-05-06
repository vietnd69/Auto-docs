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
from validator.content.schemas import REVIEW_SCHEMA
from validator.content.guards import is_runaway, validate_review_schema, compact_bad_response

_GUARD_RUNAWAY = (
    "[BAD RESPONSE GUARD] Your previous response contained repeated non-JSON content "
    "and could not be used.\n"
    "You MUST respond with a single valid JSON object matching the schema:\n"
    '{"approved": <bool>, "findings": [{"issue": "<str>", "suggestion": "<str>"}]}\n'
    "Do NOT generate markdown tables, repeated rows, or any text outside the JSON object."
)
_GUARD_PARSE = (
    "[BAD RESPONSE GUARD] Your previous response could not be parsed as JSON.\n"
    'Respond ONLY with a valid JSON object: {"approved": <bool>, "findings": [...]}'
)
_GUARD_SCHEMA = (
    "[BAD RESPONSE GUARD] Your JSON response is missing required fields.\n"
    "Required: 'approved' (boolean) and 'findings' (array of objects with "
    "'issue' (string) and 'suggestion' (string)).\n"
    "Respond with a correctly structured JSON object."
)
_GUARD_INVARIANT = (
    "[BAD RESPONSE GUARD] Invalid state: 'approved' is false but 'findings' is empty.\n"
    "If there are content issues, list them in 'findings'. "
    "If the document is correct, set 'approved' to true."
)

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
    need_special_case: bool = False
    special_case_reason: str = ""
    special_case_standard_heading: str = ""  # the standard heading being replaced, e.g. "## Main functions"
    raw_response: str = ""  # raw LLM JSON response — used for multi-turn correction


@dataclass
class Finding:
    """One content accuracy issue targeting a specific (section, function, field)."""
    section: str           # e.g. "## Overview", "## Main functions"
    function: str | None   # None for non-function sections
    field: str | None      # e.g. "Returns", "Description", None = whole section/function
    rule_id: str           # typed identifier from allowed set for the section
    issue: str             # human-readable description


def parse_review_response(raw: str) -> ReviewResult:
    """Parse LLM2 response into ReviewResult. Handles JSON in markdown fences."""
    # Strip markdown code fence if present
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    # Remove <think>...</think> blocks (Qwen model)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()

    try:
        data = json.loads(cleaned)
        need_special_case = bool(data.get("need_special_case", False))
        special_case_reason = str(data.get("special_case_reason", ""))
        special_case_standard_heading = str(data.get("special_case_standard_heading", ""))
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
        return ReviewResult(
            approved=approved, issues=issues, suggestions=suggestions,
            need_special_case=need_special_case, special_case_reason=special_case_reason,
            special_case_standard_heading=special_case_standard_heading,
        )
    except (json.JSONDecodeError, TypeError):
        return ReviewResult(
            approved=False,
            issues=[f"Failed to parse reviewer response: {raw[:200]}"],
            suggestions=[],
        )


def parse_review_json(data: dict) -> ReviewResult:
    """Parse pre-validated JSON dict (from Ollama format parameter) into ReviewResult.

    Supports both the structured 'findings' format (from REVIEW_SCHEMA) and the
    legacy 'issues'/'suggestions' flat-array format.
    """
    need_special_case = bool(data.get("need_special_case", False))
    special_case_reason = str(data.get("special_case_reason", ""))
    special_case_standard_heading = str(data.get("special_case_standard_heading", ""))
    approved = bool(data.get("approved", False))
    if "findings" in data:
        findings = data["findings"] or []
        issues = [str(f.get("issue", "")) for f in findings if isinstance(f, dict)]
        suggestions = [str(f.get("suggestion", "")) for f in findings if isinstance(f, dict)]
    else:
        # Legacy format: separate issues/suggestions arrays
        issues = list(data.get("issues", []))
        suggestions = list(data.get("suggestions", []))
    return ReviewResult(
        approved=approved, issues=issues, suggestions=suggestions,
        need_special_case=need_special_case, special_case_reason=special_case_reason,
        special_case_standard_heading=special_case_standard_heading,
    )


def parse_findings_response(raw: str) -> list["Finding"]:
    """Parse LLM reviewer response into list of Finding objects."""
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
    try:
        data = json.loads(cleaned)
        return parse_findings_json(data)
    except (json.JSONDecodeError, TypeError):
        return []


def parse_findings_json(data: dict) -> list["Finding"]:
    """Parse pre-validated JSON dict into Finding list."""
    if not isinstance(data, dict):
        return []
    findings_data = data.get("findings") or []
    result = []
    for f in findings_data:
        if isinstance(f, dict) and f.get("rule_id") and f.get("issue"):
            result.append(Finding(
                section=str(f.get("section", "")),
                function=f.get("function") or None,
                field=f.get("field") or None,
                rule_id=str(f["rule_id"]),
                issue=str(f["issue"]),
            ))
    return result


def review_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    model: str,
    previous_review: "ReviewResult | None" = None,
    prior_turns: "list[dict] | None" = None,
) -> ReviewResult:
    """Send document to LLM2 for review. Returns structured ReviewResult.

    prior_turns: optional list of {"role": ..., "content": ...} dicts injected as
    conversation history before the current review request. Used to pass jury rejection
    context so the reviewer doesn't re-request special cases that were already denied.
    Structure expected: [..., assistant(prior_review_json), user(jury_verdict), ...]
    The last turn must be a user message — it is merged with the current review request.
    """
    system_prompt, user_content = build_reviewer_prompt(
        md_content, lua_source, connected_content,
        previous_issues=previous_review.issues if previous_review else None,
        previous_suggestions=previous_review.suggestions if previous_review else None,
    )
    token_count = count_tokens(system_prompt + user_content)
    prior_info = f" + {len(prior_turns)} prior turn(s)" if prior_turns else ""
    print(f"  [content/reviewer] Prompt: {token_count:,} tokens{prior_info}")

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if prior_turns:
        # Build multi-turn history so the reviewer "recalls" prior special-case attempts
        # and the jury verdicts that followed. Structure:
        #   system → user(doc) → [assistant(prior) → user(verdict)]* → user(verdict_n + current doc)
        messages.append({"role": "user", "content": user_content})
        messages.extend(prior_turns[:-1])
        last = prior_turns[-1]
        messages.append({
            "role": last["role"],
            "content": last["content"] + "\n\nNow re-review the document.",
        })
    else:
        messages.append({"role": "user", "content": user_content})

    if DEBUG_PROMPTS:
        full_dump = "\n\n".join(
            f"=== [{m['role'].upper()}] ===\n{m['content']}" for m in messages
        )
        _dump_prompt("reviewer", full_dump)
    result = ReviewResult(approved=False, issues=["No response"], suggestions=[])
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages, format=REVIEW_SCHEMA)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("reviewer_response", raw)
        remaining = BAD_RESPONSE_RETRIES - attempt

        # Layer 1: runaway detection (before JSON parse)
        if is_runaway(raw):
            print(f"  [content/reviewer] Runaway response ({len(raw):,} chars) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_RUNAWAY})
            continue

        # Layer 2: JSON parse
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            print(f"  [content/reviewer] Bad response (JSON parse) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_PARSE})
            continue

        # Layer 3: schema validation
        if not validate_review_schema(data):
            print(f"  [content/reviewer] Bad response (schema) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_SCHEMA})
            continue

        result = parse_review_json(data)

        # Layer 4: invariant — approved=false requires non-empty findings
        if not result.approved and not result.issues:
            print(f"  [content/reviewer] INVARIANT violation: approved=false with empty findings → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_INVARIANT})
            continue

        # All layers passed — safe to store raw_response
        result.raw_response = raw
        return result

    return result  # exhausted retries; raw_response="" prevents context contamination


def reviewer_oscillation_correction(
    md_content: str,
    lua_source: str,
    connected_content: str,
    current_review: ReviewResult,
    oscillating_issues: list[tuple[str, str]],
    model: str,
    resolved_history: list[str] | None = None,
) -> ReviewResult:
    """Multi-turn reviewer self-correction for oscillating issues.

    Sends: system → user(doc) → assistant(current_review.raw_response) → user(guard message)
    so the reviewer sees its own previous response and the contradiction, then re-reviews.

    oscillating_issues: list of (current_issue, contradicted_resolved_issue) pairs.
    """
    system_prompt, user_content = build_reviewer_prompt(
        md_content, lua_source, connected_content,
    )

    guard_lines = [
        "[OSCILLATION GUARD — SYSTEM FEEDBACK]",
        f"Your previous response found {len(current_review.issues)} issue(s), but {len(oscillating_issues)} of them",
        "contradict issues that were resolved in a previous iteration, causing an infinite correction loop.",
        "Please re-evaluate the following contradictions carefully:",
        "",
    ]
    for idx, (curr_iss, fixed_iss) in enumerate(oscillating_issues, 1):
        guard_lines += [
            f"Contradiction {idx}:",
            f'  You just flagged: "{curr_iss}"',
            f'  This contradicts a previously-resolved issue: "{fixed_iss}"',
            "  The document was already patched to address the earlier finding.",
            "  These two findings are contradictory — re-read the Lua source to determine which is correct.",
            "",
        ]
    if resolved_history:
        guard_lines += [
            "Additionally, the following issues were resolved in earlier iterations and MUST NOT be re-raised.",
            "Drop any finding that matches one of these resolved topics unless you have NEW concrete evidence from the Lua source:",
            "",
        ]
        for iss in resolved_history[:20]:
            guard_lines.append(f'  - "{iss[:150]}"')
        guard_lines.append("")
    guard_lines += [
        "Action required:",
        "- Re-read the relevant Lua source lines carefully.",
        "- Only flag an issue if you can point to a SPECIFIC LINE in the Lua source that contradicts the documentation.",
        "- If you cannot find concrete evidence in the source, do NOT re-raise the issue.",
        "- Provide a corrected review of the FULL document below (complete JSON response, not just the contradictions).",
    ]
    guard_message = "\n".join(guard_lines)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": current_review.raw_response},
        {"role": "user", "content": guard_message},
    ]

    token_count = count_tokens(system_prompt + user_content + current_review.raw_response + guard_message)
    print(f"  [content/reviewer] Oscillation correction prompt: {token_count:,} tokens")
    if DEBUG_PROMPTS:
        full_dump = "\n\n".join(f"=== [{m['role'].upper()}] ===\n{m['content']}" for m in messages)
        _dump_prompt("reviewer_oscillation_correction", full_dump)

    result = ReviewResult(approved=False, issues=["No response"], suggestions=[])
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages, format=REVIEW_SCHEMA)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("reviewer_oscillation_correction_response", raw)
        remaining = BAD_RESPONSE_RETRIES - attempt

        # Layer 1: runaway detection
        if is_runaway(raw):
            print(f"  [content/reviewer] Oscillation correction runaway ({len(raw):,} chars) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_RUNAWAY})
            continue

        # Layer 2: JSON parse
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            print(f"  [content/reviewer] Oscillation correction bad response (JSON parse) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_PARSE})
            continue

        # Layer 3: schema validation
        if not validate_review_schema(data):
            print(f"  [content/reviewer] Oscillation correction bad response (schema) → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_SCHEMA})
            continue

        result = parse_review_json(data)

        # Layer 4: invariant
        if not result.approved and not result.issues:
            print(f"  [content/reviewer] Oscillation correction INVARIANT violation → retrying ({remaining} left)")
            if remaining > 0:
                messages.append({"role": "assistant", "content": compact_bad_response(raw)})
                messages.append({"role": "user", "content": _GUARD_INVARIANT})
            continue

        result.raw_response = raw
        return result

    return result  # exhausted retries; raw_response="" prevents context contamination
