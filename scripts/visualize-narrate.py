#!/usr/bin/env python3
"""
Generate a spoken narration MP3 for a visualize board.

Reads graph.json, builds a section-by-section walkthrough, synthesizes
audio via edge-tts (same voice as /speak), and outputs:
  - narration.mp3       — full audio, section segments concatenated
  - narration-timing.json — {sections: [{id, start_ms}], total_ms, voice}

The render.py step embeds both into visualize.html automatically.

Usage:
  python visualize-narrate.py <graph.json> <output_dir> [voice]

Voice defaults to the voice in $CLAUDEBOOST_HOME/state/speak-state.json,
falling back to en-US-AndrewNeural.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

CLAUDEBOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME", Path(__file__).parent.parent))
DEFAULT_VOICE = "en-US-AndrewNeural"


def _read_voice() -> str:
    """Read the user's configured /speak voice."""
    state_path = CLAUDEBOOST_HOME / "state" / "speak-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return state.get("voice", DEFAULT_VOICE)
    except Exception:
        return DEFAULT_VOICE


def _card_sentence(card: dict) -> str:
    name = card.get("title", "")
    detail = card.get("detail") or card.get("subtitle") or ""
    if name and detail:
        return f"{name}: {detail}"
    return name or detail


def build_segments(graph: dict) -> list[dict]:
    """
    Build narration segments that each map to a visible section/card group.
    Returns list of {id, text} dicts — one per section to highlight.
    """
    segments: list[dict] = []

    # ── Intro ────────────────────────────────────────────────────────────────
    title = graph.get("title", graph.get("project", "Architecture"))
    subtitle = graph.get("subtitle", "")
    intro = f"Welcome to the {title} architecture overview."
    if subtitle:
        intro += f" {subtitle}."
    segments.append({"id": "_intro", "text": intro})

    # ── Side rails ──────────────────────────────────────────────────────────
    for rail in graph.get("side_rails", []):
        parts = [f"{rail.get('title', '')} — a cross-cutting concern on the {rail.get('side', 'side')}."]
        if rail.get("detail"):
            parts.append(rail["detail"])
        resp = (rail.get("responsibilities") or [])[:3]
        if resp:
            parts.append("Key aspects: " + ". ".join(resp) + ".")
        segments.append({"id": rail["id"], "text": " ".join(parts)})

    # ── Layers ───────────────────────────────────────────────────────────────
    for layer in graph.get("layers", []):
        layer_id = layer.get("id") or f"layer-{len(segments)}"
        label = layer.get("label", layer_id)
        parts: list[str] = [f"{label}."]

        # Flat cards (cap at 3)
        for card in (layer.get("cards") or [])[:3]:
            s = _card_sentence(card)
            if s:
                parts.append(s)

        # Columns (cap at 2 cards per column, 2 columns)
        for col in (layer.get("columns") or [])[:2]:
            for card in (col.get("cards") or [])[:2]:
                s = _card_sentence(card)
                if s:
                    parts.append(s)

        # Exchanges
        for ex in (layer.get("exchanges") or []):
            for side in ("left", "right"):
                s = _card_sentence(ex.get(side, {}))
                if s:
                    parts.append(s)

        # Decisions
        for dec in (layer.get("decisions") or []):
            q = dec.get("question", {})
            s = _card_sentence(q)
            if s:
                parts.append(s)
            for outcome in (dec.get("outcomes") or [])[:2]:
                s = _card_sentence(outcome)
                if s:
                    parts.append(s)

        # Keep narration tight — cap at ~6 sentences per layer
        segments.append({"id": layer_id, "text": " ".join(parts[:7])})

    return segments


async def synthesize_segment(text: str, voice: str) -> tuple[bytes, int]:
    """
    Synthesize one segment. Returns (mp3_bytes, duration_ms).
    Duration is computed from edge-tts WordBoundary events.
    """
    import edge_tts  # type: ignore

    communicate = edge_tts.Communicate(text, voice)
    audio_chunks: list[bytes] = []
    last_offset_100ns = 0
    last_duration_100ns = 0

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            last_offset_100ns = chunk.get("offset", 0)
            last_duration_100ns = chunk.get("duration", 0)

    audio = b"".join(audio_chunks)

    # Prefer word-boundary duration; fall back to bitrate estimate (24 kbps)
    duration_100ns = last_offset_100ns + last_duration_100ns
    if duration_100ns > 0:
        duration_ms = duration_100ns // 10000
    else:
        duration_ms = len(audio) * 8 * 1000 // 24000

    return audio, duration_ms


async def generate(graph_path: str, output_dir: str, voice: str) -> None:
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    segments = build_segments(graph)

    all_audio = bytearray()
    timing_sections: list[dict] = []
    current_ms = 0

    for seg in segments:
        print(f"  [{seg['id']}] synthesizing...", flush=True)
        audio, duration_ms = await synthesize_segment(seg["text"], voice)
        timing_sections.append({"id": seg["id"], "start_ms": current_ms})
        all_audio.extend(audio)
        current_ms += duration_ms

    out = Path(output_dir)
    mp3_path = out / "narration.mp3"
    timing_path = out / "narration-timing.json"

    mp3_path.write_bytes(bytes(all_audio))
    timing_path.write_text(
        json.dumps(
            {"sections": timing_sections, "total_ms": current_ms, "voice": voice},
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Narration: {mp3_path} ({len(all_audio):,} bytes, ~{current_ms // 1000}s)")
    print(f"Timing:    {timing_path} ({len(timing_sections)} sections)")


def main() -> None:
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "graph.json"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else str(Path(graph_path).parent)
    voice = sys.argv[3] if len(sys.argv) > 3 else _read_voice()

    print(f"Voice: {voice}")
    asyncio.run(generate(graph_path, output_dir, voice))


if __name__ == "__main__":
    main()
