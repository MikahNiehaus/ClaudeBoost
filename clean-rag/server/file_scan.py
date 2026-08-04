"""Project file selection for clean-rag: what counts as indexable source.

Extracted from indexing.py so the isolated GraphRAG venv can reuse the exact same
hardened skip rules without importing indexing.py (which pulls chromadb and the
embedding stack). Pathlib only, no heavy deps, importable from anywhere.

The skip rules matter: measured on ClaudeBoost, without the virtualenv and
site packages skips a single venv leaked 9330 of 9721 scanned files into the index.
With them, the same tree scans to 391 real source files.
"""

import logging
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
        if path.name in SKIP_FILES:
            continue
        if any(path.name.endswith(s) for s in SKIP_SUFFIXES):
            continue
        # Lowercased because Windows is case insensitive about filenames and
        # fnmatch is not: `AppSettings.json` is the same file on this platform
        # and must not slip past a lowercase glob.
        if any(fnmatch(path.name.lower(), g) for g in SKIP_NAME_GLOBS):
            continue
        if path.suffix.lower() not in CODE_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue
        if looks_binary(path):
            continue
        files.append(str(path))

    return sorted(_drop_ignored(root, files))
