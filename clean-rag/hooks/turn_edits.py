"""Track the files an Edit or Write actually touched this session.

The Stop gates (auto-test-gate, verifier-gate) used git relative to the session
cwd to find changed code. That silently does nothing when the cwd is not a git
repo, or when the edits land in a different repo than the cwd, which is exactly
what happened, and why the gates never fired all session. This records the file
each edit touched, so the gates look at where the work went, not at the cwd.

Pathlib and subprocess only, no heavy deps, and it never raises: a broken tracker
must not break a hook.
"""

import hashlib
import os
import subprocess
from pathlib import Path

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".mm",
    ".sh", ".bash", ".ps1", ".sql", ".vue", ".svelte",
}


def _home() -> Path:
    return Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)


def _path(session_id: str) -> Path:
    key = hashlib.sha256((session_id or "no-session").encode("utf-8")).hexdigest()[:16]
    d = _home() / "state" / "turn-edits"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.txt"


def record_edit(session_id: str, file_path: str) -> None:
    """Append an edited code file's absolute path to this session's list."""
    if not file_path:
        return
    try:
        if Path(file_path).suffix.lower() not in CODE_EXTENSIONS:
            return
        with open(_path(session_id), "a", encoding="utf-8") as f:
            f.write(str(Path(file_path).resolve()) + "\n")
    except OSError:
        pass


def edited_code_files(session_id: str) -> list:
    """The distinct code files edited this session that still exist on disk."""
    try:
        lines = _path(session_id).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    seen, out = set(), []
    for ln in lines:
        p = ln.strip()
        if p and p not in seen and Path(p).is_file():
            seen.add(p)
            out.append(p)
    return out


def git_root(path: str):
    """The git top level containing path, or None if it is not in a repo."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(Path(path).resolve().parent),
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    root = r.stdout.strip()
    return root or None
