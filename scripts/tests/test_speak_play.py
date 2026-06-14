"""
Tests for scripts/speak-play.py (background TTS player).

Tests the pure Python logic using direct import with mocking.
Does NOT test actual audio playback or edge-tts synthesis.
"""
from __future__ import annotations

import asyncio
import ctypes as _ctypes
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("speak_play", SCRIPTS_DIR / "speak-play.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _make_text_file(tmp_path: Path, text: str = "Hello world") -> Path:
    f = tmp_path / "speech.txt"
    f.write_text(text, encoding="utf-8")
    return f


class TestSynthesize:
    def test_synthesize_calls_communicate_save(self, monkeypatch):
        """synthesize() imports edge_tts and calls communicate.save(mp3_path)."""
        mock_communicate = MagicMock()
        mock_communicate.save = AsyncMock()
        mock_edge_tts = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_communicate
        monkeypatch.setitem(sys.modules, "edge_tts", mock_edge_tts)

        asyncio.run(_mod.synthesize("hello world", "en-US-GuyNeural", "/tmp/out.mp3"))

        mock_edge_tts.Communicate.assert_called_once_with("hello world", "en-US-GuyNeural")
        mock_communicate.save.assert_called_once_with("/tmp/out.mp3")


class TestPlayMp3Windows:
    def _make_mocks(self):
        mock_windll = MagicMock()
        mock_windll.winmm.mciSendStringW.return_value = 0
        mock_windll.user32.GetAsyncKeyState.return_value = 0
        mock_buf = MagicMock()
        mock_buf.value = "stopped"
        return mock_windll, mock_buf

    def test_error_on_open_returns_immediately(self, tmp_path):
        """mciSendStringW returns non-zero on open — function returns at line 66."""
        mock_windll, mock_buf = self._make_mocks()
        mock_windll.winmm.mciSendStringW.return_value = 1

        with patch.object(_ctypes, "windll", mock_windll), \
             patch.object(_ctypes, "create_unicode_buffer", return_value=mock_buf):
            _mod.play_mp3_windows(str(tmp_path / "audio.mp3"), str(tmp_path / "stop"))

        # Only one call (the open) — never reached play
        assert mock_windll.winmm.mciSendStringW.call_count == 1

    def test_successful_open_buf_not_playing_exits_loop(self, tmp_path):
        """Normal flow: open succeeds, buf.value != 'playing' breaks loop."""
        mock_windll, mock_buf = self._make_mocks()

        with patch.object(_ctypes, "windll", mock_windll), \
             patch.object(_ctypes, "create_unicode_buffer", return_value=mock_buf):
            _mod.play_mp3_windows(str(tmp_path / "audio.mp3"), str(tmp_path / "stop"))

        # Should call stop and close at the end
        calls = [c.args[0] for c in mock_windll.winmm.mciSendStringW.call_args_list]
        assert any("stop cbtts" in c for c in calls)
        assert any("close cbtts" in c for c in calls)

    def test_stale_stop_file_cleared_before_play(self, tmp_path):
        """Stop file existing before play is cleared (lines 69-73)."""
        mock_windll, mock_buf = self._make_mocks()
        stop_file = tmp_path / "claudeboost_tts.stop"
        stop_file.write_text("stop", encoding="utf-8")

        with patch.object(_ctypes, "windll", mock_windll), \
             patch.object(_ctypes, "create_unicode_buffer", return_value=mock_buf):
            _mod.play_mp3_windows(str(tmp_path / "audio.mp3"), str(stop_file))

        assert not stop_file.exists()

    def test_stale_stop_file_unlink_exception_ignored(self, tmp_path):
        """os.unlink on stale stop file raising is silently ignored (line 72)."""
        mock_windll, mock_buf = self._make_mocks()
        stop_file = tmp_path / "stop"
        stop_file.mkdir()  # directory: os.unlink raises IsADirectoryError

        with patch.object(_ctypes, "windll", mock_windll), \
             patch.object(_ctypes, "create_unicode_buffer", return_value=mock_buf):
            _mod.play_mp3_windows(str(tmp_path / "audio.mp3"), str(stop_file))

    def test_stop_file_in_loop_breaks(self, tmp_path):
        """Stop file appearing in loop triggers break (lines 81-86)."""
        mock_windll, mock_buf = self._make_mocks()
        stop_file = tmp_path / "tts.stop"
        # Make buf.value appear as "playing" first so we enter the loop fully
        mock_buf.value = "playing"

        call_count = [0]
        original_exists = os.path.exists

        def patched_exists(path):
            call_count[0] += 1
            if str(stop_file) in str(path):
                # Return False for stale-check (before play), True in loop
                return call_count[0] > 1
            return original_exists(path)

        with patch.object(_ctypes, "windll", mock_windll), \
             patch.object(_ctypes, "create_unicode_buffer", return_value=mock_buf), \
             patch("os.path.exists", side_effect=patched_exists), \
             patch("os.unlink"), \
             patch("time.sleep"):
            _mod.play_mp3_windows(str(tmp_path / "audio.mp3"), str(stop_file))

    def test_space_key_press_breaks_loop(self, tmp_path):
        """Space key press while playing breaks loop (lines 88-90)."""
        mock_windll, mock_buf = self._make_mocks()
        mock_buf.value = "playing"

        # First call: space_was_down = False, second call: space_is_down = True
        mock_windll.user32.GetAsyncKeyState.side_effect = [0, -1, 0]

        with patch.object(_ctypes, "windll", mock_windll), \
             patch.object(_ctypes, "create_unicode_buffer", return_value=mock_buf), \
             patch("os.path.exists", return_value=False), \
             patch("time.sleep"):
            _mod.play_mp3_windows(str(tmp_path / "audio.mp3"), str(tmp_path / "stop"))

    def test_loop_stop_file_unlink_exception_ignored(self, tmp_path):
        """os.unlink of stop file in loop raising is ignored (lines 83-85)."""
        mock_windll, mock_buf = self._make_mocks()
        mock_buf.value = "playing"

        call_count = [0]
        def patched_exists(path):
            call_count[0] += 1
            return call_count[0] > 1

        def fail_unlink(path):
            raise PermissionError("cannot unlink")

        with patch.object(_ctypes, "windll", mock_windll), \
             patch.object(_ctypes, "create_unicode_buffer", return_value=mock_buf), \
             patch("os.path.exists", side_effect=patched_exists), \
             patch("os.unlink", side_effect=fail_unlink), \
             patch("time.sleep"):
            _mod.play_mp3_windows(str(tmp_path / "audio.mp3"), str(tmp_path / "stop"))


class TestPlayMp3Macos:
    def test_normal_playback_proc_exits_quickly(self, tmp_path):
        """Normal flow: Popen started, poll() returns 0 immediately (loop condition fails)."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # already finished

        with patch.object(subprocess, "Popen", return_value=mock_proc), \
             patch("os.path.exists", return_value=False):
            _mod.play_mp3_macos(str(tmp_path / "audio.mp3"), str(tmp_path / "stop"))

        mock_proc.wait.assert_called()

    def test_stale_stop_file_cleared_before_play(self, tmp_path):
        """Stop file present before play is cleared (lines 114-118)."""
        stop_file = tmp_path / "tts.stop"
        stop_file.write_text("stop", encoding="utf-8")

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc):
            _mod.play_mp3_macos(str(tmp_path / "audio.mp3"), str(stop_file))

        assert not stop_file.exists()

    def test_stale_stop_file_unlink_exception_ignored(self, tmp_path):
        """Stale stop file unlink raising is silently ignored (line 117)."""
        stop_file = tmp_path / "stop"
        stop_file.mkdir()  # directory: unlink raises

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0

        with patch.object(subprocess, "Popen", return_value=mock_proc), \
             patch("os.path.exists", return_value=False):
            _mod.play_mp3_macos(str(tmp_path / "audio.mp3"), str(stop_file))

    def test_stop_file_appears_during_playback(self, tmp_path):
        """Stop file appears in loop → proc.terminate(), break (lines 130-135)."""
        stop_file = tmp_path / "tts.stop"

        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, None, 0]

        call_count = [0]
        original_exists = os.path.exists

        def patched_exists(path):
            call_count[0] += 1
            if str(stop_file) in str(path):
                return call_count[0] > 2  # False for pre-play, True in loop
            return original_exists(path)

        with patch.object(subprocess, "Popen", return_value=mock_proc), \
             patch("os.path.exists", side_effect=patched_exists), \
             patch("os.unlink"), \
             patch("time.sleep"):
            _mod.play_mp3_macos(str(tmp_path / "audio.mp3"), str(stop_file))

        mock_proc.terminate.assert_called()

    def test_stop_file_unlink_exception_during_playback_ignored(self, tmp_path):
        """os.unlink of stop file during loop raising is ignored (line 132)."""
        stop_file = tmp_path / "tts.stop"

        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]

        call_count = [0]
        def patched_exists(path):
            call_count[0] += 1
            return call_count[0] > 1

        def fail_unlink(path):
            raise PermissionError("cannot unlink")

        with patch.object(subprocess, "Popen", return_value=mock_proc), \
             patch("os.path.exists", side_effect=patched_exists), \
             patch("os.unlink", side_effect=fail_unlink), \
             patch("time.sleep"):
            _mod.play_mp3_macos(str(tmp_path / "audio.mp3"), str(stop_file))

    def test_timeout_expired_kills_proc(self, tmp_path):
        """proc.wait TimeoutExpired causes proc.kill() (lines 140-141)."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="afplay", timeout=2)

        with patch.object(subprocess, "Popen", return_value=mock_proc), \
             patch("os.path.exists", return_value=False):
            _mod.play_mp3_macos(str(tmp_path / "audio.mp3"), str(tmp_path / "stop"))

        mock_proc.kill.assert_called()


class TestMainFunction:
    def test_main_too_few_args_returns_1(self):
        """main() with < 3 args returns 1 (line 146)."""
        sys.argv = ["speak-play.py", "only-one-arg"]
        result = _mod.main()
        assert result == 1

    def test_main_windows_flow_calls_play(self, tmp_path):
        """main() on Windows calls play_mp3_windows when synthesis succeeds."""
        text_file = _make_text_file(tmp_path)

        with patch.object(_mod, "IS_WINDOWS", True), \
             patch.object(_mod, "IS_MACOS", False), \
             patch.object(_mod, "play_mp3_windows", MagicMock()), \
             patch("asyncio.run", lambda coro: None):
            sys.argv = ["speak-play.py", str(text_file), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 0

    def test_main_macos_flow_calls_play(self, tmp_path):
        """main() on macOS calls play_mp3_macos when synthesis succeeds."""
        text_file = _make_text_file(tmp_path)

        with patch.object(_mod, "IS_WINDOWS", False), \
             patch.object(_mod, "IS_MACOS", True), \
             patch.object(_mod, "play_mp3_macos", MagicMock()), \
             patch("asyncio.run", lambda coro: None):
            sys.argv = ["speak-play.py", str(text_file), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 0

    def test_main_linux_exits_0_immediately(self, tmp_path):
        """main() on Linux (not Windows/macOS) returns 0 immediately."""
        text_file = _make_text_file(tmp_path)

        with patch.object(_mod, "IS_WINDOWS", False), \
             patch.object(_mod, "IS_MACOS", False):
            sys.argv = ["speak-play.py", str(text_file), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 0

    def test_main_text_file_unreadable_returns_1(self, tmp_path):
        """Text file that cannot be read causes main() to return 1 (lines 168-169)."""
        bad_path = tmp_path / "nofile.txt"  # does not exist

        with patch.object(_mod, "IS_WINDOWS", True), \
             patch.object(_mod, "IS_MACOS", False):
            sys.argv = ["speak-play.py", str(bad_path), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 1

    def test_main_pid_file_write_exception_silently_ignored(self, tmp_path):
        """PID file write fails silently when pid_file path is a directory (lines 162-163)."""
        text_file = _make_text_file(tmp_path)
        pid_dir = tmp_path / _mod.PID_FILE_NAME
        pid_dir.mkdir()

        with patch.object(_mod, "IS_WINDOWS", True), \
             patch.object(_mod, "IS_MACOS", False), \
             patch.object(_mod, "play_mp3_windows", MagicMock()), \
             patch("asyncio.run", lambda coro: None):
            sys.argv = ["speak-play.py", str(text_file), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 0

    def test_main_text_path_unlink_exception_silently_ignored(self, tmp_path):
        """text_path.unlink exception is silently ignored (lines 173-174)."""
        text_file = _make_text_file(tmp_path)

        def fake_unlink(*args, **kwargs):
            raise PermissionError("cannot unlink")

        with patch.object(_mod, "IS_WINDOWS", True), \
             patch.object(_mod, "IS_MACOS", False), \
             patch.object(_mod, "play_mp3_windows", MagicMock()), \
             patch("asyncio.run", lambda coro: None), \
             patch.object(Path, "unlink", fake_unlink):
            sys.argv = ["speak-play.py", str(text_file), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 0

    def test_main_play_exception_silently_ignored(self, tmp_path):
        """play_mp3_windows raising is silently ignored (lines 191-192)."""
        text_file = _make_text_file(tmp_path)

        with patch.object(_mod, "IS_WINDOWS", True), \
             patch.object(_mod, "IS_MACOS", False), \
             patch.object(_mod, "play_mp3_windows", side_effect=RuntimeError("play failed")), \
             patch("asyncio.run", lambda coro: None):
            sys.argv = ["speak-play.py", str(text_file), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 0

    def test_main_synthesis_exception_returns_1(self, tmp_path):
        """asyncio.run raising (synthesis failure) exits with code 1."""
        text_file = _make_text_file(tmp_path)

        with patch.object(_mod, "IS_WINDOWS", True), \
             patch.object(_mod, "IS_MACOS", False), \
             patch("asyncio.run", side_effect=RuntimeError("edge-tts failed")):
            sys.argv = ["speak-play.py", str(text_file), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 1

    def test_main_empty_text_returns_0(self, tmp_path):
        """Empty text file returns 0 without calling synthesize."""
        text_file = tmp_path / "empty.txt"
        text_file.write_text("   ", encoding="utf-8")

        with patch.object(_mod, "IS_WINDOWS", True), \
             patch.object(_mod, "IS_MACOS", False), \
             patch("asyncio.run") as mock_run:
            sys.argv = ["speak-play.py", str(text_file), "en-US-GuyNeural", str(tmp_path)]
            result = _mod.main()

        assert result == 0
        mock_run.assert_not_called()

    def test_main_guard_covers_sys_exit(self):
        """Running as __main__ with too few args exits 1 (covers line 204)."""
        import subprocess as _sp
        result = _sp.run(
            [sys.executable, str(SCRIPTS_DIR / "speak-play.py"), "only-one-arg"],
            capture_output=True,
        )
        assert result.returncode == 1


class TestSpeedPlayRemainingLines:
    """Covers lines 97 (Windows sleep loop) and 117-118 (macOS unlink exception)."""

    def _make_win_mocks(self):
        from unittest.mock import MagicMock
        import ctypes as _ctypes
        mock_windll = MagicMock()
        mock_windll.winmm.mciSendStringW.return_value = 0
        mock_windll.user32.GetAsyncKeyState.return_value = 0
        mock_buf = MagicMock()
        return mock_windll, mock_buf

    def test_windows_loop_sleeps_when_still_playing(self, tmp_path):
        """Line 97: buf.value == 'playing' on first iteration -> time.sleep called."""
        import ctypes as _ctypes
        from unittest.mock import patch, MagicMock, call
        import sys

        mod_spec = __import__("importlib").util.spec_from_file_location(
            "speak_play", Path(__file__).resolve().parent.parent / "speak-play.py"
        )
        _mod = __import__("importlib").util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(_mod)

        mock_windll = MagicMock()
        mock_windll.winmm.mciSendStringW.return_value = 0
        mock_windll.user32.GetAsyncKeyState.return_value = 0

        # Make buf.value return "playing" first, then "stopped"
        mock_buf = MagicMock()
        values = iter(["playing", "stopped"])
        type(mock_buf).value = property(lambda self: next(values, "stopped"))

        sleep_calls = []
        with patch.object(_ctypes, "windll", mock_windll),              patch.object(_ctypes, "create_unicode_buffer", return_value=mock_buf),              patch("time.sleep", side_effect=lambda t: sleep_calls.append(t)):
            _mod.play_mp3_windows(str(tmp_path / "audio.mp3"), str(tmp_path / "stop"))

        assert len(sleep_calls) >= 1

    def test_macos_stale_stop_unlink_raises_silently_ignored(self, tmp_path):
        """Lines 117-118: os.unlink(stop_file) raises -> except Exception: pass."""
        from unittest.mock import patch, MagicMock
        from pathlib import Path as _P
        import sys

        mod_spec = __import__("importlib").util.spec_from_file_location(
            "speak_play2", _P(__file__).resolve().parent.parent / "speak-play.py"
        )
        _mod = __import__("importlib").util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(_mod)

        stop_file = tmp_path / "stop"
        stop_file.mkdir()  # directory: os.unlink raises IsADirectoryError

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.poll.return_value = 0

        with patch("subprocess.Popen", return_value=mock_proc),              patch("time.sleep"):
            _mod.play_mp3_macos(str(tmp_path / "audio.mp3"), str(stop_file))
        # Should not raise; exception on unlink is swallowed
