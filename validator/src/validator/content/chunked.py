"""Section-by-section content validation for large Lua files (≥32K tokens)."""

import re
import time
from pathlib import Path
from typing import Callable

_DATA_CONFIG_DIRS = {"map", "languages", "util"}


def _sleep(stop_check: Callable[[], bool], seconds: int) -> None:
    """Sleep in 1-second increments, stopping early if stop is requested."""
    for _ in range(seconds):
        if stop_check():
            break
        time.sleep(1)


def _fingerprint_issues(issues: list[str]) -> set[str]:
    """Normalize and deduplicate issues for convergence comparison."""
    return {issue.strip().lower() for issue in issues if issue.strip()}


def _detect_file_type(lua_filepath: str) -> str:
    """Returns 'component' or 'data_config' based on path relative to dst-scripts/."""
    parts = Path(lua_filepath).parts
    try:
        dst_idx = next(i for i, p in enumerate(parts) if p == "dst-scripts")
        rel = parts[dst_idx + 1:]
    except StopIteration:
        rel = parts
    if len(rel) <= 1 or rel[0].lower() in _DATA_CONFIG_DIRS:
        return "data_config"
    return "component"

from llm.client import ollama_chat
from llm.paths import PROJECT_ROOT
from llm.settings import BAD_RESPONSE_RETRIES, BATCH_TOKEN_LIMIT, DEBUG_PROMPTS, SECTION_LUA_CONTEXT_TOKENS, SECTION_TOKEN_THRESHOLD, VALIDATOR_CALL_SLEEP
from llm.tokens import count_tokens

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _dump_prompt(label: str, text: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = _DEBUG_DIR / f"{label}_{ts}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"  [debug] Prompt dumped → {path}")
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


def _is_bad_review(raw: str, result: ReviewResult) -> bool:
    """True if reviewer returned empty or unparseable response."""
    if not raw.strip():
        return True
    return bool(result.issues and result.issues[0].startswith("Failed to parse"))


def review_section(
    section_text: str,
    lua_context: str,
    model: str,
    section_heading: str = "",
    file_type: str = "component",
) -> ReviewResult:
    """Send one markdown section to the reviewer LLM. Retries on bad/empty response."""
    system_prompt, user_content = build_section_reviewer_prompt(
        section_text, lua_context, section_heading, file_type
    )
    prompt_text = system_prompt + "\n" + user_content  # for token counting/debug
    print(f"  [content/chunked] Reviewer prompt: {count_tokens(prompt_text):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_reviewer", prompt_text)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    result = ReviewResult(approved=False, issues=["No response"], suggestions=[])
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages)
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_reviewer_response", raw)
        result = parse_review_response(raw)
        if not _is_bad_review(raw, result):
            return result
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/chunked] Bad reviewer response → retrying ({remaining} left)")
        else:
            print(f"  [content/chunked] Bad reviewer response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")
    return result


def write_section_patches(
    section_text: str,
    lua_context: str,
    review: ReviewResult,
    model: str,
    section_heading: str = "",
    file_type: str = "component",
) -> list[Patch]:
    """Ask the writer LLM to patch one section based on review feedback. Retries on empty response."""
    system_prompt, user_content = build_section_writer_prompt(
        section_text, lua_context, review.issues, review.suggestions,
        section_heading, file_type
    )
    prompt_text = system_prompt + "\n" + user_content
    print(f"  [content/chunked] Writer prompt: {count_tokens(prompt_text):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer", prompt_text)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    raw = ""
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(model=model, messages=messages)
        raw = response["message"]["content"]
        if raw.strip():
            break
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/chunked] Empty writer response → retrying ({remaining} left)")
        else:
            print(f"  [content/chunked] Empty writer response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")

    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer_response", raw)
    patches = parse_writer_response(raw)
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
    file_type = _detect_file_type(lua_filepath)
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
                    lua_source, extract_function_names(batch_text),
                    max_tokens=SECTION_LUA_CONTEXT_TOKENS,
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
                        batch_text, lua_ctx, config.reviewer_model,
                        section.heading, file_type
                    )
                    _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)
                    if batch_last_review.approved:
                        batch_approved = True
                        print(
                            f"  [content/chunked] Section {idx} batch {batch_idx} — "
                            f"approved at iteration {i + 1}"
                        )
                        break

                    patches = write_section_patches(
                        batch_text, lua_ctx, batch_last_review, config.writer_model,
                        section.heading, file_type
                    )
                    _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)
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
                        batch_text, lua_ctx, config.reviewer_model,
                        section.heading, file_type
                    )
                    _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)
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
            lua_ctx = extract_lua_context(
                lua_source, fn_names, max_tokens=SECTION_LUA_CONTEXT_TOKENS
            )
            fn_desc = f"{len(fn_names)} fn(s)" if fn_names else "0 fn(s) — structure only"
            print(
                f"  [content/chunked] Section {idx}/{len(sections)} "
                f"{section.heading!r} — {fn_desc} found"
            )

            if not fn_names:
                print(
                    f"  [content/chunked] Section {idx}/{len(sections)} — "
                    "skipped (no function entries to validate)"
                )
                continue

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
                last_review = review_section(
                    section.text, lua_ctx, config.reviewer_model,
                    section.heading, file_type
                )
                _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)

                if last_review.approved:
                    section_approved = True
                    print(
                        f"  [content/chunked] Section {idx}/{len(sections)} — "
                        f"approved at iteration {i + 1}"
                    )
                    break

                patches = write_section_patches(
                    section.text, lua_ctx, last_review, config.writer_model,
                    section.heading, file_type
                )
                _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)
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
                last_review = review_section(
                    section.text, lua_ctx, config.reviewer_model,
                    section.heading, file_type
                )
                _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)
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
