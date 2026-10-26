"""Materialise the Harness² editable tree into OpenCode's native layout.

Source of truth: ``.opencode/harness/`` (Harness² c1..c8 surface):

    systemprompt.md, guardrails.md, LongTermMEMORY.md, tool_descriptions/tool_guidance.md
    skills/<name>/SKILL.md     → .opencode/skills/<name>/SKILL.md
    sub_agents/<name>/AGENT.md → .opencode/agent/<name>.md
    plugin/<name>.ts           → .opencode/plugin/<name>.ts
    scripts/<name>.py          → .opencode/scripts/<name>.py

Always-on files are referenced from ``opencode.json`` ``instructions``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ALWAYS_ON = (
    "systemprompt.md",
    "guardrails.md",
    "LongTermMEMORY.md",
    "tool_descriptions/tool_guidance.md",
)
_MANAGED = ("skills", "plugin", "scripts")
_MANIFEST = ".harness-generated.json"


def tree_dir(opencode_dir: Path) -> Path:
    return opencode_dir / "harness"


def _targets(tree: Path, opencode_dir: Path) -> dict[Path, Path]:
    pairs: dict[Path, Path] = {}
    for src in sorted(tree.rglob("*")):
        if not src.is_file() or src.name == "README.md":
            continue
        rel = src.relative_to(tree).as_posix()
        parts = rel.split("/")
        if parts[0] == "sub_agents" and len(parts) == 3 and parts[2] == "AGENT.md":
            pairs[src] = opencode_dir / "agent" / f"{parts[1]}.md"
        elif parts[0] in _MANAGED:
            pairs[src] = opencode_dir / rel
    return pairs


def materialise(opencode_dir: Path) -> list[str]:
    """Regenerate OpenCode files from the tree; returns the written paths (relative)."""
    tree = tree_dir(opencode_dir)
    manifest_path = opencode_dir / _MANIFEST
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    for rel in previous:
        stale = opencode_dir / rel
        if stale.is_file():
            stale.unlink()
    written: list[str] = []
    for src, dst in _targets(tree, opencode_dir).items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(dst.relative_to(opencode_dir).as_posix())
    manifest_path.write_text(json.dumps(sorted(written), indent=1) + "\n", encoding="utf-8")
    _sync_instructions(opencode_dir)
    return written


def _sync_instructions(opencode_dir: Path) -> None:
    config_path = opencode_dir / "opencode.json"
    if not config_path.exists():
        return
    config = json.loads(config_path.read_text(encoding="utf-8"))
    present = [f".opencode/harness/{rel}" for rel in ALWAYS_ON if (tree_dir(opencode_dir) / rel).exists()]
    if config.get("instructions") != present:
        config["instructions"] = present
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def replace_tree(opencode_dir: Path, candidate: Path) -> Path:
    """Swap in a candidate tree; returns the backup directory of the previous tree."""
    tree = tree_dir(opencode_dir)
    backup = opencode_dir.parent / ".harness" / "backups" / "harness-tree"
    if backup.exists():
        shutil.rmtree(backup)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(tree, backup)
    memory = (
        (tree / "LongTermMEMORY.md").read_text(encoding="utf-8")
        if (tree / "LongTermMEMORY.md").exists()
        else ""
    )
    try:
        shutil.rmtree(tree)
        shutil.copytree(candidate, tree)
        if memory:  # memory is rendered from the library, never taken from a candidate
            (tree / "LongTermMEMORY.md").write_text(memory, encoding="utf-8")
        materialise(opencode_dir)
    except Exception:  # restore live configuration on any failed installation
        if tree.exists():
            shutil.rmtree(tree)
        shutil.copytree(backup, tree)
        materialise(opencode_dir)
        raise
    return backup


def restore_tree(opencode_dir: Path, backup: Path) -> None:
    tree = tree_dir(opencode_dir)
    shutil.rmtree(tree)
    shutil.copytree(backup, tree)
    materialise(opencode_dir)
