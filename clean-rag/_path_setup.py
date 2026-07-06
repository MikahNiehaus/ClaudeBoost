"""Path setup for clean-rag modules.

Because the directory is named 'clean-rag' (with a hyphen), Python cannot
import it as a package via 'python -m clean_rag'. This module adds the
clean-rag directory to sys.path so that subpackages (server, research, cli,
hooks, verifier) can be imported as top-level packages.

Usage at the top of any entry point:
    import _path_setup  # noqa: F401  (side-effect import)
"""

import sys
from pathlib import Path

_CLEAN_RAG_ROOT = str(Path(__file__).resolve().parent)

if _CLEAN_RAG_ROOT not in sys.path:
    sys.path.insert(0, _CLEAN_RAG_ROOT)
