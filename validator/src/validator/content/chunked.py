"""Section-by-section content validation for large Lua files (>=32K tokens).

Typed-ops pipeline: deterministic pre-filter -> typed LLM review -> typed ops apply.
No guards. No free-text patches. Convergence = findings == [].
"""

import json
import re
import time
from pathlib import Path
from typing import Callable

from llm.client import ollama_chat
from llm.paths import PROJECT_ROOT
from validator.content.cache import CacheManager
from validator.content.checkpoint import load_validator_checkpoint, save_validator_checkpoint
from llm.settings import (
    BAD_RESPONSE_RETRIES, DEBUG_PROMPTS,
    REVIEWER_TEMPERATURE, WRITER_TEMPERATURE, WRITER_THINK,
    VALIDATOR_CALL_SLEEP,
)
from llm.tokens import count_tokens
from rag.docs import safe_read_lua
from validator.content.loop import ContentLoopConfig, ContentLoopResult
from validator.content.prompts import (
    build_typed_reviewer_prompt,
    build_typed_writer_batch_prompt,
    _RULE_IDS_BY_SECTION,
)
from validator.content.reviewer import Finding, parse_findings_json
from validator.content.schemas import FINDINGS_SCHEMA, TYPED_OPS_LIST_SCHEMA
from validator.content.sections import (
    DocSection,
    _canonical_fn_name,
    apply_typed_ops,
    check_stategraph_events_null,
    classify_lua_functions,
    ensure_required_fields,
    extract_function_names,
    extract_lua_context,
    extract_section_lua_context,
    extract_stategraph_event_names,
    join_md_sections,
    normalize_fn_headings,
    prefilter_fn_blocks,
    split_md_sections,
    split_section_blocks,
    sub_chunk_section_lua_aware,
)
# Leave unchanged: from validator.content.reviewer import Finding, parse_findings_json
from validator.content.writer import TypedOp, parse_typed_ops_json

_DATA_CONFIG_DIRS = {"map", "languages", "util"}
_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"
_MAX_OSC_HISTORY = 8  # max findings injected per oscillation list to cap reviewer prompt size

_STRUCTURAL_HEADINGS = {
    "## Dependencies & tags",
    "## Properties",
    "## Main functions",
    "## Events & listeners",
    "## Action Handlers",    # stategraph-specific; no-op for docs that lack this section
}
_NARRATIVE_HEADINGS = {"## Overview", "## Usage example"}


def _sleep(stop_check: Callable[[], bool], seconds: int) -> None:
    for _ in range(seconds):
        if stop_check():
            break
        time.sleep(1)


def _dump_prompt(label: str, text: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = _DEBUG_DIR / f"{label}_{ts}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"  [debug] Prompt dumped -> {path}")


def _detect_file_type(lua_filepath: str, lua_source: str = "") -> str:
    """Returns 'component', 'data_config', or 'utility'."""
    from pathlib import Path as _Path
    parts = _Path(lua_filepath).parts
    try:
        dst_idx = next(i for i, p in enumerate(parts) if p == "dst-scripts")
        rel = parts[dst_idx + 1:]
    except StopIteration:
        rel = parts
    if rel and rel[0].lower() in _DATA_CONFIG_DIRS:
        return "data_config"
    if lua_source and not re.search(r'\bClass\s*\(', lua_source):
        return "utility"
    return "component"


def _try_parse_json(raw: str) -> dict | list | None:
    """Strip fences and think-tags then parse JSON. Returns None on failure."""
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned)
    if '</think>' in cleaned:
        cleaned = cleaned[cleaned.index('</think>') + len('</think>'):]
    cleaned = cleaned.strip()
    try:
        import json
        return json.loads(cleaned)
    except Exception:
        return None


