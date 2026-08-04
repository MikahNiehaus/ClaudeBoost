#!/usr/bin/env python
"""PostToolUse hook: lint nudge after code writes.

Fires after Write/Edit/MultiEdit on code files. Detects language, runs the
appropriate linter, auto fixes where possible, reports residual issues to
stderr so the model sees them and can act.

This is a nudge, not a gate. It always exits 0. The model sees the issues
via stderr and can choose to address them.

Exit codes: 0 always. PostToolUse hooks never block.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".mm",
    ".sh", ".bash", ".ps1", ".sql", ".vue", ".svelte",
}

EXEMPT_SEGMENTS = {
    "workspace", "state", "plans", "docs", "node_modules",
    ".claude", ".claudeboost", ".git", "__pycache__", "scratchpad",
}

LINT_TIMEOUT = 30


def _is_exempt(file_path):
    if not file_path:
        return True
    path = Path(file_path)
    if path.suffix.lower() not in CODE_EXTENSIONS:
        return True
    parts = {p.lower() for p in path.parts}
    if parts & EXEMPT_SEGMENTS:
        return True
    return False


def _find_project_root(file_path):
    """Walk up to find the project root (has package.json or pyproject.toml)."""
    current = Path(file_path).resolve().parent
    for _ in range(20):
        if (current / "package.json").exists() or (current / "pyproject.toml").exists():
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return str(Path(file_path).resolve().parent)


def _lint_python(file_path):
    """Run ruff on a Python file. Auto fix first, then report residuals."""
    ruff = shutil.which("ruff")
    if not ruff:
        return

    # Auto fix pass
    try:
        subprocess.run(
            [ruff, "check", "--fix", file_path],
            shell=False, capture_output=True, text=True,
            timeout=LINT_TIMEOUT, errors="replace",
        )
    except Exception:
        pass

    # Check for residual issues
    try:
        proc = subprocess.run(
            [ruff, "check", file_path],
            shell=False, capture_output=True, text=True,
            timeout=LINT_TIMEOUT, errors="replace",
        )
    except Exception:
        return

    output = (proc.stdout or "").strip()
    if proc.returncode != 0 and output:
        print(f"[lint-gate] ruff found issues in {file_path}:\n{output}", file=sys.stderr)


def _lint_js(file_path):
    """Run eslint on a JS/TS file if eslint config exists."""
    project_root = _find_project_root(file_path)

    # Only run if an eslint config exists in the project
    config_patterns = [
        ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
        ".eslintrc.yml", ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs",
        "eslint.config.cjs",
    ]
    has_config = any((Path(project_root) / c).exists() for c in config_patterns)
    if not has_config:
        return

    # Prefer local eslint over global
    local_eslint = Path(project_root) / "node_modules" / ".bin" / "eslint"
    if local_eslint.exists():
        eslint = str(local_eslint)
    else:
        eslint = shutil.which("eslint")
    if not eslint:
        return

    try:
        proc = subprocess.run(
            [eslint, file_path],
            shell=False, capture_output=True, text=True,
            timeout=LINT_TIMEOUT, cwd=project_root, errors="replace",
        )
    except Exception:
        return

    output = (proc.stdout or "").strip()
    if proc.returncode != 0 and output:
        print(f"[lint-gate] eslint found issues in {file_path}:\n{output}", file=sys.stderr)


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if _is_exempt(file_path):
        return 0

    ext = Path(file_path).suffix.lower()

    if ext == ".py":
        _lint_python(file_path)
    elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        _lint_js(file_path)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
