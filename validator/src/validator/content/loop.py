"""Orchestrates the content validation loop: review -> fix -> review -> approve.

Cache-based flow:
1. Read md content → create cache file
2. Reviewer reads from cache
3. If rejected → writer patches content in cache (original file untouched)
4. Loop until approved or max iterations
5. Final cache content written back to original file
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rag.docs import safe_read_lua
from validator.content.cache import CacheManager
from validator.content.jury import run_jury
from validator.content.reviewer import ReviewResult, review_document, reviewer_oscillation_correction
from validator.content.writer import rewrite_document, correct_failed_patches, correct_guard_blocked_patches, apply_patches
from validator.utils import resolve_connected_content
from llm.settings import VALIDATOR_LOOP_MAX_ITERATIONS, VALIDATOR_WRITER_INNER_ITERATIONS, MODEL_MAIN, MODEL_JURY, NORMAL_SLEEP


def _never_stop() -> bool:
    return False


def _extract_topic_keywords(issue: str) -> frozenset[str]:
    """Extract identifiable terms from an issue string for oscillation detection."""
    quoted = re.findall(r"['\"`]([^'\"`\n]+)['\"`]", issue)
    terms = {q.strip().lower() for q in quoted if 2 < len(q.strip()) < 60}
    headings = re.findall(r'##\s+[\w\s]+', issue.lower())
    terms.update(h.strip() for h in headings if len(h.strip()) > 3)
    return frozenset(terms)


def _find_oscillating_issues(
    current_review: ReviewResult,
    history: list[ReviewResult],
) -> list[tuple[str, str]]:
    """Detect oscillating issues across the FULL history (not just the last 2 steps).

    An issue oscillates when the current review re-raises a topic that was resolved
    at any prior point in history (present in history[i] but absent from history[i+1]).
    Returns list of (current_issue, contradicted_resolved_issue) pairs.
    """
    if len(history) < 2:
        return []
    # Collect all issues resolved at any prior step (full history, not just last 2)
    ever_resolved: set[str] = set()
    for i in range(len(history) - 1):
        next_issue_set = set(history[i + 1].issues)
        for issue in history[i].issues:
            if issue not in next_issue_set:
                ever_resolved.add(issue)
    if not ever_resolved:
        return []
    oscillating: list[tuple[str, str]] = []
    seen_curr: set[str] = set()
    for curr in current_review.issues:
        if curr in seen_curr:
            continue
        curr_kw = _extract_topic_keywords(curr)
        if not curr_kw:
            continue
        for resolved in ever_resolved:
            resolved_kw = _extract_topic_keywords(resolved)
            if curr_kw & resolved_kw:
                oscillating.append((curr, resolved))
                seen_curr.add(curr)
                break
    return oscillating


def _collect_all_resolved_issues(history: list[ReviewResult]) -> list[str]:
    """Collect all issues resolved at any point across the full review history.

    Used to inform the oscillation correction so the reviewer knows which topics
    have already been addressed and must not be re-raised.
    """
    resolved: set[str] = set()
    for i in range(len(history) - 1):
        next_issue_set = set(history[i + 1].issues)
        for issue in history[i].issues:
            if issue not in next_issue_set:
                resolved.add(issue)
    return list(resolved)


_STANDARD_HEADINGS = [
    "## Overview",
    "## Usage example",
    "## Dependencies & tags",
    "## Properties",
    "## Main functions",
    "## Events & listeners",
]



def _extract_standard_heading(review: "ReviewResult") -> str:
    """Extract the standard heading being replaced from the review result.

    Primary source: review.special_case_standard_heading (explicit field).
    Fallback: scan special_case_reason for any known standard heading name.
    """
    if review.special_case_standard_heading.strip():
        heading = review.special_case_standard_heading.strip()
        # Normalize: ensure "## " prefix
        if not heading.startswith("## "):
            heading = f"## {heading}"
        return heading
    # Fallback: find any standard heading mentioned in the reason text
    for heading in _STANDARD_HEADINGS:
        if heading in review.special_case_reason:
            return heading
    return ""


@dataclass
class ContentLoopConfig:
    """Configuration for the content validation loop."""
    max_iterations: int = VALIDATOR_LOOP_MAX_ITERATIONS
    writer_model: str = MODEL_MAIN
    reviewer_model: str = MODEL_MAIN
    jury_model: str = MODEL_JURY
    stop_check: Callable[[], bool] = field(default=_never_stop, repr=False)


@dataclass
class ContentLoopResult:
    """Result of a content validation loop run."""
    approved: bool
    iterations: int
    final_issues: list[str]
    accepted_headings: set[str] = field(default_factory=set)  # standard headings jury accepted as replaced


def _build_writer_prior_context(
    prev_issues: list[str],
    applied: int,
    failed: int,
    guard_blocked: int,
) -> str:
    """Compact user-turn summary of the previous writer iteration for multi-turn context.

    Avoids repeating the full doc/Lua source — just describes what was requested,
    what happened to the patches, and instructs the writer not to re-fix resolved issues.
    """
    issues_text = "\n".join(f"- {iss}" for iss in prev_issues) or "(none)"
    result_parts = [f"{applied} applied"]
    if failed:
        result_parts.append(f"{failed} not found/ambiguous")
    if guard_blocked:
        result_parts.append(f"{guard_blocked} guard-blocked")
    return (
        "[CONTEXT: PREVIOUS WRITER ATTEMPT]\n"
        f"In the previous iteration you were asked to fix:\n{issues_text}\n\n"
        f"Patch application results: {', '.join(result_parts)}.\n"
        "The document was updated with the applied patches. Your previous response is shown "
        "above (assistant turn). Below you will receive the updated document and remaining issues.\n"
        "Do NOT re-generate patches for issues already resolved — only fix what the new reviewer feedback flags."
    )


def _collect_failed_patches(
    content: str,
    patches: list,
) -> tuple[list, list[str]]:
    """Identify patches that failed to apply and describe why.

    Returns (failed_patches, failure_reasons) — parallel lists.
    Only includes patches where old_text was not found or was ambiguous.
    """
    failed: list = []
    reasons: list[str] = []
    for p in patches:
        count = content.count(p.old_text)
        if count == 0:
            failed.append(p)
            reasons.append("old_text not found in document")
        elif count > 1:
            failed.append(p)
            reasons.append(f"old_text appears {count} times (ambiguous — must be unique)")
    return failed, reasons


def run_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
    """
    Run the content validation loop using cache files:
    1. Create cache from md content
    2. LLM2 reviews cached content against Lua source
    3. If approved -> write cache to original file, done
    4. If not -> LLM1 patches cached content based on feedback
    5. Repeat until approved or max_iterations reached
    6. Write final cache content back to original file
    """
    md_content = Path(md_filepath).read_text(encoding="utf-8")
    lua_source = safe_read_lua(lua_filepath)
    if lua_source is None:
        print(f"  [content] Cannot read Lua source: {lua_filepath}")
        return ContentLoopResult(
            approved=False, iterations=0,
            final_issues=[f"Cannot read Lua source: {lua_filepath}"],
        )

    _, connected_content = resolve_connected_content(lua_filepath)
    print(f"  [content] Starting loop (max {config.max_iterations} iterations)")

    # Create cache from md content
    cache = CacheManager(md_filepath)
    cache_id = "full"
    cache.create(cache_id, md_content)
    print(f"  [content] Cache created: {cache.cache_dir}")

    previous_review = None
    jury_verdicts: dict[str, bool] = {}  # std_heading → accepted (True) or rejected (False)
    jury_context_turns: list[dict] = []  # assistant+user turn pairs injected into reviewer after jury rejects
    accepted_headings: set[str] = set()  # standard headings jury accepted as replaced by non-standard names
    review_history: list[ReviewResult] = []  # for oscillation detection
    writer_prior_turns: list[dict] = []  # [compact_user, assistant] from last writer call
    for i in range(config.max_iterations):
        if config.stop_check():
            print(f"  [content] Stopped by Ctrl+C before iteration {i + 1}")
            # Write current cache state to original file before exit
            Path(md_filepath).write_text(cache.read(cache_id), encoding="utf-8")
            return ContentLoopResult(
                approved=False, iterations=i, final_issues=["Interrupted by user"],
                accepted_headings=accepted_headings,
            )

        # Read from cache for review
        cached_content = cache.read(cache_id)

        print(f"  [content] Iteration {i + 1}/{config.max_iterations} — reviewing...")
        # LLM2 review
        review = review_document(
            cached_content, lua_source, connected_content, config.reviewer_model,
            previous_review=previous_review,
            prior_turns=jury_context_turns or None,
        )

        # --- Step 1: Resolve need_special_case before checking content approval ---
        # Valid reviewer states:
        #   approved:true,  need_special_case:false, findings:[]   → fully approved
        #   approved:true,  need_special_case:true,  findings:[]   → content ok, section name disputed
        #   approved:false, need_special_case:false, findings:[..] → content issues only
        #   approved:false, need_special_case:true,  findings:[..] → content issues + section name disputed
        # INVALID: approved:false + findings:[] (enforced by reviewer prompt/skill)
        if review.need_special_case:
            std_heading = _extract_standard_heading(review)
            if not std_heading:
                # Can't determine which heading — skip jury (would waste 5 LLM calls with no actionable result)
                print(f"  [content] Reviewer requests special case but standard heading unknown — skipping jury")
            elif std_heading not in jury_verdicts:
                # New heading — run jury vote
                reason_preview = review.special_case_reason[:120]
                print(f"  [content] Reviewer requests special case for '{std_heading}': {reason_preview}")
                verdict = run_jury(
                    cached_content, lua_source, connected_content,
                    review.special_case_reason, config.jury_model,
                )
                jury_verdicts[std_heading] = verdict.accepted
                if verdict.accepted:
                    accepted_headings.add(std_heading)
                    print(f"  [content] Jury ACCEPTED — '{std_heading}' heading check bypassed")
                else:
                    # Jury rejected — go back to reviewer with verdict injected via prior_turns
                    print(f"  [content] Jury REJECTED — going back to reviewer in next iteration")
                    prior_assistant = json.dumps({
                        "approved": review.approved,
                        "need_special_case": True,
                        "special_case_standard_heading": std_heading,
                        "special_case_reason": review.special_case_reason,
                        "findings": [
                            {
                                "issue": iss,
                                "suggestion": (
                                    review.suggestions[idx]
                                    if idx < len(review.suggestions or [])
                                    else ""
                                ),
                            }
                            for idx, iss in enumerate(review.issues)
                        ],
                    }, ensure_ascii=False)
                    jury_context_turns.extend([
                        {"role": "assistant", "content": prior_assistant},
                        {
                            "role": "user",
                            "content": (
                                f"[JURY VERDICT — BINDING] Your special case request for '{std_heading}' "
                                f"was reviewed by 5 independent judges and REJECTED (majority voted NO). "
                                f"You MUST NOT set need_special_case=true for '{std_heading}' in any future response. "
                                f"The document must use the standard heading name."
                            ),
                        },
                    ])
                    # Don't set previous_review here — writer never ran, nothing was patched.
                    # jury_context_turns already carries the rejection context for the reviewer.
                    continue
            elif not jury_verdicts[std_heading]:
                # Same heading already rejected — go back to reviewer (jury_context_turns already contains verdict)
                print(f"  [content] Reviewer again requests special case for '{std_heading}' but jury already rejected — going back to reviewer")
                # Don't set previous_review here — writer never ran, nothing was patched.
                continue
            else:
                # Jury already accepted this heading — log it and fall through
                reason_preview = review.special_case_reason[:120]
                print(f"  [content] Reviewer again requests special case for '{std_heading}' (different reason) — jury already accepted, bypassing heading check")
                print(f"  [content] New reason: {reason_preview}")

        # --- Step 2: Check content approval (after special case resolved) ---
        if review.approved:
            print(f"  [content] Approved at iteration {i + 1}")
            Path(md_filepath).write_text(cache.read(cache_id), encoding="utf-8")
            return ContentLoopResult(
                approved=True, iterations=i + 1, final_issues=[],
                accepted_headings=accepted_headings,
            )

        # Oscillation correction: if reviewer re-raises contradictory issues,
        # send its own response back as assistant turn + guard feedback as user turn
        # so it can self-correct before the writer runs.
        if review.raw_response:
            oscillating = _find_oscillating_issues(review, review_history)
            if oscillating:
                print(f"  [content] Oscillation detected in {len(oscillating)} issue(s) — reviewer self-correction...")
                corrected = reviewer_oscillation_correction(
                    cached_content, lua_source, connected_content,
                    review, oscillating, config.reviewer_model,
                    resolved_history=_collect_all_resolved_issues(review_history),
                )
                if corrected.approved:
                    print(f"  [content] Self-correction approved at iteration {i + 1}")
                    Path(md_filepath).write_text(cache.read(cache_id), encoding="utf-8")
                    return ContentLoopResult(
                        approved=True, iterations=i + 1, final_issues=[],
                        accepted_headings=accepted_headings,
                    )
                if len(corrected.issues) < len(review.issues):
                    print(f"  [content] Self-correction reduced: {len(review.issues)} → {len(corrected.issues)} issue(s)")
                    review = corrected
                else:
                    print(f"  [content] Self-correction did not reduce issues — proceeding with original")

        print(f"  [content] Rejected — {len(review.issues)} issue(s): {', '.join(review.issues[:2])}" +
              (f" (+{len(review.issues) - 2} more)" if len(review.issues) > 2 else ""))

        if config.stop_check():
            print(f"  [content] Stopped by Ctrl+C after review")
            Path(md_filepath).write_text(cache.read(cache_id), encoding="utf-8")
            return ContentLoopResult(
                approved=False, iterations=i + 1, final_issues=review.issues,
                accepted_headings=accepted_headings,
            )

        print(f"  [content] Sleeping {NORMAL_SLEEP}s before writing patches...")
        time.sleep(NORMAL_SLEEP)

        # Inner writer loop: retry until all patches apply, no progress, or max passes
        current_content = cached_content
        inner_prior_turns: list[dict] = writer_prior_turns[:]
        for w_iter in range(VALIDATOR_WRITER_INNER_ITERATIONS):
            inner_suffix = f" (pass {w_iter + 1}/{VALIDATOR_WRITER_INNER_ITERATIONS})" if VALIDATOR_WRITER_INNER_ITERATIONS > 1 else ""
            print(f"  [content] Iteration {i + 1}/{config.max_iterations} — writing patches{inner_suffix}...")
            patches, raw = rewrite_document(
                current_content, lua_source, connected_content, review, config.writer_model,
                prior_turns=inner_prior_turns or None,
            )

            if not patches:
                if w_iter == 0:
                    print(f"  [content] Writer returned no patches, stopping early")
                    Path(md_filepath).write_text(cache.read(cache_id), encoding="utf-8")
                    return ContentLoopResult(
                        approved=False, iterations=i + 1, final_issues=review.issues,
                        accepted_headings=accepted_headings,
                    )
                print(f"  [content] Writer returned no patches — stopping writer loop")
                break

            updated_content, failed, _, guard_blocked_patches = apply_patches(current_content, patches)
            applied = len(patches) - failed
            parts = [f"applied {applied}/{len(patches)}"]
            if failed:
                parts.append(f"{failed} failed")
            print(f"  [content] Patches: {', '.join(parts)}")

            remaining_failed = failed

            if failed > 0:
                failed_patches, failure_reasons = _collect_failed_patches(current_content, patches)
                guard_blocked_count = len(guard_blocked_patches)
                breakdown = []
                if guard_blocked_count:
                    breakdown.append(f"{guard_blocked_count} guard-blocked")
                if failed_patches:
                    breakdown.append(f"{len(failed_patches)} not-found/ambiguous")
                if breakdown:
                    print(f"  [content]   Failure breakdown: {', '.join(breakdown)}")
                if failed_patches:
                    print(f"  [content] Sleeping {NORMAL_SLEEP}s before correction...")
                    time.sleep(NORMAL_SLEEP)
                    print(f"  [content] Not-found correction: requesting for {len(failed_patches)} patch(es)...")
                    correction = correct_failed_patches(
                        updated_content,
                        failed_patches,
                        failure_reasons,
                        config.writer_model,
                        review_issues=review.issues,
                        review_suggestions=review.suggestions,
                        previous_writer_raw=raw,
                        previous_patches=patches,
                    )
                    if correction:
                        updated_content, corr_failed, _, corr_guard_blocked = apply_patches(updated_content, correction)
                        if corr_guard_blocked:
                            guard_blocked_patches.extend(corr_guard_blocked)
                        corr_applied = len(correction) - corr_failed
                        remaining_failed = max(0, remaining_failed - corr_applied)
                        remaining_failed = max(remaining_failed, corr_failed)
                        print(f"  [content] Not-found correction: applied {corr_applied}/{len(correction)} patches")

            if guard_blocked_patches:
                guard_count = len(guard_blocked_patches)
                print(f"  [content] Sleeping {NORMAL_SLEEP}s before guard correction...")
                time.sleep(NORMAL_SLEEP)
                print(f"  [content] Guard correction: requesting for {guard_count} blocked patch(es)...")
                guard_correction = correct_guard_blocked_patches(
                    current_content, lua_source, connected_content,
                    review, guard_blocked_patches, raw, updated_content, config.writer_model,
                )
                if guard_correction:
                    updated_content, gc_failed, _, _ = apply_patches(updated_content, guard_correction)
                    gc_applied = len(guard_correction) - gc_failed
                    remaining_failed = max(0, remaining_failed - gc_applied)
                    remaining_failed = max(remaining_failed, gc_failed)
                    print(f"  [content] Guard correction: applied {gc_applied}/{len(guard_correction)} patches")

            if patches and remaining_failed > len(patches) / 2:
                print(f"  [content] Warning: majority of patches failed — writer may have hallucinated old_text")

            iter_applied = len(patches) - remaining_failed
            inner_prior_turns = [
                {"role": "user", "content": _build_writer_prior_context(
                    prev_issues=review.issues,
                    applied=iter_applied,
                    failed=remaining_failed,
                    guard_blocked=len(guard_blocked_patches),
                )},
                {"role": "assistant", "content": raw},
            ]
            current_content = updated_content

            if remaining_failed == 0:
                if w_iter > 0:
                    print(f"  [content] All patches applied after {w_iter + 1} writer pass(es)")
                break

            if iter_applied == 0:
                print(f"  [content] No progress in writer pass {w_iter + 1} — stopping")
                break

            if w_iter < VALIDATOR_WRITER_INNER_ITERATIONS - 1:
                print(f"  [content] Sleeping {NORMAL_SLEEP}s before next writer pass...")
                time.sleep(NORMAL_SLEEP)

        writer_prior_turns = inner_prior_turns
        previous_review = review
        review_history.append(review)
        # Write updated content to cache (NOT to original file)
        cache.write(cache_id, current_content)

        if current_content == cached_content:
            print(f"  [content] Writer unable to make progress — stopping loop early")
            break

        print(f"  [content] Sleeping {NORMAL_SLEEP}s before next iteration...")
        time.sleep(NORMAL_SLEEP)

    # Max iterations reached — do final review to get current status
    print(f"  [content] Max iterations reached, running final review...")
    final_content = cache.read(cache_id)
    final_review = review_document(
        final_content, lua_source, connected_content, config.reviewer_model,
        previous_review=previous_review,
        prior_turns=jury_context_turns or None,
    )

    # Final review: resolve need_special_case same as loop (jury runs at most once per heading)
    if final_review.need_special_case:
        std_heading = _extract_standard_heading(final_review)
        if not std_heading:
            print(f"  [content] Final review requests special case but standard heading unknown — skipping jury")
        elif std_heading not in jury_verdicts:
            reason_preview = final_review.special_case_reason[:120]
            print(f"  [content] Final review requests special case for '{std_heading}': {reason_preview}")
            verdict = run_jury(
                final_content, lua_source, connected_content,
                final_review.special_case_reason, config.jury_model,
            )
            jury_verdicts[std_heading] = verdict.accepted
            if verdict.accepted:
                accepted_headings.add(std_heading)
                print(f"  [content] Jury ACCEPTED on final review — '{std_heading}' heading check bypassed")
            else:
                print(f"  [content] Jury REJECTED on final review — file remains unapproved")
                final_review = ReviewResult(
                    approved=False,
                    issues=[f"Jury rejected format exception for '{std_heading}'. Rename non-standard sections to required headings."],
                    suggestions=["Rename any non-standard section headings to match the required names exactly"],
                )
        elif not jury_verdicts[std_heading]:
            print(f"  [content] Final review requests special case for '{std_heading}' but jury already rejected")
            final_review = ReviewResult(
                approved=False,
                issues=[f"Section heading does not match required names. Rename '{std_heading}' to the standard heading."],
                suggestions=["Rename any non-standard section headings to match the required names exactly"],
            )
        else:
            # Jury already accepted this heading in an earlier iteration — bypass the check
            accepted_headings.add(std_heading)
            print(f"  [content] Final review requests special case for '{std_heading}' — jury already accepted, bypassing")

    status = "approved" if final_review.approved else f"rejected ({len(final_review.issues)} issue(s))"
    print(f"  [content] Final review: {status}")

    # Write final cache content to original file
    Path(md_filepath).write_text(cache.read(cache_id), encoding="utf-8")

    return ContentLoopResult(
        approved=final_review.approved,
        iterations=config.max_iterations,
        final_issues=final_review.issues,
        accepted_headings=accepted_headings,
    )
