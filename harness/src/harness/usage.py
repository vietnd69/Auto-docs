"""Conservative cost comparison from an isolated OpenCode database, all agents included.

Rates pinned from the 2026-10-26 trial (USD per million tokens). Unknown models or
incomplete assistant turns fail closed. This is an estimate, not a provider invoice.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def regression_cost(database: Path) -> float | None:
    if not database.is_file():
        return None
    total = 0.0
    seen = False
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            for (raw,) in conn.execute("SELECT data FROM message"):
                message = json.loads(raw)
                if message.get("role") != "assistant":
                    continue
                seen = True
                if message.get("finish") not in ("stop", "tool-calls") or message.get("error"):
                    return None
                provider, model = message.get("providerID"), message.get("modelID")
                if provider == "deepseek" and model == "deepseek-flash":
                    rates = (0.30, 0.006, 1.20)
                elif provider == "dst-proxy" and model in ("reviewer", "planner"):
                    # Alias may fall back to DeepSeek: use the larger rate per category.
                    rates = (0.30, 0.014, 1.20)
                else:
                    return None
                tokens = message["tokens"]
                values = [
                    tokens["input"],
                    tokens["output"],
                    tokens.get("reasoning", 0),
                    tokens.get("cache", {}).get("read", 0),
                    tokens.get("cache", {}).get("write", 0),
                ]
                if any(not isinstance(v, (int, float)) or v < 0 for v in values):
                    return None
                inp, out, reasoning, cached, write = values
                total += ((inp + write) * rates[0] + cached * rates[1] + (out + reasoning) * rates[2]) / 1e6
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        return None
    return total if seen and total > 0 else None
