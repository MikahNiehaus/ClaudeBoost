#!/usr/bin/env python3
"""clean-rag RAG enforcement: UserPromptSubmit hook.

Fires on every user message. Injects a mandate to search RAG before
responding or editing. This is the strongest enforcement point for
ensuring all responses and decisions are research-grounded.

This hook cannot block responses (UserPromptSubmit has no exit-code gate),
but it injects instructions into every turn so Claude is reminded to
search RAG before doing anything.

Exit codes:
  0 = always (UserPromptSubmit hooks cannot block)
"""

import json
import os
import sys
import time
from pathlib import Path


def _clean_rag_home() -> Path:
    """Resolve the clean-rag root directory."""
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _health_check(port: str) -> dict:
    """Quick, non-blocking check of clean-rag server health.

    Mirrors the /status probe cli/server_ctl.py's cmd_start already uses to verify
    a fresh launch. status=='warming_up' is treated as healthy for the first 90s
    (matches the ~23s cold start measured after the startup-warmup fix in app.py's
    _on_startup) so a server that just started doesn't get flagged as broken.
    """
    import http.client

    try:
        conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=1.0)
        conn.request("GET", "/status")
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        data = json.loads(body)
    except Exception as e:
        return {"ok": False, "reason": f"unreachable: {e}"}

    status = data.get("status")
    uptime = data.get("uptime_s", 0)

    if status == "ready":
        return {"ok": True}
    if status == "warming_up" and uptime < 90:
        return {"ok": True}

    return {
        "ok": False,
        "reason": (
            f"status={status} uptime_s={uptime} "
            f"embedding_loaded={data.get('embedding_loaded')} "
            f"code_embedding_loaded={data.get('code_embedding_loaded')}"
        ),
    }


def _should_nudge_doctor(state_dir: Path, cooldown_s: int = 600) -> bool:
    """Rate-limit doctor-agent nudges so an in-progress repair isn't re-triggered every turn."""
    marker = state_dir / "last-doctor-nudge.json"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if time.time() - data.get("ts", 0) < cooldown_s:
            return False
    except Exception:
        pass
    return True


def _mark_doctor_nudged(state_dir: Path) -> None:
    marker = state_dir / "last-doctor-nudge.json"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
    except Exception:
        pass


def _read_mode() -> str:
    """Check if ClaudeBoost AUTO mode is active."""
    cb_home = os.environ.get("CLAUDEBOOST_HOME", "")
    if not cb_home:
        return "CONSULT"
    mode_file = Path(cb_home) / "state" / "claudeboost-mode.json"
    if mode_file.exists():
        try:
            data = json.loads(mode_file.read_text(encoding="utf-8"))
            return data.get("mode", "CONSULT")
        except Exception:
            pass
    return "CONSULT"


def _load_topic_tree() -> str:
    """Build a compact topic tree from topics.json for routing."""
    home = _clean_rag_home()
    registry_path = home / "state" / "topics.json"
    if not registry_path.exists():
        return "  (no topics indexed yet)"

    try:
        topics = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return "  (failed to read topic registry)"

    if not topics:
        return "  (no topics indexed yet)"

    # Group by category
    by_cat: dict[str, list[str]] = {}
    for name, info in topics.items():
        cat = info.get("category", "uncategorized")
        chunks = info.get("chunks", 0)
        by_cat.setdefault(cat, []).append(f"{name}({chunks})")

    lines = []
    for cat in sorted(by_cat):
        items = ", ".join(sorted(by_cat[cat]))
        lines.append(f"  {cat}/: {items}")

    return "\n".join(lines)


def main() -> int:
    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    topic_tree = _load_topic_tree()

    # The mandate injected into every user message turn (compressed for local inference)
    mandate = (
        "\n\n--- CLEAN-RAG: RESEARCH-FIRST ---\n"
        "1. Topics: {topic_tree}\n"
        "2. SEARCH: POST http://127.0.0.1:{port}/search OR direct research (Grep/WebSearch)\n"
        "3. Cite source: file:line, grep result, or WebSearch title\n"
        "4. Base response on research. For edits: write proof file (2+ angles: technology, codebase, pitfalls, security, best-practices, methodology)\n"
        "5. Save findings to clean-rag/knowledge/<category>/<topic>/ and POST /index-topic\n"
        "6. NO unresearched claims. NO 'typically/generally/usually' without sources.\n"
        "7. METHODOLOGY (code quality): clean-code-principles, solid-principles, code-smells,\n"
        "   design-patterns, refactoring-techniques, error-handling, api-design, testing-strategy,\n"
        "   defensive-programming, logging-observability, performance-optimization, architectural-patterns\n"
        "   Search these when writing or reviewing code for quality guidance.\n"
        "--- END CLEAN-RAG MANDATE ---\n"
    )

    # Output the mandate so it gets injected into the conversation
    print(mandate.format(topic_tree=topic_tree, port=port))

    health = _health_check(port)
    if not health["ok"]:
        home = _clean_rag_home()
        state_dir = home / "state"
        if _should_nudge_doctor(state_dir):
            _mark_doctor_nudged(state_dir)
            print(
                "\n--- CLEAN-RAG SERVER ISSUE DETECTED ---\n"
                f"Health check failed: {health['reason']}\n"
                "Spawn clean-rag-doctor-agent via the Task tool right now, running in the "
                "background (do not wait for it). Continue whatever you were already doing in "
                "parallel; do not block on the repair.\n"
                "--- END NOTICE ---\n"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
