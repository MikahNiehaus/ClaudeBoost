"""
scripts/setup.py must be idempotent: installing the hook set twice produces the
same settings as installing it once.

_install_hook decides "already installed" by looking for its `sentinel` substring
inside the entry's prompt plus command text. So a sentinel that does not appear
in the entry it guards matches nothing, and every setup run appends another copy.
Nothing warns, and setup runs often (ensure-setup.py repairs the install on every
prompt), so the entry multiplies quietly.

That is not hypothetical. Removing a stale prompt hook from the PreCompact entry
left `sentinel="CONTEXT PRESERVATION"` guarding an entry whose text no longer
contained that phrase, and a duplicate compaction-save.py appeared in the live
settings within one session.

The second test is the cheap structural version of the same rule, and it names
the offending sentinel instead of just reporting a count.

Run: python -m pytest tests/test_setup_hooks_idempotent.py -v
"""

import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def setup_mod():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("cb_setup", REPO / "scripts" / "setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fingerprint(settings):
    """Every (event, command-or-prompt) pair, counted."""
    counts = Counter()
    for event, entries in (settings.get("hooks") or {}).items():
        for entry in entries:
            for h in entry.get("hooks", []):
                text = (h.get("command") or h.get("prompt") or "")[:120]
                counts[(event, entry.get("matcher", ""), text)] += 1
    return counts


def test_installing_the_hook_set_twice_changes_nothing(setup_mod, capsys):
    settings = {}
    setup_mod._install_all_hooks(settings)
    once = _fingerprint(settings)

    setup_mod._install_all_hooks(settings)
    twice = _fingerprint(settings)

    capsys.readouterr()

    grew = {k: (once[k], twice[k]) for k in twice if twice[k] > once.get(k, 0)}
    assert not grew, (
        "setup.py is not idempotent. These entries were appended a second time, "
        "which means their sentinel does not match their own text:\n"
        + "\n".join(f"  {k[0]} [{k[1]}] {k[2][:80]!r}: {v[0]} -> {v[1]}"
                    for k, v in grew.items())
    )
    assert once == twice


def test_a_pre_existing_duplicate_is_collapsed(setup_mod, capsys):
    """
    Fixing a sentinel stops the growth but cannot undo it.

    Once a sentinel stopped matching, every setup run appended another copy of
    that entry. Correcting the sentinel prevents new copies and leaves the ones
    already written, so a real install still ran compaction-save.py twice on
    every compaction. The cleanup pass has to remove them.
    """
    entry = {
        "matcher": "Always",
        "hooks": [{"type": "command", "command": "x /some/script.py", "timeout": 5000}],
    }
    settings = {"hooks": {"PreCompact": [dict(entry), dict(entry), dict(entry)]}}

    setup_mod._collapse_duplicate_hooks(settings)
    capsys.readouterr()

    assert len(settings["hooks"]["PreCompact"]) == 1, (
        "byte identical entries for the same event must collapse to one"
    )


def test_entries_differing_only_by_matcher_are_kept(setup_mod, capsys):
    """
    rag-read-guard is registered twice on purpose, once for Grep and once for
    Read. Collapsing on the script name rather than the whole entry would
    silently drop one of them.
    """
    def mk(matcher):
        return {
            "matcher": matcher,
            "hooks": [{"type": "command",
                       "command": "x /scripts/rag-read-guard.py", "timeout": 10}],
        }

    settings = {"hooks": {"PreToolUse": [mk("Grep"), mk("Read")]}}
    setup_mod._collapse_duplicate_hooks(settings)
    capsys.readouterr()

    assert len(settings["hooks"]["PreToolUse"]) == 2
    assert {e["matcher"] for e in settings["hooks"]["PreToolUse"]} == {"Grep", "Read"}


def test_every_sentinel_appears_in_the_entry_it_guards(setup_mod, capsys):
    """
    The structural form of the rule above.

    Reads back what _install_all_hooks produced and checks each sentinel against
    the entry text, so a mismatch is reported by name rather than as a count.
    """
    settings = {}
    setup_mod._install_all_hooks(settings)
    capsys.readouterr()

    source = (REPO / "scripts" / "setup.py").read_text(encoding="utf-8")
    sentinels = set(re.findall(r'sentinel="([^"]+)"', source))

    all_text = []
    for entries in (settings.get("hooks") or {}).values():
        for entry in entries:
            for h in entry.get("hooks", []):
                all_text.append((h.get("prompt", "") or "") + (h.get("command", "") or ""))

    unmatched = [s for s in sentinels if not any(s in t for t in all_text)]
    assert not unmatched, (
        "these sentinels match no installed hook, so setup.py will append a "
        f"duplicate entry on every run: {sorted(unmatched)}"
    )
