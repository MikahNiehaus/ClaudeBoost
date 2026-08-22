"""
ClaudeBoost session primer, a UserPromptSubmit command hook.

Emits only what CHANGED since the last prompt. It used to restate a fixed
1,437 token block of rules on every message. That text is not paid for once:
additionalContext lands in the transcript and every later request re-reads it,
so a constant block costs on the order of N squared across N prompts, roughly
86k tokens of pure repetition by turn 60.

The rules themselves now live in CLAUDE.md, which is loaded once into the
cached prefix. What is left here is the part CLAUDE.md genuinely cannot carry,
because it is only knowable at runtime:

- the RAG server going offline or coming back
- CONSULT and AUTO being toggled
- the active workspace changing, or one of its indexes flipping state
- one shot restores after /clear and after a compaction

Steady state, when nothing has changed, this emits a single pointer line.

State is tracked per session in a temp file keyed on session_id, so a delta is
measured against the previous prompt in the same conversation rather than
against a process that no longer exists.

Boost injection modes (state/boost-injection.json):
- "false"  skip all injection entirely
- "true"   skip the RAG health check, still emit deltas and restores
- "verify" (default) full behavior
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Pre-compiled once per process — used by _tokenize() called N times per session-primer run.
_TOKEN_RE = re.compile(r'[a-zA-Z][a-zA-Z0-9]*', re.IGNORECASE)
_STOP_WORDS = frozenset({
    'a', 'an', 'the', 'is', 'it', 'its', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or',
    'but', 'not', 'be', 'was', 'are', 'were', 'has', 'have', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'can', 'may', 'might', 'that', 'this', 'these',
    'those', 'with', 'from', 'by', 'as', 'if', 'so', 'then', 'than', 'when', 'where',
    'which', 'who', 'what', 'how', 'i', 'you', 'we', 'they', 'he', 'she', 'my', 'your',
    'our', 'their', 'me', 'him', 'her', 'us', 'them', 'also', 'just', 'up', 'about',
    'into', 'after', 'before', 'all', 'any', 'each', 'get', 'got', 'make', 'use',
    'run', 'see', 'look', 'go', 'work', 'need', 'want', 'fix', 'add', 'new', 'old',
})


from hook_session_state import (
    digest as _digest,
    read_payload,
    read_state,
    session_key as _session_key,
    temp_dir,
    write_state,
)
from rag_port import rag_url, server_ctl
from workspace_identity import get_instance_id, read_ws_instance, normalize_cwd


def _get_rag_status(timeout: float = 0.5) -> dict | None:
    """
    Quick GET /status. Returns the status dict, or None if unreachable or slow.

    Probed on every prompt rather than cached. There was a 60s cache here, and
    it was keyed on os.getpid(), so it never once hit: a hook is a fresh
    process per prompt. Probing every time is therefore the behavior that has
    actually been running all along. Reinstating a real cache would be worse
    than useless now, because a cached healthy answer hides the server going
    down for as long as the cache lives, and going down is precisely the
    transition this hook exists to report.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(rag_url("/status"), timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _temp_dir() -> Path:
    return temp_dir()


def _tokenize(text: str) -> set:
    """Word tokens filtered to meaningful terms (len>2, not stop words)."""
    return {w for w in _TOKEN_RE.findall(text.lower()) if len(w) > 2 and w not in _STOP_WORDS}


def _read_workspace_summary(ws_path: str) -> str:
    """Read the first meaningful lines from ticket.md or context.md."""
    for fname in ('ticket.md', 'context.md'):
        p = Path(ws_path) / fname
        try:
            text = p.read_text(encoding='utf-8', errors='replace')
            # First 600 chars is enough for keyword matching
            return text[:600]
        except OSError:
            continue
    return ''


def _find_best_workspace(home: Path, user_message: str = '') -> tuple:
    """
    Return the best-matching workspace for the current project and message.

    Priority:
    1. Per-instance ws-instance file (unique per Claude window)
    2. Keyword scoring + recency across project-scoped workspaces only (CWD filter)
    3. active-workspace.json (last resort for fresh sessions after /clear-safe)

    Returns:
    - (ws_id, ws_path, project_path, candidates) where candidates is a list
      of (ws_id, ws_path, project_path, summary_snippet, score) tuples
    - If one workspace clearly dominates (score >= 1.8x runner-up): candidates is empty
    - If scores are close: candidates list has top matches for Claude to pick from
    - If no workspace active in last 48h: all empty
    """
    reg_file = home / 'state' / 'workspaces.json'
    try:
        reg = json.loads(reg_file.read_text(encoding='utf-8'))
    except Exception:
        return '', '', '', []

    cwd_norm = normalize_cwd(os.getcwd())

    # Check per-instance file first (unique per Claude window, survives compaction)
    instance_id = get_instance_id()
    inst_path = home / 'state' / 'ws-instance' / f'{instance_id}.json'
    ws_id = read_ws_instance(inst_path, cwd_norm)
    if ws_id:
        entry = reg.get(ws_id, {})
        ws_path = entry.get('workspace_path', '')
        project_path = entry.get('project_path', '')
        if ws_path:
            return ws_id, ws_path, project_path, []

    cutoff = datetime.now(timezone.utc).timestamp() - 48 * 3600
    user_tokens = _tokenize(user_message) if user_message else set()

    scored = []
    for ws_id, entry in reg.items():
        ws_path = entry.get('workspace_path', '')
        if not ws_path:
            continue

        # Only score workspaces that belong to the current project
        pp = entry.get('project_path', '').replace('\\', '/').rstrip('/')
        if pp and pp.lower() != cwd_norm.lower():
            continue

        ws_dir = Path(ws_path)
        ctx = ws_dir / 'context.md'
        target = ctx if ctx.exists() else ws_dir
        try:
            mtime = target.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            continue

        summary = _read_workspace_summary(ws_path)
        ws_tokens = _tokenize(summary)

        # Keyword overlap score + recency bonus (hours ago, max 48)
        overlap = len(user_tokens & ws_tokens) if user_tokens else 0
        hours_ago = (datetime.now(timezone.utc).timestamp() - mtime) / 3600
        recency_bonus = max(0, (48 - hours_ago) / 48)  # 0..1
        score = overlap + recency_bonus

        # First ~120 chars of summary as display snippet
        snippet = summary.replace('\n', ' ').replace('\r', '').strip()[:120]
        project_path = entry.get('project_path', '')
        scored.append((score, overlap, mtime, ws_id, ws_path, project_path, snippet))

    if not scored:
        # Fallback: active-workspace.json (last resort for fresh sessions)
        try:
            aw = json.loads((home / "state" / "active-workspace.json").read_text(encoding="utf-8"))
            aw_id = aw.get("workspace", "")
            if aw_id:
                entry = reg.get(aw_id, {})
                ws_path = entry.get("workspace_path", "") or aw.get("workspace_path", "")
                proj_path = entry.get("project_path", "") or aw.get("project_path", "")
                if ws_path:
                    return aw_id, ws_path, proj_path, []
        except Exception:
            pass
        return '', '', '', []

    scored.sort(key=lambda x: (-x[0], -x[2]))  # desc score, then desc mtime

    top = scored[0]
    top_score, top_overlap = top[0], top[1]
    top_score_v, top_overlap_v, top_mtime, top_id, top_ws, top_proj, top_snip = top

    # Build candidates list for the top 3
    candidates = [
        (row[3], row[4], row[5], row[6], row[0])  # id, ws, proj, snippet, score
        for row in scored[:3]
    ]

    # Clear winner: only one candidate, OR top score >= 1.8x runner-up AND has keyword overlap
    if len(scored) == 1:
        return top_id, top_ws, top_proj, []

    runner_score = scored[1][0]
    if top_overlap_v > 0 and top_score_v >= runner_score * 1.8:
        return top_id, top_ws, top_proj, []

    # Ambiguous: return top match + candidates for Claude to consider
    return top_id, top_ws, top_proj, candidates


def _active_workspace_reminder(
    home: Path,
    rag_status: dict | None = None,
    task_description: str = '',
    ws_info: tuple | None = None,
) -> str:
    """
    Return a workspace status dashboard with tier health and action directives.

    Auto-detects the best-matching workspace for the user's current message:
    - Single clear winner: uses it silently
    - Ambiguous (scores close): shows top candidates so Claude can pick from context
    - Nothing active in 48h: returns empty string (no dashboard)

    ws_info: optional pre-computed (ws_id, ws_path, project_path, candidates) from main()
             to avoid calling _find_best_workspace() twice.
    """
    if ws_info is not None:
        ws_id, ws_path, project_path, candidates = ws_info
    else:
        ws_id, ws_path, project_path, candidates = _find_best_workspace(home, task_description)
    if not ws_path:
        return ''

    # Tier 4: check codebase index via live /status response
    codebase_ready = False
    codebase_detail = 'unknown (RAG offline)'
    if rag_status is not None and project_path:
        indexed = rag_status.get('indexed_projects', [])
        if isinstance(indexed, list):
            norm = project_path.rstrip('/\\').replace('\\', '/')
            for p in indexed:
                p_norm = p.get('project_path', '').rstrip('/\\').replace('\\', '/')
                if p_norm == norm:
                    codebase_ready = True
                    files = p.get('files', '?')
                    chunks = p.get('chunks', '?')
                    codebase_detail = f'READY ({files} files / {chunks} chunks)'
                    break
            if not codebase_ready:
                codebase_detail = 'NOT INDEXED'
    elif rag_status is None:
        codebase_detail = 'unknown (RAG offline - run /rag)'

    # Tier 5: research index directory check
    t3c_exists = (Path(ws_path) / '.rag-index' / 'research').exists()
    t3c_detail = 'READY' if t3c_exists else 'NOT BUILT'

    # Project KB status — .claudeboost/knowledge/ inside the project
    project_kb_exists = False
    project_kb_detail = 'N/A (no project_path)'
    if project_path:
        kb_dir = Path(project_path) / '.claudeboost' / 'knowledge'
        try:
            kb_files = list(kb_dir.glob('*.md')) if kb_dir.exists() else []
            if kb_files:
                project_kb_detail = f'READY ({len(kb_files)} files)'
                project_kb_exists = True
            else:
                project_kb_detail = 'NOT BUILT'
        except PermissionError:
            project_kb_detail = 'UNKNOWN (permission error)'

    # Required actions for missing indexes — all appends must happen before lines is built
    required_actions = []
    if project_path and not codebase_ready and rag_status is not None:
        required_actions.append(
            f"  [1] CODEBASE NOT INDEXED - run Skill(skill='index-project', args='{project_path}')"
            f" as your FIRST action. Tiers 3+4 are offline until indexed."
        )
    lines = []

    # Show candidates when detection is ambiguous
    if candidates and len(candidates) > 1:
        lines += ['WORKSPACE CANDIDATES (multiple active - using best match for this message):']
        for i, (cid, cws, cproj, csnip, cscore) in enumerate(candidates):
            marker = '[selected]' if i == 0 else '[other]   '
            lines.append(f'  {marker} {cid} - {csnip[:80]}')
        lines += [
            'If the selected workspace does not match your question, use the other candidate',
            'and adjust POST /context params accordingly.',
            '',
        ]

    if required_actions:
        lines += ['REQUIRED BEFORE RESPONDING (missing indexes - do these first):']
        lines += required_actions
        lines += ['']

    lines += [
        f'ACTIVE WORKSPACE: {ws_id}',
        f'  workspace_path: {ws_path}',
    ]
    if project_path:
        lines.append(f'  project_path:   {project_path}')

    lines += [
        '',
        'INDEX STATUS:',
        f'  codebase (clean-rag):  {codebase_detail}',
        f'  task research:         {t3c_detail}',
        f'  project KB:            {project_kb_detail}',
    ]

    # Deliberately no task_description echo here. Repeating the user's own
    # message back at them costs tokens and, worse, made this block different
    # on every prompt, so the change detection below could never call it
    # unchanged and it reprinted forever.
    if project_path:
        lines += [
            '',
            'Codebase search this session:',
            f'  POST {rag_url("/search")}',
            f'    sources = ["project:{project_path}"]',
            '    mode    = "both"   (vector and graph together, never only one)',
        ]

    return '\n'.join(lines)


def _get_boost_injection_mode(home: Path) -> str:
    """Return boost injection mode: 'true', 'false', or 'verify' (default)."""
    state_path = home / "state" / "boost-injection.json"
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data.get("mode", "verify").lower()
    except Exception:
        return "verify"


def consult_mode_active(home: Path) -> bool:
    mode_file = home / "state" / "claudeboost-mode.json"
    if not mode_file.exists():
        return True  # default is CONSULT when file is missing
    try:
        data = json.loads(mode_file.read_text(encoding="utf-8"))
        return data.get("mode", "CONSULT").upper() != "AUTO"
    except Exception:
        return True  # default to CONSULT on read error


def _sentinel_path() -> Path:
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    return Path(temp) / "claudeboost_rag_ok"


def rag_verified() -> bool:
    return _sentinel_path().exists()


def _try_auto_recover_rag(home: Path) -> bool:
    """
    Auto recover when the sentinel is missing.

    Fast path: the server is already up (common, because rag-session-reset.py
    deletes the sentinel at every SessionStart while the daemon keeps running).
    Write the sentinel and return.

    Slow path: start it detached. This used to launch scripts/rag-server-start.py,
    which was deleted with the 8612 server, so recovery always failed and every
    prompt got a "could not be started" banner it could do nothing about.
    clean-rag's own server_ctl.py is the launcher that exists.
    """
    # Fast path: already running, so just write the sentinel
    if _get_rag_status(timeout=1.0) is not None:
        try:
            _sentinel_path().touch()
        except Exception:
            pass
        return True

    start_script = server_ctl()
    if not start_script.exists():
        return False

    python = os.environ.get("CLAUDEBOOST_PYTHON") or sys.executable
    try:
        kwargs: dict = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        subprocess.Popen([python, str(start_script), "start"], **kwargs)
        # Optimistic: the server takes a few seconds, and the alternative is
        # warning about it on every prompt until it finishes booting.
        try:
            _sentinel_path().touch()
        except Exception:
            pass
        return True
    except Exception:
        return False


def _get_home() -> Path:
    return Path(os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ))


