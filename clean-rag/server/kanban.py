"""Portable kanban board for Claude Code tasks.

Watches ~/.claude/projects/ for task JSON files and streams updates to a
browser via SSE. Served from clean-rag at /kanban (board UI), /kanban/tasks
(JSON snapshot), and /kanban/events (SSE stream).

No npm, no Node.js. Pure Python backend, self contained HTML frontend.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp_sse import EventSourceResponse

logger = logging.getLogger(__name__)

# Claude Code stores tasks at ~/.claude/tasks/<session-uuid>/<id>.json
# Each file is a single JSON object: {id, subject, description, status, blocks, blockedBy}
CLAUDE_DIR = Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude"))
TASKS_DIR = CLAUDE_DIR / "tasks"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# How often the poll loop checks for changes (seconds)
POLL_INTERVAL = 2.0

# Cache for session project paths (session_uuid -> project_path)
# TTL of 10s to avoid re-reading JSONL on every poll cycle.
_project_path_cache: dict[str, tuple[float, str | None]] = {}
_PROJECT_PATH_TTL = 10.0


def _get_project_path(session_uuid: str) -> str | None:
    """Extract the project working dir from the session's JSONL transcript.

    Reads the first 64KB of the matching JSONL file under ~/.claude/projects/
    to find the cwd field. Results are cached with a 10s TTL.
    """
    now = time.time()
    cached = _project_path_cache.get(session_uuid)
    if cached and (now - cached[0]) < _PROJECT_PATH_TTL:
        return cached[1]

    result = None
    if PROJECTS_DIR.exists():
        for project_dir in PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue
            jsonl_path = project_dir / f"{session_uuid}.jsonl"
            if jsonl_path.exists():
                try:
                    with jsonl_path.open(encoding="utf-8") as fh:
                        # Read first 64KB only, enough for early metadata lines
                        chunk = fh.read(65536)
                    for line in chunk.split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            cwd = data.get("cwd")
                            if cwd:
                                result = cwd
                                break
                        except json.JSONDecodeError:
                            continue
                except OSError:
                    pass
                break  # Found the session file, no need to keep searching

    _project_path_cache[session_uuid] = (now, result)
    return result


def _find_task_files() -> list[Path]:
    """Find all task JSON files across all Claude Code sessions."""
    results = []
    if not TASKS_DIR.exists():
        return results
    for session_dir in TASKS_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        for f in session_dir.glob("*.json"):
            results.append(f)
    return results


def _parse_task(path: Path) -> dict[str, Any] | None:
    """Parse a single Claude Code task file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(raw, dict):
        return None

    # Skip internal tasks
    meta = raw.get("metadata") or {}
    if meta.get("_internal"):
        return None

    session = path.parent.name

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0

    project = _get_project_path(session)

    return {
        "id": raw.get("id", path.stem),
        "subject": raw.get("subject", raw.get("content", "")),
        "description": raw.get("description"),
        "active_form": raw.get("activeForm"),
        "status": raw.get("status", "pending"),
        "blocks": raw.get("blocks", []),
        "blocked_by": raw.get("blockedBy", []),
        "session": session[:12],
        "session_full": session,
        "project": project,
        "project_name": Path(project).name if project else None,
        "file": str(path),
        "mtime": mtime,
    }


def _scan_all_tasks() -> list[dict[str, Any]]:
    """Scan all task files and return parsed tasks."""
    tasks = []
    for path in _find_task_files():
        task = _parse_task(path)
        if task:
            tasks.append(task)
    # Most recent files first
    tasks.sort(key=lambda t: t.get("mtime", 0), reverse=True)
    return tasks


# SSE client tracking
_sse_clients: list[EventSourceResponse] = []


async def _broadcast(event: str, data: dict) -> None:
    """Send an SSE event to all connected clients. Remove dead ones."""
    payload = json.dumps(data)
    dead = []
    for client in _sse_clients:
        try:
            await client.send(payload, event=event)
        except BaseException:
            dead.append(client)
            logger.debug("SSE client disconnected during broadcast")
    for client in dead:
        try:
            client.stop_streaming()
        except BaseException:
            logger.error("Failed to stop dead SSE client during broadcast", exc_info=True)
        if client in _sse_clients:
            _sse_clients.remove(client)


