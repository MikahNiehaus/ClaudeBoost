"""human-voice-guard.py's unverified-claim hedge check.

The rule: a hedge about work that was done ("that should work now") reads as a
verified result while having done the work of neither verifying nor admitting it
was not verified. Two forms replace it, and there is no third:

    Verified: <command> -> <result line>
    UNVERIFIED - to confirm, run: <command>

Why HEDGE_PATTERNS is regex and not a substring list, which is the whole test
surface here: a bare substring like "should fix" blocks "we should fix it in a
follow up", which is a plan about future work, not a claim about code that ran.
Every pattern therefore requires either a subject referring to the work
("that should work") or an explicit after-the-fact marker ("should work now").

Both directions have to hold:
  - the hedge shapes block
  - planning and hypothetical sentences containing the same words do not

Run: python -m pytest scripts/tests/test_human_voice_guard_hedges.py -v
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from helpers import SCRIPTS_DIR, run_hook


def _load_hvg():
    spec = importlib.util.spec_from_file_location(
        "human_voice_guard_hedges", SCRIPTS_DIR / "human-voice-guard.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hvg():
    return _load_hvg()


def _hedge_violations(hvg, text: str) -> list[str]:
    return [v for v in hvg.check_violations(text) if v.startswith("Unverified-claim")]


# ---------------------------------------------------------------------------
# Hedges block
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "I changed the parser. That should work now.",
        "This should fix the crash.",
        "It should resolve the timeout.",
        "Everything should pass now.",
        "The gate should be fine now.",
        "Patched the offset. Should work now.",
        "The suite should now be working.",
        "This should be fixed.",
        "The change likely resolves the race.",
        "That likely fixes it.",
        "The retry ought to now succeed.",
        "The output appears correct.",
        "The regex appears to be correct.",
        "The hook seems to work.",
        "The import seems to be fixed.",
        "Rebuilt the index. Should be good now.",
        "Which should work once the server restarts.",
    ],
)
def test_hedge_blocks(hvg, text):
    assert _hedge_violations(hvg, text), f"hedge not caught: {text!r}"


# ---------------------------------------------------------------------------
# MUTANT: replace the regex patterns with bare substrings. These sentences are
# plans, requirements, and hypotheticals, not claims about code that ran. A
# substring list flags every one of them, and a guard that fires on ordinary
# planning prose gets disabled by the human within a day.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "We should fix it in a follow up.",
        "You should work through the failures one at a time.",
        "I should resolve the merge conflict first.",
        "We should pass the absolute path here.",
        "Someone should work out whether the cache matters.",
        "The team should fix the flaky test before the release.",
        "The spec says the parser should reject an empty string.",
        "The docstring claims it should raise on a negative amount.",
        "Ask whether the endpoint should resolve relative paths.",
        "If the tests should fail, the gate blocks the stop.",
        "The comparator should return a number, per the contract.",
        "A reviewer should work from the diff, never the reasoning.",
    ],
)
def test_planning_and_requirements_do_not_block(hvg, text):
    assert not _hedge_violations(hvg, text), (
        f"false positive on planning/requirement prose: {text!r}"
    )


# ---------------------------------------------------------------------------
# The two legal forms are themselves legal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "Verified: python -m pytest tests/ -> 31 passed in 0.08s",
        "UNVERIFIED - to confirm, run: python -m pytest tests/",
        "Ran the suite. 31 passed, 0 failed.",
        "I did not run it. To confirm, run: npm test",
    ],
)
def test_legal_forms_pass(hvg, text):
    assert not _hedge_violations(hvg, text), f"legal form blocked: {text!r}"


# ---------------------------------------------------------------------------
# strip_noise still applies, so the rule can be quoted and discussed
# ---------------------------------------------------------------------------

def test_hedge_inside_code_fence_is_ignored(hvg):
    text = 'Here is the banned shape:\n```\nthat should work now\n```\nRan it instead.'
    assert not _hedge_violations(hvg, text)


def test_hedge_inside_backticks_is_ignored(hvg):
    text = "Never write `that should work now` about your own diff."
    assert not _hedge_violations(hvg, text)


def test_hedge_inside_double_quotes_is_ignored(hvg):
    text = 'The guard bans "this should fix the crash" and its variants.'
    assert not _hedge_violations(hvg, text)


# ---------------------------------------------------------------------------
# Reporting shape and the end to end block
# ---------------------------------------------------------------------------

def test_reports_the_matched_text_not_the_pattern(hvg):
    v = _hedge_violations(hvg, "That should work now.")
    assert len(v) == 1
    assert "that should work" in v[0], v
    assert "\\b" not in v[0], f"leaked the regex into the message: {v[0]}"


def test_multiple_hedges_deduped(hvg):
    v = _hedge_violations(hvg, "That should work now. That should work now.")
    assert len(v) == 1
    assert v[0].count("that should work") == 1, v


def test_hedge_and_banned_word_both_reported(hvg):
    v = hvg.check_violations("We leverage the cache. That should work now.")
    assert any(x.startswith("Banned vocabulary") for x in v), v
    assert any(x.startswith("Unverified-claim") for x in v), v


def test_clean_text_passes(hvg):
    assert hvg.check_violations("Ran the suite. 31 passed. Restored the file.") == []


def test_end_to_end_blocks_and_names_the_two_forms(boost_home, tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Patched it. That should work now."}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # CLAUDEBOOST_HOME must point at the fixture, not just be requested. The hook
    # keeps loop-prevention state in $CLAUDEBOOST_HOME/state/human-voice-check.json
    # and lets a message through when last_blocked_hash matches it. Without this
    # override the hook read the real repo's state file, so whether this test
    # blocked depended on what an earlier test had already blocked, and the suite
    # wrote into the developer's live state directory as a side effect.
    result = run_hook(
        "human-voice-guard.py",
        {
            "hook_event_name": "Stop",
            "session_id": "hedge-e2e",
            "transcript_path": str(transcript),
        },
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    reason = payload["reason"]
    assert "Unverified-claim hedges" in reason, reason
    assert "Verified: <command>" in reason, reason
    assert "UNVERIFIED" in reason, reason
