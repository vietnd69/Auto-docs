"""Orchestrates the content validation loop: review -> fix -> review -> approve."""

from dataclasses import dataclass
from pathlib import Path

from rag.docs import safe_read_lua
from validator.content.reviewer import review_document
from validator.content.writer import rewrite_document, apply_patches
from validator.utils import resolve_connected_content


@dataclass
class ContentLoopConfig:
    """Configuration for the content validation loop."""
    max_iterations: int = 3
    writer_model: str = "qwen3.5:cloud"
    reviewer_model: str = "qwen3.5:cloud"


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
        return ContentLoopResult(
            approved=False, iterations=0,
            final_issues=[f"Cannot read Lua source: {lua_filepath}"],
        )

    _, connected_content = resolve_connected_content(lua_filepath)

    for i in range(config.max_iterations):
        # LLM2 review
        review = review_document(
            md_content, lua_source, connected_content, config.reviewer_model,
        )

        if review.approved:
            return ContentLoopResult(approved=True, iterations=i + 1, final_issues=[])

        # LLM1 fix
        patches = rewrite_document(
            md_content, lua_source, connected_content, review, config.writer_model,
        )

        if not patches:
            # LLM1 returned no patches — can't fix
            return ContentLoopResult(
                approved=False, iterations=i + 1, final_issues=review.issues,
            )

        md_content, failed = apply_patches(md_content, patches)

        # Fallback warning if too many patches failed
        if patches and failed > len(patches) / 2:
            print(f"  [content] Warning: {failed}/{len(patches)} patches failed to apply")

        # Write updated content to disk
        Path(md_filepath).write_text(md_content, encoding="utf-8")

    # Max iterations reached — do final review to get current status
    final_review = review_document(
        md_content, lua_source, connected_content, config.reviewer_model,
    )
    return ContentLoopResult(
        approved=final_review.approved,
        iterations=config.max_iterations,
        final_issues=final_review.issues,
    )
