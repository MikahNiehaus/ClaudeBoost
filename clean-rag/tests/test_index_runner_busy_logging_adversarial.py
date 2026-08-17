"""_index_project_runner.py is spawned with stdout and stderr both sent to
DEVNULL by rag-enforce.py, so state/index-runner.log is the only channel
that survives. This tests that a 423 (index lock busy) and a 500 (server
error) each write a distinguishable, durable line, that the process exits
non zero on both, and that _log() itself can never be the reason indexing
reports a failure.

Runs the real runner as a subprocess against a local stub HTTP server the
test controls, never against the real clean-rag server on 8613.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
RUNNER = CLEAN_RAG / "hooks" / "_index_project_runner.py"


def _make_handler(status_code: int, body: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    return Handler


@pytest.fixture()
def stub_server():
    """A local HTTP server on an unused port, never the real 8613 server."""
    servers = []

    def start(status_code: int, body: dict) -> int:
        server = HTTPServer(("127.0.0.1", 0), _make_handler(status_code, body))
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return port

    yield start
    for s in servers:
        s.shutdown()


def _run_runner(project_path: Path, port: int, home: Path):
    env = dict(os.environ)
    env["CLEAN_RAG_HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(RUNNER), str(project_path), str(port)],
        capture_output=True, text=True, env=env, timeout=15,
    )


class TestBusyAndFailureAreDistinguishableAndDurable:
    def test_423_writes_a_busy_marker_and_exits_nonzero(self, tmp_path, stub_server):
        (tmp_path / "state").mkdir()
        port = stub_server(423, {"error": "index lock held"})
        proc = _run_runner(tmp_path / "someproject", port, tmp_path)

        assert proc.returncode != 0
        log = (tmp_path / "state" / "index-runner.log").read_text(encoding="utf-8")
        assert "BUSY" in log
        assert "423" in log

    def test_500_writes_a_fail_marker_distinguishable_from_busy(self, tmp_path, stub_server):
        (tmp_path / "state").mkdir()
        port = stub_server(500, {"error": "boom"})
        proc = _run_runner(tmp_path / "someproject", port, tmp_path)

        assert proc.returncode != 0
        log = (tmp_path / "state" / "index-runner.log").read_text(encoding="utf-8")
        assert "FAIL" in log
        assert "BUSY" not in log

    def test_success_writes_an_ok_marker_and_exits_zero(self, tmp_path, stub_server):
        (tmp_path / "state").mkdir()
        port = stub_server(200, {"status": "ok", "files_indexed": 42})
        proc = _run_runner(tmp_path / "someproject", port, tmp_path)

        assert proc.returncode == 0
        log = (tmp_path / "state" / "index-runner.log").read_text(encoding="utf-8")
        assert "OK" in log


class TestLogNeverRaises:
    """_log()'s own docstring says logging must never be the reason indexing
    reports a failure. Attack the two ways state/ can be unwritable."""

    def test_state_directory_blocked_by_a_same_named_file(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(CLEAN_RAG / "hooks"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "index_runner_log_test", str(RUNNER)
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        blocked_home = tmp_path / "blocked"
        blocked_home.mkdir()
        (blocked_home / "state").write_text("not a directory", encoding="utf-8")
        monkeypatch.setenv("CLEAN_RAG_HOME", str(blocked_home))

        mod._log("this must not raise even though state/ is a file")

    def test_illegal_path_characters_in_clean_rag_home(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(CLEAN_RAG / "hooks"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "index_runner_log_test2", str(RUNNER)
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        monkeypatch.setenv("CLEAN_RAG_HOME", "C:\\bad?name<>|path\\deep\\deeper")

        mod._log("this must not raise even with an unwritable/illegal path")
