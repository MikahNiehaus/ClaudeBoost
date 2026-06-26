"""Tests for the proof-gate hook logic.

Covers all audit findings: path exemptions (segment boundary), extension
exemptions (no .json/.yaml/.toml), content hash binding, min_score threshold,
strict timestamp validation, TOCTOU atomic consumption, keyed proof files,
AUTO mode logging, and empty file_path blocking.
"""

import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# proof-gate.py has a hyphen so we can't import it normally
_gate_path = Path(__file__).resolve().parent.parent / "hooks" / "proof-gate.py"
_spec = importlib.util.spec_from_file_location("proof_gate", _gate_path)
proof_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proof_gate)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(tool_name, file_path, **extra_input):
    """Build a hook payload dict."""
    inp = {"file_path": file_path}
    inp.update(extra_input)
    return {"tool_name": tool_name, "tool_input": inp}


def _write_proof(state_dir, file_path, verdict="VERIFIED",
                 content_hash="", min_score=0.85, ts=None,
                 verifier_response="Proof sufficient"):
    """Write a keyed proof file the way the gate expects to find it."""
    canonical = proof_gate._canonicalize(file_path)
    proof_path = proof_gate._proof_file_for(Path(state_dir), canonical)
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    proof = {
        "file": file_path,
        "file_canonical": canonical,
        "ts": ts,
        "verdict": verdict,
        "verifier_response": verifier_response,
        "rag_results_count": 3,
        "topics_cited": ["test"],
        "project_cited": False,
        "content_hash": content_hash,
        "min_score": min_score,
    }
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    return proof_path


def _run_gate(payload, env_overrides=None):
    """Run main() with the given payload on stdin."""
    env = {"CLEAN_RAG_HOME": "", "CLAUDEBOOST_HOME": ""}
    if env_overrides:
        env.update(env_overrides)
    with patch.dict(os.environ, env, clear=False), \
         patch("sys.stdin", StringIO(json.dumps(payload))):
        return proof_gate.main()


# ---------------------------------------------------------------------------
# Path segment matching (not substring)
# ---------------------------------------------------------------------------

class TestSegmentMatching:
    """AUDIT FIX: Exempt paths use directory-boundary matching, not substring."""

    @pytest.mark.parametrize("path,expected", [
        # Real segment matches (should be exempt)
        ("/home/user/project/workspace/task/notes.py", True),
        ("C:/Dev/project/knowledge/topic/doc.py", True),
        ("/project/plans/architecture.py", True),
        ("/project/docs/api.py", True),
        ("/project/state/session.py", True),
        ("/project/.claudeboost/config.py", True),
        ("/project/.claude/settings.py", True),
        # Substring false positives (should NOT be exempt)
        ("/project/my-workspace-tool/main.py", False),
        ("/home/user/knowledgebase/index.py", False),
        ("/project/estate/manager.py", False),
        ("/project/plansreport/gen.py", False),
    ])
    def test_segment_boundary_check(self, path, expected):
        canonical = proof_gate._canonicalize(path)
        matched = any(
            proof_gate._path_has_segment(canonical, seg)
            for seg in proof_gate.EXEMPT_SEGMENTS
        )
        assert matched == expected, f"{path}: expected exempt={expected}"


class TestCleanRagNotExempt:
    """AUDIT FIX: /clean-rag/ is NOT in EXEMPT_SEGMENTS. The enforcement
    system does not exempt itself."""

    def test_clean_rag_not_in_exempt_segments(self):
        assert "clean-rag" not in proof_gate.EXEMPT_SEGMENTS

    def test_clean_rag_path_not_exempt(self):
        canonical = proof_gate._canonicalize("/project/clean-rag/server/app.py")
        matched = any(
            proof_gate._path_has_segment(canonical, seg)
            for seg in proof_gate.EXEMPT_SEGMENTS
        )
        assert not matched


# ---------------------------------------------------------------------------
# Extension exemptions (no structured data formats)
# ---------------------------------------------------------------------------

