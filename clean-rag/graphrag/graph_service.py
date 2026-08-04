"""The GraphRAG build and query service. Runs in the isolated graphrag-venv.

fast-graphrag cannot share the main clean-rag environment (it is locked out of
hnswlib by the running ChromaDB and rewrites shared deps), and its persisted store
cannot be read by the main server anyway (a gzipped igraph pickle plus an hnswlib
binary index, both needing those packages to deserialize). So it lives here, in its
own venv and process, and the main server reads it over HTTP. Confirmed by research.

What it does:
  - build:  scan a project with the SAME hardened file_scan the main index uses,
            insert files in small batches (a "layer" at a time) with a resumable
            percent progress, into a fresh build-<ts> dir, then atomically flip a
            manifest, then unload the model so it does not sit idle in VRAM.
  - query:  load the active build and answer, reloading only when the manifest
            version changes so a reader never sees a half written graph.

Grounded facts (from fast-graphrag source and Ollama docs):
  - insert() takes a List[str] + metadata list, persists directly under working_dir,
    and dedups by content hash chunk id, so resume is just re-running the batch loop.
  - n_checkpoints stays 0 so fast-graphrag's own versioning does not collide with
    our build-<ts> + manifest scheme.
  - keep_alive is ignored over the OpenAI /v1 surface, so unload is a separate
    native POST /api/generate {"keep_alive": 0}.
  - os.replace is atomic on Windows for a same directory rename.

Manual only. Nothing here auto triggers a build. Stdlib http.server, no web dep.
"""

import importlib.util
import json
import os
import shutil
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import instructor
from fast_graphrag import GraphRAG
from fast_graphrag._llm import OpenAIEmbeddingService, OpenAILLMService

