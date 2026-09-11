"""Tests for scripts/uninstall.py — _is_link_into_repo()'s footprint check.

uninstall.py's own docstring promises it "never touches anything ClaudeBoost
did not create". _is_link_into_repo() is where that promise is enforced for
~/.claude symlinks: it decides whether a link is ours to unlink by asking
whether its target lives inside the repo. Containment has to be judged per path
component. A bare string prefix has no separator boundary, so a second checkout
sitting beside this one ("ClaudeBoostFake", "ClaudeBoost2", "ClaudeBoost-old")
matched the repo name as a prefix and its symlink was classified as ours.

No symlink is created and nothing is unlinked here. The function is a pure
predicate over a path, so it is exercised with a Path-shaped stand-in rather
than by running any part of the uninstaller.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from helpers import SCRIPTS_DIR

_spec = importlib.util.spec_from_file_location("uninstall_scope_test", SCRIPTS_DIR / "uninstall.py")
_uninstall = importlib.util.module_from_spec(_spec)
sys.modules["uninstall_scope_test"] = _uninstall
_spec.loader.exec_module(_uninstall)


def _link_resolving_to(target: Path) -> MagicMock:
    """A Path-shaped symlink whose target is `target`."""
    link = MagicMock(spec=Path)
    link.is_symlink.return_value = True
    link.resolve.return_value = target
    link.__str__.return_value = str(target)
    return link


def test_sibling_directory_sharing_a_name_prefix_is_not_in_repo(tmp_path, monkeypatch):
    """A neighbour whose name merely starts with the repo's name is not ours."""
    parent = tmp_path.resolve()
    repo = parent / "ClaudeBoost"
    monkeypatch.setattr(_uninstall, "BOOST_HOME", repo)

    sibling_target = parent / "ClaudeBoostFake" / "commands"
    # The shape that made a string prefix say yes is still present...
    assert str(sibling_target).startswith(str(repo))
    # ...and the containment check must say no anyway.
    assert _uninstall._is_link_into_repo(_link_resolving_to(sibling_target)) is False


def test_actual_subdirectory_of_repo_is_in_repo(tmp_path, monkeypatch):
    """Contrast case: a real subdirectory must still be recognized as ours."""
    repo = tmp_path.resolve() / "ClaudeBoost"
    monkeypatch.setattr(_uninstall, "BOOST_HOME", repo)

    target = repo / ".claude" / "commands"
    assert _uninstall._is_link_into_repo(_link_resolving_to(target)) is True


def test_repo_root_itself_is_in_repo(tmp_path, monkeypatch):
    """The boundary case: the repo root is inside the repo, not outside it."""
    repo = tmp_path.resolve() / "ClaudeBoost"
    monkeypatch.setattr(_uninstall, "BOOST_HOME", repo)

    assert _uninstall._is_link_into_repo(_link_resolving_to(repo)) is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows paths are case-insensitive")
def test_windows_target_differing_only_in_case_is_in_repo(tmp_path, monkeypatch):
    """Windows compares paths case-insensitively; the check must too.

    A link written as c:\\...\\claudeboost\\.claude\\commands points at exactly
    the same directory as C:\\...\\ClaudeBoost\\.claude\\commands. Leaving it
    behind would be a footprint the uninstaller failed to clean.
    """
    repo = tmp_path.resolve() / "ClaudeBoost"
    monkeypatch.setattr(_uninstall, "BOOST_HOME", repo)

    target = Path(str(repo / ".claude" / "commands").lower())
    assert _uninstall._is_link_into_repo(_link_resolving_to(target)) is True


def test_unrelated_root_is_not_in_repo(tmp_path, monkeypatch):
    """A target with nothing in common with the repo is never ours."""
    repo = tmp_path.resolve() / "ClaudeBoost"
    monkeypatch.setattr(_uninstall, "BOOST_HOME", repo)

    outside = tmp_path.resolve() / "somewhere-else" / "commands"
    assert _uninstall._is_link_into_repo(_link_resolving_to(outside)) is False


def test_plain_file_that_is_not_a_link_is_not_in_repo(tmp_path, monkeypatch):
    """A real file the user wrote is left alone, whatever its path says."""
    repo = tmp_path.resolve() / "ClaudeBoost"
    monkeypatch.setattr(_uninstall, "BOOST_HOME", repo)

    real_file = repo / ".claude" / "CLAUDE.md"
    plain = MagicMock(spec=Path)
    plain.is_symlink.return_value = False
    # A real file resolves to itself, which is how the check tells it apart
    # from a link — it sits inside the repo path and must still be left alone.
    plain.resolve.return_value = plain
    plain.__str__.return_value = str(real_file)

    assert _uninstall._is_link_into_repo(plain) is False
