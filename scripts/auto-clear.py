"""
ClaudeBoost auto-clear — Stop command hook.

When /clear-safe writes state/auto-clear-pending.json, this hook injects
/clear into the terminal after Claude finishes responding. The user types
/clear-safe once — that's it.

Injection methods:
  - tmux ($TMUX set): tmux send-keys
  - Windows (no tmux): ctypes SendInput to inject hardware-level keystrokes
    into the foreground window (no message pump required, no PowerShell)

The flag is one-shot: deleted immediately on first check regardless of
whether injection succeeds, so it never fires twice.

Stale guard: flags older than MAX_AGE_SECONDS are discarded silently.

Exit codes:
  0 = always (this hook never blocks)
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MAX_AGE_SECONDS = 300  # 5 minutes

# Windows API flags
_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200

# Windows virtual key codes
_VK_RETURN = 0x0D
_KEYEVENTF_UNICODE = 0x0004
_KEYEVENTF_KEYUP = 0x0002
_INPUT_KEYBOARD = 1


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("_input", _INPUT_UNION),
    ]


def _send_char(user32: ctypes.WinDLL, char: str) -> None:
    """Send a single Unicode character via SendInput (key down + key up)."""
    inp = _INPUT()
    inp.type = _INPUT_KEYBOARD
    inp._input.ki.wVk = 0
    inp._input.ki.wScan = ord(char)
    inp._input.ki.dwFlags = _KEYEVENTF_UNICODE
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    inp._input.ki.dwFlags = _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _send_vk(user32: ctypes.WinDLL, vk: int) -> None:
    """Send a virtual key press via SendInput (key down + key up)."""
    inp = _INPUT()
    inp.type = _INPUT_KEYBOARD
    inp._input.ki.wVk = vk
    inp._input.ki.wScan = 0
    inp._input.ki.dwFlags = 0
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    inp._input.ki.dwFlags = _KEYEVENTF_KEYUP
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _restore_focus(user32: ctypes.WinDLL, kernel32: ctypes.WinDLL, hwnd: int) -> None:
    """Force focus back to a specific window, even if the user clicked away.

    Uses AttachThreadInput so SetForegroundWindow succeeds across processes.
    """
    try:
        cur_tid = kernel32.GetCurrentThreadId()
        tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)
        user32.AttachThreadInput(cur_tid, tgt_tid, True)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.AttachThreadInput(cur_tid, tgt_tid, False)
    except Exception:
        pass


def _sendinput_win(text: str, hwnd: int) -> bool:
    """Restore focus to hwnd, then inject text + Enter via SendInput.

    Capturing hwnd at hook-start and restoring it here ensures keystrokes
    always land in the Claude Code terminal — even if the user clicked
    somewhere else during the delay.

    Returns True on success, False on any failure.
    """
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        _restore_focus(user32, kernel32, hwnd)
        time.sleep(0.1)  # brief pause after focus restore
        for char in text:
            _send_char(user32, char)
            time.sleep(0.01)
        _send_vk(user32, _VK_RETURN)
        return True
    except Exception:
        return False


def _sendinput_win_delayed(text: str, hwnd: int, delay_seconds: int) -> None:
    """Restore focus to hwnd and send text + Enter after a delay (background).

    Passes hwnd to the child process so the rename lands in the right terminal
    even if the user has moved focus elsewhere by the time it fires.
    """
    script = (
        "import ctypes,ctypes.wintypes,time;"
        "u=ctypes.windll.user32;k=ctypes.windll.kernel32;"
        "KI=type('KI',(ctypes.Structure,),{'_fields_':["
        "('wVk',ctypes.wintypes.WORD),('wScan',ctypes.wintypes.WORD),"
        "('dwFlags',ctypes.wintypes.DWORD),('time',ctypes.wintypes.DWORD),"
        "('dwExtraInfo',ctypes.POINTER(ctypes.c_ulong))]});"
        "UI=type('UI',(ctypes.Union,),{'_fields_':[('ki',KI)]});"
        "IN=type('IN',(ctypes.Structure,),{'_fields_':[('type',ctypes.wintypes.DWORD),('_input',UI)]});"
        f"time.sleep({delay_seconds});"
        # Restore focus to the saved hwnd
        f"hw={hwnd};"
        "ct=k.GetCurrentThreadId();tt=u.GetWindowThreadProcessId(hw,None);"
        "u.AttachThreadInput(ct,tt,True);u.SetForegroundWindow(hw);u.BringWindowToTop(hw);u.AttachThreadInput(ct,tt,False);"
        "time.sleep(0.1);"
    )
    for char in text:
        c = ord(char)
        script += (
            f"i=IN();i.type=1;i._input.ki.wScan={c};i._input.ki.dwFlags=4;"
            "u.SendInput(1,ctypes.byref(i),ctypes.sizeof(IN));"
            "i._input.ki.dwFlags=6;"
            "u.SendInput(1,ctypes.byref(i),ctypes.sizeof(IN));"
            "time.sleep(0.01);"
        )
    script += (
        "i=IN();i.type=1;i._input.ki.wVk=13;i._input.ki.dwFlags=0;"
        "u.SendInput(1,ctypes.byref(i),ctypes.sizeof(IN));"
        "i._input.ki.dwFlags=2;"
        "u.SendInput(1,ctypes.byref(i),ctypes.sizeof(IN));"
    )
    try:
        subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP,
        )
    except Exception:
        pass


def main() -> int:
    home = os.environ.get("CLAUDEBOOST_HOME", "")
    if not home:
        return 0

    flag_path = Path(home) / "state" / "auto-clear-pending.json"
    if not flag_path.exists():
        return 0

    try:
        flag = json.loads(flag_path.read_text(encoding="utf-8"))
    except Exception:
        flag_path.unlink(missing_ok=True)
        return 0

    # One-shot: delete immediately
    flag_path.unlink(missing_ok=True)

    # Staleness guard
    ts = flag.get("timestamp", 0.0)
    if time.time() - ts > MAX_AGE_SECONDS:
        return 0

    session_name = flag.get("session_name", "").strip()

    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "send-keys", "/clear", "Enter"], check=False)
        if session_name:
            safe_name = session_name.replace("'", "\\'")
            cmd = f"sleep 5 && tmux send-keys '/rename {safe_name}' Enter"
            subprocess.Popen(
                ["bash", "-c", cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

    elif sys.platform == "win32":
        # Capture the terminal window handle NOW, before sleeping.
        # This is the Claude Code terminal — we restore focus to it
        # before typing, so even if the user clicks elsewhere during
        # the delay, keystrokes still land in the right window.
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            # No foreground window (e.g. UAC prompt, lock screen) — can't inject.
            print(json.dumps({
                "additionalContext": "Auto-clear: no foreground window — type /clear manually to proceed."
            }))
            return 0
        time.sleep(1.5)
        ok = _sendinput_win("/clear", hwnd)
        if not ok:
            # SendInput failed (UIPI, security policy, wrong window class).
            print(json.dumps({
                "additionalContext": "Auto-clear: keystroke injection failed — type /clear manually to proceed."
            }))
            return 0
        if session_name:
            _sendinput_win_delayed(f"/rename {session_name}", hwnd, delay_seconds=5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
