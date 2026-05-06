"""Response validation guards for LLM structured outputs."""


def is_runaway(raw: str) -> bool:
    """Detect repetitive/looping LLM output (e.g. repeated markdown table rows).

    Returns True if any non-trivial line repeats >=8 times in a sufficiently
    large response. Checked before json.loads to catch format-enforcement failures.
    """
    if len(raw) < 3000:
        return False
    lines = [l.strip() for l in raw.splitlines() if l.strip() and len(l.strip()) > 10]
    if len(lines) < 20:
        return False
    counts: dict[str, int] = {}
    for line in lines:
        counts[line] = counts.get(line, 0) + 1
    return max(counts.values(), default=0) >= 8


def validate_review_schema(data: object) -> bool:
    """Validate parsed JSON against REVIEW_SCHEMA structure.

    Required: approved (bool), findings (list of {issue: str, suggestion: str}).
    """
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("approved"), bool):
        return False
    findings = data.get("findings")
    if not isinstance(findings, list):
        return False
    for f in findings:
        if not isinstance(f, dict):
            return False
        if not isinstance(f.get("issue"), str) or not isinstance(f.get("suggestion"), str):
            return False
    return True


def validate_patches_schema(data: object) -> bool:
    """Validate parsed JSON against PATCHES_SCHEMA structure.

    Required: list of {old_text: str, new_text: str, reason: str}.
    """
    if not isinstance(data, list):
        return False
    for p in data:
        if not isinstance(p, dict):
            return False
        for key in ("old_text", "new_text", "reason"):
            if not isinstance(p.get(key), str):
                return False
    return True


def validate_jury_schema(data: object) -> bool:
    """Validate parsed JSON against JURY_VOTE_SCHEMA structure.

    Required: vote in {"yes", "no"}, reason (str).
    """
    if not isinstance(data, dict):
        return False
    if data.get("vote") not in ("yes", "no"):
        return False
    if not isinstance(data.get("reason"), str):
        return False
    return True


def compact_bad_response(raw: str, max_chars: int = 500) -> str:
    """Compact a large/bad LLM response for safe injection as assistant turn in retry.

    For runaway responses: summarizes the repeated pattern.
    For other large responses: truncates with size prefix.
    Always much smaller than the original, preventing prompt bloat on retry.
    """
    if len(raw) <= max_chars:
        return raw

    lines = [l.strip() for l in raw.splitlines() if l.strip() and len(l.strip()) > 10]
    if lines:
        counts: dict[str, int] = {}
        for line in lines:
            counts[line] = counts.get(line, 0) + 1
        max_count = max(counts.values(), default=0)
        if max_count >= 8:
            most_repeated = max(counts, key=lambda k: counts[k])
            return (
                f"[RESPONSE TRUNCATED — {len(raw):,} chars / {len(lines):,} lines — runaway detected]\n"
                f"Most repeated line ({max_count}×): {most_repeated[:100]!r}\n"
                f"First 200 chars: {raw[:200]!r}"
            )

    return f"[RESPONSE TRUNCATED — {len(raw):,} chars]\n{raw[:max_chars]}..."
