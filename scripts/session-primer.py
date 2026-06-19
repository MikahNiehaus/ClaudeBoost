"""
ClaudeBoost session primer — UserPromptSubmit command hook.

Injects a compact, imperative behavior briefing into Claude's context
before every substantive user message. Acts as standing orders that
re-surface at the start of each turn before Claude decides anything.

Also handles /clear recovery: if /clear-safe wrote state/clear-pending.json
before the clear, this script injects the saved workspace context on the
first message after /clear (regardless of prompt length).

Skips:
- Short prompts (<15 chars) when no clear-pending flag is present

Boost injection modes (state/boost-injection.json):
- "false"  — skip all injection entirely
- "true"   — inject always-on rules only, skip RAG verification
- "verify" — (default) full RAG-gated behavior

Always-on rules (A-H) inject in both "true" and "verify" modes:
A. Tasks first — create tasks before multi-step work
B. Human voice
C. Code comments, no dashes
D. Architectural approval before changes
E. RAG usage when available
F. Workspace update when one exists
G. Dynamic RAG tiers — project_path/workspace_path params and what each enables
H. Irreversible actions — stop and confirm before anything that can't be undone

RAG standing orders (1-8) only inject in "verify" mode when RAG is confirmed online.

Workspace dashboard injects when active-workspace.json resolves to a real path (any mode):
- Live tier status: codebase index (checked via GET /status) + research index (directory check)
- REQUIRED directives when indexes are missing, with exact skill to run
- Exact POST /context params to use this session (including task_description from user message)
- Self-clearing: once an index is built, its directive disappears automatically
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
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


def _get_rag_status(timeout: float = 0.2) -> dict | None:
    """Quick GET /status. Returns status dict or None if unreachable or slow."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8612/status", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _find_claude_pid_windows() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import ctypes.wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize",              ctypes.wintypes.DWORD),
                ("cntUsage",            ctypes.wintypes.DWORD),
                ("th32ProcessID",       ctypes.wintypes.DWORD),
                ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID",        ctypes.wintypes.DWORD),
                ("cntThreads",          ctypes.wintypes.DWORD),
                ("th32ParentProcessID", ctypes.wintypes.DWORD),
                ("pcPriClassBase",      ctypes.c_long),
                ("dwFlags",             ctypes.wintypes.DWORD),
                ("szExeFile",           ctypes.c_char * 260),
            ]

        snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == ctypes.wintypes.HANDLE(-1).value:
            return None

        process_map: dict[int, tuple[int, str]] = {}
        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(entry)):
                while True:
                    pid  = entry.th32ProcessID
                    ppid = entry.th32ParentProcessID
                    exe  = entry.szExeFile.decode("utf-8", errors="replace").lower()
                    process_map[pid] = (ppid, exe)
                    if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(entry)):
                        break
        finally:
            ctypes.windll.kernel32.CloseHandle(snap)

        claude_exec = os.environ.get("CLAUDE_CODE_EXECPATH", "").replace("\\", "/").lower()
        target_exe = claude_exec.split("/")[-1] if claude_exec else "node.exe"

        pid = os.getpid()
        seen: set[int] = set()
        for _ in range(20):
            if pid in seen or pid not in process_map:
                break
            seen.add(pid)
            ppid, _ = process_map[pid]
            if ppid not in process_map:
                break
            _, parent_exe = process_map[ppid]
            if target_exe in parent_exe or "node" in parent_exe:
                return ppid
            pid = ppid

        return None
    except Exception:
        return None


def _get_instance_id() -> str:
    node_pid = _find_claude_pid_windows()
    if node_pid:
        return f"node-{node_pid}"
    env_id = os.environ.get("CLAUDEBOOST_INSTANCE_ID", "")
    if env_id:
        return env_id
    return f"ppid-{os.getppid()}"


