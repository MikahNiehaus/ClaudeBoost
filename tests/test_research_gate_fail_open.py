"""research-gate.py's docstring says "Exit codes: 0 always. Nothing here
blocks." That is a contract: a PreToolUse hook that ever exits non-zero on a
malformed-but-plausible payload can wedge an edit the model never intended to
block, the exact failure mode the whole fail-open design exists to avoid.

Only the initial json.loads() call in main() is wrapped in a try/except. Every
line after it (payload.get, tool_input.get) assumes payload is a dict and
tool_input is a dict, and nothing wraps the module-level
`if __name__ == "__main__": sys.exit(main())` guard the way verifier-gate.py's
equivalent guard does. A payload that is valid JSON but not shaped the way the
code assumes reaches main() past the try/except and can raise all the way out.

Run: python -m pytest tests/test_research_gate_fail_open.py -v
"""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"
RESEARCH_GATE = HOOKS_DIR / "research-gate.py"


def run_research_gate(raw_stdin: str):
    """Invoke the real script exactly as Claude Code's PreToolUse dispatch does:
    a subprocess with the payload on stdin. Returns (exit_code, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(RESEARCH_GATE)],
        input=raw_stdin.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def test_bare_json_scalar_payload_still_exits_zero():
    """A payload that parses as valid JSON but isn't an object (Claude Code has
    never been observed to send this, but nothing in the code checks for it
    before calling payload.get). The docstring promises exit 0 unconditionally."""
    code, err = run_research_gate("5")
    assert code == 0, (
        f"research-gate.py exited {code}, not 0, on a bare JSON scalar payload. "
        f"stderr:\n{err}"
    )


def test_null_tool_input_still_exits_zero():
    """tool_input present in the payload but explicitly JSON null. payload.get(
    "tool_input", {}) returns None here (the key exists), not the {} default,
    so .get("file_path", "") on the result raises AttributeError with nothing
    to catch it."""
    payload = json.dumps({"tool_name": "Edit", "tool_input": None})
    code, err = run_research_gate(payload)
    assert code == 0, (
        f"research-gate.py exited {code}, not 0, when tool_input is JSON null. "
        f"stderr:\n{err}"
    )


def test_tool_input_wrong_type_still_exits_zero():
    """tool_input is a string instead of an object, another JSON-valid but
    code-assumption-violating shape."""
    payload = json.dumps({"tool_name": "Write", "tool_input": "not-an-object"})
    code, err = run_research_gate(payload)
    assert code == 0, (
        f"research-gate.py exited {code}, not 0, when tool_input is a string. "
        f"stderr:\n{err}"
    )


def test_non_string_file_path_still_exits_zero():
    """file_path present and non-empty but not a string. This one gets past a
    tool_input type check and fails further in, at Path(file_path) inside
    _is_exempt, with TypeError rather than AttributeError."""
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": 123}})
    code, err = run_research_gate(payload)
    assert code == 0, (
        f"research-gate.py exited {code}, not 0, when file_path is a number. "
        f"stderr:\n{err}"
    )


def test_non_string_session_id_still_exits_zero():
    """A well formed edit payload whose session_id is an object. Nothing about
    tool_input is wrong here, so field-level validation of the edit target alone
    does not cover it: the session id gets hashed to locate the turn record, and
    a non-string raises AttributeError on .encode() well away from this file.
    The unconditional exit-0 claim covers this shape too."""
    payload = json.dumps({
        "tool_name": "Edit",
        "tool_input": {"file_path": "widget.py"},
        "session_id": {"unexpected": "object"},
    })
    code, err = run_research_gate(payload)
    assert code == 0, (
        f"research-gate.py exited {code}, not 0, when session_id is an object. "
        f"stderr:\n{err}"
    )


# The subprocess tests above pin the exit code a PreToolUse dispatch actually
# sees. They cannot tell which of the two fail-open layers produced it, because
# the __main__ guard turns any escaping exception into the same exit 0. These
# call main() directly so a payload the field reads mishandle shows up as a
# raised exception instead of being absorbed, which is what separates "the
# payload was understood and judged not gateable" from "something blew up and
# the net caught it". Both are exit 0; only the first is the intended path.
HOSTILE_PAYLOADS = [
    pytest.param(5, id="bare-scalar"),
    pytest.param([1, 2], id="bare-list"),
    pytest.param({"tool_name": "Edit", "tool_input": None}, id="tool-input-null"),
    pytest.param({"tool_name": "Edit", "tool_input": "str"}, id="tool-input-string"),
    pytest.param({"tool_name": "Edit", "tool_input": ["a"]}, id="tool-input-list"),
    pytest.param(
        {"tool_name": "Edit", "tool_input": {"file_path": 123}}, id="file-path-int"
    ),
    pytest.param(
        {"tool_name": "Edit", "tool_input": {"file_path": ["a.py"]}}, id="file-path-list"
    ),
    pytest.param(
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "widget.py"},
            "session_id": {"unexpected": "object"},
        },
        id="session-id-object",
    ),
]


@pytest.mark.parametrize("payload", HOSTILE_PAYLOADS)
def test_main_returns_zero_without_raising(payload, monkeypatch, tmp_path):
    """main() itself returns 0 on a hostile payload rather than raising into the
    __main__ guard. CLEAN_RAG_HOME is redirected so a payload that does reach the
    audit append writes to a throwaway state dir, not the real one."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        "research_gate_under_test", RESEARCH_GATE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, "stdin", io.StringIO(json.dumps(payload)))

    assert module.main() == 0