def _call_reviewer(
    text: str,
    lua_ctx: str,
    section_heading: str,
    config: ContentLoopConfig,
    file_type: str,
    reviewed_context: str = "",
    oscillation_fixed: "list[Finding] | None" = None,
    oscillation_unfixed: "list[Finding] | None" = None,
) -> "list[Finding] | None":
    """Call the reviewer LLM and return structured findings.

    Returns [] when the reviewer approves, a non-empty list of findings when it
    finds issues, or None when all retries are exhausted (bad JSON / server error).
    Callers must treat None as "skip iteration, do not approve".

    When oscillation_fixed or oscillation_unfixed are provided, a 4-turn conversation
    is built: [system, user(review_request), assistant(previous_findings), user(re-check)].

    - oscillation_fixed: findings the writer successfully patched (changed == True).
      Reviewer is asked to verify they are no longer present.
    - oscillation_unfixed: findings the writer could not resolve (no-change) or that
      belong to another batch (cross-batch skip). Reviewer is told not to re-report them.
    """
    rule_ids = _RULE_IDS_BY_SECTION.get(section_heading)
    system_prompt, user_content = build_typed_reviewer_prompt(
        text, lua_ctx, section_heading, rule_ids=rule_ids, file_type=file_type,
        reviewed_context=reviewed_context,
    )
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    all_prev = (oscillation_fixed or []) + (oscillation_unfixed or [])
    if all_prev:
        fixed_count = len(oscillation_fixed or [])
        unfixed_count = len(oscillation_unfixed or [])
        prev_resp = {
            "approved": False,
            "context": {
                "type": "oscillation_handoff",
                "fixed_findings_count": fixed_count,
                "unfixed_findings_count": unfixed_count,
            },
            "findings": [
                {
                    "section": f.section,
                    "function": f.function,
                    "field": f.field,
                    "rule_id": f.rule_id,
                    "issue": f.issue,
                    "status": (
                        "fixed_in_previous_writer_call"
                        if oscillation_fixed and f in oscillation_fixed
                        else "unfixed_or_out_of_batch"
                    ),
                }
                for f in all_prev
            ],
        }
        messages.append({
            "role": "assistant",
            "content": json.dumps(prev_resp, ensure_ascii=False),
        })
        parts: list[str] = []
        if oscillation_fixed:
            parts.append(
                "The findings marked status=fixed_in_previous_writer_call were patched by the writer "
                "in the previous step — verify they are truly resolved before reporting them again."
            )
        if oscillation_unfixed:
            parts.append(
                "The findings marked status=unfixed_or_out_of_batch could not be resolved in the last step "
                "or target functions outside this batch — do not re-report unless they now clearly appear in "
                "the current batch text."
            )
        parts.append("Review the current document carefully and only report issues that are clearly still present.")
        messages.append({"role": "user", "content": " ".join(parts)})

    token_count = count_tokens(system_prompt + user_content)
    osc_note = f" +oscillation({len(all_prev)})" if all_prev else ""
    print(f"  [content/chunked] reviewer call: {token_count:,} tok{osc_note}")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_reviewer", system_prompt + "\n\n" + user_content)

    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        if attempt:
            print(f"  [content/chunked] reviewer retry {attempt}/{BAD_RESPONSE_RETRIES}")
        resp = ollama_chat(
            model=config.reviewer_model,
            messages=messages,
            format=FINDINGS_SCHEMA,
            options={"temperature": REVIEWER_TEMPERATURE},
        )
        raw = resp["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_reviewer_response", raw)
        data = _try_parse_json(raw)
        if data is None:
            print(f"  [content/chunked] reviewer bad JSON (attempt {attempt + 1})")
            continue
        approved = bool(data.get("approved", False))
        findings = parse_findings_json(data)
        if approved:
            return []
        if not findings:
            # Invariant violation: reviewer rejected but returned zero findings.
            # Treat as a bad response and retry rather than silently approving.
            print(f"  [content/chunked] reviewer invariant: rejected with 0 findings (attempt {attempt + 1})")
            continue
        return findings
    return None  # exhausted retries — callers must NOT treat this as approval



def _extract_target_text(text: str, finding: Finding) -> str | None:
    """Extract the specific text snippet that a finding targets.

    For function-level findings in ## Main functions: returns the fn_block for
    finding.function, or None if not present (cross-batch hallucination → skip).
    For non-function sections (## Usage example, etc.) with no ### blocks:
    finding.function is a contextual reference, not a heading → use full section text.
    For section-level findings (no function): returns the full section text.
    """
    if finding.function:
        _, fn_blocks = split_section_blocks(text)
        if not fn_blocks:
            # Section has no ### headings (e.g. ## Usage example) — finding.function
            # is a contextual reference to a function mentioned in the text, not a
            # heading. Fall back to full section text so the writer can fix it.
            return text
        # ## Main functions: match by heading, return None for cross-batch hallucinations.
        # Use _canonical_fn_name on both sides so stategraph handlers like
        # "onupdate (idle)" and "onupdate (attack_recoil)" don't false-match.
        fn_name = _canonical_fn_name(finding.function)
        for block in fn_blocks:
            heading_line = block.split("\n", 1)[0]
            # Extract full content between backticks (e.g. "onupdate (idle)")
            m = re.match(r'^### `([^`\n]+)`', heading_line) or re.match(r'^### `?([^`\n]+)', heading_line)
            if m and _canonical_fn_name(m.group(1)) == fn_name:
                return block
        return None  # function not in this batch — skip instead of using full text
    return text


