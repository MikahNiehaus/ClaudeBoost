#!/usr/bin/env python3
"""ClaudeBoost Changes Viewer - TUI for reviewing code changes with explanations."""

import json
import sys
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.widgets import Footer, Header, RichLog, Static, Tree
from textual.widgets.tree import TreeNode


STATUS_ICONS = {
    "modified": "[M]",
    "added": "[A]",
    "deleted": "[D]",
}

STATUS_COLORS = {
    "modified": "yellow",
    "added": "green",
    "deleted": "red",
}


def load_changes(path: str) -> dict[str, Any]:
    """Load and validate the changes JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    # Ensure required keys with defaults
    data.setdefault("summary", {})
    data.setdefault("files", [])
    data.setdefault("project", "Unknown")
    data["summary"].setdefault("files_changed", len(data["files"]))
    data["summary"].setdefault("lines_added", 0)
    data["summary"].setdefault("lines_removed", 0)
    data["summary"].setdefault("agents", [])
    for f in data["files"]:
        f.setdefault("path", "unknown")
        f.setdefault("status", "modified")
        f.setdefault("agent", "")
        f.setdefault("summary", "")
        f.setdefault("hunks", [])
    return data


def build_summary_markup(data: dict[str, Any]) -> str:
    """Build Rich markup string for the summary panel."""
    s = data["summary"]
    project = data.get("project", "Unknown")
    agents = ", ".join(f"[cyan]{a}[/cyan]" for a in s["agents"]) or "[dim]none[/dim]"
    lines = [
        f"[bold]Project:[/bold] {project}   "
        f"[bold]Files changed:[/bold] {s['files_changed']}   "
        f"[green]+{s['lines_added']}[/green]  "
        f"[red]-{s['lines_removed']}[/red]",
        f"[bold]Agents:[/bold] {agents}",
    ]
    ts = data.get("generated_at", "")
    if ts:
        lines[0] += f"   [dim]{ts}[/dim]"
    return "\n".join(lines)


def build_diff_content(file_data: dict[str, Any]) -> Text:
    """Build a Rich Text object for the diff view of a single file."""
    text = Text()
    path = file_data["path"]
    status = file_data["status"]
    agent = file_data.get("agent", "")
    summary = file_data.get("summary", "")
    icon = STATUS_ICONS.get(status, "[?]")
    color = STATUS_COLORS.get(status, "white")

    text.append(f" {icon} ", style=f"bold {color}")
    text.append(path, style="bold white")
    if agent:
        text.append(f"  ({agent})", style="dim cyan")
    text.append("\n")
    if summary:
        text.append(f" {summary}\n", style="dim")
    text.append("\n")

    hunks = file_data.get("hunks", [])
    if not hunks:
        text.append(" No hunks recorded.\n", style="dim")
        return text

    for i, hunk in enumerate(hunks):
        header = hunk.get("header", "")
        if header:
            text.append(f" {header}\n", style="bold cyan")

        old_code = hunk.get("old_code", "")
        new_code = hunk.get("new_code", "")

        if old_code:
            for line in old_code.splitlines():
                text.append(f" - {line}\n", style="#ff4444 on #1a0000")
        if new_code:
            for line in new_code.splitlines():
                text.append(f" + {line}\n", style="#44ff44 on #001a00")

        explanation = hunk.get("explanation", "")
        if explanation:
            text.append("\n")
            text.append(f"   {explanation}\n", style="#6a9955")
        text.append("\n")

    return text


class ChangesViewer(App):
    """TUI application for viewing ClaudeBoost code changes."""

    TITLE = "ClaudeBoost Changes"
    CSS_PATH = "changes-viewer.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "go_back", "Back", show=True),
    ]

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        self.data = data
        self._file_lookup: dict[str, dict[str, Any]] = {}
        for f in data["files"]:
            self._file_lookup[f["path"]] = f

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(build_summary_markup(self.data), id="summary")
        yield Tree("Changed Files", id="file-tree")
        yield ScrollableContainer(RichLog(id="diff-log", highlight=True, markup=False), id="diff-view")
        yield Footer()

    def on_mount(self) -> None:
        tree: Tree = self.query_one("#file-tree", Tree)
        tree.show_root = True
        tree.root.expand()

        # Group files by directory
        dirs: dict[str, list[dict[str, Any]]] = {}
        for f in self.data["files"]:
            parts = f["path"].rsplit("/", 1)
            if len(parts) == 2:
                dirname, filename = parts
            else:
                dirname, filename = ".", parts[0]
            dirs.setdefault(dirname, []).append(f)

        for dirname in sorted(dirs.keys()):
            dir_node = tree.root.add(f"[bold]{dirname}/[/bold]", expand=True)
            for f in dirs[dirname]:
                filename = f["path"].rsplit("/", 1)[-1]
                status = f["status"]
                icon = STATUS_ICONS.get(status, "[?]")
                color = STATUS_COLORS.get(status, "white")
                agent = f.get("agent", "")
                agent_str = f"  [dim cyan]({agent})[/dim cyan]" if agent else ""
                label = f"[{color}]{icon}[/{color}] {filename}{agent_str}"
                node = dir_node.add_leaf(label)
                node.data = f["path"]

        # Start with diff view hidden
        self.query_one("#diff-view").display = False

    @on(Tree.NodeSelected, "#file-tree")
    def on_tree_select(self, event: Tree.NodeSelected) -> None:
        node: TreeNode = event.node
        if node.data is None:
            return
        file_path = node.data
        file_data = self._file_lookup.get(file_path)
        if file_data is None:
            return

        diff_log: RichLog = self.query_one("#diff-log", RichLog)
        diff_log.clear()
        diff_log.write(build_diff_content(file_data))

        self.query_one("#file-tree").display = False
        self.query_one("#diff-view").display = True
        diff_log.focus()

    def action_go_back(self) -> None:
        """Return from diff view to file tree."""
        diff_view = self.query_one("#diff-view")
        file_tree = self.query_one("#file-tree")
        if diff_view.display:
            diff_view.display = False
            file_tree.display = True
            file_tree.focus()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/changes-viewer.py <path-to-changes.json>", file=sys.stderr)
        sys.exit(1)
    data = load_changes(sys.argv[1])
    app = ChangesViewer(data)
    app.run()


if __name__ == "__main__":
    main()