class TestExtensionExemptions:
    """AUDIT FIX: .json, .yaml, .yml, .toml, .xml NOT exempt."""

    @pytest.mark.parametrize("ext", [".md", ".mdx", ".rst", ".txt",
                                      ".gitignore", ".env.example",
                                      ".csv", ".svg"])
    def test_still_exempt(self, ext):
        path = f"/project/file{ext}"
        matched = any(path.endswith(e) for e in proof_gate.EXEMPT_EXTENSIONS)
        assert matched, f"{ext} should still be exempt"

    @pytest.mark.parametrize("ext", [".json", ".yaml", ".yml", ".toml", ".xml"])
    def test_structured_data_not_exempt(self, ext):
        """Structured data files can fabricate proof. Must require proof."""
        path = f"/project/file{ext}"
        matched = any(path.endswith(e) for e in proof_gate.EXEMPT_EXTENSIONS)
        assert not matched, f"{ext} should NOT be exempt (proof fabrication risk)"

    @pytest.mark.parametrize("ext", [".py", ".ts", ".js", ".cs", ".go",
                                      ".rs", ".java", ".tsx", ".jsx"])
    def test_source_not_exempt(self, ext):
        path = f"/project/file{ext}"
        matched = any(path.endswith(e) for e in proof_gate.EXEMPT_EXTENSIONS)
        assert not matched, f"{ext} should NOT be exempt"


# ---------------------------------------------------------------------------
# Content hash binding
# ---------------------------------------------------------------------------

class TestContentHash:
    """AUDIT FIX: Proof is bound to specific edit content via SHA-256 hash."""

    def test_edit_hash_computation(self):
        tool_input = {
            "file_path": "/project/main.py",
            "old_string": "old code",
            "new_string": "new code",
        }
        h = proof_gate._file_content_hash(tool_input)
        assert len(h) == 64  # SHA-256 hex
        assert h == hashlib.sha256(
            b"old code\x00new code"
        ).hexdigest()

    def test_write_hash_computation(self):
        tool_input = {
            "file_path": "/project/main.py",
            "content": "full file content",
        }
        h = proof_gate._file_content_hash(tool_input)
        assert h == hashlib.sha256(b"full file content").hexdigest()

    def test_multiedit_hash_computation(self):
        tool_input = {
            "file_path": "/project/main.py",
            "edits": [
                {"old_string": "a", "new_string": "b"},
                {"old_string": "c", "new_string": "d"},
            ],
        }
        h = proof_gate._file_content_hash(tool_input)
        expected = hashlib.sha256(b"a\x00b\x01c\x00d\x01").hexdigest()
        assert h == expected

    def test_mismatched_hash_blocks(self, tmp_path):
        """Proof with wrong content_hash must be rejected."""
        file_path = str(tmp_path / "src" / "main.py")
        state_dir = tmp_path / "state"

        # Write proof with hash "aaa..."
        _write_proof(state_dir, file_path, content_hash="a" * 64)

        # Attempt edit with different content (different hash)
        payload = _make_payload("Edit", file_path,
                                old_string="x", new_string="y")
        result = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result == 2, "Mismatched content hash should block"

    def test_matching_hash_passes(self, tmp_path):
        """Proof with correct content_hash must pass."""
        file_path = str(tmp_path / "src" / "main.py")
        state_dir = tmp_path / "state"

        # Compute hash for the actual edit
        edit_hash = hashlib.sha256(b"old\x00new").hexdigest()
        _write_proof(state_dir, file_path, content_hash=edit_hash)

        payload = _make_payload("Edit", file_path,
                                old_string="old", new_string="new")
        result = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result == 0, "Matching content hash should pass"


# ---------------------------------------------------------------------------
# Min score threshold
# ---------------------------------------------------------------------------

