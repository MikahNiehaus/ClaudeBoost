"""
boost-inline.py — Inline terminal display for ClaudeBoost activation.

Prints a clean header or closing banner directly to the current terminal.
Replaces the wt.exe new-tab matrix animation — same terminal, no new tab.

Usage:
  python boost-inline.py          — opening header (run at boost start)
  python boost-inline.py --done   — closing banner (run when all checks pass)
"""
import io
import sys

# Force UTF-8 so box-drawing chars survive Windows cp1252 terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

GREEN  = "\033[32m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

HEADER = (
    f"\n{CYAN}{BOLD}"
    "  +======================================+\n"
    "  |      C L A U D E  B O O S T         |\n"
    "  +======================================+"
    f"{RESET}\n"
)

DONE_BANNER = (
    f"\n{GREEN}{BOLD}"
    "  +======================================+\n"
    "  |   > All systems online               |\n"
    "  +======================================+"
    f"{RESET}\n"
)


def main() -> None:
    if "--done" in sys.argv:
        print(DONE_BANNER)
    else:
        print(HEADER)


if __name__ == "__main__":
    main()
