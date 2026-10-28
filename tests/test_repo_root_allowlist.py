"""Every tracked root entry is listed here on purpose.

Screenshots and a literal `~` folder were once committed at the root.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

ROOT_ALLOWED = {
    ".claude", ".claude-plugin", ".claudeboost", ".env.example", ".gitignore",
    ".ragignore", "CLAUDE.md", "LICENSE", "README.md", "benchmarks",
    "clean-rag", "conftest.py", "docs", "hooks", "install.bat", "install.sh",
    "plans", "pytest.ini", "scripts", "spec", "tests", "uninstall.bat",
    "uninstall.sh",
}


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def test_every_tracked_root_entry_is_allowed():
    roots = {p.split("/", 1)[0] for p in _tracked()}
    assert roots - ROOT_ALLOWED == set(), "add it to ROOT_ALLOWED or move it"


def test_no_tracked_path_starts_with_tilde():
    assert [p for p in _tracked() if p.startswith("~")] == []
