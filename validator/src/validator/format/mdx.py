"""MDX validation via Node.js subprocess."""

import json
import shutil
import subprocess
from pathlib import Path

from validator.constants import MDX_NODE_TIMEOUT
from validator.format.checks import ValidationError


def validate_mdx(filepath: str) -> list[ValidationError]:
    """Validate MDX by calling validate_mdx.mjs via Node.js subprocess."""
    if not shutil.which("node"):
        return [ValidationError("mdx", "error", "Node.js không tìm thấy — hãy cài Node.js")]

    script = Path(__file__).parent / "validate_mdx.mjs"
    if not script.exists():
        return [ValidationError("mdx", "error", f"Không tìm thấy {script}")]

    try:
        result = subprocess.run(
            ["node", "--experimental-vm-modules", str(script), filepath],
            capture_output=True,
            text=True,
            timeout=MDX_NODE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return [ValidationError("mdx", "error", f"MDX validation timeout ({MDX_NODE_TIMEOUT}s)")]

    if result.returncode != 0 and not result.stdout:
        return [ValidationError("mdx", "error", f"Node error: {result.stderr.strip()}")]

    try:
        data = json.loads(result.stdout)
        return [
            ValidationError("mdx", "error", e)
            for e in data.get("errors", [])
        ]
    except json.JSONDecodeError:
        return [ValidationError("mdx", "error", f"Unexpected output: {result.stdout[:200]}")]
