# conftest.py at core/ root
# Ensures core/src is at the front of sys.path so that the installed `core`
# package (core/src/core) takes precedence over the core/ directory itself,
# which would otherwise be picked up as a namespace package.
import sys
from pathlib import Path

_HERE = Path(__file__).parent

def _prepend(p: Path) -> None:
    s = str(p)
    if s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)

_prepend(_HERE / "src")
_prepend(_HERE / "../llm/src")
_prepend(_HERE / "../rag/src")
_prepend(_HERE / "../prompts/src")
_prepend(_HERE / "../validator/src")
_prepend(_HERE / "../watcher/src")
