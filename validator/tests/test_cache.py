"""Unit tests for CacheManager."""

import pytest
from pathlib import Path

from validator.content.cache import CacheManager


def test_create_and_read(tmp_path):
    """create() writes content, read() retrieves it."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    cache.create("batch_1", "# Hello\nContent here.\n")
    assert cache.read("batch_1") == "# Hello\nContent here.\n"


def test_write_overwrites(tmp_path):
    """write() overwrites existing cache content."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    cache.create("chunk", "original")
    cache.write("chunk", "updated")
    assert cache.read("chunk") == "updated"


def test_read_missing_raises(tmp_path):
    """read() on non-existent cache id raises FileNotFoundError."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    with pytest.raises(FileNotFoundError):
        cache.read("nonexistent")


def test_exists(tmp_path):
    """exists() returns True for created, False for missing."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    assert cache.exists("x") is False
    cache.create("x", "data")
    assert cache.exists("x") is True


def test_list_ids(tmp_path):
    """list_ids() returns sorted cache ids."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    cache.create("batch_2", "b")
    cache.create("batch_1", "a")
    cache.create("section_1", "c")
    ids = cache.list_ids()
    assert ids == ["batch_1", "batch_2", "section_1"]


def test_cleanup_removes_dir(tmp_path):
    """cleanup() removes the cache directory entirely."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    cache.create("x", "data")
    assert cache.cache_dir.exists()
    cache.cleanup()
    assert not cache.cache_dir.exists()


def test_cache_dir_property(tmp_path):
    """cache_dir returns the directory path."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "my_cache")
    assert cache.cache_dir == tmp_path / "my_cache"


def test_create_returns_path(tmp_path):
    """create() returns the cache file path."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    path = cache.create("batch_1", "content")
    assert isinstance(path, Path)
    assert path.exists()
    assert path.name == "batch_1.md"


def test_cache_id_sanitization(tmp_path):
    """Cache ids with slashes/backslashes are sanitised."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    cache.create("sec/batch\\1", "data")
    assert cache.read("sec/batch\\1") == "data"
    # File name should not contain slashes
    files = list((tmp_path / "cache").glob("*.md"))
    assert len(files) == 1
    assert "/" not in files[0].name
    assert "\\" not in files[0].name


def test_default_cache_dir_uses_stem():
    """Default cache dir is based on md file stem (no custom dir)."""
    cache = CacheManager("path/to/myfile.md")
    assert "myfile" in cache.cache_dir.name
    # Cleanup
    cache.cleanup()


def test_multiple_creates_and_reads(tmp_path):
    """Multiple cache entries coexist."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    cache.create("a", "alpha")
    cache.create("b", "beta")
    cache.create("c", "gamma")
    assert cache.read("a") == "alpha"
    assert cache.read("b") == "beta"
    assert cache.read("c") == "gamma"


def test_utf8_content(tmp_path):
    """Cache handles UTF-8 content correctly."""
    cache = CacheManager("test.md", cache_dir=tmp_path / "cache")
    content = "## Tổng quan\nNội dung tiếng Việt 🎉\n"
    cache.create("utf8", content)
    assert cache.read("utf8") == content
