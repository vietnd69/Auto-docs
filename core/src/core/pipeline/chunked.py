"""
Module handling Ollama calls for chunked pipeline.
Separated from olm.py because:
  - Intermediate chunk: calls LLM but DOES NOT write file, only returns text
  - Final merge: calls LLM and writes .md file

Functions:
  - save/load/clear_checkpoint(): manage checkpoints
  - generate_chunk_analysis(): calls LLM for 1 chunk/group, returns text
  - generate_merged_doc():     calls LLM merge + writes .md file
  - hierarchical_merge():      2-tier merge for extremely large files
  - rolling_merge_to_one():    fallback merge by pairs
  - process_chunked_file():    full pipeline: split → analyze chunks → merge
"""

import os
import sys
import time
import json
from pathlib import Path
from llm import client as config
from llm.paths import PROJECT_ROOT
from llm.settings import DEBUG_PROMPTS, BAD_RESPONSE_RETRIES, MAIN_THINK
from core.utils import shutdown

from core.config import CHECKPOINT_DIR

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _dump_debug(label: str, content: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = _DEBUG_DIR / f"{label}_{int(time.time())}.txt"
    path.write_text(content, encoding="utf-8")
    print(f"  [debug] {label} → {path.name}")


def _detect_context_mode(content: str) -> str:
    """Determine mode of connected content based on marker strings."""
    if "--[SIGONLY:" in content:
        return "signatures"
    if "-- COMPRESSED:" in content:
        return "compressed"
    if "-- COMPACT:" in content:
        return "compact"
    if "-- [REQUIRE FULL:" in content:
        return "require_full"
    if "-- [REQUIRE MODULE:" in content:
        return "require_module"
    return "full"

def _ensure_events_section(doc: str) -> str:
    """
    Guarantee ## Events & listeners is present in merge LLM output.
    If the heading is absent, append a minimal fallback block.
    Must be called AFTER the empty-content guard in generate_merged_doc().
    """
    if "## Events & listeners" not in doc:
        doc = doc.rstrip() + "\n\n## Events & listeners\nThis file is not event-driven.\n"
    return doc


from rag.docs import (
    clean_model_output,
    extract_lua_references,
    inject_frontmatter_field,
    safe_read_lua,
    compute_source_hash,
    format_connected_section,
)
from rag.content import (
    extract_connected_for_chunk,
    extract_connected_content,
    extract_compact_content,
    compress_connected_content,
)
from llm.tokens import estimate_merge_tokens
from core.pipeline.chunking import (
    needs_chunking,
    split_lua_into_chunks,
    strip_bulk_data,
    calc_token_budget,
    MERGE_TOKEN_LIMIT,
    CONTEXT_RESERVE,
)
from llm.settings import CHUNK_PROMPT_TOKEN_LIMIT
from prompts.chunked import (
    build_chunk_prompt,
    build_merge_prompt,
    build_intermediate_merge_prompt,
    _build_merge_prompt_legacy,
    build_deps_props_prompt,
    build_functions_batch_prompt,
    build_events_prompt,
    build_prose_prompt,
)
from prompts.pre_synthesis import pre_synthesize
from prompts.type_detect import detect_lua_type

_MULTIPASS_FUNC_THRESHOLD = 100

# ── Checkpoint System ──────────────────────────────────────────

def save_checkpoint(
    comp_name: str,
    chunk_results: dict[int, str],  # change list → dict {chunk_index: result}
    last_index: int,
    failed_indices: list[int] | None = None,
) -> None:
    """Save progress after each successful chunk (atomic write)."""
    Path(CHECKPOINT_DIR).mkdir(parents=True, exist_ok=True)
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.json"
    temp_path = f"{checkpoint_path}.tmp"

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump({
            "version": 2,
            "comp_name": comp_name,
            "last_index": last_index,
            "chunk_results": {str(k): v for k, v in chunk_results.items()},
            "failed_indices": failed_indices or [],
        }, f, ensure_ascii=False)

    # Atomic rename
    os.replace(temp_path, checkpoint_path)


def load_checkpoint(comp_name: str) -> tuple[dict[int, str], int, list[int]] | None:
    """
    Load checkpoint if exists.
    Returns (chunk_results, last_index, failed_indices) or None if not available.
    """
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.json"
    if not Path(checkpoint_path).exists():
        return None
    try:
        with open(checkpoint_path, encoding="utf-8") as f:
            state = json.load(f)

        # Version detection: v1 checkpoints contain text markdown, not JSON
        version = state.get("version", 1)
        if version == 1:
            print("  [CHECKPOINT] v1 checkpoint detected — clearing, restart from scratch")
            clear_checkpoint(comp_name)
            return None

        chunk_results = {int(k): v for k, v in state["chunk_results"].items()}
        failed_indices = state.get("failed_indices", [])
        last_index = state["last_index"]
        print(f"  [CHECKPOINT] Resume from chunk {last_index + 2}")
        if failed_indices:
            print(f"  [CHECKPOINT] There are {len(failed_indices)} failed chunks needing retry: {failed_indices}")
        return chunk_results, last_index, failed_indices
    except Exception as e:
        print(f"  [CHECKPOINT] Failed to load: {e}")
        return None


def clear_checkpoint(comp_name: str) -> None:
    """Clear checkpoint after successful merge."""
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.json"
    if Path(checkpoint_path).exists():
        Path(checkpoint_path).unlink()


# ── Merge Checkpoint ──────────────────────────────────────────

def save_merge_checkpoint(
    comp_name: str,
    stage: str,           # "hierarchical_t1" | "rolling"
    results: list[str],   # merged results up to now
    last_index: int,      # last successfully processed index
) -> None:
    """Save merge progress (atomic write)."""
    Path(CHECKPOINT_DIR).mkdir(parents=True, exist_ok=True)
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.merge.json"
    temp_path = f"{checkpoint_path}.tmp"

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump({
            "stage": stage,
            "results": results,
            "last_index": last_index,
        }, f, ensure_ascii=False)

    # Atomic rename
    os.replace(temp_path, checkpoint_path)


def load_merge_checkpoint(comp_name: str) -> dict | None:
    """Load merge checkpoint if exists."""
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.merge.json"
    if not Path(checkpoint_path).exists():
        return None
    try:
        with open(checkpoint_path, encoding="utf-8") as f:
            state = json.load(f)
        print(f"  [MERGE CHECKPOINT] Resume stage='{state['stage']}' from index {state['last_index'] + 1}")
        return state
    except Exception as e:
        print(f"  [MERGE CHECKPOINT] Failed to load: {e}")
        return None


def clear_merge_checkpoint(comp_name: str) -> None:
    """Clear merge checkpoint after success."""
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.merge.json"
    if Path(checkpoint_path).exists():
        Path(checkpoint_path).unlink()


def generate_chunk_analysis(
    prompt: str,
    chunk_index: int,
    total_chunks: int,
    model_name: str = "qwen3-coder-next:cloud",
    sleep_time: int = 10,
    label: str = "Chunk",
) -> str | None:
    """
    Call Ollama to analyze 1 chunk or group. Returns text result (DOES NOT write file).

    Args:
        prompt: Prompt for this chunk.
        chunk_index: Order number (1-based).
        total_chunks: Total.
        model_name: Ollama model name.
        sleep_time: Rest between calls (seconds).
        label: Display label ("Chunk", "Group", "Rolling").
    """
    print(f"    [{label} {chunk_index}/{total_chunks}] Processing...")

    if DEBUG_PROMPTS:
        _dump_debug(f"chunk_{label.lower()}{chunk_index}_prompt", prompt)

    for attempt in range(1, BAD_RESPONSE_RETRIES + 2):
        try:
            response = config.ollama_chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                think=bool(MAIN_THINK),
            )
            result = response["message"]["content"]
            if DEBUG_PROMPTS:
                _dump_debug(f"chunk_{label.lower()}{chunk_index}_response", result)
            result = clean_model_output(result)

            if not result:
                remaining = BAD_RESPONSE_RETRIES + 1 - attempt
                if remaining > 0:
                    print(f"    [{label} {chunk_index}/{total_chunks}] Model returned empty → retry ({remaining} left)")
                    continue
                print(f"    [{label} {chunk_index}/{total_chunks}] Failed — model returned empty after {attempt} attempts")
                return None

            lines_count = result.count("\n") + 1
            print(f"    [{label} {chunk_index}/{total_chunks}] Done — {lines_count} lines of output")

            if sleep_time > 0 and not shutdown.stop_requested:
                print(f"    Resting {sleep_time} seconds...")
                shutdown.interruptible_sleep(sleep_time)

            return result

        except Exception as e:
            remaining = BAD_RESPONSE_RETRIES + 1 - attempt
            if remaining > 0:
                print(f"    [Error] {label} {chunk_index}/{total_chunks}: {e} → retry ({remaining} left)")
                shutdown.interruptible_sleep(5)
            else:
                print(f"    [Error] {label} {chunk_index}/{total_chunks}: {e} — giving up")
                return None

    return None


