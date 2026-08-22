"""
No slash command or portable skill may name a script or directory that is gone.

754a2d4 deleted mcp-rag-server/, agents/, knowledge/ and a number of scripts.
Command files kept naming them, and a command file is not documentation: the
model executes its steps. /visualize ran `ls agents/ knowledge/` to pick a mode
and then shelled scripts/visualize-extract.py, all three deleted, so self-map
mode was dead twice over and nothing said so. /ticket-handoff read a deleted
knowledge file. /workspace listed 27 of them in a table.

None of that shows up in a normal test run, because these are prose files that
nothing imports.

Two things this must NOT flag, both of which a first cut got wrong:

  install paths   `~/.claude/skills/powerpoint/scripts/pptx_env.py` is where a
                  portable skill lands after install. It is not a repo path,
                  and neither is a reference to another project's file such as
                  Anthropic's document-skills plugin.

  the explanation Saying "scripts/rag-supervisor.py was deleted with the 8612
                  server" is the point, not a regression. Prose wraps, so the
                  words that mark it historical are often on a neighbouring
                  line, which is why this looks at a window rather than one
                  line.

Run: python -m pytest tests/test_no_dead_command_refs.py -v
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMANDS = sorted((REPO / ".claude" / "commands").glob("*.md"))
SKILLS = sorted((REPO / "clean-rag" / "portable" / "skills").rglob("SKILL.md"))

SCRIPT_RE = re.compile(
    r"(?:\$\{?CLAUDEBOOST_HOME\}?/)?((?:scripts|clean-rag)/[\w./-]+\.py)"
)

DELETED_DIRS = ("agents/", "knowledge/", "mcp-rag-server/")

#: Anchors meaning "not a path in this repo".
FOREIGN = ("~/.claude", "$HOME", "${HOME}", "plugins/marketplaces",
           ".claudeboost/knowledge", "%USERPROFILE%")

#: Words that mark a mention as an explanation of the retirement.
HISTORICAL = (
    "used to", "was deleted", "were deleted", "deleted in", "no longer",
    "retired", "went with it", "there used to be", "replaces the old",
    "not there", "deprecated", "deleted with", "both were deleted",
    "all three were deleted", "which read the", "licence", "anthropic's own",
)

#: How many lines either side count as the same passage.
WINDOW = 3


def _historical_window(lines, idx) -> bool:
    lo = max(0, idx - WINDOW)
    hi = min(len(lines), idx + WINDOW + 1)
    blob = " ".join(lines[lo:hi]).lower()
    return any(marker in blob for marker in HISTORICAL)


def _findings(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if any(f in line for f in FOREIGN):
            continue
        if _historical_window(lines, i):
            continue

        for rel in SCRIPT_RE.findall(line):
            rel = rel.lstrip("/")
            if (REPO / rel).exists():
                continue
            # A skill may ship its own scripts/ folder.
            if (path.parent / rel).exists():
                continue
            out.append((i + 1, rel, line.strip()[:90]))

        for d in DELETED_DIRS:
            if re.search(rf"(?<![\w./-]){re.escape(d)}", line) and not (REPO / d).exists():
                out.append((i + 1, d, line.strip()[:90]))
    return out


@pytest.mark.parametrize("md", COMMANDS, ids=lambda p: p.name)
def test_command_has_no_dead_reference(md):
    dead = _findings(md)
    assert not dead, (
        f"{md.name} names {len(dead)} thing(s) that do not exist. A command "
        "step naming a missing file fails silently, because the model executes "
        "these steps:\n"
        + "\n".join(f"  line {n}: {ref}\n    {ctx}" for n, ref, ctx in dead)
    )


@pytest.mark.parametrize("sk", SKILLS, ids=lambda p: p.parent.name)
def test_skill_has_no_dead_reference(sk):
    """Portable skills are copied into ~/.claude and travel to other machines."""
    dead = _findings(sk)
    assert not dead, (
        f"skill {sk.parent.name} names {len(dead)} thing(s) that do not exist:\n"
        + "\n".join(f"  line {n}: {ref}\n    {ctx}" for n, ref, ctx in dead)
    )


def test_the_check_would_actually_catch_something():
    """
    Guard against the guard passing because its patterns match nothing.

    A regex that finds no candidates reports every file clean, which is
    indistinguishable from every file being clean.
    """
    seen = sum(
        len(SCRIPT_RE.findall(md.read_text(encoding="utf-8", errors="replace")))
        for md in COMMANDS
    )
    assert seen > 10, (
        f"only {seen} script references found across {len(COMMANDS)} commands; "
        "the pattern has probably stopped matching"
    )


def test_a_planted_dead_reference_is_caught(tmp_path):
    """
    Prove the detector bites, using the exact shape that got through before:
    an executable step naming a script deleted in 754a2d4.
    """
    planted = tmp_path / "planted.md"
    planted.write_text(
        "## Step 1\n\n"
        "```bash\n"
        '"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/visualize-extract.py" out.json\n'
        "```\n",
        encoding="utf-8",
    )
    dead = _findings(planted)
    assert dead, "the detector missed a planted dead script reference"
    assert any("visualize-extract.py" in ref for _, ref, _ in dead)


def test_an_explained_deletion_is_not_flagged(tmp_path):
    """The counterpart: explaining a retirement must stay allowed."""
    explained = tmp_path / "explained.md"
    explained.write_text(
        "This step used to run `scripts/visualize-extract.py`, which read the\n"
        "`agents/` and `knowledge/` trees. All three were deleted in 754a2d4.\n",
        encoding="utf-8",
    )
    assert not _findings(explained), (
        "an explanation of the retirement was flagged as a regression"
    )
