# core/src/core/changelog/pipeline.py
"""
Changelog generation pipeline.

Usage:
    .venv/Scripts/python -m core.changelog
    .venv/Scripts/python -m core.changelog --dry-run
"""
import json
import signal
import sys
from pathlib import Path

from llm.paths import DATA_DIR, PROJECT_ROOT


def load_diff_report() -> dict | None:
    path = Path(DATA_DIR) / "diff_report.json"
    if not path.exists():
        print(f"[Lỗi] Không tìm thấy {path}. Hãy chạy watcher trước.")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_changelog_entry(report: dict) -> str | None:
    raise NotImplementedError


def prepend_to_changelog(entry: str, changelog_path: Path) -> None:
    header = "# DST API Changelog\n"
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
        # Strip existing header to avoid duplication
        body = existing.removeprefix(header).lstrip("\n")
    else:
        changelog_path.parent.mkdir(parents=True, exist_ok=True)
        body = ""
    changelog_path.write_text(
        f"{header}\n{entry.strip()}\n\n{body}".rstrip() + "\n",
        encoding="utf-8",
    )


def main() -> None:
    raise NotImplementedError
