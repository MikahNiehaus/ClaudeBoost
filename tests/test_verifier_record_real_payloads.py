"""The record hooks against the payload shapes Claude Code actually sends.

The existing suite (test_verifier_record_stamps.py) hands `tool_response` a
plain string that already contains the report. No real payload ever looks like
that, which is why a total loss of coverage data survived a green suite:

  - PostToolUse on Task fires when the Task tool call RETURNS. The harness runs
    subagents asynchronously, so that is LAUNCH time. `tool_response` is
    {agentId, canReadOutputFile, description, isAsync, outputFile, prompt,
    resolvedModel, status: "async_launched"} and carries no report at all.
    Every stamp written this way recorded `covers: []`, and
    `file_in_scope(path, [])` is False, so no file was ever seen as covered.

  - SubagentStop fires when the subagent actually finishes and carries the
    finished report in `last_assistant_message`, with `agent_type` at the top
    level and no `tool_input` at all.

Both shapes below were captured from live payloads, not from documentation.

Run: python -m pytest tests/test_verifier_record_real_payloads.py -v
"""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import verifier_state  # noqa: E402

SESSION = "verifier-record-real-payload-session"

CLEAN_REPORT = """Ran the adversarial suite, everything green.

VERIFIED: clean-rag/hooks/verifier_state.py, clean-rag/hooks/research_state.py
"""

JUDGE_REPORT = """| 1 | "walk through everything" | plan.md | PROVEN |

FULLY VERIFIED: 9 clauses, all proven
"""


def _load_hook(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, HOOKS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier_record = _load_hook("verifier-record.py", "verifier_record_real_payloads")


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    yield tmp_path


def _fire(payload: dict, monkeypatch) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return verifier_record.main()


def stamps():
    path = verifier_state._record_path(SESSION)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["stamps"]


def async_launch_payload(agent_type: str) -> dict:
    """The real PostToolUse payload for a Task spawn. Note there is no report
    anywhere in it: the agent has not run yet."""
    return {
        "tool_name": "Task",
        "session_id": SESSION,
        "tool_input": {"subagent_type": agent_type, "prompt": "review the diff"},
        "tool_response": {
            "agentId": "a1b2c3",
            "canReadOutputFile": True,
            "description": "Adversarial review",
            "isAsync": True,
            "outputFile": "/tmp/does-not-matter.output",
            "prompt": "review the diff",
            "resolvedModel": "claude-sonnet-5",
            "status": "async_launched",
        },
    }


def subagent_stop_payload(agent_type: str, report: str) -> dict:
    """The real SubagentStop payload. agent_type is top level, the report is in
    last_assistant_message, and there is no tool_input and no `prompt`."""
    return {
        "hook_event_name": "SubagentStop",
        "session_id": SESSION,
        "agent_id": "a1b2c3",
        "agent_type": agent_type,
        "last_assistant_message": report,
        "agent_transcript_path": "/tmp/agent.jsonl",
        "cwd": "/repo",
        "permission_mode": "default",
        "stop_hook_active": False,
    }


# ── the launch-time payload carries nothing, and must not pretend otherwise ──


def test_async_launch_payload_records_no_coverage(monkeypatch):
    """The bug, pinned. A launch-time payload has no report, so whatever it
    records must not claim to cover any file."""
    assert _fire(async_launch_payload("bad-cop"), monkeypatch) == 0
    assert [s["covers"] for s in stamps()] == [[]]


# ── SubagentStop is the one that actually carries the report ────────────────


def test_subagent_stop_records_the_files_the_report_covered(monkeypatch):
    assert _fire(subagent_stop_payload("bad-cop", CLEAN_REPORT), monkeypatch) == 0
    recorded = stamps()
    assert len(recorded) == 1
    assert recorded[0]["agent"] == "bad-cop"
    assert recorded[0]["covers"] == [
        "clean-rag/hooks/verifier_state.py",
        "clean-rag/hooks/research_state.py",
    ]


def test_subagent_stop_marks_the_covered_file_verified(monkeypatch, tmp_path):
    """End to end: the gate's own question, not just the record's contents."""
    assert _fire(subagent_stop_payload("good-cop", CLEAN_REPORT), monkeypatch) == 0
    target = tmp_path / "clean-rag" / "hooks" / "verifier_state.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")
    # Stamp is written before the file's mtime, which is the ordering
    # check_file_verified treats as "edited again after review".
    ok, reason = verifier_state.check_file_verified(SESSION, str(target))
    assert ok is False and "edited again" in reason

    # Re-stamp after the write and the same file now reads as verified.
    assert _fire(subagent_stop_payload("good-cop", CLEAN_REPORT), monkeypatch) == 0
    ok, reason = verifier_state.check_file_verified(SESSION, str(target))
    assert ok is True, reason


def test_agent_type_comes_from_the_top_level_not_tool_input(monkeypatch):
    """SubagentStop has no tool_input at all; reading only that yields ''."""
    payload = subagent_stop_payload("bad-cop", CLEAN_REPORT)
    assert "tool_input" not in payload
    assert verifier_record._agent_type(payload) == "bad-cop"


# ── filtering still holds on the new event ──────────────────────────────────


def test_non_verifier_agent_on_subagent_stop_is_ignored(monkeypatch):
    assert _fire(subagent_stop_payload("researcher", CLEAN_REPORT), monkeypatch) == 0
    assert stamps() == []




def test_evidence_judge_pass_is_still_not_recorded(monkeypatch):
    """Mode B never looked at a diff. SubagentStop carries no spawn prompt, so
    this relies on the report-text signal alone."""
    payload = subagent_stop_payload("bad-cop", JUDGE_REPORT)
    assert "prompt" not in payload
    assert _fire(payload, monkeypatch) == 0
    assert stamps() == []


