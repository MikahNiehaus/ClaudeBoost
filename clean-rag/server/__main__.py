"""Entry point for the clean-rag server.

Run from the clean-rag directory:
    python server/__main__.py
Or via server_ctl:
    python cli/server_ctl.py start
"""

import sys
from pathlib import Path

# Add clean-rag root to sys.path so subpackages are importable
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from server.app import run_server

if __name__ == "__main__":
    run_server()
