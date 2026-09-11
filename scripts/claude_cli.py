"""Locate the Claude Code CLI so subprocess can actually launch it.

Why a module and not three copies
---------------------------------
`subprocess.run(["claude", ...])` passes no shell, and Windows CreateProcess
appends only ".exe" to a bare name — it never consults PATHEXT. npm installs
the CLI as three files in one directory: an extensionless `claude` shell
script, `claude.ps1`, and `claude.cmd`. None of them is `claude.exe`, so on a
completely standard Windows install `shutil.which("claude")` succeeds and the
same name in an argv list still raises FileNotFoundError [WinError 2].

Resolve the full path here instead, and hand that to subprocess. Same fix the
GitHub Copilot SDK landed for its own CLI (github/copilot-sdk#79: "Resolve the
full path on Windows (handles .cmd/.bat files)").

Windows candidates are probed extension first. shutil.which() does consult
PATHEXT, but on the 3.12 line it also matches the extensionless shell script
(python/cpython#109590), and handing THAT to subprocess raises
OSError [WinError 193] rather than launching anything — the failure reported
against Anthropic's own SDK in anthropics/claude-agent-sdk-python#252. Asking
for the extension we can launch removes the interpreter-version dependency.

No `cmd /c` wrapper: CreateProcess launches a .cmd given its full path on its
own (measured). That is convenient and it is also the trap — see below.

POSIX is the plain case — one extensionless executable named `claude`.

The batch shim re-parses your arguments, so validate them
--------------------------------------------------------
Returning `claude.cmd` hands the caller a target that CreateProcess starts by
implicitly running cmd.exe, so cmd.exe re-parses the whole command line no
matter that `shell=True` was never passed. `subprocess.list2cmdline` escapes
for CommandLineToArgvW (the C runtime convention), not for cmd.exe, and the two
disagree. That gap is BatBadBut: CVE-2024-24576 (Rust, CVSS 10.0) and
CVE-2024-27980 (Node.js). Python is not immune and bpo-34489 is still open.

Measured against a throwaway shim on this machine, an argument reaches cmd.exe
as live syntax in two distinct ways:

    '...x" & echo INJECTED>marker & rem '   ->  marker written
    'x&echo.>marker'                        ->  marker written

The first works because list2cmdline emits a literal `\\"`, and the backslash
means nothing to cmd.exe — the quote just closes the quoted region. The second
works because list2cmdline only quotes an argument containing a space or tab,
so a whitespace-free argument arrives unquoted. `%VAR%` also expands (measured:
`%USERNAME%` came back as the real username) and an embedded newline silently
truncates the argument.

Rust's answer after CVE-2024-24576 was to "return an `InvalidInput` error when
it cannot safely escape an argument" rather than to escape harder. Node's April
2024 release did the same class of thing for `child_process.spawn`. This module
follows that: `reject_unsafe_args` refuses, and callers with untrusted text
send it on stdin instead of argv, which takes it off the command line entirely.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Iterable

# Windows: only extensions CreateProcess can start, best first. A real .exe
# (native installer) skips the batch layer entirely; the npm .cmd shim is the
# common case. The extensionless npm script is deliberately absent — it is a
# shell script, so returning it would hand callers a path that cannot run.
_CANDIDATES = ("claude.exe", "claude.cmd", "claude.bat") if os.name == "nt" else ("claude",)


def claude_cmd() -> list[str] | None:
    """Argv prefix that launches the Claude Code CLI, or None when absent.

    Append the CLI's own arguments to the returned list:

        cmd = claude_cmd()
        if cmd is None:
            ...                     # CLI not installed, degrade rather than crash
        subprocess.run(cmd + ["mcp", "list"], ...)
    """
    for name in _CANDIDATES:
        path = shutil.which(name)
        if path:
            return [path]
    return None


# Extensions CreateProcess starts by handing the command line to cmd.exe.
_BATCH_SUFFIXES = (".cmd", ".bat")

# Characters measured to escape an argument on a batch target, or to change its
# value on the way in. `"` closes the quoted region; `& | < > ^` start a new
# command once the argument is unquoted, which list2cmdline leaves it whenever
# it holds no space or tab; `%` and `!` expand; a control character truncates.
# Parentheses are deliberately absent: measured inert on their own, and
# chat-watcher's own system prompt contains a pair.
_UNSAFE_IN_BATCH_ARG = frozenset('"&|<>^%!')


def is_batch_shim(executable: str) -> bool:
    """True when launching this path routes the command line through cmd.exe."""
    return executable.lower().endswith(_BATCH_SUFFIXES)


def reject_unsafe_args(cmd: list[str], args: Iterable[str]) -> None:
    """Raise ValueError for an argument cmd.exe would re-parse rather than pass.

    Call it on the arguments you are about to append to `claude_cmd()`'s result.
    A no-op when the resolved CLI is a real executable, which is every POSIX
    install and a native Windows one — there is no second parser to defend
    against there.

    This refuses; it never rewrites. An escaper for cmd.exe is the thing
    everyone gets wrong, and the caller has a better option anyway: untrusted
    text belongs on stdin, not on a command line.
    """
    if not cmd or not is_batch_shim(cmd[0]):
        return
    for arg in args:
        bad = sorted({c for c in arg if c in _UNSAFE_IN_BATCH_ARG or ord(c) < 0x20})
        if bad:
            raise ValueError(
                f"refusing to pass {''.join(repr(c) for c in bad)} to the batch shim "
                f"{cmd[0]} — cmd.exe would re-parse it (CVE-2024-24576). "
                f"Send untrusted text on stdin instead of in argv."
            )
