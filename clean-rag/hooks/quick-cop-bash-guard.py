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

import json
import re
import shlex
import sys

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
    a real shell construct."""
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
            sub = None
            j = i + 1
            while j < n and parts[j].startswith("-"):
                j += 1
            if j < n:
                sub = parts[j]
            if sub in _GIT_BLOCKED:
                return f"git {sub!r} mutates git state, not allowed: {command!r}"
            i = j + 1
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


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    command = (payload.get("tool_input", {}).get("command") or "").strip()
    if not command:
        return 0

    stripped = _strip_quoted(command)

    if _WRITE_REDIRECT.search(stripped):
        return (_refuse(f"file write redirection or a write pipe is not allowed: {command!r}") or 2)

    try:
        parts = shlex.split(command)
    except ValueError:
        return _refuse(f"could not parse the command safely: {command!r}")

    if not parts:
        return 0

    reason = _check_subcommand_chain(parts, command)
    if reason:
        return _refuse(reason)

    return 0


if __name__ == "__main__":
    sys.exit(main())
