# llm/tests/test_router.py
"""Tests for the load-balancing router with token-based tracking."""
import json
import time
from unittest.mock import patch, MagicMock

import pytest

import llm.router as router
from llm.router import (
    record_call,
    select_key,
    get_stats,
    mark_rate_limited,
    get_rate_limited,
    _prune_token_log,
    _tokens_in_window,
    WINDOW_SECONDS,
    RATE_LIMIT_COOLDOWN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache(*entries):
    """Build a cache dict from (key_index, token_log, total_tokens, recent, total) tuples."""
    data = {}
    for item in entries:
        idx, token_log, total_tokens, recent, total = item
        data[str(idx)] = {
            "total": total,
            "recent": recent,
            "token_log": token_log,
            "total_tokens": total_tokens,
        }
    return data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestPruneTokenLog:
    def test_keeps_entries_within_window(self):
        now = time.time()
        log = [{"ts": now - 100, "count": 1000}, {"ts": now - 200, "count": 500}]
        result = _prune_token_log(log, now - WINDOW_SECONDS)
        assert len(result) == 2

    def test_prunes_old_entries(self):
        now = time.time()
        log = [
            {"ts": now - WINDOW_SECONDS - 1, "count": 9999},  # expired
            {"ts": now - 10, "count": 100},  # fresh
        ]
        result = _prune_token_log(log, now - WINDOW_SECONDS)
        assert result == [{"ts": now - 10, "count": 100}]

    def test_empty_log(self):
        assert _prune_token_log([], time.time() - 100) == []


class TestTokensInWindow:
    def test_sums_tokens_within_window(self):
        now = time.time()
        log = [
            {"ts": now - 10, "count": 1000},
            {"ts": now - 20, "count": 500},
            {"ts": now - WINDOW_SECONDS - 1, "count": 99999},  # expired
        ]
        assert _tokens_in_window(log, now - WINDOW_SECONDS) == 1500

    def test_empty_returns_zero(self):
        assert _tokens_in_window([], time.time()) == 0

    def test_all_expired_returns_zero(self):
        now = time.time()
        log = [{"ts": now - WINDOW_SECONDS - 100, "count": 9999}]
        assert _tokens_in_window(log, now - WINDOW_SECONDS) == 0


# ---------------------------------------------------------------------------
# record_call
# ---------------------------------------------------------------------------

class TestRecordCall:
    def test_creates_new_entry(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)

        record_call(0, 1234)

        data = json.loads(cache_path.read_text())
        entry = data["0"]
        assert entry["total"] == 1
        assert entry["total_tokens"] == 1234
        assert len(entry["recent"]) == 1
        assert len(entry["token_log"]) == 1
        assert entry["token_log"][0]["count"] == 1234

    def test_accumulates_tokens(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)

        record_call(0, 1000)
        record_call(0, 2000)

        data = json.loads(cache_path.read_text())
        entry = data["0"]
        assert entry["total"] == 2
        assert entry["total_tokens"] == 3000
        assert len(entry["token_log"]) == 2

    def test_does_not_reset_total_tokens_on_existing_entry(self, tmp_path, monkeypatch):
        """Upgrading an old cache entry (no total_tokens) should default to 0 then add."""
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)
        # Simulate an old cache entry missing token_log / total_tokens
        cache_path.write_text(json.dumps({"0": {"total": 5, "recent": []}}))

        record_call(0, 500)

        data = json.loads(cache_path.read_text())
        entry = data["0"]
        assert entry["total"] == 6
        assert entry["total_tokens"] == 500
        assert entry["token_log"][0]["count"] == 500

    def test_prunes_old_token_log_entries(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)

        old_ts = time.time() - WINDOW_SECONDS - 10
        cache_path.write_text(json.dumps({
            "0": {
                "total": 1,
                "recent": [],
                "token_log": [{"ts": old_ts, "count": 9999}],
                "total_tokens": 9999,
            }
        }))

        record_call(0, 100)

        data = json.loads(cache_path.read_text())
        # old expired entry should be pruned; only new entry remains
        assert len(data["0"]["token_log"]) == 1
        assert data["0"]["token_log"][0]["count"] == 100
        # total_tokens is cumulative — not affected by pruning
        assert data["0"]["total_tokens"] == 10099

    def test_multiple_keys(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)

        record_call(0, 1000)
        record_call(1, 2000)

        data = json.loads(cache_path.read_text())
        assert data["0"]["total_tokens"] == 1000
        assert data["1"]["total_tokens"] == 2000


# ---------------------------------------------------------------------------
# select_key
# ---------------------------------------------------------------------------

