"""Orchestrates the content validation loop: review -> fix -> review -> approve.

Cache-based flow:
1. Read md content → create cache file
2. Reviewer reads from cache
3. If rejected → writer patches content in cache (original file untouched)
4. Loop until approved or max iterations
5. Final cache content written back to original file
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rag.docs import safe_read_lua
from validator.content.cache import CacheManager
from validator.content.jury import run_jury
from validator.content.reviewer import ReviewResult, review_document
from validator.content.writer import rewrite_document, correct_failed_patches, apply_patches
from validator.utils import resolve_connected_content
from llm.settings import VALIDATOR_LOOP_MAX_ITERATIONS, MODEL_MAIN, MODEL_JURY, NORMAL_SLEEP


def _never_stop() -> bool:
    return False


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
                            {"issue": iss, "suggestion": sug}
                            for iss, sug in zip(review.issues, review.suggestions or [])
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
                    previous_review = review
                    continue
            elif not jury_verdicts[std_heading]:
                # Same heading already rejected — go back to reviewer (jury_context_turns already contains verdict)
                print(f"  [content] Reviewer again requests special case for '{std_heading}' but jury already rejected — going back to reviewer")
                previous_review = review
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

        print(f"  [content] Iteration {i + 1}/{config.max_iterations} — writing patches...")
        # LLM1 fix — works on cached content
        patches, raw = rewrite_document(
            cached_content, lua_source, connected_content, review, config.writer_model,
        )

        if not patches:
            # LLM1 returned no patches — can't fix
            print(f"  [content] Writer returned no patches, stopping early")
            Path(md_filepath).write_text(cache.read(cache_id), encoding="utf-8")
            return ContentLoopResult(
                approved=False, iterations=i + 1, final_issues=review.issues,
                accepted_headings=accepted_headings,
            )

        updated_content, failed, _ = apply_patches(cached_content, patches)
        applied = len(patches) - failed
        print(f"  [content] Applied {applied}/{len(patches)} patches" +
              (f" ({failed} failed)" if failed else ""))

        # Multi-turn correction: when patches fail, tell writer which old_text didn't match
        if failed > 0:
            failed_patches, failure_reasons = _collect_failed_patches(cached_content, patches)
            if failed_patches:
                print(f"  [content] Sleeping {NORMAL_SLEEP}s before correction...")
                time.sleep(NORMAL_SLEEP)
                print(f"  [content] Requesting correction for {len(failed_patches)} failed patch(es)...")
                correction = correct_failed_patches(
                    updated_content, lua_source, connected_content,
                    review, failed_patches, failure_reasons, raw, config.writer_model,
                )
                if correction:
                    updated_content, corr_failed, _ = apply_patches(updated_content, correction)
                    corr_applied = len(correction) - corr_failed
                    print(f"  [content] Correction applied {corr_applied}/{len(correction)} patches")

        # Fallback warning if still majority failed after correction
        if patches and failed > len(patches) / 2:
            print(f"  [content] Warning: majority of patches failed — writer may have hallucinated old_text")

        previous_review = review
        # Write updated content to cache (NOT to original file)
        cache.write(cache_id, updated_content)

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