class TestMinScore:
    """AUDIT FIX: Mechanical score threshold >= 0.5 enforced."""

    def test_score_below_threshold_blocks(self, tmp_path):
        file_path = str(tmp_path / "src" / "main.py")
        state_dir = tmp_path / "state"

        edit_hash = hashlib.sha256(b"old\x00new").hexdigest()
        _write_proof(state_dir, file_path,
                     content_hash=edit_hash, min_score=0.3)

        payload = _make_payload("Edit", file_path,
                                old_string="old", new_string="new")
        result = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result == 2, "Score 0.3 < 0.5 threshold should block"

    def test_score_at_threshold_passes(self, tmp_path):
        file_path = str(tmp_path / "src" / "main.py")
        state_dir = tmp_path / "state"

        edit_hash = hashlib.sha256(b"old\x00new").hexdigest()
        _write_proof(state_dir, file_path,
                     content_hash=edit_hash, min_score=0.5)

        payload = _make_payload("Edit", file_path,
                                old_string="old", new_string="new")
        result = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result == 0, "Score 0.5 at threshold should pass"

    def test_score_zero_blocks(self, tmp_path):
        file_path = str(tmp_path / "src" / "main.py")
        state_dir = tmp_path / "state"

        edit_hash = hashlib.sha256(b"old\x00new").hexdigest()
        _write_proof(state_dir, file_path,
                     content_hash=edit_hash, min_score=0.0)

        payload = _make_payload("Edit", file_path,
                                old_string="old", new_string="new")
        result = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result == 2, "Score 0.0 should block"


# ---------------------------------------------------------------------------
# Strict timestamp validation
# ---------------------------------------------------------------------------

class TestStrictTimestamp:
    """AUDIT FIX: Naive timestamps (no timezone) are rejected."""

    def test_fresh_utc_timestamp_passes(self):
        now = datetime.now(timezone.utc)
        proof = {"ts": now.isoformat().replace("+00:00", "Z")}
        assert proof_gate._is_fresh_strict(proof) is True

    def test_stale_timestamp_fails(self):
        old = datetime.now(timezone.utc) - timedelta(seconds=200)
        proof = {"ts": old.isoformat().replace("+00:00", "Z")}
        assert proof_gate._is_fresh_strict(proof) is False

    def test_naive_timestamp_rejected(self):
        """Naive datetime (no timezone) must be rejected, not assumed UTC."""
        naive = datetime.now().isoformat()  # No timezone info
        proof = {"ts": naive}
        assert proof_gate._is_fresh_strict(proof) is False

    def test_future_timestamp_rejected(self):
        """Timestamps more than 5 seconds in the future are rejected."""
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        proof = {"ts": future.isoformat().replace("+00:00", "Z")}
        assert proof_gate._is_fresh_strict(proof) is False

    def test_empty_timestamp_fails(self):
        assert proof_gate._is_fresh_strict({"ts": ""}) is False

    def test_missing_timestamp_fails(self):
        assert proof_gate._is_fresh_strict({}) is False

    def test_malformed_timestamp_fails(self):
        assert proof_gate._is_fresh_strict({"ts": "not-a-date"}) is False

    def test_boundary_119s_passes(self):
        ts = datetime.now(timezone.utc) - timedelta(seconds=119)
        proof = {"ts": ts.isoformat().replace("+00:00", "Z")}
        assert proof_gate._is_fresh_strict(proof) is True

    def test_boundary_121s_fails(self):
        ts = datetime.now(timezone.utc) - timedelta(seconds=121)
        proof = {"ts": ts.isoformat().replace("+00:00", "Z")}
        assert proof_gate._is_fresh_strict(proof) is False


# ---------------------------------------------------------------------------
# TOCTOU: atomic proof consumption
# ---------------------------------------------------------------------------

