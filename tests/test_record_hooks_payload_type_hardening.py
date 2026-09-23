"""Every field the record hooks read out of a SubagentStop payload is untrusted.

test_record_hooks_nonstring_last_assistant_message.py covers one field. The
same class reaches three more, each reproduced as a real exit 1 before the fix:

    agent_type: ["good-cop"]        TypeError: unhashable type: 'list'
                                    (truthy non-str returned, then tested for
                                    membership in the VERIFIER_AGENTS set)
    tool_input: "astring"           AttributeError: 'str' object has no attribute 'get'
    session_id: ["s"]               AttributeError: 'list' object has no attribute 'encode'
                                    (raised inside _record_path while hashing)

All four are the same bug: a field is read as though its JSON type were
guaranteed. They are read through _payload.str_field/dict_field now, the pair
research-gate.py and rag-enforce.py already use for exactly this.

The second half of this file pins down what a hook does when the report is
unreadable, which "exit 0" alone does not say. It records the completion with
NO file scope rather than recording nothing and rather than coercing the value
with str(): an empty scope is the codebase's existing "ran but declared
nothing" signal (extract_covered_files' docstring, and research-record.py's own
proof-violation path), it grants no clearance through check_file_verified, and
it keeps the fact that the agent ran. str() would instead write text that looks
like a report and parses to nothing.

Run: python -m pytest tests/test_record_hooks_payload_type_hardening.py -v
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "clean-rag" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import verifier_state  # noqa: E402


def _load_hook(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, HOOKS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier_record = _load_hook("verifier-record.py", "vr_type_hardening")
research_record = _load_hook("research-record.py", "rr_type_hardening")

SESSION = "payload-type-hardening-session"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    yield tmp_path


def _fire(module, payload: dict, monkeypatch) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return module.main()


def _stamps():
    path = verifier_state._record_path(SESSION)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["stamps"]


# --- the class the one reported field belongs to -----------------------------

MALFORMED_FIELDS = [
    ("agent_type", ["good-cop"]),
    ("agent_type", {"name": "good-cop"}),
    ("agent_type", 7),
    ("tool_input", "astring"),
    ("tool_input", ["a"]),
    ("tool_input", 3),
    ("session_id", ["s"]),
    ("session_id", {"id": "s"}),
    ("session_id", 12),
]


@pytest.mark.parametrize("field,bad_value", MALFORMED_FIELDS)
def test_verifier_record_exits_zero_on_malformed_field(field, bad_value, monkeypatch):
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "good-cop",
        "last_assistant_message": "VERIFIED: clean-rag/hooks/verifier-record.py",
        "session_id": SESSION,
    }
    payload[field] = bad_value
    assert _fire(verifier_record, payload, monkeypatch) == 0, (
        f"verifier-record.py crashed on {field}={bad_value!r}"
    )


@pytest.mark.parametrize("field,bad_value", MALFORMED_FIELDS)
def test_research_record_exits_zero_on_malformed_field(field, bad_value, monkeypatch):
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "swiper",
        "last_assistant_message": "COVERS: clean-rag/hooks/research-record.py",
        "session_id": SESSION,
    }
    payload[field] = bad_value
    assert _fire(research_record, payload, monkeypatch) == 0, (
        f"research-record.py crashed on {field}={bad_value!r}"
    )


def test_spawn_prompt_of_the_wrong_type_does_not_crash_the_judge_check(monkeypatch):
    """is_evidence_judge_pass() calls .upper() on the spawn prompt. A report
    with no stamp line reaches that call, so a non-str prompt crashed there."""
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "bad-cop",
        "tool_input": {"prompt": ["MODE: evidence-judge"]},
        "last_assistant_message": "no stamp line anywhere in this report",
        "session_id": SESSION,
    }
    assert _fire(verifier_record, payload, monkeypatch) == 0


# --- what an unreadable report is allowed to record --------------------------

@pytest.mark.parametrize("bad_value", [["not", "a", "string"], {"weird": "shape"}, 42, 3.14, True])
def test_unreadable_report_records_a_stamp_with_no_scope(bad_value, monkeypatch, tmp_path):
    """Not a bogus stamp: it names no files, so it clears nothing."""
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "good-cop",
        "last_assistant_message": bad_value,
        "session_id": SESSION,
    }
    assert _fire(verifier_record, payload, monkeypatch) == 0

    stamps = _stamps()
    assert len(stamps) == 1
    assert stamps[0]["covers"] == [], (
        f"an unreadable report claimed file coverage: {stamps[0]['covers']!r}"
    )
    assert stamps[0]["nits_only"] is False

    target = tmp_path / "some_file.py"
    target.write_text("x = 1\n", encoding="utf-8")
    ok, _reason = verifier_state.check_file_verified(SESSION, str(target))
    assert ok is False, "an empty-scope stamp granted verifier clearance"


@pytest.mark.parametrize("bad_value", [["VERIFIED: sneaky.py"], {"VERIFIED": "sneaky.py"}])
def test_unreadable_report_is_never_coerced_with_str(bad_value, monkeypatch):
    """str() on a structure yields text that looks like a report. Whatever the
    hook records must not be a Python repr of the payload value."""
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "good-cop",
        "last_assistant_message": bad_value,
        "session_id": SESSION,
    }
    assert _fire(verifier_record, payload, monkeypatch) == 0
    verdict = _stamps()[0]["verdict"]
    assert verdict != str(bad_value), f"report was coerced with str(): {verdict!r}"


def test_report_delivered_as_content_blocks_still_stamps_its_scope(monkeypatch):
    """The one non-str shape that does carry a real report: an assistant message
    as a list of content blocks, the same shape tool_response already arrives in."""
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "good-cop",
        "last_assistant_message": [
            {"type": "text", "text": "Everything green.\n\nVERIFIED: clean-rag/hooks/_payload.py"},
        ],
        "session_id": SESSION,
    }
    assert _fire(verifier_record, payload, monkeypatch) == 0
    assert _stamps()[0]["covers"] == ["clean-rag/hooks/_payload.py"]


def test_plain_string_report_still_stamps_its_scope(monkeypatch):
    """Regression guard: the ordinary path the fix must not have disturbed."""
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "good-cop",
        "last_assistant_message": "All green.\n\nVERIFIED: clean-rag/hooks/verifier-record.py\n",
        "session_id": SESSION,
    }
    assert _fire(verifier_record, payload, monkeypatch) == 0
    assert _stamps()[0]["covers"] == ["clean-rag/hooks/verifier-record.py"]


# --- the same thing as a real process, with a declared environment -----------

SUBPROCESS_SHAPES = [
    {"last_assistant_message": ["a", "b"]},
    {"last_assistant_message": {"k": "v"}},
    {"last_assistant_message": 42},
    {"last_assistant_message": 3.14},
    {"last_assistant_message": True},
    {"last_assistant_message": None},
    {"last_assistant_message": [{"content": ["nested", "list"]}]},
    {"agent_type": ["good-cop"]},
    {"tool_input": "astring"},
    {"tool_input": ["a"]},
    {"tool_input": {"prompt": ["a"]}, "last_assistant_message": "no stamp here"},
    {"session_id": ["s"]},
    {"session_id": 12},
]


@pytest.mark.parametrize("hook", ["verifier-record.py", "research-record.py"])
@pytest.mark.parametrize("overrides", SUBPROCESS_SHAPES, ids=lambda o: ",".join(sorted(o)))
def test_hook_exits_zero_as_a_real_process_with_a_scrubbed_environment(
        hook, overrides, tmp_path):
    """In-process main() shares this interpreter's sys.path and environment.
    The hook actually runs as a subprocess with only what the harness gives it,
    so the same shapes are re-run with the environment declared, not inherited.
    """
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "good-cop" if hook == "verifier-record.py" else "swiper",
        "last_assistant_message": "VERIFIED: x.py",
        "session_id": "subprocess-shape-session",
    }
    payload.update(overrides)

    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "CLEAN_RAG_HOME": str(tmp_path),
    }
    if os.name == "nt":  # python on Windows will not start without these
        for key in ("SYSTEMROOT", "COMSPEC", "PATHEXT"):
            if key in os.environ:
                env[key] = os.environ[key]

    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"{hook} exited {result.returncode} for {overrides!r}\n"
        f"stderr:\n{result.stderr}"
    )
