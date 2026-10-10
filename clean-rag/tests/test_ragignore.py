""".ragignore excludes files from the index, including files git tracks."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.file_scan import scan_project  # noqa: E402


def _names(root: Path) -> set:
    return {Path(p).relative_to(root).as_posix() for p in scan_project(str(root))}


def _project(tmp_path: Path) -> Path:
    for rel in ("src/app.py", "src/gen/client.py", "fixtures/seed.py", "deep/data/big.py"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_without_ragignore_everything_is_scanned(tmp_path):
    root = _project(tmp_path)
    assert _names(root) == {"src/app.py", "src/gen/client.py", "fixtures/seed.py", "deep/data/big.py"}


def test_ragignore_patterns_follow_gitignore_syntax(tmp_path):
    root = _project(tmp_path)
    (root / ".ragignore").write_text("# comment\nfixtures/\nsrc/gen/\ndata/\n", encoding="utf-8")
    assert _names(root) == {"src/app.py"}


def test_ragignore_drops_tracked_files_that_gitignore_cannot(tmp_path):
    root = _project(tmp_path)
    try:
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    (root / ".gitignore").write_text("fixtures/\n", encoding="utf-8")
    assert "fixtures/seed.py" in _names(root), "gitignore must not drop a tracked file"
    (root / ".ragignore").write_text("fixtures/\n", encoding="utf-8")
    assert "fixtures/seed.py" not in _names(root)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xef\xbb\xbffixtures/\r\nsrc/gen/\r\n",
        "fixtures/\r\nsrc/gen/\r\n".encode("utf-16"),
    ],
    ids=["utf8-bom-crlf", "utf16"],
)
def test_ragignore_saved_with_a_bom_still_applies_every_line(tmp_path, raw):
    root = _project(tmp_path)
    (root / ".ragignore").write_bytes(raw)
    assert _names(root) == {"src/app.py", "deep/data/big.py"}
