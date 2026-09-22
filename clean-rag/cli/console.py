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
from pathlib import Path

_CLEAN_RAG_HOME = Path(__file__).resolve().parent.parent
if str(_CLEAN_RAG_HOME) not in sys.path:
    sys.path.insert(0, str(_CLEAN_RAG_HOME))

try:
    from textual.app import App, ComposeResult
    from textual.containers import Grid, Horizontal, Vertical
    from textual.screen import ModalScreen
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
from cli.single_instance import already_running  # noqa: E402
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


# There is deliberately no age or staleness column here.
#
# Reindexing is incremental and keyed on content hashes, so a project last
# touched a month ago is correctly indexed, not stale, as long as nothing in it
# changed. An age column coloured red past a week says the opposite, and says it
# about the normal case.
#
# "Currently indexing" is the live signal worth having, and _state_of provides
# it from the index lock.


def _state_of(entry: dict, busy_path: str) -> Text:
    """INDEXING, INDEXED or EMPTY.

    Age is deliberately not a state. Reindexing is incremental and keyed on
    content hashes, so a project last touched a month ago is correctly indexed,
    not stale, as long as nothing in it changed.
    """
    path = entry.get("project_path", "")
    if busy_path and path and Path(busy_path) == Path(path):
        return Text("INDEXING", style="bold yellow")

    # files_total, not files_indexed. files_indexed counts one run, so a
    # project whose last sweep found nothing changed wrote 0 and rendered
    # EMPTY while holding thousands of vectors. ContosoMobile showed EMPTY on
    # 1,072 vectors and 1,486 edges. The column headers at :356 were renamed
    # to "Run files" after the same misreading, and this cell was missed.
    #
    # /status omits files_total when it could not read the project's manifest,
    # so the fallback runs on an unreadable manifest and nothing else.
    # chunks_created and the graph counts are both real liveness signals, and a
    # project with neither and no run count really is empty.
    total = entry.get("files_total")
    if total is None:
        graph = entry.get("graph") or {}
        total = (
            entry.get("files_indexed")
            or entry.get("chunks_created")
            or graph.get("pagerank_nodes")
            or graph.get("edges_total")
        )
    if not total:
        return Text("EMPTY", style="bold red")
    return Text("INDEXED", style="green")


def _delete_summary(project_path: str, body) -> tuple[str, str]:
    """What to tell the user after a delete the server accepted.

    A directory the server could not erase is not an error, because the index
    is out of reach either way. Saying nothing about it would still be wrong:
    the disk is not back yet, and deleting again is what clears it.
    """
    body = body or {}
    removed = len(body.get("dirs_removed") or [])
    stranded = len(body.get("dirs_left_on_disk") or [])
    message = (
        f"Deleted the index of {Path(project_path).name}. "
        f"{removed} director(ies) removed."
    )
    if not stranded:
        return message, "information"
    return (
        f"{message} {stranded} of them still hold disk because something has "
        f"the files open. Deleting again clears them.",
        "warning",
    )


