""".claude/browser-targets.local.json decides what curl and browser automation
may reach, exactly the role _ALLOWED_DEV_HOSTS / _ALLOWED_DEV_SUFFIXES used to
play as hardcoded literals in tracked source. _PROTECTED_PATH_RES already
refuses a Bash write to .claude/settings*.json for the same reason: "A guard
that the thing it guards can overwrite is not a guard." This file's own config
had no such protection.

Written by bad-cop to prove the gap; inverted here to assert it is closed.

Two of bad-cop's assertions demanded that _host_is_allowed_dev_env reject a
host the config named. That is the feature, not the bug: the config exists so a
human can name their own lower environments, and TestBrowserTargetAllowlist in
test_bash_guard_boundary.py pins five cases of it being honoured. The contract
is that the human is the only writer, so those two are rewritten below to
assert the write is refused rather than that the content is distrusted.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "bash-guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("bash_guard_unprotected", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard():
    return _load_guard()


class TestBrowserTargetsConfigIsProtected:
    """Every one of these commands would overwrite the file that decides which
    hosts curl and browser automation may reach, and each is refused.
    """

    def test_is_protected_path_returns_true(self, guard):
        assert guard._is_protected_path(".claude/browser-targets.local.json") is True

    def test_the_committed_example_is_protected_too(self, guard):
        """Overwriting the example rewrites the rules a human reads before
        filling in the real file."""
        assert guard._is_protected_path(".claude/browser-targets.example.json") is True

    def test_settings_json_for_comparison_is_protected(self, guard):
        """Sanity check: the sibling file this one matches IS protected."""
        assert guard._is_protected_path(".claude/settings.json") is True

    @pytest.mark.parametrize("command", [
        'echo {"allowed_hosts":["attacker.example"]} > .claude/browser-targets.local.json',
        'echo {"allowed_suffixes":[".example"]} >> .claude/browser-targets.local.json',
        'cp payload.json .claude/browser-targets.local.json',
        'cat payload.json > .claude/browser-targets.local.json',
        'mv payload.json .claude/browser-targets.local.json',
        'tee .claude/browser-targets.local.json < payload.json',
        'rm .claude/browser-targets.local.json',
        r'echo x > C:\Projects\MyApp\.claude\browser-targets.local.json',
    ])
    def test_check_protected_paths_blocks_the_write(self, guard, command):
        result = guard.check_protected_paths(command)
        assert result is not None, (
            f"check_protected_paths() allowed a write to the browser allowlist "
            f"config: {command!r}. It must be refused the same way "
            f".claude/settings.json is."
        )

    def test_full_evaluate_pipeline_blocks_the_write(self, guard):
        """The end-to-end guard, not just the one check, refuses this."""
        command = ('echo {"allowed_hosts":["attacker.example"]} '
                   '> .claude/browser-targets.local.json')
        assert guard.evaluate(command) is not None

    def test_reading_the_config_is_still_allowed(self, guard):
        """The refusal is on writes. A read has to stay free, or every
        diagnostic of why a host was denied needs a human."""
        assert guard.check_protected_paths(
            "cat .claude/browser-targets.local.json") is None

    def test_a_planted_config_is_honoured_which_is_why_the_write_is_refused(
            self, guard, tmp_path):
        """The full chain, in an isolated scratch home so the real repo file is
        never touched.

        _host_is_allowed_dev_env trusts whatever the config names, by design.
        That trust is only safe while the human is the only writer, so this
        asserts both halves together: the content is honoured, and the Bash
        routes to putting content there are refused.
        """
        (tmp_path / ".claude").mkdir()
        config = tmp_path / ".claude" / "browser-targets.local.json"
        guard._BROWSER_TARGETS_PATH = str(config)
        guard._browser_targets = None

        planted = "api-test.fabrikam.org"
        assert guard._host_is_allowed_dev_env(planted) is False, (
            "sanity check: must be denied before any config exists"
        )

        config.write_text('{"allowed_hosts": ["' + planted + '"]}', encoding="utf-8")
        guard._browser_targets = None
        assert guard._host_is_allowed_dev_env(planted) is True, (
            "a config the human wrote must widen the allowlist, or the file "
            "has no purpose"
        )

        assert guard.evaluate(
            'echo {"allowed_hosts":["attacker.example"]} '
            f'> {config.as_posix()}') is not None, (
            "and the session must not be able to write that content itself"
        )
