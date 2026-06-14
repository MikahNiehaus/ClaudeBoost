#!/usr/bin/env python3
"""ClaudeBoost Changes Core - Shared logic for all themed change viewers."""

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
from textual.widgets import Footer, Header, Input, RichLog, Static, Tree
from textual.widgets.tree import TreeNode
import tempfile
import threading
import time


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


def build_summary_markup(
    data: dict[str, Any],
    colors: dict[str, str] | None = None,
) -> str:
    """Build Rich markup string for the summary panel.

    Args:
        data: The changes data dict.
        colors: Optional color scheme override with keys:
            'agent' - color for agent names (default 'cyan')
            'added' - color for additions (default 'green')
            'removed' - color for removals (default 'red')
            'dim' - color for dim text (default 'dim')
            'label' - style for labels (default 'bold')
    """
    if colors is None:
        colors = {}
    agent_color = colors.get("agent", "cyan")
    added_color = colors.get("added", "green")
    removed_color = colors.get("removed", "red")
    dim_style = colors.get("dim", "dim")
    label_style = colors.get("label", "bold")

    s = data["summary"]
    project = data.get("project", "Unknown")
    agents = ", ".join(
        f"[{agent_color}]{a}[/{agent_color}]" for a in s["agents"]
    ) or f"[{dim_style}]none[/{dim_style}]"
    lines = [
        f"[{label_style}]Project:[/{label_style}] {project}   "
        f"[{label_style}]Files changed:[/{label_style}] {s['files_changed']}   "
        f"[{added_color}]+{s['lines_added']}[/{added_color}]  "
        f"[{removed_color}]-{s['lines_removed']}[/{removed_color}]",
        f"[{label_style}]Agents:[/{label_style}] {agents}",
    ]
    ts = data.get("generated_at", "")
    if ts:
        lines[0] += f"   [{dim_style}]{ts}[/{dim_style}]"
    goal = data.get("goal", "")
    if goal:
        lines.append(f"[{label_style}]Goal:[/{label_style}] {goal}")
    return "\n".join(lines)


