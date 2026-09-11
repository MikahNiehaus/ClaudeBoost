"""Tests for scripts/install-terminal-mode-reset.py — the PowerShell profile block.

setup.py runs this on Windows, so the block is now written to a real user's
profile. That makes three properties load bearing: it only ever appends, it is
a no op when already present, and it comes back out cleanly leaving whatever
the user wrote around it exactly as it was.

_profile_path is redirected to a temp file in every test here. Nothing touches
the real PowerShell profile.
"""
from __future__ import annotations

import importlib.util
import sys

import pytest

from helpers import SCRIPTS_DIR

_spec = importlib.util.spec_from_file_location(
    "terminal_mode_reset", SCRIPTS_DIR / "install-terminal-mode-reset.py")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["terminal_mode_reset"] = _mod
_spec.loader.exec_module(_mod)

USER_LINES = "function prompt { 'PS> ' }\r\nSet-Alias ll Get-ChildItem\r\n"


@pytest.fixture()
def profile(tmp_path, monkeypatch):
    """A scratch PowerShell profile the installer will write to."""
    path = tmp_path / "Microsoft.PowerShell_profile.ps1"
    monkeypatch.setattr(_mod, "_profile_path", lambda: path)
    return path


def test_install_appends_and_keeps_what_was_there(profile):
    profile.write_bytes(USER_LINES.encode("utf-8"))

    assert _mod.main() == 0

    # Bytes, not text: read_text would translate line endings and hide whether
    # the original CRLFs survived, which is the thing being asserted.
    content = profile.read_bytes()
    assert content.startswith(USER_LINES.encode("utf-8"))
    assert _mod.MARKER_BEGIN.encode("utf-8") in content
    assert _mod.MARKER_END.encode("utf-8") in content
    assert profile.with_suffix(profile.suffix + ".bak").exists()


def test_install_is_a_no_op_when_already_present(profile):
    profile.write_bytes(USER_LINES.encode("utf-8"))
    assert _mod.main() == 0
    once = profile.read_bytes()

    assert _mod.main() == 0

    assert profile.read_bytes() == once
    assert once.count(_mod.MARKER_BEGIN.encode("utf-8")) == 1


def test_remove_restores_the_original_bytes(profile):
    original = USER_LINES.encode("utf-8")
    profile.write_bytes(original)
    assert _mod.main() == 0
    assert _mod.MARKER_BEGIN.encode("utf-8") in profile.read_bytes()

    assert _mod.remove() == 0

    assert profile.read_bytes() == original


def test_remove_leaves_a_profile_without_the_block_alone(profile):
    original = USER_LINES.encode("utf-8")
    profile.write_bytes(original)

    assert _mod.remove() == 0

    assert profile.read_bytes() == original


def test_remove_on_a_missing_profile_is_not_an_error(profile):
    assert not profile.exists()
    assert _mod.remove() == 0


def test_remove_restores_the_original_bytes_when_profile_had_no_trailing_newline(profile):
    """A profile with no trailing newline is a normal, common shape (many
    editors do not add one on save). Round-tripping through install then
    remove must give back exactly what was there before, per the module's own
    'exactly as it was' contract — not that plus a stray line ending.
    """
    original = b"Set-Alias ll Get-ChildItem"  # no trailing \r\n or \n
    profile.write_bytes(original)

    assert _mod.main() == 0
    assert _mod.remove() == 0

    assert profile.read_bytes() == original


@pytest.mark.parametrize(
    "original",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"Set-Alias ll Get-ChildItem", id="no_trailing_newline"),
        pytest.param(b"Set-Alias ll Get-ChildItem\r\n", id="crlf"),
        pytest.param(b"Set-Alias ll Get-ChildItem\n", id="lf_only"),
        pytest.param(b"Set-Alias ll Get-ChildItem\r\n\r\n", id="trailing_blank_line"),
        pytest.param(b"Set-Alias ll Get-ChildItem\r\n\r\n\r\n", id="two_trailing_blank_lines"),
        pytest.param("# café — a byte this machine round trips badly\r\n".encode("utf-8"),
                     id="non_ascii"),
    ],
)
def test_install_then_remove_is_a_byte_exact_round_trip(profile, original):
    """The reversibility contract, over the profile shapes that actually occur.

    One shape passing is not the property. A trailing blank line the user wrote
    has to survive, and a missing trailing newline must not become one, and the
    two look identical to remove() unless install() leaves them distinguishable.
    """
    profile.write_bytes(original)

    assert _mod.main() == 0
    assert _mod.MARKER_BEGIN.encode("utf-8") in profile.read_bytes()
    assert _mod.remove() == 0

    assert profile.read_bytes() == original


