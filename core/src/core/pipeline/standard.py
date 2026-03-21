import os
import time
from llm import client as config
from rag.docs import clean_model_output


def generate_doc(
    prompt: str,
    md_filepath: str,
    model_name: str = "qwen3-coder-next:cloud",
    sleep_time: int = 0,
    max_retries: int = 3,
    retry_delay: int = 30,
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

            response = config.ollama_chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
            )

            md_content = response["message"]["content"]

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
                print(f"[Cảnh báo] Output của {md_filename} không bắt đầu bằng YAML frontmatter!")

            dirname = os.path.dirname(md_filepath)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

            with open(md_filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            if attempt > 1:
                print(f"  [Retry] Thành công ở lần {attempt}")
            print(f"  Đã tạo {md_filename}")

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
