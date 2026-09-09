"""Project file selection for clean-rag: what counts as indexable source.

Extracted from indexing.py so the isolated GraphRAG venv can reuse the exact same
hardened skip rules without importing indexing.py (which pulls chromadb and the
embedding stack). Pathlib only, no heavy deps, importable from anywhere.

The skip rules matter: measured on ClaudeBoost, without the virtualenv and
site packages skips a single venv leaked 9330 of 9721 scanned files into the index.
With them, the same tree scans to 391 real source files.
"""

from __future__ import annotations

import logging
import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path

logger = logging.getLogger(__name__)

# Extensions considered indexable source code
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs",
    ".go", ".rs", ".java", ".kt", ".scala",
    ".cs", ".fs", ".vb",
    ".c", ".cpp", ".cc", ".h", ".hpp",
    ".rb", ".php", ".swift", ".m",
    ".lua", ".r", ".jl", ".dart", ".zig",
    ".sh", ".bash", ".zsh", ".ps1",
    ".sql", ".graphql", ".proto",
    ".html", ".cshtml", ".razor", ".css", ".scss", ".less", ".vue", ".svelte",
    ".yaml", ".yml", ".toml", ".json", ".xml",
    ".md", ".mdx", ".rst", ".txt",
}

# Directories to skip during project scanning
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target",
    "vendor", ".tox", ".mypy_cache", ".pytest_cache",
    "coverage", ".coverage", "bin", "obj",
    "workspace",  # ClaudeBoost workspace dirs
    ".rag-index",  # ClaudeBoost RAG index
    ".claude",  # Claude config
    "knowledge",  # clean-rag knowledge (indexed separately as topics)
    "databases",  # clean-rag databases
    # Installed dependency trees. The site packages dir is the big one: a single
    # venv leaks thousands of dependency files into the graph without it (measured
    # on ClaudeBoost, 9330 of 9721 scanned files were venv contents).
    "site-packages", ".eggs", "env", ".conda",
    # IDE and editor state (these pass the extension allowlist otherwise).
    ".idea", ".vscode",
    # Build, cache, and generated output across ecosystems.
    "htmlcov", ".ruff_cache", ".ipynb_checkpoints", ".gradle", "out",
    ".terraform", ".serverless", ".turbo", ".parcel-cache",
    ".svelte-kit", ".angular",
    # Apple and iOS dependency and build dirs.
    "Pods", "Carthage", "DerivedData",
}

# Generated files to skip (exact filenames)
SKIP_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Packages.lock.json",
    "packages.lock.json",
    "npm-shrinkwrap.json",
    # Lockfiles across ecosystems: data, not code, zero graph value.
    "Cargo.lock", "Gemfile.lock", "poetry.lock", "Pipfile.lock",
    "composer.lock", "mix.lock", "go.sum",
    # Coverage and report artifacts.
    "coverage.xml", "coverage.json", "lcov.info",
}

# Config files that routinely carry live credentials.
#
# `.json`, `.yaml` and `.xml` are all in CODE_EXTENSIONS, and there is no
# gitignore or secrets awareness anywhere in this scan, so without this these go
# straight into the index. Measured on one real project: 14 files with populated
# values, including four `ConnectionStrings.*` entries of 150 plus characters
# each and an Azure Functions `local.settings.json` holding a database
# connection, a SignalR endpoint and a ServiceBus namespace.
#
# The index is localhost only and these files were already tracked in git, so
# nothing was leaking off the machine. The problem is narrower and still real: a
# `/search` hit can lift a live connection string into an agent's context, and
# agents send their context onward.
#
# Globs rather than exact names because the environment suffix is arbitrary,
# `appsettings.Development.json`, `.Staging.`, `.Test.`, and whatever a project
# invents next. fnmatch is stdlib and does exactly this.
#
# The cost is real and accepted: config keys stop being searchable, so "where is
# the connection string configured" no longer answers from the index. Names of
# the files are still discoverable by other means, and a credential surfacing in
# a search result is the worse of the two failures.
SKIP_NAME_GLOBS = (
    "appsettings*.json",       # .NET, connection strings and API keys
    "local.settings.json",     # Azure Functions, secrets by design
    "secrets.json",            # dotnet user-secrets
    "*.secrets.json",
    "*.secrets.yaml",
    "*.secrets.yml",
)