def highlight_code_line(line: str, lexer: str, bg_color: str | None = None) -> Text:
    """Apply syntax highlighting to a single code line with an optional background tint."""
    if lexer == "text" or not line.strip():
        t = Text(line)
        if bg_color:
            t.stylize(Style(bgcolor=bg_color))
        return t
    try:
        syntax = Syntax(line, lexer, theme="monokai", background_color=None)
        ht = syntax.highlight(line)
        plain = ht.plain.rstrip("\n")
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
    theme: dict[str, str] | None = None,
) -> Text:
    """Build a Rich Text object for the diff view of a single file.

    Args:
        file_data: Single file dict from changes JSON.
        show_explanations: Whether to show hunk explanations.
        collapsed_hunks: Set of hunk indices that are collapsed.
        theme: Optional color/style overrides with keys:
            'status_icon_style' - style for status icon (default based on status)
            'path_style' - style for file path (default 'bold white')
            'agent_style' - style for agent name (default 'dim cyan')
            'summary_style' - style for file summary (default 'dim')
            'hunk_marker_style' - style for collapse marker (default 'bold white')
            'hunk_label_style' - style for hunk label (default 'bold #00ff41')
            'hunk_header_style' - style for @@ header (default 'bold cyan')
            'line_num_style' - style for line numbers (default 'dim #666666')
            'removed_prefix_style' - style for '-' prefix (default '#ff4444 on #1a0000')
            'removed_bg' - background color for removed lines (default '#1a0000')
            'added_prefix_style' - style for '+' prefix (default '#44ff44 on #001a00')
            'added_bg' - background color for added lines (default '#001a00')
            'explanation_style' - style for explanation text (default '#6a9955')
            'collapsed_style' - style for [collapsed] text (default 'dim')
            'hunk_label_prefix' - text before hunk number (default 'Hunk')
            'explanation_prefix' - prefix for explanation lines (default '   ')
    """
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

    if theme is None:
        theme = {}

    status_style = theme.get("status_icon_style", f"bold {color}")
    path_style = theme.get("path_style", "bold white")
    agent_style = theme.get("agent_style", "dim cyan")
    summary_style = theme.get("summary_style", "dim")
    hunk_marker_style = theme.get("hunk_marker_style", "bold white")
    hunk_label_style = theme.get("hunk_label_style", "bold #00ff41")
    hunk_header_style = theme.get("hunk_header_style", "bold cyan")
    line_num_style = theme.get("line_num_style", "dim #666666")
    removed_prefix_style = theme.get("removed_prefix_style", "#ff4444 on #1a0000")
    removed_bg = theme.get("removed_bg", "#1a0000")
    added_prefix_style = theme.get("added_prefix_style", "#44ff44 on #001a00")
    added_bg = theme.get("added_bg", "#001a00")
    explanation_style = theme.get("explanation_style", "#6a9955")
    collapsed_style = theme.get("collapsed_style", "dim")
    hunk_label_prefix = theme.get("hunk_label_prefix", "Hunk")
    explanation_prefix = theme.get("explanation_prefix", "   ")

    text.append(f" {icon} ", style=status_style)
    text.append(path, style=path_style)
    if agent:
        text.append(f"  ({agent})", style=agent_style)
    text.append("\n")
    if summary:
        text.append(f" {summary}\n", style=summary_style)
    text.append("\n")

    hunks = file_data.get("hunks", [])
    if not hunks:
        text.append(" No hunks recorded.\n", style=collapsed_style)
        return text

    total_hunks = len(hunks)
    for i, hunk in enumerate(hunks):
        header = hunk.get("header", "")
        old_start, new_start = parse_hunk_header(header)

        collapse_marker = "▸" if i in collapsed_hunks else "▾"
        if header:
            text.append(f" {collapse_marker} ", style=hunk_marker_style)
            text.append(f"{hunk_label_prefix} {i + 1}/{total_hunks}  ", style=hunk_label_style)
            text.append(f"{header}\n", style=hunk_header_style)

        if i in collapsed_hunks:
            text.append("   [collapsed]\n\n", style=collapsed_style)
            continue

        old_code = hunk.get("old_code", "")
        new_code = hunk.get("new_code", "")
        old_line = old_start
        new_line = new_start
        ln_width = 5

        if old_code:
            for line in old_code.splitlines():
                ln_old = str(old_line).rjust(ln_width)
                ln_new = " " * ln_width
                text.append(f" {ln_old} {ln_new} ", style=line_num_style)
                text.append("- ", style=removed_prefix_style)
                hl = highlight_code_line(line, lexer, bg_color=removed_bg)
                text.append_text(hl)
                text.append("\n")
                old_line += 1

        if new_code:
            for line in new_code.splitlines():
                ln_old = " " * ln_width
                ln_new = str(new_line).rjust(ln_width)
                text.append(f" {ln_old} {ln_new} ", style=line_num_style)
                text.append("+ ", style=added_prefix_style)
                hl = highlight_code_line(line, lexer, bg_color=added_bg)
                text.append_text(hl)
                text.append("\n")
                new_line += 1

        if show_explanations:
            explanation = hunk.get("explanation", "")
            if explanation:
                text.append("\n")
                text.append(f"{explanation_prefix}{explanation}\n", style=explanation_style)
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

    # Subclasses can override these for theming
    back_indicator: str = "<"
    accent_color: str = "#00ff41"
    dim_color: str = "dim"

    def set_path(self, file_path: str) -> None:
        parts = file_path.rsplit("/", 1)
        ac = self.accent_color
        dc = self.dim_color
        bi = self.back_indicator
        if len(parts) == 2:
            dirname, filename = parts
            markup = f"[bold {ac}]{bi}[/bold {ac}] [{dc}]Changed Files > {dirname}/ >[/{dc}] [bold {ac}]{filename}[/bold {ac}]"
        else:
            markup = f"[bold {ac}]{bi}[/bold {ac}] [{dc}]Changed Files >[/{dc}] [bold {ac}]{parts[0]}[/bold {ac}]"
        self.update(markup)

    def on_click(self) -> None:  # pragma: no cover
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

    hunk_label: str = "Hunk"

    def set_hunk(self, current: int, total: int) -> None:
        if total > 0:
            self.update(f"{self.hunk_label} {current}/{total}")
        else:
            self.update("")


