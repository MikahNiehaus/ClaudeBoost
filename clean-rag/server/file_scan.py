"""Project file selection for clean-rag: what counts as indexable source.

Extracted from indexing.py so the isolated GraphRAG venv can reuse the exact same
hardened skip rules without importing indexing.py (which pulls chromadb and the
embedding stack). Pathlib only, no heavy deps, importable from anywhere.

The skip rules matter: measured on ClaudeBoost, without the virtualenv and
site packages skips a single venv leaked 9330 of 9721 scanned files into the index.
With them, the same tree scans to 391 real source files.
"""

from pathlib import Path

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
    ".html", ".css", ".scss", ".less", ".vue", ".svelte",
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
        # Skip directories in SKIP_DIRS
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if any(path.name.endswith(s) for s in SKIP_SUFFIXES):
            continue
        if path.suffix.lower() not in CODE_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue
        files.append(str(path))

    return sorted(files)
