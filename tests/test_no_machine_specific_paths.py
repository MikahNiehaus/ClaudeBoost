"""ClaudeBoost must run from any clone, on any machine, under any username,
and it must not carry anyone's private information into a public repo.

Three shapes prove it does not, and each one fails silently rather than
loudly. A test that hardcodes the repo root passes on the machine that wrote
it for the wrong reason, so the suite stops being evidence of anything. A
committed home directory names whoever wrote the line. A committed internal
hostname names whoever the work was for.

The first two shapes used to be matched as two fixed literals, one developer's
name and one clone path. A literal only ever catches the machine it was
written on: a second developer's home directory sat in three tracked files the
whole time the suite was green. These patterns are structural instead, so a
username nobody has seen yet still fails.

This is the repo-wide version of the per-skill check in
plans/test_powerpoint_env.py (t_no_machine_specific_paths). It scans what git
tracks, so generated output (~/.claude/settings.json, .rag-index, state/)
is out of scope by construction -- clean-rag/install.py deliberately writes
absolute per-machine paths there and must keep doing so.

Synthetic path fixtures are unaffected: they use placeholder names
(C:/Development/MyApp, C:/Users/foo, /Users/user), and PLACEHOLDER_NAMES
below is the list of user names that read as obvious stand-ins.

What the hostname rule deliberately does NOT try to do: decide whether an
arbitrary domain is someone's private property. Measured against this tree, a
"hostname on a real TLD" rule matches 305 distinct domains, nearly all of them
legitimate citations, and a checker that noisy gets switched off. The rule
below targets the narrower shape that is never a public citation: a named
lower environment, such as api-test.contoso.com or acme-staging.someorg.net.
An internal environment hostname is the part that both leaks a client and, in
this repo, doubles as a browser automation allowlist entry. A bare
corporate hostname carrying no environment label is not structurally
distinguishable from github.com and is not claimed to be covered.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# User names that read as an obvious stand in rather than a real account.
# Two real first names sat in fixtures here for months because they looked
# like placeholders. If a name is not on this list, the test says so.
# "test" is deliberately absent, unlike "testuser": it is an ordinary local
# account name on a shared QA box, so accepting it as a stand-in hides a real
# leak. Measured cost of dropping it: three synthetic paths in
# scripts/tests/test_workspace_identity.py, now on "foo".
PLACEHOLDER_NAMES = frozenset({
    "foo", "bar", "baz", "qux", "user", "username", "youruser", "your-name",
    "you", "me", "someone", "somebody", "alice", "bob", "carol", "example",
    "testuser", "demo", "dummy", "placeholder", "name", "x",
    # Already redacted prose: `C:/Users/.../AppData`.
    "...",
    # Real, but the same on every GitHub Actions and container runner, so
    # it is not this machine.
    "runner", "ubuntu", "vscode", "root",
})

# A home directory in any of the three spellings this repo has produced:
# Windows (C:\Users\NAME), POSIX (/home/NAME, /Users/NAME), and Claude Code's
# own mangled slug for a cwd (~/.claude/projects/C--Users-NAME/, every non
# alphanumeric character replaced with a dash -- see scripts/session-restore.py
# _transcript_exists). A doc that quotes the mangled slug directly, as
# .claude/commands/self-improve.md once did, is just as machine specific as one
# that quotes the raw path, and the colon/slash form alone misses it.
_NAME = r"[A-Za-z0-9._-]+"
HOME_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(" + _NAME + r")", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]--Users-(" + _NAME + r")", re.IGNORECASE),
    # ":" joins the lookbehind so "C:/Users/x" is reported once by the Windows
    # pattern rather than twice.
    re.compile(r"(?<![\w.:])/(?:home|Users)/(" + _NAME + r")"),
)

# A hostname naming someone's lower environment. The environment word has to
# be a whole hyphen delimited segment of a label, never a substring, or
# "developer.nvidia.com" and "tutorialspoint.com" both read as environments.
_ENV_WORD = (r"(?:test|tst|temp|tmp|trial|dev|devel|staging|stage|qa|uat|sit"
             r"|prod|preprod|nonprod|sandbox|sbx|demo|perf|integration)")

# Environment words that are also ordinary organisation names, so they only
# count in the one position an organisation never uses: after the thing they
# qualify. Measured against real public sites, matching these anywhere claimed
# www.acc.org, www.stg.co.jp, stg-labs.com, acc-ltd.co.uk, www.int-evry.fr,
# docs.acc-systems.io and www.development-bank.org, while the leak shape is
# always api-acc.<client> or manager-stg.<client>.
#
# Wikipedia's "Deployment environment" names integration, acceptance and
# staging as standard tiers; these are their usual short spellings.
_TRAILING_ONLY_ENV_WORDS = frozenset({"development", "stg", "int", "acc"})
_PUBLIC_TLD = (r"(?:com|org|net|io|co|ai|dev|app|edu|gov|info|cloud|tech|me"
               r"|sh|us|uk|ca|de|fr|nl|au|jp|eu|xyz|online|site|biz)")
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
ENV_HOST_PATTERN = re.compile(
    r"\b((?:" + _LABEL + r"\.)+" + _PUBLIC_TLD + r")\b", re.IGNORECASE)

# Zones where every subdomain is exempt, because the whole domain exists to be
# written down. Nobody's real environment lives here, so a fixture may invent
# api-test.contoso.com and mean nothing by it.
ALLOWED_ZONES = frozenset({
    # RFC 2606 / RFC 6761 reserved for documentation. Always safe.
    "example.com", "example.org", "example.net",
    # Microsoft's fictional companies, registered by them precisely so
    # documentation has a hostname that implicates nobody. Test fixtures that
    # need a realistic environment hostname use these.
    "contoso.com", "fabrikam.org", "fabrikam.com",
})

# Single public hosts, matched whole. A real company's zone never goes in here:
# allowlisting the registrable domain of one exempts every name under it, so
# api-test.paypal.com and manager-stg.paypal.com both read as clean while
# carrying the shape this file exists to catch.
ALLOWED_HOSTS = frozenset({
    # Public developer services whose own hostname carries an environment word.
    "dev.azure.com",
    # PayPal's sandbox is public, documented, and appears verbatim in their own
    # code samples. A checker that calls that a leak is one somebody turns off.
    "sandbox.paypal.com", "api-m.sandbox.paypal.com",
    # A public product cited by name in a fetched article. Named host, not the
    # vercel.app zone, because a client's own staging site can live there too.
    "ai-dev-toolkit-five.vercel.app",
})

# Extensions that can execute, instruct, or record. A results log neither
# executes nor instructs, but it carries the absolute paths of the machine that
# produced it, which is the whole point of the home directory rule.
#
# Markup is here because a leak does not care what renders it: a path or a
# hostname in a comment inside clean-rag/server/kanban.html is as public as one
# in a .py file, and was scanned by nothing.
#
# .example is here because .env.example is tracked: a template carries the
# same hostnames and the same username as the file it is a template for, and
# it is the one a reader copies.
SCANNED_SUFFIXES = {".py", ".js", ".ts", ".sh", ".bat", ".ps1", ".json", ".md",
                    ".toml", ".cfg", ".ini", ".yml", ".yaml", ".txt",
                    ".html", ".htm", ".css", ".example"}

# Prose that documents a real past incident by quoting the path it happened
# to. These are comments, not paths anything resolves.
ALLOWED = {
    "clean-rag/hooks/rag-enforce.py",
}

# The detector and its fixtures. Both have to spell out the leak shapes they
# match, so scanning them reports every fixture as a leak.
SELF = {
    "tests/test_no_machine_specific_paths.py",
    "tests/test_no_machine_specific_paths_adversarial_gaps.py",
}


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line.strip()]


def _scannable() -> list[Path]:
    files = []
    for path in _tracked_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED or rel in SELF:
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        if not path.is_file():
            continue
        files.append(path)
    return files


def _read(path: Path) -> str | None:
    """Undecodable bytes are replaced, never a reason to skip the file.

    benchmarks/codesearchnet/results/run_log.txt is cp1252 and carried a home
    directory for as long as this test skipped whatever failed to decode.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _home_hits(line: str) -> list[str]:
    names = []
    for pattern in HOME_PATTERNS:
        for name in pattern.findall(line):
            if name.lower() not in PLACEHOLDER_NAMES:
                names.append(name)
    return names


