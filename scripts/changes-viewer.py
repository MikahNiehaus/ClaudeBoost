#!/usr/bin/env python3
"""ClaudeBoost Changes Viewer - TUI for reviewing code changes with explanations."""

import json
import re
import sys
from pathlib import Path
from typing import Any

from rich.syntax import Syntax
from rich.style import Style
from rich.text import Text, Span
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.reactive import reactive
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

# File extension to Syntax lexer name mapping
EXT_TO_LEXER = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".cs": "csharp",
    ".xml": "xml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".toml": "toml",
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


def parse_hunk_header(header: str) -> tuple[int, int]:
    """Parse @@ -old_start,count +new_start,count @@ to get starting line numbers."""
    m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", header)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 1, 1


def count_file_changes(file_data: dict[str, Any]) -> tuple[int, int]:
    """Count total additions and removals for a file from its hunks."""
    added = 0
    removed = 0
    for hunk in file_data.get("hunks", []):
        old_code = hunk.get("old_code", "")
        new_code = hunk.get("new_code", "")
        if old_code:
            removed += len(old_code.splitlines())
        if new_code:
            added += len(new_code.splitlines())
    return added, removed


def get_lexer_for_path(file_path: str) -> str:
    """Determine syntax lexer from file extension."""
    ext = Path(file_path).suffix.lower()
    return EXT_TO_LEXER.get(ext, "text")


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
    goal = data.get("goal", "")
    if goal:
        lines.append(f"[bold]Goal:[/bold] {goal}")
    return "\n".join(lines)


def highlight_code_line(line: str, lexer: str, bg_color: str | None = None) -> Text:
    """Apply syntax highlighting to a single code line with an optional background tint.

    Extracts foreground colors from the monokai theme and applies them on top of
    the given background color (e.g. red tint for removals, green for additions).
    """
    if lexer == "text" or not line.strip():
        t = Text(line)
        if bg_color:
            t.stylize(Style(bgcolor=bg_color))
        return t
    try:
        syntax = Syntax(line, lexer, theme="monokai", background_color=None)
        ht = syntax.highlight(line)
        plain = ht.plain.rstrip("\n")
        # Extract only foreground colors from syntax spans, drop monokai bg
        new_spans = []
        for span in ht._spans:
            fg = span.style.color
            if fg:
                new_spans.append(Span(span.start, min(span.end, len(plain)), Style(color=fg)))
        result = Text(plain)
        result._spans = new_spans
        if bg_color:
            result.stylize(Style(bgcolor=bg_color))
        return result
    except Exception:
        t = Text(line)
        if bg_color:
            t.stylize(Style(bgcolor=bg_color))
        return t


def build_diff_content(
    file_data: dict[str, Any],
    show_explanations: bool = True,
    collapsed_hunks: set[int] | None = None,
) -> Text:
    """Build a Rich Text object for the diff view of a single file."""
    text = Text()
    path = file_data["path"]
    status = file_data["status"]
    agent = file_data.get("agent", "")
    summary = file_data.get("summary", "")
    icon = STATUS_ICONS.get(status, "[?]")
    color = STATUS_COLORS.get(status, "white")
    lexer = get_lexer_for_path(path)

    if collapsed_hunks is None:
        collapsed_hunks = set()

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

    total_hunks = len(hunks)
    for i, hunk in enumerate(hunks):
        header = hunk.get("header", "")
        old_start, new_start = parse_hunk_header(header)

        # Hunk header line (acts as toggle indicator)
        collapse_marker = "▸" if i in collapsed_hunks else "▾"
        if header:
            text.append(f" {collapse_marker} ", style="bold white")
            text.append(f"Hunk {i + 1}/{total_hunks}  ", style="bold #00ff41")
            text.append(f"{header}\n", style="bold cyan")

        if i in collapsed_hunks:
            text.append("   [collapsed]\n\n", style="dim")
            continue

        old_code = hunk.get("old_code", "")
        new_code = hunk.get("new_code", "")
        old_line = old_start
        new_line = new_start

        # Line number column widths
        ln_width = 5

        if old_code:
            for line in old_code.splitlines():
                ln_old = str(old_line).rjust(ln_width)
                ln_new = " " * ln_width
                text.append(f" {ln_old} {ln_new} ", style="dim #666666")
                text.append("- ", style="#ff4444 on #1a0000")
                hl = highlight_code_line(line, lexer, bg_color="#1a0000")
                text.append_text(hl)
                text.append("\n")
                old_line += 1

        if new_code:
            for line in new_code.splitlines():
                ln_old = " " * ln_width
                ln_new = str(new_line).rjust(ln_width)
                text.append(f" {ln_old} {ln_new} ", style="dim #666666")
                text.append("+ ", style="#44ff44 on #001a00")
                hl = highlight_code_line(line, lexer, bg_color="#001a00")
                text.append_text(hl)
                text.append("\n")
                new_line += 1

        if show_explanations:
            explanation = hunk.get("explanation", "")
            if explanation:
                text.append("\n")
                text.append(f"   {explanation}\n", style="#6a9955")
        text.append("\n")

    return text