def _consume_clear_pending(home: Path) -> str:
    """
    Check for a clear-pending flag written by /clear-safe.
    If present and < 10 minutes old, return restore context string and consume the flag.
    The flag is always deleted (one-shot) whether or not it is valid.
    """
    flag_path = home / "state" / "clear-pending.json"
    if not flag_path.exists():
        return ""

    # Always consume the flag — one use only, regardless of outcome
    try:
        flag = json.loads(flag_path.read_text(encoding="utf-8"))
    except Exception:
        flag = {}
    finally:
        try:
            flag_path.unlink(missing_ok=True)
        except Exception:
            pass

    if not flag.get("pending"):
        return ""

    ts_str = flag.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > 600:  # 10-minute window — stale flag after that
            return ""
    except Exception:
        return ""

    # Load workspace memo from handoff-latest.json
    handoff_path = home / "state" / "handoff-latest.json"
    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    workspace_memo = handoff.get("workspace_memo", "") or handoff.get("memo", "")
    if not workspace_memo:
        return ""

    # The auto-save hook writes ALL workspace memos into one string.
    # Filter to just the active workspace section — injecting everything wastes tokens.
    active_ws = handoff.get("active_workspace", "").strip()
    if active_ws:
        marker = f"### {active_ws}\n"
        idx = workspace_memo.find(marker)
        if idx != -1:
            rest = workspace_memo[idx + len(marker):]
            next_section = rest.find("\n### ")
            workspace_memo = rest[:next_section].strip() if next_section != -1 else rest.strip()

    # Restore the ws-instance binding for this new session so the status bar
    # and workspace dashboard pick up the right workspace automatically.
    ws_restored_note = ""
    if active_ws:
        try:
            reg_path = home / "state" / "workspaces.json"
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            if active_ws in reg:
                cwd = os.getcwd().replace("\\", "/").rstrip("/")
                instance_id = get_instance_id()
                inst_dir = home / "state" / "ws-instance"
                inst_dir.mkdir(parents=True, exist_ok=True)
                inst_path = inst_dir / f"{instance_id}.json"
                try:
                    existing = json.loads(inst_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
                existing[cwd] = active_ws
                inst_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
                ws_restored_note = f"\nWorkspace restored: {active_ws} (set automatically from handoff)"
        except Exception:
            pass

    handoff_msg = handoff.get("handoff_message", "").strip()

    return (
        "POST-CLEAR CONTEXT RESTORATION\n"
        "===============================\n\n"
        "You just returned from a /clear or a Low Token Mode terminal switch. "
        "Below is your saved working state.\n\n"
        + workspace_memo
        + (f"\n\nHANDOFF TASK:\n{handoff_msg}" if handoff_msg else "")
        + ws_restored_note
        + "\n\nRESUME INSTRUCTIONS:\n"
        "- Read workspace context.md files above for full detail\n"
        "- Continue from the last documented next step\n"
        "- Keep workspace context.md files updated as you work\n"
        "- If the user gave you a task before the clear, pick it back up\n"
        "- If there is a HANDOFF TASK above, start on it immediately\n"
    )


def _consume_compaction_pending(home: Path) -> bool:
    """
    Check for a compaction-pending flag written by compaction-save.py.
    If present, consume it (one-shot) and return True so the caller can
    bypass the 15-char guard on the first post-compaction message.
    """
    flag_path = home / "state" / "compaction-pending.json"
    if not flag_path.exists():
        return False
    try:
        flag_path.unlink(missing_ok=True)
    except Exception:
        pass
    return True


# Steady state output. Short on purpose: the rules it points at are in
# CLAUDE.md, already in the cached prefix, and repeating them here is what
# cost 1,437 tokens a prompt.
POINTER = "ClaudeBoost active. Standing rules are in CLAUDE.md: always on rules, the research gate, CONSULT mode."

RAG_OFFLINE = (
    "clean-rag is OFFLINE. Start it with /rag, or "
    "`clean-rag/cli/server_ctl.py start`. Until it is up, say so rather than "
    "quietly falling back to grep and whole file reads."
)

RAG_BACK = "clean-rag is back online. Search it before reading files."

# How long to wait before trying to launch the server again, when it is down.
RECOVER_COOLDOWN_S = 120.0

COMPACTION_NOTE = (
    "Context was just compacted. Re-read the workspace context.md before "
    "continuing, and pick up from the last documented next step."
)

CONSULT_ON = (
    "CONSULT mode is now ON. Architectural decisions need an explicit yes "
    "first (see Collaborative Mode in CLAUDE.md)."
)

CONSULT_OFF = (
    "AUTO mode is now ON. Proceed autonomously on architectural decisions, "
    "still citing sources."
)


def _dashboard_signature(dashboard: str) -> str:
    """
    Hash only the part of the workspace dashboard that reflects real state.

    The candidate list at the top is ranked by keyword overlap with the current
    message, so it reorders as the conversation moves even when nothing about
    the workspace changed. Hashing it would make the dashboard look different
    on every prompt and defeat the whole point of emitting deltas.
    """
    marker = 'ACTIVE WORKSPACE:'
    idx = dashboard.find(marker)
    return _digest(dashboard[idx:] if idx != -1 else dashboard)


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    data = read_payload(raw)

    prompt = data.get("prompt", "").strip()
    home = _get_home()

    boost_mode = _get_boost_injection_mode(home)
    if boost_mode == "false":
        return 0

    # Both flags are one shot and must be consumed even if we emit nothing
    # else, so read them before the short prompt guard.
    clear_context = _consume_clear_pending(home)
    compaction_pending = _consume_compaction_pending(home)

    if len(prompt) < 15 and not clear_context and not compaction_pending:
        return 0

    session_key = _session_key(data)
    last = read_state("primer", session_key)
    first_prompt = not last

    # Ask the server rather than trusting the sentinel file. _try_auto_recover_rag
    # touches that sentinel optimistically, before the daemon has finished
    # booting, so a launch that never succeeds reads as healthy forever. Under
    # the old always inject behavior that only cost a wrong line on an otherwise
    # identical block; now it would mean the offline warning fires once and can
    # never fire again for the rest of the session.
    #
    # boost "true" means skip the health check, not skip the deltas.
    now = time.time()
    recover_ts = float(last.get("recover_ts") or 0)
    rag_status = None
    rag_online = True
    if boost_mode != "true":
        rag_status = _get_rag_status()
        rag_online = rag_status is not None
        if not rag_online and now - recover_ts > RECOVER_COOLDOWN_S:
            # Throttled: without this, every prompt while the server is down
            # spawns another launcher.
            _try_auto_recover_rag(home)
            recover_ts = now

    consult = consult_mode_active(home)

    ws_info = _find_best_workspace(home, prompt)
    ws_id, ws_path = ws_info[0], ws_info[1]
    dashboard = _active_workspace_reminder(home, rag_status, prompt, ws_info=ws_info)
    ws_sig = _dashboard_signature(dashboard) if dashboard else ''

    parts: list[str] = []

    if clear_context:
        parts.append(clear_context)
    elif compaction_pending:
        parts.append(COMPACTION_NOTE)

    if rag_online != last.get("rag"):
        if not rag_online:
            parts.append(RAG_OFFLINE)
        elif not first_prompt:
            # Coming back up is worth one line. Being up on the first prompt of
            # a session is the normal case and needs no announcement.
            parts.append(RAG_BACK)

    if not first_prompt and consult != last.get("consult"):
        parts.append(CONSULT_ON if consult else CONSULT_OFF)

    if dashboard and ws_sig != last.get("ws_sig"):
        parts.append(dashboard)

    write_state("primer", session_key, {
        "rag": rag_online,
        "consult": consult,
        "ws": ws_id,
        "ws_sig": ws_sig,
        "recover_ts": recover_ts,
    })

    if not parts:
        parts.append(POINTER)

    print(json.dumps({"additionalContext": "\n\n".join(parts)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
