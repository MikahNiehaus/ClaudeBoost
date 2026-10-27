"""Example deck: two slides built from real files, to copy the shapes from.

Render: python scripts/narrate.py example_deck.py
"""
from pathlib import Path

from narrate import mark, page, terminal

BRAND = "presentation"
NAME = "example"
SKILL = Path(__file__).resolve().parent


def slides():
    rules = page(SKILL / "SKILL.md", "### What makes an explainer good", "### Making one")
    rules = mark(rules, "Show proof, not pictures of ideas.", 1)
    rules = mark(rules, "Highlights land on the spoken word.", 2)

    files = sorted(p.name for p in (SKILL / "scripts").iterdir() if p.suffix in (".py", ".css"))
    listing = terminal(["$ ls scripts"] + [(f, 2 if f == "narrate.py" else 0) for f in files])

    return [
        dict(title="Every slide shows something real", body=f'<div class="sheet small">{rules}</div>',
             labels={1: "Proof", 2: "Timed highlights"},
             say=["Every slide in an explainer shows something real: a page, a screenshot, or a command's output.",
                  "And each highlight shows up the moment the voice names it."]),
        dict(title="One script renders and narrates", body=listing,
             labels={2: "The engine"},
             say=["The skill's scripts folder holds the whole pipeline.",
                  "narrate dot py renders one still per beat, voices each beat, and cross fades them into an mp4."]),
    ]
