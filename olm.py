import os
import time
import config
from get_docs import clean_model_output


def generate_doc(
    prompt: str,
    md_filepath: str,
    model_name: str = "qwen3-coder-next:cloud",
    sleep_time: int = 0,
) -> str | None:
    """
    Gọi Ollama để tạo tài liệu từ prompt, ghi kết quả ra file .md.

    Args:
        prompt: Prompt đầy đủ để gửi cho LLM.
        md_filepath: Đường dẫn đầy đủ tới file .md cần ghi.
        model_name: Tên model Ollama để sử dụng.
        sleep_time: Thời gian nghỉ (giây) sau khi xử lý xong. Mặc định 0.

    Returns:
        Tên file .md (basename) nếu thành công, None nếu thất bại.
    """
    md_filename = os.path.basename(md_filepath)

    try:
        response = config.ollama_chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )

        md_content = response["message"]["content"]

        # Làm sạch output (thinking block + code fence)
        md_content = clean_model_output(md_content)

        # Kiểm tra sanity: output phải bắt đầu bằng YAML frontmatter
        if not md_content.startswith("---"):
            print(f"[Cảnh báo] Output của {md_filename} không bắt đầu bằng YAML frontmatter!")

        dirname = os.path.dirname(md_filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"  Đã tạo {md_filename}")

        # Nghỉ giữa các lần gọi
        if sleep_time > 0:
            print(f"  Đang nghỉ {sleep_time} giây...")
            time.sleep(sleep_time)

        return md_filename

    except Exception as e:
        print(f"  [Lỗi] Không thể xử lý {md_filename}: {e}")
        return None