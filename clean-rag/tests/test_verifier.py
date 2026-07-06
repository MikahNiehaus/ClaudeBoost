"""Tests for the verifier module: prompt building and atomic proof writes."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from verifier.prompts import build_verification_prompt, format_rag_results  # noqa: E402
from verifier.log import write_pending_proof, read_proof_log  # noqa: E402


class TestVerificationPrompt:
    """The prompt template should produce well-formed verification requests."""

    def test_prompt_contains_all_fields(self):
        prompt = build_verification_prompt(
            file_path="src/main.py",
            proposed_change="Add logging",
            architecture_context="Flask app with structured logging",
            rag_results="score: 0.85 | topic: flask",
            justification="Flask docs show this pattern",
        )
        assert "src/main.py" in prompt
        assert "Add logging" in prompt
        assert "Flask app" in prompt
        assert "VERIFIED" in prompt
        assert "RESEARCH_MORE" in prompt
        assert "INSUFFICIENT" in prompt

    def test_score_threshold_is_0_5(self):
        prompt = build_verification_prompt(
            file_path="x.py",
            proposed_change="change",
            architecture_context="context",
            rag_results="results",
            justification="reason",
        )
        assert ">= 0.5" in prompt
        assert ">= 0.55" not in prompt


class TestFormatRagResults:
    """RAG results formatting for the prompt."""

    def test_empty_results(self):
        assert format_rag_results([]) == "(no results found)"

    def test_topic_result_formatting(self):
        results = [{"source_type": "topic", "score": 0.87, "topic": "fastapi",
                     "file": "deps.md", "content": "Use Depends()..."}]
        formatted = format_rag_results(results)
        assert "0.87" in formatted
        assert "fastapi" in formatted
        assert "deps.md" in formatted

    def test_project_result_formatting(self):
        results = [{"source_type": "project", "score": 0.72,
                     "file": "api/auth.py", "line_start": 23,
                     "content": "class AuthService..."}]
        formatted = format_rag_results(results)
        assert "project" in formatted
        assert "api/auth.py:23" in formatted


class TestAtomicProofWrite:
    """write_pending_proof must be atomic (no partial reads)."""

    def test_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_pending_proof(
                state_dir=tmpdir,
                file_path="src/main.py",
                verdict="VERIFIED",
                verifier_response="Proof is good",
                rag_results_count=3,
                topics_cited=["flask"],
                project_cited=True,
                content_hash="abc123",
                min_score=0.85,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["file"] == "src/main.py"
            assert data["verdict"] == "VERIFIED"
            assert data["verifier_response"] == "Proof is good"
            assert data["rag_results_count"] == 3
            assert data["topics_cited"] == ["flask"]
            assert data["project_cited"] is True
            assert data["ts"].endswith("Z")
            assert data["content_hash"] == "abc123"
            assert data["min_score"] == 0.85
            assert "file_canonical" in data

    def test_no_temp_files_left_behind(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            write_pending_proof(
                state_dir=tmpdir,
                file_path="x.py",
                verdict="VERIFIED",
                verifier_response="ok",
            )
            files = list(Path(tmpdir).iterdir())
            # Only keyed proof file should exist, no .tmp files
            names = [f.name for f in files]
            assert any(n.startswith("pending-proof-") and n.endswith(".json") for n in names)
            assert not any(n.endswith(".tmp") for n in names)

    def test_keyed_files_for_different_paths(self):
        """Different file paths produce different proof files (concurrent support)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = write_pending_proof(tmpdir, "a.py", "VERIFIED", "first")
            path_b = write_pending_proof(tmpdir, "b.py", "VERIFIED", "second")
            # Different keyed files, both should exist
            assert path_a != path_b
            assert path_a.exists()
            assert path_b.exists()
            data_a = json.loads(path_a.read_text(encoding="utf-8"))
            data_b = json.loads(path_b.read_text(encoding="utf-8"))
            assert data_a["file"] == "a.py"
            assert data_b["file"] == "b.py"

    def test_same_path_overwrites(self):
        """Same file path overwrites the keyed proof file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            write_pending_proof(tmpdir, "a.py", "VERIFIED", "first")
            path = write_pending_proof(tmpdir, "a.py", "VERIFIED", "second")
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["verifier_response"] == "second"


class TestProofLog:
    """read_proof_log returns entries newest-first."""

    def test_empty_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert read_proof_log(tmpdir) == []

    def test_reads_entries_newest_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "proof-log.jsonl"
            entries = [
                {"ts": "2026-01-01T00:00:00Z", "file": "a.py"},
                {"ts": "2026-01-02T00:00:00Z", "file": "b.py"},
                {"ts": "2026-01-03T00:00:00Z", "file": "c.py"},
            ]
            log_path.write_text(
                "\n".join(json.dumps(e) for e in entries),
                encoding="utf-8",
            )
            result = read_proof_log(tmpdir)
            assert len(result) == 3
            assert result[0]["file"] == "c.py"
            assert result[2]["file"] == "a.py"
