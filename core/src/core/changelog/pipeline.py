# core/src/core/changelog/pipeline.py
"""
Changelog generation pipeline.

Usage:
    .venv/Scripts/python -m core.changelog
    .venv/Scripts/python -m core.changelog --dry-run
"""
import argparse
import json
import signal
import sys
from pathlib import Path

from core.changelog.prompts import build_changelog_prompt
from core.utils import shutdown
from llm.client import ollama_chat
from llm.paths import DATA_DIR, PROJECT_ROOT
from llm.settings import MODEL_UPDATE
from validator.format.autofix import autofix_file, get_mdx_errors

CHANGELOG_PATH: Path = PROJECT_ROOT / "dst-api-webdocs" / "change-log.md"
_CHANGELOG_HEADER = "# DST API Changelog\n"


def _build_frontmatter(new_ver: str, date: str) -> str:
    return (
        "---\n"
        "id: change-log\n"
        "title: DST API Changelog\n"
        "description: Build-by-build changelog for the DST Lua API documentation.\n"
        "tags: [changelog]\n"
        "sidebar_position: 1\n"
        f"last_updated: {date}\n"
        f"build_version: {new_ver}\n"
        "change_status: updated\n"
        "---"
    )


def _strip_frontmatter_and_header(text: str) -> str:
    """Remove YAML frontmatter block and the # DST API Changelog header."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    text = text.lstrip("\n")
    return text.removeprefix(_CHANGELOG_HEADER).lstrip("\n")


def load_diff_report() -> dict | None:
    path = Path(DATA_DIR) / "diff_report.json"
    if not path.exists():
        print(f"[Lỗi] Không tìm thấy {path}. Hãy chạy watcher trước.")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_changelog_entry(report: dict) -> str | None:
    old_ver = report["version"]["old"]
    new_ver = report["version"]["new"]
    date = report["date"]
    changes = report["changes"]

    prompt = build_changelog_prompt(
        old_ver=old_ver,
        new_ver=new_ver,
        date=date,
        changes=changes,
    )

    try:
        response = ollama_chat(
            MODEL_UPDATE,
            [{"role": "user", "content": prompt}],
            think=False,
        )
    except Exception as e:
        print(f"[Changelog] Cảnh báo: LLM call thất bại — {e}")
        return None

    content = response["message"]["content"].strip()
    if not content:
        print("[Changelog] Cảnh báo: LLM trả về empty response.")
        return None
    return content


def prepend_to_changelog(entry: str, changelog_path: Path, *, new_ver: str, date: str) -> None:
    frontmatter = _build_frontmatter(new_ver, date)
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
        body = _strip_frontmatter_and_header(existing)
    else:
        changelog_path.parent.mkdir(parents=True, exist_ok=True)
        body = ""
    changelog_path.write_text(
        f"{frontmatter}\n\n{_CHANGELOG_HEADER}\n{entry.strip()}\n\n{body}".rstrip() + "\n",
        encoding="utf-8",
    )


def main() -> None:
    def _handle_sigint(signum, frame):
        if not shutdown.stop_requested:
            print("\n[Changelog] Ctrl+C — stopping.")
            shutdown.request_stop()
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_sigint)

    parser = argparse.ArgumentParser(description="Generate changelog entry from diff_report.json")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only, do not call LLM or write file")
    args = parser.parse_args()

    report = load_diff_report()
    if report is None:
        sys.exit(1)

    new_ver = report["version"]["new"]

    if args.dry_run:
        prompt = build_changelog_prompt(
            old_ver=report["version"]["old"],
            new_ver=new_ver,
            date=report["date"],
            changes=report["changes"],
        )
        print(prompt)
        return

    # Idempotency check
    if CHANGELOG_PATH.exists():
        existing = CHANGELOG_PATH.read_text(encoding="utf-8")
        if f"## Build {new_ver}" in existing:
            print(f"[Changelog] Already logged: Build {new_ver}. Dùng --force để ghi đè.")
            return

    entry = build_changelog_entry(report)
    if entry is None:
        sys.exit(1)

    prepend_to_changelog(entry, CHANGELOG_PATH, new_ver=new_ver, date=report["date"])

    # Only check for real MDX compilation errors (validate_all returns false positives
    # for doc-format rules like required headings that don't apply to the changelog)
    mdx_errors_before = get_mdx_errors(str(CHANGELOG_PATH))
    if mdx_errors_before:
        fix_result = autofix_file(str(CHANGELOG_PATH))
        if fix_result.changes:
            print(f"[Changelog] MDX autofix: {len(fix_result.changes)} fix(es) applied")
        remaining = get_mdx_errors(str(CHANGELOG_PATH))
        if remaining:
            print(f"[Changelog] Cảnh báo: {len(remaining)} MDX error(s) còn lại — kiểm tra thủ công")

    print(f"[Changelog] Done: {CHANGELOG_PATH}")
