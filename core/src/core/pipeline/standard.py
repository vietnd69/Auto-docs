import os
import re
import time
from pathlib import Path
from llm import client as config
from llm.paths import PROJECT_ROOT
from llm.settings import DEBUG_PROMPTS
from rag.docs import clean_model_output, inject_frontmatter_field
from validator.format.section_filler import _REQUIRED_HEADINGS, rewrite_document

_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _dump_debug(label: str, content: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = _DEBUG_DIR / f"{label}_{int(time.time())}.txt"
    path.write_text(content, encoding="utf-8")
    print(f"  [debug] {label} → {path.name}")


def _check_missing_sections(md_content: str) -> list[str]:
    return [h for h in _REQUIRED_HEADINGS if not re.search(r'^' + re.escape(h), md_content, re.MULTILINE)]


def generate_doc(
    prompt: str,
    md_filepath: str,
    source_hash: str = "",
    lua_filepath: str = "",
    model_name: str = "qwen3-coder-next:cloud",
    sleep_time: int = 0,
    max_retries: int = 3,
    retry_delay: int = 30,
    max_section_retries: int = 2,
) -> str | None:
    """
    Gọi Ollama để tạo tài liệu từ prompt, ghi kết quả ra file .md.
    Tự động retry khi LLM thất bại (không phải rate limit).

    Args:
        prompt: Prompt đầy đủ để gửi cho LLM.
        md_filepath: Đường dẫn đầy đủ tới file .md cần ghi.
        model_name: Tên model Ollama để sử dụng.
        sleep_time: Thời gian nghỉ (giây) sau khi xử lý xong. Mặc định 0.
        max_retries: Số lần retry tối đa (mặc định 3).
        retry_delay: Nghỉ giữa các lần retry (giây, mặc định 30).

    Returns:
        Tên file .md (basename) nếu thành công, None nếu thất bại.
    """
    md_filename = os.path.basename(md_filepath)

    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f"  [Retry {attempt}/{max_retries}] {md_filename}...")

            if DEBUG_PROMPTS:
                _dump_debug(f"standard_prompt_{md_filename}", prompt)

            response = config.ollama_chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
            )

            md_content = response["message"]["content"]
            if DEBUG_PROMPTS:
                _dump_debug(f"standard_response_{md_filename}", md_content)

            # Làm sạch output (thinking block + code fence)
            md_content = clean_model_output(md_content)

            # Guard: model trả về rỗng (chỉ có thinking block hoặc lỗi)
            if not md_content:
                print(f"  [Lỗi] Lần {attempt}/{max_retries} — model trả về rỗng cho {md_filename}")
                if attempt < max_retries:
                    print(f"  Đang nghỉ {retry_delay} giây trước khi retry...")
                    time.sleep(retry_delay)
                continue

            # Kiểm tra sanity: output phải bắt đầu bằng YAML frontmatter
            if not md_content.startswith("---"):
                if attempt < max_retries:
                    print(
                        f"  [Bad response] Lần {attempt}/{max_retries} — output của {md_filename} "
                        f"không bắt đầu bằng YAML frontmatter, retry..."
                    )
                    time.sleep(retry_delay)
                    continue
                print(
                    f"  [Cảnh báo] Output của {md_filename} không bắt đầu bằng YAML frontmatter "
                    f"sau {max_retries} lần thử — ghi file và tiếp tục"
                )

            if source_hash:
                md_content = inject_frontmatter_field(md_content, "source_hash", source_hash)

            dirname = os.path.dirname(md_filepath)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

            with open(md_filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            if attempt > 1:
                print(f"  [Retry] Thành công ở lần {attempt}")
            print(f"  Đã tạo {md_filename}")

            # Kiểm tra sections sau khi gen lần đầu
            if lua_filepath:
                missing = _check_missing_sections(md_content)
                if missing:
                    print(f"  [sections] Thiếu {len(missing)} section(s): {', '.join(missing)}")
                    for sec_attempt in range(1, max_section_retries + 1):
                        print(f"  [sections] Rewrite lần {sec_attempt}/{max_section_retries}...")
                        ok = rewrite_document(md_filepath, missing, lua_filepath, model=model_name, original_prompt=prompt)
                        if not ok:
                            print(f"  [sections] Rewrite thất bại lần {sec_attempt}")
                            continue
                        new_content = Path(md_filepath).read_text(encoding="utf-8")
                        missing = _check_missing_sections(new_content)
                        if not missing:
                            print(f"  [sections] Đủ sections sau rewrite lần {sec_attempt}")
                            break
                        print(f"  [sections] Vẫn thiếu: {', '.join(missing)}")
                    if missing:
                        print(f"  [sections] Cảnh báo: vẫn thiếu {', '.join(missing)} sau {max_section_retries} lần rewrite")

            # Nghỉ giữa các lần gọi
            if sleep_time > 0:
                print(f"  Đang nghỉ {sleep_time} giây...")
                time.sleep(sleep_time)

            return md_filename

        except Exception as e:
            # Rate limit đã được config.ollama_chat xử lý (account rotation).
            # Lỗi đến đây là non-rate-limit: timeout, connection reset, v.v.
            print(f"  [Lỗi] Lần {attempt}/{max_retries} — {md_filename}: {e}")
            if attempt < max_retries:
                print(f"  Đang nghỉ {retry_delay} giây trước khi retry...")
                time.sleep(retry_delay)

    print(f"  [Lỗi] {md_filename} thất bại sau {max_retries} lần thử — skip")
    return None