# Generated file suffixes to skip
SKIP_SUFFIXES = (
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".d.ts",
    ".generated.cs",
    ".Designer.cs",
    ".g.cs",
    ".AssemblyInfo.cs",
    # Generated code (protobuf, dart codegen), per linguist patterns.
    "_pb2.py", "_pb2_grpc.py", ".pb.go", ".g.dart", ".freezed.dart",
)

MAX_FILE_SIZE = 500_000  # 500KB


def _venv_roots(root: Path) -> set:
    """Directories that are Python virtualenvs, found by their pyvenv.cfg marker.

    Skipping these catches any venv (venv, .venv, graphrag-venv, whatever it is
    named) without maintaining a name list. A venv's installed packages are the
    single biggest source of graph pollution, so this is the general catch behind
    the site packages entry in SKIP_DIRS.
    """
    roots = set()
    try:
        for cfg in root.rglob("pyvenv.cfg"):
            roots.add(cfg.parent)
    except OSError:
        pass
    return roots


#: Ceiling on the one `git check-ignore` call per scan. It took a few seconds on
#: the largest project here (4,486 paths). The timeout exists because
#: mcp-rag-server/src/rag_server/core/scanner.py records subprocess.run() hanging
#: indefinitely on Windows in the MCP subprocess context, which is why that module
#: dropped its git tier entirely. A hang here must degrade to "index everything",
#: never to a stalled scan.
_GIT_TIMEOUT_S = 120


def _git_ignored(root: Path, rels: list) -> set:
    """Which of these paths does git itself consider ignored? None if it cannot say.

    Asking git rather than matching patterns is not pedantry, it is the whole
    correctness argument. A first cut used pathspec against the root .gitignore
    and dropped 64 committed .cs files from one project, whose .gitignore names
    a top level source directory that is nonetheless tracked. **gitignore has no
    effect on a tracked file.** pathspec matches patterns and knows nothing about
    the index, so it cannot express that rule. `check-ignore` consults the index
    by default and reports those files as not ignored, which is correct.

    It also picks up what a root-only pattern read would miss: nested
    .gitignore files, .git/info/exclude, and the user's global excludes file.

    Exit status is a value, not an error: 0 means at least one path is ignored,
    1 means none are, and both are success. Anything else, or a timeout, or no
    git at all, returns None so the caller keeps every file.
    """
    if not rels:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-z", "--stdin"],
            input="\0".join(rels).encode("utf-8"),
            capture_output=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("git check-ignore unavailable for %s: %s", root, e)
        return None
    if proc.returncode not in (0, 1):
        logger.warning(
            "git check-ignore failed for %s (exit %d): %s",
            root, proc.returncode, proc.stderr.decode("utf-8", "replace")[:200],
        )
        return None
    return {p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p}


def _pathspec_ignored(root: Path, rels: list) -> set:
    """Same question for a directory that is not a git repo.

    Safe here precisely because there is no index: with nothing tracked, the
    tracked-wins rule that broke the git case cannot apply, so pattern matching
    is the whole of the answer.

    Cloned from mcp-rag-server/src/rag_server/core/scanner.py:166
    `_discover_via_pathspec`. Returns an empty set rather than None when
    pathspec is missing, keeping the promise in this module's docstring that the
    isolated GraphRAG venv can import it with pathlib and nothing else.
    """
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return set()
    try:
        import pathspec
    except ImportError:
        logger.warning("pathspec not installed; skipping gitignore parsing")
        return set()
    lines = gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
    spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)
    return {r for r in rels if spec.match_file(Path(r).as_posix())}