def generate_merged_doc(
    prompt: str,
    md_filepath: str,
    source_hash: str = "",
    model_name: str = "qwen3-coder-next:cloud",
    sleep_time: int = 10,
    max_retries: int = 3,
    retry_delay: int = 30,
) -> str | None:
    """
    Call Ollama with merge prompt, write result to .md file.
    Auto retry if model returns empty or error.

    Args:
        prompt: Merge prompt containing all chunk results.
        md_filepath: Output .md file path.
        model_name: Ollama model name.
        sleep_time: Rest after writing (seconds).
        max_retries: Maximum number of retries (default 3).
        retry_delay: Sleep between retries (seconds, default 30).

    Returns:
        .md file name (basename) if successful, None if failed.
    """
    md_filename = os.path.basename(md_filepath)

    for attempt in range(1, max_retries + 1):
        try:
            if attempt == 1:
                print(f"    [Merge] Synthesizing document...")
            else:
                print(f"    [Merge retry {attempt}/{max_retries}] Retrying...")

            if DEBUG_PROMPTS and attempt == 1:
                _dump_debug(f"merge_prompt_{md_filename}", prompt)

            response = config.ollama_chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                think=bool(MAIN_THINK),
            )

            md_content = response["message"]["content"]
            if DEBUG_PROMPTS:
                _dump_debug(f"merge_response_{md_filename}", md_content)
            md_content = clean_model_output(md_content)

            # Guard: model returned empty (only thinking block or error)
            if not md_content:
                print(f"    [Merge] Attempt {attempt}/{max_retries} — model returned empty")
                if attempt < max_retries:
                    print(f"    Resting {retry_delay} seconds before retry...")
                    shutdown.interruptible_sleep(retry_delay)
                continue

            md_content = _ensure_events_section(md_content)

            # Sanity check: output must start with YAML frontmatter
            if not md_content.startswith("---"):
                if attempt < max_retries:
                    print(
                        f"    [Bad response] Attempt {attempt}/{max_retries} — merge output of {md_filename} "
                        f"does not start with YAML frontmatter, retrying..."
                    )
                    shutdown.interruptible_sleep(retry_delay)
                    continue
                print(
                    f"    [Warning] Merge output of {md_filename} does not start with YAML frontmatter "
                    f"after {max_retries} attempts — writing file and continuing"
                )

            if source_hash:
                md_content = inject_frontmatter_field(md_content, "source_hash", source_hash)

            dir_name = os.path.dirname(md_filepath)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            with open(md_filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            if attempt > 1:
                print(f"    [Merge] Succeeded on attempt {attempt}")
            print(f"    [Merge] Created {md_filename}")

            if sleep_time > 0 and not shutdown.stop_requested:
                print(f"    Resting {sleep_time} seconds...")
                shutdown.interruptible_sleep(sleep_time)

            return md_filename

        except Exception as e:
            print(f"    [Merge] Attempt {attempt}/{max_retries} error: {e}")
            if attempt < max_retries:
                print(f"    Resting {retry_delay} seconds before retry...")
                shutdown.interruptible_sleep(retry_delay)

    print(f"    [Error] Merge failed for {md_filename} after {max_retries} attempts")
    return None


def multipass_merge(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    presynthesis,                # PreSynthesisResult
    source_hash: str,
    md_filepath: str,
    *,
    file_tree: str = "",
    connected_section: str = "",
    connected_content: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    lua_type: str = "",
    sidebar_position: int = 10,
    model_name: str = "qwen3-coder-next:cloud",
    sleep_time: int = 10,
    max_retries: int = 3,
    retry_delay: int = 30,
    functions_batch_size: int = 150,
) -> str | None:
    """
    Multipass merge strategy for large files with many functions.
    Splits merge into 4 focused LLM passes:
      Pass 1a: deps + props section
      Pass 1b: function batches (N passes, each up to functions_batch_size)
      Pass 1c: events section
      Pass 2:  prose (YAML frontmatter + Overview + Usage example)
    Then assembles and writes the final file.
    """
    # ── Checkpoint resume ──
    ckpt = load_merge_checkpoint(comp_name)
    if ckpt and ckpt["stage"] == "multipass":
        completed_sections = ckpt["results"]
        print(f"  [MULTIPASS] Resuming from section {ckpt['last_index'] + 2}")
    else:
        completed_sections = []

    # Pre-compute structure
    functions = presynthesis.functions
    batches = [functions[i:i + functions_batch_size] for i in range(0, len(functions), functions_batch_size)]
    total_batches = len(batches)
    # Section order in completed_sections:
    #   0        → deps_props
    #   1..N     → function batch 1..N
    #   N+1      → events
    #   N+2      → prose
    total_sections = 1 + total_batches + 1 + 1  # deps_props + batches + events + prose
    events_section_idx = 1 + total_batches       # 0-based index in completed_sections
    prose_section_idx = events_section_idx + 1

    section_counter = 0  # tracks 1-based index for generate_chunk_analysis display

    print(f"  [MULTIPASS] {total_sections} sections total ({total_batches} fn batches of {functions_batch_size})")

    # ── Pass 1a: deps + props ──
    if len(completed_sections) <= 0:
        print(f"  [MULTIPASS] Pass 1a: deps+props...")
        deps_json = json.dumps(presynthesis.dependencies, indent=2, ensure_ascii=False)
        game_tags_json = json.dumps(presynthesis.game_tags, indent=2, ensure_ascii=False)
        external_deps_json = json.dumps(presynthesis.external_deps, indent=2, ensure_ascii=False)
        props_json = json.dumps(presynthesis.constructor_properties, indent=2, ensure_ascii=False)
        prompt = build_deps_props_prompt(
            comp_name, display_filepath, deps_json, game_tags_json, external_deps_json, props_json,
            lua_type=lua_type,
        )
        section_counter += 1
        result = generate_chunk_analysis(prompt, section_counter, total_sections, model_name, sleep_time, label="Multipass")
        if result is None:
            return None
        completed_sections.append(result)
        save_merge_checkpoint(comp_name, "multipass", completed_sections, len(completed_sections) - 1)
    else:
        section_counter += 1

    # ── Pass 1b: function batches ──
    if total_batches > 0:
        print(f"  [MULTIPASS] Pass 1b: functions ({total_batches} batches)...")
        for batch_idx, batch in enumerate(batches, 1):
            completed_idx = batch_idx  # completed_sections index = 1-based batch index (0 is deps_props)
            if len(completed_sections) > completed_idx - 1 + 1:
                # Already done
                section_counter += 1
                continue
            prompt = build_functions_batch_prompt(
                comp_name, display_filepath, batch, batch_idx, total_batches,
                lua_type=lua_type,
            )
            section_counter += 1
            result = generate_chunk_analysis(prompt, section_counter, total_sections, model_name, sleep_time, label="Multipass")
            if result is None:
                return None
            completed_sections.append(result)
            save_merge_checkpoint(comp_name, "multipass", completed_sections, len(completed_sections) - 1)
    else:
        section_counter += total_batches

    # ── Pass 1c: events ──
    if len(completed_sections) <= events_section_idx:
        print(f"  [MULTIPASS] Pass 1c: events...")
        events_json = json.dumps(
            {"listens_to": presynthesis.events_listens, "pushes": presynthesis.events_pushes},
            indent=2,
            ensure_ascii=False,
        )
        prompt = build_events_prompt(comp_name, display_filepath, events_json, lua_type=lua_type)
        section_counter += 1
        result = generate_chunk_analysis(prompt, section_counter, total_sections, model_name, sleep_time, label="Multipass")
        if result is None:
            return None
        completed_sections.append(result)
        save_merge_checkpoint(comp_name, "multipass", completed_sections, len(completed_sections) - 1)
    else:
        section_counter += 1

    # ── Pass 2: prose ──
    if len(completed_sections) <= prose_section_idx:
        print(f"  [MULTIPASS] Pass 2: prose...")
        function_names = [f["name"] for f in presynthesis.functions]
        prompt = build_prose_prompt(
            comp_name,
            comp_title,
            display_filepath,
            presynthesis,
            function_names,
            file_tree=file_tree,
            connected_section=connected_section,
            connected_content=connected_content,
            today_date=today_date,
            version=version,
            category_type=category_type,
            lua_type=lua_type,
            sidebar_position=sidebar_position,
            source_hash=source_hash,
        )
        section_counter += 1
        result = generate_chunk_analysis(prompt, section_counter, total_sections, model_name, sleep_time, label="Multipass")
        if result is None:
            return None
        completed_sections.append(result)
        save_merge_checkpoint(comp_name, "multipass", completed_sections, len(completed_sections) - 1)

    # ── Assemble ──
    prose_result = completed_sections[prose_section_idx]
    deps_props_result = completed_sections[0]
    fn_batch_results = completed_sections[1:events_section_idx]
    events_result = completed_sections[events_section_idx]

    assembled = prose_result.rstrip()
    assembled += "\n\n" + deps_props_result.strip()
    assembled += "\n\n## Main functions\n\n" + "\n\n".join(fn.strip() for fn in fn_batch_results)
    assembled += "\n\n" + events_result.strip()

    assembled = _ensure_events_section(assembled)

    if source_hash:
        assembled = inject_frontmatter_field(assembled, "source_hash", source_hash)

    if DEBUG_PROMPTS:
        _dump_debug(f"multipass_assembled_{os.path.basename(md_filepath)}", assembled)

    dir_name = os.path.dirname(md_filepath)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(md_filepath, "w", encoding="utf-8") as f:
        f.write(assembled)
    md_filename = os.path.basename(md_filepath)
    print(f"    [Multipass] Created {md_filename}")

    return md_filename


def hierarchical_merge(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    chunk_results: list[str],
    source_hash: str,
    md_filepath: str,
    *,
    file_tree: str = "",
    connected_section: str = "",
    connected_content: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    sidebar_position: int = 10,
    model_name: str = "qwen3-coder-next:cloud",
    group_size: int = 10,
    sleep_time: int = 10,
) -> str | None:
    """
    2-tier hierarchical merge:
      Tier 1: Split chunk_results into group_size groups, merge each group → intermediate summary
      Tier 2: Merge all intermediate summaries → final document
    """
    total = len(chunk_results)

    # Auto calculate group_size based on actual tokens
    # Goal: each group fits within MERGE_TOKEN_LIMIT
    total_tokens = estimate_merge_tokens(chunk_results)
    if total_tokens > 0:
        avg_tokens = total_tokens / total
        computed = max(2, int(MERGE_TOKEN_LIMIT / avg_tokens))
        group_size = min(computed, group_size, total)
        print(
            f"  [HIERARCHICAL] Auto group_size: {total_tokens} tokens / {total} chunks "
            f"≈ {avg_tokens:.0f} tok/chunk → group_size={group_size}"
        )

    groups = [chunk_results[i:i + group_size] for i in range(0, total, group_size)]
    total_groups = len(groups)

    print(f"  [HIERARCHICAL] {total} chunks → {total_groups} groups × {group_size}")

    # ── Resume tier 1 if available ──
    merge_ckpt = load_merge_checkpoint(comp_name)
    if merge_ckpt and merge_ckpt["stage"] == "hierarchical_t1":
        intermediate_results = merge_ckpt["results"]
        resume_group_from = merge_ckpt["last_index"]
        print(f"  [HIERARCHICAL] Resuming tier 1 from group {resume_group_from + 2}")
    else:
        intermediate_results = []
        resume_group_from = -1

    # Tier 1: merge each group
    for g_idx, group in enumerate(groups, 1):
        if g_idx - 1 <= resume_group_from:
            continue

        prompt = build_intermediate_merge_prompt(
            comp_name=comp_name,
            display_filepath=display_filepath,
            group_results=group,
            group_index=g_idx,
            total_groups=total_groups,
        )

        result = generate_chunk_analysis(
            prompt=prompt,
            chunk_index=g_idx,
            total_chunks=total_groups,
            model_name=model_name,
            sleep_time=sleep_time,
            label="Group",
        )

        if result:
            intermediate_results.append(result)
            save_merge_checkpoint(comp_name, "hierarchical_t1", intermediate_results, g_idx - 1)
        else:
            print(f"  [HIERARCHICAL] Group {g_idx} failed, skipping.")

    if not intermediate_results:
        print("  [HIERARCHICAL] All intermediate groups failed!")
        return None

    print(f"  [HIERARCHICAL] Tier 1 done: {len(intermediate_results)} intermediate summaries")

    # Check: does tier 2 exceed threshold?
    if estimate_merge_tokens(intermediate_results) > MERGE_TOKEN_LIMIT:
        print("  [HIERARCHICAL] Intermediate results still large → tier 2 rolling merge")
        rolled = rolling_merge_to_one(
            comp_name=comp_name,
            display_filepath=display_filepath,
            results=intermediate_results,
            model_name=model_name,
            sleep_time=sleep_time,
        )
        if rolled is None:
            return None # checkpoint already saved in rolling, resume on next run
        rolled_tokens = estimate_merge_tokens([rolled])
        if rolled_tokens > MERGE_TOKEN_LIMIT:
            print(f"  [HIERARCHICAL] Warning: rolled result still large ({rolled_tokens:,} tok > {MERGE_TOKEN_LIMIT:,} limit) — continue tier 2 merge")
        intermediate_results = [rolled]

    # Tier 2: final merge (legacy text-based prompt)
    merge_prompt = _build_merge_prompt_legacy(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        chunk_results=intermediate_results,
        source_hash=source_hash,
        file_tree=file_tree,
        connected_section=connected_section,
        connected_content=connected_content,
        today_date=today_date,
        version=version,
        category_type=category_type,
        sidebar_position=sidebar_position,
        input_label="GROUP",
    )

    result = generate_merged_doc(
        prompt=merge_prompt,
        md_filepath=md_filepath,
        model_name=model_name,
        sleep_time=sleep_time,
    )
    if result:
        clear_merge_checkpoint(comp_name)   # only delete when success is confirmed
    return result


def rolling_merge_to_one(
    comp_name: str,
    display_filepath: str,
    results: list[str],
    model_name: str,
    sleep_time: int,
) -> str | None:
    """
    Fallback: sequential merge pair by pair. Returns 1 synthesized string.
    """
    # ── Resume if available ──
    merge_ckpt = load_merge_checkpoint(comp_name)
    if merge_ckpt and merge_ckpt["stage"] == "rolling":
        accumulated = merge_ckpt["results"][0]
        resume_from = merge_ckpt["last_index"]
        print(f"  [ROLLING] Resume from step {resume_from + 2}")
    else:
        accumulated = results[0]
        resume_from = 0

    for i, result in enumerate(results[1:], 2):
        if i <= resume_from:
            continue

        prompt = build_intermediate_merge_prompt(
            comp_name=comp_name,
            display_filepath=display_filepath,
            group_results=[accumulated, result],
            group_index=i,
            total_groups=len(results),
        )
        merged = generate_chunk_analysis(
            prompt=prompt,
            chunk_index=i,
            total_chunks=len(results),
            model_name=model_name,
            sleep_time=sleep_time,
            label="Rolling",
        )

        if merged:
            accumulated = merged
            save_merge_checkpoint(comp_name, "rolling", [accumulated], i)
        else:
            # Save progress and return None so the caller knows processing was interrupted
            save_merge_checkpoint(comp_name, "rolling", [accumulated], i - 1)
            print(f"  [ROLLING] Failed at step {i}, checkpoint saved.")
            return None

    return accumulated


def process_chunked_file(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    lua_code: str,
    connected_section: str,
    connected_content: str,
    source_hash: str,
    md_filepath: str,
    *,
    full_refs: list[tuple[str, list[str]]] | None = None,
    file_tree: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    lua_type: str = "",
    model_name: str = "qwen3-coder-next:cloud",
    chunk_sleep: int = 10,
    merge_sleep: int = 20,
    sidebar_position: int = 10,
    fresh_start: bool = False,
) -> str | None:
    """
    Full pipeline for long Lua files with Checkpoint and Hierarchical Merge.

    Args:
        full_refs: Refs of the entire Lua file, used as fallback in
                   extract_connected_for_chunk() for chunks without local refs.
                   If None: smart fallback doesn't work (graceful degrade).
        fresh_start: If True, clear old checkpoint before running (no resume).
    """
    # Step 1: Strip bulk numerical data (tile data)
    stripped_code = strip_bulk_data(lua_code)
    original_chars = len(lua_code)
    stripped_chars = len(stripped_code)
    if stripped_chars < original_chars:
        saved = original_chars - stripped_chars
        print(f"  [STRIP] Removed {saved:,} characters of tile/map data ({saved*100//original_chars}% file)")

    # Step 2: Calculate dynamic token budget (no connected — CONTEXT_RESERVE subtracted internally)
    # Use CHUNK_PROMPT_TOKEN_LIMIT instead of PROMPT_TOKEN_LIMIT for sufficient per-chunk budget.
    # PROMPT_TOKEN_LIMIT only used to trigger chunking, not chunk size limit.
    token_budget = calc_token_budget(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        connected_section="",
        connected_content="",
        source_hash=source_hash,
        file_tree=file_tree,
        today_date=today_date,
        version=version,
        category_type=category_type,
        prompt_token_limit=CHUNK_PROMPT_TOKEN_LIMIT,
    )

    # Step 3: Split chunks by token budget
    chunks = split_lua_into_chunks(stripped_code, max_tokens=token_budget)
    total_chunks = len(chunks)
    if total_chunks > 30:
        print(f"  [CHUNKED] Large number of chunks ({total_chunks} > 30), increase sleep to 20s")
        chunk_sleep = 20

    print(f"  [CHUNKED] Split into {total_chunks} chunks")

    # ── SHORTCUT: 1 chunk → direct standard pipeline ──────────────────
    # With only 1 chunk, the intermediate step (chunk JSON → pre-synthesis) is unnecessary.
    # Use standard pipeline with per-chunk connected content to save 1 LLM call.
    if total_chunks == 1:
        print(f"  [1-CHUNK] Only 1 chunk — using standard pipeline directly (saves 1 LLM call)")
        _own_filename = os.path.basename(display_filepath)
        chunk_section, chunk_content, ref_count = extract_connected_for_chunk(
            chunk_code=stripped_code,
            own_filename=_own_filename,
            full_refs=full_refs,
            max_lines_per_file=100,
            max_total_tokens=CONTEXT_RESERVE,
        )
        if chunk_content:
            _func_mode = _detect_context_mode(chunk_content)
            _has_req_full = "-- [REQUIRE FULL:" in chunk_content
            _has_req_module = "-- [REQUIRE MODULE:" in chunk_content
            _req_mode = "require_full" if _has_req_full else ("require_module" if _has_req_module else None)
            if _req_mode:
                print(f"    [CTX] {ref_count} refs, func_mode={_func_mode} | req_stubs={_req_mode}")
            else:
                print(f"    [CTX] {ref_count} refs, mode={_func_mode}")
        elif ref_count > 0:
            print(f"    [CTX] {ref_count} refs but could not extract content")
        else:
            print(f"    [CTX] no external context (standalone file)")

        from prompts.standard import build_prompt as _build_std_prompt
        from core.pipeline.standard import generate_doc as _generate_doc

        std_prompt = _build_std_prompt(
            comp_name=comp_name,
            comp_title=comp_title,
            display_filepath=display_filepath,
            lua_code=stripped_code,
            connected_section=chunk_section,
            connected_content=chunk_content,
            source_hash=source_hash,
            file_tree=file_tree,
            today_date=today_date,
            version=version,
            category_type=category_type,
        )

        if DEBUG_PROMPTS:
            _dump_debug(f"1chunk_prompt_{os.path.basename(md_filepath)}", std_prompt)

        return _generate_doc(
            prompt=std_prompt,
            md_filepath=md_filepath,
            source_hash=source_hash,
            model_name=model_name,
            sleep_time=merge_sleep,
        )

    # ── CHECKPOINT RESUME ──
    if fresh_start:
        clear_checkpoint(comp_name)
        clear_merge_checkpoint(comp_name)
    resume = load_checkpoint(comp_name)
    if resume:
        chunk_results, resume_from, pending_retries = resume
        print(f"  [CHECKPOINT] Found {len(chunk_results)} existing chunks")
    else:
        chunk_results: dict[int, str] = {}
        resume_from = -1
        pending_retries: list[int] = []

    # Validate shape of loaded checkpoint entries — stale entries from before fix may have wrong shape
    if chunk_results:
        stale_bad: list[int] = []
        clean_results: dict[int, str] = {}
        for k, v in chunk_results.items():
            try:
                p = json.loads(v)
                if isinstance(p, dict) and "functions" in p:
                    clean_results[k] = v
                else:
                    stale_bad.append(k)
            except (json.JSONDecodeError, ValueError):
                stale_bad.append(k)
        if stale_bad:
            print(f"  [CHECKPOINT] {len(stale_bad)} checkpoint entries have incorrect shape, will retry: {stale_bad}")
            pending_retries = list(set(pending_retries) | set(stale_bad))
            chunk_results = clean_results

    # ── PER-CHUNK CONTEXT SETUP ──
    own_filename = os.path.basename(display_filepath)

    # ── MAIN LOOP ──
    failed_indices: list[int] = list(pending_retries)  # carry over failures from previous run

    for i, chunk_code in enumerate(chunks, 1):
        if shutdown.stop_requested:
            print("  [System] Chunked pipeline stopped after current chunk.")
            break
        # Skip chunks already processed
        if i - 1 <= resume_from:
            continue
        if i in chunk_results:  # already present from checkpoint
            continue

        # ── PER-CHUNK CONTEXT ──
        chunk_section, chunk_content, ref_count = extract_connected_for_chunk(
            chunk_code=chunk_code,
            own_filename=own_filename,
            full_refs=full_refs,
            max_lines_per_file=100,
            max_total_tokens=CONTEXT_RESERVE,
        )
        if chunk_content:
            # Detect modes for func content and req stubs separately
            func_mode = _detect_context_mode(chunk_content)
            has_req_full = "-- [REQUIRE FULL:" in chunk_content
            has_req_module = "-- [REQUIRE MODULE:" in chunk_content
            req_mode = "require_full" if has_req_full else ("require_module" if has_req_module else None)
            if req_mode:
                print(f"    [CTX] Chunk {i}: {ref_count} refs, func_mode={func_mode} | req_stubs={req_mode}")
            else:
                print(f"    [CTX] Chunk {i}: {ref_count} refs, mode={func_mode}")
        elif ref_count > 0:
            print(f"    [CTX] Chunk {i}: {ref_count} refs but could not extract content (require-only, no function call)")
        else:
            print(f"    [CTX] Chunk {i}: no external context (standalone chunk)")

        prompt = build_chunk_prompt(
            comp_name=comp_name,
            comp_title=comp_title,
            display_filepath=display_filepath,
            chunk_code=chunk_code,
            chunk_index=i,
            total_chunks=total_chunks,
            today_date=today_date,
            version=version,
            category_type=category_type,
            lua_type=lua_type,
            file_tree=file_tree,
            connected_section=chunk_section,
            connected_content=chunk_content,
        )

        result = generate_chunk_analysis(
            prompt=prompt,
            chunk_index=i,
            total_chunks=total_chunks,
            model_name=model_name,
            sleep_time=chunk_sleep,
            label="Chunk",
        )

        if result:
            try:
                parsed = json.loads(result)
                if not isinstance(parsed, dict) or "functions" not in parsed:
                    raise ValueError("chunk JSON missing required shape")
                chunk_results[i] = result
                save_checkpoint(comp_name, chunk_results, i - 1, failed_indices)
            except (json.JSONDecodeError, ValueError):
                print(f"    [Warning] Chunk {i} JSON is invalid or has wrong schema, will retry.")
                failed_indices.append(i)
                save_checkpoint(comp_name, chunk_results, i - 1, failed_indices)
        else:
            failed_indices.append(i)
            print(f"    [Warning] Chunk {i} failed.")
            save_checkpoint(comp_name, chunk_results, i - 1, failed_indices)

    # ── RETRY LOOP — runs after all chunks have been processed ──
    if failed_indices and not shutdown.stop_requested:
        print(f"\n  [RETRY] {len(failed_indices)} chunks failed: {failed_indices}")
        print(f"  [RETRY] Starting retry (up to 3 attempts, 30s apart)...")

        still_failing: list[int] = []

        for chunk_i in failed_indices:
            if shutdown.stop_requested:
                still_failing.extend(failed_indices[failed_indices.index(chunk_i):])
                break
            chunk_code = chunks[chunk_i - 1]  # chunks list is 0-based

            # Per-chunk context cho retry
            chunk_section, chunk_content, ref_count = extract_connected_for_chunk(
                chunk_code=chunk_code,
                own_filename=own_filename,
                full_refs=full_refs,
                max_lines_per_file=100,
                max_total_tokens=CONTEXT_RESERVE,
            )
            if chunk_content:
                func_mode = _detect_context_mode(chunk_content)
                has_req_full = "-- [REQUIRE FULL:" in chunk_content
                has_req_module = "-- [REQUIRE MODULE:" in chunk_content
                req_mode = "require_full" if has_req_full else ("require_module" if has_req_module else None)
                if req_mode:
                    print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs, func_mode={func_mode} | req_stubs={req_mode}")
                else:
                    print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs, mode={func_mode}")
            elif ref_count > 0:
                print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs but could not extract content (require-only, no function call)")
            else:
                print(f"    [CTX] Chunk {chunk_i} (retry): no external context (standalone chunk)")

            prompt = build_chunk_prompt(
                comp_name=comp_name,
                comp_title=comp_title,
                display_filepath=display_filepath,
                chunk_code=chunk_code,
                chunk_index=chunk_i,
                total_chunks=total_chunks,
                today_date=today_date,
                version=version,
                category_type=category_type,
                lua_type=lua_type,
                file_tree=file_tree,
                connected_section=chunk_section,
                connected_content=chunk_content,
            )

            success = False
            for attempt in range(1, 4):
                print(f"    [Retry {attempt}/3] Chunk {chunk_i}/{total_chunks}...")
                result = generate_chunk_analysis(
                    prompt=prompt,
                    chunk_index=chunk_i,
                    total_chunks=total_chunks,
                    model_name=model_name,
                    sleep_time=30 if attempt < 3 else 0,
                    label=f"Retry-{attempt}",
                )
                if result:
                    try:
                        parsed = json.loads(result)
                        if not isinstance(parsed, dict) or "functions" not in parsed:
                            raise ValueError("chunk JSON missing required shape")
                        chunk_results[chunk_i] = result
                        save_checkpoint(comp_name, chunk_results, total_chunks - 1, still_failing)
                        print(f"    [Retry] Chunk {chunk_i} succeeded on attempt {attempt}.")
                        success = True
                        break
                    except (json.JSONDecodeError, ValueError):
                        if attempt < 3:
                            print(f"    [Retry] Attempt {attempt} JSON invalid or wrong schema, retrying...")
                elif attempt < 3:
                    print(f"    [Retry] Attempt {attempt} failed, retrying after 30s...")

            if not success:
                still_failing.append(chunk_i)
                print(f"    [Retry] Chunk {chunk_i} still failed after 3 attempts.")

        failed_indices = still_failing

    # ── USER CONFIRM if chunks still failing ──
    if failed_indices:
        print(f"\n  ⚠️  {len(failed_indices)} chunks still failed after 3 retry attempts: {failed_indices}")
        print(f"  The document will be missing content from these chunks.")
        save_checkpoint(comp_name, chunk_results, total_chunks - 1, failed_indices)

        if not sys.stdin.isatty():
            print(f"  [HEADLESS] Cannot receive input (stdin is not a TTY). Stopping pipeline.")
            print(f"  [HEADLESS] {len(failed_indices)} chunks still failed. Re-run manually to continue.")
            return None
        confirm = input("\n  Continue merge with available data? [y/N]: ").strip().lower()
        if confirm != "y":
            print(f"  [STOPPED] Progress saved. Re-run to retry {len(failed_indices)} remaining chunks.")
            return None

        print(f"  [CONTINUING] Merging with {len(chunk_results)}/{total_chunks} chunks.")

    if not chunk_results:
        print(f"  [Error] No chunks succeeded!")
        return None

    # ── PRE-SYNTHESIS — pure Python aggregation, no LLM call ──
    print(f"  [PRE-SYNTHESIS] Aggregating {len(chunk_results)} chunk results...")
    presynthesis, malformed = pre_synthesize(chunk_results)

    if malformed:
        save_checkpoint(comp_name, chunk_results, total_chunks - 1, malformed)
        print(f"  [PRE-SYNTHESIS] {len(malformed)} chunk malformed JSON: {malformed}")
        print(f"  [PRE-SYNTHESIS] Retry the above chunks then re-run.")
        return None

    print(f"  [PRE-SYNTHESIS] OK — {len(presynthesis.game_tags)} game_tags, "
          f"{len(presynthesis.external_deps)} external_deps, "
          f"{len(presynthesis.functions)} functions, "
          f"scope={presynthesis.system_scope}")

    # ── MERGE ──
    if len(presynthesis.functions) > _MULTIPASS_FUNC_THRESHOLD:
        n_funcs = len(presynthesis.functions)
        print(f"  [MERGE STRATEGY] Multipass merge ({n_funcs} functions)")
        result_filename = multipass_merge(
            comp_name=comp_name,
            comp_title=comp_title,
            display_filepath=display_filepath,
            presynthesis=presynthesis,
            source_hash=source_hash,
            md_filepath=md_filepath,
            file_tree=file_tree,
            connected_section=connected_section,
            connected_content=connected_content,
            today_date=today_date,
            version=version,
            category_type=category_type,
            lua_type=lua_type,
            sidebar_position=sidebar_position,
            model_name=model_name,
            sleep_time=merge_sleep,
        )
    else:
        print(f"  [MERGE STRATEGY] Direct merge (JSON pipeline)")
        merge_prompt = build_merge_prompt(
            comp_name=comp_name,
            comp_title=comp_title,
            display_filepath=display_filepath,
            presynthesis=presynthesis,
            source_hash=source_hash,
            today_date=today_date,
            version=version,
            category_type=category_type,
            lua_type=lua_type,
            sidebar_position=sidebar_position,
            file_tree=file_tree,
            connected_section=connected_section,
            connected_content=connected_content,
        )
        result_filename = generate_merged_doc(
            prompt=merge_prompt,
            md_filepath=md_filepath,
            source_hash=source_hash,
            model_name=model_name,
            sleep_time=merge_sleep,
        )

    if result_filename:
        # Keep chunk checkpoint in case LLM output has errors and needs review.
        # Only delete merge checkpoint since it is no longer needed after merge completes.
        clear_merge_checkpoint(comp_name)

    return result_filename
