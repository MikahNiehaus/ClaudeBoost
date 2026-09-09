"""
Tests for scripts/chat-watcher.py — answers chat questions via claude CLI.

We test the importable functions directly, standing a fake process in for the
claude CLI so nothing here reaches the network.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helpers import hook_env, isolate_path_to

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location("chat_watcher", SCRIPTS_DIR / "chat-watcher.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

check_and_answer = _mod.check_and_answer
answer_question = _mod.answer_question


class FakeCLI:
    """Stands in for the claude CLI process, recording what it was sent.

    Patched over subprocess.Popen. Standing in for the process rather than for
    one stdlib function is what keeps these tests off the network: the four
    that used to patch subprocess.run went on calling the real CLI the moment
    the call site stopped using that function, and still passed.
    """

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.argv: list[str] | None = None
        self.stdin_text: str | None = None

    def __call__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def communicate(self, input=None, timeout=None):
        self.stdin_text = input
        return self._stdout, self._stderr


class TestCheckAndAnswer:
    def test_skips_missing_file(self, tmp_path):
        # No file → no crash, no action
        chat_file = tmp_path / "no_chat.json"
        check_and_answer(chat_file)  # should not raise

    def test_skips_already_answered(self, tmp_path):
        chat_file = tmp_path / "chat.json"
        data = {"question": "what does this do?", "answer": "It does X", "answered_at": "2026-01-01"}
        chat_file.write_text(json.dumps(data), encoding="utf-8")
        # Should not call claude CLI — already answered
        with patch("subprocess.Popen") as mock_popen:
            check_and_answer(chat_file)
            mock_popen.assert_not_called()

    def test_skips_empty_question(self, tmp_path):
        chat_file = tmp_path / "chat.json"
        data = {"question": "", "answer": ""}
        chat_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("subprocess.Popen") as mock_popen:
            check_and_answer(chat_file)
            mock_popen.assert_not_called()

    def test_skips_invalid_json(self, tmp_path):
        chat_file = tmp_path / "chat.json"
        chat_file.write_text("NOT JSON", encoding="utf-8")
        # Should not crash
        check_and_answer(chat_file)

    def test_answers_question_and_updates_file(self, tmp_path):
        chat_file = tmp_path / "chat.json"
        data = {
            "question": "what does this function do?",
            "context_file": "src/foo.py",
            "context_code": "def foo(): pass",
            "answer": "",
            "answered_at": "",
        }
        chat_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("subprocess.Popen", FakeCLI(stdout="This function does nothing.")):
            check_and_answer(chat_file)

        updated = json.loads(chat_file.read_text(encoding="utf-8"))
        assert updated["answer"] == "This function does nothing."
        assert updated["answered_at"] != ""

    @pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe parsing is Windows only")
    def test_a_hostile_chat_file_does_not_reach_the_os(self, tmp_path, monkeypatch):
        """The whole path, from the file on disk to the process that spawns.

        The watcher polls %TEMP%\\claudeboost\\changes_chat.json, so whatever can
        write that file supplies every field below. The tests on
        answer_question cover the fields one at a time; this one runs the
        function the poll loop actually calls, so a future change that
        reintroduces the argv path anywhere between the two fails here.
        """
        shim_dir = tmp_path / "fake_bin"
        shim_dir.mkdir()
        (shim_dir / "claude.cmd").write_text("@echo off\r\necho answered\r\n", encoding="ascii")
        isolate_path_to(monkeypatch, shim_dir)

        marker = tmp_path / "pwned_by_chat_file.txt"
        payload = f'x" & echo INJECTED>{marker} & rem '
        chat_file = tmp_path / "chat.json"
        chat_file.write_text(json.dumps({
            "question": payload,
            "context_file": payload,
            "context_code": payload,
            "answer": "",
            "answered_at": "",
        }), encoding="utf-8")

        check_and_answer(chat_file)

        assert not marker.exists(), "the chat file's payload ran as a command"
        assert json.loads(chat_file.read_text(encoding="utf-8"))["answer"] == "answered"

    def test_handles_claude_cli_error(self, tmp_path, capsys):
        """A failed CLI is logged and leaves the question unanswered, not raised."""
        chat_file = tmp_path / "chat.json"
        data = {"question": "explain this code please", "answer": "", "answered_at": ""}
        chat_file.write_text(json.dumps(data), encoding="utf-8")

        with patch("subprocess.Popen", FakeCLI(stderr="boom", returncode=1)):
            check_and_answer(chat_file)  # must not raise

        assert "boom" in capsys.readouterr().out
        assert json.loads(chat_file.read_text(encoding="utf-8"))["answer"] == ""


class TestMain:
    def test_exits_1_when_claude_not_found(self):
        """main() exits 1 when 'claude --version' raises FileNotFoundError."""
        import subprocess as _sp
        with patch.object(_sp, "run", side_effect=FileNotFoundError("claude not found")):
            with pytest.raises(SystemExit) as exc:
                _mod.main()
        assert exc.value.code == 1

    @pytest.mark.skipif(sys.platform != "win32", reason="the CLI ships as claude.cmd only on Windows")
    def test_starts_when_the_cli_on_path_is_a_cmd_shim(self, tmp_path, monkeypatch, capsys):
        """The watcher must start on a normal Windows install.

        npm installs the Claude Code CLI as claude.cmd, and CreateProcess
        cannot resolve a bare "claude" in an argv list to it, so the startup
        probe used to fail and the watcher exited 1 on every Windows machine.
        Nothing is mocked here: a real claude.cmd sits on an isolated PATH and
        the probe really runs it. MAX_RUNTIME is 0 so the poll loop ends
        immediately instead of running for its usual 15 minutes.
        """
        shim_dir = tmp_path / "fake_bin"
        shim_dir.mkdir()
        (shim_dir / "claude.cmd").write_text("@echo off\r\necho 2.1.0\r\n", encoding="ascii")
        isolate_path_to(monkeypatch, shim_dir)
        assert shutil.which("claude") is not None, "test setup failed: shim not resolvable at all"
        monkeypatch.setattr(_mod, "MAX_RUNTIME", 0)

        _mod.main()  # must not SystemExit

        out = capsys.readouterr().out
        assert "not found" not in out, out
        assert "Started" in out, out

    @pytest.mark.skipif(sys.platform != "win32", reason="the CLI ships as claude.cmd only on Windows")
    def test_exits_1_when_no_cli_is_on_path(self, tmp_path, monkeypatch, capsys):
        """No CLI is still a clean exit 1, not a traceback."""
        empty = tmp_path / "empty_bin"
        empty.mkdir()
        isolate_path_to(monkeypatch, empty)
        assert shutil.which("claude") is None, "test setup failed: claude still resolvable"

        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        assert "not found" in capsys.readouterr().out

    def test_main_polls_once_then_exits(self):
        """main() completes immediately when time limit is already exceeded."""
        import subprocess as _sp
        import time as _time

        mock_result = MagicMock()
        mock_result.returncode = 0

        # First call: claude --version check (succeeds)
        # Subsequent calls: time.monotonic — first returns 0 (start), second returns MAX+1
        mono_calls = [0]
        def fake_mono():
            v = mono_calls[0]
            mono_calls[0] += _mod.MAX_RUNTIME + 2
            return float(v)

        with patch.object(_sp, "run", return_value=mock_result):
            with patch("time.monotonic", side_effect=fake_mono):
                with patch("time.sleep"):
                    _mod.main()  # should return without raising

    def test_main_executes_loop_body_once(self):
        """main() loop body executes (lines 116-118) when there is time remaining."""
        import subprocess as _sp

        mock_result = MagicMock()
        mock_result.returncode = 0

        # start=0, first check=0 (passes), second check=MAX_RUNTIME+1 (fails)
        mono_values = iter([0, 0, _mod.MAX_RUNTIME + 1])

        with patch.object(_sp, "run", return_value=mock_result), \
             patch("time.monotonic", side_effect=mono_values), \
             patch("time.sleep"), \
             patch.object(_mod, "check_and_answer"):
            _mod.main()

    def test_main_guard_via_subprocess(self):
        """The __main__ guard runs main(), through a real subprocess.

        PATH is emptied so the CLI cannot be found and main() takes its exit-1
        branch instead of entering the 15-minute poll loop.
        """
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "chat-watcher.py")],
            capture_output=True,
            env=hook_env({"PATH": ""}),
            timeout=60,
        )
        assert result.returncode == 1
        assert b"'claude' CLI not found" in result.stdout


class TestAnswerQuestion:
    def test_builds_prompt_with_context(self):
        fake = FakeCLI(stdout="Answer text")
        with patch("subprocess.Popen", fake):
            assert answer_question("what does this do?", "src/app.py", "x = 1") == "Answer text"

        assert "claude" in fake.argv[0]
        assert "src/app.py" in fake.stdin_text
        assert "x = 1" in fake.stdin_text
        assert "what does this do?" in fake.stdin_text

    @pytest.mark.skipif(sys.platform != "win32", reason="only a .cmd shim puts a grandchild on the pipes")
    def test_a_stalled_cli_fails_inside_its_declared_timeout(self, tmp_path, monkeypatch):
        """The number in CLI_TIMEOUT has to be the number that happens.

        subprocess.run() does raise TimeoutExpired on schedule, then collects
        the output Windows buffers on reader threads with a second
        communicate() that carries no timeout at all (python/cpython#87512).
        Popen.kill() reached cmd.exe only, so the CLI it launched kept the
        inherited stdout pipe open and that second call waited on it:
        measured at 39.4s against a declared 3s with this shim, and at 851s
        against the shipped 60s, which is 94% of MAX_RUNTIME.

        The shim stalls with ping, a grandchild writing to the inherited pipe,
        which is the shape that reproduces it. ping's own -n bound is what
        keeps a regression here failing slowly rather than not at all.
        """
        shim_dir = tmp_path / "fake_bin"
        shim_dir.mkdir()
        (shim_dir / "claude.cmd").write_text("@echo off\r\nping -n 30 127.0.0.1\r\n", encoding="ascii")
        isolate_path_to(monkeypatch, shim_dir)
        monkeypatch.setattr(_mod, "CLI_TIMEOUT", 3)

        start = time.monotonic()
        with pytest.raises(RuntimeError, match="gave no answer within 3s"):
            answer_question("are you there?", "", "")
        elapsed = time.monotonic() - start

        assert elapsed < 15, f"declared a 3s timeout, took {elapsed:.1f}s"

    def test_a_prompt_utf8_cannot_encode_is_reported(self, capsys):
        """A lone surrogate is sent with substitutions, and that is said out loud.

        json.loads turns a "\\ud800" escape into a real lone surrogate, and no
        UTF-8 codec can encode one. errors="replace" keeps that from killing
        the stdin writer thread mid-prompt; this is the line that stops the
        substitution from being silent.
        """
        lone_surrogate = json.loads(r'"\ud800 hunk"')
        with patch("subprocess.Popen", FakeCLI(stdout="ok")):
            assert answer_question("what is this?", "", lone_surrogate) == "ok"

        assert "UTF-8 cannot encode" in capsys.readouterr().out

    def test_raises_on_nonzero_exit(self):
        with patch("subprocess.Popen", FakeCLI(stderr="some error", returncode=1)):
            with pytest.raises(RuntimeError, match="claude -p failed"):
                answer_question("test question", "", "")

    def test_builds_prompt_without_context(self):
        fake = FakeCLI(stdout="Simple answer")
        with patch("subprocess.Popen", fake):
            assert answer_question("simple question", "", "") == "Simple answer"

        assert "File:" not in fake.stdin_text
        assert "Code:" not in fake.stdin_text

    @pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe parsing is Windows only")
    def test_a_quote_in_the_question_does_not_become_a_command(self, tmp_path, monkeypatch):
        """The question is data, never part of a command line cmd.exe parses.

        An earlier version of this test used `&` with a space around it and
        passed, which read as proof and was not: subprocess quotes an argument
        containing whitespace and `&` is inert inside quotes. A `"` is not. It
        closes the quoted region, because subprocess escapes it as `\\"` for
        CommandLineToArgvW and cmd.exe does not read a backslash that way, so
        everything after it is live shell syntax (CVE-2024-24576). On Windows
        the CLI resolves to claude.cmd and CreateProcess starts a batch target
        by running cmd.exe, so that parser is always in the path.

        The marker file is the proof: nothing in the shim writes it, so if it
        exists the payload ran as a command of its own.
        """
        shim_dir = tmp_path / "fake_bin"
        shim_dir.mkdir()
        (shim_dir / "claude.cmd").write_text("@echo off\r\necho answered\r\n", encoding="ascii")
        isolate_path_to(monkeypatch, shim_dir)

        marker = tmp_path / "pwned.txt"
        answer = answer_question(f'x" & echo INJECTED>{marker} & rem ', "", "")

        assert answer == "answered"
        assert not marker.exists(), "the question escaped its argument and ran as a command"

    @pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe parsing is Windows only")
    def test_a_quote_in_the_context_fields_does_not_become_a_command(self, tmp_path, monkeypatch):
        """Every field off the chat JSON is hostile, not just the question.

        context_file and context_code are filled from the diff under review, so
        a hunk chooses them and nobody types them. context_file is the one that
        reaches cmd.exe intact: it opens the prompt, and an argument is
        truncated at its first newline, so the later fields were out of reach
        by accident rather than by design. Both are covered here so the test
        does not depend on that accident holding.
        """
        shim_dir = tmp_path / "fake_bin"
        shim_dir.mkdir()
        (shim_dir / "claude.cmd").write_text("@echo off\r\necho answered\r\n", encoding="ascii")
        isolate_path_to(monkeypatch, shim_dir)

        from_file = tmp_path / "pwned_by_path.txt"
        assert answer_question(
            "what does this do?", f'x" & echo INJECTED>{from_file} & rem ', "code = 1"
        ) == "answered"
        assert not from_file.exists(), "context_file escaped its argument and ran as a command"

        from_code = tmp_path / "pwned_by_hunk.txt"
        assert answer_question(
            "what does this do?", "src/foo.py", f'x" & echo INJECTED>{from_code} & rem '
        ) == "answered"
        assert not from_code.exists(), "context_code escaped its argument and ran as a command"

    @pytest.mark.skipif(sys.platform != "win32", reason="batch shim is Windows only")
    def test_the_prompt_reaches_the_cli_on_stdin_and_never_in_argv(self, tmp_path, monkeypatch):
        """Not escaping: the untrusted text is off the command line entirely.

        This is the property the two tests above depend on, asserted directly
        so a future change that moves the prompt back into argv fails here
        rather than only on whichever payload someone thought to try.
        """
        shim_dir = tmp_path / "fake_bin"
        shim_dir.mkdir()
        seen_stdin = tmp_path / "seen_stdin.txt"
        seen_args = tmp_path / "seen_args.txt"
        (shim_dir / "claude.cmd").write_text(
            f'@echo off\r\nfindstr "^" > "{seen_stdin}"\r\n'
            f'echo ARGS: %* > "{seen_args}"\r\necho answered\r\n',
            encoding="ascii")
        isolate_path_to(monkeypatch, shim_dir)

        assert answer_question("why is this here?", "src/foo.py", "secret = 1") == "answered"

        assert "why is this here?" in seen_stdin.read_text()
        assert "secret = 1" in seen_stdin.read_text()
        assert "why is this here?" not in seen_args.read_text()
        assert "secret = 1" not in seen_args.read_text()