def _drop_ignored(root: Path, files: list) -> list:
    """Remove whatever the project itself declared untracked.

    The hand kept name lists above cannot keep up. Measured across 9 indexed
    projects, 2,192 of 4,695 recorded files (47%) were already declared ignored
    by those projects: 848 coverage report HTML, 824 playwright MCP page
    snapshots, 481 vendored agent skill files. Exactly 90 of the 2,192 carried a
    source extension and every one was generated or vendored, never application
    code. The project's own ignore rules are a better filter than any list
    maintained here, and they need no upkeep when the next tool invents an
    output directory.

    Batched into one subprocess for the whole scan rather than one per file.
    Fails open: when git cannot answer, every file is kept.
    """
    if not files:
        return files
    rels = [str(Path(f).relative_to(root)) for f in files]
    if (root / ".git").exists():
        ignored = _git_ignored(root, rels)
        if ignored is None:
            return files
    else:
        ignored = _pathspec_ignored(root, rels)
    if not ignored:
        return files
    return [f for f, r in zip(files, rels) if r not in ignored]


#: How much of a file to sniff. git reads the first blob-sized chunk for the
#: same decision; 8KB is plenty to find a NUL in any real binary.
_SNIFF_BYTES = 8192


def looks_binary(path) -> bool:
    """Is this file binary, judged by content rather than by its name?

    Extension is not enough. ``.txt`` is in CODE_EXTENSIONS, so a log file with
    a stray 0x97 byte passed every name and size filter here and then died in
    ``index_project``'s ``read_text(encoding="utf-8")``. That failure left no
    manifest entry, so ``find_changed_files`` reported the file as changed on
    every single sweep and the indexer refused it every single time: an
    infinite retry, and a file permanently missing from search.

    The rule is git's, from ``convert.c``'s ``convert_is_binary``: a single NUL
    byte anywhere in the sniffed chunk is decisive, and separately a
    nonprintable to printable ratio worse than 1:128 catches binaries that
    contain no NUL at all. Only the first is implemented here; the ratio check
    is the second line of defence and is not worth building speculatively.

    Errs toward "not binary": a file we cannot open is left for the indexer to
    report properly rather than silently dropped from the scan.
    """
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(_SNIFF_BYTES)
    except OSError:
        return False
    return b"\x00" in chunk


#: Credential formats that identify themselves. A string matching one of these
#: is a credential whatever file it sits in, so these carry no keyword or length
#: qualifier and no placeholder exemption.
#:
#: The AWS pattern is Yelp/detect-secrets' own, verbatim from
#: detect_secrets/plugins/aws.py (AWSKeyDetector.denylist[0]); the private key
#: headers follow detect_secrets/plugins/private_key.py. The vendor prefixes are
#: the issuer assigned ones, which is what makes them unambiguous: a literal
#: ``ghp_`` or ``xoxb-`` followed by the token body is not something prose
#: produces by accident.
_IDENTIFIABLE_SECRET_PATTERNS = (
    re.compile(r"(?:A3T[A-Z0-9]|ABIA|ACCA|AKIA|ASIA)[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN\s+(?:[A-Z]+\s+)?PRIVATE KEY(?:\s+BLOCK)?-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
)

#: Names that introduce a credential when something is assigned to them. Same
#: idea as detect_secrets' KeywordDetector: the variable name is the signal,
#: because a password is not distinguishable from any other short string by
#: looking at the value alone.
_SECRET_NAME_RE = re.compile(
    r"password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?key"
    r"|auth[_-]?token|client[_-]?secret|private[_-]?key|connection[_-]?string",
    re.IGNORECASE,
)

#: Names that contain a credential word but describe something ABOUT a
#: credential rather than holding one. Both examples are from real projects:
#: ``passwordErrorMessage`` holds validation copy shown to a user, and
#: ``CHANGE_PASSWORD_POLICY_NAME`` holds the name of an Azure B2C policy.
#: Dropping either from the index protects nothing and loses real code.
_NOT_THE_SECRET_NAME_RE = re.compile(
    r"(?:name|message|label|policy|error|hint|prompt|title|description"
    r"|regex|pattern|length|enabled|required|placeholder|visible)$",
    re.IGNORECASE,
)

#: Characters allowed to sit between the name and the assignment operator.
#: Yelp/detect-secrets' own ``CLOSING`` from detect_secrets/plugins/keyword.py,
#: verbatim as a character class.
#:
#: This is the only reason the rule below reaches JSON. JSON quotes its keys,
#: so ``{"password": "..."}`` puts a quote immediately after the name, and a
#: pattern anchored straight to ``[:=]`` cannot fire on any .json file at all,
#: which is the format that carries the connection strings this module was
#: written for. detect-secrets has no JSON specific rule either (JSON is absent
#: from its REGEX_BY_FILETYPE and falls to the default set); quoted keys match
#: there purely because these three characters are permitted here. The bracket
#: also picks up ``creds["password"] = "..."``.
#:
#: Measured cost of allowing them, re-measured over six real projects, 7846
#: files scanned: 14 files dropped before, 16 after. Both new drops are false
#: positives, and both come from the same shape, a name that merely CONTAINS a
#: keyword sitting behind a quote or a bracket:
#: ``Headers["X-Secret-Translation-Password"] = "secret-password"`` in a .NET
#: test fixture, and ``"secretStore": "AzureAppSettings"`` in a generated Azure
#: service dependency file.
#:
#: Read that as a class, not as a list. ``_SECRET_NAME_RE`` below is a bare
#: ``re.search``, so any bracket indexed name containing a keyword anywhere
#: qualifies, whatever it describes: ``errors["api_key"] = "missingValueCode"``
#: (an error catalogue) and ``testCases["apiKeyValidationScenario"] = "..."``
#: (a fixture table) both match here and neither holds a credential. The two
#: found in real trees are what that class costs at today's corpus size, not
#: its ceiling.
#:
#: Removing ``]`` would take the bracket half back to zero and still fix JSON,
#: at the price of never seeing a real ``config["db_password"] = "<live>"``.
#: Kept, because this module's standing trade is that a credential reaching a
#: /search result is the worse of the two failures, and over-suppression is the
#: direction SKIP_NAME_GLOBS and the keyword rule already accepted.
_CLOSING = r"""[]"']{0,2}"""

#: What a key may be called. Shared by both assignment rules below so the two
#: cannot disagree about it, which they did: the quoted rule allowed dots and
#: the environment rule did not, so ``spring.datasource.password=<live value>``
#: matched neither. That is not a hypothetical key format. It is how every
#: Spring, Java and .NET hierarchical property is written, and while
#: ``.properties`` itself is not in CODE_EXTENSIONS, the same block pasted into
#: a README or a TROUBLESHOOTING.md is, which is precisely the "jotted it into
#: notes.md for now" case looks_like_secret exists to catch.
#:
#: Hyphens come along for the same reason: ``x-api-key`` is a real header name
#: and a real key name.
#:
#: Measured cost of widening the environment rule to this class, over the same
#: six real projects and 7846 files: zero additional files dropped, and none
#: lost. That is what one corpus happened to contain, not what the class costs,
#: and it should be read the way the _CLOSING note above asks to be read: a
#: floor, not a ceiling.
#:
#: The shape it does not cover is a dotted or hyphenated key that CONTAINS a
#: credential word while naming something ABOUT the credential. These three are
#: ordinary Spring, .NET and Java config, hold nothing secret, and are all
#: dropped:
#:
#:     app.api-key-rotation-schedule=EVERY_30_DAYS_AT_MIDNIGHT_UTC
#:     com.example.auth-token-refresh-interval-ms=1800000000000000
#:     service.client-secret-file-path=/etc/secrets/client.pem
#:
#: None of the three existed in the corpus, which is why the measurement is
#: zero. It is not why the cost is.
#:
#: The guards after the name match do not hold that line and cannot: a
#: schedule, an interval and a file path are all literals longer than
#: _MIN_SECRET_VALUE_LEN, and none is a placeholder or prose. The only guard
#: that could is _NOT_THE_SECRET_NAME_RE, and only for the suffixes it lists,
#: none of which these end in. Kept anyway, for the reason _CLOSING is kept:
#: dropping a config key costs a search hit, and the other direction puts a
#: live credential in one.
_KEY_NAME = r"[A-Za-z_][A-Za-z0-9_.\-]*"

#: A credential assigned as a quoted literal: ``Secret = "whsec_..."``,
#: ``apiKey: 'key_live_...'``, ``"connectionString": "Server=..."``.
#:
#: The value has to be a literal, and that restriction is the whole difference
#: between a usable rule and an unusable one. Measured on a real .NET project,
#: accepting an unquoted right hand side dropped 26 files of 1668, and 24 of
#: those were correct code READING a secret out of config
#: (``ApiKey = Environment.GetEnvironmentVariable(...)``,
#: ``password: Input.Password``). That is the pattern you want developers to
#: use and the code they most need to find, so matching it is worse than
#: useless. A quoted literal cannot be an expression.
_QUOTED_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<name>" + _KEY_NAME + r")" + _CLOSING + r"\s*[:=]\s*"
    r"(?P<quote>[\"'])(?P<value>[^\"'\n]+)(?P=quote)",
)

#: A credential in environment file form: ``DB_PASSWORD=hunter2`` on a line of
#: its own, optionally exported. The whole line being the assignment is what
#: makes this safe to accept unquoted: source code assigns with spaces around
#: the operator and rarely ends the statement there, so the shapes do not
#: overlap. This is the form a developer uses in the scratch note that
#: SKIP_NAME_GLOBS never sees, and the form a Spring or Java property block
#: keeps when it is pasted into one, which is why the name class is shared with
#: the quoted rule above rather than spelled out again here.
_ENV_SECRET_ASSIGNMENT_RE = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?P<name>" + _KEY_NAME + r")="
    r"(?P<value>[^\s#]+)[ \t]*$",
    re.MULTILINE,
)

#: Trailing characters that belong to the surrounding prose, not to the value.
#: Stripped so a value written at the end of a sentence is judged on the value
#: itself rather than on the full stop that follows it.
_VALUE_TRAILING_PUNCTUATION = ".,;:!?)]`"

#: Shortest assigned value treated as a real credential. Real secrets are
#: comfortably longer than this; doc examples and obvious stand ins are
#: shorter. The bar exists so a name match alone cannot drop a file, since the
#: name based rule is the one that can be wrong.
_MIN_SECRET_VALUE_LEN = 12

#: Values that read as a credential but are placeholders. Substring matched
#: case insensitively, so ``YOUR_API_KEY_HERE`` and ``replace-with-your-token``
#: are both covered.
_PLACEHOLDER_MARKERS = (
    "example", "placeholder", "your", "yours", "changeme", "change_me",
    "todo", "tbd", "dummy", "sample", "test", "fake", "redacted", "xxxx",
    "insert", "replace", "notreal", "n/a", "none", "null", "empty",
)


def _is_prose(value: str) -> bool:
    """Does this value read as a sentence rather than as a credential?

    Credentials do not contain spaces. Connection strings are the one real
    exception (``Integrated Security=True``), and they are recognisable by
    their own delimiters, so they are kept.
    """
    if " " not in value:
        return False
    return not (";" in value and "=" in value)


def _is_placeholder(value: str) -> bool:
    """Is this assigned value a stand in rather than a live credential?

    The templated shapes are Yelp/detect-secrets'
    ``filters/heuristic.is_templated_secret``: ``{secret}``, ``<secret>`` and
    ``${secret}`` are all interpolation syntax, never the secret itself.
    """
    if not value:
        return True
    if (
        (value[0] == "{" and value[-1] == "}")
        or (value[0] == "<" and value[-1] == ">")
        or (value.startswith("${") and value[-1] == "}")
        or (value.startswith("%") and value.endswith("%"))
    ):
        return True
    low = value.lower()
    return any(marker in low for marker in _PLACEHOLDER_MARKERS)


