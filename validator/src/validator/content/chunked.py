"""Section-by-section content validation for large Lua files (≥32K tokens)."""

import re
from pathlib import Path

from llm.client import ollama_chat
from llm.settings import BATCH_TOKEN_LIMIT, SECTION_TOKEN_THRESHOLD
from llm.tokens import count_tokens
from rag.docs import safe_read_lua
from validator.content.loop import ContentLoopConfig, ContentLoopResult
from validator.content.prompts import (
    build_section_reviewer_prompt,
    build_section_writer_prompt,
)
from validator.content.reviewer import ReviewResult, parse_review_response
from validator.content.sections import (
    DocSection,
    extract_fn_headings,
    extract_function_names,
    extract_lua_context,
    join_md_sections,
    restore_lost_blocks,
    split_md_sections,
    split_section_blocks,
    sub_chunk_section,
)
from validator.content.writer import Patch, apply_patches, parse_writer_response


def review_section(section_text: str, lua_context: str, model: str) -> ReviewResult:
    """Send one markdown section to the reviewer LLM."""
    prompt = build_section_reviewer_prompt(section_text, lua_context)
    print(f"  [content/chunked] Reviewer prompt: {count_tokens(prompt):,} tokens")
    response = ollama_chat(model=model, messages=[{"role": "user", "content": prompt}])
    return parse_review_response(response["message"]["content"])


def write_section_patches(
    section_text: str,
    lua_context: str,
    review: ReviewResult,
    model: str,
) -> list[Patch]:
    """Ask the writer LLM to patch one section based on review feedback."""
    prompt = build_section_writer_prompt(
        section_text, lua_context, review.issues, review.suggestions
    )
    print(f"  [content/chunked] Writer prompt: {count_tokens(prompt):,} tokens")
    response = ollama_chat(model=model, messages=[{"role": "user", "content": prompt}])
    patches = parse_writer_response(response["message"]["content"])
    if not patches:
        print("  [content/chunked] Writer returned no patches")
    else:
        print(f"  [content/chunked] {len(patches)} patch(es) generated")
    return patches


