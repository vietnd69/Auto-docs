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
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError
