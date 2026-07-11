#!/usr/bin/env python3
"""clean-rag proof stop-gate: Stop hook for CLEAN_RAG_GATE_MODE=stop.

Only does anything when proof-gate.py (PreToolUse) deferred one or more
Edit/Write/MultiEdit calls this session because CLEAN_RAG_GATE_MODE=stop
was active. In the default 'pretooluse' mode nothing ever gets recorded to
the pending list, so this hook is a fast no-op on every turn.

Checks every file recorded in state/stop-pending/<session_id>.json: has a
valid proof shown up since the edit happened? If yes, consume it and clear
it. If any files are still unproven when Claude tries to end its turn,
block once with a single consolidated message covering every unproven
file -- instead of one PreToolUse rejection per file, which is the burst-
cost problem this mode exists to fix (see workspace/
llama-server-wifi-switch-2026-07-01/context.md).

To guarantee this never becomes an infinite loop, a second consecutive
block in the same turn (stop_hook_active=True) is allowed through instead
of blocked again, the same convention scripts/speak-tts.py already uses
for the same reason. The bypass is logged for audit visibility.

Exit codes:
  0 = pass (nothing pending, everything got proven, or loop-guard let it through)
  2 = block (files still need proof, listed in one consolidated message)
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
_GATE_PATH = _HOOKS_DIR / "proof-gate.py"
_spec = importlib.util.spec_from_file_location("proof_gate", _GATE_PATH)
proof_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proof_gate)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return 0  # can't parse -- never block on our own malfunction

    session_id = payload.get("session_id", "")
    if not session_id:
        return 0

    home = proof_gate._clean_rag_home()
    state_dir = home / "state"

    pending = proof_gate.load_stop_pending(state_dir, session_id)
    if not pending:
        return 0  # fast path: nothing was ever deferred this session

    still_unproven = {}
    for canonical, record in pending.items():
        proof = None
        try:
            proof = proof_gate._try_consume_proof(state_dir, canonical)
        except (json.JSONDecodeError, OSError):
            proof = None

        if proof is None:
            still_unproven[canonical] = record
            continue

        valid, _reasons = proof_gate._validate_proof(
            proof, canonical,
            record.get("needs_methodology", False),
            record.get("suggested_methodology_topics", []),
            record.get("needs_best_practices", False),
            False,  # security-sensitive files never defer to this hook
        )
        if valid:
            proof_gate._log_proof(state_dir, record.get("file_path", canonical), proof, "")
        else:
            still_unproven[canonical] = record

    # Persist whatever's left -- clears fully-proven entries either way.
    proof_gate.save_stop_pending(state_dir, session_id, still_unproven)

    if not still_unproven:
        return 0

    # Loop guard: never block the same turn twice in a row.
    if payload.get("stop_hook_active", False):
        _log_loop_guard_bypass(state_dir, session_id, still_unproven)
        return 0

    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    print(_build_consolidated_message(still_unproven, port), file=sys.stderr)
    return 2


def _log_loop_guard_bypass(state_dir: Path, session_id: str, unproven: dict) -> None:
    log_path = state_dir / "stop-gate-bypass.jsonl"
    entry = {
        "ts": proof_gate._utc_now_iso(),
        "session_id": session_id,
        "files_unproven": [r.get("file_path", c) for c, r in unproven.items()],
        "reason": "loop_guard -- allowed turn to end with unproven files to avoid an infinite Stop-hook loop",
    }
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _build_consolidated_message(unproven: dict, port: str) -> str:
    files_list = "\n".join(
        f"  - {r.get('file_path', c)}" for c, r in unproven.items()
    )
    return (
        "CLEAN-RAG: turn cannot end -- {n} file(s) written this turn have no verified proof yet:\n"
        "{files}\n\n"
        "1. SEARCH: POST http://127.0.0.1:{port}/search "
        '{{"query": "<what you need>", "sources": ["all_topics", "project:<path>"]}} -- need score >= {min_score}.\n'
        "   Nothing found? Grep/Read/WebSearch directly (counts as research), then re-search.\n\n"
        "2. PROVE each file: POST http://127.0.0.1:{port}/prove "
        '{{"file_path": "<file>", "search_ids": ["<id1>", "<id2>"], '
        '"quality_aspects": [{{"aspect":"architecture","assertion":"<fits project how>"}}, '
        '{{"aspect":"patterns","assertion":"<follows what existing pattern>"}}]}}\n'
        "   Reuse the same search_ids across multiple files' /prove calls if the research genuinely "
        "covers all of them -- no need to repeat identical searches per file.\n\n"
        "3. This is one consolidated check for every file changed this turn, not one message per "
        "file. Write proof for all {n} files above, then you're done."
    ).format(n=len(unproven), files=files_list, port=port, min_score=proof_gate.MIN_PROOF_SCORE)


if __name__ == "__main__":
    sys.exit(main())
