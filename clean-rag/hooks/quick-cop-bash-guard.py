#!/usr/bin/env python
"""PreToolUse guard on Bash, scoped to quick-cop via its own frontmatter.

quick-cop's whole job is a cheap read: read code, run something existing to
observe real behavior, report whether a claim holds. It never needed to write,
install, delete, or move anything to do that job, so none of those verbs cost
it anything to lose. This guard makes that boundary real instead of assumed.

Fail closed by design, per an explicit user requirement: only basic, safe,
reversible actions pass. "Reversible" here means nothing persists past the
command itself, reading a file, running an existing test or build command,
grepping, listing. Anything that writes a file, changes git state, installs
or removes a package, deletes or moves something, or controls a process or
service is refused, even if this guard cannot name the exact command in
advance, because an unrecognized command is not evidence it is safe.

When a command is refused, the message tells quick-cop to note what it wanted
to run and why in its own report instead of giving up silently or guessing.
The orchestrator reads that note and decides whether to run it, right after
quick-cop's report comes back, not at some later point.

Exit codes: 0 allows, 2 blocks with the stderr message shown to the agent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from shell_tokens import (  # noqa: E402
        git_subcommand,
        pad_shell_operators,
        split_readings,
    )
except ImportError as _exc:
    # The helper ships in this directory, so this only fires on a broken
    # install. It still has to be handled rather than left to propagate: an
    # uncaught ImportError exits 1, and 1 is not a block under this hook
    # contract, so this read only cage would have allowed the command. Failing
    # at the point of use instead puts it on the refusal path at the bottom of
    # this file, which is what "fail closed by design" above means.
    #
    # Rebound to a module level name on purpose. Python deletes the `as` target
    # at the end of the except block (PEP 3110), so a nested function closing
    # over `_exc` raises NameError instead of the RuntimeError written below.
    # The refusal still happens either way, but the operator sees the wrong
    # cause, which is the kind of thing that costs an hour on a broken install.
    _tokenizer_import_error = _exc

    def pad_shell_operators(command: str) -> str:  # noqa: E402
        raise RuntimeError(
            "the shell tokenizer is unavailable") from _tokenizer_import_error

    def split_readings(padded: str) -> tuple:  # noqa: E402
        raise RuntimeError(
            "the shell tokenizer is unavailable") from _tokenizer_import_error

    def git_subcommand(parts: list, start: int) -> tuple:  # noqa: E402
        raise RuntimeError(
            "the shell tokenizer is unavailable") from _tokenizer_import_error

# Redirection that writes or appends to a file, or pipes into a command that
# would. A single '>' inside a comparison like 'a > b' in a quoted string is
# not a shell redirection and won't reach here since quoted spans are removed
# before this check runs.
_WRITE_REDIRECT = re.compile(r"(?<!\d)>>?(?!=)|\btee\b")

# git subcommands that change history, the working tree beyond reading, or a
# remote. quick-cop never legitimately touches git state at all, so this is
# stricter than the bad-cop/good-cop guard: even 'git add' is refused, since
# quick-cop has no file of its own to stage.
_GIT_BLOCKED = {
    "add", "commit", "push", "merge", "rebase", "reset", "restore",
    "clean", "cherry-pick", "revert", "pull", "am", "apply", "stash",
    "branch", "tag", "checkout", "switch", "worktree", "submodule",
    "gc", "reflog", "filter-branch", "filter-repo",
}

# Package manager subcommands that install, remove, publish, or otherwise
# mutate the environment or a registry. Build/test/restore/list subcommands
# for the same tools are deliberately not in this set.
_PACKAGE_MUTATIONS = {
    "npm": {"install", "i", "ci", "add", "remove", "uninstall", "un", "unlink",
            "link", "publish", "update", "up", "audit", "prune", "dedupe",
            "rebuild", "init", "config"},
    "yarn": {"add", "remove", "install", "publish", "link", "unlink", "up",
             "upgrade", "init"},
    "pnpm": {"add", "remove", "install", "i", "publish", "link", "unlink",
             "update", "up", "prune", "dedupe", "init"},
    "pip": {"install", "uninstall"},
    "pip3": {"install", "uninstall"},
    "poetry": {"add", "remove", "install", "update", "publish", "init"},
    "dotnet": {"add", "remove", "new", "nuget", "pack", "publish", "clean"},
    "cargo": {"install", "uninstall", "add", "remove", "publish", "new",
              "init", "update"},
    "gem": {"install", "uninstall", "push"},
    "go": {"install", "get"},
    "brew": {"install", "uninstall", "upgrade", "remove"},
    "apt": None,  # any apt subcommand mutates system packages
    "apt-get": None,
    "choco": None,
    "winget": {"install", "uninstall", "upgrade"},
}

# Filesystem, process, and service binaries that mutate or control something
# beyond the current read. Blocked outright; quick-cop has no legitimate use
# for any of them.
_BLOCKED_BINARIES = {
    "rm", "del", "erase", "mv", "move", "cp", "copy", "mkdir", "rmdir",
    "touch", "chmod", "chown", "attrib", "ln",
    "docker", "docker-compose", "podman", "kubectl", "helm",
    "systemctl", "service", "sc", "net",
    "kill", "pkill", "taskkill", "shutdown", "reboot",
    "ssh", "scp", "rsync", "ftp",
}


def _refuse(reason: str) -> int:
    print(
        f"BLOCKED for quick-cop: {reason}\n\n"
        "quick-cop is read only: it checks a claim by reading code and "
        "running something that already exists, never by writing, "
        "installing, deleting, moving, or otherwise mutating anything. "
        "Do not retry a different way to do the same mutation.\n\n"
        "If this command was genuinely necessary to check the claim, say so "
        "in your report as its own line: what you wanted to run, and why. "
        "The orchestrator reads that and decides whether to run it right "
        "after your report comes back, not by you finding a workaround.\n\n"
        "Allowed: reading files, grep/find, and running the project's "
        "existing test, build, or lint commands (dotnet test, npm test, "
        "pytest, go test, cargo test, and the like) so long as the command "
        "itself does not write, install, or delete anything.",
        file=sys.stderr,
    )
    return 2


def _strip_quoted(command: str) -> str:
    """Remove quoted string contents so a '>' or binary name inside a
    quoted argument (a commit message, a grep pattern) isn't mistaken for
    a real shell construct.

    Run on the operator-padded command, never the raw one. Padding has already
    lifted a command substitution out of the double quotes around it, so a
    redirection the shell really performs, `echo "$(printf hi > secrets)"`,
    survives this strip while a literal '>' in `echo "a > b"` still does not.
    Reading the raw command here let that write through.
    """
    out = []
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c in "\"'":
            j = command.find(c, i + 1)
            if j == -1:
                out.append(command[i:])
                break
            out.append(c * 2)
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _binary_name(token: str) -> str:
    name = token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def _check_subcommand_chain(parts: list, command: str) -> str | None:
    """Walk the token stream once, checking every binary invocation in a
    chained command (a && b, a; b, a | b), not just parts[0]."""
    i = 0
    n = len(parts)
    while i < n:
        token = parts[i]
        binary = _binary_name(token)

        if binary == "git":
            # git_subcommand is shared with verify-loop-git-guard.py so both
            # guards read a git invocation the same way. The copy that lived
            # here skipped tokens starting with '-' but not the separate value
            # token that -C, -c and --work-tree take, so it read that value as
            # the subcommand and let `git -c user.name=x push` through.
            sub, j = git_subcommand(parts, i)
            if sub in _GIT_BLOCKED:
                return f"git {sub!r} mutates git state, not allowed: {command!r}"
            i = j
            continue

        if binary in _PACKAGE_MUTATIONS:
            blocked_subs = _PACKAGE_MUTATIONS[binary]
            j = i + 1
            sub = parts[j] if j < n else None
            if blocked_subs is None or (sub and sub in blocked_subs):
                return f"{binary!r} mutates packages or the system, not allowed: {command!r}"
            i = j + 1
            continue

        if binary in _BLOCKED_BINARIES:
            return f"{binary!r} is not on quick-cop's allowlist: {command!r}"

        if binary == "sed" and any(a.startswith("-i") or a == "--in-place" for a in parts[i + 1:i + 4]):
            return f"sed -i writes files in place, not allowed: {command!r}"

        if binary in ("powershell", "pwsh") and re.search(
            r"\b(set-content|out-file|remove-item|move-item|copy-item|new-item)\b",
            command, re.IGNORECASE,
        ):
            return f"PowerShell file-mutating cmdlet is not allowed: {command!r}"

        i += 1
    return None


def _bash_command(payload) -> tuple[str, str]:
    """The Bash command out of a PreToolUse payload, as (command, problem).

    An empty command means there is nothing to judge: not a Bash call, or a
    Bash call with no command in it. A non-empty problem means the payload's
    shape could not be read at all, which is a refusal rather than an allow.

    Stdin is a system boundary and every shape handled here is valid JSON: the
    payload a bare scalar, null, or a list; tool_input null or a string; the
    command a number or a list. A naive payload.get(...).get(...) chain raises
    on each of them, and an uncaught exception exits 1 -- neither allow (0) nor
    block (2) under this hook contract, so the command would run anyway.
    """
    if not isinstance(payload, dict):
        return "", "the tool payload was not a JSON object"
    if payload.get("tool_name") != "Bash":
        return "", ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return "", "the Bash tool_input was not a JSON object"
    command = tool_input.get("command")
    if command is None or command == "":
        return "", ""
    if not isinstance(command, str):
        return "", "the Bash command was not a string"
    return command.strip(), ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        # Fail closed, matching this module's stated contract and the
        # shlex.split() path below: an unrecognized command is not evidence it
        # is safe, and neither is an unreadable payload.
        return _refuse("could not parse the tool payload")

    command, problem = _bash_command(payload)
    if problem:
        return _refuse(problem)
    if not command:
        return 0

    # Padded first, and both checks below read the padded string: shlex splits
    # only on whitespace and quotes, so 'pytest;rm -rf x' would otherwise
    # tokenize as the single word 'pytest;rm' and never match 'rm' in
    # _BLOCKED_BINARIES below.
    try:
        padded = pad_shell_operators(command)
    except ValueError:
        return _refuse(f"could not parse the command safely: {command!r}")

    if _WRITE_REDIRECT.search(_strip_quoted(padded)):
        return (_refuse(f"file write redirection or a write pipe is not allowed: {command!r}") or 2)

    # Both shlex readings, not just the POSIX one. POSIX mode eats the
    # backslashes out of `C:\Program Files\Git\bin\git.exe push`, leaving
    # ['C:Program', 'FilesGitbingit.exe', 'push'] -- no token that
    # _binary_name can reduce to "git", so a fully qualified path to git.exe,
    # the ordinary spelling on Windows, walked straight through this cage.
    # verify-loop-git-guard.py closed the same hole for its own denylist;
    # split_readings is now the one implementation both guards read a command
    # through, so they cannot diverge on it again.
    readings, complete = split_readings(padded)

    if not complete:
        # A reading that failed is a reading whose evidence is missing, and
        # "cannot tell" is not "safe" in a cage that fails closed by design.
        # Stricter than verify-loop-git-guard.py, which refuses an unreadable
        # command only when it mentions git: that guard exists to keep two
        # agents off a remote and needs broad Bash for builds either way,
        # whereas this one is meant to pass nothing but reads.
        return _refuse(f"could not parse the command safely: {command!r}")

    if not any(readings):
        return 0

    for parts in readings:
        reason = _check_subcommand_chain(parts, command)
        if reason:
            return _refuse(reason)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - last line of the read-only cage
        # An uncaught exception exits 1, and 1 is not a block under this hook
        # contract, so a crashing guard has allowed the command. Land on 2.
        sys.exit(_refuse(f"the guard itself failed ({exc!r})"))
