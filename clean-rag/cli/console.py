"""A live console for the clean-rag server.

Replaces the plain scrolling log with a status header, a table of indexed
projects, and tabs for the log and the views that have no data behind them yet.

Runs as its own process and talks to the server only over HTTP and the log file,
so it starts, stops and crashes without touching the server. Launch it with:

    python clean-rag/cli/console.py

Textual is an optional dependency. The import is guarded so nothing else in the
tree breaks on a machine that never installed it.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_CLEAN_RAG_HOME = Path(__file__).resolve().parent.parent
if str(_CLEAN_RAG_HOME) not in sys.path:
    sys.path.insert(0, str(_CLEAN_RAG_HOME))

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import (
        Button, DataTable, Footer, Header, Label, RichLog, Static, TabbedContent, TabPane,
    )
except ImportError:  # noqa: BLE001 - the message matters more than the traceback
    print(
        "This console needs textual. Install it with:\n"
        "    python -m pip install 'textual>=8.2,<9.0'\n"
        "or reinstall clean-rag's requirements.",
        file=sys.stderr,
    )
    raise SystemExit(1)

from rich.text import Text  # noqa: E402

from cli.log_tail import LogTail  # noqa: E402
from server.config import STANDALONE_PORT, STATE_DIR  # noqa: E402

BASE_URL = f"http://127.0.0.1:{STANDALONE_PORT}"
SERVER_LOG = STATE_DIR / "server.log"

STATUS_EVERY_S = 3.0
LOG_EVERY_S = 0.5


def _get(path: str, timeout: float = 4.0):
    """Return parsed JSON from the server, or None when it does not answer."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _post(path: str, body: dict, timeout: float = 4.0):
    """Return (status, parsed body); status is None when the server is unreachable."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None, None


def _age(iso: str) -> str:
    """A short human age for an ISO timestamp, or a dash."""
    if not iso:
        return "-"
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return "-"
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    secs = (datetime.now(timezone.utc) - then).total_seconds()
    if secs < 90:
        return f"{int(secs)}s"
    if secs < 5400:
        return f"{int(secs // 60)}m"
    if secs < 172800:
        return f"{int(secs // 3600)}h"
    return f"{int(secs // 86400)}d"


def _state_of(entry: dict, busy_path: str) -> Text:
    """INDEXING, INDEXED or EMPTY.

    Age is deliberately not a state. Reindexing is incremental and keyed on
    content hashes, so a project last touched a month ago is correctly indexed,
    not stale, as long as nothing in it changed.
    """
    path = entry.get("project_path", "")
    if busy_path and path and Path(busy_path) == Path(path):
        return Text("INDEXING", style="bold yellow")
    if not entry.get("files_indexed"):
        return Text("EMPTY", style="bold red")
    return Text("INDEXED", style="green")


def _lock_state() -> tuple[str, str]:
    """(operation, project_path) from the index lock, or empty strings."""
    try:
        data = json.loads((STATE_DIR / "index-lock.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("operation") or "indexing"), str(data.get("project") or "")


def _age_style(iso: str) -> str:
    """Green when it was indexed recently, red once it is a week stale."""
    if not iso:
        return "dim"
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return "dim"
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - then).total_seconds() / 3600
    if hours < 24:
        return "bold green"
    if hours < 168:
        return "yellow"
    return "red"


def _num(value: int, zero_is_odd: bool = False) -> Text:
    """A right aligned count, dimmed at zero because zero usually means a gap."""
    if value == 0:
        return Text("0", style="red" if zero_is_odd else "dim", justify="right")
    return Text(f"{value:,}", justify="right")


def _level_of(line: str) -> str:
    """The log level in a line, for colouring."""
    if " ERROR" in line or "Traceback" in line:
        return "err"
    if " WARNING" in line:
        return "warn"
    if " DEBUG" in line:
        return "dim"
    return ""


class EmptyView(Static):
    """A view with no data behind it, saying so rather than inventing rows."""

    def __init__(self, title: str, why: str, where: str) -> None:
        super().__init__()
        self._title, self._why, self._where = title, why, where

    def render(self) -> str:
        return (
            f"[b]{self._title} is not recorded yet.[/b]\n\n"
            f"{self._why}\n\n"
            f"[dim]Where it would come from: {self._where}[/dim]"
        )


class ConsoleApp(App):
    TITLE = "clean-rag"
    CSS = """
    Screen { layout: vertical; background: $surface; }

    #bar {
        height: 3;
        padding: 0 2;
        background: $panel;
        border-bottom: tall $primary;
        align: left middle;
    }
    #bar Label {
        width: auto;
        height: 3;
        margin-right: 4;
        content-align: left middle;
    }
    /* Textual's default Button draws a tall border, which reads as a white box
       inside a blue block. Flatten it to a single filled chip. */
    #bar #pause {
        dock: right;
        width: auto;
        min-width: 18;
        height: 1;
        margin: 1 0;
        padding: 0 2;
        border: none;
        background: $primary 25%;
        color: $text;
        text-style: bold;
    }
    #bar #pause:hover { background: $primary 45%; }
    #bar #pause.-paused { background: $warning 30%; color: $warning; }

    .ok   { color: $success; text-style: bold; }
    .bad  { color: $error;   text-style: bold; }
    .warn { color: $warning; text-style: bold; }

    TabbedContent { height: 1fr; }
    TabPane { padding: 0; }
    DataTable {
        height: 1fr;
        background: $surface;
    }
    DataTable > .datatable--header {
        background: $panel;
        color: $accent;
        text-style: bold;
    }
    DataTable > .datatable--cursor { background: $accent 30%; }
    RichLog { height: 1fr; background: $surface; padding: 0 1; }
    EmptyView { padding: 2 4; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_pause", "Pause indexing"),
        ("r", "refresh_now", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._tail = LogTail(SERVER_LOG)
        self._rows: set[str] = set()
        self._paused = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="bar"):
            yield Label("connecting", id="state")
            yield Label("", id="models")
            yield Label("", id="ram")
            yield Label("", id="projects")
            yield Button("Pause indexing", id="pause", variant="primary")
        with TabbedContent(initial="tab-indexed"):
            with TabPane("Indexed", id="tab-indexed"):
                yield DataTable(id="projects-table", zebra_stripes=True)
            with TabPane("Ignored", id="tab-ignored"):
                yield EmptyView(
                    "Ignored files",
                    "scan_project() applies SKIP_DIRS, SKIP_FILES, SKIP_SUFFIXES and a "
                    "500 KB cap by never yielding those paths, so nothing records what "
                    "was skipped or why.",
                    "server/file_scan.py would have to report its skips.",
                )
            with TabPane("Issues", id="tab-issues"):
                yield EmptyView(
                    "Indexing issues",
                    "Only unreadable files are recorded, as UNREADABLE_SENTINEL in each "
                    "project's manifest. An embed or store failure increments a count "
                    "and logs free text; the filename is never kept.",
                    "an append only jsonl in state/, like search-log.jsonl.",
                )
            with TabPane("Logs", id="tab-logs"):
                yield RichLog(id="log", highlight=False, markup=True, wrap=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#projects-table", DataTable)
        table.cursor_type = "row"
        # Two projects share the name AscendMobile and two share Nectar, so the
        # parent directory is what tells them apart.
        for key, label, width in (
            ("state", "State", 9),
            ("project", "Project", 24),
            ("where", "Directory", 30),
            ("files", "Files", 9),
            ("chunks", "Chunks", 10),
            ("edges", "Edges", 10),
            ("nodes", "Nodes", 9),
            ("age", "Indexed", 9),
        ):
            table.add_column(label, key=key, width=width)

        self.query_one("#log", RichLog).write("[dim]waiting for the server...[/dim]")
        self.set_interval(STATUS_EVERY_S, self.refresh_status)
        self.set_interval(LOG_EVERY_S, self.drain_log)
        self.call_after_refresh(self.refresh_status)

    def refresh_status(self) -> None:
        data = _get("/status")
        state = self.query_one("#state", Label)

        if data is None:
            state.update("OFFLINE")
            state.set_classes("bad")
            for wid in ("#models", "#ram", "#projects"):
                self.query_one(wid, Label).update("")
            return

        state.update(str(data.get("status", "?")).upper())
        state.set_classes("ok" if data.get("status") == "ready" else "warn")

        models = data.get("loaded_models") or []
        short = ", ".join(m.split("/")[-1] for m in models) or "none loaded"
        self.query_one("#models", Label).update(f"[dim]models[/dim] {short}")
        self.query_one("#ram", Label).update(f"[dim]ram[/dim] {data.get('ram_mb', 0):,.0f} MB")

        projects = (data.get("projects") or {}).get("entries") or {}
        operation, busy_path = _lock_state()
        label = (
            f"[dim]projects[/dim] {len(projects)}  [b yellow]INDEXING[/b yellow] "
            f"[dim]{operation}[/dim]"
            if operation
            else f"[dim]projects[/dim] {len(projects)}  [dim]idle[/dim]"
        )
        self.query_one("#projects", Label).update(label)
        self._fill(projects, busy_path)

    def _fill(self, projects: dict, busy_path: str = "") -> None:
        """Update cells in place so the cursor and scroll position survive."""
        table = self.query_one("#projects-table", DataTable)
        for pid, entry in projects.items():
            graph = entry.get("graph") or {}
            path = Path(entry.get("project_path", pid))
            indexed_at = entry.get("indexed_at", "")
            parent = str(path.parent)
            if len(parent) > 31:
                parent = "..." + parent[-28:]

            values = {
                "state": _state_of(entry, busy_path),
                "project": Text(path.name or pid, style="bold"),
                "where": Text(parent, style="dim"),
                "files": _num(entry.get("files_indexed", 0), zero_is_odd=True),
                "chunks": _num(entry.get("chunks_created", 0), zero_is_odd=True),
                "edges": _num(graph.get("edges_total", 0)),
                "nodes": _num(graph.get("pagerank_nodes", 0)),
                "age": Text(_age(indexed_at), style=_age_style(indexed_at)),
            }
            if pid not in self._rows:
                table.add_row(*values.values(), key=pid)
                self._rows.add(pid)
            else:
                for col, val in values.items():
                    table.update_cell(pid, col, val)

    def drain_log(self) -> None:
        log = self.query_one("#log", RichLog)
        for line in self._tail.poll():
            level = _level_of(line)
            log.write(f"[{level}]{line}[/{level}]" if level else line)

    def action_refresh_now(self) -> None:
        self.refresh_status()

    def action_toggle_pause(self) -> None:
        self.on_button_pressed(None)

    def on_button_pressed(self, _event) -> None:
        """Ask the server to flip the flag, then show whatever it reports back."""
        want = not self._paused
        status, body = _post("/sweep-pause", {"paused": want})
        button = self.query_one("#pause", Button)

        if status is None:
            self.notify("Server is not answering.", severity="error")
            return
        if status == 404:
            self.notify(
                "The server has no /sweep-pause route yet, so indexing cannot be "
                "paused from here.",
                severity="warning",
                timeout=8,
            )
            return

        # The server's answer wins, so the button shows the truth if it refuses.
        self._paused = bool((body or {}).get("paused", want))
        button.label = "Resume indexing" if self._paused else "Pause indexing"
        button.set_class(self._paused, "-paused")

        if not self._paused:
            self.notify("Indexing resumed.")
            return

        # Says "released", not "freed". Measured 2026-09-17: evicting drops RSS
        # by about 4 MB, because torch pools freed blocks rather than returning
        # them. What eviction buys is a ceiling, since the next load reuses that
        # pool, not memory back now.
        freed = len((body or {}).get("models_evicted") or [])
        still = (body or {}).get("indexing_project") or ""
        msg = f"Indexing paused. {freed} model(s) released."
        if still:
            msg += f" {Path(still).name} finishes first."
        self.notify(msg, timeout=7)


def main() -> int:
    ConsoleApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
