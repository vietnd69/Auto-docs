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

# Lua standard-library names that are always available and not worth listing as external deps
_LUA_STDLIB = frozenset({
    "math", "string", "table", "io", "os", "coroutine", "package", "debug",
    "ipairs", "pairs", "next", "select", "type", "tostring", "tonumber",
    "rawget", "rawset", "rawequal", "rawlen", "setmetatable", "getmetatable",
    "pcall", "xpcall", "error", "assert", "print", "unpack",
})


@dataclass
class PreSynthesisResult:
    game_tags: list[dict]              # [{name, operation}] — dedup by "name"
    external_deps: list[dict]          # [{name, usage}]     — dedup by "name"
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
            if not isinstance(parsed, dict) or "functions" not in parsed:
                raise ValueError("chunk JSON missing required shape (must be dict with 'functions' key)")
            valid_chunks.append(parsed)
        except (json.JSONDecodeError, ValueError):
            malformed_indices.append(idx)

    if malformed_indices:
        return _empty_result(), malformed_indices

    return _aggregate(valid_chunks), []


def _aggregate(chunks: list[dict]) -> PreSynthesisResult:
    game_tags = _dedup_by_key(
        [t for c in chunks for t in c.get("game_tags", [])
         if t.get("name") and t["name"] != "None"],
        "name"
    )
    external_deps = _dedup_by_key(
        [_normalize_ext_dep(d) for c in chunks for d in c.get("external_deps", [])
         if d.get("name") and d["name"] != "None"
         and d["name"].split(".")[0] not in _LUA_STDLIB],
        "name"
    )
    deps = _dedup_by_key(
        [d for c in chunks for d in c.get("dependencies", []) if d.get("component") != "None"],
        "component"
    )
    props = _dedup_by_key(
        [p for c in chunks for p in c.get("constructor_properties", [])
         if isinstance(p, dict) and p.get("name") and p["name"] != "None"],
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
    # Functions: flatten, exclude incomplete, deduplicate by name.
    # Keep first occurrence (earlier chunk = earlier in source file = more likely correct definition).
    funcs = _dedup_by_key(
        [f for c in chunks for f in c.get("functions", []) if not f.get("incomplete")],
        "name",
    )

    return PreSynthesisResult(game_tags, external_deps, scope, deps, descs, funcs, listens, pushes, props)


def _empty_result() -> PreSynthesisResult:
    return PreSynthesisResult(
        game_tags=[], external_deps=[], system_scope="entity",
        dependencies=[], partial_descriptions=[], functions=[],
        events_listens=[], events_pushes=[], constructor_properties=[]
    )


def _normalize_ext_dep(dep: dict) -> dict:
    """Normalize GLOBAL.X → GLOBAL so all sub-field accesses collapse to one entry."""
    name = dep.get("name", "")
    if name.startswith("GLOBAL."):
        return dict(dep, name="GLOBAL")
    return dep


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
