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
 11. non-read git/gh verbs       — positive allowlist, parsed, wrapper-aware
 12. writes to the guard's own files, and reads of any .env
 13. shell routing: pipe-to-shell, find -exec, awk system(), sed e

Two layers with different jobs. Checks 1-9 exist to dodge a Claude Code BUILT-IN
scanner that prompts regardless of the allow list; they are ergonomics. Checks
10-13 are the security boundary, and they are here rather than in the permission
list because the list structurally cannot express them: its rules match the raw
command string by prefix, so `xargs git commit` and `find . -exec git commit ;`
match no `Bash(git commit *)` rule and run unasked.

Off switch: CLAUDEBOOST_BASH_GUARD=off disables the ergonomic half only. It no
longer disables the security half. One env var that turns off the whole boundary
is not a boundary, and the value of the switch was always unblocking a workflow
that checks 1-9 obstruct.

Fail safe: an ergonomic check that raises is skipped; a security check that
raises blocks. A guard that cannot decide has no basis to allow, and exiting
non-zero-but-not-2 is the documented silent failure of this hook contract (exit
1 is neither allow nor block, so the command runs anyway).

Exit codes:
  0 = allow (pass)
  2 = block (Claude sees stderr message and retries)
"""
from __future__ import annotations

import json
import os
import re
import sys
# pathlib is not imported for the same reason as urllib.parse below: it cost
# 9ms of this hook's startup to build one string. os.path does that without the
# import. normpath rather than a bare string because Path collapsed a `//` and
# a `.` segment, and the prefix below is compared with startswith, where a
# spelling difference is a hole. It also collapses `..`, which Path leaves
# alone, and that difference only ever makes the prefix match a real path it
# would otherwise have missed.
_BOOST_HOME = os.path.normpath(
    os.environ.get("CLAUDEBOOST_HOME")
    or os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

# urllib.parse is imported inside _url_host_is_local rather than here. It costs
# 30ms of this hook's 150ms, measured with -X importtime, and it is only needed
# for a command carrying a URL. The hook runs before every single Bash call, so
# that is 30ms paid on every `ls` to parse a URL that is usually not there.

# The value of a message flag is human prose, never a command. A commit or tag
# message that talks about curling a URL, or that contains a backslash before a
# space, is text and must not read as an invocation or as a shell-escaped path.
# Narrower on purpose than _strip_quoted: stripping every quoted span would also
# hide the real command in `bash -c "curl https://evil.example.com/x"`.
_MESSAGE_FLAG_RE = re.compile(
    r"(?:^|\s)(?:-m|--message)(?:\s+|=)(?:'[^']*'|\"(?:[^\"\\]|\\.)*\"|\S+)"
)

# Binaries whose -m really is --message. Spelling alone is not enough to know:
# curl's own -m is --max-time, so a strip that does not check which binary it
# is reading deletes `curl -m https://evil.example.com/x`'s destination URL and
# hands the call a clean bill of health.
_MESSAGE_COMMAND_RE = re.compile(r"\b(?:git|gh|hg|svn|jj|bzr)(?:\.exe)?\b", re.IGNORECASE)

# What ends the command a flag belongs to, for the lookback above. Quoting is
# not tracked here: a separator inside a quoted message only shortens the
# lookback, which at worst leaves a message value unstripped.
_SEPARATOR_SPLIT_RE = re.compile(r"[;&|\n`()]")


def _strip_message_values(command: str) -> str:
    """The command with the value of every -m/--message flag removed.

    Only within a command that has message semantics. Two commands can spell
    the same flag with different meanings, so the binary in front of the flag
    decides: git's -m takes prose to discard, curl's -m takes a timeout and the
    token after it may be the destination itself.
    """
    def drop_if_a_message(match: re.Match) -> str:
        segment = _SEPARATOR_SPLIT_RE.split(command[:match.start()])[-1]
        return " " if _MESSAGE_COMMAND_RE.search(segment) else match.group(0)

    return _MESSAGE_FLAG_RE.sub(drop_if_a_message, command)


def _write_block_telemetry(tool: str, summary: str, reason: str,
                           result: str = "blocked") -> None:
    """Write a PreToolUse block event to claude-actions.jsonl.

    PostToolUse never fires when a PreToolUse hook exits 2, so we capture
    the block here before returning.

    `result` is also how a check that crashed and was skipped gets recorded.
    Swallowing that would be a silent failure, and this file is the only sink
    a PreToolUse hook has: stderr on an allow would show Claude a message about
    a command that ran fine.
    """
    try:
        sys.path.insert(0, os.path.join(_BOOST_HOME, "scripts"))
        from telemetry_writer import now_iso, session_id, write_telemetry
        record = {
            "ts": now_iso(),
            "session_id": session_id(),
            "tool": tool,
            "summary": f"{tool} {summary[:200]}",
            "result": result,
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


_LOCALHOST_NAMES = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})

# RFC 6761 reserves .test and RFC 6762 reserves .local, so neither can ever be
# a real organisation's zone. They ship allowed. Every other environment a
# machine may reach is site specific and names somebody's infrastructure, so it
# lives in the gitignored file below instead of in tracked source.
_BUILTIN_DEV_SUFFIXES = frozenset({".local", ".test"})

# Site specific browser and curl targets. `.claude/browser-targets.example.json`
# is the committed shape, and carries the rules a new entry has to satisfy.
#
# Absent, unreadable or malformed, this file contributes nothing and the guard
# allows only localhost plus the two reserved suffixes above. Deny by default is
# the required direction for an allowlist (OWASP Proactive Controls C5): a
# config the guard cannot read must never widen what a browser can reach.
_BROWSER_TARGETS_PATH = os.path.join(
    _BOOST_HOME, ".claude", "browser-targets.local.json")

_browser_targets: tuple[frozenset[str], frozenset[str]] | None = None


def _valid_suffix(entry: str) -> bool:
    """A suffix entry has to be a dotted zone of at least two labels.

    The leading dot is the only thing making the endswith() below a label
    boundary rather than a substring: "evil-env-dev.contoso.com" does not end
    with ".env-dev.contoso.com", because the character before the label is
    "-". Stored undotted, that evasion starts working.

    Two labels minimum because a bare ".com" would allow the entire TLD, and
    the whole point of the file is naming one zone at a time.
    """
    return (entry.startswith(".")
            and entry == entry.lower()
            and entry.isascii()
            and "/" not in entry
            and len(entry[1:].split(".")) >= 2
            and all(entry[1:].split(".")))


def _valid_host(entry: str) -> bool:
    """An exact host entry is a bare hostname, never a URL and never a zone."""
    return (not entry.startswith(".")
            and entry == entry.lower()
            and entry.isascii()
            and "/" not in entry
            and ":" not in entry
            and "." in entry)


def _load_browser_targets() -> tuple[frozenset[str], frozenset[str]]:
    """Read the site config once per process, on the first host actually checked.

    Lazy for the same reason urllib.parse is imported lazily: this hook runs
    before every Bash call, and most of them carry no URL at all.
    """
    global _browser_targets
    if _browser_targets is not None:
        return _browser_targets

    suffixes, hosts = set(_BUILTIN_DEV_SUFFIXES), set()
    try:
        with open(_BROWSER_TARGETS_PATH, encoding="utf-8") as handle:
            config = json.load(handle)
        raw_suffixes = config.get("allowed_suffixes") or []
        raw_hosts = config.get("allowed_hosts") or []
        if isinstance(raw_suffixes, list):
            suffixes.update(e for e in raw_suffixes
                            if isinstance(e, str) and _valid_suffix(e))
        if isinstance(raw_hosts, list):
            hosts.update(e for e in raw_hosts
                         if isinstance(e, str) and _valid_host(e))
    except (OSError, ValueError, AttributeError):
        # No file, bad JSON, wrong shape: keep the builtin set and allow
        # nothing extra. A guard that cannot read its config has no basis to
        # widen, which matches this hook's "fail safe" rule at the top.
        pass

    _browser_targets = (frozenset(suffixes), frozenset(hosts))
    return _browser_targets


def _host_is_allowed_dev_env(host: str) -> bool:
    """True when the host sits inside an allowed test or dev domain.

    Three normalisations happen before the comparison, and each one closes a
    way of writing the same host that would otherwise read as a different one:

    - Case, because DNS is case insensitive and API.EXAMPLE is the same host.
    - A trailing dot, because "app.env-e.example.com." is a valid FQDN naming
      that host. Without the strip it fails closed rather than open, but the
      next person to notice would be tempted to loosen the comparison instead
      of stripping, which is how the boundary check gets lost.
    - Non ASCII is refused outright. str.lower() does not fold Cyrillic
      homographs, so an IDN lookalike of a real dev domain would otherwise be
      compared as if it were a different string that happens to render the
      same. The exact-set check above never needed this because none of four
      loopback literals has a plausible homograph; a real corporate domain does.
    """
    host = host.lower().rstrip(".")
    if not host or not host.isascii():
        return False
    suffixes, hosts = _load_browser_targets()
    if host in hosts:
        return True
    return any(
        host == suffix[1:] or host.endswith(suffix)
        for suffix in suffixes
    )

# curl flags whose value is request content rather than a destination: a body,
# a header, a form field, a cookie. A URL sitting in one of those is never
# connected to, so it must not be read as a target.
_CURL_PAYLOAD_FLAG_RE = re.compile(
    r"(?:^|\s)(?:--data-raw|--data-binary|--data-urlencode|--data-ascii|--data|-d"
    r"|--header|-H|--form-string|--form|-F|--json"
    r"|--cookie|-b|--user-agent|-A|--referer|-e)"
    r"(?:\s+|=)(?:'[^']*'|\"[^\"]*\"|\S+)"
)

_URL_RE = re.compile(r"https?://[^\s'\"`|;&)]+", re.IGNORECASE)


def _url_host_is_local(url: str) -> bool:
    """True only when the URL's destination host is provably this machine.

    An RFC 3986 authority is [userinfo "@"] host [":" port], so reading the
    host as everything before the first colon returns the *username* for
    user:pass@host: https://127.0.0.1:secret@evil.example.com/ reads as
    127.0.0.1 while curl connects to evil.example.com. That is the bug class
    behind open-webui GHSA-8w7q-q5jp-jvgx. urlsplit() applies the real
    grammar, so the parse is not hand-rolled here.

    Userinfo is refused outright rather than parsed past, because curl and
    urlsplit disagree on odd authorities (a backslash ahead of the @, the
    same advisory's actual payload) and a call to this machine never needs
    credentials in the URL. An authority urlsplit cannot parse is not local
    either: unparseable is not evidence of safety.
    """
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        if "@" in parts.netloc or "\\" in parts.netloc:
            return False
        host = parts.hostname
    except ValueError:
        return False
    if not host:
        return False
    return host.lower() in _LOCALHOST_NAMES or _host_is_allowed_dev_env(host)


_CURL_TOKEN_RE = re.compile(r"\bcurl(?:\.exe)?\b", re.IGNORECASE)

# curl flags that decide the TCP endpoint independently of the URL, so the URL
# in the command can read "localhost" while the bytes go anywhere. --resolve
# and --connect-to remap host:port to another address; the proxy flags send the
# whole request somewhere else first. curl's own --help all names them:
# "--connect-to <HOST1:PORT1:HOST2:PORT2>  Connect to host2 instead of host1"
# and "--resolve <[+]host:port:addr[,addr]...>  Resolve host+port to address".
# Refused outright rather than followed: reading the value would mean
# reimplementing curl's address selection, and nothing in this project uses one.
_CURL_REMAP_FLAG_RE = re.compile(
    r"(?:^|\s)(--resolve|--connect-to|--proxy|-x|--preproxy"
    r"|--socks4|--socks4a|--socks5|--socks5-hostname|--proxy1\.0)(?:[=\s]|$)"
)

# -K/--config makes curl read further options, the URL included, out of a file.
# The destination then never appears in the command string at all, so there is
# nothing here to check and "cannot tell" is not "safe".
_CURL_CONFIG_FLAG_RE = re.compile(r"(?:^|\s)(--config|-K)(?:[=\s]|$)")

# A shell control operator ends the curl invocation's own arguments.
_CURL_ARG_END = frozenset(";|&\n`)")


def _curl_argument_span(text: str, start: int) -> str:
    """`text` from `start` up to the first unquoted shell control operator.

    A curl invocation owns only its own arguments. Reading past the separator
    made an unrelated later command's URL look like curl's destination, and
    reading a URL from an earlier one was the same mistake in reverse.
    """
    quote = None
    i, n = start, len(text)
    while i < n:
        char = text[i]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in _CURL_ARG_END:
            return text[start:i]
        i += 1
    return text[start:]


def _curl_flag_problem(args: str) -> str | None:
    """Why this curl argument list connects somewhere the URL does not name."""
    remap = _CURL_REMAP_FLAG_RE.search(args)
    if remap:
        return (
            f"BLOCKED: curl {remap.group(1)} is not allowed. It chooses the address "
            "curl actually connects to, so the URL in the command stops meaning "
            "anything: a request reading http://localhost/ can be pointed at any "
            "host on the internet. Call the local service by its real URL with no "
            "connection-remapping flag."
        )
    config = _CURL_CONFIG_FLAG_RE.search(args)
    if config:
        return (
            f"BLOCKED: curl {config.group(1)} reads its options, the destination URL "
            "included, from a file this guard cannot see. Pass the URL and flags on "
            "the command line so the destination is visible."
        )
    return None


def check_curl_external(command: str) -> str | None:
    """Block curl reaching anything other than this machine.

    Catches curl anywhere in the command — including compound commands like
    `sleep 40 && curl https://external.com` and `curl ... | head`.

    Every destination has to be local, not just one of them: a command that
    mixes an external URL with a localhost one still reaches the external
    host. And the destination is not only the URL: the flags in
    _curl_flag_problem pick the address independently of it.

    The two halves are scoped differently on purpose. Any URL anywhere in the
    command counts, because narrowing that to one invocation's own arguments
    loses `URL=https://evil/x ; curl $URL` and `echo "curl https://evil/x" | sh`,
    where the URL and the fetch are not in the same span. The flags are read
    per invocation instead, because an unscoped flag denylist blocks grepping
    for the flag name or writing it in a commit message.
    """
    prose_free = _strip_message_values(command)
    if not _CURL_TOKEN_RE.search(prose_free):
        return None

    for text, kind in [(prose_free, "shell")] + _executor_payloads(prose_free):
        for match in _CURL_TOKEN_RE.finditer(text):
            # Interpreter source does not follow shell quoting, so a quoted
            # string there is normally the command being run. Read whole, the
            # same way check_routed_git_write reads one.
            if kind != "interpreter" and not _in_command_position(text, match.start()):
                continue
            problem = _curl_flag_problem(_curl_argument_span(text, match.end()))
            if problem:
                return problem

    for url in _URL_RE.findall(_CURL_PAYLOAD_FLAG_RE.sub(" ", prose_free)):
        if not _url_host_is_local(url):
            return (
                "BLOCKED: curl to this URL is not allowed. Only localhost "
                "(localhost, 127.0.0.1, 0.0.0.0, ::1), *.local, *.test, and "
                "whatever .claude/browser-targets.local.json names are "
                f"permitted. Found: {url}"
            )
    return None


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
    """Detect backslash-escaped spaces in paths.

    The value of a -m/--message flag is dropped first. The lookbehind below
    only excludes a match whose single preceding character is a quote, so a
    backslash-space a few words into an already-quoted commit message reads
    as an unquoted escaped path when nothing about it needs escaping.
    """
    # Match backslash-space that looks like path escaping, not inside quotes
    # Common pattern: /some/path/F\ and\ B\ PWA/
    if re.search(r"(?<![\"'])\b\S+\\ \S+", _strip_message_values(command)):
        return (
            "BLOCKED: Do not backslash-escape spaces in paths. "
            "Use double-quoted paths instead: \"/path/X and Y PWA/Litware\". "
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
#
# `parallel ::: <arg>` belongs here rather than with the wrappers: GNU
# parallel's design document has it running `$SHELL -c $COMMAND`, so each :::
# argument is a shell command line and not an opaque operand.
_SHELL_EXEC_HEAD_RE = re.compile(
    r"\beval\b"
    r"|\b(?:ba|z|k|da)?sh" + _EXEC_FLAG_RUN + r"\s+-[a-zA-Z]*c\b"
    r"|\b(?:ba|z|k|da)?sh" + _EXEC_FLAG_RUN + r"\s*<<<"
    r"|\b(?:pwsh|powershell)(?:\.exe)?" + _EXEC_FLAG_RUN + r"\s+-(?:c|Command)\b"
    r"|\bcmd(?:\.exe)?\s+/[ckCK]\b"
    r"|\bparallel\b(?:\s+-\S+)*\s+::::?",
    re.IGNORECASE,
)

# An interpreter. Its argument is source in another language, where a quoted
# string is usually the command being run rather than data:
# `python -c "os.system('git push')"` really pushes. Shell quoting rules do not
# apply, so the payload is scanned whole rather than stripped and position
# checked. The cost is that a program legitimately handling the literal text
# "git push" gets blocked, which is a fair trade for a one line interpreter
# invocation.
# php spells the flag -r, and it is listed separately rather than folded into
# the alternation because node's own -r preloads a module (`node -r
# ts-node/register app.js`), which is an operand and not source.
_INTERPRETER_EXEC_HEAD_RE = re.compile(
    r"\b(?:python[\d.]*|perl|ruby|node|php|Rscript)\s+-(?:c|e)\b"
    r"|\bphp(?:\.exe)?\s+-r\b",
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
    r"|parallel(?:\s+-\S+)*"
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
#
# `<<tag` is a redirection operator, not the whole line. POSIX 2.7.4: the body
# "shall begin after the next <newline>", so anything else on that line -- a
# redirect, a pipe, a background '&', a comment, a second heredoc operator --
# sits legally between the tag and the newline. `tail` absorbs it. Requiring
# the newline immediately after the tag instead made `cat <<EOF > f.txt` and
# `cat <<EOF | grep x` match nothing at all, so their bodies were scanned as
# command text and an ordinary heredoc was refused.
#
# `tail` is not skipped over, it is read: a shell named there executes the body
# just as surely as one named before the << does (`cat <<EOF | bash`), so it
# joins the head in the shell check below.
#
# The lookaround excludes `<<<`, which is a herestring and has no body. Without
# it the widened tail lets `cat <<<EOF | x` match and blank the rest of the
# command, which is the allow-more direction.
#
# The `\b` after the tag is load bearing, and it is the same defect the
# paragraph above records, reached a second way. `\w*` and `[^\n]*` both match
# a plain letter, so once they sit next to each other the engine tries every
# way to split one word run between them: `echo <n a's> << <n b's>` measured
# 0.05ms before the tail group and 930ms at n=8000 after it, growing
# quadratically. A delimiter is one word, so `\b` only ever holds at the end of
# the maximal run -- the same match the greedy quantifier finds first -- and
# every shorter split now dies on the boundary instead of rescanning the tail.
# That restored 930ms to 0.4ms. `\b` rather than `\w*+`, because possessive
# quantifiers need Python 3.11 and this tree's floor is 3.9.
_HEREDOC_RE = re.compile(
    r"(?<!<)<<(?!<)-?[ \t]*(?P<q>['\"]?)(?P<tag>[A-Za-z_]\w*)\b(?P=q)"
    r"(?P<tail>[^\n]*)\r?\n(?P<body>.*?)(?:^[ \t]*(?P=tag)\b|\Z)",
    re.DOTALL | re.MULTILINE,
)
_SHELL_WORD_RE = re.compile(r"(?:^|[/\\])(?:ba|z|k|da)?sh(?:\.exe)?$", re.IGNORECASE)

# Word boundaries on the operator line. str.split() breaks on whitespace only,
# so `cat <<EOF|bash` reads as the single word "cat|bash", which matches no
# shell name and hands a body that really is executed back as data. A shell
# delimits on its control operators with no whitespace required (POSIX 2.3
# Token Recognition). Splitting on them too only ever ADDS candidate words, so
# this can find a shell the old split missed and never hide one it found.
_OPERATOR_LINE_SPLIT_RE = re.compile(r"[;|&()<>\s]+")

_QUOTE_CHAR_RE = re.compile(r"['\"]")

# Command boundaries on the operator line, without the whitespace that
# _OPERATOR_LINE_SPLIT_RE also breaks on. Keeping segments intact is what makes
# each command name locally identifiable, so deciding whether one is in command
# position needs no look back at the text in front of it.
_OPERATOR_SEGMENT_SPLIT_RE = re.compile(r"[;|&()<>]+")

# What may sit in front of a command name without being it: an assignment, a
# hand-off runner, or a flag belonging to one. This is _ROUTER_PREFIX as whole
# tokens. That pattern is not reused directly because it is a look behind, and
# anchoring it per candidate costs a copy of everything to the left -- 8000
# candidates on a 40KB line measured 4.3s against the hook's 5s bound, the same
# quadratic shape the two notes on _HEREDOC_RE record.
_ROUTER_WORD_RE = re.compile(
    r"[A-Za-z_]\w*=\S*|-\S*"
    r"|xargs|timeout|env|nohup|sudo|nice|time|command|builtin|exec"
    r"|then|do|else",
    re.IGNORECASE,
)


def _shell_reads_body_in_command_position(operator_line: str) -> bool:
    """Is a shell the command name on this heredoc's operator line?

    Quotes are inert at a command name -- POSIX 2.6 applies quote removal
    before 2.9.1 takes the first remaining field as the command name -- so
    `cat <<EOF | "bash"` runs the body exactly as the bare form does.

    Dropping quotes widens what counts as a shell, so only a command name is
    dequoted. Doing it line-wide would refuse `cat <<EOF | grep "bash"`, where
    the word is grep's argument and nothing executes the body.
    """
    for segment in _OPERATOR_SEGMENT_SPLIT_RE.split(operator_line):
        for token in segment.split():
            if _ROUTER_WORD_RE.fullmatch(token):
                continue
            # The first token that is not a prefix is the command name; what
            # follows it are that command's arguments, not another name.
            if _SHELL_WORD_RE.search(_QUOTE_CHAR_RE.sub("", token)):
                return True
            break
    return False


def _heredoc_data_spans(command: str) -> list[tuple[int, int]]:
    """Spans of heredoc bodies that are data rather than shell source.

    Only the first heredoc on an operator line is classified. POSIX 2.7.4 says
    a second `<<` on the same line takes the body after the first one's
    terminator, and following that queue is more machinery than the shape is
    worth; the later bodies stay scannable instead, which refuses more rather
    than allowing more.
    """
    spans = []
    if "<<" not in command:
        # Cheap reject so the common case never enters the regex at all.
        return spans
    for m in _HEREDOC_RE.finditer(command):
        # Everything on the operator line except the operator itself: the
        # receiving command before the <<, and whatever follows the tag.
        line_start = command.rfind("\n", 0, m.start()) + 1
        operator_line = command[line_start:m.start()] + " " + m.group("tail")
        # If a shell is the thing reading it, the body really is executed.
        if any(_SHELL_WORD_RE.search(word)
               for word in _OPERATOR_LINE_SPLIT_RE.split(operator_line)):
            continue
        # The split above tests words with their quotes still attached, so it
        # misses `cat <<EOF | "bash"`, which really does execute the body.
        if _shell_reads_body_in_command_position(operator_line):
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


# ===========================================================================
# The parsing layer.
#
# Everything above this line matches patterns against command text. That is
# enough for the ergonomic checks, and not enough for a boundary: the same
# `git commit` reads as an argument to echo, a search string to grep, a routed
# write behind xargs, or the command itself, and only splitting the command
# into words tells those apart.
#
# Hand-rolled scanning rather than shlex or bashlex. Three reasons, all of
# which are failure modes on this machine rather than preferences:
#   1. shlex.split() raises ValueError on an unbalanced quote. A PreToolUse hook
#      that raises exits 1, and exit 1 is neither allow (0) nor block (2) under
#      this contract, so the command runs with a traceback shown to nobody.
#   2. shlex in POSIX mode consumes backslashes, which destroys a Windows path.
#      This tree runs under Git Bash on Windows and sees C:/x and C:\x alike.
#   3. bashlex is a third party dependency and does not parse every builtin
#      (`time` among them). No other hook in this tree has a third party import.
# The cost is real and accepted: a true grammar catches more, but it rejects
# valid commands on esoteric quoting, and an agent that gets rejected reaches
# for eval. https://github.com/dwarvesf/claude-guardrails reaches the same
# place from the same constraint -- regex-scan the whole command in the hook,
# "so chains, wrappers, and subshells all get caught".
# ===========================================================================

# Redirections are their own words so a redirect target can be identified. A
# leading file descriptor (`2>`) flushes as its own word first, which is
# harmless: the operator still lands next to its target.
_REDIRECT_CHARS = "<>"

# What a consumed `$(...)` or backtick leaves behind in the word it sat in.
# The body is lifted out and judged as its own command; this stands for the
# text it will produce, which nothing can know until it runs.
#
# It has to be a character that survives word splitting rather than the space
# that used to go here. A space cut `out-$(date).txt` into two words and left
# the visible half looking like a complete, ordinary path.
_SUBSTITUTION_MARK = "\x00sub\x00"

# Every operator that ends one command and starts another. `(` and `)` are in
# here for a subshell; `$(` never reaches this set because command substitution
# is consumed before it.
_SEGMENT_OPERATOR_CHARS = ";&|\n()"


def _shell_words(text: str) -> list[str]:
    """`text` split into shell words, with quotes removed and redirect
    operators emitted as their own words.

    Backslash is deliberately NOT treated as an escape. Under Git Bash a
    backslash does escape, but the commands this guard sees carry Windows paths
    far more often than escaped metacharacters, and consuming the backslash
    turns C:\\Users\\x into CUsersx -- which is what the path checks below match
    against. Leaving it literal can only under-split, never hide a word.
    """
    words: list[str] = []
    current: list[str] = []
    quoted = False
    quote = None
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if quote is not None:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "\"'":
            quote = char
            quoted = True
        elif char.isspace():
            if current or quoted:
                words.append("".join(current))
            current, quoted = [], False
        elif char in _REDIRECT_CHARS:
            if current or quoted:
                words.append("".join(current))
            current, quoted = [], False
            run = i
            while i < n and text[i] in _REDIRECT_CHARS:
                i += 1
            words.append(text[run:i])
            continue
        else:
            current.append(char)
        i += 1
    if current or quoted:
        words.append("".join(current))
    return words


def _read_substitution(text: str, start: int) -> tuple[str, int]:
    """The body of a `$(...)` beginning at `start`, and the index after it."""
    depth, i, n = 1, start, len(text)
    while i < n:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    return text[start:], n


def _split_segments(text: str, depth: int = 0) -> list[tuple[str, str]]:
    """(separator, segment) for each command in `text`, quote aware.

    The separator is the operator run that preceded the segment, empty for the
    first one. It is kept because pipe-into-shell is a different thing from
    the same shell run on its own.

    A `$(...)` or backtick body is lifted out and returned as its own segment,
    carrying "$(" as its separator: a substitution runs a command exactly as a
    bare one does, and leaving it inline would hide the command inside what
    looks like one word.
    """
    if depth > 4:
        return [("", text)]
    segments: list[tuple[str, str]] = []
    current: list[str] = []
    separator = ""
    quote = None
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if quote == "'":
            current.append(char)
            if char == "'":
                quote = None
            i += 1
            continue
        if quote is None and char == "'":
            quote = "'"
            current.append(char)
            i += 1
            continue
        if char == '"':
            quote = None if quote == '"' else '"'
            current.append(char)
            i += 1
            continue
        if char == "$" and text.startswith("$(", i):
            body, after = _read_substitution(text, i + 2)
            for _, inner in _split_segments(body, depth + 1):
                segments.append(("$(", inner))
            current.append(_SUBSTITUTION_MARK)
            i = after
            continue
        if char == "`":
            end = text.find("`", i + 1)
            if end == -1:
                i += 1
                continue
            for _, inner in _split_segments(text[i + 1:end], depth + 1):
                segments.append(("`", inner))
            current.append(_SUBSTITUTION_MARK)
            i = end + 1
            continue
        if quote is None and char in _SEGMENT_OPERATOR_CHARS:
            segments.append((separator, "".join(current)))
            current = []
            run = i
            while i < n and text[i] in _SEGMENT_OPERATOR_CHARS:
                i += 1
            separator = text[run:i]
            continue
        current.append(char)
        i += 1
    segments.append((separator, "".join(current)))
    return [(sep, seg.strip()) for sep, seg in segments if seg.strip()]


def _binary_name(word: str) -> str:
    """The bare, comparable name of the binary a word names.

    Path, quotes, case and a .exe suffix all come off, because every one of
    them is a spelling that a literal permission rule misses and the shell does
    not: `Git commit`, `git.exe commit` and `/usr/bin/git commit` are one
    command.
    """
    word = word.strip("\"'").replace("\\", "/")
    name = word.rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


# The groups are read by _record_assignments, which needs the value and not
# just the shape. _strip_wrappers tests the match alone.
_ASSIGNMENT_WORD_RE = re.compile(r"^([A-Za-z_]\w*)=(.*)$")

# A command that hands off to whatever follows it rather than being the thing
# that runs. claude-code-bash-guardian keeps the same category under the name
# `wrapper_commands` (sudo, timeout, xargs, env, nice) for the same reason: a
# denylist that reads only the first word is bypassed by putting any of these
# in front of it. `start` and `wt.exe` are Windows spellings of the same idea.
_WRAPPER_WORDS = frozenset({
    "builtin", "chroot", "command", "do", "doas", "else", "elif", "env",
    "exec", "ionice", "nice", "nohup", "parallel", "setsid", "start", "stdbuf",
    "sudo", "then", "time", "timeout", "watch", "wt", "xargs",
})

# The wrappers that do not just hand off, they append arguments of their own.
# POSIX: xargs "shall construct a command line consisting of the utility and
# argument operands specified followed by as many arguments read in sequence
# from standard input as fit in length and number constraints". GNU parallel
# builds the same line from ::: or -a instead.
#
# That extra text is the whole problem. Everything this guard decides about a
# git or gh command it decides from the verb, and behind a feeder the verb can
# arrive from stdin or a file, where nothing can read it.
_ARG_FEEDER_WORDS = frozenset({"parallel", "xargs"})

# What may sit between a wrapper and the command it runs: its own flags, a
# bare duration (`timeout 5`), a numeric level (`nice -n 10`), an xargs
# placeholder (`-I{}`), or an environment assignment.
_WRAPPER_OPERAND_RE = re.compile(r"^(?:-|\d|\{\}|\+|[A-Za-z_]\w*=)")

# Feeder flags whose value is the next word rather than part of it. `xargs -n3`
# is one word and stopped in the right place; `xargs -a args.txt git` was not,
# so the scan stopped on `args.txt` and never reached the `git` behind it.
# Case is significant: xargs gives -E and -e, -I and -i, -L and -l different
# meanings. Only feeders consult this, so timeout and nice keep their existing
# numeric handling.
_FEEDER_VALUE_FLAGS = frozenset({
    "-a", "--arg-file", "-d", "--delimiter", "-E", "-e", "--eof",
    "-I", "-i", "--replace", "-L", "-l", "--max-lines", "-n", "--max-args",
    "-P", "--max-procs", "-s", "--max-chars",
    "-j", "--jobs", "-N", "--colsep", "-S", "--sshlogin", "--results",
})


def _strip_wrappers(words: list[str]) -> tuple[list[str], list[str]]:
    """(the command words, the wrapper names removed to reach them)."""
    stripped: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if _ASSIGNMENT_WORD_RE.match(word):
            index += 1
            continue
        name = _binary_name(word)
        if name in _WRAPPER_WORDS:
            stripped.append(name)
            index += 1
            feeder = name in _ARG_FEEDER_WORDS
            while index < len(words) and _WRAPPER_OPERAND_RE.match(words[index]):
                takes_value = feeder and words[index] in _FEEDER_VALUE_FLAGS
                index += 2 if takes_value else 1
            continue
        break
    return words[index:], stripped


def _without_redirections(words: list[str]) -> list[str]:
    """`words` with redirect operators, their targets, and any attached file
    descriptor dropped.

    `git branch -a 2>/dev/null` splits to [git, branch, -a, 2, >, /dev/null].
    The bare `2` read as a branch name, so a read-only listing was refused as a
    ref creation. Redirect targets are still checked, by the protected path
    scan, which reads the unstripped words for exactly that reason.
    """
    kept: list[str] = []
    skip = False
    for word in words:
        if skip:
            skip = False
            continue
        if word and set(word) <= set(_REDIRECT_CHARS):
            # The descriptor flushed as its own word just before the operator.
            if kept and kept[-1].isdigit():
                kept.pop()
            skip = True
            continue
        kept.append(word)
    return kept


def _command_words(segment: str) -> list[str]:
    """The words of the command a segment actually runs.

    Leading assignments and wrapper commands are removed, so `env FOO=1 timeout
    5 git commit` and `git commit` return the same thing. Returns [] when the
    segment runs nothing.
    """
    return _strip_wrappers(_without_redirections(_shell_words(segment)))[0]


def _is_fed(segment: str) -> bool:
    """True when an argument feeder will append words this guard cannot read."""
    return any(name in _ARG_FEEDER_WORDS
               for name in _strip_wrappers(
                   _without_redirections(_shell_words(segment)))[1])


def _is_wrapped(segment: str) -> bool:
    """True when something sits between the segment start and the command.

    A wrapped command is invisible to the permission engine, which matches the
    raw string by prefix. That distinction is the only thing separating a
    `git fetch` that still gets its prompt from one that does not.

    Redirections are removed from both sides: `git fetch 2>/dev/null` is the
    permission engine's own prefix match either way, so counting a redirect as
    a wrapper would refuse it for a route nothing actually takes.
    """
    words = _without_redirections(_shell_words(segment))
    return _command_words(segment) != words


_SHELL_BINARIES = frozenset({
    "sh", "bash", "zsh", "ksh", "dash", "ash", "busybox",
    "pwsh", "powershell", "cmd", "eval",
})


# ---------------------------------------------------------------------------
# git: a positive allowlist of read verbs.
#
# A denylist cannot be finished. `git help -a` on git 2.55 lists 150 commands
# across porcelain, ancillary and plumbing, a user alias resolves to any of
# them, and the next release adds more. The proposal this replaces had grown
# to 820 permission entries still missing `commit-graph write`,
# `multi-pack-index write`, `maintenance run` and `credential approve`.
#
# The set below is the complement: everything that touches no index, working
# tree, ref, remote, config, stash, object store or credential store. It was
# checked against the verbs that actually run in this machine's transcripts
# (scratchpad/verbfreq.py: diff, status, log, show, rev-parse, ls-files, grep,
# branch, merge-base, ls-tree, remote, ls-remote, check-ignore, cat-file,
# rev-list, for-each-ref, merge-tree, count-objects) so the allowlist covers
# real work rather than a guess at it.
# ---------------------------------------------------------------------------
_GIT_READ_VERBS = frozenset({
    "annotate", "blame", "bugreport", "cat-file", "check-attr", "check-ignore",
    "check-mailmap", "check-ref-format", "cherry", "column", "count-objects",
    "describe", "diff", "diff-files", "diff-index", "diff-pairs", "diff-tree",
    "for-each-ref", "fsck", "get-tar-commit-id", "grep", "help",
    "interpret-trailers", "log", "ls-files", "ls-remote", "ls-tree",
    "merge-base", "merge-tree", "name-rev", "patch-id", "range-diff",
    "rev-list", "rev-parse", "shortlog", "show", "show-branch", "show-index",
    "show-ref", "status", "stripspace", "var", "verify-commit", "verify-pack",
    "verify-tag", "version", "whatchanged",
})

# Recorded decision, not an oversight: `git fetch` stays a prompt rather than a
# block. It writes only remote-tracking refs and ran 47 times in the
# transcripts. It is allowed only unwrapped, because a wrapped fetch is exactly
# the shape that skips the prompt this decision relies on.
_GIT_PROMPT_VERBS = frozenset({"fetch"})

# Verbs that are part read and part write. The empty string means the bare verb
# with no subcommand: `git remote` lists, `git reflog` shows, `git submodule`
# reports status -- but `git stash` with no subcommand is `git stash push`, so
# stash is deliberately absent from that set.
_GIT_READ_SUBCOMMANDS = {
    "bisect": frozenset({"log", "view"}),
    "lfs": frozenset({"env", "ls-files", "status", "version"}),
    "notes": frozenset({"list", "show"}),
    "reflog": frozenset({"", "show"}),
    "remote": frozenset({"", "get-url", "show"}),
    "stash": frozenset({"list", "show"}),
    "submodule": frozenset({"", "status", "summary"}),
    "worktree": frozenset({"list"}),
}

# Global flags that choose a different repository or a different git binary.
# -C is not here because pointing at another checkout does not by itself write
# anything, and the verb gate still applies inside it.
_GIT_UNSAFE_GLOBAL_FLAGS = frozenset({
    "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--exec-path",
})

# Global flags with no write side at all. Anything not here and not handled
# explicitly is refused, which is the point of an allowlist: a flag added by a
# future git release is unknown, and unknown is not safe.
_GIT_SAFE_GLOBAL_FLAGS = frozenset({
    "-p", "--paginate", "-P", "--no-pager", "--bare", "--no-replace-objects",
    "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs",
    "--icase-pathspecs", "--no-optional-locks", "--version", "--help",
    "-h", "--html-path", "--man-path", "--info-path", "--exec-path",
    "--attr-source", "--no-lazy-fetch", "--no-advice",
})

# `git -c <key>=<value>` is arbitrary code execution wearing a config flag.
# Verified on this machine: `git -c diff.external=<cmd> diff --ext-diff` and
# `git -c alias.x='!<cmd>' x` both ran the command. Enumerating the dangerous
# keys is the shape that already failed -- core.pager, core.editor,
# core.sshCommand, diff.external, alias.*, credential.helper were listed and
# pager.<cmd> and sequence.editor were not. So the keys that may be set are
# listed instead. Transcripts contain exactly one `git -c` use in 2299
# commands, so the cost of a short list is close to zero.
_GIT_SAFE_CONFIG_KEYS = frozenset({
    "color.ui", "core.abbrev", "core.quotepath", "i18n.logoutputencoding",
    "log.date", "diff.noprefix", "core.longpaths",
})

# Flags that make an otherwise read only verb write a file or run a program.
_GIT_UNSAFE_VERB_FLAGS = frozenset({
    "--output", "--open-files-in-pager", "--upload-pack", "--receive-pack",
    "--exec", "--ext-diff",
})

_GIT_BRANCH_WRITE_FLAGS = frozenset({
    "-d", "-D", "-m", "-M", "-c", "-C", "-f", "-u", "-t",
    "--delete", "--move", "--copy", "--force", "--track", "--no-track",
    "--set-upstream", "--set-upstream-to", "--unset-upstream",
    "--edit-description", "--create-reflog", "--recurse-submodules",
})
_GIT_TAG_WRITE_FLAGS = frozenset({
    "-a", "-s", "-m", "-F", "-d", "-f", "-u", "-e",
    "--annotate", "--sign", "--no-sign", "--local-user", "--delete",
    "--force", "--file", "--message", "--create-reflog", "--edit",
})
# Read flags that take a value, so the token after them is that value and not a
# branch or tag name being created.
_GIT_REF_VALUE_FLAGS = frozenset({
    "--contains", "--no-contains", "--merged", "--no-merged", "--points-at",
    "--sort", "--format", "--color", "--column", "-n",
})
_GIT_BRANCH_LIST_FLAGS = frozenset({"-l", "--list"})
_GIT_TAG_LIST_FLAGS = frozenset({"-l", "--list", "-v", "--verify", "-n"})

_GIT_CONFIG_READ_SUBCOMMANDS = frozenset({
    "get", "list", "get-all", "get-regexp", "get-urlmatch",
})
_GIT_CONFIG_WRITE_FLAGS = frozenset({
    "--add", "--replace-all", "--rename-section", "--remove-section",
    "--edit", "-e", "--unset", "--unset-all",
})


def _positional_args(args: list[str], value_flags: frozenset) -> list[str]:
    """Words in `args` that are not a flag and not a flag's value."""
    positionals, skip = [], False
    for word in args:
        if skip:
            skip = False
            continue
        if word.startswith("-"):
            skip = word in value_flags
            continue
        positionals.append(word)
    return positionals


def _git_global_flag_problem(args: list[str]) -> tuple[str | None, int]:
    """Why this git invocation's global flags are unsafe, and where the verb
    starts. `args` is everything after the word `git`."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        flag = args[index]
        name = flag.split("=", 1)[0]
        if name == "-C":
            index += 2
            continue
        if name == "-c" or (flag.startswith("-c") and len(flag) > 2):
            if name == "-c":
                key = args[index + 1] if index + 1 < len(args) else ""
                index += 2
            else:
                key, index = flag[2:], index + 1
            if key.split("=", 1)[0].lower() not in _GIT_SAFE_CONFIG_KEYS:
                return (
                    f"`git -c {key}` sets configuration for this one command, and "
                    "several config keys name a program git then runs "
                    "(diff.external, alias.*, core.pager, pager.<cmd>, "
                    "sequence.editor, core.sshCommand). Only a short list of "
                    "keys with no program in them is allowed here."
                ), index
            continue
        if name in _GIT_UNSAFE_GLOBAL_FLAGS and "=" in flag:
            return (
                f"the global flag {name} redirects git at another repository or "
                "another set of git binaries, so the verb that follows is not "
                "acting where it appears to."
            ), index
        if name in _GIT_UNSAFE_GLOBAL_FLAGS and name != "--exec-path":
            return (
                f"the global flag {name} redirects git at another repository, so "
                "the verb that follows is not acting where it appears to."
            ), index
        if name not in _GIT_SAFE_GLOBAL_FLAGS:
            return (
                f"the global flag {flag} is not one this guard recognises as "
                "read-only. Unknown is not safe for a flag that runs before the "
                "verb does."
            ), index
        index += 1
    return None, index


_GIT_CONFIG_VALUE_FLAGS = frozenset({"--type", "--default", "-f", "--file", "--blob"})
_GIT_CONFIG_READ_FLAGS = frozenset({
    "-l", "--list", "--get", "--get-all", "--get-regexp", "--get-urlmatch",
})


def _git_subcommand_problem(verb: str, args: list[str]) -> str | None:
    """Why this subcommand of a part read, part write verb is not a read."""
    subs = _positional_args(args, _GIT_REF_VALUE_FLAGS)
    sub = subs[0].lower() if subs else ""
    if sub in _GIT_READ_SUBCOMMANDS[verb]:
        return None
    allowed = ", ".join(sorted(s or "(no subcommand)"
                               for s in _GIT_READ_SUBCOMMANDS[verb]))
    return (
        f"`git {verb} {sub}`".rstrip()
        + f" is not one of the read-only subcommands of `git {verb}` ({allowed})."
    )


def _git_config_problem(args: list[str]) -> str | None:
    """Why this `git config` is a write.

    Counting positional arguments is what a literal-text rule could not do:
    `git config user.email` reads the key and `git config user.email x@y`
    writes it, and the two differ only by an argument.
    """
    positionals = _positional_args(args, _GIT_CONFIG_VALUE_FLAGS)
    if positionals and positionals[0].lower() in _GIT_CONFIG_READ_SUBCOMMANDS:
        return None
    if any(a.split("=", 1)[0] in _GIT_CONFIG_WRITE_FLAGS for a in args):
        return "`git config` with a write flag changes configuration."
    if any(a.split("=", 1)[0] in _GIT_CONFIG_READ_FLAGS for a in args):
        return None
    if len(positionals) <= 1:
        return None
    return (
        "`git config <key> <value>` writes configuration. Read it with "
        "`git config --get <key>`."
    )


def _git_ref_problem(verb: str, args: list[str]) -> str | None:
    """Why this `git branch` or `git tag` writes a ref.

    Both verbs list with no operand and create with one, so the operand count
    decides, and a value belonging to a read flag such as `--contains <commit>`
    is not an operand. `--list` makes any operand a pattern instead of a name.
    """
    write_flags = _GIT_BRANCH_WRITE_FLAGS if verb == "branch" else _GIT_TAG_WRITE_FLAGS
    list_flags = _GIT_BRANCH_LIST_FLAGS if verb == "branch" else _GIT_TAG_LIST_FLAGS
    hit = [a for a in args if a.split("=", 1)[0] in write_flags]
    if hit:
        return f"`git {verb} {hit[0]}` creates, moves or deletes a ref."
    positionals = _positional_args(args, _GIT_REF_VALUE_FLAGS)
    if positionals and not any(a.split("=", 1)[0] in list_flags for a in args):
        return (
            f"`git {verb} {positionals[0]}` with a bare name creates a ref. "
            f"List them with `git {verb} --list`."
        )
    return None


def _git_verb_problem(verb: str, args: list[str], wrapped: bool) -> str | None:
    """Why this git verb is not a read, or None when it is one."""
    unsafe = [a for a in args if a.split("=", 1)[0] in _GIT_UNSAFE_VERB_FLAGS]
    if unsafe:
        return (
            f"`git {verb} {unsafe[0]}` writes a file or runs an external program "
            "chosen by configuration, which is a write however read-only the verb is."
        )
    if verb in _GIT_READ_SUBCOMMANDS:
        return _git_subcommand_problem(verb, args)
    if verb == "config":
        return _git_config_problem(args)
    if verb in ("branch", "tag"):
        return _git_ref_problem(verb, args)
    if verb in _GIT_READ_VERBS:
        if verb == "grep" and any(a.startswith("-O") for a in args):
            return "`git grep -O` runs the pager as a command."
        return None
    if verb in _GIT_PROMPT_VERBS:
        if wrapped:
            return (
                f"`git {verb}` is allowed to reach its permission prompt, but only "
                "when it is the command being run. Behind a wrapper the prompt "
                "never fires, because permission rules match the raw command by prefix."
            )
        return None
    return (
        f"`git {verb}` is not on the read-only allowlist. Git has around 150 "
        "commands and a user alias resolves to any of them, so this guard lists "
        "what reads rather than guessing at what writes."
    )


# `download` is here because it reads GitHub and writes only files it is asked
# to fetch, which is the same thing `curl -o` does and is already allowed.
_GH_READ_VERBS = frozenset({"view", "list", "diff", "checks", "status", "download"})
_GH_READ_COMMANDS = frozenset({"status", "version", "search", "help"})


def _gh_problem(args: list[str]) -> str | None:
    """Why this gh invocation is not a read, or None when it is one."""
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return None
    first = positionals[0].lower()
    if first == "api":
        return (
            "`gh api` reaches any GitHub REST or GraphQL endpoint, read or write, "
            "so the verb allowlist cannot see what it does."
        )
    if first in _GH_READ_COMMANDS:
        return None
    if len(positionals) == 1:
        return None
    verb = positionals[1].lower()
    if verb in _GH_READ_VERBS:
        return None
    return (
        f"`gh {first} {verb}` is not one of the read-only gh verbs "
        f"({', '.join(sorted(_GH_READ_VERBS))})."
    )


# In interpreter source a git call is not a shell word: `os.system('git push')`
# splits into os.system(git and push). The verb is read with a regex there
# instead, which over-matches on a program that merely handles the text -- an
# acceptable trade for a one line -c payload.
_GIT_IN_SOURCE_RE = re.compile(r"\bgit(?:\.exe)?\s+(?:-[^\s]+\s+)*([a-z][\w-]*)",
                               re.IGNORECASE)
_GH_IN_SOURCE_RE = re.compile(r"\bgh(?:\.exe)?\s+([a-z][\w-]*)(?:\s+([a-z][\w-]*))?",
                              re.IGNORECASE)


def _find_exec_payloads(text: str) -> list[str]:
    """The command each `find -exec` in `text` would run.

    find's own manual calls -exec/-execdir/-ok/-okdir "Execute command", and it
    runs the binary directly rather than through a shell, so nothing in the
    permission engine or in the executor checks above ever sees it. Verified on
    this machine: `find . -maxdepth 0 -exec echo X \\;` printed X.
    """
    payloads = []
    for _, segment in _split_segments(text):
        words = _shell_words(segment)
        for index, word in enumerate(words):
            if word in ("-exec", "-execdir", "-ok", "-okdir"):
                tail = []
                for follow in words[index + 1:]:
                    if follow in (";", "\\;", "+"):
                        break
                    tail.append(follow)
                if tail:
                    payloads.append(" ".join(tail))
    return payloads


def _scannable_texts(command: str) -> list[tuple[str, bool, str]]:
    """(text, routed, kind) for every place in `command` a command can run.

    routed means the permission engine cannot see it, which is what decides
    whether a verb that is only allowed to reach a prompt may run at all.
    """
    scannable = command
    for start, end in _heredoc_data_spans(command):
        scannable = scannable[:start] + (" " * (end - start)) + scannable[end:]

    texts = [(scannable, False, "shell")]
    for payload, kind in _executor_payloads(scannable):
        texts.append((payload, True, kind))
    for payload in _find_exec_payloads(scannable):
        texts.append((payload, True, "shell"))
    return texts


def check_git_gh_verbs(command: str) -> str | None:
    """Block any git or gh invocation that is not a read.

    This is the requirement stated as a property rather than as a list: a git
    command that writes the index, working tree, refs, a remote, config, the
    stash, the object store or the credential store must be unable to run, so
    it is handed to the human instead. Read-only git keeps working silently.
    """
    lowered = command.lower()
    if "git" not in lowered and "gh" not in lowered:
        return None

    for text, routed, kind in _scannable_texts(command):
        if kind == "interpreter":
            problem = _source_verb_problem(text)
            if problem:
                return problem
            continue
        for separator, segment in _split_segments(text):
            words = _command_words(segment)
            if not words:
                continue
            name = _binary_name(words[0])
            wrapped = routed or bool(separator.strip("\n")) or _is_wrapped(segment)
            if name == "git":
                flag_problem, verb_index = _git_global_flag_problem(words[1:])
                if flag_problem:
                    return _refuse(segment, flag_problem)
                verb_args = words[1 + verb_index:]
                if not verb_args:
                    continue
                problem = _git_verb_problem(verb_args[0].lower(), verb_args[1:], wrapped)
                if problem:
                    return _refuse(segment, problem)
            elif name == "gh":
                problem = _gh_problem(words[1:])
                if problem:
                    return _refuse(segment, problem)
    return None


def _source_verb_problem(source: str) -> str | None:
    """The same verb gate, applied to interpreter source rather than words.

    Only the verb is read, never its arguments: shell word rules do not apply
    here, so `git branch` in source cannot be told from `git branch newname`.
    A verb that reads with no arguments is therefore allowed through, which is
    the direction that keeps a program merely handling the text from being
    refused.
    """
    for match in _GIT_IN_SOURCE_RE.finditer(source):
        verb = match.group(1).lower()
        if verb in _GIT_READ_VERBS or verb in _GIT_READ_SUBCOMMANDS:
            continue
        problem = _git_verb_problem(verb, [], True)
        if problem:
            return _refuse(match.group(0), problem)
    for match in _GH_IN_SOURCE_RE.finditer(source):
        words = [w for w in match.groups() if w]
        if words[0].lower() in _GH_READ_COMMANDS:
            continue
        problem = _gh_problem(words)
        if problem:
            return _refuse(match.group(0), problem)
    return None


# Two of them, because a feeder appends one argument or many and the two are
# judged differently: `git config user.email` reads and `git config user.email
# x@y` writes. Standing in for "at least one more" rather than "exactly one"
# keeps the verdict on the writing side of that pair.
_FED_ARG = "\x00fed\x00"
_FED_ARGS = [_FED_ARG, _FED_ARG]

_INTERPRETER_NAME_RE = re.compile(
    r"^(?:python[\d.]*|perl|ruby|node|deno|bun|php|rscript)$", re.IGNORECASE)


def _fed_git_problem(words: list[str]) -> str | None:
    """Why this git command is not a read once the feeder has appended to it.

    The verb gate is re-run with unknown arguments on the end rather than
    reimplemented, so `xargs git log` stays allowed (appending paths to a read
    is still a read) while `xargs git branch` does not (appending a name to it
    creates a ref).
    """
    flag_problem, verb_index = _git_global_flag_problem(words[1:])
    if flag_problem:
        return flag_problem
    verb_args = words[1 + verb_index:]
    if not verb_args:
        return (
            "`git` here has no verb: an argument feeder supplies it at runtime "
            "from stdin or a file. The verb is the whole of what separates a "
            "read from a push, and nothing that reads the command can see it."
        )
    return _git_verb_problem(verb_args[0].lower(), verb_args[1:] + _FED_ARGS, True)


def check_argument_feeder(command: str) -> str | None:
    """Block a binary whose arguments arrive from somewhere unreadable.

    POSIX has xargs constructing "a command line consisting of the utility and
    argument operands specified followed by as many arguments read in sequence
    from standard input". Reading the words after `git` in the static text
    found an empty list there and let the command through.
    """
    lowered = command.lower()
    if "xargs" not in lowered and "parallel" not in lowered:
        return None

    for text, _routed, kind in _scannable_texts(command):
        if kind == "interpreter":
            continue
        for _separator, segment in _split_segments(text):
            if not _is_fed(segment):
                continue
            words = _command_words(segment)
            if not words:
                continue
            name = _binary_name(words[0])
            if name == "git":
                problem = _fed_git_problem(words)
                if problem:
                    return _refuse(segment, problem)
            elif name == "gh":
                problem = _gh_problem(words[1:] + _FED_ARGS)
                if problem:
                    return _refuse(segment, problem)
            elif name in _SHELL_BINARIES or _INTERPRETER_NAME_RE.match(name):
                return _refuse(segment, (
                    f"`{name}` here is handed its script by an argument feeder, so "
                    "what runs is chosen at runtime. No permission rule can match it "
                    "either, because those match the raw command by prefix."
                ))
    return None


def _refuse(what: str, why: str) -> str:
    return (
        f"BLOCKED: {why} Found in: {what.strip()[:120]!r}. "
        "Read-only git and gh run with no prompt; a write is handed to the human "
        "instead. Put the command on the clipboard for them, or ask them to run it."
    )


# ---------------------------------------------------------------------------
# The guard's own files, and every .env.
#
# A guard that the thing it guards can overwrite is not a guard. The Edit and
# Write tool rules cover those two tools and nothing else, so `cp payload.py
# scripts/bash-guard.py` and `echo x > scripts/bash-guard.py` reached the same
# paths through Bash with no prompt at all.
# ---------------------------------------------------------------------------
_BOOST_SCRIPTS_PREFIX = _BOOST_HOME.replace("\\", "/").rstrip("/").lower() + "/scripts/"

_PROTECTED_PATH_RES = (
    # The guard itself, wherever it has been installed or copied to.
    re.compile(r"(?:^|/)bash-guard(?:\.proposed)?\.py$"),
    # Claude Code's own control files: what runs, and what is permitted.
    # browser-targets belongs here because _load_browser_targets reads it to
    # decide which hosts curl and browser automation may reach, so a Bash write
    # to it widens this guard's own allowlist. redacted-terms is the same
    # shape one layer out: emptying it retires the leak check that reads it.
    re.compile(r"(?:^|/)\.claude/(?:settings[^/]*\.json$"
               r"|browser-targets[^/]*\.json$|redacted-terms[^/]*\.json$"
               r"|hooks(?:/|$)|agents(?:/|$))"),
    # The research and verifier gates.
    re.compile(r"(?:^|/)clean-rag/hooks(?:/|$)"),
    # A relative path has no root to check, so scripts/ and its tests are
    # treated as this project's until proven otherwise. Refusing more is the
    # safe direction for a path whose base is unknown.
    re.compile(r"^\.?/?scripts(?:/|$)"),
    # The directory itself, because moving or deleting it takes every file
    # above with it: `mv .claude /tmp/backup` left no settings.json, no hooks
    # and no agents behind, and matched none of the patterns above.
    re.compile(r"(?:^|/)\.claude/?$"),
)

# A shell word is not the path it names. Two expansions run before the command
# does, and both reach a protected file through a spelling that contains none
# of the literals above. Verified in this project's own Git Bash, on a scratch
# copy of the file:
#
#   echo x > .claude/browser-target*.local.json    overwrote the real file
#   rm .claude/browser-target{s,q}.local.json      deleted it
#
# _ENV_FILE_RE already reads a metacharacter as part of the path it protects.
# The patterns above were left matching literals, so the same word that reaches
# a .env was refused and the one that reaches the guard's own config was not.
_GLOB_META_RE = re.compile(r"[*?\[]")

# Expansions per word. A brace expression is finite but multiplies, and the
# only thing on the other side of this cap is a word nobody types.
_BRACE_LIMIT = 64

_STAR = ("star",)       # a run of any length, never crossing a /
_ANY = ("any",)         # a run of any length, / included
_ONE = ("one",)         # exactly one character, never a /


def _brace_end(word: str, start: int) -> int | None:
    """Index of the `}` closing the `{` at start, or None if it never closes."""
    depth = 0
    for index in range(start, len(word)):
        if word[index] == "{":
            depth += 1
        elif word[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _brace_alternatives(body: str) -> list[str] | None:
    """What `{...}` stands for, or None when it stands for itself.

    bash expands a brace only when it holds a comma or a range, so `a{s}b` is
    the literal text `a{s}b` and `a{s,q}b` is two words. Both confirmed by
    running them.
    """
    parts, depth, current = [], 0, ""
    for char in body:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    parts.append(current)
    if len(parts) > 1:
        return parts

    match = re.fullmatch(r"(-?\d+)\.\.(-?\d+)|([a-z])\.\.([a-z])", body)
    if not match:
        return None
    if match.group(1) is not None:
        low, high = int(match.group(1)), int(match.group(2))
        step = 1 if high >= low else -1
        values = range(low, high + step, step)
        return [str(v) for v in values][:_BRACE_LIMIT]
    low, high = ord(match.group(3)), ord(match.group(4))
    step = 1 if high >= low else -1
    return [chr(c) for c in range(low, high + step, step)][:_BRACE_LIMIT]


def _brace_expand(word: str) -> list[str]:
    """Every word bash would produce from this one, the original included."""
    if "{" not in word:
        return [word]
    pending, done = [word], []
    while pending and len(pending) + len(done) < _BRACE_LIMIT:
        current = pending.pop()
        expanded = False
        for start, char in enumerate(current):
            if char != "{":
                continue
            end = _brace_end(current, start)
            if end is None:
                break
            alternatives = _brace_alternatives(current[start + 1:end])
            if alternatives is None:
                continue
            pending.extend(
                current[:start] + part + current[end + 1:] for part in alternatives)
            expanded = True
            break
        if not expanded:
            done.append(current)
    return done + pending


def _glob_tokens(pattern: str, crossing: bool = False) -> tuple:
    """A glob as tokens this module can compare with another glob.

    A bracket becomes "one character" rather than the set it names. That
    over-matches, which for a guard is the direction that refuses rather than
    the one that lets a write through.
    """
    tokens, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if crossing and pattern.startswith("**", index):
                tokens.append(_ANY)
                index += 2
                continue
            tokens.append(_STAR)
        elif char == "?":
            tokens.append(_ONE)
        elif char == "[":
            # A `]` in the first position is a member of the set, not its end,
            # and so is the one after a negating `!` or `^`.
            first = index + 1
            if pattern[first:first + 1] in ("!", "^"):
                first += 1
            if pattern[first:first + 1] == "]":
                first += 1
            end = pattern.find("]", first)
            if end == -1:
                tokens.append(("lit", char))
            else:
                tokens.append(_ONE)
                index = end + 1
                continue
        else:
            tokens.append(("lit", char))
        index += 1
    return tuple(tokens)


def _globs_overlap(left: tuple, right: tuple) -> bool:
    """Whether any one path matches both patterns.

    The literal check cannot answer this, because a metacharacter stands where
    a letter of the protected name should be: `browser-target*.local.json`
    holds no `browser-targets` substring and expands onto it anyway. Comparing
    the two patterns answers it without touching the filesystem, which keeps
    the verdict the same on every machine and in every working tree.
    """
    memo: dict[tuple[int, int], bool] = {}

    def walk(i: int, j: int) -> bool:
        key = (i, j)
        if key in memo:
            return memo[key]
        memo[key] = result = decide(i, j)
        return result

    def decide(i: int, j: int) -> bool:
        if i == len(left):
            return all(token in (_STAR, _ANY) for token in right[j:])
        if j == len(right):
            return all(token in (_STAR, _ANY) for token in left[i:])
        head, other = left[i], right[j]
        head_runs, other_runs = head in (_STAR, _ANY), other in (_STAR, _ANY)
        if head_runs:
            if walk(i + 1, j):
                return True
            if other_runs or other == _ONE:
                return walk(i, j + 1)
            return (other[1] != "/" or head == _ANY) and walk(i, j + 1)
        if other_runs:
            if walk(i, j + 1):
                return True
            if head == _ONE:
                return walk(i + 1, j)
            return (head[1] != "/" or other == _ANY) and walk(i + 1, j)
        if head == _ONE and other == _ONE:
            return walk(i + 1, j + 1)
        if head == _ONE:
            return other[1] != "/" and walk(i + 1, j + 1)
        if other == _ONE:
            return head[1] != "/" and walk(i + 1, j + 1)
        return head[1] == other[1] and walk(i + 1, j + 1)

    return walk(0, 0)


def _at_any_depth(tail: str) -> tuple[str, str]:
    return tail, "**/" + tail


# The same protection as _PROTECTED_PATH_RES, written as globs so a word that
# is itself a glob can be compared with it. Only a word carrying a
# metacharacter is matched here; a literal path still goes through the regexes
# above, which stay the authority. test_bash_guard_expanded_paths.py fails if
# the two ever disagree about a literal path.
#
# Bare `.claude` is deliberately absent. `*` is treated as able to match a
# leading dot, which bash does not do without dotglob, so a witness that is one
# name beginning with a dot would read `rm build/*` as reaching `.claude`. The
# literal regex above still refuses `mv .claude /tmp`.
#
# The guard's own file is named at two anchors rather than at any depth, and
# the difference is the whole usability of this table. `**/bash-guard.py`
# overlaps `src/*.py`, `docs/*.py` and every other `<dir>/*.py` on the strength
# of a file that is not there, because the crossing `**` absorbs the word's
# directory and the word's `*` can spell `bash-guard`. Python is this repo's
# main language, so that refused ordinary work everywhere. gitignore(5) draws
# the same line for the same reason: "If there is a separator at the beginning
# or middle (or both) of the pattern, then the pattern is relative to the
# directory level ... Otherwise the pattern may also match at any level".
# Every copy in this tree sits under scripts/ or clean-rag/hooks/, so the two
# anchors below lose no file that exists. The bare name stays because a
# relative word has no directory to judge: with cwd unknown, `rm *.py` can be
# the one inside scripts/, the same way `rm bash-guard.py` can.
#
# What that gives up: a glob aimed at a copy of the guard somewhere other than
# scripts/, clean-rag/hooks/ or .claude/hooks/, such as `rm vendor/bash-guar*.py`.
# The literal regex above still refuses the spelled-out path.
_PROTECTED_GLOBS = (
    "bash-guard.py", "**/scripts/bash-guard.py",
    "bash-guard.proposed.py", "**/scripts/bash-guard.proposed.py",
    *_at_any_depth(".claude/settings*.json"),
    *_at_any_depth(".claude/browser-targets*.json"),
    *_at_any_depth(".claude/redacted-terms*.json"),
    *_at_any_depth(".claude/hooks"),
    *_at_any_depth(".claude/hooks/**"),
    *_at_any_depth(".claude/agents"),
    *_at_any_depth(".claude/agents/**"),
    *_at_any_depth("clean-rag/hooks"),
    *_at_any_depth("clean-rag/hooks/**"),
    # scripts/ is anchored at the start of a relative path, the same way its
    # regex is, so `rm build/*` is not read as reaching some other scripts dir.
    "scripts", "scripts/**", "./scripts", "./scripts/**",
    "/scripts", "/scripts/**",
    _BOOST_SCRIPTS_PREFIX + "**",
)

_PROTECTED_GLOB_TOKENS = tuple(
    _glob_tokens(pattern, crossing=True) for pattern in _PROTECTED_GLOBS)

# `.env`, `.env.local`, and the glob pathspecs that reach the same bytes:
# `git log -p -- "*.env"` prints the content of every .env in the history.
#
# The line sits at the dot-segment, not at the substring. A token is an env
# file when a path component is exactly `.env` or `.env.<something>`, where the
# component may begin with a glob metacharacter and may end with one. So
# `*.env` and `**/.env` match, and `src/environment.ts`, `docs/dotenv.md`,
# `--env-file` and `process.env` do not: in each of those the letters sit
# inside a longer name rather than forming the component.
#
# `.env.example` matches and is meant to. It is a committed template, but the
# separation between a template and a real secret is a convention rather than a
# rule, and this refusal costs one Read tool call to work around.
_ENV_FILE_RE = re.compile(r"(?:^|[/*?\]])\.env(?:\.[^/*?]*)?[*?]*$")

# Flags whose value is a name pattern rather than a file being opened. The
# split is by what the flag makes the command do, measured rather than assumed:
# `rg --glob .env SECRET` and `grep -r --include=.env SECRET` both printed the
# secret, because an inclusion filter selects the files the tool then reads.
# Only `find`'s predicates locate without reading, and `find -name .env`
# printed a path where `find -name .env -exec cat {} \;` printed the value.
#
# So an inclusion filter is deliberately absent from both sets below and reads
# as a filename. rg's negated form (`--glob !.env`) excludes rather than
# selects, and falls out for free: _ENV_FILE_RE does not match a `!` prefix.
_LOCATE_FLAGS = frozenset({"-name", "-iname", "-wholename", "-path", "-ipath"})

# Exclusion narrows what gets read, so naming .env here protects it.
_EXCLUSION_FLAGS = frozenset({"--exclude", "--exclude-dir"})

# Inclusion filters select the files the tool opens. Their value is a filename
# and never the search pattern, which matters because the pattern is what
# skip_operands below exists to drop.
_INCLUSION_FLAGS = frozenset({"--include", "--glob", "-g", "--iglob"})

# find actions that consume a match instead of printing its path. With one of
# these present the locate exemption above no longer holds.
_FIND_ACTION_FLAGS = frozenset({
    "-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint",
})

# Commands that modify every file they are given. Redirections are handled
# separately, so this only has to cover the ones that write without one.
_WRITER_COMMANDS = frozenset({
    "tee", "rm", "del", "erase", "unlink", "rmdir", "shred", "touch",
    "truncate", "chmod", "chown", "chgrp", "attrib", "icacls", "takeown",
    "patch", "gzip", "gunzip", "bzip2", "xz", "zip", "unzip", "tar", "7z",
    "set-content", "out-file", "add-content", "clear-content", "copy-item",
    "move-item", "remove-item", "new-item", "rename-item", "set-itemproperty",
})

# Commands that read their first operands and write only the last one.
# Measured, not assumed: treating every operand as written refused
# `cp settings.json settings.json.bak`, an ordinary backup, in the transcripts.
# A copy leaves the protected file where it was, and its content is readable
# anyway, so refusing one buys nothing the read rules do not already decide.
_DESTINATION_ONLY_COMMANDS = frozenset({
    "cp", "copy", "install", "ln", "mklink", "rsync",
})

# Commands that empty the source path as well as filling the destination. The
# source is a write, and the same outcome as the `rm` these already refuse:
# `rm scripts/bash-guard.py` was blocked while `mv scripts/bash-guard.py
# /tmp/backup.py` left the same empty path behind and was not.
_RELOCATING_COMMANDS = frozenset({"mv", "move", "rename", "ren"})
_REMOVE_SOURCE_FLAGS = frozenset({"--remove-source-files", "--remove-sent-files"})
_TARGET_DIRECTORY_FLAGS = ("-t", "--target-directory")

# Stream editors write only when told to. `sed -n '340,400p' <file>` is a pager,
# and it accounted for 86 of the regressions the first version of this measured.
_IN_PLACE_COMMANDS = frozenset({"sed", "perl", "ruby"})
_IN_PLACE_FLAG_RE = re.compile(r"^(?:-i|--in-place)")

# Where a sed command can start: the beginning of the script, or after ; or a
# newline or {, with an optional address in front of it. The anchor is load
# bearing and was found missing by measurement rather than by reading. Without
# it the `s` matcher below found `s(serialise(data, indent, crlf))/PROJ.write`
# inside an ordinary replacement string, because sed's `s` takes any delimiter
# and `s(` looks like one, and it refused two real transcript commands.
# Nothing in here captures, so \1 in the patterns below still means the
# delimiter captured right after the `s`.
_SED_ADDRESS = r"(?:^|[;\n{])[ \t]*(?:[0-9,$~+]|/(?:[^/\\]|\\.)*/|![ \t]*)*[ \t]*"
_SED_SUBSTITUTION = r"s(.)(?:(?!\1).|\\.)*\1(?:(?!\1).|\\.)*\1[a-z]*"

# A sed script that runs a shell command. Both forms verified on this machine:
# `sed '1e echo X' f` and `sed 's/.*/&/e' f` each printed X. GNU sed documents
# `e [command]` and the `e` modifier on `s///` as executing through /bin/sh.
_SED_EXEC_COMMAND_RE = re.compile(_SED_ADDRESS + r"e(?:[ \t]|$)")
_SED_EXEC_FLAG_RE = re.compile(_SED_ADDRESS + _SED_SUBSTITUTION + "e")

# `w <file>` and the `w` flag on `s///` write a file named in the script rather
# than on the command line, so an in place flag is not the only way sed writes.
_SED_WRITE_RE = re.compile(
    _SED_ADDRESS + r"(?:[wW][ \t]|" + _SED_SUBSTITUTION + r"[wW])")


def _target_directories(words: list[str]) -> list[str]:
    """Destinations named by a flag rather than by the last operand."""
    directories = []
    for index, word in enumerate(words[1:], start=1):
        if word.startswith("--target-directory="):
            directories.append(word.split("=", 1)[1])
        elif word in _TARGET_DIRECTORY_FLAGS and index + 1 < len(words):
            directories.append(words[index + 1])
    return directories


def _written_operands(words: list[str]) -> list[str]:
    """The operands this command writes, which is not always all of them."""
    name = _binary_name(words[0])
    flags = [w for w in words[1:] if w.startswith("-")]
    operands = [w for w in words[1:] if not w.startswith("-")]

    if name == "dd":
        return [w for w in operands if w.lower().startswith("of=")]

    if name in _IN_PLACE_COMMANDS:
        in_place = any(_IN_PLACE_FLAG_RE.match(f) for f in flags)
        if name == "sed" and not in_place and not _SED_WRITE_RE.search(_sed_script(words[1:])):
            return []
        if not in_place and name != "sed":
            return []
        return operands

    if name in _RELOCATING_COMMANDS or (
            name == "rsync" and any(f in _REMOVE_SOURCE_FLAGS for f in flags)):
        return operands + _target_directories(words)

    if name in _DESTINATION_ONLY_COMMANDS:
        return operands[-1:] + _target_directories(words)

    return operands if name in _WRITER_COMMANDS else []


def _path_candidates(word: str) -> list[str]:
    """The paths a single word could name, normalised for comparison.

    A word is not always a bare path. `dd of=<path>` and `--output=<path>` put
    the path after an `=`; git puts it after a `:`, where `git show HEAD:.env`
    prints the real bytes of any .env the history ever held. Reading only the
    whole word missed all three. A brace expression is one word here and
    several by the time the command runs, so each of those is a path too.
    """
    normalized = word.strip("\"'").replace("\\", "/").lower()
    if not normalized:
        return []
    candidates = []
    for spelling in _brace_expand(normalized):
        candidates.append(spelling)
        if "=" in spelling:
            candidates.append(spelling.split("=", 1)[1])
        # git's <ref>:<path>. A single character before the colon is a Windows
        # drive letter instead, and splitting those turned every C:/... path
        # into a rooted /... one that matched the relative `scripts/` pattern.
        head, colon, tail = spelling.partition(":")
        if colon and tail and len(head) != 1:
            candidates.append(tail)
    return [c for c in candidates if c]


def _matches_protected_literal(path: str) -> bool:
    return path.startswith(_BOOST_SCRIPTS_PREFIX) or any(
        pattern.search(path) for pattern in _PROTECTED_PATH_RES)


def _expansion_reaches_protected(path: str) -> bool:
    """Whether a path that still has to expand could land on a protected file.

    A component that is nothing but wildcards names no file in particular, so
    every protected path is technically within its reach and `rm logs/*` would
    be refused on the strength of a file that is not there. Such a component is
    read the other way round: it is protected when the directory holding it is,
    which is what makes `rm .claude/*` a refusal and `rm logs/*` not.
    """
    components = path.split("/")
    for index, component in enumerate(components):
        tokens = _glob_tokens(component)
        if tokens and all(token in (_STAR, _ONE) for token in tokens):
            prefix = "/".join(components[:index])
            return bool(prefix) and _matches_protected_literal(prefix)
    tokens = _glob_tokens(path)
    return any(_globs_overlap(tokens, witness) for witness in _PROTECTED_GLOB_TOKENS)


def _is_protected_path(word: str) -> bool:
    for path in _path_candidates(word):
        if _matches_protected_literal(path):
            return True
        if _GLOB_META_RE.search(path) and _expansion_reaches_protected(path):
            return True
    return False


def _is_env_file(word: str) -> bool:
    return any(_ENV_FILE_RE.search(path) for path in _path_candidates(word))


# Commands whose first operand is a pattern or a script rather than a file.
# `grep -i "\.env"` searches stdin for the text and opens nothing, and that
# spelling turned up in the transcripts inside an audit for committed secrets.
# The file operands after it are still read, so `grep API .env` stays refused.
_PATTERN_FIRST_COMMANDS = frozenset({
    "grep", "egrep", "fgrep", "rg", "ag", "ack", "findstr", "sed", "awk",
})


def _names_no_file(word: str, previous: str, locating: bool) -> bool:
    """True when this word names a pattern the command will not open.

    `--exclude=.env` arrives as one word, so the joined spelling is checked as
    well as the separated one. Refusing either would refuse a command whose
    whole effect is to leave the file alone.
    """
    if previous in _EXCLUSION_FLAGS:
        return True
    if locating and previous in _LOCATE_FLAGS:
        return True
    return any(word.startswith(flag + "=") for flag in _EXCLUSION_FLAGS)


def _env_read_problem(words: list[str], skip_operands: int = 0) -> str | None:
    """The refusal this word list earns for naming an .env file, or None.

    skip_operands drops that many leading non-flag words, which is how the
    command name and a search pattern are kept from reading as filenames.
    """
    # A locate predicate only stays exempt while nothing consumes the match.
    locating = not any(word in _FIND_ACTION_FLAGS for word in words)
    previous = ""
    for word in words:
        if _names_no_file(word, previous, locating):
            previous = word
            continue
        # An inclusion filter's value is a filename, never the search pattern.
        is_pattern = (skip_operands and not word.startswith("-")
                      and previous not in _INCLUSION_FLAGS)
        if is_pattern:
            skip_operands -= 1
            previous = word
            continue
        if _is_env_file(word):
            return (
                "BLOCKED: an .env file holds this project's secrets, and Bash reaches "
                f"it by any route the Read tool rule does not cover. Found: {word!r}. "
                "If you need a specific key, ask the human for that one value."
            )
        previous = word
    return None


def _operands_to_skip(segment: str) -> int:
    """How many leading operands of a segment are not filenames.

    Always the command name, plus the pattern or script for a command that
    takes one first.
    """
    words = _command_words(segment)
    if not words:
        return 0
    return 2 if _binary_name(words[0]) in _PATTERN_FIRST_COMMANDS else 1


_REDIRECT_WORDS = frozenset({">", ">>", ">|", ">&", "&>", "&>>"})
_SOURCE_PATH_RE = re.compile(r"[\w.:/\\@+-]+")

# A parameter expansion, read against bash's own grammar rather than against a
# list of spellings seen so far, because the list is what keeps coming up one
# short: `${arr[0]}` and `${UNSET:-scripts/bash-guard.py}` both reached this
# file after nine other spellings of it had been closed one at a time.
_PARAM_NAME_RE = re.compile(r"[A-Za-z_]\w*")

# The operators that put their own word in the output: ${name:-word},
# ${name-word}, ${name:=word}, ${name=word}, ${name:+word}, ${name+word}. That
# word is a path the command writes, spelled entirely inside the braces.
# GNU Bash Reference Manual, Shell Parameter Expansion.
_DEFAULT_WORD_RE = re.compile(r"^:?[-=+](.*)$", re.DOTALL)
# ${name/pattern/string} and ${name//pattern/string} put `string` there too.
_REPLACEMENT_RE = re.compile(r"^/{1,2}[^/]*/(.*)$", re.DOTALL)

# What an expansion only the environment can resolve stands for. It holds the
# place so the readable rest of a word survives: `${TMPDIR}/out.txt` still
# names out.txt. A word that reduces to nothing but this is refused, and so is
# one whose readable rest names a protected file for some value of the
# unreadable part, which _marker_reaches_protected below decides.
_UNREADABLE = "\x00var\x00"

# One word can reach the shell as several strings, the way a brace expression
# can, and both are capped for the same reason: past the cap is a word nobody
# types. The depth cap bounds `${a:-${b:-${c}}}`.
_SPELLING_LIMIT = 24
_EXPANSION_DEPTH = 4


def _split_expansion(text: str, index: int) -> tuple[str | None, str, int] | None:
    """(parameter name, the rest of the expansion, the index after it).

    The name is None where bash's grammar allows something other than a plain
    parameter, `${#x}` and `${!x}` and the positionals, because none of those
    has an assignment in the command to read. The result is None when `index`
    starts no expansion at all.
    """
    if not text.startswith("$", index):
        return None
    if not text.startswith("${", index):
        match = _PARAM_NAME_RE.match(text, index + 1)
        return (match.group(0), "", match.end()) if match else None
    depth, cursor, length = 1, index + 2, len(text)
    while cursor < length and depth:
        if text.startswith("${", cursor):
            depth += 1
            cursor += 2
            continue
        if text[cursor] == "}":
            depth -= 1
        cursor += 1
    if depth:
        return None
    body = text[index + 2:cursor - 1]
    match = _PARAM_NAME_RE.match(body)
    if not match:
        return None, body, cursor
    rest = body[match.end():]
    if rest.startswith("["):
        # A subscript selects one element of a name this guard binds whole, so
        # the reference is judged against every element. Refusing on one the
        # command did not name is the direction a guard can afford.
        close = rest.find("]")
        if close != -1:
            rest = rest[close + 1:]
    return match.group(0), rest, cursor


def _expansion_options(name: str | None, remainder: str,
                       bindings: dict[str, list[str]], depth: int) -> list[str]:
    """What this one expansion can put in the output.

    Both halves of `${name:-word}` are kept, because which one bash picks
    depends on a value that is not in the command.
    """
    values = bindings.get(name) if name else None
    options = list(values) if values else [_UNREADABLE]
    match = _DEFAULT_WORD_RE.match(remainder) or _REPLACEMENT_RE.match(remainder)
    if match and match.group(1):
        options.extend(_expansion_spellings(match.group(1), bindings, depth + 1))
    return options


def _expansion_spellings(word: str, bindings: dict[str, list[str]],
                         depth: int = 0) -> list[str]:
    """Every string this word could expand to, with unresolvable parts marked.

    A word is judged as what it becomes, not as the text it is:
    `rm ${UNSET:-scripts/bash-guard.py}` deletes this file in real bash while
    naming no protected path any check could match.
    """
    if "$" not in word or depth > _EXPANSION_DEPTH:
        return [word]
    spellings, literal = [""], []
    cursor, length = 0, len(word)
    while cursor < length:
        parsed = _split_expansion(word, cursor)
        if parsed is None:
            literal.append(word[cursor])
            cursor += 1
            continue
        name, remainder, cursor = parsed
        prefix = "".join(literal)
        literal = []
        options = _expansion_options(name, remainder, bindings, depth)
        spellings = [left + prefix + option
                     for left in spellings
                     for option in options][:_SPELLING_LIMIT]
    tail = "".join(literal)
    return [left + tail for left in spellings]


# What an unknown expansion is read as standing for while the rest of the word
# is literal. Empty is bash's own answer for an unset name, and the expansion
# ShellCheck SC2115 exists for: `rm -rf "$x/home"` reaches /home whenever x is
# unset. The two directory names are the ones whose named children are
# protected, so the literal half of the word still has to spell the name.
#
# `scripts` is deliberately absent even though it is protected the same way.
# It protects everything beneath it, so reading an unknown prefix as `scripts`
# refuses `${TMPDIR}/out.txt` and every other ordinary path built on an
# environment variable, which is the shape this guard measured as routine.
# What that gives up is named in test_bash_guard_marker_prefix_bypass.py.
_MARKER_COMPLETIONS = ("", ".claude", "clean-rag")


def _marker_reaches_protected(spelling: str) -> str | None:
    """The protected path a half readable word can land on, or None.

    The unknown half of the word supplies the directories and the literal half
    supplies the name, which is how `${DIR}/hooks` reaches `.claude/hooks`.
    `read -r DIR <<< ".claude"` binds DIR inside the same command without
    writing an assignment this guard can see, and `printf -v DIR .claude` does
    it again, so a word can carry a name nothing in the command declares.

    A word whose literal half names nothing protected is allowed however the
    unknown half expands. That is what keeps `${TMPDIR}/out.txt` running, and
    it is the whole reason the completions above are a short list rather than
    "any text at all".
    """
    if _UNREADABLE not in spelling:
        return None
    path = spelling.replace("\\", "/")
    before = path.split(_UNREADABLE, 1)[0]
    holding = before.rsplit("/", 1)[0] if "/" in before else ""
    # An unknown part inside a protected directory is judged the way a wildcard
    # component there already is, by what holds it. `rm .claude/*` is refused.
    if holding and _is_protected_path(holding):
        return holding
    tail = path.rsplit(_UNREADABLE, 1)[1].lstrip("/")
    if not tail:
        return None
    for completion in _MARKER_COMPLETIONS:
        landing = f"{completion}/{tail}" if completion else tail
        if _is_protected_path(landing):
            return landing
    return None


def _resolve_variables(segment: str, bindings: dict[str, list[str]]) -> str:
    """`segment` with every reference to a variable assigned earlier replaced.

    Without this the path checks read `$F` and learn nothing, so
    `F=scripts/bash-guard.py; rm $F` reached the guard's own file while all
    eight literal spellings of it were refused. check_env_var_expansion steers
    toward that exact idiom ("variables you assign earlier in the same command
    are fine to reference"), which makes reading it the ergonomic half's debt.

    An unknown name is left as written. An environment variable's value is not
    in the command, so nothing here can resolve it, and a guessed value is
    worse than a word that stays visibly unreadable. A loop name stands for
    several values at once and is left alone here for the same reason; the
    write target check reads all of them. So is an expansion carrying a word of
    its own, `${name:-path}`, which can reach the shell as either half.

    Single quotes suppress expansion in the shell, so they suppress it here.
    """
    out: list[str] = []
    index, length, in_double = 0, len(segment), False
    while index < length:
        char = segment[index]
        if char == '"':
            in_double = not in_double
        elif char == "'" and not in_double:
            end = segment.find("'", index + 1)
            if end == -1:
                out.append(segment[index:])
                break
            out.append(segment[index:end + 1])
            index = end + 1
            continue
        else:
            parsed = _split_expansion(segment, index)
            if parsed:
                name, remainder, end = parsed
                values = bindings.get(name, ()) if name and not remainder else ()
                out.append(values[0] if len(values) == 1 else segment[index:end])
                index = end
                continue
        out.append(char)
        index += 1
    return "".join(out)


# The array assignments, all of which bind a name whose expansion is a path:
# `arr=(a b)`, `arr+=(c)`, `declare -A m=([k]=v)` and the element form
# `arr[0]=path`. GNU Bash Reference Manual, Arrays.
_ARRAY_ASSIGNMENT_RE = re.compile(r"(?:^|[\s;&|(])([A-Za-z_]\w*)(?:\[[^]]*\])?\+?=\(")
_ELEMENT_ASSIGNMENT_RE = re.compile(r"^([A-Za-z_]\w*)\[[^]]*\]\+?=(.*)$", re.DOTALL)
_KEYED_VALUE_RE = re.compile(r"^\[[^]]*\]\+?=(.*)$", re.DOTALL)


def _record_assignments(segment: str, bindings: dict[str, list[str]]) -> None:
    """Add this segment's bindings to `bindings`.

    Every word is read rather than the leading ones only, because `export
    F=path` puts the assignment behind a command word and binds it just the
    same for everything that follows.

    A `for` name binds to the whole list it iterates, which is why a value is
    a list here. `for f in logs/*.log; do rm $f; done` names its own paths, so
    refusing it for being unreadable would refuse an ordinary loop.
    """
    words = _shell_words(segment)
    for index, word in enumerate(words):
        match = _ASSIGNMENT_WORD_RE.match(word)
        if match:
            # An empty value names no path, and `arr=(a b)` reaches here as a
            # bare `arr=` once _split_segments has cut the body off at the `(`.
            # Binding it would erase what _record_array_assignments read.
            if match.group(2):
                bindings[match.group(1)] = [match.group(2)]
            continue
        element = _ELEMENT_ASSIGNMENT_RE.match(word)
        if element:
            bindings.setdefault(element.group(1), []).append(element.group(2))
            continue
        if word == "for" and words[index + 2:index + 3] == ["in"]:
            values = words[index + 3:]
            if values:
                bindings[words[index + 1]] = values


def _array_body_end(text: str, start: int) -> int:
    """The index of the `)` that closes an array assignment body."""
    depth, quote, index = 1, None, start
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if not depth:
                return index
        index += 1
    return len(text)


def _record_array_assignments(text: str, bindings: dict[str, list[str]]) -> None:
    """Bind every array this text assigns, in each spelling bash accepts.

    Read from the whole text rather than a segment because `(` ends a command
    as far as _split_segments is concerned: `arr=(scripts/bash-guard.py)`
    arrives as a bare `arr=` and a separate segment holding the path, so the
    binding is invisible to anything reading one segment at a time.

    Position is not tracked, so a name bound later in the command counts for a
    reference earlier in it. That over-refuses rather than under-refuses.
    """
    for match in _ARRAY_ASSIGNMENT_RE.finditer(text):
        body = text[match.end():_array_body_end(text, match.end())]
        values = []
        for element in _shell_words(body):
            keyed = _KEYED_VALUE_RE.match(element)
            values.append(keyed.group(1) if keyed else element)
        if values:
            bindings.setdefault(match.group(1), []).extend(values)


def check_protected_paths(command: str) -> str | None:
    """Block writes to the guard's own files and reads of any .env, through Bash.

    Three routes are covered because three routes exist: a redirection, a
    command whose arguments are files it modifies, and an interpreter payload
    naming the path directly.
    """
    lowered = command.lower()
    # `$` and a backtick are in the prefilter because an expansion can produce a
    # protected path out of a command that names none of the other tokens:
    # `cp payload.py $(cat target.txt)` mentions nothing at all, and
    # `F=bash-guar; rm ${F}d.py` spells the name in two halves. A glob or a
    # brace is here for the same reason and was not: the tokens below are only
    # readable while the word is literal, and `mv clean-rag/hook*/x.py` spells
    # none of them.
    if not any(token in lowered for token in
               (".env", "scripts", "hooks", "settings", "bash-guard",
                ".claude", "$", "`", "*", "?", "[", "{")):
        return None

    bindings: dict[str, list[str]] = {}
    for text, _routed, kind in _scannable_texts(command):
        if kind == "interpreter":
            words = _SOURCE_PATH_RE.findall(text)
            problem = _env_read_problem(words)
            if problem:
                return problem
            for word in words:
                if _is_protected_path(word):
                    return _protected_refusal(word, "named inside interpreter source")
            continue

        _record_array_assignments(text, bindings)
        for _separator, segment in _split_segments(text):
            segment = _resolve_variables(segment, bindings)
            _record_assignments(segment, bindings)
            words = _shell_words(segment)
            problem = _env_read_problem(words, _operands_to_skip(segment))
            if problem:
                return problem
            for index, word in enumerate(words):
                if word in _REDIRECT_WORDS and index + 1 < len(words):
                    problem = _write_target_problem(
                        words[index + 1], "a redirection target", bindings)
                    if problem:
                        return problem
            command_words = _command_words(segment)
            if not command_words:
                continue
            how = f"written by `{_binary_name(command_words[0])}`"
            for word in _written_operands(command_words):
                problem = _write_target_problem(word, how, bindings)
                if problem:
                    return problem
    return None


def _write_target_problem(word: str, how: str,
                          bindings: dict[str, list[str]] | None = None) -> str | None:
    """The refusal this write target earns, or None.

    The target is judged as every string it can expand to, so a name the
    command binds is followed into its value and a word written inside the
    braces is read as the path it becomes. A loop name stands for every path
    in its list, and each is judged as if the body had written it out.

    A target built by a command substitution is refused rather than resolved.
    Nothing bounds what the substitution prints: it can emit a leading
    directory, so no amount of visible text around it rules out a control file.
    `$(echo scripts/bash-guard.py)` reached the guard itself while all eight
    literal spellings of the same path were refused.
    """
    spellings = _expansion_spellings(word, bindings or {})
    for spelling in spellings:
        landing = _marker_reaches_protected(spelling)
        if landing:
            return _protected_refusal(landing, f"{how} once {word} expands")
        if _is_protected_path(spelling):
            return _protected_refusal(spelling, how)
    if any(_SUBSTITUTION_MARK in spelling for spelling in spellings):
        return (
            f"BLOCKED: this command is {how}, and part of the target is built by a "
            "command substitution, so the path it names is only known once it runs. "
            "The files that decide what this session may do are protected by path, "
            "and a path this guard cannot read is one it cannot clear. Write the "
            "path literally, or compute the name in a separate command first."
        )
    # Nothing in the command defines it, so only the environment knows what it
    # names. Same reasoning as the substitution above, and narrowed to the
    # whole word: `> ${TMPDIR}/out.txt` keeps a readable filename.
    if any(spelling == _UNREADABLE for spelling in spellings):
        return (
            f"BLOCKED: this command is {how}, and the whole target is {word}, whose "
            "value comes from the environment rather than from the command. A path "
            "this guard cannot read is one it cannot clear against the files that "
            "decide what this session may do. Write the path literally, or assign it "
            "in the same command so it is visible."
        )
    return None


def _protected_refusal(path: str, how: str) -> str:
    return (
        f"BLOCKED: {path!r} is {how}, and it is one of the files that decide what "
        "this session is allowed to do (the command guard, the research and "
        "verifier hooks, the settings files, and the tests that keep them honest). "
        "A guard the session can overwrite is not a guard. Bash is the route that "
        "is closed: make the change with the Edit or Write tool, where the human "
        "sees the diff, or ask them to make it."
    )


# ---------------------------------------------------------------------------
# Routing through a program that runs what it is handed.
# ---------------------------------------------------------------------------

# An awk program that reaches a shell: system(), a coprocess, or print into a
# command. Verified: `awk 'BEGIN{system("echo X")}'` printed X.
_AWK_EXEC_RE = re.compile(r"\bsystem\s*\(|\|&|\|\s*[\"']")

_SED_SCRIPT_FLAGS = frozenset({"-e", "--expression", "-f", "--file"})


def check_shell_exec_routing(command: str) -> str | None:
    """Block the shapes whose whole purpose is to run text as a command.

    Piping into a shell is the one this matters most for: it defeats every
    check that reads the command, because the command being run is data at the
    time the guard sees it. claude-code-bash-guardian keeps the same category
    under `forbidden_pipe_targets` for the same reason.
    """
    lowered = command.lower()
    if not any(token in lowered for token in ("|", "sed", "awk", "xargs")):
        return None

    for text, _routed, kind in _scannable_texts(command):
        if kind == "interpreter":
            continue
        for separator, segment in _split_segments(text):
            words = _command_words(segment)
            if not words:
                continue
            name = _binary_name(words[0])
            if "|" in separator and name in _SHELL_BINARIES:
                return (
                    f"BLOCKED: this command pipes into `{name}`, so what actually runs "
                    "is text produced at runtime. Nothing that reads the command can "
                    "see it, including this guard and the permission rules. Run the "
                    "command you mean directly."
                )
            if name == "sed":
                script = _sed_script(words[1:])
                if _SED_EXEC_COMMAND_RE.search(script) or _SED_EXEC_FLAG_RE.search(script):
                    return (
                        "BLOCKED: this sed script uses the `e` command or the `e` flag on "
                        "`s///`, both of which run their argument through a shell. "
                        f"Found: {script[:80]!r}."
                    )
            if name == "awk" and any(_AWK_EXEC_RE.search(word) for word in words[1:]):
                return (
                    "BLOCKED: this awk program reaches a shell (system(), a coprocess, or "
                    "a print into a command). awk runs it directly, so nothing that reads "
                    "the command sees what runs."
                )
    return None


def _sed_script(args: list[str]) -> str:
    """The script text of a sed invocation, from -e/-f or the first operand."""
    parts, expect_script, seen_operand = [], False, False
    for word in args:
        if expect_script:
            parts.append(word)
            expect_script = False
            continue
        if word in _SED_SCRIPT_FLAGS:
            expect_script = True
            continue
        if word.startswith("-"):
            continue
        if not seen_operand:
            parts.append(word)
            seen_operand = True
    return "\n".join(parts)


def _command_from_payload(payload) -> str:
    """The Bash command out of a PreToolUse payload, or "" if there isn't one.

    Stdin is a system boundary and every shape guarded here is valid JSON: the
    payload a bare scalar, null, or a list; tool_input null or a string; the
    command a number or a list. A naive payload.get(...).get(...) chain raises
    AttributeError or TypeError on each of them, and an uncaught exception
    exits 1 — which this hook contract reads as neither allow (0) nor block
    (2), so the command runs anyway with a traceback shown to the user.
    """
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return command if isinstance(command, str) else ""


# Checks that exist so Claude Code's own scanners do not prompt on a command
# the allow list already covers. Turning one off costs an extra prompt.
_ERGONOMIC_CHECKS = (
    check_env_var_expansion,
    check_cat_heredoc,
    check_coauthor,
    check_python_multiline_c,
    check_cd_compound,
    check_backslash_spaces,
)

# Checks that are the boundary. Turning one off costs the boundary, so the off
# switch does not reach them and a crash in one blocks rather than allows.
_SECURITY_CHECKS = (
    check_db_mutation,
    check_production_environment,
    check_destructive_delete,
    check_ssh_external,
    check_netcat,
    check_curl_external,
    check_shell_exec_routing,
    check_protected_paths,
    # Before the verb gate, because a routed write and a plain write are both
    # refused and the routed message is the one that explains the route.
    check_routed_git_write,
    check_git_gh_verbs,
    # After it, so a visible write is named as one rather than as a missing verb.
    check_argument_feeder,
)

_OFF_VALUES = frozenset({"off", "0", "false", "disabled", "no"})


def _ergonomics_disabled() -> bool:
    return os.environ.get("CLAUDEBOOST_BASH_GUARD", "").strip().lower() in _OFF_VALUES


def evaluate(command: str) -> str | None:
    """The first refusal this command earns, or None.

    Security checks run first so a crash in an ergonomic check cannot let a
    write through by ordering. Each check is isolated: an ergonomic one that
    raises is skipped, because its only job is avoiding a prompt, while a
    security one that raises blocks, because a guard that cannot decide has no
    basis to allow.
    """
    for check in _SECURITY_CHECKS:
        try:
            message = check(command)
        except Exception as error:
            message = (
                f"BLOCKED: the command guard crashed while checking this command "
                f"({check.__name__}: {error!r}). It blocks rather than allows when it "
                "cannot decide, because it is what stops git writes and protects its "
                "own files. Report the command above so the guard can be fixed, or "
                "run it yourself in a terminal."
            )
        if message:
            return message

    if _ergonomics_disabled():
        return None

    for check in _ERGONOMIC_CHECKS:
        try:
            message = check(command)
        except Exception as error:
            _write_block_telemetry(
                "Bash", command, f"{check.__name__}: {error!r}", result="check_error")
            continue
        if message:
            return message
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

    command = _command_from_payload(payload)
    if not command:
        return 0

    message = evaluate(command)
    if message:
        print(message, file=sys.stderr)
        _write_block_telemetry("Bash", command, message)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