class TestAtomicConsumption:
    """AUDIT FIX: Proof file is atomically renamed before reading,
    preventing race conditions and replay attacks."""

    def test_proof_file_consumed_after_pass(self, tmp_path):
        """After a successful gate pass, the proof file should be gone."""
        file_path = str(tmp_path / "src" / "main.py")
        state_dir = tmp_path / "state"

        edit_hash = hashlib.sha256(b"old\x00new").hexdigest()
        proof_path = _write_proof(state_dir, file_path,
                                   content_hash=edit_hash)

        payload = _make_payload("Edit", file_path,
                                old_string="old", new_string="new")
        result = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result == 0

        # Both the proof file and the consumed file should be cleaned up
        assert not proof_path.exists(), "Proof file should be consumed"
        assert not proof_path.with_suffix(".consumed").exists()

    def test_proof_not_reusable(self, tmp_path):
        """Same proof cannot be used twice (consumed on first use)."""
        file_path = str(tmp_path / "src" / "main.py")
        state_dir = tmp_path / "state"

        edit_hash = hashlib.sha256(b"old\x00new").hexdigest()
        _write_proof(state_dir, file_path, content_hash=edit_hash)

        payload = _make_payload("Edit", file_path,
                                old_string="old", new_string="new")

        # First use: passes
        result1 = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result1 == 0

        # Second use: blocks (proof already consumed)
        result2 = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result2 == 2, "Consumed proof should not be reusable"


# ---------------------------------------------------------------------------
# Keyed proof files (concurrent edits)
# ---------------------------------------------------------------------------

