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
 10. routed git/gh writes        — xargs/env prefix/alias bypass of the ask rule

Most patterns here trip a Claude Code BUILT-IN scanner that prompts regardless of
the allow list. check_routed_git_write is the exception: it closes a gap the
permission engine structurally cannot, since permission rules match the raw
command string by prefix and a routed write never matches that prefix.

The bare "Bash" catch all allow entry was removed from settings.json, so an
unlisted sub-command is no longer silently allowed.

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
    """Detect Claude attribution trailers in git commit messages.

    Covers every format Claude Code's own default instructions or a model might
    reach for: the classic Co-Authored-By trailer, the Claude-Session URL trailer
    this harness's own commit template suggests, and generic "generated with/by
    Claude" phrasing. Each pattern is specific enough to avoid false positives
    against an unrelated commit message body.
    """
    patterns = (
        r"(?i)co-authored-by:\s*\S+\s*<[^>]+>",
        r"(?i)co-authored-by:\s*claude\b",
        r"(?i)claude-session:\s*\S+",
        r"(?i)generated (with|using|by)\s+claude\b",
    )
    for pattern in patterns:
        if re.search(pattern, command):
            return (
                "BLOCKED: Do not add Claude attribution to commits (Co-Authored-By, "
                "Claude-Session, 'Generated with Claude', or similar). Remove the "
                "attribution line from the commit message and retry."
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


def check_production_environment(command: str) -> str | None:
    """Block starting a local app in a way that resolves to the production environment.

    The danger here is the opposite of the usual guard: the command contains no
    dangerous looking token at all. ASP.NET Core defaults to Production whenever
    ASPNETCORE_ENVIRONMENT is unset, so *removing* a guardrail is what does the
    damage. Config then binds appsettings.json rather than
    appsettings.Development.json, which on real projects means the production
    database catalog and the production key vault.

    Seen in practice: `dotnet run --no-launch-profile` on a dev machine resolved
    a production database and a production secret store. Whether such a run
    actually connects comes down to incidental things like credential resolution
    order, which is not a safeguard.

    A keyword scan for "production" would NOT have caught it, which is why this
    matches the known risk flag and the explicit assignment instead.

    Covered patterns:
    - dotnet run / dotnet watch run with --no-launch-profile
    - an explicit --environment Production on a dotnet run
    - inline ASPNETCORE_ENVIRONMENT=Production or DOTNET_ENVIRONMENT=Production
    """
    unquoted = _strip_quoted(command)

    if re.search(
        r"\bdotnet\s+(?:watch\s+)?run\b[^|;&]*--no-launch-profile\b",
        unquoted,
        re.IGNORECASE,
    ):
        return (
            "BLOCKED: `dotnet run --no-launch-profile` skips launchSettings.json, so "
            "ASPNETCORE_ENVIRONMENT is unset and ASP.NET Core defaults to Production. "
            "That binds appsettings.json instead of appsettings.Development.json, which "
            "commonly points at the production database and the production secret store. "
            "Name the environment explicitly instead:\n"
            '  ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS="https://localhost:PORT" \\\n'
            '    dotnet run --project "<path to csproj>"\n'
            "Then confirm the startup log says `Hosting environment: Development` before using it."
        )

    if re.search(
        r"\bdotnet\s+(?:watch\s+)?run\b[^|;&]*--environment[=\s]+(Production|Staging)\b",
        unquoted,
        re.IGNORECASE,
    ):
        return (
            "BLOCKED: starting a local app with `--environment Production` (or Staging) "
            "points it at that environment's real database and secrets. "
            "Run this yourself after confirming that is what you intend."
        )

    # Matched against the RAW command, not the stripped one. _strip_quoted deletes the
    # quoted value, so ASPNETCORE_ENVIRONMENT="Production" would survive the stripped
    # pass with nothing left to match (found by testing this rule, not by inspection).
    # The anchor is what keeps the false positive out: a real assignment sits at the
    # start of a command, after a separator, or just inside a quoted -c payload, so
    # `git commit -m "set ASPNETCORE_ENVIRONMENT=Production in CI"` does not match
    # because the word `set ` precedes it.
    match = re.search(
        r"(?:^|[;&|]\s*|[\"']\s*)(ASPNETCORE_ENVIRONMENT|DOTNET_ENVIRONMENT)"
        r"\s*=\s*[\"']?(Production|Staging)\b",
        command,
        re.IGNORECASE,
    )
    if match:
        return (
            f"BLOCKED: this command sets {match.group(1)}={match.group(2)}, which points the "
            "app at that environment's real database and secrets. "
            "Use Development locally. If you genuinely need to run against "
            f"{match.group(2)}, run it yourself in the terminal."
        )

    return None


# Matches an ordinary relative-path rm -rf on purpose, since that class of
# command runs constantly for legitimate cleanup (e.g. `rm -rf test/build`
# before a fresh run) -- blocking every rm -rf would be far too disruptive.
# Only flags the actual danger class documented in arxiv.org/pdf/2604.13536
# (a Codex agent deleting 370+GB of files outside its project directory):
# root/home/system paths and heavy ".." traversal, not scoped deletes.
#
# Compared as whole tokens (see _token_is_dangerous_target below), not as a
# substring search over the raw command -- a \b-anchored substring search
# was tried first and found broken by direct testing: it both false-
# positived on legitimate relative paths (\b/ matches any slash after a
# word char, so "test/flappy-bird" tripped it) and false-negatived on the
# actual dangerous cases (\b does not transition correctly before a target
# that does not start with a word character, like "/" or "~").
_DANGEROUS_DELETE_TARGETS = (
    "/", "~", "$home", "${home}",
    "/etc", "/usr", "/bin", "/boot", "/system", "/library",
)


def _token_is_dangerous_target(token: str) -> bool:
    """True if a single whitespace-separated command token is a root/home/
    system path, checked as a whole token (exact match or a dangerous
    prefix followed by nothing or a trailing slash), not a substring match
    anywhere in the command."""
    normalized = token.rstrip("/\\").lower()
    if not normalized:
        # token was purely slashes, e.g. "/" or "//" -- that is the bare
        # root case itself
        return bool(token.strip("\\").strip() in ("/", ""))

    if normalized in _DANGEROUS_DELETE_TARGETS:
        return True

    # Windows drive root: "c:" or "c:\" alone, or "c:\windows"/"c:\users\<name>"
    # with nothing deeper (a whole profile, not a subpath inside it).
    drive_match = re.fullmatch(r"([a-z]):(\\windows)?", normalized)
    if drive_match:
        return True
    users_match = re.fullmatch(r"[a-z]:\\users\\[^\\]*", normalized)
    if users_match:
        return True

    return False


def check_destructive_delete(command: str) -> str | None:
    """Block recursive-force deletes targeting root/home/system paths or
    heavy path traversal -- the same failure class as a real, documented
    incident (arxiv.org/pdf/2604.13536): a coding agent deleted 370+GB of
    user files outside its project directory in an unattended run.

    Deliberately narrow: ordinary relative-path deletes (rm -rf
    test/build, rm -rf node_modules) are common, legitimate cleanup and
    are not touched here.

    Covered patterns:
    - rm -rf / rm -fr / rm -r -f / rm --recursive --force
    - rmdir /s /q
    - del /f /s /q
    - PowerShell Remove-Item -Recurse -Force
    """
    unquoted = _strip_quoted(command)

    is_recursive_force = bool(
        re.search(r"\brm\s+(-\w*[rf]\w*[rf]?\w*|--recursive\s+--force|--force\s+--recursive)\b", unquoted, re.IGNORECASE)
        or re.search(r"\brmdir\s+/s\s+/q\b", unquoted, re.IGNORECASE)
        or re.search(r"\bdel\s+/f\s+/s\s+/q\b", unquoted, re.IGNORECASE)
        or re.search(r"\bRemove-Item\b.*-Recurse\b.*-Force\b", unquoted, re.IGNORECASE)
        or re.search(r"\bRemove-Item\b.*-Force\b.*-Recurse\b", unquoted, re.IGNORECASE)
    )
    if not is_recursive_force:
        return None

    if re.search(r"\.\.[\\/].*\.\.[\\/].*\.\.[\\/]", unquoted):
        return (
            "BLOCKED: recursive force-delete with heavy '..' path traversal. "
            "This matches the pattern behind a real documented incident of a coding "
            "agent deleting files far outside its project directory. Use an explicit, "
            "absolute path you have confirmed, or run this yourself in the terminal."
        )

    for token in unquoted.split():
        if token.startswith("-"):
            continue
        if _token_is_dangerous_target(token):
            return (
                "BLOCKED: recursive force-delete targeting a root/home/system path. "
                "This matches the pattern behind a real documented incident of a coding "
                "agent deleting 370+GB of user files outside its project directory. "
                "Run this yourself in the terminal after confirming exactly what will "
                "be deleted."
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


# A git write we care about, in any of the forms that still reach a remote.
# Written to survive _strip_quoted emptying a quoted path, so -C "..." leaves
# behind a bare -C with nothing after it.
_GIT_WRITE_RE = re.compile(
    r"\bgit(?:\.exe)?\b"
    r"(?:\s+(?:-C|--git-dir|--work-tree|-c)(?:=|\s*)\S*)*"
    r"\s+(push|send-pack|http-push|request-pull)\b",
    re.IGNORECASE,
)

# gh subcommands that change something on the server. A denylist of verbs, not
# an allowlist of nouns, so read only calls (view, list, diff, checks, status,
# clone, download) keep working untouched.
_GH_WRITE_RE = re.compile(
    r"\bgh(?:\.exe)?\s+(pr|issue|repo|release|workflow|secret|variable|gist|auth|label|ruleset)"
    r"\s+(create|edit|merge|close|reopen|review|comment|delete|ready|lock|unlock|"
    r"pin|unpin|transfer|fork|archive|unarchive|rename|sync|upload|run|enable|"
    r"disable|set|remove|add|login|logout|refresh|token|setup-git)\b",
    re.IGNORECASE,
)

# gh api is denied outright in settings.json, so any route to it is a bypass
# attempt whatever the method.
_GH_API_RE = re.compile(r"\bgh(?:\.exe)?\s+api\b", re.IGNORECASE)

# The head of a command whose next argument is itself executed. These matter
# because _strip_quoted empties quoted text before the scan, which is right for
# a commit message and wrong here: `bash -c "git push"` really does push, and
# stripping the quotes deletes the evidence.
#
# Only the argument that follows one of these gets scanned raw, never the whole
# command. Scanning the whole command was the first attempt and it was wrong:
# an unrelated `bash -c "ls"` earlier in the line made an honest
# `git commit -m "remember to git push"` look like a routed push and blocked it.
#
# The token run between the shell name and its -c absorbs whole flags AND their
# values, so `bash -o pipefail -c` is caught and not just `bash --login -c`.
# Absorbing only dash prefixed tokens was not enough: -o takes a bare value, and
# that value stopped the run before it reached the -c. The negative lookahead
# keeps the run from swallowing the -c it is looking for, and the bound keeps
# the alternation from backtracking badly on a long command.
# Bounded rather than open ended so the alternation cannot backtrack badly, but
# generous enough that stacking flags is not an escape. Timed linear to 100k
# characters of input at this bound.
_EXEC_FLAG_RUN = r"(?:\s+(?!-[a-zA-Z]*c\b)[^\s;&|]+){0,24}"

# A shell. Its argument is shell source, so it gets read the way the top level
# command is: quote stripped, and a write only counts in command position.
_SHELL_EXEC_HEAD_RE = re.compile(
    r"\beval\b"
    r"|\b(?:ba|z|k|da)?sh" + _EXEC_FLAG_RUN + r"\s+-[a-zA-Z]*c\b"
    r"|\b(?:ba|z|k|da)?sh" + _EXEC_FLAG_RUN + r"\s*<<<"
    r"|\b(?:pwsh|powershell)(?:\.exe)?" + _EXEC_FLAG_RUN + r"\s+-(?:c|Command)\b"
    r"|\bcmd(?:\.exe)?\s+/[ckCK]\b",
    re.IGNORECASE,
)

# An interpreter. Its argument is source in another language, where a quoted
# string is usually the command being run rather than data:
# `python -c "os.system('git push')"` really pushes. Shell quoting rules do not
# apply, so the payload is scanned whole rather than stripped and position
# checked. The cost is that a program legitimately handling the literal text
# "git push" gets blocked, which is a fair trade for a one line interpreter
# invocation.
_INTERPRETER_EXEC_HEAD_RE = re.compile(
    r"\b(?:python[\d.]*|perl|ruby|node|php|Rscript)\s+-(?:c|e)\b",
    re.IGNORECASE,
)

_EXECUTOR_HEAD_RE = re.compile(
    _SHELL_EXEC_HEAD_RE.pattern + "|" + _INTERPRETER_EXEC_HEAD_RE.pattern,
    re.IGNORECASE,
)

# A shell separator ends an unquoted executor argument.
_ARG_TERMINATOR_RE = re.compile(r"[;&|\n]")

# What may sit between a command separator and the command actually being run.
# An env assignment, or a runner that hands off to whatever follows it. This is
# what tells `echo git push` (the words are an argument to echo, nothing pushes)
# apart from `xargs git push` (xargs runs the push).
_ROUTER_PREFIX = (
    r"(?:[A-Za-z_]\w*=\S*"
    r"|xargs(?:\s+-\S+)*"
    r"|timeout\s+\S+"
    r"|env|nohup|sudo|nice|time|command|builtin|exec|then|do|else"
    r")"
)
# `)` is in the separator set for a case branch: `case $1 in prod) git push ;;`
# runs the push, so the text before it has to read as a command boundary.
_CMD_START_RE = re.compile(
    r"(?:^|[;&|\n()`{]|\$\()\s*(?:" + _ROUTER_PREFIX + r"\s+)*$"
)

# A path leading up to the binary. `\bgit\b` matches the tail of `/usr/bin/git`,
# so the match lands mid token and the text before it is a directory rather than
# a command boundary. Without stripping this, `/usr/bin/git push` and `./git push`
# read as an argument mention and go through unchecked, even though nothing in
# settings.json prompts on either.
# The separators are in the class too, so the whole path is consumed in one go.
# Without them the walk back stops at the last component, leaving `/usr/` in
# front of the match and still reading as no command boundary.
_PATH_PREFIX_RE = re.compile(r"[\w.@+~:/\\-]*[/\\]$")


def _in_command_position(text: str, index: int) -> bool:
    """Is the token at `index` the command being run, or just an argument?

    `git push` at the head of a command really pushes. The same two words as an
    argument to something else do not: `echo git push` prints them, and
    `grep 'git push' file` searches for them. Without this the check blocks
    ordinary read only work, which is worse than the bypass it was written for.
    """
    head = text[:index]
    # Step back over a path so the binary is judged where its path begins.
    # `echo /usr/bin/git push` still reads as an argument, because what remains
    # after stripping the path is `echo `, not a command boundary.
    path = _PATH_PREFIX_RE.search(head)
    if path:
        head = head[:path.start()]
    return bool(_CMD_START_RE.search(head))


# A heredoc, with the command word that receives it. `python - <<'EOF' ... EOF`
# feeds the body to python's stdin as data; it is not shell to execute. A body
# that happens to contain the text of a git command must not be read as one,
# the same way a commit message is not. The exception is a body fed to a shell
# (`bash <<EOF`), which really is executed and stays scannable.
#
# Anchored on the << itself, with nothing optional or greedy in front of it.
# An earlier version opened with `(?P<recv>\S+)?[^\n<]*` to capture the
# receiving command, and those two groups overlap: on a command containing no
# << at all, the engine tried every split between them at every offset. That
# measured 6.8 seconds on a 2000 character echo and grew roughly cubically, on
# a hook that runs before every single Bash call. The receiving command is
# recovered by looking backward from the match instead, which cannot backtrack.
_HEREDOC_RE = re.compile(
    r"<<-?[ \t]*(?P<q>['\"]?)(?P<tag>[A-Za-z_]\w*)(?P=q)"
    r"\r?\n(?P<body>.*?)(?:^[ \t]*(?P=tag)\b|\Z)",
    re.DOTALL | re.MULTILINE,
)
_SHELL_WORD_RE = re.compile(r"(?:^|[/\\])(?:ba|z|k|da)?sh(?:\.exe)?$", re.IGNORECASE)


def _heredoc_data_spans(command: str) -> list[tuple[int, int]]:
    """Spans of heredoc bodies that are data rather than shell source."""
    spans = []
    if "<<" not in command:
        # Cheap reject so the common case never enters the regex at all.
        return spans
    for m in _HEREDOC_RE.finditer(command):
        # The receiving command is whatever sits on the line before the <<.
        line_start = command.rfind("\n", 0, m.start()) + 1
        head = command[line_start:m.start()]
        # If a shell is the thing reading it, the body really is executed.
        if any(_SHELL_WORD_RE.search(word) for word in head.split()):
            continue
        spans.append((m.start("body"), m.end("body")))
    return spans


def _quoted_spans(command: str) -> list[tuple[int, int]]:
    """Half open (start, end) ranges of the quoted literals in the command.

    Used to ignore an executor name that is only being talked about rather than
    run: in `echo "bash -c git push"` the whole thing is one string argument to
    echo, and nothing executes. An unterminated quote yields no span, so the
    tail stays scannable and the check stays conservative.
    """
    spans = []
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c in ("\"", "'"):
            j = i + 1
            while j < n and command[j] != c:
                j += 2 if (c == "\"" and command[j] == "\\") else 1
            if j >= n:
                break
            spans.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    return spans


def _executor_payloads(command: str, depth: int = 0) -> list[str]:
    """The argument each executor in the command would actually run.

    Returns only those arguments, quotes intact, never the surrounding command.
    That containment is the whole point: it is what tells
    `bash -c "git push"` (a real routed push) apart from
    `bash -c "ls" ; git commit -m "git push"` (a normal commit that happens to
    mention one).
    """
    payloads = []
    if depth > 3:
        # A wrapper nested this deep is pathological. Stop rather than recurse
        # without bound on a crafted input.
        return payloads
    spans = _quoted_spans(command)
    for head in _EXECUTOR_HEAD_RE.finditer(command):
        # An executor named inside a string is being quoted, not run.
        if any(start <= head.start() < end for start, end in spans):
            continue
        rest = command[head.end():].lstrip()
        if not rest:
            continue
        payload = _read_executed_argument(rest)
        if not payload:
            continue
        kind = "interpreter" if _INTERPRETER_EXEC_HEAD_RE.match(
            head.group(0)) else "shell"
        payloads.append((payload, kind))
        # A wrapper inside a wrapper still runs what it is given, so
        # `bash -c "eval 'git push'"` has to reach the inner push.
        payloads.extend(_executor_payloads(payload, depth + 1))
    return payloads


def _read_executed_argument(rest: str) -> str:
    """The single argument an executor runs, read off the front of `rest`.

    Adjacent quoted segments are concatenated because the shell concatenates
    them: `bash -c "git ""push"` is one word, `git push`, and really does push.
    Reading only as far as the first closing quote saw `git ` and let it
    through.
    """
    if rest[0] not in ("\"", "'"):
        # Starts bare, so it is an eval style argument that takes everything up
        # to the next shell separator rather than a single word.
        stop = _ARG_TERMINATOR_RE.search(rest)
        return rest[:stop.start()] if stop else rest

    # One shell word, which the shell builds from any run of quoted segments and
    # bare characters with no whitespace between them. Continuing only while the
    # next character was itself a quote was not enough: `bash -c "git p"u"sh x"`
    # really runs `git push x`, and stopping at the bare `u` returned `git p`
    # and lost the verb entirely.
    parts = []
    i, n = 0, len(rest)
    while i < n:
        c = rest[i]
        if c in ("\"", "'"):
            end = rest.find(c, i + 1)
            if end == -1:
                # Unterminated. Take the remainder rather than dropping it, so
                # an unbalanced quote cannot hide the tail of a command.
                parts.append(rest[i + 1:])
                break
            parts.append(rest[i + 1:end])
            i = end + 1
        elif c.isspace() or c in ";&|":
            # Unquoted whitespace or a separator ends the word.
            break
        else:
            parts.append(c)
            i += 1
    return "".join(parts)

# Global git flags that change which repository the command acts on. -C is
# deliberately absent: settings.json covers it with Bash(git -C ** push **), so
# a -C push does get a prompt. These three have no rule of any kind, so a write
# behind one reaches the remote with nothing asking first, even sitting at the
# start of the command.
# Case matters here and IGNORECASE would be a bug: git's -C is the directory
# flag, which settings.json covers, while -c is the config flag, which it does
# not. Only the long flags are matched case insensitively.
# `.exe` is in here for the same reason as the flags: settings.json asks on the
# literal prefix "git push", which `git.exe push` does not start with, so a
# position 0 match spelled that way still gets no prompt from anyone.
_UNCOVERED_GIT_FLAG_RE = re.compile(
    r"(?i:--git-dir|--work-tree|\.exe)|(?<![-\w])-c(?:=|\s)")


def check_routed_git_write(command: str) -> str | None:
    """Block a git or gh write that no permission rule will prompt on.

    Claude Code matches permission rules against the raw command string by
    prefix, so `Bash(git push **)` catches `git push origin main` but not
    `xargs git push`, `GIT_SSH_COMMAND=x git push`, `git add . && git push`,
    or an aliased push. Each of those reaches the same remote while the ask
    rule never fires. No glob pattern can close that, because the bypass is in
    the shell semantics the matcher does not parse.

    So: find the write, then allow it through only in the shapes settings.json
    actually covers, which is the write at the very start of the command, with
    no global git flag in front of it other than -C. Everything else is routed
    and gets blocked here, because nothing downstream is going to ask.
    """
    # A heredoc body bound for a non shell is data, so it is blanked before any
    # scanning. Writing a script that mentions `git push` must not read as
    # running one. Length is preserved so every offset below still lines up.
    scannable = command
    for start, end in _heredoc_data_spans(command):
        scannable = scannable[:start] + (" " * (end - start)) + scannable[end:]

    cleaned = _strip_quoted(scannable)

    _WRITE_PATTERNS = (
        (_GIT_WRITE_RE, "git write"),
        (_GH_API_RE, "gh api call"),
        (_GH_WRITE_RE, "gh write"),
    )

    # Whatever an executor runs is routed by definition, so those arguments are
    # checked first. Each is quote stripped the same way the top level command
    # is, because a payload has its own inner quoting: in
    # `bash -c "grep 'git push' file"` the push is grep's search string, not a
    # command. Skipping that strip made the check block ordinary read only work.
    for payload, kind in _executor_payloads(scannable):
        # Shell source follows shell quoting, so it is read exactly like the top
        # level command. Interpreter source does not, and there a quoted string
        # is normally the thing being run, so it is scanned whole.
        scanned = payload if kind == "interpreter" else _strip_quoted(payload)
        for pattern, label in _WRITE_PATTERNS:
            for match in pattern.finditer(scanned):
                if kind != "interpreter" and not _in_command_position(
                        scanned, match.start()):
                    continue
                return (
                    f"BLOCKED: this command reaches a {label} "
                    f"({match.group(0).strip()!r}) inside a shell that runs it for you "
                    f"({payload.strip()[:60]!r}) rather than running it directly. "
                    "Permission rules match the raw command by prefix, so a write "
                    "wrapped in eval or a -c argument skips the prompt that a direct "
                    "one gets. Run the git or gh command as its own Bash call so the "
                    "ask rule applies."
                )

    for pattern, label in _WRITE_PATTERNS:
        for match in pattern.finditer(cleaned):
            # Not the command being run, just words handed to something else.
            if not _in_command_position(cleaned, match.start()):
                continue

            matched = match.group(0)
            # Position 0 plus no uncovered global flag is the one shape a
            # permission rule can see, so it is left for the prompt to handle.
            if match.start() == 0 and not _UNCOVERED_GIT_FLAG_RE.search(matched):
                continue

            prefix = cleaned[:match.start()].strip()
            via = f"through {prefix!r}" if prefix else "behind a global git flag"
            return (
                f"BLOCKED: this command reaches a {label} "
                f"({matched.strip()!r}) {via} rather than running it "
                "directly. Permission rules match the raw command by prefix, so a routed "
                "write skips the prompt that a direct one gets. Run the git or gh command "
                "as its own Bash call so the ask rule applies."
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
    for check in [check_db_mutation, check_production_environment, check_destructive_delete, check_env_var_expansion, check_cat_heredoc, check_ssh_external, check_netcat, check_curl_external, check_coauthor, check_python_multiline_c, check_cd_compound, check_backslash_spaces, check_routed_git_write]:
        msg = check(command)
        if msg:
            print(msg, file=sys.stderr)
            _write_block_telemetry("Bash", command, msg)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
