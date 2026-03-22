"""Orchestrates the content validation loop: review -> fix -> review -> approve."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rag.docs import safe_read_lua
from validator.content.reviewer import review_document
from validator.content.writer import rewrite_document, apply_patches
from validator.utils import resolve_connected_content
from llm.settings import VALIDATOR_LOOP_MAX_ITERATIONS, MODEL_MAIN


def _never_stop() -> bool:
    return False


@dataclass
class ContentLoopConfig:
    """Configuration for the content validation loop."""
    max_iterations: int = VALIDATOR_LOOP_MAX_ITERATIONS
    writer_model: str = MODEL_MAIN
    reviewer_model: str = MODEL_MAIN
    stop_check: Callable[[], bool] = field(default=_never_stop, repr=False)


@dataclass
class ContentLoopResult:
    """Result of a content validation loop run."""
    approved: bool
    iterations: int
    final_issues: list[str]


def run_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
    """
    Run the content validation loop:
    1. LLM2 reviews doc against Lua source
    2. If approved -> done
    3. If not -> LLM1 patches doc based on feedback
    4. Repeat until approved or max_iterations reached
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

    for i in range(config.max_iterations):
        if config.stop_check():
            print(f"  [content] Stopped by Ctrl+C before iteration {i + 1}")
            return ContentLoopResult(
                approved=False, iterations=i, final_issues=["Interrupted by user"],
            )

        print(f"  [content] Iteration {i + 1}/{config.max_iterations} — reviewing...")
        # LLM2 review
        review = review_document(
            md_content, lua_source, connected_content, config.reviewer_model,
        )

        if review.approved:
            print(f"  [content] Approved at iteration {i + 1}")
            return ContentLoopResult(approved=True, iterations=i + 1, final_issues=[])

        print(f"  [content] Rejected — {len(review.issues)} issue(s): {', '.join(review.issues[:2])}" +
              (f" (+{len(review.issues) - 2} more)" if len(review.issues) > 2 else ""))

        if config.stop_check():
            print(f"  [content] Stopped by Ctrl+C after review")
            return ContentLoopResult(
                approved=False, iterations=i + 1, final_issues=review.issues,
            )

        print(f"  [content] Iteration {i + 1}/{config.max_iterations} — writing patches...")
        # LLM1 fix
        patches = rewrite_document(
            md_content, lua_source, connected_content, review, config.writer_model,
        )

        if not patches:
            # LLM1 returned no patches — can't fix
            print(f"  [content] Writer returned no patches, stopping early")
            return ContentLoopResult(
                approved=False, iterations=i + 1, final_issues=review.issues,
            )

        md_content, failed = apply_patches(md_content, patches)
        applied = len(patches) - failed
        print(f"  [content] Applied {applied}/{len(patches)} patches" +
              (f" ({failed} failed)" if failed else ""))

        # Fallback warning if too many patches failed
        if patches and failed > len(patches) / 2:
            print(f"  [content] Warning: majority of patches failed — writer may have hallucinated old_text")

        # Write updated content to disk
        Path(md_filepath).write_text(md_content, encoding="utf-8")

    # Max iterations reached — do final review to get current status
    print(f"  [content] Max iterations reached, running final review...")
    final_review = review_document(
        md_content, lua_source, connected_content, config.reviewer_model,
    )
    status = "approved" if final_review.approved else f"rejected ({len(final_review.issues)} issue(s))"
    print(f"  [content] Final review: {status}")
    return ContentLoopResult(
        approved=final_review.approved,
        iterations=config.max_iterations,
        final_issues=final_review.issues,
    )
