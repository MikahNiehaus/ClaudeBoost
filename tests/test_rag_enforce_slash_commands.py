"""rag-enforce.py decides two opposite things from the raw prompt: /ps marks the
turn quick (skip the research gate and the verifier) and makes that sticky for 10
minutes, and /start cancels a sticky /ps so the turn asking for the full sequence
is not still running under the skip.

Both decisions were keyed off `\\b`, which is a word/non-word boundary, not a
whitespace one. "start" followed immediately by "-", ",", ".", "!", ":", "'" or
"?" satisfies `\\b` exactly as well as a space does, so "/start-something" was
read as the full-ceremony command and deleted a /ps the human had set moments
earlier and meant to keep. `/ps` had the identical construction and the identical
flaw pointing the other way: "/ps-foo" silently turned the skip on.

A slash command is a whitespace-delimited token, so the boundary that belongs
here is "whitespace or end of prompt", not "word character to non-word
character".

Both decisions read the prompt out of a payload that arrives on stdin, so the
shape of that payload is part of the same contract. The file's own header says
its exit code is "0 = always (UserPromptSubmit hooks cannot block)". Valid JSON
that is not an object broke that: a bare list, number, string, null or bool
parses cleanly, has no .get, and crashed the hook with an AttributeError and
exit 1 on a message the human was waiting on. The tests at the bottom pin exit
0 for every stdin there is, and pin that text arriving in such a payload is
never read as a command.

Settling the payload's outer shape left the same defect one level down. Every
field inside it (prompt, session_id, transcript_path) is just as untrusted, and
`.get(key, "")` only defaults an ABSENT key, so a field present as a number, a
list, an object or a bool reached re.Pattern.search() and raised TypeError,
exit 1 again. `None` was the one type an `or ""` idiom happened to rescue. The
transcript that transcript_path points at is the same story a third time: a
line that is valid JSON but not an object crashed on .get while being scanned
for the last assistant message. So the field-type cases below run every field
against every JSON type, not just the one that was reported.

Run: python -m pytest tests/test_rag_enforce_slash_commands.py -v
"""

import contextlib
import http.server
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"
RAG_ENFORCE = HOOKS_DIR / "rag-enforce.py"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import research_state  # noqa: E402


def load_rag_enforce():
    """rag-enforce.py has a hyphen in its name, so it cannot be imported normally."""
    spec = importlib.util.spec_from_file_location("rag_enforce_under_test", RAG_ENFORCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_hook(payload, home):
    """Invoke the real script the way Claude Code's UserPromptSubmit dispatch
    does: a subprocess with the payload on stdin. Returns (exit_code, stderr)."""
    env = dict(__import__("os").environ)
    env["CLEAN_RAG_HOME"] = str(home)
    proc = subprocess.run(
        [sys.executable, str(RAG_ENFORCE)],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=30,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def run_hook_raw(raw, home):
    """Same dispatch as run_hook, but with the exact bytes on stdin.

    run_hook serialises a Python object, so it can only ever produce a JSON
    object. The payloads that broke the hook are the ones it cannot express:
    valid JSON that is not an object, text that is not JSON at all, nothing,
    and bytes that are not even UTF-8.
    """
    env = dict(__import__("os").environ)
    env["CLEAN_RAG_HOME"] = str(home)
    proc = subprocess.run(
        [sys.executable, str(RAG_ENFORCE)],
        input=raw if isinstance(raw, bytes) else raw.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=30,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def set_sticky_quick(monkeypatch, home, session_id):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(home))
    research_state.set_session_quick(session_id)
    assert research_state.is_session_quick(session_id), "test setup failed to set the flag"


def is_sticky_quick(monkeypatch, home, session_id):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(home))
    return research_state.is_session_quick(session_id)


# Every shape that must NOT be read as /start. The punctuation cases are the ones
# `\b` accepted; the rest guard the boundary from being loosened later.
START_LOOKALIKES = [
    "/start-something",
    "/started",
    "/startup",
    "/start,",
    "/start.",
    "/start!",
    "/start:",
    "/start'",
    "/start?",
    "/start_foo",
    "/startx",
    "please /start it when you can",
    "```\n/start build the thing\n```",
    '"/start" spawns researcher then swiper',
]

START_REAL = [
    "/start",
    "/start build the thing",
    "  /start feature",
    "/START a feature",
    "<command-message>start</command-message><command-name>/start</command-name>",
]

PS_LOOKALIKES = ["/ps-foo", "/ps,", "/ps.", "/pset", "/psalm", "please /ps it"]

PS_REAL = ["/ps", "/ps quick typo fix", "  /ps typo", "/PS typo"]


@pytest.mark.parametrize("prompt", START_LOOKALIKES)
def test_start_lookalike_is_not_full_ceremony(prompt):
    assert load_rag_enforce()._is_full_ceremony(prompt) is False, (
        f"{prompt!r} was read as the /start command. Only /start followed by "
        f"whitespace or end of prompt is the full-ceremony instruction."
    )


@pytest.mark.parametrize("prompt", START_REAL)
def test_real_start_is_full_ceremony(prompt):
    assert load_rag_enforce()._is_full_ceremony(prompt) is True, (
        f"{prompt!r} is a real /start and must still be recognised."
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "<command-message>started</command-message><command-name>/started</command-name>",
        "<command-name>/start-something</command-name>",
    ],
)
def test_command_wrapper_lookalike_is_not_full_ceremony(prompt):
    """The wrapper regex requires the closing tag straight after /start, so it
    never had the boundary flaw. Pinned so a later edit cannot introduce one."""
    assert load_rag_enforce()._is_full_ceremony(prompt) is False


