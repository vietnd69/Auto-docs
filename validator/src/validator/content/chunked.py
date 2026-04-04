"""Section-by-section content validation for large Lua files (>=32K tokens).

Typed-ops pipeline: deterministic pre-filter -> typed LLM review -> typed ops apply.
No guards. No free-text patches. Convergence = findings == [].
"""

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
    build_typed_writer_prompt,
    _RULE_IDS_BY_SECTION,
)
from validator.content.reviewer import Finding, parse_findings_json
from validator.content.schemas import FINDINGS_SCHEMA, TYPED_OP_SCHEMA
from validator.content.sections import (
    DocSection,
    apply_typed_ops,
    classify_lua_functions,
    ensure_required_fields,
    extract_function_names,
    extract_lua_context,
    extract_section_lua_context,
    join_md_sections,
    normalize_fn_headings,
    prefilter_fn_blocks,
    split_md_sections,
    split_section_blocks,
    sub_chunk_section_lua_aware,
)
from validator.content.writer import TypedOp, parse_typed_op_json

_DATA_CONFIG_DIRS = {"map", "languages", "util"}
_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


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


def _try_parse_json(raw: str) -> dict | None:
    """Strip fences and think-tags then parse JSON. Returns None on failure."""
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
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
) -> list[Finding]:
    """Call the reviewer LLM and return structured findings."""
    rule_ids = _RULE_IDS_BY_SECTION.get(section_heading)
    system_prompt, user_content = build_typed_reviewer_prompt(
        text, lua_ctx, section_heading, rule_ids=rule_ids, file_type=file_type
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    token_count = count_tokens(system_prompt + user_content)
    print(f"  [content/chunked] Reviewer prompt: {token_count:,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_reviewer", system_prompt + "\n\n" + user_content)

    for attempt in range(BAD_RESPONSE_RETRIES + 1):
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
            continue
        approved = bool(data.get("approved", False))
        findings = parse_findings_json(data)
        if approved:
            return []
        if findings is not None:
            return findings
    return []


def _extract_target_text(text: str, finding: Finding) -> str | None:
    """Extract the specific text snippet that a finding targets.

    For function-level findings: returns the fn_block for finding.function,
    or None if the function is not present in this batch (cross-batch hallucination).
    For section-level findings (no function): returns the full section text.
    """
    if finding.function:
        _, fn_blocks = split_section_blocks(text)
        # Strip params from reviewer output: "Foo(x, y)" → "Foo" to match heading regex
        fn_name = re.sub(r'\s*\(.*$', '', finding.function).strip()
        for block in fn_blocks:
            m = re.match(r'^### `?([^`(\n]+)', block.split("\n", 1)[0])
            if m and m.group(1).strip() == fn_name:
                return block
        return None  # function not in this batch — skip instead of using full text
    return text


def _call_writer(
    target_text: str,
    lua_ctx: str,
    finding: Finding,
    config: ContentLoopConfig,
    file_type: str,
) -> TypedOp | None:
    """Call the writer LLM for one Finding and return a TypedOp. Returns None on failure."""
    system_prompt, user_content = build_typed_writer_prompt(
        target_text, lua_ctx, finding, finding.section, file_type
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    token_count = count_tokens(system_prompt + user_content)
    print(f"  [content/chunked] Writer prompt: {token_count:,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer", system_prompt + "\n\n" + user_content)

    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        resp = ollama_chat(
            model=config.writer_model,
            messages=messages,
            format=TYPED_OP_SCHEMA,
            options={"temperature": WRITER_TEMPERATURE, "think": WRITER_THINK},
        )
        raw = resp["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_writer_response", raw)
        data = _try_parse_json(raw)
        if data is None:
            continue
        op = parse_typed_op_json(data)
        if op and op.op:
            return op
    return None


def _run_typed_loop(
    cache: CacheManager,
    cache_id: str,
    lua_ctx: str,
    section_heading: str,
    intentionally_removed: set[str],
    config: ContentLoopConfig,
    file_type: str,
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

    last_findings: list[Finding] = []

    for i in range(max_iters):
        # Read current content from cache
        text = cache.read(cache_id)

        findings = _call_reviewer(text, lua_ctx, section_heading, config, file_type)
        _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)  # sleep after every reviewer call
        if not findings:
            return text, [], i + 1
        last_findings = findings

        for finding in findings:
            # Re-read from cache each time (writer may have updated it)
            text = cache.read(cache_id)
            target_text = _extract_target_text(text, finding)
            if target_text is None:
                print(f"  [content/chunked] Finding for '{finding.function}' not in batch — skipping")
                continue
            op = _call_writer(target_text, lua_ctx, finding, config, file_type)
            _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)  # sleep after every writer call
            if op is None:
                continue
            dummy = DocSection(heading=section_heading, text=text)
            updated = apply_typed_ops(
                [dummy], [op], frontmatter="",
                intentionally_removed=intentionally_removed,
            )
            # Writer updates the cache
            cache.write(cache_id, updated[0].text)

    # Final verification: fixes from the last iteration are applied but unreviewed.
    # One extra review confirms whether they resolved the issues.
    text = cache.read(cache_id)
    final_findings = _call_reviewer(text, lua_ctx, section_heading, config, file_type)
    _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)  # sleep after final reviewer call
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

    for sec_idx, section in enumerate(sections, 1):
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
                # Create cache for this batch
                batch_cache_id = f"sec{sec_idx}_batch{bi}"
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

            # Create cache for this section
            sec_cache_id = f"sec{sec_idx}"
            cache.create(sec_cache_id, section.text)

            updated_text, issues, iters = _run_typed_loop(
                cache, sec_cache_id, lua_ctx, section.heading,
                intentionally_removed=set(), config=config, file_type=file_type,
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

    return ContentLoopResult(
        approved=n_issues == 0,
        iterations=total_iterations,
        final_issues=all_issues,
    )
