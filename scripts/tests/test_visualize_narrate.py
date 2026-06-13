"""
Tests for scripts/visualize-narrate.py — narration builder.

NOTE: visualize-narrate.py was removed from the codebase. These tests are skipped.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.skip(reason="visualize-narrate.py was removed from the codebase")

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    _spec = importlib.util.spec_from_file_location(
        "visualize_narrate", SCRIPTS_DIR / "visualize-narrate.py"
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    build_segments = _mod.build_segments
    _card_sentence = _mod._card_sentence
    _read_voice = _mod._read_voice
except FileNotFoundError:
    build_segments = None
    _card_sentence = None
    _read_voice = None


class TestCardSentence:
    def test_title_and_detail(self):
        result = _card_sentence({"title": "My Agent", "detail": "Does stuff"})
        assert "My Agent" in result
        assert "Does stuff" in result

    def test_title_only(self):
        result = _card_sentence({"title": "My Agent"})
        assert result == "My Agent"

    def test_detail_fallback_to_subtitle(self):
        result = _card_sentence({"title": "X", "subtitle": "A subtitle"})
        assert "A subtitle" in result

    def test_empty_card(self):
        result = _card_sentence({})
        assert result == ""

    def test_detail_takes_priority_over_subtitle(self):
        result = _card_sentence({"title": "X", "detail": "detail text", "subtitle": "subtitle text"})
        assert "detail text" in result


class TestBuildSegments:
    def _minimal_graph(self):
        return {
            "title": "Test Architecture",
            "subtitle": "3 agents",
            "layers": [],
            "side_rails": [],
        }

    def test_always_has_intro_segment(self):
        graph = self._minimal_graph()
        segments = build_segments(graph)
        assert len(segments) >= 1
        assert segments[0]["id"] == "_intro"

    def test_intro_contains_title(self):
        graph = self._minimal_graph()
        segments = build_segments(graph)
        assert "Test Architecture" in segments[0]["text"]

    def test_intro_contains_subtitle(self):
        graph = self._minimal_graph()
        segments = build_segments(graph)
        assert "3 agents" in segments[0]["text"]

    def test_side_rails_become_segments(self):
        graph = self._minimal_graph()
        graph["side_rails"] = [{"id": "rail1", "title": "Global Rules", "side": "left", "detail": "Always enforced"}]
        segments = build_segments(graph)
        rail_segment = next((s for s in segments if s["id"] == "rail1"), None)
        assert rail_segment is not None
        assert "Global Rules" in rail_segment["text"]

    def test_layers_become_segments(self):
        graph = self._minimal_graph()
        graph["layers"] = [{"id": "user", "label": "INPUT", "cards": [{"title": "You", "detail": "Chat input"}]}]
        segments = build_segments(graph)
        layer_segment = next((s for s in segments if s["id"] == "user"), None)
        assert layer_segment is not None
        assert "INPUT" in layer_segment["text"]

    def test_cards_limited_to_three_per_layer(self):
        graph = self._minimal_graph()
        graph["layers"] = [{
            "id": "test-layer",
            "label": "TEST",
            "cards": [{"title": f"Card{i}", "detail": f"Detail{i}"} for i in range(10)],
        }]
        segments = build_segments(graph)
        layer_seg = next(s for s in segments if s["id"] == "test-layer")
        # Text should contain at most 3 card contents (plus layer label)
        count = sum(1 for i in range(10) if f"Card{i}" in layer_seg["text"])
        assert count <= 3

    def test_columns_layers(self):
        graph = self._minimal_graph()
        graph["layers"] = [{
            "id": "agents",
            "label": "AGENTS",
            "columns": [
                {"cards": [{"title": "Opus Agent", "detail": "Strategic"}, {"title": "Extra", "detail": "More"}]},
            ],
        }]
        segments = build_segments(graph)
        agent_seg = next((s for s in segments if s["id"] == "agents"), None)
        assert agent_seg is not None

    def test_exchanges_in_layers(self):
        graph = self._minimal_graph()
        graph["layers"] = [{
            "id": "rag-layer",
            "label": "RAG",
            "exchanges": [{
                "left": {"title": "Agent", "detail": "Queries RAG"},
                "right": {"title": "Server", "detail": "Returns results"},
            }],
        }]
        segments = build_segments(graph)
        rag_seg = next((s for s in segments if s["id"] == "rag-layer"), None)
        assert rag_seg is not None
        assert "Agent" in rag_seg["text"] or "Server" in rag_seg["text"]

    def test_decisions_in_layers(self):
        graph = self._minimal_graph()
        graph["layers"] = [{
            "id": "classify",
            "label": "CLASSIFY",
            "decisions": [{
                "question": {"title": "Simple?", "detail": "Decides complexity"},
                "outcomes": [
                    {"title": "Simple", "detail": "Direct"},
                    {"title": "Complex", "detail": "Plan"},
                ],
            }],
        }]
        segments = build_segments(graph)
        seg = next((s for s in segments if s["id"] == "classify"), None)
        assert seg is not None
        assert "Simple?" in seg["text"] or "Simple" in seg["text"]

    def test_empty_graph(self):
        graph = {}
        segments = build_segments(graph)
        assert len(segments) >= 1
        assert segments[0]["id"] == "_intro"


class TestReadVoice:
    def test_returns_default_when_no_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "CLAUDEBOOST_HOME", tmp_path)
        result = _read_voice()
        assert result == _mod.DEFAULT_VOICE

    def test_reads_configured_voice(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "CLAUDEBOOST_HOME", tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "speak-state.json").write_text(
            json.dumps({"voice": "en-US-JennyNeural"}), encoding="utf-8"
        )
        result = _read_voice()
        assert result == "en-US-JennyNeural"

    def test_returns_default_on_bad_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "CLAUDEBOOST_HOME", tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "speak-state.json").write_text("BAD JSON", encoding="utf-8")
        result = _read_voice()
        assert result == _mod.DEFAULT_VOICE


# ---------------------------------------------------------------------------
# generate — mock synthesize_segment to avoid edge_tts dependency
# ---------------------------------------------------------------------------

class TestGenerate:
    def _graph_json(self, tmp_path) -> Path:
        graph = {
            "title": "Test",
            "layers": [{"id": "l1", "label": "Layer 1", "cards": []}],
            "side_rails": [],
        }
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(graph), encoding="utf-8")
        return p

    def test_generate_writes_mp3_and_timing(self, tmp_path):
        graph_path = self._graph_json(tmp_path)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        async def fake_synthesize(text, voice):
            return b"\xff\xfb\x90\x00" * 100, 1500  # fake mp3 bytes, 1500ms

        with patch.object(_mod, "synthesize_segment", side_effect=fake_synthesize):
            asyncio.run(_mod.generate(str(graph_path), str(out_dir), "en-US-AndrewNeural"))

        assert (out_dir / "narration.mp3").exists()
        assert (out_dir / "narration-timing.json").exists()

    def test_generate_timing_structure(self, tmp_path):
        graph_path = self._graph_json(tmp_path)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        async def fake_synthesize(text, voice):
            return b"\x00" * 50, 1000

        with patch.object(_mod, "synthesize_segment", side_effect=fake_synthesize):
            asyncio.run(_mod.generate(str(graph_path), str(out_dir), "en-US-AndrewNeural"))

        timing = json.loads((out_dir / "narration-timing.json").read_text(encoding="utf-8"))
        assert "sections" in timing
        assert "total_ms" in timing
        assert "voice" in timing
        assert timing["voice"] == "en-US-AndrewNeural"
        assert len(timing["sections"]) >= 1  # at least _intro section

    def test_generate_sections_have_ids(self, tmp_path):
        graph_path = self._graph_json(tmp_path)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        async def fake_synthesize(text, voice):
            return b"\x00" * 10, 500

        with patch.object(_mod, "synthesize_segment", side_effect=fake_synthesize):
            asyncio.run(_mod.generate(str(graph_path), str(out_dir), "en-US-AndrewNeural"))

        timing = json.loads((out_dir / "narration-timing.json").read_text(encoding="utf-8"))
        for section in timing["sections"]:
            assert "id" in section
            assert "start_ms" in section


# ---------------------------------------------------------------------------
# main() — tests argv parsing + generate orchestration
# ---------------------------------------------------------------------------

class TestMain:
    def _graph_json(self, tmp_path) -> Path:
        graph = {"title": "T", "layers": [], "side_rails": []}
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(graph), encoding="utf-8")
        return p

    def test_main_with_all_args(self, tmp_path):
        graph_path = self._graph_json(tmp_path)

        async def fake_generate(gp, od, voice):
            # Write expected output files
            out = Path(od)
            (out / "narration.mp3").write_bytes(b"\x00")
            (out / "narration-timing.json").write_text(
                json.dumps({"sections": [], "total_ms": 0, "voice": voice}), encoding="utf-8"
            )

        with patch("sys.argv", ["visualize-narrate.py", str(graph_path), str(tmp_path), "en-US-JennyNeural"]):
            with patch.object(_mod, "generate", side_effect=fake_generate):
                _mod.main()

    def test_main_defaults_to_graph_json(self, tmp_path):
        graph_path = self._graph_json(tmp_path)

        called_with = []
        async def fake_generate(gp, od, voice):
            called_with.append((gp, od, voice))

        with patch("sys.argv", ["visualize-narrate.py", str(graph_path)]):
            with patch.object(_mod, "generate", side_effect=fake_generate):
                _mod.main()

        assert len(called_with) == 1
        assert called_with[0][0] == str(graph_path)