@pytest.mark.parametrize("prompt", ["/start-something unrelated", "/start, then what", "/start.py is a file"])
def test_start_lookalike_leaves_a_sticky_quick_flag_alone(prompt, monkeypatch, tmp_path):
    """The failure that actually costs the human something: a prompt that merely
    begins with the letters "start" cancelled the /ps they set moments earlier,
    silently, well inside its 10 minute life."""
    session = "lookalike-session"
    set_sticky_quick(monkeypatch, tmp_path, session)

    code, err = run_hook({"session_id": session, "prompt": prompt}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is True, (
        f"{prompt!r} cleared the sticky /ps. Only a real /start may do that."
    )


def test_real_start_clears_a_sticky_quick_flag(monkeypatch, tmp_path):
    session = "real-start-session"
    set_sticky_quick(monkeypatch, tmp_path, session)

    code, err = run_hook({"session_id": session, "prompt": "/start build a feature"}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is False, (
        "a real /start must end the sticky /ps on the prompt itself, not wait "
        "for an agent to finish."
    )


def test_start_beats_ps_in_one_prompt(monkeypatch, tmp_path):
    """Asking for the full sequence and asking to skip it are contradictory.
    The turn must end up non-quick."""
    session = "both-commands-session"
    prompt = "/ps and also <command-name>/start</command-name>"

    code, err = run_hook({"session_id": session, "prompt": prompt}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is False


@pytest.mark.parametrize("prompt", PS_REAL)
def test_real_ps_sets_the_sticky_quick_flag(prompt, monkeypatch, tmp_path):
    session = f"ps-real-{abs(hash(prompt))}"

    code, err = run_hook({"session_id": session, "prompt": prompt}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is True, (
        f"{prompt!r} is a real /ps and must mark the turn quick."
    )


@pytest.mark.parametrize("prompt", PS_LOOKALIKES)
def test_ps_lookalike_does_not_set_the_sticky_quick_flag(prompt, monkeypatch, tmp_path):
    """The mirror-image defect, and the more dangerous direction: a false match
    here turns the skip ON, disabling the research gate and the verifier for a
    turn nobody asked to skip, and stickily for the next 10 minutes."""
    session = f"ps-lookalike-{abs(hash(prompt))}"

    code, err = run_hook({"session_id": session, "prompt": prompt}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is False, (
        f"{prompt!r} is not the /ps command but marked the turn quick."
    )


def test_ps_survives_a_following_ordinary_turn(monkeypatch, tmp_path):
    session = "ps-sticky-session"
    run_hook({"session_id": session, "prompt": "/ps quick typo fix"}, tmp_path)

    code, err = run_hook({"session_id": session, "prompt": "now rename the variable"}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is True


def test_ps_expires_after_its_ttl(monkeypatch, tmp_path):
    """The flag is time limited, not permanent, so a /ps from an hour ago cannot
    silently skip the ceremony on today's work."""
    session = "ps-expiry-session"
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    path = research_state._session_quick_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    stale = time.time() - (research_state.SESSION_QUICK_MAX_AGE_S + 60)
    path.write_text(json.dumps({"set_at": stale}), encoding="utf-8")

    assert research_state.is_session_quick(session) is False


def test_task_notification_cannot_clear_a_sticky_quick_flag(monkeypatch, tmp_path):
    """A background task's completion arrives as a synthetic prompt with no field
    marking it as such. One quoting /start must not cancel the human's /ps."""
    session = "task-notification-session"
    set_sticky_quick(monkeypatch, tmp_path, session)
    prompt = (
        "<task-notification>Background agent finished. It said: run "
        "<command-name>/start</command-name> next to continue.</task-notification>"
    )

    code, err = run_hook({"session_id": session, "prompt": prompt}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is True


# Checking that the payload is an object settles its outer shape only. The
# values inside it are equally untrusted, and `.get(key, "")` hands back its
# default when the key is ABSENT, never when the key is present holding the
# wrong type. So a mistyped field walks straight past that guard into code that
# assumes str: re.Pattern.search()/.match() raise TypeError on an int prompt,
# Path() raises on an int transcript_path, and session_id is hashed via
# .encode(). `None` is the one case a `value or ""` idiom happens to rescue,
# which is why testing only that one hid the rest.
#
# The three fields are every field main() reads off the payload (grep
# hook_payload in rag-enforce.py), crossed with every JSON type that is not a
# string.
PAYLOAD_FIELDS = ["prompt", "session_id", "transcript_path"]

NON_STRING_JSON_VALUES = [
    ("int", 42),
    ("list", ["/ps", "typo"]),
    ("object", {"text": "/ps"}),
    ("bool", True),
    ("null", None),
]

WELL_FORMED_PAYLOAD = {
    "prompt": "rename the variable",
    "session_id": "mistyped-field-session",
    "transcript_path": "",
}

PAYLOADS_WITH_A_MISTYPED_FIELD = [
    pytest.param({**WELL_FORMED_PAYLOAD, field: value}, id=f"{field}-{type_name}")
    for field in PAYLOAD_FIELDS
    for type_name, value in NON_STRING_JSON_VALUES
] + [
    pytest.param({}, id="every-field-absent"),
    pytest.param({"prompt": "/start build a feature"}, id="session-id-missing"),
    # A mistyped session_id alongside a prompt that IS one of the commands, so
    # the /start and /ps branches run with a session id they cannot use.
    pytest.param(
        {"session_id": 12345, "prompt": "/start build a feature"},
        id="session-id-int-with-a-start-prompt",
    ),
    pytest.param(
        {"session_id": {"a": 1}, "prompt": "/ps typo"},
        id="session-id-object-with-a-ps-prompt",
    ),
]


@pytest.mark.parametrize("payload", PAYLOADS_WITH_A_MISTYPED_FIELD)
def test_hook_exits_zero_on_any_payload_field_of_the_wrong_type(payload, tmp_path):
    """Same "0 = always" contract as the non-object payload case, one level
    deeper: a field inside an otherwise well-formed object, rather than the
    object's own shape."""
    code, err = run_hook(payload, tmp_path)

    assert code == 0, f"hook exited {code} on {payload!r}. stderr:\n{err}"
    assert "Traceback" not in err, f"hook crashed on {payload!r}. stderr:\n{err}"


@pytest.mark.parametrize(
    "prompt",
    [
        pytest.param(["/ps", "typo"], id="prompt-list"),
        pytest.param({"text": "/ps typo"}, id="prompt-object"),
        pytest.param(True, id="prompt-bool"),
    ],
)
def test_a_mistyped_prompt_cannot_set_the_quick_flag(prompt, monkeypatch, tmp_path):
    """The dangerous direction. A prompt that is not a string is not the human
    typing /ps, so it must not disable the research gate and the verifier for
    the next ten minutes, however the text inside it reads."""
    session = "mistyped-prompt-sets-session"

    code, err = run_hook({"session_id": session, "prompt": prompt}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is False, (
        f"a {type(prompt).__name__} prompt marked session {session!r} quick."
    )


@pytest.mark.parametrize(
    "prompt",
    [
        pytest.param(["/start", "build"], id="prompt-list"),
        pytest.param({"text": "/start build"}, id="prompt-object"),
        pytest.param(42, id="prompt-int"),
    ],
)
def test_a_mistyped_prompt_cannot_clear_a_sticky_quick_flag(prompt, monkeypatch, tmp_path):
    """The mirror direction. A prompt that is not a string is not the human
    typing /start either, so it must not delete a /ps set moments earlier."""
    session = "mistyped-prompt-clears-session"
    set_sticky_quick(monkeypatch, tmp_path, session)

    code, err = run_hook({"session_id": session, "prompt": prompt}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is True, (
        f"a {type(prompt).__name__} prompt was read as /start and cleared the sticky /ps."
    )


@pytest.mark.parametrize(
    "prompt",
    [
        pytest.param(42, id="prompt-int"),
        pytest.param(["/ps", "typo"], id="prompt-list"),
        pytest.param({"text": "/ps"}, id="prompt-object"),
        pytest.param(True, id="prompt-bool"),
    ],
)
def test_a_mistyped_prompt_is_recorded_as_no_prompt(prompt, tmp_path, monkeypatch):
    """Reading the field as "" is the point, not stringifying it. str(42) or
    str(["/ps"]) would put a rendering of the raw JSON into the turn record and
    into the search query, which is text the human never typed."""
    session = "mistyped-prompt-record-session"

    code, err = run_hook({"session_id": session, "prompt": prompt}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    record = json.loads(research_state._record_path(session).read_text(encoding="utf-8"))
    assert record["prompt_preview"] == ""


@pytest.mark.parametrize(
    "session_id",
    [
        pytest.param(12345, id="session-id-int"),
        pytest.param({"a": 1}, id="session-id-object"),
        pytest.param(None, id="session-id-null"),
    ],
)
def test_a_mistyped_session_id_still_opens_a_turn_record(session_id, tmp_path, monkeypatch):
    """The research gate and the verifier both read the turn record, so a
    session id of the wrong type must degrade to the same unnamed-session
    record an absent one produces, not lose the record entirely."""
    code, err = run_hook({"session_id": session_id, "prompt": "rename the variable"}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    record_path = research_state._record_path("")
    assert record_path.exists(), (
        f"a {type(session_id).__name__} session_id lost the turn record entirely"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["prompt_preview"] == "rename the variable"


# The transcript is the payload's second untrusted input: main() hands
# transcript_path to _get_recent_context(), which json.loads() each line and
# then reads .get off the result. A line that parses as valid JSON without
# being an object, or whose "message" holds any other type, raised
# AttributeError there and exited 1 for exactly the same reason a mistyped
# payload field did.
TRANSCRIPT_LINES_THAT_ARE_NOT_USABLE = [
    pytest.param("42", id="line-is-a-number"),
    pytest.param('"just a string"', id="line-is-a-string"),
    pytest.param("[1,2,3]", id="line-is-an-array"),
    pytest.param("null", id="line-is-null"),
    pytest.param('{"message": ["not", "an", "object"]}', id="message-is-an-array"),
    pytest.param('{"message": 7}', id="message-is-a-number"),
    pytest.param('{"message": null}', id="message-is-null"),
]


@pytest.mark.parametrize("transcript_path", [42, ["/a/path"], {"path": "/a/path"}, True])
def test_a_mistyped_transcript_path_is_not_an_error_the_hook_has_to_log(
    transcript_path, tmp_path
):
    """A field of the wrong type means "no transcript", the same as an absent
    one. Letting it reach Path() instead and relying on the except there still
    exits 0, but writes a read-failure to the error log on a message where
    nothing actually failed to read."""
    code, err = run_hook(
        {"session_id": "s", "prompt": "fix", "transcript_path": transcript_path}, tmp_path
    )

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    log = tmp_path / "state" / "rag-enforce.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    assert "Failed to read transcript tail" not in text, (
        f"a {type(transcript_path).__name__} transcript_path was logged as a read "
        f"failure instead of being read as absent. log:\n{text}"
    )


@pytest.mark.parametrize("line", TRANSCRIPT_LINES_THAT_ARE_NOT_USABLE)
def test_hook_exits_zero_on_a_transcript_line_that_is_not_usable(line, tmp_path):
    """A short prompt is the one that reaches the transcript, so a single
    unreadable line in it must be skipped, not crash the message the human is
    waiting on."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(line + "\n", encoding="utf-8")

    code, err = run_hook(
        {"session_id": "transcript-session", "prompt": "fix", "transcript_path": str(transcript)},
        tmp_path,
    )

    assert code == 0, f"hook exited {code} on transcript line {line!r}. stderr:\n{err}"
    assert "Traceback" not in err, f"hook crashed on transcript line {line!r}. stderr:\n{err}"


def test_an_unusable_transcript_line_does_not_hide_a_later_assistant_message(tmp_path):
    """Skipping the bad line must not mean skipping the rest of the file. The
    assistant text after it is the whole reason the transcript is read."""
    module = load_rag_enforce()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "42\n"
        '{"message": ["not", "an", "object"]}\n'
        '{"message": {"role": "assistant", "content": "the hook registration bit"}}\n',
        encoding="utf-8",
    )

    assert module._get_recent_context(str(transcript)) == "the hook registration bit"


@pytest.mark.parametrize(
    "value",
    [42, ["/some/path"], {"path": "/some/path"}, True, None],
)
def test_str_field_reads_a_mistyped_value_as_empty(value):
    """The helper the field reads go through. Anything that is not a string
    reads as "", which is the same thing an absent field already means."""
    module = load_rag_enforce()

    assert module._str_field({"prompt": value}, "prompt") == ""
    assert module._str_field({"prompt": "real text"}, "prompt") == "real text"
    assert module._str_field({}, "prompt") == ""
    assert module._str_field(value, "prompt") == ""


# Valid JSON, none of it an object. Each parses without error and then has no
# .get, so reading a field off it raises AttributeError.
PAYLOADS_THAT_ARE_NOT_OBJECTS = [
    pytest.param("[1,2,3]", id="json-array"),
    pytest.param("42", id="json-number"),
    pytest.param('"just a string"', id="json-string"),
    pytest.param("null", id="json-null"),
    pytest.param("true", id="json-bool"),
]

# Stdin that never becomes JSON at all.
STDIN_THAT_IS_NOT_JSON = [
    pytest.param(b"", id="empty-stdin"),
    pytest.param(b"not json at all", id="unparseable-text"),
    pytest.param(b"\xff\xfe\x00bad", id="not-utf8"),
]


@pytest.mark.parametrize("raw", PAYLOADS_THAT_ARE_NOT_OBJECTS)
def test_hook_exits_zero_on_json_that_is_not_an_object(raw, tmp_path):
    """The hook's own header promises "0 = always (UserPromptSubmit hooks
    cannot block)". These five payloads broke that promise: each one parsed
    fine, then died on .get with an uncaught AttributeError and exit 1, which
    surfaces a traceback on a message the human is waiting on."""
    code, err = run_hook_raw(raw, tmp_path)

    assert code == 0, f"hook exited {code} on stdin {raw!r}. stderr:\n{err}"
    assert "Traceback" not in err, f"hook crashed on stdin {raw!r}. stderr:\n{err}"


@pytest.mark.parametrize("raw", STDIN_THAT_IS_NOT_JSON)
def test_hook_exits_zero_on_stdin_that_is_not_json(raw, tmp_path):
    """The other half of the same contract, pinned so a later change to the
    payload reader cannot regress it while fixing the shape above."""
    code, err = run_hook_raw(raw, tmp_path)

    assert code == 0, f"hook exited {code} on stdin {raw!r}. stderr:\n{err}"
    assert "Traceback" not in err, f"hook crashed on stdin {raw!r}. stderr:\n{err}"


def test_json_that_is_not_an_object_cannot_clear_a_sticky_quick_flag(monkeypatch, tmp_path):
    """A payload with no object around it carries no session and no prompt, so
    the /start text inside it is not the human asking for anything. Reading it
    as one would delete a /ps set moments earlier."""
    session = "bare-string-start-session"
    set_sticky_quick(monkeypatch, tmp_path, session)

    code, err = run_hook_raw('"/start build the thing"', tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is True, (
        "text inside a payload that is not an object was read as /start and "
        "cleared the sticky /ps."
    )


@pytest.mark.parametrize("session", ["", "bare-string-ps-session"])
def test_json_that_is_not_an_object_cannot_set_the_quick_flag(session, monkeypatch, tmp_path):
    """The dangerous direction of the same case. Turning the skip on disables
    the research gate and the verifier for ten minutes, so a payload shape
    Claude Code never sends must not be able to reach it. Checked for the empty
    session id as well, since that is the one an empty payload resolves to."""
    code, err = run_hook_raw('"/ps typo"', tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    assert is_sticky_quick(monkeypatch, tmp_path, session) is False, (
        f"text inside a payload that is not an object marked session "
        f"{session!r} quick."
    )


@pytest.mark.parametrize(
    "raw",
    ["[1,2,3]", "42", '"just a string"', "null", "true", "not json at all", ""],
)
def test_read_hook_payload_always_returns_a_dict(raw, monkeypatch):
    """The guard belongs at the boundary that produces the payload, not at each
    field read. main() reads prompt, session_id and transcript_path off this
    result, and every one of them assumes .get exists."""
    module = load_rag_enforce()
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))

    payload = module._read_hook_payload()

    assert isinstance(payload, dict), f"stdin {raw!r} produced {type(payload).__name__}"


def test_a_well_formed_payload_still_opens_a_turn_record(monkeypatch, tmp_path):
    """Guarding the payload shape must not cost the hook its actual job. An
    ordinary message still has to open the turn record that the research gate
    and the verifier both read."""
    session = "ordinary-turn-session"

    code, err = run_hook({"session_id": session, "prompt": "rename the variable"}, tmp_path)

    assert code == 0, f"hook exited {code}. stderr:\n{err}"
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    record_path = research_state._record_path(session)
    assert record_path.exists(), "no turn record was written for an ordinary message"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["session_id"] == session
    assert record["prompt_preview"] == "rename the variable"


# The payload boundary and the transcript boundary both got a type guard. The
# server's own answers are the same kind of value and were read the same unsafe
# way: _git_project_context() walked `.get()` twice into whatever /status
# returned, outside the try/except that wrapped only the request, and every item
# /search returned reached `.get()` with no guard at all. A throwaway local HTTP
# server stands in for clean-rag below, so these drive the real script as a
# subprocess against a real socket rather than testing a helper in isolation.
#
# Exit 0 is necessary but not sufficient, so the shape lists below are paired
# with tests that pin what the hook still DOES when a response is unreadable.
# A blanket try/except around main() would pass every exit-code case here and
# fail those, which is the point: the guards have to degrade, not blank out.
REPO_ROOT = Path(__file__).resolve().parent.parent

HEALTHY_STATUS = {"status": "ready", "projects": {"count": 0, "entries": {}}}


def _fake_clean_rag(status_body: bytes, search_body: bytes):
    """A handler answering /status and /search with exactly the bytes given.

    Bytes, not objects, because several of the shapes under test are not
    JSON at all and cannot be expressed as a Python value.
    """

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self._send(status_body if self.path == "/status" else b"{}")

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self._send(search_body if self.path == "/search" else b"{}")

        def _send(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    return Handler


@contextlib.contextmanager
def _fake_server(status_body=b"{}", search_body=b"{}"):
    server = http.server.HTTPServer(("127.0.0.1", 0), _fake_clean_rag(status_body, search_body))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        thread.join(timeout=5)


def run_hook_against_server(port, home, prompt, transcript_path=None):
    """Drive the real hook with a fake clean-rag on `port`.

    cwd is the repo root so the hook finds a real git root, which is what makes
    the /status project-index branch run at all.
    """
    env = dict(os.environ)
    env["CLEAN_RAG_HOME"] = str(home)
    env["CLEAN_RAG_PORT"] = str(port)
    payload = {"session_id": "s", "prompt": prompt}
    if transcript_path is not None:
        payload["transcript_path"] = str(transcript_path)
    proc = subprocess.run(
        [sys.executable, str(RAG_ENFORCE)],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=60,
    )
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


def j(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# A prompt with three or more real keywords, so main() runs the whole way to
# /search instead of stopping at the no-keywords branch.
SEARCHING_PROMPT = "please refactor the authentication module today"


# Every shape /status can come back as. The server's word for its own state is
# not a contract: it can be any JSON type, and so can each level walked out of
# it (`projects`, `entries`, an entry, that entry's `project_path`).
STATUS_SHAPES = [
    pytest.param(b"null", id="status-null"),
    pytest.param(b"42", id="status-number"),
    pytest.param(b'"ready"', id="status-string"),
    pytest.param(b"[1,2,3]", id="status-array"),
    pytest.param(b"true", id="status-bool"),
    pytest.param(b"", id="status-empty-body"),
    pytest.param(b"<html>502</html>", id="status-not-json"),
    pytest.param(j({"status": "ready", "projects": 5}), id="projects-number"),
    pytest.param(j({"status": "ready", "projects": None}), id="projects-null"),
    pytest.param(j({"status": "ready", "projects": {"entries": [1, 2]}}), id="entries-array"),
    pytest.param(j({"status": "ready", "projects": {"entries": "abc"}}), id="entries-string"),
    pytest.param(j({"status": "ready", "projects": {"entries": None}}), id="entries-null"),
    pytest.param(j({"status": "ready", "projects": {"entries": {"a": 7}}}), id="entry-number"),
    pytest.param(
        j({"status": "ready", "projects": {"entries": {"a": {"project_path": 42}}}}),
        id="project-path-number",
    ),
    pytest.param(
        j({"status": "ready", "projects": {"entries": {"a": {"project_path": None}}}}),
        id="project-path-null",
    ),
]


@pytest.mark.parametrize("status_body", STATUS_SHAPES)
def test_hook_exits_zero_for_every_status_response_shape(status_body, tmp_path):
    """The file's own header says its exit code is "0 = always". /status is a
    socket read, so every level of it is untrusted: a bare `null` body crashed
    on `.get`, an `entries` that is a list crashed on `.values()`, and a
    `project_path` that is a number crashed inside Path()."""
    with _fake_server(status_body=status_body) as port:
        code, _, err = run_hook_against_server(port, tmp_path, "fix the bug")

    assert code == 0, f"hook exited {code} on this /status body. stderr:\n{err}"


def test_a_status_response_that_is_not_an_object_does_not_crash_the_hook(tmp_path):
    """The exact reported repro, kept under its own name so the regression it
    stands for stays traceable. /status was read the same way the payload used
    to be: `.get()` on whatever came back, with no isinstance guard. Valid JSON
    that is not an object (a bare `null`) reached that `.get()` outside the
    try/except that wrapped only the request and the parse."""
    with _fake_server(status_body=b"null") as port:
        code, _, err = run_hook_against_server(port, tmp_path, "fix the bug")

    assert code == 0, f"hook exited {code} on a /status body of `null`. stderr:\n{err}"


def test_search_results_whose_items_are_not_dicts_do_not_crash_the_hook(tmp_path):
    """The other half of the same gap, also kept by name: main() handed
    whatever /search returned straight to _rerank_results(), which called
    `.get()` on each item. An item that is an int raised AttributeError."""
    search = j({"results": [1, 2, 3], "web_search_results": []})
    with _fake_server(status_body=j(HEALTHY_STATUS), search_body=search) as port:
        code, _, err = run_hook_against_server(port, tmp_path, SEARCHING_PROMPT)

    assert code == 0, f"hook exited {code} on /search results that are not dicts. stderr:\n{err}"


def test_an_unreadable_status_still_opens_the_turn_record(tmp_path, monkeypatch):
    """Degraded, not dead. The turn record is what the research gate and the
    verifier read, and it does not depend on /status at all, so a malformed
    status must not cost the turn its record. This is the test a blanket
    try/except around main() would fail."""
    with _fake_server(status_body=b"null") as port:
        code, _, _ = run_hook_against_server(port, tmp_path, "fix the bug")
    assert code == 0

    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    record_path = research_state._record_path("s")
    assert record_path.exists(), "a malformed /status cost the turn its record entirely"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["prompt_preview"] == "fix the bug"


def test_an_unreadable_status_does_not_claim_the_project_is_indexed(tmp_path):
    """The two ways to guess are both wrong. Claiming "indexed" hides a missing
    index behind a reassuring line, and claiming "not indexed" queues a
    background indexing subprocess off a response nobody could parse. Saying
    nothing is the honest answer, and it matches what a failed request does."""
    with _fake_server(status_body=b"null") as port:
        code, out, _ = run_hook_against_server(port, tmp_path, "fix the bug")

    assert code == 0
    assert "## Project Context" not in out, (
        f"an unreadable /status still made a claim about the index:\n{out}"
    )


def test_a_healthy_status_still_reports_an_indexed_project(tmp_path):
    """The positive control for the guard above. Guards that turn every answer
    into silence would pass every test on this page except this one.

    files_indexed is part of a well formed entry, not decoration: the hook
    reports a project as indexed only when a row also carries a real count, so
    an entry without one belongs in the negative control below, not here. Every
    row the server writes has the field (server/app.py sets it alongside
    chunks_created and indexed_at), so this is what a healthy answer looks
    like."""
    status = j({
        "status": "ready",
        "projects": {
            "count": 1,
            "entries": {"a": {"project_path": str(REPO_ROOT), "files_indexed": 42}},
        },
    })
    with _fake_server(status_body=status) as port:
        code, out, _ = run_hook_against_server(port, tmp_path, "fix the bug")

    assert code == 0
    assert "is indexed" in out, f"a healthy /status stopped reporting the index:\n{out}"


def test_a_status_entry_with_no_file_count_is_not_treated_as_indexed(tmp_path):
    """The negative control the positive one above is only meaningful against.

    A registry row is a claim that a project exists, not evidence it holds any
    data: rows have turned up carrying files_indexed 0, a null indexed_at and no
    directory on disk, left behind by a registration that never indexed
    anything. Matching on path alone reported such a project as searchable and
    stopped queueing it, so every search over it came back empty with nothing
    to say why. Absent has to read the same as zero, and the turn has to fall
    through to the queue-indexing branch rather than go quiet."""
    status = j({
        "status": "ready",
        "projects": {"count": 1, "entries": {"a": {"project_path": str(REPO_ROOT)}}},
    })
    with _fake_server(status_body=status) as port:
        code, out, _ = run_hook_against_server(port, tmp_path, "fix the bug")

    assert code == 0
    assert "is indexed" not in out, (
        f"a row with no file count behind it was reported as indexed:\n{out}"
    )
    assert "not indexed yet" in out, (
        f"the row was not reported as indexed, but the turn went quiet instead "
        f"of reaching the queue-indexing branch:\n{out}"
    )


def test_a_healthy_status_with_no_projects_still_queues_indexing(tmp_path):
    """An empty entries map is a real answer, not a broken one: the server's
    _list_projects() returns {} when the registry does not exist yet. That
    first-run case has to keep reaching the "queue indexing" branch, so the
    unreadable-status guard must not treat empty as unreadable."""
    with _fake_server(status_body=j(HEALTHY_STATUS)) as port:
        code, out, _ = run_hook_against_server(port, tmp_path, "fix the bug")

    assert code == 0
    assert "not indexed yet" in out, f"the first-run indexing branch stopped firing:\n{out}"


# Every shape /search can come back as, given a healthy /status. "results" can
# be any JSON type, each item in it can be any type, and each field read off an
# item (score, file, content, topic) can be any type.
SEARCH_SHAPES = [
    pytest.param(b"null", id="search-null"),
    pytest.param(b"42", id="search-number"),
    pytest.param(b"[1,2,3]", id="search-array"),
    pytest.param(b"", id="search-empty-body"),
    pytest.param(j({"results": 5}), id="results-number"),
    pytest.param(j({"results": "abc"}), id="results-string"),
    pytest.param(j({"results": None}), id="results-null"),
    pytest.param(j({"results": [1, 2, 3]}), id="results-items-numbers"),
    pytest.param(j({"results": [[1], [2]]}), id="results-items-arrays"),
    pytest.param(j({"results": [None]}), id="results-items-null"),
    pytest.param(j({"results": [{"score": "high", "content": "x", "file": "y"}]}), id="score-string"),
    pytest.param(j({"results": [{"score": None, "content": "x", "file": "y"}]}), id="score-null"),
    pytest.param(j({"results": [{"score": 0.9, "file": 42, "content": "x"}]}), id="file-number"),
    pytest.param(j({"results": [{"score": 0.9, "file": "y", "content": 42}]}), id="content-number"),
    pytest.param(j({"results": [{"score": 0.9, "file": "y", "content": [1]}]}), id="content-array"),
    pytest.param(
        j({"results": [{"score": 0.9, "file": "y", "content": "auth", "topic": {"a": 1}}]}),
        id="topic-object",
    ),
    pytest.param(j({"results": [], "web_search_results": 5}), id="web-results-number"),
]


@pytest.mark.parametrize("search_body", SEARCH_SHAPES)
def test_hook_exits_zero_for_every_search_response_shape(search_body, tmp_path):
    """Same contract, the other socket. _search_rag's own try/except only ever
    covered the request and the parse; the shape of what it returned escaped
    the function and crashed in _rerank_results, _format_rag_results, and the
    `{:.2f}` format of the best score."""
    with _fake_server(status_body=j(HEALTHY_STATUS), search_body=search_body) as port:
        code, _, err = run_hook_against_server(port, tmp_path, SEARCHING_PROMPT)

    assert code == 0, f"hook exited {code} on this /search body. stderr:\n{err}"


def test_a_result_that_is_not_an_object_is_dropped_without_losing_the_good_ones(tmp_path):
    """Degrade, do not blank. One unreadable item in a result set is not a
    reason to throw away the readable ones next to it, so the guard drops the
    item rather than the response."""
    search = j({
        "results": [
            1,
            {"score": 0.9, "file": "auth.py", "content": "authentication module refactor notes"},
            None,
        ]
    })
    with _fake_server(status_body=j(HEALTHY_STATUS), search_body=search) as port:
        code, out, _ = run_hook_against_server(port, tmp_path, SEARCHING_PROMPT)

    assert code == 0
    assert "Research Context" in out, f"the good result was thrown out with the bad:\n{out}"
    assert "authentication module refactor notes" in out


def test_a_search_body_that_is_not_an_object_is_logged_differently_than_a_real_empty_result_set(tmp_path_factory):
    """A response where the ENTIRE /search body is not an object (a bare
    `null`, a bare number, a bare array) currently degrades to `[], True, []`
    with NO log line distinguishing it from a real, healthy `{"results": []}`
    response. Both a broken server and a working server with nothing relevant
    to say must not look identical: only the per-item guard (`{"results":
    [1, 2, 3]}`) logs a "Dropped N" line; the whole-body case does not, even
    though it is the more severe failure of the two."""
    def messages_only(log_text: str) -> str:
        # Strip the "%(asctime)s %(levelname)s " prefix so two independent runs
        # (which always differ by wall clock time) compare on MESSAGE CONTENT,
        # not incidental timestamps.
        lines = []
        for line in log_text.splitlines():
            parts = line.split(" ", 2)
            lines.append(parts[2] if len(parts) == 3 else line)
        return "\n".join(lines)

    malformed_home = tmp_path_factory.mktemp("malformed")
    with _fake_server(status_body=j(HEALTHY_STATUS), search_body=b"null") as port:
        run_hook_against_server(port, malformed_home, SEARCHING_PROMPT)
    log_path = malformed_home / "state" / "rag-enforce.log"
    malformed_log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

    legit_home = tmp_path_factory.mktemp("legit-empty")
    with _fake_server(status_body=j(HEALTHY_STATUS), search_body=j({"results": []})) as port2:
        run_hook_against_server(port2, legit_home, SEARCHING_PROMPT)
    log_path2 = legit_home / "state" / "rag-enforce.log"
    legit_empty_log = log_path2.read_text(encoding="utf-8", errors="replace") if log_path2.exists() else ""

    assert messages_only(malformed_log) != messages_only(legit_empty_log), (
        "a /search body of `null` produced log MESSAGES identical to a real "
        "empty result set (only timestamps differ), so a broken server cannot "
        "be told apart from a working one with nothing to say:\n"
        f"--- malformed body log ---\n{malformed_log}\n"
        f"--- legit empty-results log ---\n{legit_empty_log}"
    )
    assert all(t in malformed_log for t in ("ERROR", "NoneType", "not an object")), (
        "the malformed-body log line is not an error naming what actually "
        f"arrived, so it is not greppable evidence of a broken server:\n{malformed_log}"
    )
    assert "ERROR" not in legit_empty_log, (
        f"a legitimately empty result set was logged as an error:\n{legit_empty_log}"
    )


def test_a_result_whose_score_cannot_be_read_is_still_injected(tmp_path):
    """A score that is not a number is the one field that has to survive two
    different operations: the `+ boost` arithmetic in the reranker and the
    `{:.2f}` format in the output. Reading it as 0.0 sorts it last, which is
    the right place for a result whose relevance nobody can tell, but it is
    still shown rather than silently dropped."""
    search = j({"results": [{"score": "high", "file": "auth.py", "content": "authentication module notes"}]})
    with _fake_server(status_body=j(HEALTHY_STATUS), search_body=search) as port:
        code, out, _ = run_hook_against_server(port, tmp_path, SEARCHING_PROMPT)

    assert code == 0
    assert "authentication module notes" in out
    assert "relevance: 0.00" in out, f"an unreadable score was not reported as 0.00:\n{out}"


def test_a_readable_result_still_outranks_one_that_cannot_be_read(tmp_path):
    """Ranking still works across a mixed set: the result with a real score
    comes first, the one whose score reads as 0.0 comes after it."""
    search = j({
        "results": [
            {"score": None, "file": "a.py", "content": "authentication module unreadable score"},
            {"score": 0.95, "file": "b.py", "content": "authentication module readable score"},
        ]
    })
    with _fake_server(status_body=j(HEALTHY_STATUS), search_body=search) as port:
        code, out, _ = run_hook_against_server(port, tmp_path, SEARCHING_PROMPT)

    assert code == 0
    assert out.index("readable score") < out.index("unreadable score"), (
        f"the result with a real score did not rank first:\n{out}"
    )


def test_a_result_whose_content_cannot_be_read_is_not_stringified_into_the_context(tmp_path):
    """Reading an unreadable field as "" is the point, not str()-ing it. A
    content that arrives as a list would otherwise put a rendering of raw JSON
    into the injected block as though it were retrieved prose, which is text
    nobody wrote. Same rule the mistyped prompt already follows."""
    search = j({"results": [{"score": 0.9, "file": "auth.py", "content": ["authtokenmarker", 42]}]})
    with _fake_server(status_body=j(HEALTHY_STATUS), search_body=search) as port:
        code, out, _ = run_hook_against_server(port, tmp_path, SEARCHING_PROMPT)

    assert code == 0
    assert "authtokenmarker" not in out, (
        f"an unreadable content field was stringified into the injection:\n{out}"
    )


def test_a_transcript_text_block_that_is_not_a_string_does_not_crash_the_hook(tmp_path):
    """The third external boundary, reached through the payload's own
    transcript_path: a text block whose "text" is not a string reached
    " ".join() and raised TypeError."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": 42}]}}) + "\n",
        encoding="utf-8",
    )
    with _fake_server(status_body=j(HEALTHY_STATUS)) as port:
        code, _, err = run_hook_against_server(port, tmp_path, "fix it", transcript_path=transcript)

    assert code == 0, f"hook exited {code} on an unreadable transcript text block. stderr:\n{err}"


def test_an_unreadable_text_block_does_not_hide_the_text_beside_it(tmp_path):
    """Same degrade-do-not-blank rule one level down: the readable block in a
    message still contributes its text."""
    module = load_rag_enforce()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": 42},
                    {"type": "text", "text": "the hook registration bit"},
                ],
            }
        }) + "\n",
        encoding="utf-8",
    )

    # Equality, not containment: the unreadable block must contribute nothing at
    # all, rather than a str() rendering of the raw JSON sitting next to the
    # real text.
    assert module._get_recent_context(str(transcript)).strip() == "the hook registration bit"