def _lock_state() -> tuple[str, str]:
    """(operation, project_path) from the index lock, or empty strings."""
    try:
        data = json.loads((STATE_DIR / "index-lock.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("operation") or "indexing"), str(data.get("project") or "")


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


class ConfirmScreen(ModalScreen[bool]):
    """Yes/no dialog. Dismisses with True only if the user pressed the red one.

    Cloned from Textual's own docs/examples/guide/screens/modal01.py, with the
    three changes a returning modal needs: ModalScreen[bool] instead of Screen,
    dismiss(bool) instead of app.exit()/pop_screen(), and the caller's wording.

    The `align: center middle` rule below is load bearing. A ModalScreen with
    no alignment renders its dialog in the top left corner rather than over the
    page, which reads as a broken overlay.
    """

    CSS = """
    ConfirmScreen { align: center middle; }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 1 2;
        width: 66;
        height: 13;
        border: thick $background 80%;
        background: $surface;
    }
    #question { column-span: 2; height: 1fr; width: 1fr; content-align: center middle; }
    ConfirmScreen Button { width: 100%; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, question: str, confirm_label: str = "Delete") -> None:
        super().__init__()
        self._question = question
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(self._question, id="question"),
            Button(self._confirm_label, variant="error", id="confirm"),
            Button("Cancel", variant="primary", id="cancel"),
            id="dialog",
        )

    def on_mount(self) -> None:
        # Cancel takes focus, so a stray Enter cancels rather than deletes.
        self.query_one("#cancel", Button).focus()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


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

    /* Same flattened chip as #pause, in the error colour because it destroys
       something. Docked right too, so it sits left of Pause rather than in the
       middle of the status labels. */
    #bar #delete {
        dock: right;
        width: auto;
        min-width: 14;
        height: 1;
        margin: 1 2 1 0;
        padding: 0 2;
        border: none;
        background: $error 22%;
        color: $text;
        text-style: bold;
    }
    #bar #delete:hover { background: $error 45%; }

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
        ("d", "delete_selected", "Delete index"),
        ("r", "refresh_now", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._tail = LogTail(SERVER_LOG)
        self._rows: set[str] = set()
        #: pid -> project_path. The table stores display text, not the real
        #: path, and the Directory column is truncated from the left to fit.
        #: Sending that truncated string to the server would delete nothing.
        self._paths: dict[str, str] = {}
        self._paused = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="bar"):
            yield Label("connecting", id="state")
            yield Label("", id="models")
            yield Label("", id="ram")
            yield Label("", id="projects")
            yield Button("Delete index", id="delete", variant="error")
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
        # Two projects share the name ContosoMobile and two share Litware, so the
        # parent directory is what tells them apart.
        for key, label, width in (
            ("state", "State", 9),
            ("project", "Project", 24),
            ("where", "Directory", 30),
            # "Run files", not "Files". files_indexed counts only what a single
            # run processed, which indexing.py:1110 says in its own comment, and
            # chunks_created is the same. Labelling them as totals made the
            # table read 1 file for a project whose manifest holds 458.
            ("files", "Run files", 10),
            ("chunks", "Run chunks", 11),
            ("edges", "Edges", 10),
            ("nodes", "Nodes", 9),
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
            }
            self._paths[pid] = str(path)
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
        self._toggle_pause()

    def action_delete_selected(self) -> None:
        """Confirm, then ask the server to delete the highlighted project."""
        table = self.query_one("#projects-table", DataTable)
        try:
            pid = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:  # noqa: BLE001 - an empty table has no cell to resolve
            pid = None
        if not pid:
            self.notify("Select a project row first.", severity="warning")
            return

        path = self._paths.get(pid)
        if not path:
            self.notify("That row has no project path yet.", severity="warning")
            return

        def _go(confirmed: bool | None) -> None:
            # The key, not the cursor index. _fill updates rows on a 3 second
            # timer, so an index captured when the dialog opened can point at a
            # different project by the time the dialog closes.
            if confirmed:
                self._delete_project(pid, path)

        self.push_screen(
            ConfirmScreen(
                f"Delete clean-rag's index of\n{path}?\n\n"
                f"The project's own files are not touched.",
            ),
            _go,
        )

    def _delete_project(self, pid: str, path: str) -> None:
        status, body = _post("/delete-project", {"project_path": path, "confirm": True})

        if status is None:
            self.notify("Server is not answering.", severity="error")
            return
        if status == 404:
            self.notify(
                "The server has no /delete-project route, or does not know that "
                "project. Restart the server if you just updated it.",
                severity="warning", timeout=8,
            )
            return
        if status == 423:
            self.notify(
                "Indexing holds the lock right now. Try again in a moment.",
                severity="warning",
            )
            return
        if status != 200:
            self.notify(
                str((body or {}).get("error") or f"Delete failed ({status})."),
                severity="error", timeout=10,
            )
            return

        # The row goes only after the server says it went. Dropping it on click
        # would show a delete that did not happen.
        table = self.query_one("#projects-table", DataTable)
        try:
            table.remove_row(pid)
        except Exception:  # noqa: BLE001 - the next refresh rebuilds it anyway
            pass
        self._rows.discard(pid)
        self._paths.pop(pid, None)

        message, severity = _delete_summary(path, body)
        self.notify(message, severity=severity)
        self.refresh_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Route by which button. Without this every button ran pause."""
        if event.button.id == "delete":
            self.action_delete_selected()
        elif event.button.id == "pause":
            self._toggle_pause()

    def _toggle_pause(self) -> None:
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

        # The message says evicted and names the limit out loud, because torch
        # pools the blocks it frees rather than handing them back. Measured
        # 2026-09-17: evicting drops RSS by about 4 MB. What eviction buys is a
        # ceiling, since the next load reuses that pool, not memory back now.
        # An earlier version said "released", which reads as "freed" and sent
        # someone to Task Manager expecting gigabytes.
        evicted = len((body or {}).get("models_evicted") or [])
        still = (body or {}).get("indexing_project") or ""
        msg = (
            f"Indexing paused. {evicted} model(s) evicted, which caps growth. "
            "RAM already in use will not drop much."
        )
        if still:
            msg += f" {Path(still).name} finishes first."
        self.notify(msg, timeout=7)


def main() -> int:
    if already_running(_CLEAN_RAG_HOME):
        print(
            "A clean-rag console is already open for this checkout. "
            "Switch to that window instead of opening a second one.",
            file=sys.stderr,
        )
        return 0
    ConsoleApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
