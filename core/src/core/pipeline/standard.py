import os
import re
import time
from pathlib import Path
from llm import client as config
from llm.paths import PROJECT_ROOT
from llm.settings import DEBUG_PROMPTS, MAIN_THINK
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
    Call Ollama to generate documentation from a prompt and write the result to a .md file.
    Automatically retries when the LLM fails (not rate-limit errors).

    Args:
        prompt: Full prompt to send to the LLM.
        md_filepath: Full path to the .md file to write.
        model_name: Ollama model name to use.
        sleep_time: Rest time (seconds) after processing is done. Default 0.
        max_retries: Maximum number of retries (default 3).
        retry_delay: Sleep between retries (seconds, default 30).

    Returns:
        .md file name (basename) if successful, None if failed.
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
                think=bool(MAIN_THINK),
            )

            md_content = response["message"]["content"]
            if DEBUG_PROMPTS:
                _dump_debug(f"standard_response_{md_filename}", md_content)

            # Clean up output (thinking block + code fence)
            md_content = clean_model_output(md_content)

            # Guard: model returned empty (only thinking block or error)
            if not md_content:
                print(f"  [Error] Attempt {attempt}/{max_retries} — model returned empty for {md_filename}")
                if attempt < max_retries:
                    print(f"  Resting {retry_delay} seconds before retry...")
                    time.sleep(retry_delay)
                continue

            # Sanity check: output must start with YAML frontmatter
            if not md_content.startswith("---"):
                if attempt < max_retries:
                    print(
                        f"  [Bad response] Attempt {attempt}/{max_retries} — output for {md_filename} "
                        f"does not start with YAML frontmatter, retrying..."
                    )
                    time.sleep(retry_delay)
                    continue
                print(
                    f"  [Warning] Output for {md_filename} does not start with YAML frontmatter "
                    f"after {max_retries} attempts — writing file and continuing"
                )

            if source_hash:
                md_content = inject_frontmatter_field(md_content, "source_hash", source_hash)

            dirname = os.path.dirname(md_filepath)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

            with open(md_filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            if attempt > 1:
                print(f"  [Retry] Succeeded on attempt {attempt}")
            print(f"  Created {md_filename}")

            # Check sections after first generation
            if lua_filepath:
                missing = _check_missing_sections(md_content)
                if missing:
                    print(f"  [sections] Missing {len(missing)} section(s): {', '.join(missing)}")
                    for sec_attempt in range(1, max_section_retries + 1):
                        print(f"  [sections] Rewrite attempt {sec_attempt}/{max_section_retries}...")
                        ok = rewrite_document(md_filepath, missing, lua_filepath, model=model_name, original_prompt=prompt)
                        if not ok:
                            print(f"  [sections] Rewrite failed on attempt {sec_attempt}")
                            continue
                        new_content = Path(md_filepath).read_text(encoding="utf-8")
                        missing = _check_missing_sections(new_content)
                        if not missing:
                            print(f"  [sections] All sections present after rewrite attempt {sec_attempt}")
                            break
                        print(f"  [sections] Still missing: {', '.join(missing)}")
                    if missing:
                        print(f"  [sections] Warning: still missing {', '.join(missing)} after {max_section_retries} rewrite attempts")

            # Rest between calls
            if sleep_time > 0:
                print(f"  Resting {sleep_time} seconds...")
                time.sleep(sleep_time)

            return md_filename

        except Exception as e:
            # Rate limit errors are handled by config.ollama_chat (account rotation).
            # Errors reaching here are non-rate-limit: timeout, connection reset, etc.
            print(f"  [Error] Attempt {attempt}/{max_retries} — {md_filename}: {e}")
            if attempt < max_retries:
                print(f"  Resting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)

    print(f"  [Error] {md_filename} failed after {max_retries} attempts — skipping")
    return None