class Breadcrumb(Static):
    """Clickable breadcrumb navigation bar for the diff view."""

    DEFAULT_CSS = """
    Breadcrumb {
        height: 1;
        padding: 0 1;
        background: #111111;
        color: #666666;
    }
    Breadcrumb:hover {
        background: #1a1a1a;
    }
    """

    def set_path(self, file_path: str) -> None:
        parts = file_path.rsplit("/", 1)
        if len(parts) == 2:
            dirname, filename = parts
            markup = f"[bold #00ff41]<[/bold #00ff41] [dim]Changed Files > {dirname}/ >[/dim] [bold #00ff41]{filename}[/bold #00ff41]"
        else:
            markup = f"[bold #00ff41]<[/bold #00ff41] [dim]Changed Files >[/dim] [bold #00ff41]{parts[0]}[/bold #00ff41]"
        self.update(markup)

    def on_click(self) -> None:
        """Navigate back to file tree when breadcrumb is clicked."""
        self.app.action_go_back()


class HunkIndicator(Static):
    """Shows current hunk position like 'Hunk 2/5'."""

    DEFAULT_CSS = """
    HunkIndicator {
        height: 1;
        padding: 0 1;
        background: #111111;
        color: #00ff41;
        text-align: right;
    }
    """

    def set_hunk(self, current: int, total: int) -> None:
        if total > 0:
            self.update(f"Hunk {current}/{total}")
        else:
            self.update("")


