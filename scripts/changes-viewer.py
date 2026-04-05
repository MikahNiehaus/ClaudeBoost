#!/usr/bin/env python3
"""ClaudeBoost Changes HUD - Sci-fi HUD themed change viewer."""

import sys
import random
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, RichLog, Static, Tree

from changes_core import (
    STATUS_ICONS,
    STATUS_COLORS,
    BaseChangesViewer,
    Breadcrumb,
    ChatPanel,
    HunkIndicator,
    build_summary_markup,
    count_file_changes,
    load_changes,
)


# HUD-themed status icons
HUD_STATUS_ICONS = {
    "modified": "◈MOD",
    "added": "◈NEW",
    "deleted": "◈DEL",
}


class HudBreadcrumb(Breadcrumb):
    """Sci-fi HUD breadcrumb."""

    DEFAULT_CSS = """
    HudBreadcrumb {
        height: 1;
        padding: 0 1;
        background: #0a0a0a;
        color: #005500;
    }
    HudBreadcrumb:hover {
        background: #0d1a0d;
    }
    """
    back_indicator = "◁"
    accent_color = "#00ff41"
    dim_color = "#005500"


class HudHunkIndicator(HunkIndicator):
    """Sci-fi HUD hunk indicator."""

    DEFAULT_CSS = """
    HudHunkIndicator {
        height: 1;
        padding: 0 1;
        background: #0a0a0a;
        color: #00ff41;
        text-align: right;
    }
    """
    hunk_label = "▸ SECTOR"


def build_hud_summary(data: dict[str, Any]) -> str:
    """Build HUD-style data readout summary."""
    s = data["summary"]
    project = data.get("project", "Unknown")
    agents = ", ".join(s["agents"]) or "none"
    goal = data.get("goal", "")
    ts = data.get("generated_at", "")

    lines = [
        f"[bold #00ff41]◉ TARGET:[/bold #00ff41]  [#00ff41]{project}[/#00ff41]   "
        f"[bold #00ff41]STATUS:[/bold #00ff41] [#00ff41]{s['files_changed']} FILES DETECTED[/#00ff41]   "
        f"[#00cc33]+{s['lines_added']}[/#00cc33] [#006600]/ [/#006600][#00cc33]-{s['lines_removed']}[/#00cc33]",
        f"[bold #00ff41]◉ AGENTS:[/bold #00ff41] [#00cc33]{agents}[/#00cc33]"
        + (f"   [#004400]{ts}[/#004400]" if ts else ""),
    ]
    if goal:
        lines.append(f"[bold #00ff41]◉ MISSION:[/bold #00ff41] [#00cc33]{goal}[/#00cc33]")
    return "\n".join(lines)


class HudScanScreen(Static):
    """Full-screen scanning animation for HUD startup."""

    DEFAULT_CSS = """
    HudScanScreen {
        width: 100%;
        height: 100%;
        background: #0a0a0a;
        color: #00ff41;
        padding: 2 4;
    }
    """

    def __init__(self, data: dict[str, Any], **kwargs) -> None:
        super().__init__("", **kwargs)
        self._data = data
        self._frame = 0
        self._lines: list[str] = []
        self._file_paths = [f["path"] for f in data.get("files", [])]
        self._total_files = len(self._file_paths)
        self._scan_index = 0
        # Total frames: border(1) + title(1) + init(1) + files(N) + decode(1) + complete(1) + pause(3)
        self._total_frames = 4 + self._total_files + 3

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.3, self._tick)

    def _tick(self) -> None:
        try:
            self._frame += 1
            frame = self._frame

            if frame == 1:
                # Green border draws
                self._lines = [
                    "[#00ff41]╔══════════════════════════════════════════════════╗[/#00ff41]",
                    "[#00ff41]║[/#00ff41]                                                  [#00ff41]║[/#00ff41]",
                    "[#00ff41]╚══════════════════════════════════════════════════╝[/#00ff41]",
                ]
            elif frame == 2:
                # Title types across
                self._lines = [
                    "[#00ff41]╔══════════════════════════════════════════════════╗[/#00ff41]",
                    "[#00ff41]║[/#00ff41]  [bold #00ff41]◉ CLAUDEBOOST CHANGE ANALYZER[/bold #00ff41]                 [#00ff41]║[/#00ff41]",
                    "[#00ff41]╚══════════════════════════════════════════════════╝[/#00ff41]",
                    "",
                ]
            elif frame == 3:
                self._lines.append("[#00cc33]  ▸ INITIALIZING SCAN PROTOCOL...[/#00cc33]")
            elif frame >= 4 and self._scan_index < self._total_files:
                # Scan each file
                path = self._file_paths[self._scan_index]
                fname = path.rsplit("/", 1)[-1]
                self._lines.append(f"[#008800]  ▸ SCANNING [bold #00ff41]{fname}[/bold #00ff41][/#008800]")
                self._scan_index += 1
            elif self._scan_index >= self._total_files and frame == 4 + self._total_files:
                total_changes = self._data["summary"].get("lines_added", 0) + self._data["summary"].get("lines_removed", 0)
                self._lines.append(f"[#00cc33]  ▸ DECODING [bold #00ff41]{total_changes}[/bold #00ff41] CHANGE VECTORS...[/#00cc33]")
            elif frame == 5 + self._total_files:
                self._lines.append("")
                self._lines.append("[bold #00ff41]  ◉ ANALYSIS COMPLETE[/bold #00ff41]")
            elif frame >= self._total_frames:
                self._timer.stop()
                self.app._transition_to_main()
                return

            self.update("\n".join(self._lines))
        except Exception:
            self._timer.stop()
            self.app._transition_to_main()


