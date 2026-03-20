from llm.paths import PROJECT_ROOT, BASE_LUA_DIR, BASE_DOCS_DIR
from pathlib import Path

def test_project_root_exists():
    assert PROJECT_ROOT.exists()

def test_base_lua_dir_is_absolute():
    assert Path(BASE_LUA_DIR).is_absolute()
    assert "dst-scripts" in BASE_LUA_DIR

def test_base_docs_dir_is_absolute():
    assert Path(BASE_DOCS_DIR).is_absolute()
    assert "dst-api-webdocs" in BASE_DOCS_DIR