CHAT_FILE = Path(tempfile.gettempdir()) / "claudeboost" / "changes_chat.json"


def get_chat_file() -> Path:
    """Get the chat file path, ensuring parent directory exists."""
    CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    return CHAT_FILE


def write_chat_question(question: str, context_file: str = "", context_code: str = "") -> None:
    """Write a question to the chat file for Claude to pick up."""
    chat = {
        "question": question,
        "context_file": context_file,
        "context_code": context_code,
        "asked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "answer": "",
        "answered_at": "",
    }
    get_chat_file().write_text(json.dumps(chat, indent=2), encoding="utf-8")


def read_chat_answer() -> str:
    """Read the answer from the chat file, if one has been written."""
    path = get_chat_file()
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("answer", "")
    except (json.JSONDecodeError, KeyError):
        return ""


class ChatPanel(Static):
    """Inline chat panel for asking questions about code.

    Automatically polls the chat file every 3 seconds for answers
    from Claude. No external polling loop needed.
    """

    DEFAULT_CSS = """
    ChatPanel {
        height: auto;
        max-height: 14;
        border-top: solid #00ff41;
        background: #0d0d0d;
        padding: 0 1;
    }
    """

    _waiting_for_answer: bool = False

    def compose(self) -> ComposeResult:  # pragma: no cover
        yield ScrollableContainer(
            Static("", id="chat-response"),
            id="chat-scroll",
        )
        yield Input(placeholder="Ask about this code...", id="chat-input")

    def on_mount(self) -> None:  # pragma: no cover
        """Start the 3-second answer poll timer."""
        self.set_interval(3, self._check_for_answer)

    def _check_for_answer(self) -> None:
        """Poll the chat file for an answer from Claude."""
        if not self._waiting_for_answer:
            return
        answer = read_chat_answer()
        if answer:
            self._waiting_for_answer = False
            self.show_response(answer)

    def mark_waiting(self) -> None:
        """Mark that we're waiting for an answer."""
        self._waiting_for_answer = True
        self.show_response("")

    def show_response(self, text: str) -> None:  # pragma: no cover
        resp = self.query_one("#chat-response", Static)
        if text:
            resp.update(f"[#00ff41]◉ CLAUDE:[/#00ff41] {text}")
        else:
            resp.update("[dim]Waiting for response...[/dim]")

    def clear_response(self) -> None:  # pragma: no cover
        self._waiting_for_answer = False
        self.query_one("#chat-response", Static).update("")