class ChangesViewer(App):
    """TUI application for viewing ClaudeBoost code changes."""

    TITLE = "ClaudeBoost Changes"
    CSS_PATH = "changes-viewer.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "go_back", "Back", show=True),
        Binding("n", "next_hunk", "Next hunk", show=True),
        Binding("p", "prev_hunk", "Prev hunk", show=True),
        Binding("e", "toggle_explanations", "Explanations", show=True),
        Binding("c", "toggle_collapse", "Collapse hunk", show=True),
    ]

    show_explanations: reactive[bool] = reactive(True)

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        self.data = data
        self._file_lookup: dict[str, dict[str, Any]] = {}
        for f in data["files"]:
            self._file_lookup[f["path"]] = f
        self._current_file: dict[str, Any] | None = None
        self._current_hunk_index: int = 0
        self._total_hunks: int = 0
        self._collapsed_hunks: set[int] = set()
        self._hunk_line_offsets: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(build_summary_markup(self.data), id="summary")
        yield Tree("Changed Files", id="file-tree")
        yield Vertical(
            Breadcrumb(id="breadcrumb"),
            HunkIndicator(id="hunk-indicator"),
            ScrollableContainer(
                RichLog(id="diff-log", highlight=True, markup=False),
                id="diff-scroll",
            ),
            id="diff-view",
        )
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
                # Per-file +/- counts
                added, removed = count_file_changes(f)
                counts = ""
                if added > 0:
                    counts += f"  [green]+{added}[/green]"
                if removed > 0:
                    counts += f"  [red]-{removed}[/red]"
                label = f"[{color}]{icon}[/{color}] {filename}{counts}{agent_str}"
                node = dir_node.add_leaf(label)
                node.data = f["path"]

        # Start with diff view hidden
        self.query_one("#diff-view").display = False

    def _render_diff(self) -> None:
        """Re-render the diff view for the current file."""
        if self._current_file is None:
            return
        diff_log: RichLog = self.query_one("#diff-log", RichLog)
        diff_log.clear()
        content = build_diff_content(
            self._current_file,
            show_explanations=self.show_explanations,
            collapsed_hunks=self._collapsed_hunks,
        )
        diff_log.write(content)

        # Update hunk indicator
        indicator: HunkIndicator = self.query_one("#hunk-indicator", HunkIndicator)
        if self._total_hunks > 0:
            indicator.set_hunk(self._current_hunk_index + 1, self._total_hunks)
        else:
            indicator.set_hunk(0, 0)

    def _show_file(self, file_data: dict[str, Any]) -> None:
        """Display a file's diff view."""
        self._current_file = file_data
        self._total_hunks = len(file_data.get("hunks", []))
        self._current_hunk_index = 0
        self._collapsed_hunks = set()

        # Set breadcrumb
        breadcrumb: Breadcrumb = self.query_one("#breadcrumb", Breadcrumb)
        breadcrumb.set_path(file_data["path"])

        self._render_diff()

        self.query_one("#file-tree").display = False
        self.query_one("#diff-view").display = True
        self.query_one("#diff-log", RichLog).focus()

    @on(Tree.NodeSelected, "#file-tree")
    def on_tree_select(self, event: Tree.NodeSelected) -> None:
        node: TreeNode = event.node
        if node.data is None:
            return
        file_path = node.data
        file_data = self._file_lookup.get(file_path)
        if file_data is None:
            return
        self._show_file(file_data)

    def action_go_back(self) -> None:
        """Return from diff view to file tree."""
        diff_view = self.query_one("#diff-view")
        file_tree = self.query_one("#file-tree")
        if diff_view.display:
            diff_view.display = False
            file_tree.display = True
            file_tree.focus()
            self._current_file = None

    def action_next_hunk(self) -> None:
        """Jump to the next hunk in the diff view."""
        if self._current_file is None or self._total_hunks == 0:
            return
        if self._current_hunk_index < self._total_hunks - 1:
            self._current_hunk_index += 1
            indicator: HunkIndicator = self.query_one("#hunk-indicator", HunkIndicator)
            indicator.set_hunk(self._current_hunk_index + 1, self._total_hunks)
            self._scroll_to_hunk(self._current_hunk_index)

    def action_prev_hunk(self) -> None:
        """Jump to the previous hunk in the diff view."""
        if self._current_file is None or self._total_hunks == 0:
            return
        if self._current_hunk_index > 0:
            self._current_hunk_index -= 1
            indicator: HunkIndicator = self.query_one("#hunk-indicator", HunkIndicator)
            indicator.set_hunk(self._current_hunk_index + 1, self._total_hunks)
            self._scroll_to_hunk(self._current_hunk_index)

    def _scroll_to_hunk(self, hunk_index: int) -> None:
        """Scroll the diff log to show a specific hunk."""
        if self._current_file is None:
            return
        # Calculate approximate line offset for the target hunk
        # Header lines + file summary = ~3 lines, then each hunk has header + code + explanation
        hunks = self._current_file.get("hunks", [])
        line_offset = 3  # file header, summary, blank line
        for i in range(hunk_index):
            if i in self._collapsed_hunks:
                line_offset += 3  # header + collapsed + blank
                continue
            hunk = hunks[i]
            line_offset += 1  # hunk header
            old_code = hunk.get("old_code", "")
            new_code = hunk.get("new_code", "")
            if old_code:
                line_offset += len(old_code.splitlines())
            if new_code:
                line_offset += len(new_code.splitlines())
            if self.show_explanations and hunk.get("explanation", ""):
                line_offset += 3  # blank + explanation + blank
            else:
                line_offset += 1  # blank
        # Scroll the container
        scroll_container = self.query_one("#diff-scroll", ScrollableContainer)
        # Approximate: each line is ~1.5 units height, scroll to the offset
        scroll_container.scroll_to(y=max(0, line_offset - 2), animate=True)

    def action_toggle_explanations(self) -> None:
        """Toggle showing/hiding explanation text."""
        if self._current_file is None:
            return
        self.show_explanations = not self.show_explanations
        self._render_diff()
        self.sub_title = f"Explanations: {'ON' if self.show_explanations else 'OFF'}"

    def action_toggle_collapse(self) -> None:
        """Toggle collapse on the current hunk."""
        if self._current_file is None or self._total_hunks == 0:
            return
        idx = self._current_hunk_index
        if idx in self._collapsed_hunks:
            self._collapsed_hunks.discard(idx)
        else:
            self._collapsed_hunks.add(idx)
        self._render_diff()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/changes-viewer.py <path-to-changes.json>", file=sys.stderr)
        sys.exit(1)
    data = load_changes(sys.argv[1])
    app = ChangesViewer(data)
    app.run()


if __name__ == "__main__":
    main()
