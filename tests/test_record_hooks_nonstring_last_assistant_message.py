"""Adversarial: `last_assistant_message` arriving as a non-string JSON value.

verifier-record.py and research-record.py's _report() both added, in this
diff, an early return for SubagentStop's report field:

    last = payload.get("last_assistant_message")
    if last:
        return last

Every other branch in the same function (the tool_response flattening below
it) type-checks with isinstance(..., (str, list, dict)) before touching the
value. This new branch does not, and downstream (`is_evidence_judge_pass` ->
`_stamp_lines` -> `(text or "").splitlines()`, and research-record.py's
`_missing_proof` -> `domain_re.finditer(report)`) both require an actual str.

Nothing in main() catches this: the try/except only wraps `json.loads`, so a
JSON payload that parses fine but has a non-string last_assistant_message
propagates an uncaught AttributeError/TypeError out of `sys.exit(main())`,
producing a non-zero exit -- exactly the "never blocks, exit 0" contract this
file and clean-rag/CLAUDE.md both state for a SubagentStop record hook.

Run: python -m pytest tests/test_record_hooks_nonstring_last_assistant_message.py -v
"""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def _load_hook(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, HOOKS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier_record = _load_hook("verifier-record.py", "vr_nonstring_lam")
research_record = _load_hook("research-record.py", "rr_nonstring_lam")


def _fire(module, payload: dict, monkeypatch) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return module.main()


@pytest.mark.parametrize("bad_value", [
    ["not", "a", "string"],
    {"weird": "shape"},
    42,
    3.14,
    True,
])
def test_verifier_record_exits_zero_on_nonstring_last_assistant_message(
        bad_value, monkeypatch, tmp_path):
    """The documented contract: a SubagentStop record hook must never block,
    regardless of payload shape. This currently crashes instead."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "good-cop",
        "last_assistant_message": bad_value,
        "session_id": "nonstring-lam-session",
    }
    rc = _fire(verifier_record, payload, monkeypatch)
    assert rc == 0, (
        f"verifier-record.py exited {rc} (expected 0) for "
        f"last_assistant_message={bad_value!r} -- the hook crashed instead of "
        "recording nothing, on a payload shape that is exactly the class of "
        "malformed SubagentStop data this diff exists to tolerate."
    )


@pytest.mark.parametrize("bad_value", [
    ["not", "a", "string"],
    {"weird": "shape"},
    42,
])
def test_research_record_exits_zero_on_nonstring_last_assistant_message(
        bad_value, monkeypatch, tmp_path):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "swiper",
        "last_assistant_message": bad_value,
        "session_id": "nonstring-lam-session-research",
    }
    rc = _fire(research_record, payload, monkeypatch)
    assert rc == 0, (
        f"research-record.py exited {rc} (expected 0) for "
        f"last_assistant_message={bad_value!r} -- same crash, research half "
        "of the gate."
    )
