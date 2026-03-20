from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3].absolute()
BASE_LUA_DIR = str(PROJECT_ROOT / "dst-scripts")
BASE_DOCS_DIR = str(PROJECT_ROOT / "dst-api-webdocs" / "docs")