def run_chunked_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
    """Full content validation for large-Lua files, processed section-by-section.

    Same signature and return contract as run_content_loop.
    approved=True means every section passed its final review.
    """
    md_content = Path(md_filepath).read_text(encoding="utf-8")
    lua_source = safe_read_lua(lua_filepath)
    if lua_source is None:
        return ContentLoopResult(
            approved=False,
            iterations=0,
            final_issues=[f"Cannot read Lua source: {lua_filepath}"],
        )

    frontmatter, sections = split_md_sections(md_content)
    if not sections:
        return ContentLoopResult(approved=True, iterations=0, final_issues=[])

    print(f"  [content/chunked] {len(sections)} section(s) found")
    total_iterations = 0
    all_failed_issues: list[str] = []

    for idx, section in enumerate(sections, 1):
        tokens = count_tokens(section.text)
        has_subheadings = bool(re.search(r'(?m)^### ', section.text))

        if tokens > SECTION_TOKEN_THRESHOLD and has_subheadings:
            # ── Large section path: sub-chunked by ### boundaries ────────
            preamble, fn_blocks = split_section_blocks(section.text)
            snapshot = extract_fn_headings(fn_blocks)
            backup = list(fn_blocks)
            batches = sub_chunk_section(fn_blocks, BATCH_TOKEN_LIMIT)

            fn_desc = f"{len(fn_blocks)} fn(s) in {len(batches)} batch(es)"
            print(
                f"  [content/chunked] Section {idx}/{len(sections)} "
                f"{section.heading!r} — {fn_desc} [sub-chunked]"
            )

            offset = 0
            for batch_idx, batch in enumerate(batches, 1):
                if config.stop_check():
                    return ContentLoopResult(
                        approved=False,
                        iterations=total_iterations,
                        final_issues=["Interrupted by user"],
                    )

                batch_size = len(batch)
                batch_text = "".join(batch)
                lua_ctx = extract_lua_context(
                    lua_source, extract_function_names(batch_text)
                )

                print(
                    f"  [content/chunked] Section {idx} batch {batch_idx}/{len(batches)}"
                    f" — {batch_size} fn(s), {count_tokens(batch_text):,} tokens"
                )

                batch_approved = False
                batch_last_review: ReviewResult | None = None

                for i in range(config.max_iterations):
                    if config.stop_check():
                        return ContentLoopResult(
                            approved=False,
                            iterations=total_iterations,
                            final_issues=["Interrupted by user"],
                        )

                    total_iterations += 1
                    print(
                        f"  [content/chunked] Section {idx} batch {batch_idx} — "
                        f"reviewing... (iter {i + 1}/{config.max_iterations})"
                    )
                    batch_last_review = review_section(
                        batch_text, lua_ctx, config.reviewer_model
                    )
                    if batch_last_review.approved:
                        batch_approved = True
                        print(
                            f"  [content/chunked] Section {idx} batch {batch_idx} — "
                            f"approved at iteration {i + 1}"
                        )
                        break

                    patches = write_section_patches(
                        batch_text, lua_ctx, batch_last_review, config.writer_model
                    )
                    if not patches:
                        print(
                            f"  [content/chunked] Section {idx} batch {batch_idx} — "
                            "writer gave up, batch stays failed"
                        )
                        break
                    batch_text, failed = apply_patches(batch_text, patches)
                    applied = len(patches) - failed
                    print(
                        f"  [content/chunked] Section {idx} batch {batch_idx} — "
                        f"patches: {applied} applied, {failed} failed"
                    )
                else:
                    # max_iterations exhausted — final review on post-patch text
                    total_iterations += 1
                    batch_last_review = review_section(
                        batch_text, lua_ctx, config.reviewer_model
                    )
                    batch_approved = batch_last_review.approved

                if not batch_approved and batch_last_review is not None:
                    all_failed_issues.extend(batch_last_review.issues)

                # Write patched blocks back into fn_blocks
                updated = [b for b in re.split(r'(?m)^(?=### )', batch_text) if b]
                if len(updated) != batch_size:
                    print(
                        f"  [content/chunked] WARNING: Section {idx} batch {batch_idx} "
                        f"block count changed {batch_size} → {len(updated)}"
                    )
                fn_blocks[offset : offset + batch_size] = updated
                offset += len(updated)

            # Restore any function entries lost during patching
            restored = restore_lost_blocks(fn_blocks, snapshot, backup)
            if restored:
                print(
                    f"  [content/chunked] Restored {restored} lost fn entries "
                    f"in section {idx}"
                )

            # Reassemble once, after completeness restore
            section.text = preamble + "".join(fn_blocks)
            Path(md_filepath).write_text(
                join_md_sections(frontmatter, sections), encoding="utf-8"
            )

        else:
            # ── Small section path: existing logic, unchanged ────────────
            if tokens > SECTION_TOKEN_THRESHOLD:
                print(
                    f"  [content/chunked] WARNING: Section {idx} {section.heading!r} "
                    f"is {tokens:,} tokens but has no ### sub-headings — "
                    "cannot sub-chunk, proceeding as single unit"
                )
            fn_names = extract_function_names(section.text)
            lua_ctx = extract_lua_context(lua_source, fn_names)
            fn_desc = f"{len(fn_names)} fn(s)" if fn_names else "0 fn(s) — structure only"
            print(
                f"  [content/chunked] Section {idx}/{len(sections)} "
                f"{section.heading!r} — {fn_desc} found"
            )

            section_approved = False
            last_review: ReviewResult | None = None

            for i in range(config.max_iterations):
                if config.stop_check():
                    return ContentLoopResult(
                        approved=False,
                        iterations=total_iterations,
                        final_issues=["Interrupted by user"],
                    )

                total_iterations += 1
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    f"reviewing... (iter {i + 1}/{config.max_iterations})"
                )
                last_review = review_section(section.text, lua_ctx, config.reviewer_model)

                if last_review.approved:
                    section_approved = True
                    print(
                        f"  [content/chunked] Section {idx}/{len(sections)} — "
                        f"approved at iteration {i + 1}"
                    )
                    break

                patches = write_section_patches(
                    section.text, lua_ctx, last_review, config.writer_model
                )
                if not patches:
                    print(
                        f"  [content/chunked] Section {idx}/{len(sections)} — "
                        "writer gave up, section stays failed"
                    )
                    break

                section.text, failed = apply_patches(section.text, patches)
                applied = len(patches) - failed
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    f"patches: {applied} applied, {failed} failed"
                )
                Path(md_filepath).write_text(
                    join_md_sections(frontmatter, sections), encoding="utf-8"
                )
            else:
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    "max iterations reached, running final review"
                )
                total_iterations += 1
                last_review = review_section(section.text, lua_ctx, config.reviewer_model)
                section_approved = last_review.approved

            if not section_approved and last_review is not None:
                all_failed_issues.extend(last_review.issues)

    print(
        f"  [content/chunked] Final: "
        f"{'all approved' if not all_failed_issues else f'{len(all_failed_issues)} issue(s) across failed sections'}, "
        f"total {total_iterations} iterations"
    )
    return ContentLoopResult(
        approved=len(all_failed_issues) == 0,
        iterations=total_iterations,
        final_issues=all_failed_issues,
    )