def test_remove_flag_routes_to_remove(profile, monkeypatch):
    profile.write_bytes(USER_LINES.encode("utf-8"))
    assert _mod.main() == 0

    monkeypatch.setattr(sys, "argv", ["install-terminal-mode-reset.py", "--remove"])
    assert _mod.main() == 0

    assert _mod.MARKER_BEGIN.encode("utf-8") not in profile.read_bytes()


# ---------------------------------------------------------------------------
# The wiring. A mitigation nothing invokes protects nobody, and this one sat
# unreferenced. run_cmd is stubbed throughout: actually running either side
# would edit the real PowerShell profile of whoever runs the suite.
# ---------------------------------------------------------------------------
INSTALLER = SCRIPTS_DIR / "install-terminal-mode-reset.py"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestSetupWiring:
    def test_setup_runs_the_installer_on_windows(self, monkeypatch):
        setup = _load("setup_terminal_wiring", "setup.py")
        monkeypatch.setattr(setup, "IS_WINDOWS", True)
        calls = []
        monkeypatch.setattr(setup, "run_cmd", lambda args: (calls.append(args), (0, ""))[1])

        setup.install_terminal_mode_reset()

        assert len(calls) == 1, calls
        assert calls[0][1] == str(INSTALLER)
        assert INSTALLER.is_file(), "setup points at an installer that does not exist"

    def test_setup_skips_the_installer_off_windows(self, monkeypatch, capsys):
        setup = _load("setup_terminal_wiring", "setup.py")
        monkeypatch.setattr(setup, "IS_WINDOWS", False)
        monkeypatch.setattr(setup, "run_cmd", lambda args: pytest.fail(f"ran {args} off Windows"))

        setup.install_terminal_mode_reset()

        assert "Windows only" in capsys.readouterr().out

    def test_setup_main_calls_it(self):
        """Reachability: main() has to name the step, or none of this runs.

        main() is not executed here — it would install ClaudeBoost onto the
        machine running the tests.
        """
        setup = _load("setup_terminal_wiring", "setup.py")
        assert "install_terminal_mode_reset" in setup.main.__code__.co_names


class TestUninstallWiring:
    def test_uninstall_removes_the_block_on_windows(self, monkeypatch):
        uninstall = _load("uninstall_terminal_wiring", "uninstall.py")
        monkeypatch.setattr(uninstall, "IS_WINDOWS", True)
        monkeypatch.setattr(uninstall, "DRY_RUN", False)
        calls = []
        monkeypatch.setattr(uninstall, "_run", lambda args: (calls.append(args), (0, ""))[1])

        uninstall.remove_terminal_mode_reset()

        assert len(calls) == 1, calls
        assert calls[0][1] == str(INSTALLER)
        assert calls[0][2] == "--remove"

    def test_uninstall_dry_run_changes_nothing(self, monkeypatch):
        uninstall = _load("uninstall_terminal_wiring", "uninstall.py")
        monkeypatch.setattr(uninstall, "IS_WINDOWS", True)
        monkeypatch.setattr(uninstall, "DRY_RUN", True)
        monkeypatch.setattr(uninstall, "_run", lambda args: pytest.fail(f"ran {args} under --dry-run"))

        uninstall.remove_terminal_mode_reset()

    def test_uninstall_main_calls_it(self):
        """The reversibility contract in uninstall.py's docstring, enforced."""
        uninstall = _load("uninstall_terminal_wiring", "uninstall.py")
        assert "remove_terminal_mode_reset" in uninstall.main.__code__.co_names
