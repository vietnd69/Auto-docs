"""Changelog entry built from symbol-level diffs plus Steam patch notes."""

from __future__ import annotations

from pathlib import Path

from harness.builds import Build
from harness.diffing import FileDiff

_LABELS = {
    "added": "Added",
    "removed": "Removed",
    "renamed": "Renamed",
    "signature_changed": "Signature changed",
    "body_changed": "Behaviour changed",
}


def build_entry(build: Build, previous: str, diffs: list[FileDiff], max_files: int = 60) -> str:
    """Markdown section for one build (newest first in the changelog)."""
    lines = [f"## Build {build.number} — {build.date}", ""]
    if build.title:
        lines += [f"**{build.title}**", ""]
    lines += [f"Source diff: `{previous[:10]}` → `{build.sha[:10]}` ({len(diffs)} Lua files).", ""]
    api = [fd for fd in diffs if any(k != "body_changed" for k in fd.symbols)]
    if api:
        lines += ["### API changes", ""]
        for fd in api[:max_files]:
            changes = "; ".join(
                f"{_LABELS[k]}: {', '.join(f'`{q}`' for q in v[:8])}{'…' if len(v) > 8 else ''}"
                for k, v in fd.symbols.items()
                if k != "body_changed"
            )
            lines.append(f"- `{fd.path}` — {changes}")
        if len(api) > max_files:
            lines.append(f"- …and {len(api) - max_files} more files")
        lines.append("")
    behaviour = [fd.path for fd in diffs if set(fd.symbols) == {"body_changed"}]
    if behaviour:
        shown = ", ".join(f"`{p}`" for p in behaviour[:max_files])
        lines += ["### Behaviour-only changes", "", shown + ("…" if len(behaviour) > max_files else ""), ""]
    if build.notes:
        lines += [
            "<details>",
            "<summary>Steam patch notes</summary>",
            "",
            _escape_mdx(build.notes),
            "",
            "</details>",
            "",
        ]
    return "\n".join(lines)


def _escape_mdx(text: str) -> str:
    return text.replace("{", "\\{").replace("}", "\\}").replace("<", "&lt;")


def prepend_entry(path: Path, entry: str) -> None:
    """Insert ``entry`` after the changelog's frontmatter/title block."""
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Change log\n"
    lines = existing.split("\n")
    insert_at = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    lines[insert_at:insert_at] = [entry.rstrip("\n"), ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
