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
import config

# ── Checkpoint System ──────────────────────────────────────────

CHECKPOINT_DIR = config.CHECKPOINT_DIR

from get_docs import (
    clean_model_output,
    extract_lua_references,
    safe_read_lua,
    compute_source_hash,
    format_connected_section,
)
from rag_get_fnc_content import extract_connected_content
from chunked import (
    needs_chunking, 
    split_lua_into_chunks, 
    strip_bulk_data, 
    calc_token_budget,
    estimate_merge_tokens,
    MERGE_TOKEN_LIMIT
)
from chunked_prompt import (
    build_chunk_prompt, 
    build_merge_prompt,
    build_intermediate_merge_prompt
)

# ── Checkpoint System ──────────────────────────────────────────

CHECKPOINT_DIR = ".cache/chunked_checkpoints"

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

        lines_count = result.count("\n") + 1
        print(f"    [{label} {chunk_index}/{total_chunks}] Xong — {lines_count} dòng kết quả")

        if sleep_time > 0:
            print(f"    Đang nghỉ {sleep_time} giây...")
            time.sleep(sleep_time)

        return result

    except Exception as e:
        print(f"    [Lỗi] {label} {chunk_index}/{total_chunks}: {e}")
        return None


def generate_merged_doc(
    prompt: str,
    md_filepath: str,
    model_name: str = "qwen3-coder-next:cloud",
    sleep_time: int = 10,
) -> str | None:
    """
    Gọi Ollama với merge prompt, ghi kết quả ra file .md.

    Args:
        prompt: Merge prompt chứa tất cả chunk results.
        md_filepath: Đường dẫn file .md đầu ra.
        model_name: Tên model Ollama.
        sleep_time: Nghỉ sau khi ghi (giây).

    Returns:
        Tên file .md (basename) nếu thành công, None nếu thất bại.
    """
    md_filename = os.path.basename(md_filepath)

    try:
        print(f"    [Merge] Đang tổng hợp tài liệu...")

        response = config.ollama_chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )

        md_content = response["message"]["content"]
        md_content = clean_model_output(md_content)

        # Sanity check
        if not md_content.startswith("---"):
            print(f"    [Cảnh báo] Output merge không bắt đầu bằng YAML frontmatter!")

        dir_name = os.path.dirname(md_filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"    [Merge] Đã tạo {md_filename}")

        if sleep_time > 0:
            print(f"    Đang nghỉ {sleep_time} giây...")
            time.sleep(sleep_time)

        return md_filename

    except Exception as e:
        print(f"    [Lỗi] Merge thất bại cho {md_filename}: {e}")
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

    # Xoá merge checkpoint trước khi final merge (để final stage không bị dính t1)
    clear_merge_checkpoint(comp_name)

    # Tầng 2: final merge
    merge_prompt = build_merge_prompt(
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

    return generate_merged_doc(
        prompt=merge_prompt,
        md_filepath=md_filepath,
        model_name=model_name,
        sleep_time=sleep_time,
    )


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
    """
    # Bước 1: Strip dữ liệu số hàng loạt (tile data)
    stripped_code = strip_bulk_data(lua_code)
    original_chars = len(lua_code)
    stripped_chars = len(stripped_code)
    if stripped_chars < original_chars:
        saved = original_chars - stripped_chars
        print(f"  [STRIP] Đã loại bỏ {saved:,} ký tự tile/map data ({saved*100//original_chars}% file)")

    # Bước 2: Tính token budget động
    token_budget = calc_token_budget(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        connected_section=connected_section,
        connected_content=connected_content,
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

    # ── MAIN LOOP ──
    failed_indices: list[int] = list(pending_retries)  # giữ lại lỗi từ lần trước

    for i, chunk_code in enumerate(chunks, 1):
        # Skip các chunk đã xử lý
        if i - 1 <= resume_from:
            continue
        if i in chunk_results:  # đã có từ checkpoint
            continue

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
            connected_section=connected_section,
            connected_content=connected_content,
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
            chunk_results[i] = result
            save_checkpoint(comp_name, chunk_results, i - 1, failed_indices)
        else:
            failed_indices.append(i)
            print(f"    [Cảnh báo] Chunk {i} thất bại.")
            save_checkpoint(comp_name, chunk_results, i - 1, failed_indices)

    # ── RETRY LOOP — chạy sau khi hoàn thành 100/100 ──
    if failed_indices:
        print(f"\n  [RETRY] {len(failed_indices)} chunk thất bại: {failed_indices}")
        print(f"  [RETRY] Bắt đầu retry (tối đa 3 lần, cách nhau 30s)...")

        still_failing: list[int] = []

        for chunk_i in failed_indices:
            chunk_code = chunks[chunk_i - 1]  # chunks list là 0-based
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
                connected_section=connected_section,
                connected_content=connected_content,
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
                    chunk_results[chunk_i] = result
                    save_checkpoint(comp_name, chunk_results, total_chunks - 1, still_failing)
                    print(f"    [Retry] Chunk {chunk_i} thành công ở lần {attempt}.")
                    success = True
                    break
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

    # ── MERGE ──
    # Sắp xếp kết quả theo thứ tự chunk gốc
    ordered_results = [chunk_results[i] for i in sorted(chunk_results.keys())]

    if not ordered_results:
        print(f"  [Lỗi] Không có chunk nào thành công!")
        return None

    total_merge_tokens = estimate_merge_tokens(ordered_results)
    use_hierarchical = (total_merge_tokens > MERGE_TOKEN_LIMIT) or (len(ordered_results) > 30)

    result_filename = None
    if use_hierarchical:
        token_info = f"{total_merge_tokens} tokens" if total_merge_tokens > 0 else f"{len(ordered_results)} chunks"
        print(f"  [MERGE STRATEGY] Hierarchical ({token_info} > ngưỡng)")
        result_filename = hierarchical_merge(
            comp_name=comp_name,
            comp_title=comp_title,
            display_filepath=display_filepath,
            chunk_results=ordered_results,
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
        print(f"  [MERGE STRATEGY] Direct merge")
        merge_prompt = build_merge_prompt(
            comp_name=comp_name,
            comp_title=comp_title,
            display_filepath=display_filepath,
            chunk_results=ordered_results,
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
            model_name=model_name,
            sleep_time=merge_sleep,
        )

    # Thêm warning vào file nếu có chunk bị bỏ
    if result_filename and failed_indices:
        with open(md_filepath, "a", encoding="utf-8") as f:
            f.write(
                f"\n\n***\n> ⚠️ **Incomplete documentation**: chunks {failed_indices} "
                f"failed after 3 retries and were skipped.\n"
            )

    if result_filename:
        clear_checkpoint(comp_name)
        clear_merge_checkpoint(comp_name)

    return result_filename


# === Cho phép chạy độc lập để test ===
if __name__ == "__main__":
    import sys
    from get_tree import generate_slim_tree
    from datetime import datetime

    if len(sys.argv) < 2:
        print("Usage: python chunked_olm.py <lua_file> [output.md]")
        print("Ví dụ: python chunked_olm.py ./dst-scripts/components/combat.lua ./test_chunked.md")
        sys.exit(1)

    filepath = sys.argv[1]
    md_output = sys.argv[2] if len(sys.argv) > 2 else "./test_chunked.md"

    lua_code = safe_read_lua(filepath)
    if lua_code is None:
        print(f"[Lỗi] Không đọc được: {filepath}")
        sys.exit(1)

    total_lines = lua_code.count("\n") + 1
    print(f"File: {filepath} ({total_lines} dòng)")

    if not needs_chunking(lua_code):
        print(f"[Thông báo] File chỉ có {total_lines} dòng, không cần chunking.")
        print("Dùng pipeline thường (prompt.py + olm.py) cho file này.")
        sys.exit(0)

    # Chuẩn bị metadata
    filename = os.path.basename(filepath)
    comp_name = filename.replace(".lua", "")
    comp_title = comp_name.replace("_", " ").title()
    display_filepath = filepath.replace("./dst-scripts", ".").replace("\\", "/")
    source_hash = compute_source_hash(lua_code)
    lua_refs = extract_lua_references(lua_code, filename)
    connected_section = format_connected_section(lua_refs)
    connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
    file_tree = generate_slim_tree("./dst-scripts", max_depth=3)
    today_date = datetime.now().strftime("%Y-%m-%d")

    result = process_chunked_file(
        comp_name=comp_name,
        comp_title=comp_title,
        display_filepath=display_filepath,
        lua_code=lua_code,
        connected_section=connected_section,
        connected_content=connected_content,
        source_hash=source_hash,
        md_filepath=md_output,
        file_tree=file_tree,
        today_date=today_date,
        version="714014",
        category_type="component",
        model_name="qwen3-coder-next:cloud",
        chunk_sleep=10,
        merge_sleep=20,
    )

    if result:
        print(f"\n[OK] Tạo tài liệu thành công: {result}")
    else:
        print(f"\n[THẤT BẠI] Không tạo được tài liệu.")