class TestKeyedProofFiles:
    """AUDIT FIX: Each file gets its own proof file, keyed by path hash."""

    def test_different_files_get_different_proof_paths(self):
        state_dir = Path("/tmp/state")
        p1 = proof_gate._proof_file_for(state_dir, "/project/a.py")
        p2 = proof_gate._proof_file_for(state_dir, "/project/b.py")
        assert p1 != p2

    def test_same_file_gets_same_proof_path(self):
        state_dir = Path("/tmp/state")
        p1 = proof_gate._proof_file_for(state_dir, "/project/a.py")
        p2 = proof_gate._proof_file_for(state_dir, "/project/a.py")
        assert p1 == p2

    def test_concurrent_proofs_independent(self, tmp_path):
        """Two different files can have proofs simultaneously."""
        file_a = str(tmp_path / "src" / "a.py")
        file_b = str(tmp_path / "src" / "b.py")
        state_dir = tmp_path / "state"

        hash_a = hashlib.sha256(b"old_a\x00new_a").hexdigest()
        hash_b = hashlib.sha256(b"old_b\x00new_b").hexdigest()

        _write_proof(state_dir, file_a, content_hash=hash_a)
        _write_proof(state_dir, file_b, content_hash=hash_b)

        # Both should pass independently
        payload_a = _make_payload("Edit", file_a,
                                  old_string="old_a", new_string="new_a")
        result_a = _run_gate(payload_a, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result_a == 0

        payload_b = _make_payload("Edit", file_b,
                                  old_string="old_b", new_string="new_b")
        result_b = _run_gate(payload_b, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result_b == 0


# ---------------------------------------------------------------------------
# AUTO mode logging
# ---------------------------------------------------------------------------

class TestAutoModeLogging:
    """AUDIT FIX: AUTO mode bypass is logged to proof-log.jsonl."""

    def test_auto_bypass_logged(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        file_path = str(tmp_path / "src" / "main.py")
        payload = _make_payload("Edit", file_path,
                                old_string="x", new_string="y")

        with patch.dict(os.environ, {
            "CLEAN_RAG_HOME": str(tmp_path),
            "CLAUDEBOOST_HOME": "",
        }), patch("sys.stdin", StringIO(json.dumps(payload))), \
             patch.object(proof_gate, "_read_mode", return_value="AUTO"):
            result = proof_gate.main()

        assert result == 0

        log_path = state_dir / "proof-log.jsonl"
        assert log_path.exists(), "AUTO bypass should be logged"

        log_content = log_path.read_text()
        entry = json.loads(log_content.strip())
        assert entry["verdict"] == "AUTO_BYPASS"


# ---------------------------------------------------------------------------
# Empty file_path
# ---------------------------------------------------------------------------

class TestEmptyFilePath:
    """AUDIT FIX: Empty file_path blocks (not passes)."""

    def test_empty_path_blocks(self):
        payload = _make_payload("Edit", "")
        result = _run_gate(payload)
        assert result == 2, "Empty file_path should block"


# ---------------------------------------------------------------------------
# Non-edit tools pass through
# ---------------------------------------------------------------------------

class TestNonEditTools:
    """Tools that aren't Edit/Write/MultiEdit always pass."""

    @pytest.mark.parametrize("tool", ["Read", "Grep", "Glob", "Bash", "Agent"])
    def test_non_edit_passes(self, tool):
        payload = {"tool_name": tool, "tool_input": {"file_path": "/src/main.py"}}
        result = _run_gate(payload)
        assert result == 0


# ---------------------------------------------------------------------------
# Full integration: end-to-end proof cycle
# ---------------------------------------------------------------------------

class TestFullProofCycle:
    """End-to-end test: write proof, then gate passes on matching edit."""

    def test_complete_cycle(self, tmp_path):
        file_path = str(tmp_path / "project" / "api" / "routes.py")
        state_dir = tmp_path / "state"

        # Step 1: Compute content hash for the planned edit
        edit_hash = hashlib.sha256(
            b"return Response(data)\x00return JSONResponse(data, status_code=200)"
        ).hexdigest()

        # Step 2: Write proof with all required fields
        _write_proof(
            state_dir, file_path,
            content_hash=edit_hash,
            min_score=0.87,
        )

        # Step 3: Attempt the edit
        payload = _make_payload(
            "Edit", file_path,
            old_string="return Response(data)",
            new_string="return JSONResponse(data, status_code=200)",
        )
        result = _run_gate(payload, {"CLEAN_RAG_HOME": str(tmp_path)})
        assert result == 0

        # Step 4: Verify audit log was written
        log_path = state_dir / "proof-log.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["verdict"] == "VERIFIED"
        assert entry["content_hash"] == edit_hash
        assert entry["min_score"] == 0.87


# ---------------------------------------------------------------------------
# Path canonicalization
# ---------------------------------------------------------------------------

class TestCanonicalize:
    """Path normalization produces consistent lowercase POSIX paths."""

    def test_backslashes_converted(self):
        result = proof_gate._canonicalize("C:\\Users\\dev\\project\\main.py")
        assert "\\" not in result
        assert "/" in result

    def test_case_insensitive(self):
        r1 = proof_gate._canonicalize("C:/Project/Src/Main.py")
        r2 = proof_gate._canonicalize("c:/project/src/main.py")
        assert r1 == r2


# ---------------------------------------------------------------------------
# Verifier log.py integration
# ---------------------------------------------------------------------------

class TestVerifierLog:
    """Test the write_pending_proof utility produces gate-compatible output."""

    def test_write_creates_keyed_file(self, tmp_path):
        from verifier.log import write_pending_proof
        state_dir = tmp_path / "state"

        result_path = write_pending_proof(
            state_dir=state_dir,
            file_path="/project/main.py",
            verdict="VERIFIED",
            verifier_response="Proof sufficient",
            rag_results_count=3,
            topics_cited=["fastapi"],
            content_hash="abc123",
            min_score=0.85,
        )

        assert result_path.exists()
        # Should be a keyed file, not "pending-proof.json"
        assert "pending-proof-" in result_path.name
        assert result_path.suffix == ".json"

        data = json.loads(result_path.read_text())
        assert data["verdict"] == "VERIFIED"
        assert data["content_hash"] == "abc123"
        assert data["min_score"] == 0.85
        assert "file_canonical" in data

    def test_write_normalizes_path(self, tmp_path):
        from verifier.log import write_pending_proof
        state_dir = tmp_path / "state"

        write_pending_proof(
            state_dir=state_dir,
            file_path="C:\\Users\\dev\\Project\\Main.py",
            verdict="VERIFIED",
            verifier_response="OK",
            content_hash="x",
            min_score=0.6,
        )

        # Find the proof file
        proof_files = list(state_dir.glob("pending-proof-*.json"))
        assert len(proof_files) == 1

        data = json.loads(proof_files[0].read_text())
        assert "\\" not in data["file_canonical"]
        assert data["file_canonical"] == data["file_canonical"].lower()