class BaseChangesViewer(App):
    """Base TUI application for viewing ClaudeBoost code changes.

    Subclass and override:
        - TITLE, CSS_PATH
        - _get_summary_colors() -> dict for build_summary_markup
        - _get_diff_theme() -> dict for build_diff_content
        - _get_tree_label() -> str for root tree label
        - _format_file_label() -> str for file tree entries
        - _make_breadcrumb() -> Breadcrumb subclass instance
        - _make_hunk_indicator() -> HunkIndicator subclass instance
        - compose() if you need animation before the main view
    """

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
        self._reviewed_files: set[str] = set()
        self._tree_nodes: dict[str, TreeNode] = {}  # path -> tree node for label updates
        self._tree_built: bool = False  # guard: _build_tree() must only run once

    def _get_summary_colors(self) -> dict[str, str]:
        """Override to customize summary panel colors."""
        return {}

    def _get_diff_theme(self) -> dict[str, str]:
        """Override to customize diff view theme."""
        return {}

    def _get_tree_label(self) -> str:
        """Override to customize tree root label."""
        return "Changed Files"

    def _format_file_label(self, file_data: dict[str, Any], filename: str) -> str:
        """Override to customize file tree entry labels."""
        status = file_data["status"]
        icon = STATUS_ICONS.get(status, "[?]")
        color = STATUS_COLORS.get(status, "white")
        agent = file_data.get("agent", "")
        agent_str = f"  [dim cyan]({agent})[/dim cyan]" if agent else ""
        added, removed = count_file_changes(file_data)
        counts = ""
        if added > 0:
            counts += f"  [green]+{added}[/green]"
        if removed > 0:
            counts += f"  [red]-{removed}[/red]"
        return f"[{color}]{icon}[/{color}] {filename}{counts}{agent_str}"

    def _make_breadcrumb(self) -> Breadcrumb:
        """Override to return a themed breadcrumb widget."""
        return Breadcrumb(id="breadcrumb")

    def _make_hunk_indicator(self) -> HunkIndicator:
        """Override to return a themed hunk indicator widget."""
        return HunkIndicator(id="hunk-indicator")

    def compose(self) -> ComposeResult:  # pragma: no cover
        yield Header()
        yield Static(
            build_summary_markup(self.data, self._get_summary_colors()),
            id="summary",
        )
        yield Tree(self._get_tree_label(), id="file-tree")
        yield Vertical(
            self._make_breadcrumb(),
            self._make_hunk_indicator(),
            ScrollableContainer(
                RichLog(id="diff-log", highlight=True, markup=False),
                id="diff-scroll",
            ),
            ChatPanel(id="chat-panel"),
            id="diff-view",
        )
        yield Footer()

    def _build_tree(self) -> None:  # pragma: no cover
        """Populate the file tree. Guarded — only runs once regardless of how many times called."""
        if self._tree_built:
            return
        self._tree_built = True
        tree: Tree = self.query_one("#file-tree", Tree)
        tree.show_root = True
        tree.root.expand()

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
                label = self._format_file_label(f, filename)
                node = dir_node.add_leaf(label)
                node.data = f["path"]
                self._tree_nodes[f["path"]] = node

        self.query_one("#diff-view").display = False

    def on_mount(self) -> None:  # pragma: no cover
        self._build_tree()

    def _update_tree_labels(self) -> None:  # pragma: no cover
        """Update tree labels to show reviewed status."""
        for path, node in self._tree_nodes.items():
            file_data = self._file_lookup.get(path)
            if file_data is None:
                continue
            filename = path.rsplit("/", 1)[-1]
            label = self._format_file_label(file_data, filename)
            if path in self._reviewed_files:
                label = f"[bold cyan]✓[/bold cyan] {label}"
            node.set_label(label)
        # Force tree widget to re-render after label changes
        try:
            self.query_one("#file-tree", Tree).refresh()
        except Exception:
            pass

    def _render_diff(self) -> None:  # pragma: no cover
        if self._current_file is None:
            return
        diff_log: RichLog = self.query_one("#diff-log", RichLog)
        diff_log.clear()
        content = build_diff_content(
            self._current_file,
            show_explanations=self.show_explanations,
            collapsed_hunks=self._collapsed_hunks,
            theme=self._get_diff_theme(),
        )
        diff_log.write(content)

        indicator: HunkIndicator = self.query_one("#hunk-indicator", HunkIndicator)
        if self._total_hunks > 0:
            indicator.set_hunk(self._current_hunk_index + 1, self._total_hunks)
        else:
            indicator.set_hunk(0, 0)

    def _show_file(self, file_data: dict[str, Any]) -> None:  # pragma: no cover
        self._current_file = file_data
        self._total_hunks = len(file_data.get("hunks", []))
        self._current_hunk_index = 0
        self._collapsed_hunks = set()

        # Mark file as reviewed
        file_path = file_data["path"]
        self._reviewed_files.add(file_path)
        self._update_tree_labels()

        breadcrumb: Breadcrumb = self.query_one("#breadcrumb", Breadcrumb)
        breadcrumb.set_path(file_data["path"])

        # Clear chat from previous file
        try:
            chat_panel: ChatPanel = self.query_one("#chat-panel", ChatPanel)
            chat_panel.clear_response()
        except Exception:
            pass

        self._render_diff()

        self.query_one("#file-tree").display = False
        self.query_one("#diff-view").display = True
        self.query_one("#diff-log", RichLog).focus()

    @on(Tree.NodeSelected, "#file-tree")
    def on_tree_select(self, event: Tree.NodeSelected) -> None:
        node: TreeNode = event.node
        if node.data is None:
            return
        file_data = self._file_lookup.get(node.data)
        if file_data is None:
            return
        self._show_file(file_data)

    def action_go_back(self) -> None:  # pragma: no cover
        diff_view = self.query_one("#diff-view")
        file_tree = self.query_one("#file-tree")
        if diff_view.display:
            diff_view.display = False
            file_tree.display = True
            file_tree.focus()
            self._update_tree_labels()
            self._current_file = None

    def action_next_hunk(self) -> None:  # pragma: no cover
        if self._current_file is None or self._total_hunks == 0:
            return
        if self._current_hunk_index < self._total_hunks - 1:
            self._current_hunk_index += 1
            indicator: HunkIndicator = self.query_one("#hunk-indicator", HunkIndicator)
            indicator.set_hunk(self._current_hunk_index + 1, self._total_hunks)
            self._scroll_to_hunk(self._current_hunk_index)

    def action_prev_hunk(self) -> None:  # pragma: no cover
        if self._current_file is None or self._total_hunks == 0:
            return
        if self._current_hunk_index > 0:
            self._current_hunk_index -= 1
            indicator: HunkIndicator = self.query_one("#hunk-indicator", HunkIndicator)
            indicator.set_hunk(self._current_hunk_index + 1, self._total_hunks)
            self._scroll_to_hunk(self._current_hunk_index)

    def _scroll_to_hunk(self, hunk_index: int) -> None:  # pragma: no cover
        if self._current_file is None:
            return
        hunks = self._current_file.get("hunks", [])
        line_offset = 3
        for i in range(hunk_index):
            if i in self._collapsed_hunks:
                line_offset += 3
                continue
            hunk = hunks[i]
            line_offset += 1
            old_code = hunk.get("old_code", "")
            new_code = hunk.get("new_code", "")
            if old_code:
                line_offset += len(old_code.splitlines())
            if new_code:
                line_offset += len(new_code.splitlines())
            if self.show_explanations and hunk.get("explanation", ""):
                line_offset += 3
            else:
                line_offset += 1
        scroll_container = self.query_one("#diff-scroll", ScrollableContainer)
        scroll_container.scroll_to(y=max(0, line_offset - 2), animate=True)

    def action_toggle_explanations(self) -> None:
        if self._current_file is None:
            return
        self.show_explanations = not self.show_explanations
        self._render_diff()
        self.sub_title = f"Explanations: {'ON' if self.show_explanations else 'OFF'}"

    def action_toggle_collapse(self) -> None:
        if self._current_file is None or self._total_hunks == 0:
            return
        idx = self._current_hunk_index
        if idx in self._collapsed_hunks:
            self._collapsed_hunks.discard(idx)
        else:
            self._collapsed_hunks.add(idx)
        self._render_diff()

    @on(Input.Submitted, "#chat-input")
    def on_chat_submit(self, event: Input.Submitted) -> None:  # pragma: no cover
        """Handle chat question submission."""
        question = event.value.strip()
        if not question:
            return

        # Get context from current file and hunk
        context_file = self._current_file["path"] if self._current_file else ""
        context_code = ""
        if self._current_file and self._current_file.get("hunks"):
            idx = min(self._current_hunk_index, len(self._current_file["hunks"]) - 1)
            hunk = self._current_file["hunks"][idx]
            context_code = hunk.get("new_code", "") or hunk.get("old_code", "")

        # Write question to chat file
        write_chat_question(question, context_file, context_code)

        # Show waiting state and start auto-polling for answer
        chat_panel: ChatPanel = self.query_one("#chat-panel", ChatPanel)
        chat_panel.mark_waiting()

        # Clear input
        event.input.value = ""

        # Start polling for answer
        self._poll_chat_answer()

    def _poll_chat_answer(self) -> None:  # pragma: no cover
        """Poll the chat file for Claude's answer."""
        answer = read_chat_answer()
        if answer:
            chat_panel: ChatPanel = self.query_one("#chat-panel", ChatPanel)
            chat_panel.show_response(answer)
        else:
            # Check again in 1 second
            self.set_timer(1.0, self._poll_chat_answer)