def _get_cached_rag_status(timeout: float = 0.2) -> dict | None:
    """GET /status with a 60s per-process cache. Skips the round-trip on every prompt."""
    import time
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    cache_path = Path(temp) / f"claudeboost_status_cache_{os.getpid()}.json"
    _CACHE_TTL = 60.0
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if time.time() - float(raw.get("_ts", 0)) < _CACHE_TTL:
            return raw.get("status")
    except Exception:
        pass
    status = _get_rag_status(timeout)
    if status is not None:
        try:
            cache_path.write_text(json.dumps({"_ts": time.time(), "status": status}), encoding="utf-8")
        except Exception:
            pass
    return status


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
    1. project-workspaces.json keyed by CWD — authoritative human-set signal
    2. Keyword scoring + recency across project-scoped workspaces only (CWD filter)
    3. No cross-project bleed — workspaces from other projects are excluded

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

    cwd_norm = os.getcwd().replace('\\', '/').rstrip('/')

    # Check per-instance file first — CWD-keyed map, unique per Claude window, survives compaction
    instance_id = _get_instance_id()
    try:
        inst_path = home / 'state' / 'ws-instance' / f'{instance_id}.json'
        data = json.loads(inst_path.read_text(encoding='utf-8'))
        if 'workspace_id' not in data:
            # New format: {cwd: workspace_id}
            ws_id = data.get(cwd_norm)
            if ws_id is None:
                cwd_lower = cwd_norm.lower()
                for key, val in data.items():
                    if isinstance(val, str) and key.replace('\\', '/').rstrip('/').lower() == cwd_lower:
                        ws_id = val
                        break
        else:
            # Old format: only use if stored CWD matches
            stored = data.get('cwd', '').replace('\\', '/').rstrip('/')
            ws_id = data.get('workspace_id') if stored.lower() == cwd_norm.lower() else None
        if ws_id and isinstance(ws_id, str):
            entry = reg.get(ws_id, {})
            ws_path = entry.get('workspace_path', '')
            project_path = entry.get('project_path', '')
            if ws_path:
                return ws_id, ws_path, project_path, []
    except Exception:
        pass

    # Check project-workspaces.json — authoritative per-project pointer (shared fallback)
    try:
        pws = json.loads((home / 'state' / 'project-workspaces.json').read_text(encoding='utf-8'))
        ws_id = pws.get(cwd_norm)
        if ws_id is None:
            cwd_lower = cwd_norm.lower()
            for key, val in pws.items():
                if key.replace('\\', '/').rstrip('/').lower() == cwd_lower:
                    ws_id = val
                    break
        if ws_id and isinstance(ws_id, str):
            entry = reg.get(ws_id, {})
            ws_path = entry.get('workspace_path', '')
            project_path = entry.get('project_path', '')
            if ws_path:
                return ws_id, ws_path, project_path, []
    except Exception:
        pass

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
    if not t3c_exists:
        req_num = len(required_actions) + 1
        required_actions.append(
            f"  [{req_num}] RESEARCH NOT BUILT - run Skill(skill='research-task', args='{ws_id}')"
            f" as your FIRST action. Tier 5 task research is offline until built."
        )
    if project_path and not project_kb_exists:
        req_num = len(required_actions) + 1
        required_actions.append(
            f"  [{req_num}] PROJECT KB NOT BUILT - run Skill(skill='research-project', args='{project_path}')"
            f" to build the project knowledge base. Agents will lack project-specific context until it exists."
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
        'RAG TIER STATUS:',
        f'  Tiers 3+4 (codebase):  {codebase_detail}',
        f'  Tier 5  (research):    {t3c_detail}',
        f'  Project KB:            {project_kb_detail}',
        '',
        'HOW TO USE THIS SESSION:',
    ]

    ctx_desc = task_description[:120].replace('"', "'") if task_description else "[user's current message]"
    if project_path and ws_path:
        lines += [
            '  Every POST /context call MUST use these exact params:',
            f'    project_path     = "{project_path}"',
            f'    workspace_path   = "{ws_path}"',
            f'    task_description = "{ctx_desc}"',
        ]
    elif project_path:  # pragma: no cover
        lines += [
            '  Every POST /context call MUST include:',
            f'    project_path     = "{project_path}"',
            f'    task_description = "{ctx_desc}"',
        ]

    lines += [
        "  Always use the user's actual message as task_description - NOT 'session start'.",
        '  Every agent spawn: call POST /context as FIRST action in the spawn prompt.',
        '  Codebase search: ALWAYS run BOTH mode=vector AND mode=graph for every codebase query —',
        '  vector finds semantic matches, graph finds structural neighbours; NEVER run only one.',
        '  New finding? Update workspace/context.md before moving on.',
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
    Auto-recover when sentinel is missing.

    First checks if the server is already up (common: sentinel deleted at SessionStart
    but the long-running server daemon is still healthy). If it responds, writes the
    sentinel and returns True.

    If the server is down, launches rag-server-start.py in the background and writes
    the sentinel optimistically — the server will be ready within a few seconds.
    Returns True on launch, False only if the start script itself can't be found.
    """
    # Fast path: server already running — just write the sentinel
    if _get_rag_status(timeout=1.0) is not None:
        try:
            _sentinel_path().touch()
        except Exception:
            pass
        return True

    # Slow path: server is down — launch it as a detached background process
    start_script = home / "scripts" / "rag-server-start.py"
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
        subprocess.Popen([python, str(start_script)], **kwargs)
        # Write sentinel optimistically — server will be up within ~5s
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

    return (
        "POST-CLEAR CONTEXT RESTORATION\n"
        "===============================\n\n"
        "You just returned from a /clear. Below is your saved working state "
        "(written by /clear-safe immediately before the clear).\n\n"
        + workspace_memo
        + "\n\nRESUME INSTRUCTIONS:\n"
        "- Read workspace context.md files above for full detail\n"
        "- Continue from the last documented next step\n"
        "- Keep workspace context.md files updated as you work\n"
        "- If the user gave you a task before the clear, pick it back up\n"
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


def main() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    prompt = data.get("prompt", "").strip()
    home = _get_home()

    boost_mode = _get_boost_injection_mode(home)

    # boost false: skip all injection entirely
    if boost_mode == "false":
        return 0

    # Always check for clear-pending flag — inject even on short prompts like "continue"
    clear_context = _consume_clear_pending(home)

    # Check for compaction-pending flag — bypass 15-char guard after compaction too
    compaction_pending = _consume_compaction_pending(home)

    # Skip standing orders for short prompts unless a post-clear or post-compaction flag is set
    if len(prompt) < 15 and not clear_context and not compaction_pending:
        return 0

    # Always-inject rules: fire regardless of RAG state
    always_inject = (
        "ALWAYS-ON RULES (apply to every response): "
        "(A) TASKS FIRST — before doing any work that involves more than one action, call TaskCreate. "
        "This is not optional. If the user's request can be broken into steps, create tasks before starting. "
        "Mark each task in_progress when you begin it. Mark it completed the moment you finish it — not in a batch at the end. "
        "Never forget a step because it was not tracked. Tasks are your memory. Use them. "
        "(B) Human voice — every word you write must sound like a human wrote it. "
        "Use contractions. Vary sentence length. Start with the substance. "
        "Never use: delve, leverage, utilize, seamless, robust, comprehensive, "
        "pivotal, facilitate, harness, foster, transformative, paradigm, synergy, holistic, empower. "
        "Never open with: Certainly!, Great question!, Absolutely!, Furthermore,, Moreover,, "
        "It's worth noting, In today's rapidly evolving. "
        "No em-dashes. Rewrite as separate sentences instead. "
        "No hyphenated compound jargon (no-go, hard-block, soft-fail, non-trivial). "
        "Say what you mean in plain words instead. "
        "(C) Code comments — non-formal but professional, concise, say why not what. "
        "No dashes of any kind in comments (no hyphens as separators, no em dashes, no double dashes). "
        "(D) Architectural changes — before making any architectural change (new class, endpoint, "
        "table, schema, service, or pattern): (1) stop completely, (2) explain in plain terms "
        "what you are changing, why, and what the impact is, (3) use AskUserQuestion to get "
        "explicit YES confirmation — not a vague ok or continued conversation. "
        "The user must understand the change before you proceed, not just acknowledge it. "
        "This applies in CONSULT mode (default). In AUTO mode this check is skipped. "
        "(E) RAG usage — when RAG is available, always call POST http://127.0.0.1:8612/search before reading files or grepping. "
        "For scope=codebase queries, ALWAYS run BOTH mode=vector AND mode=graph — vector finds semantic matches, graph finds structural neighbours; NEVER run only one. "
        "Never substitute grep or Read for RAG when RAG is online. "
        "If RAG is erroring or unavailable, stop and fix it (run /rag to start the server). "
        "Do not skip RAG and fall back to file reads — fix the connection first, then proceed. "
        "(F) Workspace update — if a workspace context.md exists for the current task, "
        "update it after each meaningful finding or decision. "
        "Do not let findings accumulate in context only. "
        "(G) Dynamic RAG tiers — POST /context loads knowledge in layers. "
        "project_path enables Tier 3 stack-boosted knowledge + Tier 4 codebase search. "
        "workspace_path enables Tier 3c task research (built by /research-task). "
        "Omit a param and that tier is skipped. "
        "Always pass both when you have them. "
        "If no workspace exists yet, pass project_path alone to get Tier 3 + Tier 4. "
        "(H) Irreversible actions — before doing ANYTHING that cannot be undone "
        "(deleting files, dropping tables, force-pushing, overwriting data, sending messages, "
        "publishing to external services, running destructive shell commands), STOP. "
        "Tell the user exactly what you are about to do and why it cannot be undone. "
        "Use AskUserQuestion to get explicit YES confirmation before proceeding. "
        "If uncertain whether an action is reversible, treat it as irreversible and ask. "
        "Prefer safe reversible alternatives whenever one exists — soft deletes over hard deletes, "
        "backups before overwrites, dry-runs before destructive commands."
    )

    # Find active workspace first — only call GET /status when one exists.
    # The HTTP call blocks for up to timeout seconds and is only needed to check
    # codebase index state in the dashboard. Skip it when there's no active workspace.
    ws_info = _find_best_workspace(home, prompt)
    rag_status = _get_cached_rag_status() if (ws_info[1] and rag_verified()) else None
    workspace_reminder = _active_workspace_reminder(home, rag_status, prompt, ws_info=ws_info)

    def _emit(ctx: str) -> int:
        full = (ctx + "\n\n" + workspace_reminder) if workspace_reminder else ctx
        print(json.dumps({"additionalContext": full}))
        return 0

    # Standing orders fire on every message — no RAG sentinel required.
    # The user should not need to run /rag just to receive workflow rules.
    standing_orders = (
        "RAG STANDING ORDERS (non-negotiable): "
        "(1) RAG before files — POST http://127.0.0.1:8612/search before Read/Grep. "
        "(2) Health check — at start of any investigation, call GET http://127.0.0.1:8612/status. "
        "If unresolved edges or errors, stop and fix before continuing. "
        "(3) Write findings — after each RAG search or file read that reveals something, "
        "update workspace/[task-id]/context.md with what you found before moving on. "
        "Do not accumulate findings in your head; write them down as you go. "
        "(4) Cite file:line — for every finding. "
        "(5) Evaluator — spawn evaluator-agent, never self-verify. "
        "(6) RAG context first — call POST http://127.0.0.1:8612/context as first step in every agent spawn prompt. "
        "(7) RAG dual-mode — for every scope=codebase query, run BOTH mode=vector (semantic) AND mode=graph (structural neighbours) — never run only one. "
        "Use /context for knowledge; /search?scope=codebase with both modes for codebase work. "
        "When RAG errors mid-task, fix it (run /rag to start the server) — never skip RAG and "
        "substitute grep or file reads. "
        "(8) RAG offline = STOP — if any RAG MCP tool is unavailable or errors, "
        "do NOT self-recover by searching files; tell the user RAG is offline and wait."
    )

    if consult_mode_active(home):
        standing_orders += (
            " (CONSULT MODE IS ACTIVE) You must NOT make architectural decisions without express user permission. "
            "This includes: new endpoints, tables, dependencies, modules, middleware, auth strategies, "
            "API designs, config changes, concurrency models, or any structural change. "
            "Before proposing: explain what you want to do and why in plain language the user can understand. "
            "Then use AskUserQuestion — wait for an explicit YES before touching anything. "
            "A vague ok, continue, or non-response is NOT approval. "
            "If you are unsure whether something counts as architectural, treat it as if it does and ask."
        )

    # boost true: inject always-on rules + standing orders, skip RAG verification
    if boost_mode == "true":
        base = (clear_context + "\n\n") if clear_context else ""
        return _emit(base + always_inject + "\n\n" + standing_orders)

    # Post-clear restore path — bypass RAG hard-stop.
    # rag-session-reset.py unconditionally deletes the sentinel at every SessionStart,
    # so rag_verified() is always false on the first post-clear message. Blocking on
    # RAG here means auto-restore can never work. Inject context directly with a soft nudge.
    if clear_context and not rag_verified():
        _try_auto_recover_rag(home)
        # Fall through whether recovery succeeded or not — restore context is more important
        # than a RAG warning on a post-clear message.

    if not rag_verified():
        recovered = _try_auto_recover_rag(home)
        if not recovered:
            context = (
                "NOTE: RAG could not be started automatically. Run /rag manually before spawning agents "
                "or starting any multi-step investigation."
                "\n\n" + always_inject + "\n\n" + standing_orders
            )
            return _emit(context)
        # Auto-recovered — fall through to normal path below

    # RAG verified — full context, no warning needed
    base = (clear_context + "\n\n") if clear_context else ""
    return _emit(base + always_inject + "\n\n" + standing_orders)


if __name__ == "__main__":
    sys.exit(main())
