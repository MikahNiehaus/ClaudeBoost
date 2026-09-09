"""Independently reproduces the claim in
spec/architecture-changes/server-registry-entry-is-never-revalidated.md:
a registered path is trusted forever, regardless of whether the directory at
that path still holds what was indexed.

Not a fix, a check that the spec's own repro still holds against the code as
it stands today, using the shared isolation fixture so nothing here touches
the operator's real registry.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app as app_mod  # noqa: E402
from tests.test_exec_routes_require_registered_project import (  # noqa: E402
    _StubRequest,
    empty_registry,  # noqa: F401  (used as a fixture by name)
)


def test_a_registered_path_stays_trusted_after_its_content_is_replaced(
    tmp_path, empty_registry,
):
    legit = tmp_path / "legit-project"
    legit.mkdir()
    (legit / "test_math.py").write_text(
        "def test_adds():\n    assert 1 + 1 == 2\n", encoding="utf-8",
    )
    (empty_registry / "projects.json").write_text(
        json.dumps({
            "proj": {
                "project_path": str(legit),
                "source": "clean-rag",
                "files_indexed": 1,
                "indexed_at": "2026-01-01T00:00:00Z",
            },
        }),
        encoding="utf-8",
    )

    # The directory is now replaced wholesale, same path, different content,
    # the same reproduction the spec file describes for a network mount
    # swap or a repository handed to someone else.
    for f in legit.iterdir():
        f.unlink()
    (legit / "package.json").write_text(
        json.dumps({
            "name": "replaced-content",
            "scripts": {
                "test": "node -e \"require('fs').writeFileSync('REPLACED.txt','x')\"",
            },
        }),
        encoding="utf-8",
    )

    response = asyncio.run(
        app_mod.handle_run_tests(_StubRequest({"project_path": str(legit)}))
    )

    assert response.status == 200, (
        "if this starts returning 403, the registry gained a revalidation "
        "check and the spec file is stale, not this test"
    )
    assert (legit / "REPLACED.txt").exists(), (
        "the replaced content's own test script ran under the identity of "
        "the directory the operator originally indexed: the registry entry "
        "authorises the path string, not the content that was there when "
        "it was written, confirming the spec file's claim independently"
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