def _env_host_hits(line: str) -> list[str]:
    hosts = []
    for host in ENV_HOST_PATTERN.findall(line):
        host = host.lower()
        registrable = ".".join(host.split(".")[-2:])
        if host in ALLOWED_HOSTS or registrable in ALLOWED_ZONES:
            continue
        labels = host.split(".")
        # A bare two label domain whose name simply is the word, test.com or
        # demo.io, is a generic domain, not somebody's environment. It takes a
        # subdomain or a hyphen to name an environment of something.
        if len(labels) == 2 and "-" not in host:
            continue
        if any(_label_names_an_environment(label) for label in labels[:-1]):
            hosts.append(host)
    return hosts


# An environment word carrying an instance suffix. A second copy of a tier gets
# a number, and the number lands on either end: test1, 2test, dev01, test10x.
# Stripping only a trailing run of digits caught the first spelling and none of
# the others.
#
# The trailing letter is allowed only behind digits, which is what keeps
# "devs", "tests" and "demos" ordinary words while "test10x" reads as the
# instance it names.
_ENV_SEGMENT_RE = re.compile(r"\d*" + _ENV_WORD + r"(?:\d+[a-z]?)?", re.IGNORECASE)


def _label_names_an_environment(label: str) -> bool:
    segments = label.split("-")
    if any(_ENV_SEGMENT_RE.fullmatch(segment) for segment in segments):
        return True
    trailing = re.sub(r"\d+$", "", segments[-1]) or segments[-1]
    return len(segments) > 1 and trailing.lower() in _TRAILING_ONLY_ENV_WORDS

