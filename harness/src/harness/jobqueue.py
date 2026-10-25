"""Resumable job queue (JSONL) for generate/update runs over many pages."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from harness.timeutil import now_iso

PENDING, RUNNING = "pending", "running"
DONE_STATUSES = frozenset({"PASS", "FAIL", "BUDGET_EXHAUSTED", "ESCALATED", "ERROR", "SKIPPED"})


@dataclass
class Job:
    id: str
    kind: str  # generate | update
    page_id: str
    from_rev: str = ""
    to_rev: str = ""
    status: str = PENDING
    attempts: int = 0
    message: str = ""
    updated: str = field(default_factory=now_iso)


class JobQueue:
    """Thread-safe queue persisted after every state change."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.jobs: dict[str, Job] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    job = Job(**json.loads(line))
                    if job.status == RUNNING:  # interrupted run → retry
                        job.status = PENDING
                    self.jobs[job.id] = job

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(json.dumps(asdict(j), ensure_ascii=False) for j in self.jobs.values())
        self.path.write_text(body + ("\n" if body else ""), encoding="utf-8")

    def add(self, job: Job) -> bool:
        """Add a job unless one with the same id already exists."""
        with self._lock:
            if job.id in self.jobs:
                return False
            self.jobs[job.id] = job
            self._save()
            return True

    def claim(self) -> Job | None:
        with self._lock:
            for job in self.jobs.values():
                if job.status == PENDING:
                    job.status, job.attempts, job.updated = RUNNING, job.attempts + 1, now_iso()
                    self._save()
                    return job
            return None

    def finish(self, job_id: str, status: str, message: str = "") -> None:
        with self._lock:
            job = self.jobs[job_id]
            job.status, job.message, job.updated = status, message[:2000], now_iso()
            self._save()

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for job in self.jobs.values():
            result[job.status] = result.get(job.status, 0) + 1
        return result
