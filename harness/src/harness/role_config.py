"""Role routing shared by the CLI sessions and the OpenCode config generator."""

from __future__ import annotations

import os
from typing import Any

from dotenv import dotenv_values

from harness.config import Settings


def credentials(cfg: Settings) -> dict[str, str]:
    """Load project secrets without changing process globals; environment wins."""
    env = {k: v for k, v in dotenv_values(cfg.root / ".env").items() if v is not None}
    env.update(os.environ)
    if not env.get("ANTHROPIC_API_KEY"):
        env["ANTHROPIC_API_KEY"] = env.get("CLAUDE_API_KEY", "")
    return env


def role_models(cfg: Settings) -> dict[str, str]:
    claude = f"anthropic/{cfg.get_str('claude_model')}"
    return {
        "orchestrator": f"deepseek/{cfg.get_str('deepseek_model')}",
        "reviewer": "dst-proxy/reviewer",
        "writer": f"deepseek/{cfg.get_str('deepseek_model')}",
        "planner": "dst-proxy/planner",
        "reflector": "dst-proxy/reflector",
        "writer-experimental": "dst-proxy/writer-experimental",
        "writer-escalation": claude,
    }


def runtime_config(cfg: Settings) -> dict[str, Any]:
    """No literal secrets: OpenCode resolves API keys from the child environment."""
    roles = role_models(cfg)
    return {
        "model": roles["orchestrator"],
        "small_model": roles["writer"],
        "agent": {role: {"model": model} for role, model in roles.items()},
        "provider": {
            "anthropic": {"options": {"apiKey": "{env:ANTHROPIC_API_KEY}"}},
            "deepseek": {
                "options": {
                    "baseURL": cfg.get_str("deepseek_base_url"),
                    "apiKey": "{env:DEEPSEEK_API_KEY}",
                },
                "models": {cfg.get_str("deepseek_model"): {"tool_call": True}},
            },
            "dst-proxy": {
                "npm": "@ai-sdk/openai-compatible",
                "options": {
                    "baseURL": f"http://127.0.0.1:{cfg.get_int('proxy_port')}/v1",
                    "headers": {"X-Harness-Job": "{env:HARNESS_JOB}"},
                },
                "models": {
                    role: {"name": cfg.get_str(key), "tool_call": True}
                    for role, key in {
                        "planner": "planner_model",
                        "reviewer": "reviewer_model",
                        "reflector": "reflector_model",
                        "writer-experimental": "experimental_writer_model",
                    }.items()
                },
            },
        },
    }
