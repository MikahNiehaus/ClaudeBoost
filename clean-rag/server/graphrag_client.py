"""Main clean-rag server's client to the isolated GraphRAG service (port 8614).

The graph service runs in its own venv (fast-graphrag cannot share this env), so the
main server talks to it over HTTP. If it is not up, we start it with the graphrag
venv python, the same lazy start the OpenCode MCP server uses for clean-rag itself.
Reading status never starts it; a build or query will.
"""

import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
GRAPHRAG_PORT = int(os.environ.get("GRAPHRAG_PORT", "8614"))
_BASE = f"http://127.0.0.1:{GRAPHRAG_PORT}"

# Serializes the on-demand launch so concurrent build/query calls don't each spawn
# a second graph_service (the loser just fails to bind 8614, but pops a console).
_launch_lock = threading.Lock()


def _venv_python():
    scripts = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return CLEAN_RAG_HOME / "graphrag-venv" / scripts / exe


def _reachable(timeout=2.0):
    try:
        with urllib.request.urlopen(f"{_BASE}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_service_up(timeout_s=30.0):
    if _reachable():
        return True
    py = _venv_python()
    script = CLEAN_RAG_HOME / "graphrag" / "graph_service.py"
    if not py.is_file() or not script.is_file():
        return False
    with _launch_lock:
        if _reachable():  # another thread won the race and started it
            return True
        return _launch_and_wait(py, script, timeout_s)


def _launch_and_wait(py, script, timeout_s):
    try:
        env = {**os.environ, "CLEAN_RAG_HOME": str(CLEAN_RAG_HOME)}
        env.setdefault("CONCURRENT_TASK_LIMIT", "4")  # gentle on a local model
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)  # headed, watchable
        else:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        subprocess.Popen([str(py), str(script)], env=env, **kwargs)
    except Exception:
        return False
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(1)
        if _reachable():
            return True
    return False


def _post(path, payload, timeout):
    if not _ensure_service_up():
        return {"error": "GraphRAG service is not available and could not be started. "
                         "Is the graphrag venv installed (install.py) and Ollama running?"}
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{_BASE}{path}", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": f"GraphRAG request failed: {e}"}


def build(project_path):
    """Kick off a build (returns immediately; poll status for progress)."""
    return _post("/build", {"project_path": project_path}, timeout=10)


def query(project_path, q):
    """Query the built graph. A query may reload the model, so give it room."""
    return _post("/query", {"project_path": project_path, "query": q}, timeout=180)


def status(project_path):
    """Progress and active version. Does not start the service, only reads it."""
    if not _reachable():
        return {"building": False, "active_version": None,
                "error": "GraphRAG service not running"}
    try:
        url = f"{_BASE}/status?project_path={quote(project_path)}"
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": f"GraphRAG status failed: {e}"}