class HudChangesViewer(BaseChangesViewer):
    """Sci-fi HUD themed changes viewer."""

    TITLE = "CLAUDEBOOST // CHANGE ANALYZER"
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
        super().__init__(data)
        self._animation_done = False

    def _get_diff_theme(self) -> dict[str, str]:
        return {
            "status_icon_style": "bold #00ff41",
            "path_style": "bold #00ff41",
            "agent_style": "#00cc33",
            "summary_style": "#008800",
            "hunk_marker_style": "bold #00ff41",
            "hunk_label_style": "bold #00ff41",
            "hunk_header_style": "#00cc33",
            "line_num_style": "#005500",
            "removed_prefix_style": "#ff4444 on #1a0000",
            "removed_bg": "#1a0000",
            "added_prefix_style": "#00ff41 on #001a00",
            "added_bg": "#001a00",
            "explanation_style": "#00aa33",
            "collapsed_style": "#005500",
            "hunk_label_prefix": "▸ SECTOR",
            "explanation_prefix": "   ▪ ",
        }

    def _get_tree_label(self) -> str:
        return "◉ DETECTED FILES"

    def _format_file_label(self, file_data: dict[str, Any], filename: str) -> str:
        status = file_data["status"]
        icon = HUD_STATUS_ICONS.get(status, "◈???")
        agent = file_data.get("agent", "")
        agent_str = f"  [#00cc33]({agent})[/#00cc33]" if agent else ""
        added, removed = count_file_changes(file_data)
        counts = ""
        if added > 0:
            counts += f"  [#00ff41]+{added}[/#00ff41]"
        if removed > 0:
            counts += f"  [#cc4444]-{removed}[/#cc4444]"
        return f"[#00ff41]{icon}[/#00ff41] {filename}{counts}{agent_str}"

    def _make_breadcrumb(self) -> Breadcrumb:
        return HudBreadcrumb(id="breadcrumb")

    def _make_hunk_indicator(self) -> HunkIndicator:
        return HudHunkIndicator(id="hunk-indicator")

    def compose(self) -> ComposeResult:
        yield Header()
        yield HudScanScreen(self.data, id="scan-screen")
        yield Static(build_hud_summary(self.data), id="summary")
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

    def on_mount(self) -> None:
        # Hide main UI during animation
        self.query_one("#summary").display = False
        self.query_one("#file-tree").display = False
        self.query_one("#diff-view").display = False

    def _transition_to_main(self) -> None:
        """Called when animation completes to show the real UI."""
        try:
            self._animation_done = True
            self.query_one("#scan-screen").display = False
            self.query_one("#summary").display = True
            self.query_one("#file-tree").display = True
            # Build tree
            super().on_mount()
        except Exception:
            pass


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/changes-viewer.py <path-to-changes.json>", file=sys.stderr)
        sys.exit(1)
    data = load_changes(sys.argv[1])
    app = HudChangesViewer(data)
    app.run()


if __name__ == "__main__":
    main()
