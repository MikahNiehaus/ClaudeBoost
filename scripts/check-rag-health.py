"""RAG server health check.

Verifies that rag_server imports AND that its ML dependencies
(sentence-transformers / transformers / tokenizers) can actually load.

Exit codes:
  0 - healthy (module imports, sentence_transformers loads, path is inside ClaudeBoost)
  2 - dependency drift (ImportError from sentence_transformers / transformers / tokenizers)
      → caller should run reinstall-rag.py to self-heal
  3 - wrong install path (rag_server resolves outside CLAUDEBOOST_HOME)
      → caller should run reinstall-rag.py to reinstall editable
  1 - other error (print traceback, human must diagnose)
"""
import os
import sys
import traceback


def main() -> int:
    try:
        import rag_server  # noqa: F401
    except ImportError as e:
        print(f"rag_server import failed: {e}", file=sys.stderr)
        return 2

    boost_home = os.environ.get("CLAUDEBOOST_HOME", "")
    rag_path = getattr(rag_server, "__file__", "") or ""
    if boost_home and os.path.normcase(boost_home) not in os.path.normcase(rag_path):
        print(f"rag_server path outside CLAUDEBOOST_HOME: {rag_path}", file=sys.stderr)
        return 3

    # Actually exercise the ML stack — this is the check that would have caught
    # the tokenizers/transformers drift that the path-only check missed.
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except ImportError as e:
        print(f"sentence_transformers import failed: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"sentence_transformers failed to load: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"RAG healthy: {rag_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
