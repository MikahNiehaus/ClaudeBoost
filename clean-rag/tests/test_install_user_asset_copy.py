"""The installer must never stomp a local edit, and must never hide one either.

`install_user_assets` refuses to copy over a destination whose mtime is newer
than the repo's, so a hand tweak in `~/.claude` survives a re-install. That
direction is deliberate and is not what these tests question.

What they pin down is the reporting. mtime says which file was touched last, not
whether the two differ (apenwarr, "mtime comparison considered harmful";
moby/moby#9391 reaches the same conclusion for ADD cache invalidation). A skip
announced as a bare "leaving it" reads as a no-op, which is how
`~/.claude/CLAUDE.md` came to sit hundreds of lines away from
`clean-rag/portable/CLAUDE.md` with every install run saying nothing useful
about it.

So: silent when the skip changes nothing, explicit about the extent when it
does, and copying still never happens over a newer destination.
"""

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]


def load_installer():
    """Load clean-rag/install.py under a private name.

    `install` is a common module name and clean-rag is not an importable
    package, so load it by path rather than putting the directory on sys.path.
    """
    spec = importlib.util.spec_from_file_location(
        "clean_rag_installer_under_test", CLEAN_RAG / "install.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def installer(tmp_path, monkeypatch):
    """The installer pointed at a scratch repo and a scratch ~/.claude."""
    module = load_installer()
    portable = tmp_path / "repo" / "portable"
    (portable / "agents").mkdir(parents=True)
    (portable / "skills" / "demo").mkdir(parents=True)
    (portable / "skills" / "demo" / "SKILL.md").write_text("demo\n", encoding="utf-8")
    (portable / "hook-run.py").write_text("# launcher\n", encoding="utf-8")

    claude_dir = tmp_path / "home" / ".claude"
    monkeypatch.setattr(module, "CLEAN_RAG_HOME", tmp_path / "repo")
    monkeypatch.setattr(module, "CLAUDE_DIR", claude_dir)
    return module, portable, claude_dir


def _make(path: Path, text: str, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_newer_destination_is_never_overwritten(installer, capsys):
    module, portable, claude_dir = installer
    now = time.time()
    _make(portable / "CLAUDE.md", "repo version\n", now - 100)
    _make(claude_dir / "CLAUDE.md", "the user's own version\n", now)

    module.install_user_assets()

    assert (claude_dir / "CLAUDE.md").read_text(encoding="utf-8") == "the user's own version\n"


def test_skip_reports_how_far_apart_the_two_copies_are(installer, capsys):
    module, portable, claude_dir = installer
    now = time.time()
    _make(portable / "CLAUDE.md", "one\ntwo\nthree\n", now - 100)
    _make(claude_dir / "CLAUDE.md", "one\nCHANGED\nthree\nEXTRA\n", now)

    module.install_user_assets()
    out = capsys.readouterr().out

    assert "CLAUDE.md" in out
    assert "3 lines differ" in out, out
    assert "diff " in out, out


def test_skip_is_silent_when_the_two_copies_match(installer, capsys):
    """A newer mtime with identical content is a no-op and should read as one."""
    module, portable, claude_dir = installer
    now = time.time()
    same = "identical everywhere\n"
    _make(portable / "CLAUDE.md", same, now - 100)
    _make(claude_dir / "CLAUDE.md", same, now)

    module.install_user_assets()
    out = capsys.readouterr().out

    assert "CLAUDE.md" not in out, out


def test_line_endings_alone_are_not_drift(installer, capsys):
    """A checkout that flips CRLF to LF has not edited anything."""
    module, portable, claude_dir = installer
    now = time.time()
    (portable / "CLAUDE.md").write_bytes(b"alpha\r\nbeta\r\n")
    os.utime(portable / "CLAUDE.md", (now - 100, now - 100))
    (claude_dir).mkdir(parents=True, exist_ok=True)
    (claude_dir / "CLAUDE.md").write_bytes(b"alpha\nbeta\n")
    os.utime(claude_dir / "CLAUDE.md", (now, now))

    module.install_user_assets()
    out = capsys.readouterr().out

    assert "CLAUDE.md" not in out, out


def test_differing_lines_counts_both_sides(tmp_path):
    module = load_installer()
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("one\ntwo\n", encoding="utf-8")
    b.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert module._differing_lines(a, b) == 1
    assert module._differing_lines(a, a) == 0


def test_differing_lines_reports_unreadable_rather_than_raising(tmp_path):
    module = load_installer()
    a = tmp_path / "a.txt"
    a.write_text("one\n", encoding="utf-8")

    assert module._differing_lines(a, tmp_path / "missing.txt") == -1
