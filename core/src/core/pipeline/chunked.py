"""
Module xử lý Ollama calls cho chunked pipeline.
Tách riêng khỏi olm.py vì:
  - Chunk trung gian: gọi LLM nhưng KHÔNG ghi file, chỉ trả về text
  - Merge cuối cùng: gọi LLM và ghi file .md

Functions:
  - save/load/clear_checkpoint(): quản lý checkpoint
  - generate_chunk_analysis(): gọi LLM cho 1 chunk/group, trả về text
  - generate_merged_doc():     gọi LLM merge + ghi file .md
  - hierarchical_merge():      merge 2 tầng cho file cực lớn
  - rolling_merge_to_one():    fallback merge từng cặp
  - process_chunked_file():    pipeline đầy đủ: split → analyze chunks → merge
"""

import os
import time
import json
from pathlib import Path
from llm import client as config
from llm.paths import PROJECT_ROOT
from llm.settings import DEBUG_PROMPTS, BAD_RESPONSE_RETRIES
from core.utils import shutdown

from core.config import CHECKPOINT_DIR

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _dump_debug(label: str, content: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = _DEBUG_DIR / f"{label}_{int(time.time())}.txt"
    path.write_text(content, encoding="utf-8")
    print(f"  [debug] {label} → {path.name}")


def _detect_context_mode(content: str) -> str:
    """Xác định mode của connected content dựa trên marker strings."""
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

_MULTIPASS_FUNC_THRESHOLD = 100

# ── Checkpoint System ──────────────────────────────────────────

def save_checkpoint(
    comp_name: str,
    chunk_results: dict[int, str],  # đổi list → dict {chunk_index: result}
    last_index: int,
    failed_indices: list[int] | None = None,
) -> None:
    """Lưu tiến độ sau mỗi chunk thành công (atomic write)."""
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
    Load checkpoint nếu tồn tại.
    Returns (chunk_results, last_index, failed_indices) hoặc None nếu không có.
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
        print(f"  [CHECKPOINT] Resume từ chunk {last_index + 2}")
        if failed_indices:
            print(f"  [CHECKPOINT] Có {len(failed_indices)} chunk lỗi cần retry: {failed_indices}")
        return chunk_results, last_index, failed_indices
    except Exception as e:
        print(f"  [CHECKPOINT] Không load được: {e}")
        return None


def clear_checkpoint(comp_name: str) -> None:
    """Xoá checkpoint sau khi merge thành công."""
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.json"
    if Path(checkpoint_path).exists():
        Path(checkpoint_path).unlink()


# ── Merge Checkpoint ──────────────────────────────────────────

def save_merge_checkpoint(
    comp_name: str,
    stage: str,           # "hierarchical_t1" | "rolling"
    results: list[str],   # kết quả đã merge được đến hiện tại
    last_index: int,      # index cuối đã xử lý thành công
) -> None:
    """Lưu tiến độ merge (atomic write)."""
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
    """Load merge checkpoint nếu tồn tại."""
    checkpoint_path = f"{CHECKPOINT_DIR}/{comp_name}.merge.json"
    if not Path(checkpoint_path).exists():
        return None
    try:
        with open(checkpoint_path, encoding="utf-8") as f:
            state = json.load(f)
        print(f"  [MERGE CHECKPOINT] Resume stage='{state['stage']}' từ index {state['last_index'] + 1}")
        return state
    except Exception as e:
        print(f"  [MERGE CHECKPOINT] Không load được: {e}")
        return None


def clear_merge_checkpoint(comp_name: str) -> None:
    """Xoá merge checkpoint sau khi thành công."""
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
    Gọi Ollama để phân tích 1 chunk hoặc group. Trả về text kết quả (KHÔNG ghi file).

    Args:
        prompt: Prompt cho chunk này.
        chunk_index: Số thứ tự (1-based).
        total_chunks: Tổng số.
        model_name: Tên model Ollama.
        sleep_time: Nghỉ giữa các lần gọi (giây).
        label: Nhãn hiển thị ("Chunk", "Group", "Rolling").
    """
    print(f"    [{label} {chunk_index}/{total_chunks}] Đang xử lý...")

    if DEBUG_PROMPTS:
        _dump_debug(f"chunk_{label.lower()}{chunk_index}_prompt", prompt)

    for attempt in range(1, BAD_RESPONSE_RETRIES + 2):
        try:
            response = config.ollama_chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response["message"]["content"]
            if DEBUG_PROMPTS:
                _dump_debug(f"chunk_{label.lower()}{chunk_index}_response", result)
            result = clean_model_output(result)

            if not result:
                remaining = BAD_RESPONSE_RETRIES + 1 - attempt
                if remaining > 0:
                    print(f"    [{label} {chunk_index}/{total_chunks}] Model trả về rỗng → retry ({remaining} left)")
                    continue
                print(f"    [{label} {chunk_index}/{total_chunks}] Thất bại — model trả về rỗng sau {attempt} lần")
                return None

            lines_count = result.count("\n") + 1
            print(f"    [{label} {chunk_index}/{total_chunks}] Xong — {lines_count} dòng kết quả")

            if sleep_time > 0 and not shutdown.stop_requested:
                print(f"    Đang nghỉ {sleep_time} giây...")
                shutdown.interruptible_sleep(sleep_time)

            return result

        except Exception as e:
            remaining = BAD_RESPONSE_RETRIES + 1 - attempt
            if remaining > 0:
                print(f"    [Lỗi] {label} {chunk_index}/{total_chunks}: {e} → retry ({remaining} left)")
            else:
                print(f"    [Lỗi] {label} {chunk_index}/{total_chunks}: {e} — giving up")
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
    Gọi Ollama với merge prompt, ghi kết quả ra file .md.
    Tự động retry nếu model trả về rỗng hoặc lỗi.

    Args:
        prompt: Merge prompt chứa tất cả chunk results.
        md_filepath: Đường dẫn file .md đầu ra.
        model_name: Tên model Ollama.
        sleep_time: Nghỉ sau khi ghi (giây).
        max_retries: Số lần retry tối đa (mặc định 3).
        retry_delay: Nghỉ giữa các lần retry (giây, mặc định 30).

    Returns:
        Tên file .md (basename) nếu thành công, None nếu thất bại.
    """
    md_filename = os.path.basename(md_filepath)

    for attempt in range(1, max_retries + 1):
        try:
            if attempt == 1:
                print(f"    [Merge] Đang tổng hợp tài liệu...")
            else:
                print(f"    [Merge retry {attempt}/{max_retries}] Đang thử lại...")

            if DEBUG_PROMPTS and attempt == 1:
                _dump_debug(f"merge_prompt_{md_filename}", prompt)

            response = config.ollama_chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
            )

            md_content = response["message"]["content"]
            if DEBUG_PROMPTS:
                _dump_debug(f"merge_response_{md_filename}", md_content)
            md_content = clean_model_output(md_content)

            # Guard: model trả về rỗng (chỉ có thinking block hoặc lỗi)
            if not md_content:
                print(f"    [Merge] Lần {attempt}/{max_retries} — model trả về rỗng")
                if attempt < max_retries:
                    print(f"    Đang nghỉ {retry_delay} giây trước khi retry...")
                    shutdown.interruptible_sleep(retry_delay)
                continue

            md_content = _ensure_events_section(md_content)

            # Sanity check
            if not md_content.startswith("---"):
                print(f"    [Cảnh báo] Output merge không bắt đầu bằng YAML frontmatter!")

            if source_hash:
                md_content = inject_frontmatter_field(md_content, "source_hash", source_hash)

            dir_name = os.path.dirname(md_filepath)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            with open(md_filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            if attempt > 1:
                print(f"    [Merge] Thành công ở lần {attempt}")
            print(f"    [Merge] Đã tạo {md_filename}")

            if sleep_time > 0 and not shutdown.stop_requested:
                print(f"    Đang nghỉ {sleep_time} giây...")
                shutdown.interruptible_sleep(sleep_time)

            return md_filename

        except Exception as e:
            print(f"    [Merge] Lần {attempt}/{max_retries} lỗi: {e}")
            if attempt < max_retries:
                print(f"    Đang nghỉ {retry_delay} giây trước khi retry...")
                shutdown.interruptible_sleep(retry_delay)

    print(f"    [Lỗi] Merge thất bại cho {md_filename} sau {max_retries} lần thử")
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
        print(f"  [MULTIPASS] Resume từ section {ckpt['last_index'] + 2}")
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
            comp_name, display_filepath, deps_json, game_tags_json, external_deps_json, props_json
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
            prompt = build_functions_batch_prompt(comp_name, display_filepath, batch, batch_idx, total_batches)
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
        prompt = build_events_prompt(comp_name, display_filepath, events_json)
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
    print(f"    [Multipass] Đã tạo {md_filename}")

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
    Merge hierarchical 2 tầng:
      Tầng 1: Chia chunk_results thành nhóm group_size, merge mỗi nhóm → intermediate summary
      Tầng 2: Merge tất cả intermediate summaries → final document
    """
    total = len(chunk_results)

    # Tự động tính group_size dựa trên token thực tế
    # Mục tiêu: mỗi nhóm fit trong MERGE_TOKEN_LIMIT
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

    print(f"  [HIERARCHICAL] {total} chunks → {total_groups} nhóm × {group_size}")

    # ── Resume tầng 1 nếu có ──
    merge_ckpt = load_merge_checkpoint(comp_name)
    if merge_ckpt and merge_ckpt["stage"] == "hierarchical_t1":
        intermediate_results = merge_ckpt["results"]
        resume_group_from = merge_ckpt["last_index"]
        print(f"  [HIERARCHICAL] Resume tầng 1 từ nhóm {resume_group_from + 2}")
    else:
        intermediate_results = []
        resume_group_from = -1

    # Tầng 1: merge từng nhóm
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
            print(f"  [HIERARCHICAL] Nhóm {g_idx} thất bại, bỏ qua.")

    if not intermediate_results:
        print("  [HIERARCHICAL] Tất cả nhóm trung gian đều thất bại!")
        return None

    print(f"  [HIERARCHICAL] Tầng 1 xong: {len(intermediate_results)} intermediate summaries")

    # Kiểm tra: tầng 2 có vượt ngưỡng không?
    if estimate_merge_tokens(intermediate_results) > MERGE_TOKEN_LIMIT:
        print("  [HIERARCHICAL] Intermediate results vẫn lớn → rolling merge tầng 2")
        rolled = rolling_merge_to_one(
            comp_name=comp_name,
            display_filepath=display_filepath,
            results=intermediate_results,
            model_name=model_name,
            sleep_time=sleep_time,
        )
        if rolled is None:
            return None # checkpoint đã lưu trong rolling, lần sau resume
        intermediate_results = [rolled]

    # Tầng 2: final merge (legacy text-based prompt)
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
        clear_merge_checkpoint(comp_name)   # chỉ xóa khi chắc chắn thành công
    return result


def rolling_merge_to_one(
    comp_name: str,
    display_filepath: str,
    results: list[str],
    model_name: str,
    sleep_time: int,
) -> str | None:
    """
    Fallback: merge tuần tự từng cặp. Trả về 1 string tổng hợp.
    """
    # ── Resume nếu có ──
    merge_ckpt = load_merge_checkpoint(comp_name)
    if merge_ckpt and merge_ckpt["stage"] == "rolling":
        accumulated = merge_ckpt["results"][0]
        resume_from = merge_ckpt["last_index"]
        print(f"  [ROLLING] Resume từ bước {resume_from + 2}")
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
            # Lưu lại rồi trả về None để caller biết bị gián đoạn
            save_merge_checkpoint(comp_name, "rolling", [accumulated], i - 1)
            print(f"  [ROLLING] Thất bại tại bước {i}, đã lưu checkpoint.")
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
    model_name: str = "qwen3-coder-next:cloud",
    chunk_sleep: int = 10,
    merge_sleep: int = 20,
    sidebar_position: int = 10,
    fresh_start: bool = False,
) -> str | None:
    """
    Pipeline đầy đủ cho file Lua dài với Checkpoint và Hierarchical Merge.

    Args:
        full_refs: Refs của toàn bộ file Lua, dùng làm fallback trong
                   extract_connected_for_chunk() cho các chunk không có local refs.
                   Nếu None: smart fallback không hoạt động (graceful degrade).
        fresh_start: Nếu True, xóa checkpoint cũ trước khi chạy (không resume).
    """
    # Bước 1: Strip dữ liệu số hàng loạt (tile data)
    stripped_code = strip_bulk_data(lua_code)
    original_chars = len(lua_code)
    stripped_chars = len(stripped_code)
    if stripped_chars < original_chars:
        saved = original_chars - stripped_chars
        print(f"  [STRIP] Đã loại bỏ {saved:,} ký tự tile/map data ({saved*100//original_chars}% file)")

    # Bước 2: Tính token budget động (không có connected — CONTEXT_RESERVE trừ bên trong)
    # Dùng CHUNK_PROMPT_TOKEN_LIMIT thay vì PROMPT_TOKEN_LIMIT để per-chunk budget đủ lớn.
    # PROMPT_TOKEN_LIMIT chỉ dùng để trigger chunking, không phải giới hạn kích thước chunk.
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

    # Bước 3: Chia chunks theo token budget
    chunks = split_lua_into_chunks(stripped_code, max_tokens=token_budget)
    total_chunks = len(chunks)
    if total_chunks > 30:
        print(f"  [CHUNKED] Số lượng chunk lớn ({total_chunks} > 30), tăng sleep lên 20s")
        chunk_sleep = 20

    print(f"  [CHUNKED] Chia thành {total_chunks} chunks")

    # ── CHECKPOINT RESUME ──
    if fresh_start:
        clear_checkpoint(comp_name)
        clear_merge_checkpoint(comp_name)
    resume = load_checkpoint(comp_name)
    if resume:
        chunk_results, resume_from, pending_retries = resume
        print(f"  [CHECKPOINT] Đã có {len(chunk_results)} chunk")
    else:
        chunk_results: dict[int, str] = {}
        resume_from = -1
        pending_retries: list[int] = []

    # ── PER-CHUNK CONTEXT SETUP ──
    own_filename = os.path.basename(display_filepath)

    # ── MAIN LOOP ──
    failed_indices: list[int] = list(pending_retries)  # giữ lại lỗi từ lần trước

    for i, chunk_code in enumerate(chunks, 1):
        if shutdown.stop_requested:
            print("  [Hệ thống] Đã dừng chunked pipeline sau chunk hiện tại.")
            break
        # Skip các chunk đã xử lý
        if i - 1 <= resume_from:
            continue
        if i in chunk_results:  # đã có từ checkpoint
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
            print(f"    [CTX] Chunk {i}: {ref_count} refs nhưng không extract được content (require-only, không có function call)")
        else:
            print(f"    [CTX] Chunk {i}: không có external context (chunk độc lập)")

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
                json.loads(result)
                chunk_results[i] = result
                save_checkpoint(comp_name, chunk_results, i - 1, failed_indices)
            except json.JSONDecodeError:
                print(f"    [Cảnh báo] Chunk {i} JSON không hợp lệ, sẽ retry.")
                failed_indices.append(i)
                save_checkpoint(comp_name, chunk_results, i - 1, failed_indices)
        else:
            failed_indices.append(i)
            print(f"    [Cảnh báo] Chunk {i} thất bại.")
            save_checkpoint(comp_name, chunk_results, i - 1, failed_indices)

    # ── RETRY LOOP — chạy sau khi hoàn thành 100/100 ──
    if failed_indices and not shutdown.stop_requested:
        print(f"\n  [RETRY] {len(failed_indices)} chunk thất bại: {failed_indices}")
        print(f"  [RETRY] Bắt đầu retry (tối đa 3 lần, cách nhau 30s)...")

        still_failing: list[int] = []

        for chunk_i in failed_indices:
            if shutdown.stop_requested:
                still_failing.extend(failed_indices[failed_indices.index(chunk_i):])
                break
            chunk_code = chunks[chunk_i - 1]  # chunks list là 0-based

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
                print(f"    [CTX] Chunk {chunk_i} (retry): {ref_count} refs nhưng không extract được content (require-only, không có function call)")
            else:
                print(f"    [CTX] Chunk {chunk_i} (retry): không có external context (chunk độc lập)")

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
                        json.loads(result)
                        chunk_results[chunk_i] = result
                        save_checkpoint(comp_name, chunk_results, total_chunks - 1, still_failing)
                        print(f"    [Retry] Chunk {chunk_i} thành công ở lần {attempt}.")
                        success = True
                        break
                    except json.JSONDecodeError:
                        if attempt < 3:
                            print(f"    [Retry] Lần {attempt} JSON không hợp lệ, thử lại...")
                elif attempt < 3:
                    print(f"    [Retry] Lần {attempt} thất bại, thử lại sau 30s...")

            if not success:
                still_failing.append(chunk_i)
                print(f"    [Retry] Chunk {chunk_i} vẫn thất bại sau 3 lần.")

        failed_indices = still_failing

    # ── USER CONFIRM nếu vẫn còn chunk lỗi ──
    if failed_indices:
        print(f"\n  ⚠️  Vẫn còn {len(failed_indices)} chunk thất bại sau 3 lần retry: {failed_indices}")
        print(f"  Tài liệu sẽ bị thiếu nội dung từ các chunk này.")
        save_checkpoint(comp_name, chunk_results, total_chunks - 1, failed_indices)

        confirm = input("\n  Tiếp tục merge với dữ liệu hiện có? [y/N]: ").strip().lower()
        if confirm != "y":
            print(f"  [DỪNG] Tiến trình đã lưu. Chạy lại để retry {len(failed_indices)} chunk còn lại.")
            return None

        print(f"  [TIẾP TỤC] Merge với {len(chunk_results)}/{total_chunks} chunks.")

    if not chunk_results:
        print(f"  [Lỗi] Không có chunk nào thành công!")
        return None

    # ── PRE-SYNTHESIS — pure Python aggregation, no LLM call ──
    print(f"  [PRE-SYNTHESIS] Aggregating {len(chunk_results)} chunk results...")
    presynthesis, malformed = pre_synthesize(chunk_results)

    if malformed:
        save_checkpoint(comp_name, chunk_results, total_chunks - 1, malformed)
        print(f"  [PRE-SYNTHESIS] {len(malformed)} chunk malformed JSON: {malformed}")
        print(f"  [PRE-SYNTHESIS] Retry các chunk trên rồi chạy lại.")
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
        # Giữ lại chunk checkpoint để kiểm tra lại nếu output LLM bị lỗi.
        # Chỉ xóa merge checkpoint vì nó không còn cần thiết sau khi merge xong.
        clear_merge_checkpoint(comp_name)

    return result_filename
