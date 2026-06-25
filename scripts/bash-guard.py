"""
ClaudeBoost Bash guard — command-type PreToolUse hook.

Intercepts Bash tool calls and BLOCKS patterns that trigger Claude Code's
built-in safety prompts (which waste the user's time). Claude is told what
to do instead so it can retry correctly.

Blocked patterns:
  1. cd "/path" && command       — triggers "bare repository attack" prompt
  2. Backslash-escaped spaces    — triggers "backslash-escaped whitespace" prompt
  3. python -c "..." (multiline) — triggers newline-in-quoted-arg scanner
  4. cat > file << 'EOF'         — same scanner, forces Write tool instead
  5. curl to non-localhost URLs  — safety gate (curl:* is in allow list)
  6. Co-Authored-By in commits   — anti-attribution policy
  7. $CLAUDEBOOST_HOME in Bash   — triggers simple_expansion prompt; use absolute path
  8. ssh/scp to external hosts   — data exfiltration prevention
  9. nc/netcat to external hosts — reverse shell prevention

Each pattern here trips a Claude Code BUILT-IN scanner that prompts regardless of
the allow list. We do NOT block `|| echo` style fallbacks: ClaudeBoost's setup
puts "Bash" as a catch-all allow entry, so sub-commands like echo never prompt.

Off switch: set CLAUDEBOOST_BASH_GUARD=off (in ~/.claude/settings.json env) to
disable the guard entirely.

Exit codes:
  0 = allow (pass)
  2 = block (Claude sees stderr message and retries)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)


def _write_block_telemetry(tool: str, summary: str, reason: str) -> None:
    """Write a PreToolUse block event to claude-actions.jsonl.

    PostToolUse never fires when a PreToolUse hook exits 2, so we capture
    the block here before returning.
    """
    try:
        sys.path.insert(0, str(_BOOST_HOME / "scripts"))
        from telemetry_writer import now_iso, session_id, write_telemetry
        record = {
            "ts": now_iso(),
            "session_id": session_id(),
            "tool": tool,
            "summary": f"{tool} {summary[:200]}",
            "result": "blocked",
            "hook_event": "PreToolUse",
            "block_reason": reason[:300],
        }
        write_telemetry(record, "claude-actions.jsonl")
    except Exception:
        pass


def check_cd_compound(command: str) -> str | None:
    """Detect `cd <path> && <command>` immediate compounds.

    Only the immediate compound trips Claude Code's prompt. A standalone
    `cd /path; git ...` (cd ended by ; or newline) is fine, and the && in
    `git add X && git commit` joins the two gits, not the cd — so the match
    must not cross a command separator (; | & newline). Quotes are stripped
    first so a cd inside a commit message doesn't false-match.
    """
    cleaned = _strip_quoted(command)
    # cd <path> && <cmd>, with no separator between the cd target and the &&
    match = re.search(r"\bcd\s+[^;&|\n]+&&\s*(\w+)?", cleaned)
    if match:
        following = match.group(1) or "command"
        if following == "git":
            return (
                "BLOCKED: Do not use `cd && git`. "
                "Use `git -C \"/path\" ...` instead. "
                "Compound cd+git triggers a permission prompt."
            )
        if following in ("npm", "npx", "yarn", "pnpm"):
            return (
                "BLOCKED: Do not use `cd && " + following + "`. "
                "Use `npm --prefix \"/path\" run <script>` to run package scripts, "
                "or pass the directory to the tool itself "
                "(e.g. `npx tsc --noEmit -p \"/path\"`, `npx vitest run --root \"/path\"`, "
                "`npx jest --rootDir \"/path\"`). "
                "Compound cd commands trigger a permission prompt."
            )
        if following == "make":
            return (
                "BLOCKED: Do not use `cd && make`. "
                "Use `make -C \"/path\" <target>` instead. "
                "Compound cd commands trigger a permission prompt."
            )
        return (
            "BLOCKED: Do not use `cd && command`. "
            "Use absolute paths, or the tool's own directory flag "
            "(git -C, make -C, npm --prefix, vitest --root). "
            "Compound cd commands trigger a permission prompt."
        )
    return None


def check_coauthor(command: str) -> str | None:
    """Detect Co-Authored-By Claude attribution trailer in git commit messages."""
    # Match the actual trailer format: Co-Authored-By: Name <email>
    # Avoids false positives when the string appears in a commit message body/description.
    if re.search(r"(?i)co-authored-by:\s*\S+\s*<[^>]+>", command):
        return (
            "BLOCKED: Do not add Co-Authored-By lines to commits. "
            "Remove the Co-Authored-By trailer from the commit message and retry."
        )
    return None


def check_python_multiline_c(command: str) -> str | None:
    """Detect multiline python -c commands.

    Claude Code's built-in scanner flags \n followed by # inside a quoted argument,
    which makes any python -c script with comments or multiline code prompt the user
    even when the command is in the allow list. Force the temp-file pattern instead.
    """
    if re.search(r"python3?\s+-c\s+[\"']", command) and "\n" in command:
        return (
            "BLOCKED: Multiline python -c strings trigger Claude Code's built-in safety prompt "
            "even when the command is in the allow list. "
            "Write the code to a temp file instead: "
            "Write the Python to a file like /tmp/cb_script.py, then run "
            "`python /tmp/cb_script.py`. "
            "This avoids the prompt and is cleaner anyway."
        )
    return None


def _assigned_vars(command: str) -> set[str]:
    """Names of variables defined within the command itself.

    A variable you assign and then use in the same command (SHA=$(git rev-parse
    HEAD); ... $SHA) is locally scoped, not an environment expansion, so it
    shouldn't be blocked. Quotes are stripped first so a `FOO=bar` sitting
    inside a quoted string isn't mistaken for a real assignment.
    """
    cleaned = _strip_quoted(command)
    names: set[str] = set()
    # NAME=value at a command position (single =, not == / != comparisons)
    for m in re.finditer(r"(?:^|[\s;&|\n(])([A-Za-z_][A-Za-z0-9_]*)=(?!=)", cleaned):
        names.add(m.group(1))
    # for NAME in ...   and C-style  for (( NAME=...
    for m in re.finditer(r"\bfor\s+\(?\(?\s*([A-Za-z_][A-Za-z0-9_]*)", cleaned):
        names.add(m.group(1))
    # read [-opts] NAME
    for m in re.finditer(r"\bread\b(?:\s+-\S+)*\s+([A-Za-z_][A-Za-z0-9_]*)", cleaned):
        names.add(m.group(1))
    return names


def check_env_var_expansion(command: str) -> str | None:
    """Block $VARNAME env expansion in Bash commands.

    Claude Code's built-in simple_expansion scanner prompts on environment
    expansions regardless of the allow list. Use the ${VAR} brace form (which
    the scanner accepts) or an absolute path.

    Exceptions: $() command substitution and ${VAR} brace form are not flagged
    by the scanner, so we only block the bare $WORD form. Single-quoted strings
    are stripped first ('$VAR' never expands in shell). Variables assigned
    earlier in the same command are locally scoped, so references to them pass.
    """
    scannable = _strip_quoted(command, single_only=True)
    assigned = _assigned_vars(command)
    # Match bare $WORD (not preceded by { which would be ${VAR})
    for match in re.finditer(r"(?<!\{)\$([A-Za-z_][A-Za-z0-9_]*)", scannable):
        name = match.group(1)
        if name in assigned:
            continue
        return (
            f"BLOCKED: Do not use ${name} in Bash commands. "
            "Claude Code's simple_expansion scanner prompts on environment expansions "
            "regardless of the allow list. "
            f"Use the brace form ${{{name}}} (the scanner accepts it) or an absolute path. "
            "Variables you assign earlier in the same command are fine to reference. "
            "For log files, use the Read tool."
        )
    return None


def check_cat_heredoc(command: str) -> str | None:
    """Block cat > file << 'EOF' heredoc patterns.

    Heredocs with multiline content trigger Claude Code's built-in safety
    scanner even when cat:* is in the allow list. The Write tool does the
    same thing without any prompt.
    """
    if re.search(r"cat\s+>\s+\S+\s*<<\s*['\"]?\w", command):
        return (
            "BLOCKED: Do not use cat > file << 'EOF' heredocs to create files. "
            "Use the Write tool instead — it is always allowed and never prompts."
        )
    return None


def _strip_quoted(command: str, single_only: bool = False) -> str:
    """Remove quoted string literals so body text (e.g. git commit -m '...')
    doesn't trip checks that look for command words inside the message.

    single_only=True keeps double-quoted content (the shell still expands
    $VAR there) and removes only single-quoted literals. A character scanner
    rather than a regex: an apostrophe or single quote nested inside "..."
    is literal to the shell and must not start a bogus single-quoted span,
    otherwise "...'$VAR'..." would hide a real expansion.

    Unbalanced quotes leave the tail untouched so checks stay conservative.
    """
    out = []
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c == '"':
            j = i + 1
            while j < n and command[j] != '"':
                j += 2 if command[j] == "\\" else 1
            if j >= n:
                out.append(command[i:])
                break
            out.append(command[i : j + 1] if single_only else '""')
            i = j + 1
        elif c == "'":
            j = command.find("'", i + 1)
            if j == -1:
                out.append(command[i:])
                break
            out.append("''")
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_ssh_external(command: str) -> str | None:
    """Block ssh/scp to non-localhost hosts.

    ssh-keygen, ssh-add, ssh-agent have no host argument so they won't match.
    Quoted strings are stripped first so words inside commit messages don't
    trigger false positives.
    """
    unquoted = _strip_quoted(command)
    if not re.search(r"\b(ssh|scp)\b", unquoted):
        return None
    localhost_names = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    # For ssh: match ssh [opts] [user@]host
    for host in re.findall(r"\bssh\s+(?:-\S+\s+)*(?:\S+@)?([a-zA-Z0-9][\w.-]+)", unquoted):
        if host not in localhost_names and not host.startswith("-"):
            return (
                f"BLOCKED: ssh/scp to external host '{host}' is not allowed. "
                "Run this command yourself in the terminal if needed."
            )
    # For scp: remote paths always use user@host:/path or host:/path syntax
    for host in re.findall(r"(?:\S+@)?([a-zA-Z0-9][\w.-]+):/", unquoted):
        if host not in localhost_names:
            return (
                f"BLOCKED: ssh/scp to external host '{host}' is not allowed. "
                "Run this command yourself in the terminal if needed."
            )
    return None


def check_netcat(command: str) -> str | None:
    """Block nc/ncat/netcat to external hosts — these can create reverse shells.

    Quoted strings are stripped first to avoid false positives in commit messages.
    """
    unquoted = _strip_quoted(command)
    if not re.search(r"\b(nc|ncat|netcat)\b", unquoted):
        return None
    hosts = re.findall(r"\b(?:nc|ncat|netcat)\s+(?:-\S+\s+)*([a-zA-Z0-9][\w.-]+)", unquoted)
    localhost_names = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    for host in hosts:
        # Skip pure port numbers (e.g. `nc -l 8080`)
        if host.isdigit():
            continue
        if host not in localhost_names and not host.startswith("-"):
            return (
                f"BLOCKED: nc/netcat to external host '{host}' is not allowed."
            )
    return None


def check_curl_external(command: str) -> str | None:
    """Block curl to non-localhost URLs.

    Catches curl anywhere in the command — including compound commands like
    `sleep 40 && curl https://external.com` and `curl ... | head`.
    """
    if not re.search(r"\bcurl\b", command):
        return None
    # Strip -d / --data / -H values so URLs in request bodies don't trip us up
    cleaned = re.sub(r'(?:-d|--data|-H)\s+[\'"][^\'"]*[\'"]', "", command)
    urls = re.findall(r"https?://([^/\s]+)", cleaned)
    if not urls:
        return None
    for url_host in urls:
        host = url_host.split(":")[0]
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return None
    return (
        "BLOCKED: curl to non-localhost URL is not allowed. "
        f"Only localhost and 127.0.0.1 are permitted. "
        f"Found: {urls[0]}"
    )


def check_db_mutation(command: str) -> str | None:
    """Block commands that make irreversible changes to a database.

    These commands alter schema or data in ways that cannot be undone by the
    AI alone (no git revert, no undo). The user must run them manually so they
    can confirm the target environment first.

    Covered patterns:
    - EF Core:   dotnet ef database update
    - Alembic:   alembic upgrade
    - Flyway:    flyway migrate
    - Liquibase: liquibase update
    - Raw SQL:   sqlcmd -i / psql -f / mysql < (file based execution)
    """
    unquoted = _strip_quoted(command)

    if re.search(r"\bdotnet\b.*\bef\b.*\bdatabase\s+update\b", unquoted, re.IGNORECASE):
        return (
            "BLOCKED: `dotnet ef database update` makes irreversible schema changes. "
            "Run this yourself in the terminal after confirming the target environment "
            "(dev / test / staging / prod). "
            "Never let the AI apply database migrations autonomously."
        )

    if re.search(r"\balembic\s+upgrade\b", unquoted, re.IGNORECASE):
        return (
            "BLOCKED: `alembic upgrade` makes irreversible schema changes. "
            "Run this yourself in the terminal after confirming the target environment."
        )

    if re.search(r"\bflyway\s+migrate\b", unquoted, re.IGNORECASE):
        return (
            "BLOCKED: `flyway migrate` makes irreversible schema changes. "
            "Run this yourself in the terminal after confirming the target environment."
        )

    if re.search(r"\bliquibase\s+update\b", unquoted, re.IGNORECASE):
        return (
            "BLOCKED: `liquibase update` makes irreversible schema changes. "
            "Run this yourself in the terminal after confirming the target environment."
        )

    if re.search(r"\bsqlcmd\b.*-i\s+\S+\.sql\b", unquoted, re.IGNORECASE):
        return (
            "BLOCKED: `sqlcmd -i <file.sql>` executes SQL directly against the database. "
            "Run this yourself in the terminal after confirming the target environment."
        )

    if re.search(r"\bpsql\b.*-f\s+\S+\.sql\b", unquoted, re.IGNORECASE):
        return (
            "BLOCKED: `psql -f <file.sql>` executes SQL directly against the database. "
            "Run this yourself in the terminal after confirming the target environment."
        )

    if re.search(r"\bmysql\b.*<\s*\S+\.sql\b", unquoted, re.IGNORECASE):
        return (
            "BLOCKED: `mysql < <file.sql>` executes SQL directly against the database. "
            "Run this yourself in the terminal after confirming the target environment."
        )

    return None


def check_backslash_spaces(command: str) -> str | None:
    """Detect backslash-escaped spaces in paths."""
    # Match backslash-space that looks like path escaping, not inside quotes
    # Common pattern: /some/path/F\ and\ B\ PWA/
    if re.search(r"(?<![\"'])\b\S+\\ \S+", command):
        return (
            "BLOCKED: Do not backslash-escape spaces in paths. "
            "Use double-quoted paths instead: \"/path/F and B PWA/Nectar\". "
            "Backslash-escaped whitespace triggers a permission prompt."
        )
    return None


def main() -> int:
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:  # pragma: no cover
        return 0  # pragma: no cover

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0

    # Full off switch — set CLAUDEBOOST_BASH_GUARD=off to let everything through.
    if os.environ.get("CLAUDEBOOST_BASH_GUARD", "").strip().lower() in ("off", "0", "false", "disabled", "no"):
        return 0

    # Run checks in order
    for check in [check_db_mutation, check_env_var_expansion, check_cat_heredoc, check_ssh_external, check_netcat, check_curl_external, check_coauthor, check_python_multiline_c, check_cd_compound, check_backslash_spaces]:
        msg = check(command)
        if msg:
            print(msg, file=sys.stderr)
            _write_block_telemetry("Bash", command, msg)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
