"""Test helpers shared by conftest and test modules."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "lua"


def git(repo: Path, *args: str) -> str:
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@e",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@e",
        GIT_AUTHOR_DATE="2026-10-23T00:00:00Z",
        GIT_COMMITTER_DATE="2026-10-23T00:00:00Z",
    )
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def write_sources(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


BASE_FILES = {
    "components/health.lua": "components__health.lua",
    "stategraphs/SGpig.lua": "stategraphs__SGpig.lua",
    "strings_small.lua": "strings_small.lua",
    "components/ambient.lua": "world__ambient.lua",
}
