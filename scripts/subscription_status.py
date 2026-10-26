"""Inspect official CLI subscription logins without model calls or credential output."""
import json

from harness.config import load_settings
from harness.subscription import auth_status


def main():
    cfg = load_settings()
    for backend in ("claude-code", "codex"):
        try:
            print(json.dumps(auth_status(cfg, backend)))
        except (OSError, ValueError) as exc:
            print(json.dumps({"backend": backend, "ready": False, "error_type": type(exc).__name__}))


if __name__ == "__main__":
    main()
