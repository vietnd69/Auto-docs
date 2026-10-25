"""Harness settings: ``config.toml`` ``[harness]`` section, overridable by env.

Resolution order for every key: env ``MOD_DOC_HARNESS_<KEY>`` → ``config.toml`` → default.
Env values are cast to the type of the default (int, float or str only; never bool).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_DEFAULTS: dict[str, Any] = {
    "baseline_build": "759671",
    "baseline_sha": "b729a8f68d4b635c21279e71723b9627f24c5c38",
    "scripts_dir": "dst-scripts",
    "docs_dir": "dst-api-webdocs/docs",
    "changelog_file": "dst-api-webdocs/change-log.md",
    "state_dir": ".harness",
    "source_branch": "origin/main",
    "page_source_max": 12000,
    "read_max_tokens": 4000,
    "tool_output_max_chars": 24000,
    "proxy_host": "127.0.0.1",
    "proxy_port": 4141,
    "ollama_base_url": "https://ollama.com/v1",
    "model": "qwen3.5:cloud",
    "max_steps": 80,
    "max_tokens": 400000,
    "max_wall_minutes": 30,
    "review_rounds": 3,
    "memory_cap": 200,
    "memory_top_n": 15,
    "escalate_max": 20,
    "parallel": 0,
    "request_timeout": 600.0,
    "opencode_bin": "",
    "provider_id": "dst-proxy",
    "output_token_max": 32000,
    "reflect": 1,
    "mdx_timeout": 30,
}


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        section = tomllib.load(handle).get("harness", {})
    return section if isinstance(section, dict) else {}


def _resolve(key: str, default: Any, toml_values: dict[str, Any]) -> Any:
    env_value = os.environ.get(f"MOD_DOC_HARNESS_{key.upper()}")
    if env_value is not None:
        return type(default)(env_value)
    return toml_values.get(key, default)


@dataclass(frozen=True)
class Settings:
    """Typed, immutable view over the harness configuration."""

    root: Path
    values: dict[str, Any]

    def get_str(self, key: str) -> str:
        return str(self.values[key])

    def get_int(self, key: str) -> int:
        return int(self.values[key])

    def get_float(self, key: str) -> float:
        return float(self.values[key])

    def path(self, key: str) -> Path:
        """Resolve a configured directory/file relative to the project root."""
        value = Path(self.get_str(key))
        return value if value.is_absolute() else self.root / value

    @property
    def scripts_dir(self) -> Path:
        return self.path("scripts_dir")

    @property
    def docs_dir(self) -> Path:
        return self.path("docs_dir")

    @property
    def state_dir(self) -> Path:
        return self.path("state_dir")


def load_settings(root: Path | None = None) -> Settings:
    """Build settings for ``root`` (defaults to the repository root)."""
    base = root or Path(os.environ.get("MOD_DOC_HARNESS_ROOT", PROJECT_ROOT))
    toml_values = _load_toml(base / "config.toml")
    values = {key: _resolve(key, default, toml_values) for key, default in _DEFAULTS.items()}
    return Settings(root=base, values=values)


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Process-wide settings singleton."""
    return load_settings()
