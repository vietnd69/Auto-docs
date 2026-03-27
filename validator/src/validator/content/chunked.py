"""Section-by-section content validation for large Lua files (≥32K tokens)."""

import json
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


from llm.tokens import count_tokens as _count_tokens_early  # noqa: E402 — needed before main imports


def _compact_messages(messages: list[dict], max_turns: int, token_budget: int) -> list[dict]:
    """Compact conversation history when it exceeds token budget or turn limit.

    Primary trigger: token count of non-system messages > token_budget.
    Fallback trigger: turn count > max_turns (used when tiktoken unavailable).
    When compacting, keeps system message + last 2 non-system messages.
    """
    if not messages:
        return messages
    system_msgs = [m for m in messages if m["role"] == "system"]
    non_system = [m for m in messages if m["role"] != "system"]
    if len(non_system) <= 2:
        return messages
    # Primary: token-based compaction
    total = _count_tokens_early("\n".join(m["content"] for m in non_system))
    if total != -1:
        if total <= token_budget and len(non_system) <= max_turns:
            return messages  # under both limits
    else:
        # tiktoken unavailable — fall back to turn count only
        if len(non_system) <= max_turns:
            return messages
    return system_msgs + non_system[-2:]


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
from llm.settings import (
    BAD_RESPONSE_RETRIES, BATCH_TOKEN_LIMIT, DEBUG_PROMPTS,
    SECTION_LUA_CONTEXT_TOKENS, SECTION_TOKEN_THRESHOLD,
    VALIDATOR_CALL_SLEEP,
    REVIEWER_TEMPERATURE, WRITER_TEMPERATURE, WRITER_THINK,
    MAX_CONVERSATION_TURNS, CONVERSATION_TOKEN_BUDGET, OSCILLATION_THRESHOLD,
)
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
from validator.content.reviewer import ReviewResult, parse_review_response, parse_review_json
from validator.content.schemas import REVIEW_SCHEMA, PATCHES_SCHEMA
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
from validator.content.writer import Patch, apply_patches, parse_writer_response, parse_writer_json


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
    *,
    messages: list[dict] | None = None,
) -> tuple[ReviewResult, list[dict]]:
    """Send one markdown section to the reviewer LLM.

    If `messages` is provided, appends a new user turn with updated section text
    (multi-turn continuation). Otherwise builds a fresh conversation.

    Returns (ReviewResult, updated_messages) so caller can accumulate turns.
    """
    system_prompt, user_content = build_section_reviewer_prompt(
        section_text, lua_context, section_heading, file_type
    )

    if messages is None:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    else:
        messages.append({"role": "user", "content": f"Section after fixes:\n{section_text}"})
        messages = _compact_messages(messages, MAX_CONVERSATION_TURNS, CONVERSATION_TOKEN_BUDGET)

    prompt_text = "\n".join(m["content"] for m in messages)
    print(f"  [content/chunked] Reviewer prompt: {count_tokens(prompt_text):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_reviewer", prompt_text)

    result = ReviewResult(approved=False, issues=["No response"], suggestions=[])
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(
            model=model, messages=messages,
            temperature=REVIEWER_TEMPERATURE,
            format=REVIEW_SCHEMA,
        )
        raw = response["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_reviewer_response", raw)
        try:
            data = json.loads(raw)
            result = parse_review_json(data)
        except (json.JSONDecodeError, TypeError):
            result = parse_review_response(raw)  # fallback
        if not _is_bad_review(raw, result):
            messages.append({"role": "assistant", "content": raw})
            return result, messages
        remaining = BAD_RESPONSE_RETRIES - attempt
        if remaining > 0:
            print(f"  [content/chunked] Bad reviewer response → retrying ({remaining} left)")
        else:
            print(f"  [content/chunked] Bad reviewer response after {BAD_RESPONSE_RETRIES + 1} attempts — giving up")
    return result, messages


