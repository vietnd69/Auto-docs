"""Orchestrates the content validation loop: review -> fix -> review -> approve.

Cache-based flow:
1. Read md content → create cache file
2. Reviewer reads from cache
3. If rejected → writer patches content in cache (original file untouched)
4. Loop until approved or max iterations
5. Final cache content written back to original file
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rag.docs import safe_read_lua
from validator.content.cache import CacheManager
from validator.content.jury import run_jury
from validator.content.reviewer import ReviewResult, review_document
from validator.content.writer import rewrite_document, apply_patches
from validator.utils import resolve_connected_content
from llm.settings import VALIDATOR_LOOP_MAX_ITERATIONS, MODEL_MAIN, MODEL_JURY, NORMAL_SLEEP


def _never_stop() -> bool:
    return False


def _extract_standard_heading(review: "ReviewResult") -> str:
    """Extract the standard heading being replaced from the review result.

    Primary source: review.special_case_standard_heading (explicit field).
    Fallback: parse special_case_reason for 'instead of the standard ## ...' pattern.
    """
    if review.special_case_standard_heading.strip():
        return review.special_case_standard_heading.strip()
    m = re.search(r'instead of the standard\s+(##\s+[^\.\n,]+)', review.special_case_reason)
    if m:
        return m.group(1).strip()
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
    jury_already_run = False        # Jury runs at most once per file to prevent repeated 5x LLM calls
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
        )

        # --- Step 1: Resolve need_special_case before checking content approval ---
        # Valid reviewer states:
        #   approved:true,  need_special_case:false, findings:[]   → fully approved
        #   approved:true,  need_special_case:true,  findings:[]   → content ok, section name disputed
        #   approved:false, need_special_case:false, findings:[..] → content issues only
        #   approved:false, need_special_case:true,  findings:[..] → content issues + section name disputed
        # INVALID: approved:false + findings:[] (enforced by reviewer prompt/skill)
        if review.need_special_case:
            if not jury_already_run:
                jury_already_run = True
                reason_preview = review.special_case_reason[:120]
                print(f"  [content] Reviewer requests special case: {reason_preview}")
                verdict = run_jury(
                    cached_content, lua_source, connected_content,
                    review.special_case_reason, config.jury_model,
                )
                if verdict.accepted:
                    std_heading = _extract_standard_heading(review)
                    if std_heading:
                        accepted_headings.add(std_heading)
                        print(f"  [content] Jury ACCEPTED — '{std_heading}' heading check bypassed")
                    else:
                        print(f"  [content] Jury ACCEPTED — (standard heading unknown, no heading bypass applied)")
                else:
                    # Jury rejected — inject synthetic finding so writer renames sections
                    print(f"  [content] Jury REJECTED — enforcing standard section names")
                    review = ReviewResult(
                        approved=False,
                        issues=["Jury rejected format exception. Rename non-standard sections to required headings: ## Properties, ## Main functions"],
                        suggestions=["Rename any non-standard section headings to match the required names exactly"],
                    )
            elif not accepted_headings:
                # Jury already ran and rejected — re-inject rename instruction
                print(f"  [content] Reviewer again requests special case but jury already rejected — enforcing standard names")
                review = ReviewResult(
                    approved=False,
                    issues=["Section heading does not match required names. Rename to: ## Properties, ## Main functions, etc."],
                    suggestions=["Rename any non-standard section headings to match the required names exactly"],
                )
            # else: accepted_headings non-empty → jury already accepted → fall through with original review

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
        patches = rewrite_document(
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

        # Fallback warning if too many patches failed
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
    )

    # Final review: resolve need_special_case same as loop (jury runs at most once total)
    if final_review.need_special_case:
        if not jury_already_run:
            reason_preview = final_review.special_case_reason[:120]
            print(f"  [content] Final review requests special case: {reason_preview}")
            verdict = run_jury(
                final_content, lua_source, connected_content,
                final_review.special_case_reason, config.jury_model,
            )
            if verdict.accepted:
                std_heading = _extract_standard_heading(final_review)
                if std_heading:
                    accepted_headings.add(std_heading)
                print(f"  [content] Jury ACCEPTED on final review")
            else:
                print(f"  [content] Jury REJECTED on final review — file remains unapproved")
        elif not accepted_headings:
            print(f"  [content] Final review requests special case but jury already rejected — ignoring")

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
