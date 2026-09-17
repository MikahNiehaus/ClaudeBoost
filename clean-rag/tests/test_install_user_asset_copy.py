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
import subprocess
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


# --- A hard linked destination is someone else's file too -------------------
#
# install.bat hard links ~/.claude/CLAUDE.md to the repo's own tracked
# CLAUDE.md, then runs setup.py, which delegates here. shutil.copyfile opens
# the destination with "wb", so it truncates that shared inode in place and the
# repo's tracked file silently becomes the portable copy's content. On a fresh
# clone both mtimes come from the same checkout, so the newer-destination guard
# above does not fire and nothing else stood in the way.
#
# shutil.SameFileError does not cover this: it fires on _samefile(src, dst),
# and here src is the portable copy while the link is between dst and a third
# path, so src and dst genuinely are different files.


def _hardlink(target: Path, link: Path) -> None:
    """Hard link `link` to `target`, skipping the test if the fs cannot."""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(target, link)
    except (OSError, NotImplementedError, AttributeError) as exc:
        pytest.skip(f"filesystem does not support hard links: {exc}")
    if not os.path.samefile(target, link):
        pytest.skip("hard link did not produce a shared inode on this filesystem")


def test_hardlinked_destination_is_never_written_through(installer, tmp_path):
    """The property that matters: no file other than dst is ever mutated."""
    module, portable, claude_dir = installer
    now = time.time()
    _make(portable / "CLAUDE.md", "portable content\n", now)

    # The repo's tracked file, hard linked to the install destination exactly
    # the way install.bat's `mklink /h` leaves it.
    tracked = tmp_path / "repo" / "CLAUDE.md"
    _make(tracked, "tracked repo content\n", now)
    _hardlink(tracked, claude_dir / "CLAUDE.md")

    module.install_user_assets()

    assert tracked.read_text(encoding="utf-8") == "tracked repo content\n", (
        "the installer wrote through the hard link and clobbered the repo's "
        "own tracked CLAUDE.md")


def _hardlinked_run(installer, tmp_path, capsys, dst_mtime_offset=0.0):
    module, portable, claude_dir = installer
    now = time.time()
    _make(portable / "CLAUDE.md", "portable content\n", now)
    tracked = tmp_path / "repo" / "CLAUDE.md"
    _make(tracked, "tracked repo content\n", now + dst_mtime_offset)
    _hardlink(tracked, claude_dir / "CLAUDE.md")

    module.install_user_assets()
    return capsys.readouterr().out


def test_hardlinked_skip_names_the_hazard(installer, tmp_path, capsys):
    out = _hardlinked_run(installer, tmp_path, capsys)
    assert "hard linked" in out, out


def test_hardlinked_skip_never_advises_deleting_the_link(installer, tmp_path, capsys):
    """The remediation must not be one that quietly makes things worse.

    Telling the reader to delete the link and re-run swaps the linked document
    for the bundled copy, drops the link so it no longer follows the repo on
    git pull, and ends on a plain "installed" line that gives no sign the
    global instructions just changed identity. Following the tool's own advice
    left the user worse off than before the guard existed.
    """
    out = _hardlinked_run(installer, tmp_path, capsys)
    lowered = out.lower()
    for advice in ("del \"", "del '", "rm \"", "rm '", "delete it and", "and re-run"):
        assert advice not in lowered, (
            f"the skip message tells the reader to {advice!r}, which silently "
            f"replaces the linked document and breaks the link:\n{out}")
    # It must still say something useful rather than going quiet.
    assert "nothing to do" in lowered or "already in use" in lowered, out


def test_aliased_destination_reports_aliasing_not_mtime(installer, tmp_path, capsys):
    """A newer aliased destination must report the aliasing, not the mtime.

    The mtime branch says "reconcile by hand", which is wrong advice for a file
    that is really someone else's: editing it edits the other file too. On a
    real tree the repo root copy is newer than the portable one, so this is the
    case a user actually hits.
    """
    out = _hardlinked_run(installer, tmp_path, capsys, dst_mtime_offset=100)
    assert "hard linked" in out, out
    assert "newer than the repo copy" not in out, (
        f"the mtime branch won over the aliasing branch:\n{out}")


def test_a_plain_destination_is_still_copied(installer):
    """The guard must not fire on an ordinary file, or nothing installs."""
    module, portable, claude_dir = installer
    now = time.time()
    _make(portable / "CLAUDE.md", "portable content\n", now)
    _make(claude_dir / "CLAUDE.md", "stale content\n", now - 100)

    module.install_user_assets()

    assert (claude_dir / "CLAUDE.md").read_text(encoding="utf-8") == "portable content\n"


