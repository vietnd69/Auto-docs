# llm/src/llm/router.py
"""
Load-balancing router for Ollama API keys.

Tracks call counts per key in .cache/key_usage.json.
Selects the least-loaded key within a rolling time window.
"""
import json
import time
from pathlib import Path

from llm.paths import PROJECT_ROOT

USAGE_CACHE = PROJECT_ROOT / ".cache" / "key_usage.json"
WINDOW_SECONDS = 3600  # 1-hour rolling window
RATE_LIMIT_COOLDOWN = 5 * 3600  # 5 giờ cooldown sau khi bị 429


def _load_cache() -> dict:
    if USAGE_CACHE.exists():
        try:
            return json.loads(USAGE_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(data: dict) -> None:
    USAGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _prune(timestamps: list[float], cutoff: float) -> list[float]:
    return [t for t in timestamps if t >= cutoff]


def record_call(key_index: int) -> None:
    """Ghi nhận 1 API call thành công cho key."""
    cache = _load_cache()
    key = str(key_index)
    if key not in cache:
        cache[key] = {"total": 0, "recent": []}
    cache[key]["total"] += 1
    now = time.time()
    cache[key]["recent"].append(now)
    cache[key]["recent"] = _prune(cache[key]["recent"], now - WINDOW_SECONDS)
    _save_cache(cache)


def mark_rate_limited(key_index: int) -> None:
    """Ghi nhận key bị rate limit (429). Sẽ không dùng lại trong 5h."""
    cache = _load_cache()
    key = str(key_index)
    if key not in cache:
        cache[key] = {"total": 0, "recent": []}
    cache[key]["rate_limited_at"] = time.time()
    _save_cache(cache)


def get_rate_limited(num_keys: int) -> set[int]:
    """Trả về set các key index đang bị rate limit (chưa hết 5h cooldown)."""
    cache = _load_cache()
    now = time.time()
    limited: set[int] = set()
    for i in range(num_keys):
        entry = cache.get(str(i), {})
        limited_at = entry.get("rate_limited_at")
        if limited_at is not None and (now - limited_at) < RATE_LIMIT_COOLDOWN:
            limited.add(i)
    return limited


def select_key(num_keys: int, exclude: set[int]) -> int:
    """
    Chọn key ít tải nhất.

    Tự động loại key đang bị rate limit (cooldown 5h từ cache).
    Param exclude: các key cần bỏ qua thêm (vd: đã thử trong round hiện tại).

    Thuật toán: key có ít call nhất trong rolling window (1h).
    Nếu bằng nhau → chọn key có ít total calls nhất.
    """
    cache = _load_cache()
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    blocked = exclude | get_rate_limited(num_keys)

    best_idx = -1
    best_recent = float("inf")
    best_total = float("inf")

    for i in range(num_keys):
        if i in blocked:
            continue
        entry = cache.get(str(i), {"total": 0, "recent": []})
        recent_count = len(_prune(entry.get("recent", []), cutoff))
        total_count = entry.get("total", 0)

        if recent_count < best_recent or (
            recent_count == best_recent and total_count < best_total
        ):
            best_idx = i
            best_recent = recent_count
            best_total = total_count

    # -1 = không còn key khả dụng
    return best_idx


def get_stats() -> dict:
    """Trả về thống kê usage để log/debug."""
    cache = _load_cache()
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    stats = {}
    for key, entry in cache.items():
        recent = _prune(entry.get("recent", []), cutoff)
        limited_at = entry.get("rate_limited_at")
        remaining = None
        if limited_at is not None:
            elapsed = now - limited_at
            if elapsed < RATE_LIMIT_COOLDOWN:
                remaining = RATE_LIMIT_COOLDOWN - elapsed
        stats[int(key)] = {
            "total": entry.get("total", 0),
            "recent_1h": len(recent),
            "rate_limited": remaining is not None,
            "cooldown_remaining_m": round(remaining / 60) if remaining else 0,
        }
    return stats
