"""Which source commit each published page reflects (drives incremental updates)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from harness.timeutil import now_iso
from harness.workspace import Workspace


@dataclass
class PageSync:
    sha: str
    build: str
    updated: str
    path: str = ""
    symbols: dict[str, str] = field(default_factory=dict)  # qualname → body hash


class SyncState:
    def __init__(self, ws: Workspace) -> None:
        self.path = ws.sync_path
        raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.pages: dict[str, PageSync] = {k: PageSync(**v) for k, v in raw.get("pages", {}).items()}
        self.head: str = raw.get("head", "")

    def mark(self, page_id: str, sha: str, build: str, symbols: dict[str, str], path: str) -> None:
        self.pages[page_id] = PageSync(sha, build, now_iso(), path, symbols)

    def forget(self, page_id: str) -> None:
        self.pages.pop(page_id, None)

    def save(self) -> None:
        data = {"head": self.head, "pages": {k: vars(v) for k, v in sorted(self.pages.items())}}
        self.path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
