"""bad-cop adversarial: load_progress() narrows its except clause to
(OSError, json.JSONDecodeError), added this round to stop a corrupt progress
file from being swallowed silently. UnicodeDecodeError is a subclass of
ValueError, not OSError, so Path.read_text(encoding="utf-8") raising it on a
progress file with invalid UTF-8 bytes is not caught by that tuple at all: it
propagates out of load_progress() uncaught, crashing run()/main() instead of
falling back to a fresh start with the intended log line.

A real corruption path that produces exactly this: reindex-progress.json
records project paths (state["done"][pid]["path"]), and a path with a
non-ASCII character (a real, plausible directory name) combined with a write
truncated mid multi-byte sequence, e.g. an ungraceful kill of the process
between save_progress()'s write_text calls, leaves a file with a cut UTF-8
sequence at the end, not necessarily invalid JSON syntax at all.
"""
import importlib.util
import sys
from pathlib import Path

CLEAN_RAG = Path("C:/Development/ClaudeBoost/clean-rag")
sys.path.insert(0, str(CLEAN_RAG))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_load_progress_survives_a_non_utf8_progress_file(tmp_path):
    mod = _load_module("reindex_batch_encoding_test", CLEAN_RAG / "cli" / "reindex_batch.py")
    mod.STATE_DIR = tmp_path
    mod.PROGRESS = tmp_path / "reindex-progress.json"
    # A lone continuation byte: not valid UTF-8 at all, the kind of corruption
    # a crashed write or a truncated multi-byte character actually produces.
    mod.PROGRESS.write_bytes(b"\xff\xfe\x00\x80{not even close to json")

    result = mod.load_progress()

    assert result == {"done": {}, "failed": {}}, (
        "load_progress must fall back to a fresh state on any unreadable "
        f"progress file, got {result!r}"
    )
