#!/usr/bin/env python3
"""Persistent zero-shot query classifier server.

Runs under .venv-router (isolated venv: torch CPU + transformers), never
the shared Python environment the main clean-rag server and other projects
use — confirmed this session that installing torch/transformers in the
shared environment breaks open-webui's pinned pyarrow==20.0.0.

Loads MoritzLaurer/deberta-v3-large-zeroshot-v2.0 once at startup and
keeps it warm, so classification calls cost ~0.3-1.5s (measured this
session) instead of the ~5s cold-load cost of spawning a fresh subprocess
per call. Exposes a small HTTP API the main clean-rag server and hooks
call into, matching the existing "part of the same system, isolated
dependencies" pattern used for other clean-rag pieces this session.

Start:  .venv-router/Scripts/python.exe server/classifier_server.py
Port:   8614 (env: CLEAN_RAG_CLASSIFIER_PORT)

Endpoints:
  GET  /health              -> {"status": "ready"|"loading"}
  POST /classify {"text": "..."} -> {"label": "...", "score": 0.0, "all_scores": {...}}
"""

import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LABELS = ["programming or coding", "small talk", "explaining how a tool works"]
MODEL_NAME = "MoritzLaurer/deberta-v3-large-zeroshot-v2.0"
PORT = int(os.environ.get("CLEAN_RAG_CLASSIFIER_PORT", "8614"))

_classifier = None
_load_error = None
_ready = threading.Event()


def _load_model() -> None:
    """Load the model once, in a background thread, so the server can
    answer /health immediately instead of blocking startup.
    """
    global _classifier, _load_error
    try:
        from transformers import pipeline

        logger.info(f"Loading {MODEL_NAME} (CPU)...")
        _classifier = pipeline("zero-shot-classification", model=MODEL_NAME, device=-1)
        logger.info("Model loaded, server ready")
    except Exception as e:
        _load_error = f"{type(e).__name__}: {e}"
        logger.error(f"Model load failed: {_load_error}")
    finally:
        _ready.set()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info("%s - %s" % (self.address_string(), format % args))

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            if not _ready.is_set():
                self._send_json(200, {"status": "loading"})
            elif _load_error:
                self._send_json(503, {"status": "error", "error": _load_error})
            else:
                self._send_json(200, {"status": "ready"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/classify":
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception as e:
            self._send_json(400, {"error": f"bad JSON: {e}"})
            return

        text = body.get("text", "")
        if not text:
            self._send_json(400, {"error": "empty text"})
            return

        if not _ready.is_set():
            self._send_json(503, {"error": "model still loading"})
            return
        if _load_error:
            self._send_json(503, {"error": f"model failed to load: {_load_error}"})
            return

        try:
            result = _classifier(text, LABELS)
            self._send_json(200, {
                "label": result["labels"][0],
                "score": result["scores"][0],
                "all_scores": dict(zip(result["labels"], result["scores"])),
                "error": None,
            })
        except Exception as e:
            logger.error(f"Classification failed: {type(e).__name__}: {e}")
            self._send_json(500, {"error": f"{type(e).__name__}: {e}"})


def main() -> int:
    threading.Thread(target=_load_model, daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    logger.info(f"Classifier server listening on port {PORT} (model loading in background)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
