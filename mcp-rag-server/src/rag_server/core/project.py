"""Project identification, index paths, and file discovery."""

import hashlib
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories to always skip when discovering source files
DEFAULT_EXCLUDES = {
    "node_modules", ".git", "dist", "build", "vendor", "__pycache__",
    ".venv", "venv", ".tox", ".mypy_cache", ".next", "coverage",
    ".pytest_cache", ".ruff_cache", "target", "bin", "obj",
    ".rag-index", ".claude", "packages", ".nuget",
}

# Language name -> file extensions
LANGUAGE_EXTENSIONS = {
    "python":     {".py"},
    "javascript": {".js", ".jsx", ".mjs"},
    "typescript": {".ts", ".tsx"},
    "csharp":     {".cs"},
    "go":         {".go"},
    "rust":       {".rs"},
    "java":       {".java"},
    "c":          {".c", ".h"},
    "cpp":        {".cpp", ".cc", ".cxx", ".hpp"},
    "ruby":       {".rb"},
    "bash":       {".sh", ".bash"},
    "lua":        {".lua"},
    "kotlin":     {".kt", ".kts"},
    "swift":      {".swift"},
    "php":        {".php"},
    "css":        {".css", ".scss"},
    "html":       {".html", ".htm"},
    "cshtml":     {".cshtml", ".razor"},
    "json":       {".json"},
    "toml":       {".toml"},
    "yaml":       {".yaml", ".yml"},
    # Document formats — chunked via markdown/pdf pipeline, not code chunker
    "markdown":   {".md", ".mdx"},
    "rst":        {".rst"},
    "text":       {".txt"},
    "pdf":        {".pdf"},
}

# Reverse lookup: extension -> language name
_EXT_TO_LANGUAGE = {}
for lang, exts in LANGUAGE_EXTENSIONS.items():
    for ext in exts:
        _EXT_TO_LANGUAGE[ext] = lang

# All supported code extensions
ALL_CODE_EXTENSIONS = set()
for exts in LANGUAGE_EXTENSIONS.values():
    ALL_CODE_EXTENSIONS |= exts


def project_id(project_path: str) -> str:
    """Stable 12-char hex ID for a project, based on git remote or absolute path."""
    identity = _git_remote_url(project_path) or str(Path(project_path).resolve())
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]


def project_index_dir(project_path: str) -> Path:
    """Return the index directory for a project — stored inside the project's workspace."""
    return Path(project_path).resolve() / "workspace" / ".rag-index"


def load_ragignore(project_path: str) -> set[str]:
    """Read .ragignore from the project root and return a set of directory names to skip.

    Syntax (same philosophy as .gitignore, but directory-names only for now):
      - Lines starting with # are comments
      - Trailing slash is optional and ignored (e.g. "myproject/" == "myproject")
      - Blank lines are ignored
      - Each entry is matched against directory *names* during os.walk (not full paths)
    """
    ragignore = Path(project_path).resolve() / ".ragignore"
    extras: set[str] = set()
    if not ragignore.exists():
        return extras
    for line in ragignore.read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip("/")
        if line and not line.startswith("#"):
            extras.add(line)
    if extras:
        logger.info(".ragignore: excluding directories %s", sorted(extras))
    return extras


def discover_files(
    project_path: str,
    languages: list[str] | None = None,
    excludes: set[str] | None = None,
) -> list[str]:
    """Walk project directory and return source file paths matching language filters.

    Args:
        project_path: Root directory of the target project.
        languages: Optional list of language names to filter (e.g., ["python", "typescript"]).
                   None means all supported languages.
        excludes: Directory names to skip. Defaults to DEFAULT_EXCLUDES merged with .ragignore.

    Returns:
        List of absolute file paths.
    """
    if excludes is None:
        excludes = DEFAULT_EXCLUDES | load_ragignore(project_path)
    else:
        excludes = excludes | load_ragignore(project_path)

    # Resolve which extensions to look for
    if languages:
        target_exts = set()
        for lang in languages:
            lang_lower = lang.lower()
            if lang_lower in LANGUAGE_EXTENSIONS:
                target_exts |= LANGUAGE_EXTENSIONS[lang_lower]
            else:
                logger.warning("Unknown language filter: %s", lang)
    else:
        target_exts = ALL_CODE_EXTENSIONS

    root = Path(project_path).resolve()
    files = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if d not in excludes]

        for fname in filenames:
            if Path(fname).suffix in target_exts:
                files.append(str(Path(dirpath) / fname))

    logger.info("Discovered %d source files in %s", len(files), project_path)
    return files


def extension_to_language(ext: str) -> str | None:
    """Map a file extension to its language name."""
    return _EXT_TO_LANGUAGE.get(ext)


def git_head(project_path: str) -> str | None:
    """Get current git HEAD SHA, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _git_remote_url(project_path: str) -> str | None:
    """Get the git remote origin URL, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None