def looks_like_secret(path) -> bool:
    """Does this file carry a live credential, judged by content?

    The companion to looks_binary above, and asked the same way: about what is
    in the file, not what the file is called. SKIP_NAME_GLOBS only knows config
    file NAMES, so it never sees the case this catches, which is a developer
    jotting a real value into ``credentials.txt``, ``notes.md`` or ``TODO.md``
    "for now". Those pass every name and extension filter, get chunked and
    embedded like ordinary prose, and come back verbatim in a /search hit. This
    module's own risk statement covers that exactly: "a /search hit can lift a
    live connection string into an agent's context, and agents send their
    context onward."

    Two rules, deliberately unequal, because they have very different false
    positive rates:

    - An identifiable credential (an AWS key id, a PEM private key header, a
      vendor prefixed token) is decisive on its own. Those formats are issuer
      assigned and prose does not produce them by accident.
    - A credential named variable only counts when a literal is assigned to it,
      that literal is long enough to be real, and it is not a recognisable
      placeholder. This is the rule that can be wrong, so it is the qualified
      one: it deliberately does not fire on code that reads a secret from
      configuration, which is both the correct pattern and the code developers
      most need to find.

    The cost is the same one SKIP_NAME_GLOBS already accepted and wrote down: a
    document that quotes a realistic looking credential stops being searchable.
    A credential surfacing in a search result is the worse of the two failures.

    Errs toward "no secret" on any read error, matching looks_binary: a file we
    cannot open is left for the indexer to report properly rather than silently
    dropped.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    for pattern in _IDENTIFIABLE_SECRET_PATTERNS:
        if pattern.search(text):
            return True

    for pattern in (_QUOTED_SECRET_ASSIGNMENT_RE, _ENV_SECRET_ASSIGNMENT_RE):
        for match in pattern.finditer(text):
            name = match.group("name")
            if not _SECRET_NAME_RE.search(name):
                continue
            if _NOT_THE_SECRET_NAME_RE.search(name):
                continue
            value = match.group("value").strip().rstrip(_VALUE_TRAILING_PUNCTUATION)
            if len(value) < _MIN_SECRET_VALUE_LEN:
                continue
            if _is_placeholder(value) or _is_prose(value):
                continue
            return True

    return False


def exclusion_reason(path) -> str | None:
    """Why this one file must not be indexed, or None if it may be.

    Every rule that can be decided from a single file lives here, so both entry
    points into the index apply the same set. They did not before: scan_project
    held the full set and reindex_file, the per edit path, carried a reduced
    copy that checked only the extension and the size. An appsettings.json that
    scan_project refuses was therefore indexed anyway the moment somebody edited
    it, which is the same credential exposure SKIP_NAME_GLOBS was added to close,
    reached through the more common of the two paths.

    Directory level rules (SKIP_DIRS, virtualenv roots, gitignore) are not here.
    They need the walk that scan_project does and cannot be answered from one
    path in isolation.

    Ordered cheapest first: name, then extension, then a stat, then the two
    checks that read the file.
    """
    path = Path(path)
    if path.name in SKIP_FILES:
        return f"{path.name} is a generated file"
    if any(path.name.endswith(s) for s in SKIP_SUFFIXES):
        return f"{path.name} has a generated file suffix"
    # Lowercased because Windows is case insensitive about filenames and
    # fnmatch is not: `AppSettings.json` is the same file on this platform
    # and must not slip past a lowercase glob.
    if any(fnmatch(path.name.lower(), g) for g in SKIP_NAME_GLOBS):
        return f"{path.name} is a config file that carries credentials"
    suffix = path.suffix.lower()
    if suffix not in CODE_EXTENSIONS:
        return f"Extension {suffix} not indexable"
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return "File too large"
    except OSError as e:
        return f"Cannot stat {path}: {e}"
    if looks_binary(path):
        return f"{path.name} is binary"
    if looks_like_secret(path):
        return f"{path.name} contains what looks like a live credential"
    return None


def scan_project(project_path: str) -> list:
    """Scan a project directory for indexable source files.

    Returns a list of absolute file paths.
    """
    root = Path(project_path).resolve()
    venv_roots = _venv_roots(root)
    files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # A file inside any virtualenv is a dependency, not project source.
        if any(vr in path.parents for vr in venv_roots):
            continue
        rel = path.relative_to(root)
        # Skip directories in SKIP_DIRS
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        reason = exclusion_reason(path)
        if reason is not None:
            logger.debug("Skipping %s: %s", rel, reason)
            continue
        files.append(str(path))

    return sorted(_drop_ignored(root, files))
