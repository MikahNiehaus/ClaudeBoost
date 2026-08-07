"""Every RAG URL in a command file must resolve against the real router.

16 of 36 files in `.claude/commands/` spent months telling Claude to POST to
port 8612, a server that was retired on purpose (clean-rag/CLAUDE.md, "Why the
KB is gone"), at routes like `/context` and `/index` that no longer exist
anywhere. Nothing failed loudly. The calls just returned connection refused and
the skills carried on with no local context.

Docs drift because nothing checks them. So check them.

Five classes of stale reference are caught, each one found live in these files:

* a retired port (`:8612`)
* a route the router does not serve (`/context`)
* a fabricated path nested under a real route (`/search/nonexistent`)
* a URL a formatter wrapped across two lines, or written `HTTP://`
* a `scope=` parameter, which no clean-rag route has ever taken — these name no
  host at all (`POST /search scope=codebase ...`), which is exactly why the
  port migration walked straight past them

The route set comes from `create_app().router`, the same aiohttp dispatcher the
running server uses, not from a list copied into this file. A mirrored list
would rot exactly the way the command files did. `create_app()` is cheap: it
builds a lazily loading ModelCache and mkdirs the state dir, and the model
warmup lives in an `on_startup` handler that never fires here.

Pattern cloned from tests/test_qa_md_cross_references.py, which already does
this shape for qa.md's step numbers: regex the references out, diff against
what really exists, assert the stale list is empty, and print the offenders
with line numbers so the failure is a worklist rather than a puzzle.

Scope: markdown under `.claude/commands/` only. Those files are instructions a
model follows literally, so a wrong URL there becomes a wrong action. A stale
port in a Python comment is untidy but inert, and `~/.claude/skills/` lives
outside the repo where a test cannot reach it.
"""

import bisect
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CLEAN_RAG = REPO / "clean-rag"
COMMANDS = REPO / ".claude" / "commands"

if str(CLEAN_RAG) not in sys.path:
    sys.path.insert(0, str(CLEAN_RAG))

#: A hand edit or a markdown formatter can wrap a long URL, leaving the rest of
#: it on the next line. Permitting one optional newline plus indentation at each
#: join is what makes such a reference visible at all: scanning line by line
#: meant `http://127.0.0.1` + newline + `:8612/context` appeared whole on
#: neither line and a retired-port URL hid there indefinitely.
_WRAP = r"[ \t]*\n?[ \t]*"

#: Any localhost URL, with its full path. Written against the whole file, not a
#: single line, so `_WRAP` can do its job.
#:
#: The scheme is matched case-insensitively (`re.IGNORECASE`): `HTTP://` is what
#: an autocapitalising editor produces and it names exactly the same server.
#:
#: The path repeats its segment group, so `/search/nonexistent` is captured
#: whole. Capturing only the first segment made every fabricated nested route
#: look like its real parent. Trailing punctuation stays out of the segment
#: class on purpose: these appear inside prose and code fences, so a URL is
#: routinely followed by a backtick, comma or full stop that is not part of it.
LOCALHOST_URL = re.compile(
    rf"""
    https? : {_WRAP} // {_WRAP}
    (?: 127\.0\.0\.1 | localhost )
    {_WRAP} : {_WRAP} (\d+)
    ( (?: {_WRAP} / [A-Za-z0-9_\-]+ )* )
    """,
    re.VERBOSE | re.IGNORECASE,
)

#: A route named with no host at all — `POST /search ...`. Plain shorthand for a
#: real endpoint is fine and common in this prose, so this is only ever paired
#: with SCOPE_PARAM below rather than reported on its own.
ROUTE_MENTION = re.compile(
    r"\b(?:POST|GET)\s+(?:https?://(?:127\.0\.0\.1|localhost):\d+)?(/[A-Za-z0-9_\-]+)",
    re.IGNORECASE,
)

#: `scope=` was a parameter of the retired bundled server's `/context` and
#: `/index`. No clean-rag route has ever accepted it — `/search` takes `sources`
#: (`clean-rag/server/search.py:362-373`) — so a line still passing it is a
#: stale reference even when the route name beside it happens to be real. These
#: survived the port migration precisely because they name no host, which put
#: them out of LOCALHOST_URL's reach.
SCOPE_PARAM = re.compile(r"\bscope\s*=")

