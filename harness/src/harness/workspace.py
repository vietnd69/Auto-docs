"""Shared runtime context: settings, source repository and state directory layout."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from harness.config import Settings, settings
from harness.gitsource import GitSource


@dataclass(frozen=True)
class Workspace:
    """Everything a tool needs: where source, docs and harness state live."""

    settings: Settings
    git: GitSource
    rev: str

    def _state(self, *parts: str) -> Path:
        path = self.settings.state_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def plan_path(self) -> Path:
        return self._state("doc-plan.json")

    @property
    def sync_path(self) -> Path:
        return self._state("sync-state.json")

    @property
    def regression_path(self) -> Path:
        return self._state("regression.json")

    def ledger_path(self, page_id: str) -> Path:
        return self._state("ledger", f"{_slug(page_id)}.jsonl")

    def notes_path(self, page_id: str) -> Path:
        return self._state("notes", f"{_slug(page_id)}.md")

    def draft_path(self, page_path: str) -> Path:
        return self._state("drafts", page_path)

    def library_dir(self, domain: str) -> Path:
        return self._state("library", domain, "x").parent

    def queue_path(self, job_set: str) -> Path:
        return self._state("queue", f"{_slug(job_set)}.jsonl")

    def report_path(self, name: str) -> Path:
        return self._state("reports", name)

    def cache_path(self, name: str) -> Path:
        return self._state("cache", name)


def _slug(text: str) -> str:
    return text.replace("/", "__").replace("\\\\", "__").replace("..", "_")


def make_workspace(cfg: Settings | None = None, rev: str | None = None) -> Workspace:
    cfg = cfg or settings()
    return Workspace(
        settings=cfg,
        git=GitSource(cfg.scripts_dir),
        rev=rev or os.environ.get("MOD_DOC_HARNESS_REV", "HEAD"),
    )


@lru_cache(maxsize=1)
def workspace() -> Workspace:
    """Process-wide workspace (MCP server, CLI)."""
    return make_workspace()
