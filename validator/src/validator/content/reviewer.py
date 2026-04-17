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
            "content": last["content"] + "\n\nNow re-review the updated document:\n\n" + user_content,
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
        result = parse_review_response(raw)
        is_parse_error = not raw.strip() or (result.issues and result.issues[0].startswith("Failed to parse"))
        is_invariant_violation = not result.approved and not result.issues
        is_bad = is_parse_error or is_invariant_violation
        if not is_bad:
            return result
        remaining = BAD_RESPONSE_RETRIES - attempt
        if is_invariant_violation:
            print(f"  [content/reviewer] INVARIANT violation: approved=false with empty findings → retrying ({remaining} left)")
        elif remaining > 0:
            print(f"  [content/reviewer] Bad response → retrying ({remaining} left)")
        else:
            print(f"  [content/reviewer] Bad response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")
    return result