# --- Aliasing is not only hard links ----------------------------------------
#
# Path.stat() follows links, so a symlinked destination reports its TARGET's
# link count, which is 1 for an ordinary file however many symlinks point at
# it. shutil.copyfile then opens dst "wb", follows the link and truncates the
# target. Same hazard, different mechanism.


def test_symlinked_destination_is_never_written_through(installer, tmp_path):
    """Skips where the OS will not grant symlink creation (Windows, no Dev Mode)."""
    module, portable, claude_dir = installer
    now = time.time()
    _make(portable / "CLAUDE.md", "portable content\n", now)
    target = tmp_path / "repo" / "CLAUDE.md"
    _make(target, "tracked repo content\n", now)

    link = claude_dir / "CLAUDE.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError, AttributeError) as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    module.install_user_assets()

    assert target.read_text(encoding="utf-8") == "tracked repo content\n", (
        "the installer followed the symlink and truncated its target")


def test_alias_description_detects_each_mechanism(tmp_path):
    """Unit level, so the mechanisms that need no privilege are always covered."""
    module = load_installer()

    plain = tmp_path / "plain.txt"
    plain.write_text("x\n", encoding="utf-8")
    assert module._alias_description(plain) is None

    target = tmp_path / "t.txt"
    target.write_text("y\n", encoding="utf-8")
    hard = tmp_path / "hard.txt"
    try:
        os.link(target, hard)
    except (OSError, NotImplementedError, AttributeError) as exc:
        pytest.skip(f"cannot create a hard link here: {exc}")
    assert "hard linked" in (module._alias_description(hard) or "")

    # A junction is a reparse point that Path.is_symlink() reports as False
    # (measured), so it needs its own test or it goes undetected. It is also
    # the only non hard link aliasing mechanism creatable without elevation on
    # Windows, which makes it the one that can always run here.
    real_dir = tmp_path / "jtarget"
    real_dir.mkdir()
    junction = tmp_path / "jlink"
    rc = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(real_dir)],
                        capture_output=True, text=True)
    if rc.returncode == 0 and junction.exists():
        assert not junction.is_symlink(), (
            "assumption changed: is_symlink() now reports junctions, so the "
            "separate isjunction check may be redundant")
        assert module._alias_description(junction) == "a junction"


def test_alias_description_reports_a_symlink(tmp_path, monkeypatch):
    """Drives the symlink branch where the OS will not let us make one.

    test_symlinked_destination_is_never_written_through covers this end to end
    but skips without the Windows symlink privilege, so on this machine nothing
    would exercise the branch at all. Forcing is_symlink() runs the real
    detection code rather than the OS.
    """
    module = load_installer()
    f = tmp_path / "looks-like-a-link.txt"
    f.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(Path, "is_symlink", lambda self: True)

    assert (module._alias_description(f) or "").startswith("a symlink")


def test_aliased_destination_stays_silent_when_content_matches(installer, tmp_path, capsys):
    """An alias whose content already matches is not worth a warning.

    Nothing would change, so there is no hazard to report. This is the same
    "silent when the skip changes nothing" rule the mtime branch follows.
    """
    module, portable, claude_dir = installer
    now = time.time()
    same = "identical everywhere\n"
    _make(portable / "CLAUDE.md", same, now)
    tracked = tmp_path / "repo" / "CLAUDE.md"
    _make(tracked, same, now)
    _hardlink(tracked, claude_dir / "CLAUDE.md")

    module.install_user_assets()
    out = capsys.readouterr().out

    assert "CLAUDE.md" not in out, out


def test_alias_description_ignores_an_aliased_parent(tmp_path):
    """An ordinary file under a junction must stay installable.

    os.path.realpath would call this aliased, because it resolves the parent.
    Refusing here would break every install for anyone keeping ~/.claude behind
    a junction or a dotfiles symlink.
    """
    module = load_installer()
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    junction = tmp_path / "jdir"
    rc = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(real_dir)],
                        capture_output=True, text=True)
    if rc.returncode != 0 or not junction.exists():
        pytest.skip("junctions unavailable on this platform")

    inside = junction / "ordinary.txt"
    inside.write_text("content\n", encoding="utf-8")
    assert module._alias_description(inside) is None, (
        "a plain file inside a junction was treated as aliased, which would "
        "refuse every install under an aliased ~/.claude")


def test_alias_description_treats_an_unreadable_stat_as_unaliased(tmp_path):
    """Degradation path: a stat that cannot answer must not block an install."""
    module = load_installer()
    assert module._alias_description(tmp_path / "does-not-exist") is None


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