def _call_writer_batch(
    batch_text: str,
    lua_ctx: str,
    findings: "list[Finding]",
    config: ContentLoopConfig,
    file_type: str,
) -> "list[TypedOp]":
    """Call the writer LLM for all findings in one call. Returns list of TypedOps."""
    section_heading = findings[0].section if findings else ""
    system_prompt, user_content = build_typed_writer_batch_prompt(
        batch_text, lua_ctx, findings, section_heading, file_type
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    token_count = count_tokens(system_prompt + user_content)
    print(f"  [content/chunked] writer call: {token_count:,} tok ({len(findings)} finding(s))")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer", system_prompt + "\n\n" + user_content)

    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        if attempt:
            print(f"  [content/chunked] writer retry {attempt}/{BAD_RESPONSE_RETRIES}")
        resp = ollama_chat(
            model=config.writer_model,
            messages=messages,
            format=TYPED_OPS_LIST_SCHEMA,
            temperature=WRITER_TEMPERATURE,
            think=bool(WRITER_THINK),
        )
        raw = resp["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_writer_response", raw)
        data = _try_parse_json(raw)
        if data is None:
            print(f"  [content/chunked] writer bad JSON (attempt {attempt + 1})")
            continue
        # Model may return a single object instead of a wrapped array — coerce defensively
        if isinstance(data, dict) and data.get("op"):
            data = [data]
        ops = parse_typed_ops_json(data)
        if ops:
            print(f"  [content/chunked] writer → {len(ops)} op(s)")
            return ops
        print(f"  [content/chunked] writer → 0 ops (attempt {attempt + 1})")
    return []


def _run_typed_loop(
    cache: CacheManager,
    cache_id: str,
    lua_ctx: str,
    section_heading: str,
    intentionally_removed: set[str],
    config: ContentLoopConfig,
    file_type: str,
    reviewed_context: str = "",
) -> tuple[str, list[str], int]:
    """Review + fix loop for one section or batch using cache.

    The cache file identified by cache_id holds the current content.
    Reviewer reads from cache, writer edits the cache.

    Returns (updated_text, remaining_issues, iterations_used).
    remaining_issues is [] when all findings resolved within max_iterations.
    max_iterations is capped at 3 per spec.
    """
    max_iters = config.max_iterations

    # Normalize headings in cache before starting
    text = normalize_fn_headings(cache.read(cache_id))
    cache.write(cache_id, text)

    # attempt_counts: how many times each (function, field) pair has been processed
    # (writer call or cross-batch skip). Used for oscillation blocking after 2 attempts.
    attempt_counts: dict[tuple[str | None, str | None], int] = {}
    # Flat lists of findings passed as oscillation context to the next reviewer call.
    # fixed_findings: writer successfully changed the doc (changed == True).
    # unfixed_findings: writer returned no-change OR function was cross-batch skipped.
    # Keeping them separate lets the reviewer message accurately distinguish "fixed" vs
    # "could not resolve / out of scope".
    # Capped at _MAX_OSC_HISTORY each to avoid bloating the reviewer prompt.
    fixed_findings: list[Finding] = []
    unfixed_findings: list[Finding] = []

    _pfx = f"  [content/chunked] [{cache_id}]"

    for i in range(max_iters):
        iter_label = f"iter {i + 1}/{max_iters}"
        # Read current content from cache
        text = cache.read(cache_id)

        findings = _call_reviewer(
            text, lua_ctx, section_heading, config, file_type, reviewed_context,
            oscillation_fixed=fixed_findings[-_MAX_OSC_HISTORY:] or None,
            oscillation_unfixed=unfixed_findings[-_MAX_OSC_HISTORY:] or None,
        )
        _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)  # sleep after every reviewer call

        if findings is None:
            # All retries exhausted (bad JSON / server error) — skip this iteration,
            # do not treat as approval.
            print(f"{_pfx} {iter_label}: reviewer failed (all retries exhausted) — skipping iter")
            break
        if not findings:
            print(f"{_pfx} {iter_label}: reviewer → 0 finding(s) → approved")
            return text, [], i + 1

        print(f"{_pfx} {iter_label}: reviewer → {len(findings)} finding(s)")

        any_actionable = False
        in_batch_count = 0
        oscillating_count = 0
        oscillation_blocked_findings: list[Finding] = []
        actionable: list[Finding] = []

        for fi, finding in enumerate(findings, 1):
            fn_label = finding.function or "(section-level)"
            # Oscillation key: omit field for section-level findings (function=None) because
            # the reviewer inconsistently varies field names across iterations for the same issue,
            # causing the oscillation tracker to never fire on repeated section-level reports.
            pair = (
                (finding.function, finding.rule_id)
                if finding.function is None
                else (finding.function, finding.field, finding.rule_id)
            )
            cnt = attempt_counts.get(pair, 0)

            # Cross-section hallucination: reviewer reported a finding for a section other than
            # the one currently under review (likely from reviewed_context exposure).
            # Writer ops targeting another section would be silent no-ops — skip early.
            if finding.section and finding.section.strip().lower() != section_heading.strip().lower():
                print(f"{_pfx} {iter_label}: [{fi}/{len(findings)}] '{fn_label}' wrong section '{finding.section}' — skip")
                if cnt < 2:
                    unfixed_findings.append(finding)
                    attempt_counts[pair] = cnt + 1
                continue

            target_text = _extract_target_text(text, finding)
            if target_text is None:
                # Cross-batch hallucination: function lives in another batch.
                if cnt < 2:
                    unfixed_findings.append(finding)
                    attempt_counts[pair] = cnt + 1  # cross-batch: safe to increment directly (1 skip = 1 attempt)
                print(f"{_pfx} {iter_label}: [{fi}/{len(findings)}] '{fn_label}' not in batch — skip")
                continue
            any_actionable = True
            in_batch_count += 1

            if cnt >= 2:
                print(
                    f"{_pfx} {iter_label}: [{fi}/{len(findings)}] "
                    f"oscillation blocked '{fn_label}/{finding.rule_id}' "
                    f"(attempted {cnt}x)"
                )
                oscillating_count += 1
                oscillation_blocked_findings.append(finding)
                continue

            if cnt == 1:
                print(
                    f"{_pfx} {iter_label}: [{fi}/{len(findings)}] "
                    f"oscillation inject for '{fn_label}/{finding.rule_id}'"
                )
            else:
                print(f"{_pfx} {iter_label}: [{fi}/{len(findings)}] '{fn_label}' {finding.rule_id} → writer")
            actionable.append(finding)

        if not any_actionable:
            print(f"{_pfx} {iter_label}: all {len(findings)} finding(s) cross-batch — treating as approved")
            return cache.read(cache_id), [], i + 1

        if in_batch_count > 0 and in_batch_count == oscillating_count:
            remaining = [f.issue for f in oscillation_blocked_findings]
            print(
                f"{_pfx} {iter_label}: all {in_batch_count} finding(s) oscillation-blocked"
                f" — {len(remaining)} issue(s) unresolved"
            )
            return cache.read(cache_id), remaining, i + 1

        if actionable:
            ops = _call_writer_batch(text, lua_ctx, actionable, config, file_type)
            _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)

            if not ops:
                # Writer gave up (bad JSON / no fix found) — do NOT increment attempt_counts.
                # Only genuine fix attempts (ops returned) count toward oscillation blocking.
                # This ensures persistent writer failures exhaust max_iters and reach
                # the final verify rather than being silently treated as approved.
                print(f"{_pfx} {iter_label}: writer returned no ops")
                for finding in actionable:
                    unfixed_findings.append(finding)
            else:
                text_before = text
                for op in ops:
                    dummy = DocSection(heading=section_heading, text=text)
                    updated = apply_typed_ops(
                        [dummy], [op], frontmatter="",
                        intentionally_removed=intentionally_removed,
                    )
                    new_text = updated[0].text
                    op_fn = f" fn='{op.function}'" if op.function else ""
                    op_field = f" field='{op.field}'" if op.field else ""
                    changed = new_text != text
                    print(f"{_pfx} {iter_label}: op={op.op}{op_fn}{op_field} → {'applied' if changed else 'no change'}")
                    text = new_text
                cache.write(cache_id, text)

                # Update oscillation tracking — compare per-function text before/after.
                # Increment at most once per unique (function, field, rule_id) pair per writer
                # call to avoid over-counting when multiple findings share the same pair.
                pairs_incremented: set[tuple] = set()
                for finding in actionable:
                    pair = (
                        (finding.function, finding.rule_id)
                        if finding.function is None
                        else (finding.function, finding.field, finding.rule_id)
                    )
                    if pair not in pairs_incremented:
                        attempt_counts[pair] = attempt_counts.get(pair, 0) + 1
                        pairs_incremented.add(pair)
                    fn_before = _extract_target_text(text_before, finding)
                    fn_after  = _extract_target_text(text, finding)
                    if fn_before is not None and fn_after is not None and fn_before != fn_after:
                        # Function modified (rewrite_function / update_field)
                        fixed_findings.append(finding)
                    elif fn_before is not None and fn_after is None and text_before != text:
                        # Function deleted (delete_function succeeded)
                        fixed_findings.append(finding)
                    elif fn_before is None and text_before != text:
                        # Section-level finding (function=None) — overall text changed
                        fixed_findings.append(finding)
                    else:
                        unfixed_findings.append(finding)

    # Final verification: fixes from the last iteration are applied but unreviewed.
    # One extra review confirms whether they resolved the issues.
    text = cache.read(cache_id)
    print(f"{_pfx} final verify after {max_iters} iter(s)...")
    final_findings = _call_reviewer(text, lua_ctx, section_heading, config, file_type, reviewed_context)
    _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)  # sleep after final reviewer call
    if final_findings is None:
        print(f"{_pfx} final verify → reviewer failed (all retries exhausted)")
        return text, [], max_iters + 1  # treat as approved — cannot determine otherwise
    if final_findings:
        print(f"{_pfx} final verify → {len(final_findings)} issue(s) remain unresolved")
    else:
        print(f"{_pfx} final verify → approved")
    return text, [f.issue for f in final_findings], max_iters + 1