CHECKS = {
    "a developer's home directory": _home_hits,
    "a private environment hostname": _env_host_hits,
}


def test_git_ls_files_actually_returned_something():
    """Guard the guard. If git fails or the filter is wrong, every other test
    in this file passes vacuously over an empty list."""
    files = _scannable()
    assert len(files) > 100, f"expected to scan hundreds of tracked files, got {len(files)}"


def test_no_tracked_file_hardcodes_this_clone():
    pattern = re.compile(
        r"[Cc]:[\\/]+Development[\\/]+ClaudeBoost|C--Development-ClaudeBoost",
        re.IGNORECASE)
    hits = []
    for path in _scannable():
        text = _read(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = path.relative_to(REPO_ROOT).as_posix()
                hits.append(f"  {rel}:{lineno}: {line.strip()[:110]}")

    assert not hits, (
        f"{len(hits)} tracked line(s) hardcode this clone's absolute path.\n"
        "Derive it instead: Path(__file__).resolve().parents[N], Path.home(), "
        "or the $CLEAN_RAG_HOME / $CLAUDEBOOST_HOME env vars this repo already uses.\n"
        + "\n".join(hits)
    )


@pytest.mark.parametrize("label", sorted(CHECKS))
def test_no_tracked_file_leaks(label: str):
    find = CHECKS[label]
    hits = []
    for path in _scannable():
        text = _read(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            found = find(line)
            if found:
                rel = path.relative_to(REPO_ROOT).as_posix()
                hits.append(f"  {rel}:{lineno}: {sorted(set(found))} :: {line.strip()[:90]}")

    assert not hits, (
        f"{len(hits)} tracked line(s) leak {label} into a public repo.\n"
        "Home directories: derive the path, or use a PLACEHOLDER_NAMES stand-in.\n"
        "Environment hostnames: they belong in the gitignored local config that\n"
        ".claude/browser-targets.example.json documents, never in tracked source.\n"
        + "\n".join(hits)
    )


def test_the_home_pattern_matches_real_leaks_and_not_placeholders():
    """A regex that matches nothing would make the test above always pass."""
    for leaked, name in (
        (r"C:\Users\jdoe\.claude\agents\quick-cop.md", "jdoe"),
        ("C:/Users/jdoe/.claude/settings.json", "jdoe"),
        ("~/.claude/projects/C--Users-jdoe/memory/MEMORY.md", "jdoe"),
        ("Project: C:/Users/asmith/OneDrive/prj/ClaudeBoost", "asmith"),
        (r"Writing files to C:\Users\asmith\AppData\Local\Temp\csn_bench", "asmith"),
        ("/home/bjones/src/claudeboost", "bjones"),
        ("ls /Users/kpatel/Documents", "kpatel"),
        # An ordinary account name on a shared QA box, not a stand-in.
        (r"C:\Users\test\Documents\client-notes.txt", "test"),
    ):
        assert _home_hits(leaked) == [name], leaked

    for benign in (
        "C:/Development/MyApp",
        r"C:\Users\foo\project",
        "/Users/user/notes",
        "/home/runner/work/repo",
        "C:/Users/<user>/.claude",
        "Path(__file__).resolve().parents[1]",
    ):
        assert _home_hits(benign) == [], benign


def test_the_hostname_pattern_matches_real_environments_and_not_citations():
    # Deliberately not the ALLOWED_HOSTS placeholders: these have to prove the
    # structural pattern bites, which an allowlisted domain cannot do.
    for leaked in (
        "api-test.someclient.com",
        "admin-temp.someclient.com",
        "manager-test.otherclient.org",
        "*.otherclient-dev.com",
        "https://acme-staging.someorg.net/login",
        "api-uat.newclient.io",
        "sandbox.someorg.com",
        "api-development.someclient.com",
        "manager-stg.someclient.com",
        "api-int.someclient.com",
        "portal-acc.someclient.net",
        # An instance number, wherever it lands in the label.
        "api-test10x.someclient.com",
        "api-2test.someclient.com",
        "01dev.someclient.com",
        # A zone allowlisted for one public host does not exempt the rest of it.
        "api-test.paypal.com",
        "manager-stg.paypal.com",
    ):
        assert _env_host_hits(leaked), leaked

    for benign in (
        "https://developer.nvidia.com/blog",
        "https://developer.mozilla.org/en-US/docs/Web",
        "https://tutorialspoint.com/x",
        "https://javatpoint.com/y",
        "https://developers.googleblog.com/z",
        "https://github.com/anthropics/claude-code",
        "https://react.dev/reference",
        "https://dev.azure.com/org/project",
        "https://api-m.sandbox.paypal.com/v2/checkout",
        "https://staging.example.com/health",
        "https://headroom-docs.vercel.app/guide",
        # A plural is a word, not a numbered instance.
        "https://devs.someclient.com/docs",
        "https://demos.someorg.net/",
        "git commit --author 'Test <test@test.com>'",
        "localhost:8613",
        "manager.env-e.local",
        "app.something.test",
    ):
        assert _env_host_hits(benign) == [], benign