@pytest.mark.parametrize("value", [42, "text", ["a"], True, None, 1.5])
def test_dict_field_reads_a_mistyped_value_as_an_empty_dict(value):
    """The nested-object half of the same helper family. {} is also what a
    healthy server sends when nothing is indexed, so the "nothing matched"
    path already handles it."""
    module = load_rag_enforce()

    assert module._dict_field({"projects": value}, "projects") == {}
    assert module._dict_field({"projects": {"entries": {}}}, "projects") == {"entries": {}}
    assert module._dict_field({}, "projects") == {}
    assert module._dict_field(value, "projects") == {}


@pytest.mark.parametrize("value", [42, "abc", {"a": 1}, True, None, 1.5])
def test_list_field_reads_a_mistyped_value_as_an_empty_list(value):
    """The sequence half. A string is the interesting one: it is iterable, so
    without this it iterated character by character instead of failing."""
    module = load_rag_enforce()

    assert module._list_field({"results": value}, "results") == []
    assert module._list_field({"results": [{"score": 1}]}, "results") == [{"score": 1}]
    assert module._list_field({}, "results") == []
    assert module._list_field(value, "results") == []


@pytest.mark.parametrize("value", ["high", "0.9", ["0.9"], {"nested": 1}, None])
def test_number_field_reads_a_mistyped_value_as_zero(value):
    """The numeric half, for the values this file does arithmetic and `{:.2f}`
    formatting on. A numeric string is deliberately not coerced: "0.9" is the
    server describing a score, not sending one."""
    module = load_rag_enforce()

    assert module._number_field({"score": value}, "score") == 0.0
    assert module._number_field({}, "score") == 0.0


@pytest.mark.parametrize("source", [42, "abc", ["a"], True, None, 1.5])
def test_the_field_helpers_read_a_source_that_is_not_an_object_as_empty(source):
    """All four helpers take the container itself as untrusted, so a caller
    holding a non-object gets the empty value rather than an AttributeError on
    `.get`. That is what lets a nested walk like status["projects"]["entries"]
    be written as one expression."""
    module = load_rag_enforce()

    assert module._str_field(source, "any") == ""
    assert module._dict_field(source, "any") == {}
    assert module._list_field(source, "any") == []
    assert module._number_field(source, "any") == 0.0


def test_number_field_reads_real_numbers_and_refuses_bools():
    """bool passes isinstance(x, int) in Python, and a JSON `true` is not a
    relevance score."""
    module = load_rag_enforce()

    assert module._number_field({"score": 0.75}, "score") == 0.75
    assert module._number_field({"score": 1}, "score") == 1.0
    assert module._number_field({"score": 0}, "score") == 0.0
    assert module._number_field({"score": True}, "score") == 0.0
    assert module._number_field({"score": False}, "score") == 0.0
