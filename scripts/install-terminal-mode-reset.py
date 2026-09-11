"""Wire scripts/reset-terminal-modes.ps1 into the PowerShell profile.

Why this exists
---------------
Claude Code turns on xterm mouse reporting when it starts and turns it off when
it exits. A process that is KILLED never runs that cleanup, so the terminal
keeps reporting mouse positions and the shell reads them as typed input. What
you see is bursts of `^[[<35;39;1M^[[<35;40;1M...` at a bare prompt.

This is an open upstream bug in Claude Code itself, anthropics/claude-code#59720:

    "When Claude Code is killed externally while agent view is active..., the
    disable sequences for DECSET 1000/1002/1003/1006 are never emitted. The
    parent shell remains in SGR mouse-tracking mode indefinitely."

There is no client side fix and no Windows Terminal or PSReadLine setting that
compensates (microsoft/terminal#8613: a sequence that is never sent cannot be
handled). The shell is the only thing still running after the kill, so the
recovery belongs there.

Why the prompt function, and not $PROFILE's top level
-----------------------------------------------------
Microsoft's own about_prompts doc: "The prompt function determines the
appearance of the PowerShell prompt... you can override it by defining your own
prompt function", and it runs before every prompt is drawn. That is the
property that matters. Code at the top of $PROFILE runs once per shell launch,
which recovers nothing for a shell that was already open when the kill
happened, and that is the common case.

PSConsoleHostReadLine is the wrong layer: it fires per line read, not per
prompt paint.

Safety
------
Append only. The existing profile is read as bytes and written back byte for
byte with the new block after it, so nothing already in the file is re-encoded.
That matters here: the profile is on OneDrive and already contains a character
this machine round trips badly. A .bak copy is written first. Re-running is a
no op once the block is present.

Who runs this
-------------
setup.py's install_terminal_mode_reset() on Windows, and uninstall.py with
--remove, which takes the block back out between the same two markers. Run it
by hand with --remove to undo it without uninstalling anything else.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESET_SCRIPT = REPO / "scripts" / "reset-terminal-modes.ps1"

# Written into the profile so a later run can find its own block, and so a human
# reading the profile can tell where it came from.
MARKER_BEGIN = "# >>> ClaudeBoost terminal mode reset >>>"
MARKER_END = "# <<< ClaudeBoost terminal mode reset <<<"

# ASCII only, deliberately. A non ASCII character here renders as mojibake on a
# Windows console under the wrong code page, and this file is read by a human
# exactly when their terminal is already misbehaving.
BLOCK_TEMPLATE = """
{begin}
# Recover the terminal after a TUI is killed rather than exited.
#
# Claude Code, vim and lazygit enable xterm mouse reporting on start and disable
# it on exit. A killed process runs no cleanup, so the terminal keeps sending
# mouse position reports and the shell reads them as typed input. Upstream bug:
# anthropics/claude-code#59720. Nothing can fix it from inside the dead process,
# so the reset runs from the shell instead.
#
# It goes in `prompt` and not at profile top level on purpose: `prompt` runs
# before every prompt is drawn, so it also recovers a shell that was already
# open when the kill happened. Top level code runs once per launch and would
# miss exactly that case.
$__ClaudeBoostResetScript = "{reset_script}"
if (Test-Path $__ClaudeBoostResetScript) {{
    # Dot sourced once to define Reset-TerminalModes. Doing it here rather than
    # inside `prompt` keeps the per prompt cost to one function call instead of
    # re-parsing a file on every keystroke-to-prompt cycle.
    . $__ClaudeBoostResetScript

    # Keep whatever `prompt` was before this block so a custom prompt survives.
    # Guarded so re-sourcing the profile in a live session cannot capture the
    # wrapper as its own original and recurse forever.
    if (-not (Test-Path function:__ClaudeBoostOriginalPrompt)) {{
        Copy-Item function:prompt function:__ClaudeBoostOriginalPrompt -ErrorAction SilentlyContinue
    }}

    function prompt {{
        Reset-TerminalModes
        if (Test-Path function:__ClaudeBoostOriginalPrompt) {{
            __ClaudeBoostOriginalPrompt
        }} else {{
            # PowerShell's own default, reproduced so a missing original prompt
            # degrades to the normal prompt rather than to an empty one.
            "PS " + $executionContext.SessionState.Path.CurrentLocation + (">" * ($nestedPromptLevel + 1)) + " "
        }}
    }}
}}
{end}
"""


def _profile_path() -> Path | None:
    """Ask PowerShell itself where CurrentUserCurrentHost lives.

    Not constructed from $HOME: Documents is redirected to OneDrive on this
    machine, and guessing the path would write a profile nothing ever loads.
    """
    try:
        out = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "$PROFILE.CurrentUserCurrentHost",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Could not ask PowerShell for its profile path: {e}", file=sys.stderr)
        return None
    path = out.stdout.strip()
    if not path:
        print("PowerShell returned no profile path.", file=sys.stderr)
        return None
    return Path(path)


def remove() -> int:
    """Strip our own block back out, leaving the rest of the profile untouched.

    The uninstaller calls this, so the profile edit is reversible the same way
    every other thing setup.py writes outside the repo is. Only the bytes
    between the two markers go; anything the user wrote around them stays, and
    a profile without the markers is left exactly as it was.
    """
    profile = _profile_path()
    if profile is None:
        return 1
    if not profile.exists():
        print("No PowerShell profile, nothing to remove")
        return 0

    existing = profile.read_bytes()
    begin = MARKER_BEGIN.encode("utf-8")
    end = MARKER_END.encode("utf-8")
    start = existing.find(begin)
    stop = existing.find(end)
    if start == -1 or stop == -1 or stop < start:
        print(f"Block not present in {profile}, nothing to remove")
        return 0

    backup = profile.with_suffix(profile.suffix + ".bak")
    shutil.copy2(profile, backup)

    stop += len(end)
    # Take the line ending that followed the end marker with it, so removing
    # and re-adding the block does not accumulate blank lines.
    while stop < len(existing) and existing[stop:stop + 1] in (b"\r", b"\n"):
        stop += 1
    # BLOCK_TEMPLATE opens with a newline, so install put exactly one line
    # ending in front of the begin marker. Take exactly that one back, never
    # more: a blank line beyond it is the user's.
    head = existing[:start]
    for eol in (b"\r\n", b"\n"):
        if head.endswith(eol):
            head = head[:-len(eol)]
            break

    profile.write_bytes(head + existing[stop:])
    print(f"Removed the terminal mode reset from {profile} (backup: {backup})")
    return 0


def main() -> int:
    if "--remove" in sys.argv[1:]:
        return remove()

    if not RESET_SCRIPT.exists():
        print(f"Missing {RESET_SCRIPT}", file=sys.stderr)
        return 1

    profile = _profile_path()
    if profile is None:
        return 1

    existing = b""
    if profile.exists():
        existing = profile.read_bytes()
        if MARKER_BEGIN.encode("utf-8") in existing:
            print(f"Already installed in {profile}")
            return 0
        backup = profile.with_suffix(profile.suffix + ".bak")
        shutil.copy2(profile, backup)
        print(f"Backed up {profile} -> {backup}")
    else:
        profile.parent.mkdir(parents=True, exist_ok=True)

    block = BLOCK_TEMPLATE.format(
        begin=MARKER_BEGIN,
        end=MARKER_END,
        reset_script=str(RESET_SCRIPT),
    )

    # Bytes, not text, and no BOM. Set-Content -Encoding UTF8 under PowerShell
    # 5.1 writes a BOM, and appending through the text layer would re-encode
    # what is already in the file. Neither is acceptable for a file we did not
    # write and cannot re-encode safely.
    # Appended raw, with no line ending padded in front. BLOCK_TEMPLATE already
    # opens with a newline, which terminates the user's last line for us when
    # it had no terminator of its own. Padding one in here looked harmless and
    # was not: it left two line endings before the marker where a profile
    # ending in one leaves two as well, so remove() could not tell how many of
    # them were ours and gave back a file one line longer than it found.
    profile.write_bytes(existing + block.replace("\n", "\r\n").encode("utf-8"))

    print(f"Installed the terminal mode reset into {profile}")
    print("Open a new PowerShell window, or re-source your profile")
    print(f"To undo: {sys.executable} {Path(__file__).resolve()} --remove")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
