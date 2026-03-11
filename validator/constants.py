import sys
from pathlib import Path

# Add project root to sys.path to find config.py
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

MDX_NODE_TIMEOUT = config.MDX_NODE_TIMEOUT