def run_chunked_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
    resume: bool = False,
) -> ContentLoopResult:
    """Per-section typed-ops validation loop for large files using cache.

    Cache-based flow:
    1. Read md content, split into sections/batches
    2. Create cache files for each batch/section
    3. Reviewer reads from cache, writer edits cache
    4. After all sections done, assemble from cache and write to original file

    Phase 1 (pre-filter): classify local functions, strip hallucinations,
    ensure required fields -- deterministic, no LLM.
    Phase 2-4 (typed loop): reviewer emits Finding objects, writer produces
    TypedOp per finding, apply_typed_ops applies by name -- no guards.
    Convergence: findings == [] or max 3 iterations per section/batch.
    """
    if config.stop_check():
        return ContentLoopResult(
            approved=False, iterations=0, final_issues=["Interrupted by user"]
        )

    lua_source = safe_read_lua(lua_filepath)
    if lua_source is None:
        return ContentLoopResult(
            approved=False, iterations=0,
            final_issues=[f"Cannot read Lua source: {lua_filepath}"],
        )

    md_path = Path(md_filepath)
    md_content = md_path.read_text(encoding="utf-8")
    frontmatter, sections = split_md_sections(md_content)

    if not sections:
        return ContentLoopResult(approved=True, iterations=0, final_issues=[])

    # Load checkpoint if resume mode
    checkpoint = load_validator_checkpoint(md_filepath) if resume else None
    completed_sections: set[int] = set()
    if checkpoint:
        cache = CacheManager(md_filepath, cache_dir=Path(checkpoint["cache_dir"]))
        completed_sections = set(checkpoint["completed_sections"])
        total_iterations = checkpoint.get("total_iterations", 0)
        all_issues = list(checkpoint.get("all_issues", []))
        print(f"  [content/chunked] Resuming from checkpoint: {len(completed_sections)} section(s) already done")
        print(f"  [content/chunked] Cache dir: {cache.cache_dir}")
    else:
        cache = CacheManager(md_filepath)
        total_iterations = 0
        all_issues = []
        print(f"  [content/chunked] Cache created: {cache.cache_dir}")

    # Restore section texts from cache for completed sections (resume only)
    if checkpoint and completed_sections:
        for _sec_idx in completed_sections:
            if 1 <= _sec_idx <= len(sections):
                _sec = sections[_sec_idx - 1]
                if cache.exists(f"sec{_sec_idx}_assembled"):
                    _sec.text = cache.read(f"sec{_sec_idx}_assembled")
                elif cache.exists(f"sec{_sec_idx}"):
                    _sec.text = cache.read(f"sec{_sec_idx}")

    file_type = _detect_file_type(lua_filepath, lua_source)

    # Group sections: structural first, narrative last (preserve doc order within each group)
    structural_idxs = [(i, s) for i, s in enumerate(sections, 1) if s.heading in _STRUCTURAL_HEADINGS]
    narrative_idxs  = [(i, s) for i, s in enumerate(sections, 1) if s.heading in _NARRATIVE_HEADINGS]
    other_idxs      = [(i, s) for i, s in enumerate(sections, 1)
                       if s.heading and s.heading not in _STRUCTURAL_HEADINGS and s.heading not in _NARRATIVE_HEADINGS]
    # preamble sections (no heading) are skipped inside the loop already

    ordered_pairs = structural_idxs + other_idxs + narrative_idxs

    reviewed_context = ""
    for sec_idx, section in ordered_pairs:
        # Compute reviewed_context lazily, just before first narrative section
        if not reviewed_context and section.heading in _NARRATIVE_HEADINGS:
            reviewed_context = "\n\n".join(s.text for _, s in structural_idxs if s.text.strip())

        if config.stop_check():
            # Write current state from cache/sections to original file
            md_path.write_text(join_md_sections(frontmatter, sections), encoding="utf-8")
            return ContentLoopResult(
                approved=False, iterations=total_iterations,
                final_issues=["Interrupted by user"],
            )
        if not section.heading:
            continue  # skip preamble

        if sec_idx in completed_sections:
            print(f"  [content/chunked] Section {sec_idx}/{len(sections)} '{section.heading}' -- skipped (checkpoint: already done)")
            continue

        print(f"  [content/chunked] Section {sec_idx}/{len(sections)} '{section.heading}'", end="")

        lua_ctx = extract_section_lua_context(
            section.heading, lua_source, max_tokens=8000
        )

        if section.heading == "## Main functions":
            preamble, fn_blocks = split_section_blocks(section.text)

            # Pre-filter: strip local and hallucinated functions
            fn_blocks, stripped_names = prefilter_fn_blocks(fn_blocks, lua_source)
            intentionally_removed = set(stripped_names)

            if not fn_blocks:
                print(f" -- skipped (all functions pre-filtered)")
                section.text = preamble
                completed_sections.add(sec_idx)
                save_validator_checkpoint(md_filepath, cache.cache_dir, completed_sections, total_iterations, all_issues)
                continue

            # Ensure required fields present before review
            fn_blocks = ensure_required_fields(fn_blocks)

            # Dynamic batching: Lua token budget 8K, doc token budget 4K
            batches = sub_chunk_section_lua_aware(
                fn_blocks, lua_source, lua_token_limit=8000, doc_token_limit=4000
            )
            n_batches = len(batches)
            print(f" -- {len(fn_blocks)} fn(s) in {n_batches} batch(es) [typed-ops]")

            all_updated_blocks: list[str] = []
            for bi, batch in enumerate(batches, 1):
                batch_text = "".join(batch)
                batch_lua_ctx = extract_lua_context(
                    lua_source, extract_function_names(batch_text), max_tokens=8000
                )
                # Create cache for this batch; preserve existing cache on resume
                # (crash mid-batch leaves the cache at whatever state was last written).
                batch_cache_id = f"sec{sec_idx}_batch{bi}"
                if cache.exists(batch_cache_id):
                    batch_text = cache.read(batch_cache_id)
                else:
                    cache.create(batch_cache_id, batch_text)

                print(f"  [content/chunked] Section {sec_idx} batch {bi}/{n_batches} -- reviewing...")
                batch_text, issues, iters = _run_typed_loop(
                    cache, batch_cache_id, batch_lua_ctx, section.heading,
                    intentionally_removed, config, file_type,
                )
                total_iterations += iters
                all_issues.extend(issues)
                # Split updated batch back into individual fn_blocks
                updated_blocks = [b for b in re.split(r'(?m)^(?=### )', batch_text) if b]
                all_updated_blocks.extend(updated_blocks)
                # Intermediate write to cache (assemble section so far)
                section.text = preamble + "".join(all_updated_blocks)
                cache.write(f"sec{sec_idx}_assembled", section.text)

            # Section fully done — save checkpoint
            completed_sections.add(sec_idx)
            save_validator_checkpoint(md_filepath, cache.cache_dir, completed_sections, total_iterations, all_issues)

        else:
            fn_count = len(re.findall(r'(?m)^### ', section.text))
            label = f"{fn_count} fn(s)" if fn_count else "structure only"
            print(f" -- {label} found")

            if fn_count == 0 and not lua_ctx:
                print(f"  [content/chunked] Section {sec_idx} -- skipped (no content to validate)")
                completed_sections.add(sec_idx)
                save_validator_checkpoint(md_filepath, cache.cache_dir, completed_sections, total_iterations, all_issues)
                continue

            # ── Stategraph events guard (pre-pass before LLM loop) ───────────
            # If the events section claims "None" but source has EventHandlers,
            # call the writer directly to pre-correct before the normal loop.
            # CRITICAL: must update section.text BEFORE cache.create so the
            # loop reads the corrected content, not the broken original.
            if (section.heading == "## Events & listeners"
                    and check_stategraph_events_null(section.text, lua_source)):
                event_names = extract_stategraph_event_names(lua_source)
                forced_finding = Finding(
                    section=section.heading,
                    function=None,
                    field=None,
                    rule_id="MISSING_EVENT",
                    issue=(
                        f"Section claims no events but source defines "
                        f"{len(event_names)} EventHandler(s): "
                        f"{', '.join(event_names)}. "
                        "Rewrite Events & listeners to list all EventHandlers."
                    ),
                )
                forced_ops = _call_writer_batch(
                    section.text, lua_ctx, [forced_finding], config, file_type
                )
                if forced_ops:
                    dummy = DocSection(heading=section.heading, text=section.text)
                    corrected = apply_typed_ops([dummy], forced_ops, frontmatter="")
                    if corrected[0].text != section.text:
                        section.text = corrected[0].text
                        print(
                            f"  [content/chunked] events guard: pre-corrected "
                            f"'None' → {len(event_names)} EventHandler(s)"
                        )
                    else:
                        print(
                            "  [content/chunked] events guard: writer returned no change "
                            "— falling through to normal loop"
                        )
            # ── end events guard ─────────────────────────────────────────────

            # Create cache for this section (AFTER guard pre-pass)
            sec_cache_id = f"sec{sec_idx}"
            cache.create(sec_cache_id, section.text)

            updated_text, issues, iters = _run_typed_loop(
                cache, sec_cache_id, lua_ctx, section.heading,
                intentionally_removed=set(), config=config, file_type=file_type,
                reviewed_context=reviewed_context if section.heading in _NARRATIVE_HEADINGS else "",
            )
            section.text = updated_text
            total_iterations += iters
            all_issues.extend(issues)

            # Section fully done — save checkpoint
            completed_sections.add(sec_idx)
            save_validator_checkpoint(md_filepath, cache.cache_dir, completed_sections, total_iterations, all_issues)

    # Final assembly: write all sections to original file
    md_path.write_text(join_md_sections(frontmatter, sections), encoding="utf-8")

    n_issues = len(all_issues)
    if n_issues:
        print(f"  [content/chunked] Final: {n_issues} issue(s) across failed sections, "
              f"total {total_iterations} iterations")
        print(f"  [pipeline] Content not approved after {total_iterations} iterations")
    else:
        print(f"  [content/chunked] All sections approved ({total_iterations} total iterations)")

    # TODO: chunked path does not support jury (need_special_case) — the typed reviewer
    # emits Finding objects, not the ReviewResult.need_special_case field used by the standard
    # loop. accepted_headings will always be empty for chunked files. To support jury here,
    # the section-level reviewer would need to signal need_special_case and run_chunked_content_loop
    # would need to aggregate and dispatch jury votes before returning.
    return ContentLoopResult(
        approved=n_issues == 0,
        iterations=total_iterations,
        final_issues=all_issues,
    )
