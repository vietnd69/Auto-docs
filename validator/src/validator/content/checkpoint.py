"""Checkpoint system for validator pipeline — enables resume after rate-limit failures.

Checkpoints are always written (every run), but only read when --resume is passed.
This means if a crash happens on a normal run, the next run just needs --resume.

File locations:
  - Per-file:  .cache/validator_checkpoints/<md_stem>.json
  - Batch:     .cache/validator_checkpoints/_batch_<hash>.json
"""

import hashlib
import json
import os
from pathlib import Path

from llm.paths import PROJECT_ROOT

_CHECKPOINT_DIR = PROJECT_ROOT / ".cache" / "validator_checkpoints"


def _checkpoint_path(md_filepath: str) -> Path:
    stem = Path(md_filepath).stem
    # Include path hash to avoid collisions between same-named files in different dirs
    h = hashlib.md5(md_filepath.encode()).hexdigest()[:8]
    return _CHECKPOINT_DIR / f"{stem}_{h}.json"


def _batch_checkpoint_path(target: str) -> Path:
    h = hashlib.md5(target.encode()).hexdigest()[:8]
    return _CHECKPOINT_DIR / f"_batch_{h}.json"


def save_validator_checkpoint(
    md_filepath: str,
    cache_dir: Path,
    completed_sections: set[int],
    total_iterations: int,
    all_issues: list[str],
) -> None:
    """Save validator checkpoint after completing a section (atomic write)."""
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        content_hash = hashlib.md5(
            Path(md_filepath).read_bytes()
        ).hexdigest()[:12]
    except Exception:
        content_hash = ""
    path = _checkpoint_path(md_filepath)
    tmp = path.with_suffix(".tmp")
    data = {
        "version": 1,
        "md_filepath": md_filepath,
        "content_hash": content_hash,
        "cache_dir": str(cache_dir),
        "completed_sections": sorted(completed_sections),
        "total_iterations": total_iterations,
        "all_issues": all_issues,
    }
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_validator_checkpoint(md_filepath: str) -> dict | None:
    """Load checkpoint for a file. Returns None if not found, invalid, or stale."""
    path = _checkpoint_path(md_filepath)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            return None
        cache_dir = Path(data.get("cache_dir", ""))
        if not cache_dir.exists():
            return None
        # Invalidate if md file content changed since checkpoint was written
        saved_hash = data.get("content_hash", "")
        if saved_hash:
            current_hash = hashlib.md5(Path(md_filepath).read_bytes()).hexdigest()[:12]
            if current_hash != saved_hash:
                print(f"  [checkpoint] File content changed since last run — ignoring stale checkpoint")
                return None
        return data
    except Exception:
        return None


def save_batch_checkpoint(target: str, completed_files: list[str]) -> None:
    """Save batch-level checkpoint tracking which files are done."""
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = _batch_checkpoint_path(target)
    tmp = path.with_suffix(".tmp")
    data = {
        "version": 1,
        "target": target,
        "completed_files": completed_files,
    }
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_batch_checkpoint(target: str) -> list[str]:
    """Load batch checkpoint. Returns list of completed file path strings."""
    path = _batch_checkpoint_path(target)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            return []
        return data.get("completed_files", [])
    except Exception:
        return []
