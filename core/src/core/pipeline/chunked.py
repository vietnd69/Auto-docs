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
from core.utils import shutdown

from core.config import CHECKPOINT_DIR


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
from prompts.chunked import (
    build_chunk_prompt,
    build_merge_prompt,
    build_intermediate_merge_prompt,
    _build_merge_prompt_legacy,
)
from prompts.pre_synthesis import pre_synthesize

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
    try:
        print(f"    [{label} {chunk_index}/{total_chunks}] Đang xử lý...")

        response = config.ollama_chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )

        result = response["message"]["content"]
        result = clean_model_output(result)

        if not result:
            print(f"    [{label} {chunk_index}/{total_chunks}] Thất bại — model trả về rỗng")
            return None

        lines_count = result.count("\n") + 1
        print(f"    [{label} {chunk_index}/{total_chunks}] Xong — {lines_count} dòng kết quả")

        if sleep_time > 0 and not shutdown.stop_requested:
            print(f"    Đang nghỉ {sleep_time} giây...")
            shutdown.interruptible_sleep(sleep_time)

        return result

    except Exception as e:
        print(f"    [Lỗi] {label} {chunk_index}/{total_chunks}: {e}")
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

            response = config.ollama_chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
            )

            md_content = response["message"]["content"]
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
) -> str | None:
    """
    Pipeline đầy đủ cho file Lua dài với Checkpoint và Hierarchical Merge.

    Args:
        full_refs: Refs của toàn bộ file Lua, dùng làm fallback trong
                   extract_connected_for_chunk() cho các chunk không có local refs.
                   Nếu None: smart fallback không hoạt động (graceful degrade).
    """
    # Bước 1: Strip dữ liệu số hàng loạt (tile data)
    stripped_code = strip_bulk_data(lua_code)
    original_chars = len(lua_code)
    stripped_chars = len(stripped_code)
    if stripped_chars < original_chars:
        saved = original_chars - stripped_chars
        print(f"  [STRIP] Đã loại bỏ {saved:,} ký tự tile/map data ({saved*100//original_chars}% file)")

    # Bước 2: Tính token budget động (không có connected — CONTEXT_RESERVE trừ bên trong)
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
    )

    # Bước 3: Chia chunks theo token budget
    chunks = split_lua_into_chunks(stripped_code, max_tokens=token_budget)
    total_chunks = len(chunks)
    if total_chunks > 30:
        print(f"  [CHUNKED] Số lượng chunk lớn ({total_chunks} > 30), tăng sleep lên 20s")
        chunk_sleep = 20

    print(f"  [CHUNKED] Chia thành {total_chunks} chunks")

    # ── CHECKPOINT RESUME ──
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

    # ── MERGE — always direct, PreSynthesisResult is small ──
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
