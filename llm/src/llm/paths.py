from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3].absolute()
BASE_LUA_DIR = str(PROJECT_ROOT / "dst-scripts")
BASE_DOCS_DIR = str(PROJECT_ROOT / "dst-api-webdocs" / "docs")
COMPRESSION_CACHE_DIR = str(PROJECT_ROOT / ".cache" / "compression_cache")
DATA_DIR = str(PROJECT_ROOT / "data")


def read_build_version(fallback: str = "unknown") -> str:
    """Read current build version from data/version_log.txt ('now version: XXXXXX')."""
    version_log = PROJECT_ROOT / "data" / "version_log.txt"
    try:
        for line in version_log.read_text(encoding="utf-8").splitlines():
            if line.startswith("now version:"):
                return line.split(":", 1)[1].strip()
    except FileNotFoundError:
        pass
    return fallback