async def _poll_loop() -> None:
    """Poll task directories for changes and broadcast updates.

    Uses file modification times to detect changes. Cheaper than watchdog
    and avoids the thread-to-asyncio bridge complexity on Windows.
    """
    last_snapshot: dict[str, float] = {}

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            current: dict[str, float] = {}
            for path in _find_task_files():
                try:
                    current[str(path)] = path.stat().st_mtime
                except OSError:
                    continue

            # Detect changes
            changed = False
            if current != last_snapshot:
                changed = True
                last_snapshot = current

            if changed and _sse_clients:
                tasks = _scan_all_tasks()
                await _broadcast("tasks", {"tasks": tasks, "ts": time.time()})

        except asyncio.CancelledError:
            # If the poll task itself is cancelled (shutdown), propagate.
            # Otherwise a stray cancellation leaked from _broadcast cleanup.
            if asyncio.current_task() and asyncio.current_task().cancelling() > 0:
                raise
            logger.error("Kanban poll caught stray CancelledError, continuing",
                         exc_info=True)
        except Exception:
            logger.error("Kanban poll error", exc_info=True)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def handle_kanban_page(request: web.Request) -> web.Response:
    """Serve the kanban board HTML."""
    html_path = Path(__file__).parent / "kanban.html"
    if not html_path.exists():
        return web.Response(text="kanban.html not found", status=404)
    return web.Response(
        text=html_path.read_text(encoding="utf-8"),
        content_type="text/html",
    )


async def handle_kanban_tasks(request: web.Request) -> web.Response:
    """Return JSON snapshot of all current tasks."""
    tasks = _scan_all_tasks()
    return web.Response(
        text=json.dumps({"tasks": tasks, "count": len(tasks)}, indent=2),
        content_type="application/json",
    )


async def handle_kanban_events(request: web.Request) -> EventSourceResponse:
    """SSE endpoint for real time task updates."""
    resp = EventSourceResponse()
    await resp.prepare(request)

    _sse_clients.append(resp)
    logger.info("Kanban SSE client connected (%d total)", len(_sse_clients))

    # Send initial snapshot
    tasks = _scan_all_tasks()
    try:
        await resp.send(
            json.dumps({"tasks": tasks, "ts": time.time()}),
            event="tasks",
        )
    except (ConnectionResetError, ConnectionError):
        if resp in _sse_clients:
            _sse_clients.remove(resp)
        return resp

    # Keep connection alive until client disconnects
    try:
        await resp.wait()
    except (asyncio.CancelledError, ConnectionResetError, ConnectionError):
        pass
    finally:
        if resp in _sse_clients:
            _sse_clients.remove(resp)
        logger.info("Kanban SSE client disconnected (%d remaining)", len(_sse_clients))

    return resp


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_kanban(app: web.Application) -> None:
    """Register kanban routes and start the background poll loop."""

    app.router.add_get("/kanban", handle_kanban_page)
    app.router.add_get("/kanban/tasks", handle_kanban_tasks)
    app.router.add_get("/kanban/events", handle_kanban_events)

    async def _start_kanban(app: web.Application) -> None:
        app["kanban_poll_task"] = asyncio.create_task(_poll_loop())
        logger.info("Kanban board available at /kanban")

    async def _stop_kanban(app: web.Application) -> None:
        task = app.get("kanban_poll_task")
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # Clean up SSE clients
        for client in _sse_clients[:]:
            try:
                client.stop_streaming()
            except Exception:
                logger.error("Failed to stop SSE client during shutdown", exc_info=True)
        _sse_clients.clear()
        logger.info("Kanban poll loop stopped")

    app.on_startup.append(_start_kanban)
    app.on_shutdown.append(_stop_kanban)
