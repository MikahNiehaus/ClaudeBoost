# ClaudeBoost Coding Patterns

## Hook Script Pattern

Every hook script follows this structure:

```python
"""Module docstring explaining what it guards, exit codes, and blocked patterns."""
from __future__ import annotations
import json, sys
from pathlib import Path

def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input") or {}
    # ... logic ...
    return 0  # or 2 to block

if __name__ == "__main__":
    sys.exit(main())
```

Never use print() for block messages — always write to `sys.stderr`.
Exit 0 = pass. Exit 2 = hard block. Exit 1 = non-blocking warning (rare).

## Test Pattern

Tests live in `scripts/tests/`. Each test file covers one hook script.

```python
from helpers import run_hook, pretooluse, posttooluse, SCRIPTS_DIR

def test_passes_happy_path(boost_home):
    result = run_hook("my-guard.py", pretooluse("Read", {"file_path": "/safe.py"}),
                      env_overrides={"CLAUDEBOOST_HOME": str(boost_home)})
    assert result.returncode == 0

def test_blocks_bad_input():
    result = run_hook("my-guard.py", pretooluse("Read", {"file_path": "/bad.py"}))
    assert result.returncode == 2
    assert b"BLOCKED" in result.stderr
```

Always test both pass and block paths. Use `boost_home` fixture for any test that
reads state files. Use `rag_live`/`rag_dead` fixtures when testing RAG-gated logic.

## RAG Heartbeat Check Pattern

Scripts that behave differently when RAG is online vs offline use `_rag_is_live()`:

```python
def _rag_is_live() -> bool:
    rag_index_dir = os.environ.get("RAG_INDEX_DIR", "")
    if not rag_index_dir:
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            rag_index_dir = str(Path(local_appdata) / "rag-server-index")
        else:
            rag_index_dir = str(Path(__file__).resolve().parent.parent / "mcp-rag-server" / ".rag-index")
    heartbeat = Path(rag_index_dir) / ".heartbeat"
    if not heartbeat.exists():
        return False
    try:
        raw = heartbeat.read_text(encoding="utf-8").strip()
        data = json.loads(raw)
        return time.time() - float(data.get("ts", 0)) <= 90
    except Exception:
        return False
```

Key: if RAG is offline, guards MUST return 0 (allow). Never block when RAG is down.

## Behavior Tracker Pattern

Scripts that need to track event counts use `state/behavior-tracker.json`:

```python
home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
tracker_path = home / "state" / "behavior-tracker.json"
try:
    behavior = json.loads(tracker_path.read_text(encoding="utf-8"))
except Exception:
    behavior = {}
count = behavior.get("reads_since_rag", 0)
```

Write-back: update the dict and write back atomically.

## Python Script Instead of python -c

Never use `python -c "..."` for multi-line code in Bash commands. The bash-guard
blocks it. Write a file to `C:/Users/grayw/AppData/Local/Temp/cb_script.py` and
run `python "C:/Users/grayw/AppData/Local/Temp/cb_script.py"` instead.

## Exemption Pattern in Guards

Guards that should allow certain file types without blocking:

```python
EXEMPTED_SUFFIXES = {".json", ".lock", ".env", ".toml", ".yaml", ".yml"}
EXEMPTED_FRAGMENTS = {"context.md", "settings", "memory", "package", "pyproject"}

def is_exempted(tool_input: dict) -> bool:
    path = str(tool_input.get("file_path", "")).lower()
    if any(frag in path for frag in EXEMPTED_FRAGMENTS):
        return True
    if Path(path).suffix in EXEMPTED_SUFFIXES:
        return True
    return False
```

Always check exemptions before any blocking logic.

## State File Convention

State files live in `state/` as JSON. Always handle missing/corrupt files gracefully:

```python
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {}  # default, never crash
```

Never write state files from within a test — use `boost_home` fixture (tmp_path).
