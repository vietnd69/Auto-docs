"""MDX compilation check via the existing ``validate_mdx.mjs`` (Node.js)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from harness.config import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "validator" / "src" / "validator" / "format" / "validate_mdx.mjs"


class MdxUnavailableError(RuntimeError):
    """Node.js or the MDX compiler is not installed."""


def compile_errors(path: Path, timeout: int = 30) -> list[str]:
    """MDX compile errors for ``path`` (empty list = compiles)."""
    node = shutil.which("node")
    if node is None or not SCRIPT.exists():
        raise MdxUnavailableError("node or validate_mdx.mjs missing (run `npm ci` in validator/)")
    try:
        result = subprocess.run(
            [node, "--experimental-vm-modules", str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return [f"MDX validation timed out after {exc.timeout}s"]
    if "Cannot find package" in result.stderr or "ERR_MODULE_NOT_FOUND" in result.stderr:
        raise MdxUnavailableError("@mdx-js/mdx not installed (run `npm ci` in validator/)")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [f"unexpected validator output: {(result.stdout or result.stderr)[:200]}"]
    return [str(e) for e in data.get("errors", [])]