#: A `{...}` literal on the line is the request body, so text inside it is data.
#: `{"query": "QA session ... scope=$SCOPE ..."}` is a search string that happens
#: to contain the word and must not be flagged. Quoting alone is not the test:
#: `"Run POST /index scope=all to regenerate"` is quoted prose passing a real
#: dead parameter, and exempting every quoted span would hide it.
JSON_BODY = re.compile(r"\{[^{}]*\}")

#: Ports clean-rag has ever answered on. 8612 is the retired bundled server and
#: is the whole reason this test exists; it must never appear again. The live
#: port is added at run time from config.
#:
#: Scoped deliberately. Command files also name localhost:3000 (a project's dev
#: server) and localhost:11434 (Ollama), which are real services this test has
#: no business judging. Matching every localhost URL flagged those as failures.
RETIRED_RAG_PORTS = frozenset({8612})


def real_routes() -> set:
    """Every path the live app serves, read off its own aiohttp dispatcher."""
    from server.app import create_app

    app = create_app()
    paths = set()
    for route in app.router.routes():
        canonical = getattr(route.resource, "canonical", None)
        if canonical:
            paths.add(canonical)
    return paths


def real_port() -> int:
    from server.config import STANDALONE_PORT

    return int(STANDALONE_PORT)


def command_files() -> list:
    return sorted(COMMANDS.glob("*.md"))


def _line_starts(text: str) -> list:
    """Offset of the first character of every line, for offset -> line_no."""
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def references() -> list:
    """(file, line_no, port, path, line_text) for every clean-rag URL found.

    Scans each file whole rather than line by line, so a URL a formatter
    wrapped is still one match. The line number reported is the line the URL
    *starts* on, found by bisecting the line-start offsets.
    """
    rag_ports = RETIRED_RAG_PORTS | {real_port()}
    found = []
    for path in command_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        starts = _line_starts(text)
        lines = text.splitlines()
        for m in LOCALHOST_URL.finditer(text):
            port = int(m.group(1))
            if port not in rag_ports:
                continue
            # Whitespace inside the capture is the wrap itself; the route the
            # reference names is the path with that wrap taken back out.
            route = re.sub(r"\s+", "", m.group(2)) or "/"
            lineno = bisect.bisect_right(starts, m.start())
            found.append((path.name, lineno, port, route, lines[lineno - 1].strip()))
    return found


def _without_json_bodies(line: str) -> str:
    """The line with every `{...}` literal removed, innermost first."""
    previous = None
    while previous != line:
        previous, line = line, JSON_BODY.sub("", line)
    return line


def scope_parameter_references() -> list:
    """(file, line_no, route, line_text) for every route line still passing `scope=`."""
    found = []
    for path in command_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if not SCOPE_PARAM.search(_without_json_bodies(line)):
                continue
            m = ROUTE_MENTION.search(line)
            if m:
                found.append((path.name, lineno, m.group(1), line.strip()))
    return found


# --- guards, so a broken regex or import cannot make this pass vacuously ----

def test_command_files_are_present():
    files = command_files()
    assert len(files) > 20, f"only found {len(files)} command files under {COMMANDS}"


def test_router_introspection_returns_a_real_route_set():
    routes = real_routes()
    assert len(routes) > 15, f"router gave only {len(routes)} routes, introspection broke"
    assert "/search" in routes and "/status" in routes


def test_the_regex_actually_matches_something():
    """If this goes to zero the other two tests below become meaningless."""
    assert references(), "no RAG URLs matched at all; the regex or the paths moved"


# --- the actual contract ----------------------------------------------------

def test_every_rag_url_uses_the_live_port():
    port = real_port()
    stale = [r for r in references() if r[2] != port]
    assert stale == [], (
        f"These point at a port clean-rag does not serve (live port is {port}):\n"
        + "\n".join(
            f"  {name}:{lineno}  port {found}  {line[:100]}"
            for name, lineno, found, _path, line in stale
        )
    )


def test_every_rag_url_hits_a_route_that_exists():
    routes = real_routes()
    port = real_port()
    # Only judge paths on the live port. A wrong port is already reported by the
    # test above, and its paths belong to a different server's route table.
    stale = [
        r for r in references()
        if r[2] == port and r[3] != "/" and r[3] not in routes
    ]
    assert stale == [], (
        "These name a route the server does not serve:\n"
        + "\n".join(
            f"  {name}:{lineno}  {path}  {line[:100]}"
            for name, lineno, _port, path, line in stale
        )
        + "\n\nRoutes that do exist:\n  "
        + "\n  ".join(sorted(routes))
    )


