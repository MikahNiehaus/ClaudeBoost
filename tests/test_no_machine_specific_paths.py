"""ClaudeBoost must run from any clone, on any machine, under any username.

Two literals prove it does not: this developer's home directory, and the
absolute path of this particular clone. Either one baked into tracked source
means the file only works here, and it fails silently rather than loudly --
a test that hardcodes the repo root passes on the machine that wrote it for
the wrong reason, so the suite stops being evidence of anything.

This is the repo-wide version of the per-skill check in
plans/test_powerpoint_env.py (t_no_machine_specific_paths). It scans what git
tracks, so generated output (~/.claude/settings.json, .rag-index, state/)
is out of scope by construction -- clean-rag/install.py deliberately writes
absolute per-machine paths there and must keep doing so.

Synthetic path fixtures are unaffected: they use placeholder names
(C:/Development/MyApp, C:\\Development\\Domain, C:/Users/foo), none of which
contain the two banned literals.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The developer's home directory, and this clone's absolute location. Each
# needs two forms: the real path (colon and slash/backslash) and Claude Code's
# own mangled slug for it (~/.claude/projects/<mangled cwd>/, every non
# alphanumeric character replaced with a dash -- see scripts/session-restore.py
# _transcript_exists). A doc that quotes the mangled slug directly, as
# .claude/commands/self-improve.md once did, is just as machine specific as
# one that quotes the raw path, and the colon/slash form alone misses it.
# Case-insensitive: Windows paths get spelled both ways.
BANNED = {
    "personal home directory": re.compile(
        r"[Cc]:[\\/]+Users[\\/]+mniehaus|C--Users-mniehaus", re.IGNORECASE
    ),
    "this clone's absolute path": re.compile(
        r"[Cc]:[\\/]+Development[\\/]+ClaudeBoost|C--Development-ClaudeBoost", re.IGNORECASE
    ),
}

# Extensions that can actually execute or instruct. Binary and lock files are
# not scanned; a .md under .claude/ IS scanned, because Claude follows it.
SCANNED_SUFFIXES = {".py", ".js", ".ts", ".sh", ".bat", ".ps1", ".json", ".md", ".toml", ".cfg", ".ini", ".yml", ".yaml"}

# Prose that documents a real past incident by quoting the path it happened
# to. These are comments, not paths anything resolves.
ALLOWED = {
    "clean-rag/hooks/rag-enforce.py",
}


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line.strip()]


def _scannable() -> list[Path]:
    files = []
    for path in _tracked_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED or rel == "tests/test_no_machine_specific_paths.py":
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        if not path.is_file():
            continue
        files.append(path)
    return files


def test_git_ls_files_actually_returned_something():
    """Guard the guard. If git fails or the filter is wrong, every other test
    in this file passes vacuously over an empty list."""
    files = _scannable()
    assert len(files) > 100, f"expected to scan hundreds of tracked files, got {len(files)}"


@pytest.mark.parametrize("label,pattern", sorted(BANNED.items()))
def test_no_tracked_file_hardcodes(label: str, pattern: re.Pattern):
    hits = []
    for path in _scannable():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = path.relative_to(REPO_ROOT).as_posix()
                hits.append(f"  {rel}:{lineno}: {line.strip()[:110]}")

    assert not hits, (
        f"{len(hits)} tracked line(s) hardcode the {label}.\n"
        "Derive it instead: Path(__file__).resolve().parents[N], Path.home(), "
        "or the $CLEAN_RAG_HOME / $CLAUDEBOOST_HOME env vars this repo already uses.\n"
        + "\n".join(hits)
    )


def test_the_banned_patterns_actually_match_what_they_claim():
    """A regex that matches nothing would make the test above always pass."""
    home = BANNED["personal home directory"]
    clone = BANNED["this clone's absolute path"]

    assert home.search(r"C:\Users\mniehaus\.claude\agents\quick-cop.md")
    assert home.search("C:/Users/mniehaus/.claude/settings.json")
    assert home.search("~/.claude/projects/C--Users-mniehaus/memory/MEMORY.md")
    assert clone.search(r"Path('C:\Development\ClaudeBoost\clean-rag')")
    assert clone.search('sys.path.insert(0, "C:/Development/ClaudeBoost/clean-rag")')
    assert clone.search("~/.claude/projects/C--Development-ClaudeBoost/memory/MEMORY.md")

    # ...and do not fire on the synthetic fixtures the suite legitimately uses.
    for benign in (
        "C:/Development/MyApp",
        r"C:\Development\Domain",
        "C:/Users/foo/project",
        "/home/user/myapp",
        "Path(__file__).resolve().parents[1]",
    ):
        assert not home.search(benign), benign
        assert not clone.search(benign), benign
