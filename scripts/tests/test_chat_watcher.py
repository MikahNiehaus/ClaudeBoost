"""
Tests for scripts/chat-watcher.py — answers chat questions via claude CLI.

We test the importable functions directly, mocking out subprocess.run for claude CLI.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location("chat_watcher", SCRIPTS_DIR / "chat-watcher.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

check_and_answer = _mod.check_and_answer
answer_question = _mod.answer_question


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
        with patch("subprocess.run") as mock_run:
            check_and_answer(chat_file)
            mock_run.assert_not_called()

    def test_skips_empty_question(self, tmp_path):
        chat_file = tmp_path / "chat.json"
        data = {"question": "", "answer": ""}
        chat_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("subprocess.run") as mock_run:
            check_and_answer(chat_file)
            mock_run.assert_not_called()

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

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "This function does nothing."
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            check_and_answer(chat_file)

        updated = json.loads(chat_file.read_text(encoding="utf-8"))
        assert updated["answer"] == "This function does nothing."
        assert updated["answered_at"] != ""

    def test_handles_claude_cli_error(self, tmp_path):
        chat_file = tmp_path / "chat.json"
        data = {"question": "explain this code please", "answer": "", "answered_at": ""}
        chat_file.write_text(json.dumps(data), encoding="utf-8")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            # Should not raise — logs error and continues
            check_and_answer(chat_file)


class TestMain:
    def test_exits_1_when_claude_not_found(self):
        """main() exits 1 when 'claude --version' raises FileNotFoundError."""
        import subprocess as _sp
        with patch.object(_sp, "run", side_effect=FileNotFoundError("claude not found")):
            with pytest.raises(SystemExit) as exc:
                _mod.main()
        assert exc.value.code == 1

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
        """Covers line 124 (if __name__ == '__main__': main()) via subprocess."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "chat-watcher.py")],
            capture_output=True,
            env={**os.environ, "PATH": ""},  # no PATH so claude not found
        )
        assert result.returncode == 1


class TestAnswerQuestion:
    def test_builds_prompt_with_context(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Answer text"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = answer_question("what does this do?", "src/app.py", "x = 1")
            assert result == "Answer text"
            # Verify claude was called
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "claude" in cmd[0]

    def test_raises_on_nonzero_exit(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "some error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="claude -p failed"):
                answer_question("test question", "", "")

    def test_builds_prompt_without_context(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Simple answer"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = answer_question("simple question", "", "")
            assert result == "Simple answer"