def test_no_route_line_still_passes_a_scope_parameter():
    stale = scope_parameter_references()
    assert stale == [], (
        "`scope=` is not a parameter of any clean-rag route; /search takes "
        "`sources: [\"project:<abs path>\"]`. These lines still send it:\n"
        + "\n".join(
            f"  {name}:{lineno}  {route}  {line[:100]}"
            for name, lineno, route, line in stale
        )
    )


# --- the forms that used to slip past -------------------------------------
#
# The three guard tests above prove the happy path isn't vacuous. These four
# pin the forms that were provably invisible before: a wrapped URL, an
# uppercase scheme, a fabricated nested path, and a hostless `scope=` line.
# Each writes to a scratch file under a stand-in COMMANDS dir, so the real
# command files are never touched.

@pytest.fixture
def scratch_command_file(monkeypatch, tmp_path):
    """A throwaway .md file inside a COMMANDS-like dir, swapped in for the run.

    Points the module's own COMMANDS constant at *tmp_path* so
    ``command_files()``/``references()`` see only the one file this test
    writes, and never touch the real .claude/commands tree.
    """
    mod = sys.modules[__name__]

    monkeypatch.setattr(mod, "COMMANDS", tmp_path)

    def _write(text: str) -> Path:
        f = tmp_path / "scratch.md"
        f.write_text(text, encoding="utf-8")
        return f

    return _write


def test_a_url_wrapped_across_two_lines_is_caught(scratch_command_file):
    """A stale reference split by a line wrap is still one reference.

    An editor or a markdown formatter can leave `http://127.0.0.1` on one line
    and `:8612/context` on the next. Read as prose it still names the retired
    port and the retired route, so it has to be reported as one, on the line
    it starts on.
    """
    mod = sys.modules[__name__]

    scratch_command_file(
        "Call `POST http://127.0.0.1\n:8612/context` as your FIRST action.\n"
    )
    found = mod.references()
    assert len(found) == 1, f"expected one wrapped reference, got {found}"
    _, lineno, port, path, _ = found[0]
    assert (lineno, port, path) == (1, 8612, "/context")


def test_a_multi_segment_path_is_captured_whole(scratch_command_file):
    """A fabricated nested route is judged on its full path, not its parent.

    `/search/nonexistent` used to be captured as just `/search`, and `/search`
    really is a route, so the route contract could not tell a real endpoint
    from an invented path under it.
    """
    mod = sys.modules[__name__]

    scratch_command_file(
        "Call `POST http://127.0.0.1:8613/search/nonexistent` for details.\n"
    )
    found = mod.references()
    assert found, "the reference itself should still be picked up"
    _, _, _, path, _ = found[0]
    assert path == "/search/nonexistent", f"path was truncated to {path!r}"
    assert path not in mod.real_routes(), (
        "the whole point: the full path is not a route, so the route contract "
        "must be able to fail on it"
    )


def test_an_uppercase_scheme_is_caught(scratch_command_file):
    """`HTTP://` names the same server as `http://` and is judged the same.

    An autocapitalising editor produces it routinely, and a lowercase-only
    `https?://` let the whole match fail silently.
    """
    mod = sys.modules[__name__]

    scratch_command_file("Call `HTTP://127.0.0.1:8612/context` first.\n")
    found = mod.references()
    assert len(found) == 1, f"expected the uppercase-scheme reference, got {found}"
    _, _, port, path, _ = found[0]
    assert (port, path) == (8612, "/context")


def test_a_hostless_scope_parameter_line_is_caught(scratch_command_file):
    """`POST /search scope=...` has no host, so only the scope check sees it.

    Line 2 is quoted prose that still passes the dead parameter, and must be
    flagged: quoting is not what makes `scope=` data. Lines 3 and 4 must NOT
    be flagged — bare `POST /search` is fine shorthand for a real endpoint,
    and a `scope=` inside the request body is search text.
    """
    mod = sys.modules[__name__]

    scratch_command_file(
        '- `POST /search scope=codebase query="routes" mode=graph limit=6`\n'
        '- FAIL if any missing -> "Run POST /index scope=all to regenerate"\n'
        "- `POST /search` on its own is fine shorthand and must not be flagged\n"
        '- `POST /search {"query":"audit scope=$SCOPE","sources":["project:X"]}`\n'
    )
    found = mod.scope_parameter_references()
    assert [(lineno, route) for _, lineno, route, _ in found] == [
        (1, "/search"),
        (2, "/index"),
    ], f"expected only the two scope= lines, got {found}"
    assert mod.references() == [], "no host is named, so no URL should be reported"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