# ── SubagentStop that omits agent_type entirely ─────────────────────────────
# Two live payloads on this machine arrived with agent_type "" and a populated
# last_assistant_message, and anthropics/claude-code#27755 reports the same
# shape. A blank type used to fall straight through the VERIFIER_AGENTS test,
# so a real good-cop pass wrote no stamp and its files stayed unverified.
# The type is recovered from the sidecar the harness writes beside the agent
# transcript: <session>/subagents/agent-<agent_id>.meta.json.


def write_sidecar(root: Path, agent_id: str, agent_type: str) -> Path:
    """The agent-<id>.meta.json Claude Code writes next to each transcript."""
    subagents = root / "projects" / SESSION / "subagents"
    subagents.mkdir(parents=True, exist_ok=True)
    transcript = subagents / f"agent-{agent_id}.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    (subagents / f"agent-{agent_id}.meta.json").write_text(
        json.dumps({
            "agentType": agent_type,
            "description": "Fix bad-cop High findings",
            "spawnDepth": 1,
            "requestShape": "background",
        }),
        encoding="utf-8",
    )
    return transcript


def test_blank_agent_type_is_recovered_from_the_harness_sidecar(monkeypatch, tmp_path):
    """The finding, fixed: a genuine VERIFIED: pass whose payload lost its
    agent_type still lands its stamp."""
    transcript = write_sidecar(tmp_path, "a1b2c3", "good-cop")
    payload = subagent_stop_payload("", CLEAN_REPORT)
    payload["agent_transcript_path"] = str(transcript)

    assert _fire(payload, monkeypatch) == 0
    recorded = stamps()
    assert len(recorded) == 1
    assert recorded[0]["agent"] == "good-cop"
    assert recorded[0]["covers"] == [
        "clean-rag/hooks/verifier_state.py",
        "clean-rag/hooks/research_state.py",
    ]


def test_blank_agent_type_resolves_from_session_transcript_when_no_agent_path(
        monkeypatch, tmp_path):
    """The other derivation: <session>.jsonl + agent_id, for a payload that
    carries transcript_path but not agent_transcript_path."""
    write_sidecar(tmp_path, "a1b2c3", "bad-cop")
    payload = subagent_stop_payload("", CLEAN_REPORT)
    del payload["agent_transcript_path"]
    payload["transcript_path"] = str(tmp_path / "projects" / f"{SESSION}.jsonl")

    assert _fire(payload, monkeypatch) == 0
    assert [s["agent"] for s in stamps()] == ["bad-cop"]


def test_sidecar_naming_a_non_verifier_agent_still_records_nothing(monkeypatch, tmp_path):
    """Recovering the name is not the same as widening the filter."""
    transcript = write_sidecar(tmp_path, "a1b2c3", "swiper")
    payload = subagent_stop_payload("", CLEAN_REPORT)
    payload["agent_transcript_path"] = str(transcript)

    assert _fire(payload, monkeypatch) == 0
    assert stamps() == []


def test_a_verified_line_alone_cannot_mint_a_stamp(monkeypatch, tmp_path):
    """The security property this fix is shaped around.

    Identity comes from harness-written state or not at all. Inferring it from
    the report instead would let any agent stamp its own coverage by printing
    one line, which is the path clean-rag/CLAUDE.md says must not exist.
    """
    payload = subagent_stop_payload("", CLEAN_REPORT)
    payload["agent_transcript_path"] = str(tmp_path / "no-such-agent.jsonl")

    assert _fire(payload, monkeypatch) == 0
    assert stamps() == [], "a report with a VERIFIED: line minted a stamp on its own"


def test_a_populated_agent_type_wins_over_the_sidecar(monkeypatch, tmp_path):
    """The sidecar is a fallback, not an override: the payload is authoritative
    whenever it actually says something."""
    transcript = write_sidecar(tmp_path, "a1b2c3", "good-cop")
    payload = subagent_stop_payload("researcher", CLEAN_REPORT)
    payload["agent_transcript_path"] = str(transcript)

    assert verifier_record._agent_type(payload) == "researcher"
    assert _fire(payload, monkeypatch) == 0
    assert stamps() == []


@pytest.mark.parametrize("raw", ["null", "[]", '"just a string"', "42", "{oops"])
def test_every_payload_shape_exits_zero_and_never_blocks(raw, monkeypatch):
    """json.loads accepts any JSON value, so a non-dict payload parses fine and
    then used to die at the first .get(). A record hook must never block."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert verifier_record.main() == 0


# ── research-record.py takes the same payloads through the same helpers ─────

research_record = _load_hook("research-record.py", "research_record_real_payloads")


@pytest.mark.parametrize("raw", ["null", "[]", '"just a string"', "42", "{oops"])
def test_research_record_also_exits_zero_on_every_payload_shape(raw, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert research_record.main() == 0


def test_research_record_recovers_a_blank_agent_type_from_the_sidecar(
        monkeypatch, tmp_path):
    """Same failure, same fix, on the research half of the gate."""
    import research_state

    transcript = write_sidecar(tmp_path, "a1b2c3", "swiper")
    payload = subagent_stop_payload("", "COVERS: clean-rag/hooks/research_state.py")
    payload["agent_transcript_path"] = str(transcript)

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert research_record.main() == 0

    record = json.loads(
        research_state._record_path(SESSION).read_text(encoding="utf-8"))
    assert record["stamps"][-1]["agent"] == "swiper"
    assert record["stamps"][-1]["covers"] == ["clean-rag/hooks/research_state.py"]
