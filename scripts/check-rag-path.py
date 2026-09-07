"""Print where the rag_server package is installed.

Exit 0 means a real path was found and is on stdout. Exit 1 means it was not,
with the reason on stderr, so a caller can tell the two apart.

`__file__` alone is not enough: a namespace package (a directory with no
__init__.py, which is how mcp-rag-server/src/rag_server is laid out) has no
single file backing it, so `__file__` is unset and printing it yields the
literal text "None". Its locations live on `__path__` instead.
See https://docs.python.org/3/reference/import.html#__file__
"""
import sys

try:
    import rag_server
except ImportError as e:
    print(f"rag_server is not importable: {e}", file=sys.stderr)
    sys.exit(1)

path = getattr(rag_server, "__file__", None) or next(
    iter(getattr(rag_server, "__path__", [])), None
)
if not path:
    print(
        "rag_server imported but has no filesystem location "
        "(built-in, frozen, or loaded from memory)",
        file=sys.stderr,
    )
    sys.exit(1)

print(path)