# ---- config (env overridable) --------------------------------------------------
CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
OLLAMA_BASE = os.environ.get("GRAPHRAG_OLLAMA_BASE", "http://localhost:11434")
LLM_MODEL = os.environ.get("GRAPHRAG_LLM_MODEL", "qwen2.5:7b-instruct")
EMBED_MODEL = os.environ.get("GRAPHRAG_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.environ.get("GRAPHRAG_EMBED_DIM", "768"))
PORT = int(os.environ.get("GRAPHRAG_PORT", "8614"))
BATCH_SIZE = int(os.environ.get("GRAPHRAG_BATCH", "20"))
KEEP_BUILDS = 2  # keep the last N build dirs, never delete the active one

DOMAIN = ("A software project: its modules, classes, functions, and how they "
          "import, call, and depend on one another, plus what each is for.")
ENTITY_TYPES = ["Module", "Class", "Function", "Concept", "Config", "Endpoint"]
EXAMPLE_QUERIES = [
    "What calls this function?",
    "How does module A depend on module B?",
    "Where is X defined and what uses it?",
    "What would break if this changed?",
]

_build_lock = threading.Lock()
_query_lock = threading.Lock()
_active_graph = {"key": None, "grag": None}


def _scan_project(project_path):
    """The main index's hardened file selection, loaded without its heavy deps."""
    fs_path = CLEAN_RAG_HOME / "server" / "file_scan.py"
    spec = importlib.util.spec_from_file_location("_file_scan", str(fs_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.scan_project(project_path)


def _project_dir(project_path):
    """Where this project's graphrag data lives. Resolve only, never create.

    project_id.py is stdlib only, so it imports fine in this isolated venv
    even though most of server/ does not. Sharing it is the point: this
    directory name has to match what the main server computes or the two
    write to different places for the same project.

    There is deliberately no fallback name. The only way this import fails is
    a CLEAN_RAG_HOME that is not a clean-rag checkout, and then projects_root
    below is wrong too, so a locally computed name would name a directory the
    main server never reads: a second, invisible store for the project, which
    is the exact split project_id.py exists to end. Guessing is worse than
    stopping ("errors should never pass silently... refuse the temptation to
    guess", PEP 20), so this raises with the path to fix.

    Creating the directory is build_graph's job, the only writer. A status or
    query call for a project that was never built leaves nothing behind.
    """
    if str(CLEAN_RAG_HOME) not in sys.path:
        sys.path.insert(0, str(CLEAN_RAG_HOME))
    try:
        from server.project_id import resolve_project_dir
    except ImportError as e:
        raise RuntimeError(
            f"cannot import server.project_id from CLEAN_RAG_HOME={CLEAN_RAG_HOME}; "
            "point CLEAN_RAG_HOME at the clean-rag checkout"
        ) from e
    projects_root = CLEAN_RAG_HOME / "databases" / "_projects"
    return resolve_project_dir(projects_root, project_path) / "graphrag"


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json_atomic(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # atomic same directory rename, safe on Windows


def _make_grag(working_dir):
    return GraphRAG(
        working_dir=str(working_dir),
        domain=DOMAIN,
        example_queries="\n".join(EXAMPLE_QUERIES),
        entity_types=ENTITY_TYPES,
        config=GraphRAG.Config(
            llm_service=OpenAILLMService(
                model=LLM_MODEL, base_url=f"{OLLAMA_BASE}/v1", api_key="ollama",
                mode=instructor.Mode.JSON, client="openai",
            ),
            embedding_service=OpenAIEmbeddingService(
                model=EMBED_MODEL, base_url=f"{OLLAMA_BASE}/v1", api_key="ollama",
                embedding_dim=EMBED_DIM, client="openai",
            ),
        ),
    )


def _unload_models():
    """Free the models from VRAM. keep_alive is ignored over /v1, so hit the native
    api with keep_alive 0, which unloads immediately."""
    for model in (LLM_MODEL, EMBED_MODEL):
        try:
            body = json.dumps({"model": model, "keep_alive": 0}).encode("utf-8")
            req = urllib.request.Request(
                f"{OLLAMA_BASE}/api/generate", data=body,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            urllib.request.urlopen(req, timeout=30).read()
        except Exception:  # noqa: BLE001
            pass  # unload is best effort; a failure just means it idles out later


def _read_file(path, cap=200_000):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    text = text.strip()
    return text[:cap] if text else None


def _prune_builds(pdir, active_version):
    builds = sorted(pdir.glob("build-*"), key=lambda p: p.name)
    for b in builds[:-KEEP_BUILDS]:
        if b.name == f"build-{active_version}":
            continue
        shutil.rmtree(b, ignore_errors=True)


def build_graph(project_path):
    """Build (or resume) the graph for a project. Blocking; run it in a thread."""
    # Resolved before the lock: _project_dir raises on a broken CLEAN_RAG_HOME
    # and there is no lock to leak yet if it does.
    pdir = _project_dir(project_path)
    # Pure path arithmetic, cannot raise, and the except clause below writes to
    # it, so it has to be bound before the try or a failing mkdir surfaces as
    # UnboundLocalError instead of the real error.
    prog = pdir / "progress.json"
    if not _build_lock.acquire(blocking=False):
        return {"error": "a build is already running"}
    # Nothing goes between the acquire and the try. Anything that raises here
    # leaves the lock held forever and every later build is refused until the
    # process restarts. mkdir sat here and did exactly that. This is the shape
    # the threading docs give as the equivalent of `with lock:`.
    try:
        pdir.mkdir(parents=True, exist_ok=True)  # the only writer creates it
        files = _scan_project(project_path)
        total = len(files)
        if total == 0:
            _write_json_atomic(prog, {"building": False, "error": "no source files found",
                                      "files_total": 0, "files_done": 0, "percent": 0})
            return {"error": "no source files found"}

        # Resume an unfinished build, or start a fresh one.
        prev = _read_json(prog, {}) or {}
        if prev.get("building") and prev.get("build_dir") and Path(prev["build_dir"]).is_dir():
            build_dir = Path(prev["build_dir"])
            start = int(prev.get("files_done", 0))
            version = build_dir.name.replace("build-", "")
        else:
            version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            build_dir = pdir / f"build-{version}"
            build_dir.mkdir(parents=True, exist_ok=True)
            start = 0

        _write_json_atomic(prog, {"building": True, "build_dir": str(build_dir),
                                  "files_total": total, "files_done": start,
                                  "percent": round(100 * start / total), "error": None})

        grag = _make_grag(build_dir)
        i = start
        while i < total:
            contents, metas = [], []
            for p in files[i:i + BATCH_SIZE]:
                c = _read_file(p)
                if c:
                    contents.append(c)
                    metas.append({"path": p})
            if contents:
                # Re-inserting an already processed file is a cheap no-op (content
                # hash dedup), which is what makes a killed run resumable.
                grag.insert(contents, metadata=metas)
            i = min(i + BATCH_SIZE, total)
            _write_json_atomic(prog, {"building": True, "build_dir": str(build_dir),
                                      "files_total": total, "files_done": i,
                                      "percent": round(100 * i / total), "error": None})

        # Build finished: flip the manifest so readers switch to this version.
        _write_json_atomic(pdir / "manifest.json", {"active_version": version,
                                                    "built_at": time.time(), "files": total})
        _write_json_atomic(prog, {"building": False, "build_dir": str(build_dir),
                                  "files_total": total, "files_done": total,
                                  "percent": 100, "error": None})
        _prune_builds(pdir, version)
        _unload_models()  # do not sit in VRAM after an overnight build
        return {"ok": True, "version": version, "files": total}

    except Exception as e:  # noqa: BLE001
        _write_json_atomic(prog, {"building": False, "error": f"{type(e).__name__}: {e}",
                                  "trace": traceback.format_exc()[-1500:]})
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        _build_lock.release()


def _active_build_dir(project_path):
    pdir = _project_dir(project_path)
    man = _read_json(pdir / "manifest.json", {}) or {}
    version = man.get("active_version")
    if not version:
        return None, None
    bdir = pdir / f"build-{version}"
    return (bdir, version) if bdir.is_dir() else (None, None)


def query_graph(project_path, query):
    bdir, version = _active_build_dir(project_path)
    if not bdir:
        return {"error": "no built graph for this project yet; run a build first"}
    with _query_lock:
        if _active_graph["key"] != str(bdir):
            _active_graph["grag"] = _make_grag(bdir)
            _active_graph["key"] = str(bdir)
        grag = _active_graph["grag"]
    try:
        r = grag.query(query)
        return {"answer": str(r.response), "version": version, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def status(project_path):
    pdir = _project_dir(project_path)
    prog = _read_json(pdir / "progress.json", {}) or {}
    man = _read_json(pdir / "manifest.json", {}) or {}
    return {
        "building": bool(prog.get("building")),
        "percent": prog.get("percent", 0),
        "files_done": prog.get("files_done", 0),
        "files_total": prog.get("files_total", 0),
        "active_version": man.get("active_version"),
        "error": prog.get("error"),
    }


# ---- HTTP ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send({"ok": True})
        if self.path.startswith("/status"):
            pp = (parse_qs(urlparse(self.path).query).get("project_path") or [""])[0]
            if not pp:
                return self._send({"error": "project_path query param required"}, 400)
            return self._send(status(pp))
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        body = self._body()
        pp = (body.get("project_path") or "").strip()
        if self.path.startswith("/build"):
            if not pp:
                return self._send({"error": "project_path required"}, 400)
            if _build_lock.locked():
                return self._send({"error": "a build is already running", "status": status(pp)}, 409)
            threading.Thread(target=build_graph, args=(pp,), daemon=True).start()
            return self._send({"started": True, "project_path": pp})
        if self.path.startswith("/query"):
            q = (body.get("query") or "").strip()
            if not pp or not q:
                return self._send({"error": "project_path and query required"}, 400)
            return self._send(query_graph(pp, q))
        self._send({"error": "not found"}, 404)


def main():
    print(f"GraphRAG service on http://127.0.0.1:{PORT}  (model {LLM_MODEL} via {OLLAMA_BASE})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
