"""
Pre-synthesis aggregation — pure Python, no LLM calls.

Parses JSON output from all chunks and aggregates into a single
PreSynthesisResult that the merge LLM receives as pre-filled data.

Functions:
  - pre_synthesize(): parse + aggregate all chunk JSON results
  - PreSynthesisResult: dataclass holding aggregated data
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass

SCOPE_PATTERN = re.compile(r'^[a-z_]+$')  # lowercase letters and underscores only


@dataclass
class PreSynthesisResult:
    tags: list[str]                    # dedup, sorted
    system_scope: str                  # majority vote, format-validated
    dependencies: list[dict]           # dedup by "component"
    partial_descriptions: list[str]    # 1 per chunk, for merge LLM
    functions: list[dict]              # flat, incomplete=False only
    events_listens: list[dict]         # dedup by "event"
    events_pushes: list[dict]          # dedup by "event"
    constructor_properties: list[dict] # dedup by "name"


def pre_synthesize(
    chunk_results: dict[int, str],     # {chunk_index (1-based): json_string}
) -> tuple[PreSynthesisResult, list[int]]:
    """
    Parse and aggregate JSON from all chunks.
    Returns (PreSynthesisResult, malformed_indices).
    malformed_indices != [] means caller must block merge and retry.
    When malformed chunks exist, valid data is discarded — the function
    always needs all chunks clean to ensure complete aggregation.
    """
    valid_chunks: list[dict] = []
    malformed_indices: list[int] = []

    for idx in sorted(chunk_results.keys()):
        raw = chunk_results[idx]
        try:
            parsed = json.loads(raw)
            valid_chunks.append(parsed)
        except (json.JSONDecodeError, ValueError):
            malformed_indices.append(idx)

    if malformed_indices:
        return _empty_result(), malformed_indices

    return _aggregate(valid_chunks), []


def _aggregate(chunks: list[dict]) -> PreSynthesisResult:
    tags = sorted({
        t["name"] for c in chunks
        for t in c.get("tags", [])
        if t.get("name") and t["name"] != "None"
    })
    deps = _dedup_by_key(
        [d for c in chunks for d in c.get("dependencies", []) if d.get("component") != "None"],
        "component"
    )
    props = _dedup_by_key(
        [p for c in chunks for p in c.get("constructor_properties", [])],
        "name"
    )
    listens = _dedup_by_key(
        [e for c in chunks for e in c.get("events", {}).get("listens_to", [])],
        "event"
    )
    pushes = _dedup_by_key(
        [e for c in chunks for e in c.get("events", {}).get("pushes", [])],
        "event"
    )
    scope = _majority_vote(
        [c.get("suggested_scope", "") for c in chunks],
        fallback="entity",
    )
    descs = [
        c["partial_description"] for c in chunks
        if c.get("partial_description") and c["partial_description"] != "None"
    ]
    # Functions: flatten, exclude incomplete.
    # Name-level dedup is the merge LLM's responsibility (semantic dedup).
    # Python only removes functions cut at chunk boundaries.
    funcs = [
        f for c in chunks
        for f in c.get("functions", [])
        if not f.get("incomplete")
    ]

    return PreSynthesisResult(tags, scope, deps, descs, funcs, listens, pushes, props)


def _empty_result() -> PreSynthesisResult:
    return PreSynthesisResult(
        tags=[], system_scope="entity", dependencies=[],
        partial_descriptions=[], functions=[],
        events_listens=[], events_pushes=[], constructor_properties=[]
    )


def _dedup_by_key(items: list[dict], key: str) -> list[dict]:
    """Keep first-seen entry for each value of key."""
    seen: set[str] = set()
    result: list[dict] = []
    for item in items:
        k = item.get(key, "")
        if k and k not in seen:
            seen.add(k)
            result.append(item)
    return result


def _majority_vote(values: list[str], fallback: str) -> str:
    """
    Majority vote from list of values.
    Validate format: lowercase letters and underscores only (e.g. "player", "combat_ai").
    Tie-break: first-seen order in the original list.
    If no value passes format validation, return fallback.
    """
    valid_values = [v for v in values if v and SCOPE_PATTERN.match(v)]
    if not valid_values:
        return fallback
    counts = Counter(valid_values)
    max_count = max(counts.values())
    # Tie-break: first-seen order
    for v in valid_values:
        if counts[v] == max_count:
            return v
    return fallback
