"""Evidence-backed review findings with stable IDs (goal G4; kills review oscillation).

A finding is accepted only when its quote really occurs in the cited source lines. A
resolved finding re-opens only with *different* evidence, so a reviewer cannot raise
the same point again in new words.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field

from harness.safepath import normalize_rel
from harness.textutil import short_hash
from harness.timeutil import now_iso
from harness.workspace import Workspace

MAX_EVIDENCE_LINES = 200
STATUSES = ("open", "resolved", "rejected")


@dataclass
class Evidence:
    file: str
    line_start: int
    line_end: int
    quote: str

    def key(self) -> str:
        return f"{self.file}:{self.line_start}-{self.line_end}:{_squash(self.quote)}"


@dataclass
class Finding:
    id: str
    page_id: str
    symbol: str
    field: str
    claim: str
    evidence: Evidence
    status: str = "open"
    created: str = dc_field(default_factory=now_iso)
    updated: str = dc_field(default_factory=now_iso)
    history: list[str] = dc_field(default_factory=list)  # evidence keys seen so far
    note: str = ""


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def finding_id(page_id: str, symbol: str, field_name: str) -> str:
    return short_hash(f"{page_id}|{symbol}|{field_name.lower().strip()}", 10)


class Ledger:
    """Per-page finding store backed by a JSONL file."""

    def __init__(self, ws: Workspace, page_id: str) -> None:
        self.ws = ws
        self.page_id = page_id
        self.path = ws.ledger_path(page_id)
        self.items: dict[str, Finding] = self._load()

    def _load(self) -> dict[str, Finding]:
        if not self.path.exists():
            return {}
        items: dict[str, Finding] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                raw = json.loads(line)
                raw["evidence"] = Evidence(**raw["evidence"])
                finding = Finding(**raw)
                items[finding.id] = finding
        return items

    def _save(self) -> None:
        lines = [json.dumps(asdict(f), ensure_ascii=False) for f in self.items.values()]
        self.path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def verify_evidence(self, ev: Evidence) -> str | None:
        """Return an error message, or ``None`` when the quote matches the cited lines."""
        if ev.line_end < ev.line_start or ev.line_end - ev.line_start > MAX_EVIDENCE_LINES:
            return f"evidence range must be 1..{MAX_EVIDENCE_LINES} lines"
        if len(_squash(ev.quote)) < 3:
            return "quote too short"
        try:
            source = self.ws.git.show(self.ws.rev, normalize_rel(ev.file))
        except Exception as exc:  # GitError or bad path
            return f"cannot read {ev.file}: {exc}"
        window = "\n".join(source.splitlines()[ev.line_start - 1 : ev.line_end])
        if _squash(ev.quote) not in _squash(window):
            return f"quote not found in {ev.file} L{ev.line_start}-{ev.line_end}"
        return None

    def add(self, symbol: str, field_name: str, claim: str, ev: Evidence) -> tuple[bool, str]:
        """Record a finding. Returns (accepted, message)."""
        error = self.verify_evidence(ev)
        if error:
            return False, f"rejected: {error}"
        fid = finding_id(self.page_id, symbol, field_name)
        existing = self.items.get(fid)
        if existing is not None and existing.status == "open":
            existing.claim, existing.evidence, existing.updated = claim, ev, now_iso()
            if ev.key() not in existing.history:
                existing.history.append(ev.key())
            self._save()
            return True, f"updated open finding {fid}"
        if existing is not None and ev.key() in existing.history:
            return False, f"rejected: finding {fid} was already {existing.status} with this same evidence"
        finding = existing or Finding(fid, self.page_id, symbol, field_name, claim, ev)
        finding.claim, finding.evidence, finding.status, finding.updated = claim, ev, "open", now_iso()
        finding.history.append(ev.key())
        self.items[fid] = finding
        self._save()
        return True, f"{'reopened' if existing else 'opened'} finding {fid}"

    def resolve(self, fid: str, note: str, status: str = "resolved") -> str:
        if status not in STATUSES[1:]:
            return f"status must be one of {STATUSES[1:]}"
        finding = self.items.get(fid)
        if finding is None:
            return f"unknown finding {fid}"
        finding.status, finding.note, finding.updated = status, note, now_iso()
        self._save()
        return f"{fid} → {status}"

    def open_findings(self) -> list[Finding]:
        return [f for f in self.items.values() if f.status == "open"]

    def render(self, status: str = "") -> str:
        rows = [
            f"{f.id} [{f.status}] {f.symbol}.{f.field}: {f.claim} "
            f"(evidence {f.evidence.file} L{f.evidence.line_start}-{f.evidence.line_end})"
            for f in self.items.values()
            if not status or f.status == status
        ]
        return "\n".join(rows) or "no findings"
