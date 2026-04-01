"""Cache file management for the content validation loop.

Creates temporary cache files from md content before review. The reviewer reads
from cache, the writer edits cache files, and the loop continues on cache until
approved. Only then is the original file updated with the final cache content.

Cache files are retained after completion for debugging (manual cleanup).
"""

import time
from pathlib import Path

from llm.paths import PROJECT_ROOT

_CACHE_ROOT = PROJECT_ROOT / ".cache" / "validator"


class CacheManager:
    """Manages cache files for the review loop.

    Each CacheManager instance creates a unique directory under
    ``PROJECT_ROOT/.cache/validator/<md_stem>_<timestamp>/``.
    Batch/section content is stored as individual files inside that directory.
    """

    def __init__(self, md_filepath: str, cache_dir: Path | None = None) -> None:
        md_stem = Path(md_filepath).stem
        if cache_dir is not None:
            self._dir = cache_dir
        else:
            ts = int(time.time())
            self._dir = _CACHE_ROOT / f"{md_stem}_{ts}"
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        """Return the cache directory path."""
        return self._dir

    def _path(self, cache_id: str) -> Path:
        """Return the file path for a cache id."""
        # Sanitise cache_id to a safe filename
        safe = cache_id.replace("/", "_").replace("\\", "_")
        return self._dir / f"{safe}.md"

    def create(self, cache_id: str, content: str) -> Path:
        """Create a cache file with initial content. Returns the file path."""
        path = self._path(cache_id)
        path.write_text(content, encoding="utf-8")
        return path

    def read(self, cache_id: str) -> str:
        """Read content from a cache file. Raises FileNotFoundError if missing."""
        return self._path(cache_id).read_text(encoding="utf-8")

    def write(self, cache_id: str, content: str) -> None:
        """Overwrite a cache file with new content."""
        self._path(cache_id).write_text(content, encoding="utf-8")

    def exists(self, cache_id: str) -> bool:
        """Check whether a cache file exists."""
        return self._path(cache_id).exists()

    def list_ids(self) -> list[str]:
        """Return all cache ids (without .md extension)."""
        return [p.stem for p in sorted(self._dir.glob("*.md"))]

    def cleanup(self) -> None:
        """Remove all cache files and the cache directory."""
        import shutil
        if self._dir.exists():
            shutil.rmtree(self._dir)
