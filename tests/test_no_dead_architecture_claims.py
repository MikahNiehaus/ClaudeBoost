"""Docs must not present the deleted 8612 server, or a nonexistent slash command, as current.

One history marker exempts its whole sentence, table row or code line.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCES = {
    "README.md": lambda: [ROOT / "README.md"],
    "docs": lambda: (ROOT / "docs").glob("*.md"),
    ".claude/commands": lambda: (ROOT / ".claude" / "commands").glob("*.md"),
}

DEAD = re.compile(
    r"\b8612\b"
    r"|(?<![\w/.\]-])/context(?![\w.-])"
    r"|mcp-rag-server"
    r"|\b109 knowledge\b",
    re.IGNORECASE,
)
HISTORY = re.compile(
    r"\b(?:used to|retired|deleted|removed|no longer|does not exist|"
    r"doesn't exist|there is no|returns 404|went with|belonged to|"
    r"described the old|old architecture|legacy|is gone)\b",
    re.IGNORECASE,
)
NEGATED = re.compile(r"\b(?:not|never)\b[\w\s]{0,20}$|n't\s+(?:been\s+|yet\s+)?$", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _is_history(unit: str) -> bool:
    return any(not NEGATED.search(unit[:m.start()]) for m in HISTORY.finditer(unit))


def units(text: str):
    """Yield (line_number, unit). Prose lines are joined, then split into sentences."""
    prose: list[tuple[int, str]] = []
    in_fence = False

    def flush():
        if not prose:
            return
        start = prose[0][0]
        joined = " ".join(line.strip() for _, line in prose)
        prose.clear()
        for sentence in _SENTENCE_END.split(joined):
            yield start, sentence

    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            yield from flush()
            in_fence = not in_fence
            continue
        if in_fence or stripped.startswith("|"):
            yield from flush()
            yield n, stripped
        elif not stripped or stripped.startswith("#"):
            yield from flush()
            if stripped:
                yield n, stripped
        else:
            prose.append((n, line))
    yield from flush()


def dead_claims(text: str) -> list[tuple[int, str]]:
    return [(n, u) for n, u in units(text) if DEAD.search(u) and not _is_history(u)]


# Only backtick quoted mentions are checked; the lookahead skips paths like `/c/Development`.
COMMAND_REF = re.compile(r"`/([a-z][a-z0-9-]*)(?=[\s`\[.,;:!?)])")
# Hand copied from Claude Code 2.1.280, so a built in it later drops still passes.
CLAUDE_CODE_BUILTINS = frozenset({"clear", "code-review", "init", "review", "simplify", "voice"})
# Proposes commands that were never built.
ROADMAPS = {"IMPROVEMENTS.md"}


def known_commands() -> set[str]:
    names = {p.stem for p in (ROOT / ".claude" / "commands").glob("*.md")}
    for skills in (ROOT / ".claude" / "skills", ROOT / "clean-rag" / "portable" / "skills"):
        names |= {p.name for p in skills.iterdir() if (p / "SKILL.md").is_file()}
    app = (ROOT / "clean-rag" / "server" / "app.py").read_text(encoding="utf-8")
    names |= set(re.findall(r'add_(?:get|post|put|delete)\(\s*"/([\w-]+)"', app))
    return names | CLAUDE_CODE_BUILTINS


def unknown_commands(text: str, known: set[str]) -> list[tuple[int, str]]:
    return [(n, m.group(1)) for n, u in units(text) if not _is_history(u)
            for m in COMMAND_REF.finditer(u) if m.group(1) not in known]


def _files():
    for files in SOURCES.values():
        yield from files()


def test_every_source_contributes_files():
    empty = [name for name, files in SOURCES.items()
             if not [p for p in files() if p.is_file()]]
    assert not empty, empty


def test_no_doc_presents_the_deleted_server_as_current():
    hits = []
    for path in _files():
        for n, unit in dead_claims(path.read_text(encoding="utf-8")):
            hits.append(f"{path.relative_to(ROOT)}:{n}: {unit[:160]}")
    assert not hits, "\n".join(hits)


def test_the_guard_bites():
    assert dead_claims("The RAG server exposes an HTTP API at `http://127.0.0.1:8612`:")
    assert dead_claims("| `POST /context` | Load agent identity |")
    assert dead_claims("Agents call `POST /context` as their first action.")
    assert dead_claims("├── mcp-rag-server/      HTTP RAG server")
    assert dead_claims("It loads 109 knowledge files into every\nsession.")
    assert dead_claims("```\nGET http://127.0.0.1:8612/status\n```")


def test_history_framing_passes():
    assert not dead_claims("These figures were measured on the retired 8612 server.")
    assert not dead_claims("This file described the old search server: `mcp-rag-server/` on\n"
                           "port 8612, its `/context` and `/index` routes.")
    assert not dead_claims("There is no /context route; it returns 404.")
    assert not dead_claims("It used to index into the ClaudeBoost RAG server on 8612.")
    assert not dead_claims("Read `$WORKSPACE_ABS/context.md` first.")
    assert not dead_claims("Update `workspace/[task-id]/context.md` after work.")


def test_every_quoted_command_exists():
    known = known_commands()
    hits = [f"{path.relative_to(ROOT)}:{n}: /{name}"
            for path in _files() if path.name not in ROADMAPS
            for n, name in unknown_commands(path.read_text(encoding="utf-8"), known)]
    assert not hits, "\n".join(hits)


def test_known_commands_reads_every_source():
    known = known_commands()
    assert {"boost", "code-quality-metrics", "ps", "search", "reindex-file", "init"} <= known


def test_command_guard_bites():
    known = known_commands()
    assert unknown_commands("`/auto` `/better-permissions` `/edit-state`", known) == [(1, "better-permissions")]
    assert unknown_commands("| `/setup` | Installs everything | `/setup` |", known)
    assert unknown_commands("Run `/definitely-not-real [x]` first.", known)
    assert unknown_commands("Call `/context` for identity.", known)
    for tail in ".,;:!?)":
        assert unknown_commands(f"Run `/totally-fake-cmd{tail}` first.", known), tail


def test_command_guard_passes_real_references():
    known = known_commands()
    assert not unknown_commands("`/boost` `/ps` `/fix-perm` `/init` `/simplify`", known)
    assert not unknown_commands("POST `/search` or `/reindex-file` with `project_path`.", known)
    assert not unknown_commands("Clone into `/c/Development/app` and read and/or skim it.", known)
    assert not unknown_commands("`/end-to-end-test` was listed here and does not exist.", known)


def test_dead_match_ignores_case():
    assert dead_claims("Loads 109 Knowledge files from MCP-RAG-SERVER.")
    assert dead_claims("Call POST /CONTEXT first.")


def test_history_marker_cannot_launder_a_live_claim():
    assert dead_claims("Call POST /context first. The old server was removed.")
    assert dead_claims("Call POST /context first; it has not been removed.")
    assert dead_claims("| `POST /context` | load context | (not deleted) |")
    assert dead_claims("Removed nothing.\n\n```\ncurl 127.0.0.1:8612/status\n```")