class TestSelectKey:
    def _write_cache(self, tmp_path, monkeypatch, data):
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)
        cache_path.write_text(json.dumps(data))

    def test_selects_key_with_fewest_tokens_1h(self, tmp_path, monkeypatch):
        now = time.time()
        data = {
            "0": {"total": 10, "recent": [], "token_log": [{"ts": now - 10, "count": 50000}], "total_tokens": 50000},
            "1": {"total": 5,  "recent": [], "token_log": [{"ts": now - 10, "count": 10000}], "total_tokens": 10000},
        }
        self._write_cache(tmp_path, monkeypatch, data)
        assert select_key(2, set()) == 1

    def test_tiebreaker_uses_total_tokens(self, tmp_path, monkeypatch):
        now = time.time()
        # Both have same tokens_1h=0 (no fresh log entries), but different total_tokens
        data = {
            "0": {"total": 10, "recent": [], "token_log": [], "total_tokens": 999999},
            "1": {"total": 5,  "recent": [], "token_log": [], "total_tokens": 1000},
        }
        self._write_cache(tmp_path, monkeypatch, data)
        assert select_key(2, set()) == 1

    def test_new_account_no_cache_entry_selected_first(self, tmp_path, monkeypatch):
        now = time.time()
        # Key 0 has some token usage; key 1 has no entry at all → gets 0/0
        data = {
            "0": {"total": 5, "recent": [], "token_log": [{"ts": now - 10, "count": 1000}], "total_tokens": 1000},
        }
        self._write_cache(tmp_path, monkeypatch, data)
        assert select_key(2, set()) == 1  # key 1 has tokens_1h=0 → wins

    def test_exclude_blocks_key(self, tmp_path, monkeypatch):
        now = time.time()
        data = {
            "0": {"total": 1, "recent": [], "token_log": [{"ts": now - 10, "count": 1}], "total_tokens": 1},
            "1": {"total": 5, "recent": [], "token_log": [{"ts": now - 10, "count": 50000}], "total_tokens": 50000},
        }
        self._write_cache(tmp_path, monkeypatch, data)
        # Exclude key 0 (the lighter one) → should pick key 1
        assert select_key(2, {0}) == 1

    def test_returns_minus_one_when_all_excluded(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)
        assert select_key(2, {0, 1}) == -1

    def test_expired_token_log_not_counted(self, tmp_path, monkeypatch):
        now = time.time()
        old_ts = now - WINDOW_SECONDS - 100
        data = {
            "0": {
                "total": 10,
                "recent": [],
                "token_log": [{"ts": old_ts, "count": 99999}],  # expired
                "total_tokens": 99999,
            },
            "1": {
                "total": 10,
                "recent": [],
                "token_log": [{"ts": now - 10, "count": 500}],  # fresh but smaller
                "total_tokens": 500,
            },
        }
        self._write_cache(tmp_path, monkeypatch, data)
        # Key 0: tokens_1h=0 (expired), key 1: tokens_1h=500 → key 0 wins
        assert select_key(2, set()) == 0

    def test_rate_limited_key_skipped(self, tmp_path, monkeypatch):
        now = time.time()
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)
        data = {
            "0": {
                "total": 1,
                "recent": [],
                "token_log": [{"ts": now - 10, "count": 1}],
                "total_tokens": 1,
                "rate_limited_at": now - 60,  # recently rate-limited, still in cooldown
            },
            "1": {
                "total": 10,
                "recent": [],
                "token_log": [{"ts": now - 10, "count": 99999}],
                "total_tokens": 99999,
            },
        }
        cache_path.write_text(json.dumps(data))
        # Key 0 is rate-limited → must pick key 1 despite heavier load
        assert select_key(2, set()) == 1


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_includes_token_fields(self, tmp_path, monkeypatch):
        now = time.time()
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)
        cache_path.write_text(json.dumps({
            "0": {
                "total": 3,
                "recent": [now - 10],
                "token_log": [{"ts": now - 10, "count": 4000}],
                "total_tokens": 12000,
            }
        }))

        stats = get_stats()
        entry = stats[0]

        # New fields
        assert entry["tokens_1h"] == 4000
        assert entry["total_tokens"] == 12000

        # Existing fields preserved
        assert entry["total"] == 3
        assert entry["recent_1h"] == 1
        assert entry["rate_limited"] is False
        assert entry["cooldown_remaining_m"] == 0

    def test_tokens_1h_excludes_expired(self, tmp_path, monkeypatch):
        now = time.time()
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)
        old_ts = now - WINDOW_SECONDS - 100
        cache_path.write_text(json.dumps({
            "0": {
                "total": 2,
                "recent": [],
                "token_log": [
                    {"ts": old_ts, "count": 9999},  # expired
                    {"ts": now - 10, "count": 200},  # fresh
                ],
                "total_tokens": 10199,
            }
        }))

        stats = get_stats()
        assert stats[0]["tokens_1h"] == 200
        assert stats[0]["total_tokens"] == 10199

    def test_empty_cache_returns_empty_stats(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)
        assert get_stats() == {}

    def test_missing_token_fields_default_to_zero(self, tmp_path, monkeypatch):
        """Old cache entries without token_log/total_tokens should report zeros."""
        now = time.time()
        cache_path = tmp_path / "key_usage.json"
        monkeypatch.setattr(router, "USAGE_CACHE", cache_path)
        cache_path.write_text(json.dumps({
            "0": {"total": 5, "recent": [now - 10]}
        }))

        stats = get_stats()
        assert stats[0]["tokens_1h"] == 0
        assert stats[0]["total_tokens"] == 0
