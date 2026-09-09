"""A prompt outside the machine's default code page must not stall chat-watcher.

answer_question() sends the prompt to the CLI on stdin. A pipe opened in text
mode without a named encoding falls back to locale.getpreferredencoding(False),
which is cp1252 on a typical Windows machine and ASCII under LANG=C, not UTF-8.
context_code is "the literal text of a diff hunk" per chat-watcher's own
docstring, and diff hunks routinely carry characters cp1252 cannot represent:
arrows, checkmarks, CJK identifiers, emoji, smart quotes from a pasted source.

Run this repo's own suite through the same path with a plain ASCII prompt and
nothing looks wrong. The break only shows up with a real subprocess and a real
narrow-encoding stdin pipe, which is why this spawns one rather than standing a
fake process in the way the rest of test_chat_watcher.py does.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from helpers import SCRIPTS_DIR, hook_env

WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="cp1252 default is a Windows-only fallback")

_REPRO = textwrap.dedent(r"""
    import importlib.util
    import os
    import sys
    from pathlib import Path

    scripts_dir = Path(sys.argv[1])
    scratch = Path(sys.argv[2])
    sys.path.insert(0, str(scripts_dir))

    # findstr lives in System32 and is what actually blocks on stdin below --
    # drop System32 from PATH and findstr never launches, the child never
    # blocks reading stdin, and the hang this test is proving does not occur.
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    shim = scratch / "claude.cmd"
    shim.write_text('@echo off\r\nfindstr "^" >nul\r\necho answered\r\n', encoding="ascii")
    os.environ["PATH"] = str(scratch) + os.pathsep + system_root + os.pathsep + str(Path(system_root) / "System32")

    spec = importlib.util.spec_from_file_location("chat_watcher", scripts_dir / "chat-watcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # RIGHTWARDS ARROW (U+2192) is not representable in cp1252 and is ordinary
    # in a diff. The lone surrogate is what json.loads() produces from a
    # "\ud800" escape in the chat file, and no UTF-8 codec can encode one, so
    # naming an encoding without an errors policy still fails on this half.
    answer = mod.answer_question("does this arrow render: → and \ud800 ?", "", "")
    print("OK:", answer)
""")


@WINDOWS_ONLY
def test_a_non_cp1252_character_in_the_prompt_does_not_stall_the_watcher(tmp_path):
    """Reproduces with a real subprocess; the test itself stays bounded.

    The bug under test: the child's stdin writer thread dies with
    UnicodeEncodeError before it can close stdin, so the child never sees EOF.
    subprocess.run's timeout does fire on schedule, and then run() collects
    output with a second communicate() carrying no timeout, which waits on
    pipes the orphaned grandchild still holds. Measured at 851 seconds against
    a declared 60, or 94% of the watcher's whole 15-minute lifetime. Proving
    that safely means giving the reproduction a hard external bound and
    reaping it, since letting the stall run for real would cost this suite the
    same 851 seconds.

    PYTHONUTF8 is pinned off rather than inherited: UTF-8 mode makes
    locale.getpreferredencoding() return utf-8, which hides the bug entirely
    and would leave this passing on the developer's machine for the wrong
    reason.
    """
    repro_script = tmp_path / "repro.py"
    repro_script.write_text(_REPRO, encoding="utf-8")
    env = hook_env({"PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8"})

    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, str(repro_script), str(SCRIPTS_DIR), str(tmp_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        out, err = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        # The direct child (this repro's own python.exe) can be killed, but it
        # already spawned cmd.exe -> findstr underneath it, and killing the
        # parent does not take those with it on Windows. Reap the whole tree
        # so a proven-real stall does not also leak an orphaned findstr.
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
        )
        pytest.fail(
            "answer_question() stalled on a prompt holding U+2192 and a lone "
            "surrogate. The stdin pipe needs encoding='utf-8' AND a non-strict "
            "errors= policy: surrogateescape does not help, since it refuses a "
            "lone surrogate the same way strict does."
        )

    assert "OK: answered" in out, (proc.returncode, out, err)
    # Not "eventually". The old shape also finished eventually, 851 seconds in.
    assert time.monotonic() - started < 20