def write_section_patches(
    section_text: str,
    lua_context: str,
    review: ReviewResult,
    model: str,
    section_heading: str = "",
    file_type: str = "component",
    *,
    messages: list[dict] | None = None,
) -> tuple[list[Patch], list[dict]]:
    """Ask the writer LLM to patch one section based on review feedback.

    Returns (patches, updated_messages) so caller can accumulate turns.
    """
    system_prompt, user_content = build_section_writer_prompt(
        section_text, lua_context, review.issues, review.suggestions,
        section_heading, file_type
    )

    if messages is None:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    else:
        feedback_lines = []
        for i, issue in enumerate(review.issues, 1):
            suggestion = review.suggestions[i - 1] if i - 1 < len(review.suggestions) else ""
            feedback_lines.append(f"{i}. Issue: {issue}")
            if suggestion:
                feedback_lines.append(f"   Suggestion: {suggestion}")
        feedback = "\n".join(feedback_lines)
        follow_up = f"Updated section:\n{section_text}\n\nNew feedback:\n{feedback}"
        messages.append({"role": "user", "content": follow_up})
        messages = _compact_messages(messages, MAX_CONVERSATION_TURNS, CONVERSATION_TOKEN_BUDGET)

    prompt_text = "\n".join(m["content"] for m in messages)
    print(f"  [content/chunked] Writer prompt: {count_tokens(prompt_text):,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer", prompt_text)

    writer_think = bool(WRITER_THINK)

    raw = ""
    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        response = ollama_chat(
            model=model, messages=messages,
            think=writer_think,
            temperature=WRITER_TEMPERATURE,
            format=PATCHES_SCHEMA,
        )
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
    try:
        data = json.loads(raw)
        patches = parse_writer_json(data)
    except (json.JSONDecodeError, TypeError):
        patches = parse_writer_response(raw)  # fallback
    if not patches:
        print("  [content/chunked] Writer returned no patches")
    else:
        print(f"  [content/chunked] {len(patches)} patch(es) generated")
        messages.append({"role": "assistant", "content": raw})
    return patches, messages


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
                reviewer_msgs: list[dict] | None = None
                writer_msgs: list[dict] | None = None
                prev_fingerprint: set[str] = set()

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
                    batch_last_review, reviewer_msgs = review_section(
                        batch_text, lua_ctx, config.reviewer_model,
                        section.heading, file_type,
                        messages=reviewer_msgs,
                    )
                    _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)
                    if batch_last_review.approved:
                        batch_approved = True
                        print(
                            f"  [content/chunked] Section {idx} batch {batch_idx} — "
                            f"approved at iteration {i + 1}"
                        )
                        break

                    # Convergence guard
                    current_fp = _fingerprint_issues(batch_last_review.issues)
                    if prev_fingerprint and current_fp:
                        overlap = len(current_fp & prev_fingerprint) / max(len(current_fp), 1)
                        if overlap >= OSCILLATION_THRESHOLD / 100:
                            print(
                                f"  [content/chunked] Section {idx} batch {batch_idx} — "
                                f"oscillation detected ({overlap:.0%} overlap), stopping"
                            )
                            break
                    prev_fingerprint = current_fp

                    patches, writer_msgs = write_section_patches(
                        batch_text, lua_ctx, batch_last_review, config.writer_model,
                        section.heading, file_type,
                        messages=writer_msgs,
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
                    batch_last_review, _ = review_section(
                        batch_text, lua_ctx, config.reviewer_model,
                        section.heading, file_type,
                        messages=reviewer_msgs,
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
            reviewer_msgs: list[dict] | None = None
            writer_msgs: list[dict] | None = None
            prev_fingerprint: set[str] = set()

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
                last_review, reviewer_msgs = review_section(
                    section.text, lua_ctx, config.reviewer_model,
                    section.heading, file_type,
                    messages=reviewer_msgs,
                )
                _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)

                if last_review.approved:
                    section_approved = True
                    print(
                        f"  [content/chunked] Section {idx}/{len(sections)} — "
                        f"approved at iteration {i + 1}"
                    )
                    break

                # Convergence guard
                current_fp = _fingerprint_issues(last_review.issues)
                if prev_fingerprint and current_fp:
                    overlap = len(current_fp & prev_fingerprint) / max(len(current_fp), 1)
                    if overlap >= OSCILLATION_THRESHOLD / 100:
                        print(
                            f"  [content/chunked] Section {idx}/{len(sections)} — "
                            f"oscillation detected ({overlap:.0%} overlap), stopping"
                        )
                        break
                prev_fingerprint = current_fp

                patches, writer_msgs = write_section_patches(
                    section.text, lua_ctx, last_review, config.writer_model,
                    section.heading, file_type,
                    messages=writer_msgs,
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
                last_review, _ = review_section(
                    section.text, lua_ctx, config.reviewer_model,
                    section.heading, file_type,
                    messages=reviewer_msgs,
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
