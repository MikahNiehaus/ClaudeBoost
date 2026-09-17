"""A VERIFIED file list must survive a path that contains a space.

Sibling of test_verifier_covers_scoping_gap.py and
test_verifier_multiline_covers_gap.py, covering the third way the same covers
list came back empty on a genuinely clean, fully evidenced close.

_is_file_token used to reject any token containing whitespace. A space is legal
in a filename on both platforms (POSIX permits every byte but "/" and NUL;
Windows allows spaces outright), so a real path such as
"C:\\Development\\F and B PWA\\src\\app.py" failed that check, _continuation_files
rejected the whole line on it, and covered_files_in_block returned []. The stamp
was still written, since real execution proof was present, but with an empty
covers list, which is the shape HANDOFF and NITS use: loop_stage read
`agent == "bad-cop" and not covers` as STAGE_BUGS_FOUND and routed a clean pass
to good-cop, while check_file_verified for that file returned False forever.

The same guard dropped extensionless root files with no separator (Makefile,
Dockerfile, LICENSE) for the same reason.

The whitespace check could not simply be deleted: prose below the marker is also
a single comma-free token, and dropping it swept sentences into the covers list.
The class of input that must still be rejected is asserted here alongside the
class that must now be accepted.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
RECORD = HOOKS / "verifier-record.py"

# The subprocess gets a declared environment, never the inherited one: a test
# that passes on what happens to be present is an undeclared dependency.
ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PYTHONHOME", "PYTHONPATH",
}


def _load(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, HOOKS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vs = _load("verifier_state.py", "vs_spaced_path")
gate = _load("verifier-gate.py", "gate_spaced_path")


def payload(report: str, agent: str, session: str) -> dict:
    return {
        "tool_name": "Task",
        "session_id": session,
        "tool_input": {"subagent_type": agent, "prompt": "review the diff"},
        "tool_response": [{"type": "text", "text": report}],
    }


def run_hook(report: str, agent: str, session: str, clean_rag_home: str):
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_ALLOWLIST}
    env["CLEAN_RAG_HOME"] = clean_rag_home
    return subprocess.run(
        [sys.executable, str(RECORD)],
        input=json.dumps(payload(report, agent, session)),
        text=True, capture_output=True, timeout=120, env=env,
    )


SPACED_PATH = "C:\\Development\\F and B PWA\\src\\app.py"

CLEAN_PASS_WITH_A_SPACED_PATH = (
    "I reviewed the changed file under the spaced-path project directory.\n\n"
    "$ python -m pytest tests/ -q\n"
    "5 passed in 0.20s\n\n"
    "VERIFIED:\n"
    f"{SPACED_PATH}\n"
)


class TestASpacedPathOnAContinuationLine:
    def test_the_close_is_still_read_as_verified(self):
        assert vs.closing_stamp(CLEAN_PASS_WITH_A_SPACED_PATH) == vs.VERIFIER_MARKER

    def test_the_spaced_path_is_recorded(self, tmp_path, monkeypatch):
        r = run_hook(
            CLEAN_PASS_WITH_A_SPACED_PATH, "bad-cop",
            "spaced-path-covers", str(tmp_path),
        )
        assert r.returncode == 0
        assert "not recorded" not in r.stderr, (
            "real execution proof is present, so this must be recorded; "
            f"it was withheld: {r.stderr!r}"
        )

        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        record = json.loads(
            gate._record_path("spaced-path-covers").read_text(encoding="utf-8")
        )
        assert record["stamps"][-1]["covers"] == [SPACED_PATH]

    def test_loop_stage_does_not_read_this_as_bad_cop_found_bugs(self, tmp_path, monkeypatch):
        run_hook(
            CLEAN_PASS_WITH_A_SPACED_PATH, "bad-cop",
            "spaced-path-stage", str(tmp_path),
        )
        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        assert gate.loop_stage("spaced-path-stage") != gate.STAGE_BUGS_FOUND, (
            "a clean bad-cop pass with real pytest output routed to good-cop "
            "purely because the reviewed file sat under a directory with a "
            "space in its name"
        )

    def test_a_spaced_path_reaches_check_file_verified(self, tmp_path, monkeypatch):
        """End to end: the recorded name is what the gate matches on."""
        reviewed = tmp_path / "F and B PWA" / "app.py"
        reviewed.parent.mkdir(parents=True)
        reviewed.write_text("# x\n")
        time.sleep(0.3)

        report = (
            "$ python -m pytest -q\n1 passed in 0.10s\n\n"
            "VERIFIED:\n"
            f"{reviewed}\n"
        )
        run_hook(report, "bad-cop", "spaced-path-e2e", str(tmp_path))

        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        ok, reason = vs.check_file_verified("spaced-path-e2e", str(reviewed))
        assert ok, reason

    def test_a_spaced_path_on_the_marker_line_still_records(self, tmp_path, monkeypatch):
        """The marker-line path was already working; it must not regress."""
        report = (
            "$ python -m pytest -q\n1 passed in 0.10s\n\n"
            f"VERIFIED: {SPACED_PATH}\n"
        )
        run_hook(report, "bad-cop", "spaced-path-marker-line", str(tmp_path))
        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        record = json.loads(
            gate._record_path("spaced-path-marker-line").read_text(encoding="utf-8")
        )
        assert record["stamps"][-1]["covers"] == [SPACED_PATH]


class TestExtensionlessFilesOnAContinuationLine:
    """Same root cause: a root level file with no extension and no separator."""

    @pytest.mark.parametrize("name", ["Makefile", "Dockerfile", "LICENSE", "README"])
    def test_a_known_bare_filename_is_recorded(self, name):
        assert vs.covered_files_in_block(["VERIFIED:", name]) == [name]

    def test_a_mixed_list_is_recorded(self):
        assert vs.covered_files_in_block(
            ["VERIFIED:", "Makefile, Dockerfile, src/app.py"]
        ) == ["Makefile", "Dockerfile", "src/app.py"]


class TestProseIsStillRejected:
    """The whitespace check could not just be dropped. These are what it was for."""

    @pytest.mark.parametrize("line", [
        "I did not review * of the other files.",
        "Everything else was already clean.",
        "The Makefile was not part of this change.",
        "Nothing else needed a second look.",
        "I reviewed the src/app.py entry point.",
        "src/app.py was the only file that mattered.",
        "Reviewed against the requirements above.",
    ])
    def test_a_sentence_below_the_stamp_is_not_recorded(self, line):
        assert vs.covered_files_in_block(["VERIFIED: a.py", line]) == ["a.py"], (
            f"prose was swept into the covers list: {line!r}"
        )

    def test_a_lowercase_licence_word_is_not_read_as_a_file(self):
        assert vs.covered_files_in_block(["VERIFIED: a.py", "license"]) == ["a.py"]

    def test_prose_cannot_smuggle_in_a_matching_glob(self, tmp_path, monkeypatch):
        """Even if a sentence were accepted, it must not verify a real file."""
        target = tmp_path / "app.py"
        target.write_text("# x\n")
        block = ["VERIFIED: a.py", "I did not review * of the other files."]
        covers = vs.covered_files_in_block(block)
        assert not vs.file_in_scope(str(target), covers)
