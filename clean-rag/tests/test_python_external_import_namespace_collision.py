"""_project_namespaces (graph_store.py) is shared between the C# using-directive
fallback and the pre-existing Python dotted-import fallback in
resolve_target_files. The dotted-directory split it does (registering "google"
as a namespace segment for a directory literally named "google.api") was added
to fix a real C# problem (a .NET folder like "ViveryAscend.API/" carrying the
dotted namespace it holds), but the helper is not C# specific, so the same
split also feeds the unrelated Python branch.

That is not hypothetical for Python. Protobuf/gRPC projects commonly vendor or
generate proto packages under a directory literally named after the proto
package, and Google's own proto packages are named "google.api", "google.cloud",
"google.logging", etc. (googleapis/googleapis). ".proto" is itself one of the
extensions clean-rag indexes (file_scan.CODE_EXTENSIONS), so such a directory
is a real, ordinary project layout, not a contrived one.

When a project has such a folder, "google" is registered as a project
namespace purely because of an unrelated proto directory name, and a genuine
`from google.cloud import storage` import (the real, PyPI-published Google
Cloud SDK) stops being marked "_external_" and is instead left empty
("ours, not yet resolved") -- indistinguishable from a real unresolved
project-internal reference. This regresses the Python resolution outcome
that predates and is unrelated to the C# work in this diff.
"""

import sys
from pathlib import Path

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server.graph_store import (  # noqa: E402
    GraphEdge,
    SQLiteGraphStore,
    _project_namespaces,
)
from server.indexing import _register_file_variants  # noqa: E402


def test_dotted_proto_folder_registers_a_namespace_segment_unrelated_to_python():
    file_map = {}
    _register_file_variants("protos/google.api/service.proto", file_map)
    assert "google" in _project_namespaces(file_map), (
        "the dotted-directory split (added for the C# namespace-folder case) "
        "also fires on a non-C# file's directory name"
    )


def test_real_third_party_python_import_stops_being_marked_external(tmp_path):
    """A real, unresolvable, third party dotted Python import must be marked
    _external_ regardless of an unrelated dotted directory elsewhere in the
    same project. This is the regression: it currently is NOT."""
    store = SQLiteGraphStore(str(tmp_path / "graph.db"))
    store.add_edges([GraphEdge(
        source_file="app/storage_client.py", source_symbol="<module>",
        target_file="", target_symbol="google.cloud",
        edge_type="imports", confidence="EXTRACTED",
    )])
    file_map = {}
    # Unrelated proto directory, vendored/generated, nothing to do with the
    # Python import below.
    _register_file_variants("protos/google.api/service.proto", file_map)
    _register_file_variants("app/storage_client.py", file_map)

    store.resolve_target_files(file_map)
    rows = [e for e in store.get_all_edges() if e.target_symbol == "google.cloud"]
    assert rows[0].target_file == "_external_", (
        "a real third party Python package (google-cloud-storage) must be "
        "marked external even when an unrelated dotted proto directory "
        f"happens to share its first namespace segment, got {rows[0].target_file!r}"
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
