"""The global instructions ship in three places and must agree with the code.

`CLAUDE.md` exists three times: the repo copy, the canonical `clean-rag/portable/`
copy that `clean-rag/install.py` deploys, and the installed `~/.claude/CLAUDE.md`
that Claude Code actually loads. Nothing keeps them in step, and an edit applied
to one of them is invisible in the other two.

Two failures are checked, both of which shipped:

* **Drift.** A section hand-edited into one copy and not the others means the
  behaviour described to a session depends on which file it read. The fan-out
  section is checked because it is the newest and had no coverage at all.
* **A claim the code contradicts.** The fan-out section asserted that nothing
  reads `state/audit-in-progress.json` and told future sessions not to add
  another flag. `scripts/skill-verify-gate.py` reads it as a registered
  PreToolUse hook and exits 2 without it; `scripts/action-gate.py`,
  `scripts/verify-gate-cmd.py`, `scripts/context-nudge.py` and
  `scripts/rules-compliance-check.py` read it too. Acting on the shipped text
  would have removed a live bypass.

The second check compares two sets of file names and never reads the English.
An earlier version matched a regex against the prose to decide whether a
sentence denied that the flag was read. That was abandoned because it was wrong
in both directions: it missed "has no readers left in the codebase" and "is not
consulted by anything anymore", and it failed the accurate sentence
"`scripts/action-gate.py` reads the flag; nothing else reads it". Detecting
negation and its scope in English is its own research problem with its own
decades-old literature (NegEx and its successors), and a five-branch regex
written for one document is not going to land on the right side of it. A test
that fails on accurate prose is worse than no test, because it teaches people to
phrase around it.

So the property is a fact, not a phrasing: the documents must name every script
that really reads the flag, and must not name one that does not. Both halves are
derived from the filesystem at run time. A denial cannot satisfy the first half
without listing the readers it is denying, which is the shipped defect. It is
worth being explicit about the limit: a retraction that enumerates all five
current readers and then says they are gone would pass. That is the price of a
check that never fires on true prose, and it is the right side to err on.

**Where the names have to appear is part of the property.** "The document names
it" was once read as "the string occurs somewhere in the file", and that is a
hole rather than a check: a denial naming no reader at all passes as long as
those five filenames survive verbatim anywhere else in the document, in an
installer table or a changelog, attached to no claim about what they read. So
every mention of the flag is attributed to the innermost section enclosing it,
and the reader list has to be in that same section. This is the attribution rule
LangChain's `MarkdownHeaderTextSplitter` uses to decide which header a line
belongs under, where a new header pops every open header of equal or greater
depth (`libs/text-splitters/langchain_text_splitters/markdown.py`, the
`while header_stack and header_stack[-1]["level"] >= current_header_level` loop).
Subsections stay inside, so a reader list one heading below the denial still
counts as part of it.

Both directions resolve that scope through one helper. They did not before, and
they drifted exactly the way the documents did: the reverse direction looked up
one heading by name and the forward direction read the whole file.

The innermost section is not the only scope that would pass today, and an
earlier version of this docstring claimed it was. Measured on all three copies:
the only mention of the flag in each sits in `### Fan-out mode` (repo 490-561,
installed 410-481, portable 432-503), whose enclosing `## Agent Spawning`
section (459-561, 379-481, 401-503) names no script the fan-out section does
not name itself. Widening the scope one level up leaves both directions green
on every copy. The repo and installed copies do name `scripts/bash-guard.py`
and `scripts/chat-watcher.py`, but under `### Never start an app without naming
the environment` and `### Recorded decision: no blocking external model
reviewer on Stop`, neither of which is inside `## Agent Spawning` at all. The
portable copy does not contain either name anywhere.

So the choice is settled by direction rather than by what these files happen to
say, which is a property of set inclusion and holds whatever the documents
become. A wider scope is a superset of the text: it can only shrink the set of
unnamed readers the forward check reports, and can only grow the set of script
names the reverse check has to justify. Widening therefore loses bite exactly
where the shipped defect was, and takes on false failure risk where the prose
is accurate. Narrowing to one known heading is worse than either: a denial
written under any other heading escapes the check entirely. Both halves of that
are tested rather than argued here.

**Heading detection is a block level scan, not a per line one**, because both
things that defeat a per line test are ordinary Markdown. A `#` comment inside
a fenced code block read as a heading and cut the scope off mid section, which
failed prose that named every reader directly above the denial. A setext
heading (text underlined with `---` or `===`) read as no heading at all, which
collapsed a whole document into one scope and reopened the file-wide hole. So
`heading_depths` tracks fences the way LangChain's splitter does, remembering
the opening run and closing only on the same character (`markdown.py`,
`in_code_block` and `opening_fence`), and applies the CommonMark rule that a
`-` or `=` run underlines the line above it only when that line is a paragraph.

What is deliberately left out, each of the four checked line by line against
markdown-it-py rather than assumed: an info string is only tested for the
backtick it may not contain, not parsed; one underline under a multi line
paragraph heads the section at the last of those lines rather than the first;
an ATX run CommonMark rejects, with no space after it (`#Foo`) or more than
six hashes, still counts as a heading here, which errs toward the narrower
scope; and a fence opened inside a list item is closed here by a run at column
0, where CommonMark's container rules keep it open, so markdown-it-py finds no
heading below that run and this finds one. Indented code blocks need no
handling at all, because four spaces of indentation already fails both the ATX
and the setext patterns. On the three real copies the two agree on every line,
and no copy indents a fence at all, so none of that is load bearing today.

Same shape as test_skill_rag_routes.py: derive the truth from the real files,
diff the documentation against it, and report the offenders as a worklist. A
list mirrored into this file would rot the way the documents did.

The installed copy under `~/.claude/` is checked when it exists and skipped when
it does not, so a fresh clone or a CI container still runs the repo half.
"""

import re
from collections.abc import Sequence
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INSTALLED_CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"

#: The two copies that live in the repo. Both must always exist.
REPO_COPIES = (REPO / "CLAUDE.md", REPO / "clean-rag" / "portable" / "CLAUDE.md")

#: The state flag `/audit` sets at Phase 0 and clears at Phase 5.
AUDIT_FLAG = "audit-in-progress.json"

#: Where a reader of that flag could plausibly live. Hooks and scripts are the
#: only things Claude Code executes from this repo.
READER_DIRS = (REPO / "scripts", REPO / "clean-rag" / "hooks")

SECTION_HEADING = "### Fan-out mode"

#: How the documents write a script path. The reverse check reads names back out
#: of a claim with it.
NAMED_SCRIPT = re.compile(r"`scripts/([a-z0-9_-]+\.py)`")


def claude_md_copies() -> list[Path]:
    """Every CLAUDE.md a session could load, installed copy included when present."""
    copies = list(REPO_COPIES)
    if INSTALLED_CLAUDE_MD.is_file():
        copies.append(INSTALLED_CLAUDE_MD)
    return copies


#: A code fence: a run of at least three backticks or tildes, indented no more
#: than three spaces, with an info string or nothing after it.
CODE_FENCE = re.compile(r"^ {0,3}(?P<run>`{3,}|~{3,})(?P<rest>.*)$")

#: A setext underline. `=` heads a depth 1 section, `-` a depth 2 one.
SETEXT_UNDERLINE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")

#: Line starts a setext underline cannot turn into a heading, because they open
#: a list item or a block quote rather than a paragraph.
NOT_A_PARAGRAPH = re.compile(r"^ {0,3}(?:>|[-*+][ \t]|\d{1,9}[.)][ \t])")

#: Four spaces or a tab of indentation is an indented code block, not prose.
CODE_INDENT = re.compile(r"^(?: {4,}|\t)")


def opening_fence(line: str) -> str | None:
    """The fence run this line opens a code block with, or None.

    A backtick run followed by another backtick is an inline code span, so a
    line like ```` ```json``` ```` opens nothing. That is CommonMark's rule
    about info strings and it is why a fence scan cannot just match the run.
    """
    match = CODE_FENCE.match(line)
    if match is None:
        return None
    run, rest = match.group("run"), match.group("rest")
    return None if run[0] == "`" and "`" in rest else run


def closes_fence(line: str, fence: str) -> bool:
    """Whether this line closes a block opened by `fence`.

    The same character, at least as long, and nothing but whitespace after it.
    A shorter run, the other character, or a trailing info string is content,
    which is what lets a document quote a fenced block inside a fenced block.
    """
    match = CODE_FENCE.match(line)
    if match is None:
        return False
    run = match.group("run")
    return (run[0] == fence[0] and len(run) >= len(fence)
            and not match.group("rest").strip())


def heads_a_setext_section(line: str, depth: int) -> bool:
    """Whether an underline below `line` makes it a heading.

    Only a paragraph can be underlined. A blank line, an existing heading, a
    fence, another underline, a list item, a block quote and an indented code
    line are all something else, and a run of dashes below any of them is a
    thematic break.
    """
    return (
        depth == 0
        and line.strip() != ""
        and CODE_FENCE.match(line) is None
        and SETEXT_UNDERLINE.match(line) is None
        and NOT_A_PARAGRAPH.match(line) is None
        and CODE_INDENT.match(line) is None
    )


def heading_depths(lines: Sequence[str]) -> list[int]:
    """Every line's heading depth, 0 where the line heads no section.

    The one place that decides what a heading is. ATX (`## Name`) and setext
    (a name underlined with `===` or `---`) both count, and a `#` inside a
    fenced code block does not. A setext heading's depth lands on the text
    line rather than on the underline, so a section starts where its name is.
    """
    depths = [0] * len(lines)
    fence: str | None = None
    for index, line in enumerate(lines):
        if fence is not None:
            if closes_fence(line, fence):
                fence = None
            continue
        opener = opening_fence(line)
        if opener is not None:
            fence = opener
            continue
        if line.startswith("#"):
            depths[index] = len(line) - len(line.lstrip("#"))
            continue
        underline = SETEXT_UNDERLINE.match(line)
        if (underline and index
                and heads_a_setext_section(lines[index - 1], depths[index - 1])):
            depths[index - 1] = 1 if underline.group(1)[0] == "=" else 2
    return depths


def section_end(depths: Sequence[int], start: int) -> int:
    """Where the section headed at `start` ends, exclusive.

    At the next heading of the same depth or shallower. Deeper headings stay
    inside it. This is the only place that decides where a section ends, so
    nothing that needs a scope can disagree with anything else about what it
    is reading.
    """
    for offset in range(start + 1, len(depths)):
        if 0 < depths[offset] <= depths[start]:
            return offset
    return len(depths)


def extract_section(text: str, heading: str) -> str | None:
    """Return the named section's body, or None when the heading is absent.

    A line inside a fenced code block that happens to read like the heading is
    a quoted example, not the section, so it is skipped.
    """
    lines = text.splitlines()
    depths = heading_depths(lines)
    start = next(
        (i for i, line in enumerate(lines) if line == heading and depths[i]), None)
    if start is None:
        return None
    return "\n".join(lines[start:section_end(depths, start)]).rstrip()


def scope_bounds(lines: Sequence[str], index: int) -> tuple[int, int]:
    """The half open line range of the region line `index` belongs to.

    The innermost section enclosing it, or the preamble when no heading comes
    above it. Every line has a region, so nothing can fall outside them all.
    """
    depths = heading_depths(lines)
    enclosing = next((i for i in range(index, -1, -1) if depths[i]), None)
    if enclosing is not None:
        return enclosing, section_end(depths, enclosing)
    return 0, next((i for i, depth in enumerate(depths) if depth), len(depths))


def flag_claim_scopes(text: str) -> list[str]:
    """Every region of `text` whose own prose discusses the flag.

    One region per mention, which is the text a reader of that sentence is
    reading. Regions are deduplicated, so a section that mentions the flag five
    times is one scope.
    """
    lines = text.splitlines()
    scopes: dict[tuple[int, int], str] = {}
    for index, line in enumerate(lines):
        if AUDIT_FLAG in line:
            start, end = scope_bounds(lines, index)
            scopes[(start, end)] = "\n".join(lines[start:end]).rstrip()
    return list(scopes.values())


def reader_search_space() -> list[Path]:
    """Every Python file the reader scan actually looks at."""
    return [
        path
        for directory in READER_DIRS if directory.is_dir()
        for path in sorted(directory.rglob("*.py")) if "tests" not in path.parts
    ]


def flag_readers() -> list[Path]:
    """Every Python file that actually reads the audit flag."""
    return [
        path for path in reader_search_space()
        if AUDIT_FLAG in path.read_text(encoding="utf-8", errors="replace")
    ]


def unnamed_readers(text: str, readers: set[str]) -> list[str]:
    """Real readers the text never mentions. Empty means the text accounts for all.

    A name counts only where it appears as a whole filename. The plain substring
    test this replaces let a longer filename stand in for a shorter one it ends
    with, and this tree really contains that pair: `bash-guard.py` reads as
    mentioned in any document that mentions `quick-cop-bash-guard.py`,
    `research-agent-bash-guard.py` or `toggle-bash-guard.py`. So the check could
    report a reader as accounted for that no document ever named.

    The two boundaries are not symmetric, because a dot means different things
    on each side. A dot before the name is always part of a longer name, so it
    disqualifies. A dot after it is usually the end of a sentence, so it only
    disqualifies when another word character follows and the name is really a
    stem: `action-gate.py.bak` is a backup file, not a mention of the script.
    """
    return sorted(
        name for name in readers
        if not re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w-])(?!\.\w)", text)
    )


def test_fanout_section_present_in_every_copy():
    missing = [p for p in claude_md_copies()
               if extract_section(p.read_text(encoding="utf-8"), SECTION_HEADING) is None]
    assert not missing, (
        f"{SECTION_HEADING} is missing from:\n"
        + "\n".join(f"  {p}" for p in missing)
    )


def test_fanout_section_identical_across_copies():
    sections = {p: extract_section(p.read_text(encoding="utf-8"), SECTION_HEADING)
                for p in claude_md_copies()}
    reference_path, reference = next(iter(sections.items()))
    drifted = [p for p, body in sections.items() if body != reference]
    assert not drifted, (
        f"{SECTION_HEADING} has drifted from {reference_path}:\n"
        + "\n".join(f"  {p}" for p in drifted)
        + "\nEdit clean-rag/portable/CLAUDE.md, then mirror it to the others."
    )


def test_the_reader_scan_looks_at_real_files():
    """A stale READER_DIRS makes both checks below vacuous, and does it quietly.

    With nothing to scan, no file can be found reading the flag, and the forward
    check skips instead of failing. Assert the search space is real so that
    reads as the bug it is rather than as a clean run.
    """
    assert reader_search_space(), (
        "READER_DIRS matched no Python files, so nothing can be found to read "
        f"{AUDIT_FLAG} and the checks below prove nothing: "
        + ", ".join(str(d) for d in READER_DIRS)
    )


def test_audit_flag_claim_names_every_real_reader():
    """A section that discusses the flag must account for all of its real readers."""
    readers = {p.name for p in flag_readers()}
    if not readers:
        pytest.skip(f"nothing reads {AUDIT_FLAG}; there is no reader list to check")

    offenders = []
    for path in claude_md_copies():
        for scope in flag_claim_scopes(path.read_text(encoding="utf-8")):
            unnamed = unnamed_readers(scope, readers)
            if unnamed:
                offenders.append(
                    f"{path}, under {scope.splitlines()[0]!r}: "
                    f"never names {', '.join(unnamed)}"
                )

    assert not offenders, (
        f"These sections discuss {AUDIT_FLAG} without accounting for every script "
        f"that reads it ({', '.join(sorted(readers))}), so a session can be told "
        f"the flag is dead while a registered hook still gates on it. Naming them "
        f"elsewhere in the file does not count; the reader has only this section:\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_no_doc_names_a_script_that_does_not_read_the_flag():
    """The other direction: a named reader that stopped reading it is also drift."""
    real = {p.name for p in flag_readers()}

    offenders = []
    for path in claude_md_copies():
        for scope in flag_claim_scopes(path.read_text(encoding="utf-8")):
            for name in NAMED_SCRIPT.findall(scope):
                if name not in real:
                    offenders.append(
                        f"{path}: names scripts/{name}, which does not read {AUDIT_FLAG}")

    assert not offenders, "\n".join(offenders)


# ---------------------------------------------------------------------------
# The helpers above only catch drift if they can see it. These prove they do,
# against a tree built to be wrong, so the checks above are not passing by
# accident on a tree that happens to be right.
# ---------------------------------------------------------------------------
def test_extract_section_stops_at_the_next_sibling_heading():
    doc = "## Top\nintro\n\n### Fan-out mode\nbody\n\n## Next\nother\n"
    assert extract_section(doc, SECTION_HEADING) == "### Fan-out mode\nbody"


def test_extract_section_keeps_deeper_headings_inside():
    doc = "### Fan-out mode\nbody\n\n#### Detail\nmore\n\n### Sibling\nout\n"
    section = extract_section(doc, SECTION_HEADING)
    assert "#### Detail" in section and "### Sibling" not in section


def test_extract_section_returns_none_when_absent():
    assert extract_section("## Something else\ntext\n", SECTION_HEADING) is None


def test_drift_between_two_copies_is_detected():
    a = "### Fan-out mode\nthree agents below 50%\n"
    b = "### Fan-out mode\nfive agents below 50%\n"
    assert extract_section(a, SECTION_HEADING) != extract_section(b, SECTION_HEADING)


#: A stand-in reader set for the cases below, so they stay fixed while the real
#: one moves. The checks above read the real set off disk.
SAMPLE_READERS = {
    "skill-verify-gate.py", "verify-gate-cmd.py", "context-nudge.py",
    "rules-compliance-check.py", "action-gate.py",
}


def test_the_shipped_denial_is_caught():
    """The defect that shipped: the flag called dead, no reader named at all."""
    doc = (
        "No lock file is needed. state/audit-in-progress.json is a leftover and\n"
        "nothing reads it anymore, so do not add another flag like it.\n"
    )
    assert unnamed_readers(doc, SAMPLE_READERS) == sorted(SAMPLE_READERS)


def test_a_retraction_that_names_one_real_reader_is_still_caught():
    """The shape a name-presence check passed: one real reader inside a denial."""
    doc = (
        "state/audit-in-progress.json is no longer read by anything.\n"
        "scripts/action-gate.py used to check it, but that gate was retired, so\n"
        "nothing in this repo reads the flag anymore\n"
    )
    assert "action-gate.py" in doc, "presence of one name alone would have passed"
    assert unnamed_readers(doc, SAMPLE_READERS) == [
        "context-nudge.py", "rules-compliance-check.py",
        "skill-verify-gate.py", "verify-gate-cmd.py",
    ]


def test_accurate_prose_passes_however_it_is_phrased():
    """The sentences the old phrasing check rejected. Every one of them is true."""
    for doc in (
        "state/audit-in-progress.json is still load-bearing: "
        "scripts/skill-verify-gate.py exits 2 while it is unset, and "
        "scripts/verify-gate-cmd.py, scripts/context-nudge.py and "
        "scripts/rules-compliance-check.py read it too. scripts/action-gate.py "
        "reads it as well but is registered nowhere.\n",

        "No hook other than scripts/skill-verify-gate.py, scripts/verify-gate-cmd.py, "
        "scripts/context-nudge.py and scripts/rules-compliance-check.py reads "
        "state/audit-in-progress.json; scripts/action-gate.py reads it as plain code.\n",
    ):
        assert unnamed_readers(doc, SAMPLE_READERS) == []


def test_a_reader_list_outside_the_claim_does_not_account_for_it():
    """The hole a whole file scan left, and the reason the scope is the section.

    The denial names nobody. An earlier section lists all five filenames as
    scripts the installer registers, claiming nothing about what they read.
    Read as one blob the document accounts for every reader; read as the section
    a session is actually being told this in, it accounts for none.
    """
    doc = (
        "# Global instructions\n\n"
        "## Installed hooks\n\n"
        "The installer registers `scripts/action-gate.py`,\n"
        "`scripts/context-nudge.py`, `scripts/rules-compliance-check.py`,\n"
        "`scripts/skill-verify-gate.py` and `scripts/verify-gate-cmd.py`.\n\n"
        "### Fan-out mode\n\n"
        f"No lock file is needed. `state/{AUDIT_FLAG}` is a leftover and nothing\n"
        "reads it anymore, so do not add another flag like it.\n"
    )
    assert unnamed_readers(doc, SAMPLE_READERS) == [], (
        "the whole file really does mention all five, which is what made this pass")

    scopes = flag_claim_scopes(doc)
    assert [s.splitlines()[0] for s in scopes] == [SECTION_HEADING]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == sorted(SAMPLE_READERS)


def test_a_denial_under_any_other_heading_is_caught_too():
    """Scope follows the mention, so it cannot be escaped by moving the claim.

    Resolving the scope by looking up one known heading would skip this
    document: the fan-out section is present and says nothing about the flag,
    while the denial sits under a sibling.
    """
    doc = (
        "### Verify gate\n\n"
        f"`state/{AUDIT_FLAG}` is dead and nothing reads it.\n\n"
        f"{SECTION_HEADING}\n\n"
        "Fan out the reviewers by dimension.\n"
    )
    fanout = extract_section(doc, SECTION_HEADING)
    assert fanout is not None, "the heading is in the document"
    assert AUDIT_FLAG not in fanout, (
        "a scope keyed on one heading would skip the denial entirely")

    scopes = flag_claim_scopes(doc)
    assert [s.splitlines()[0] for s in scopes] == ["### Verify gate"]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == sorted(SAMPLE_READERS)


def test_a_denial_above_the_first_heading_is_caught():
    """No mention falls outside every scope. One with no heading above it is the preamble."""
    doc = f"`state/{AUDIT_FLAG}` is dead.\n\n## Later\nunrelated `scripts/action-gate.py`\n"
    scopes = flag_claim_scopes(doc)
    assert len(scopes) == 1 and "## Later" not in scopes[0]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == sorted(SAMPLE_READERS)


def test_a_reader_list_in_a_subsection_of_the_claim_counts():
    """Accurate prose still passes: a subsection is part of the section above it."""
    doc = (
        f"{SECTION_HEADING}\n\n"
        f"Fan out mode does not set `state/{AUDIT_FLAG}`, which is load bearing.\n\n"
        "#### What reads it\n\n"
        "`scripts/skill-verify-gate.py`, `scripts/verify-gate-cmd.py`,\n"
        "`scripts/context-nudge.py`, `scripts/rules-compliance-check.py` and\n"
        "`scripts/action-gate.py`.\n"
    )
    scopes = flag_claim_scopes(doc)
    assert len(scopes) == 1
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == []


def test_a_script_named_outside_the_claim_is_not_read_back_as_a_reader():
    """The reverse direction reads names out of the claim, not out of its parent.

    No copy does this today, so this is the shape the narrow scope protects
    against rather than a description of one: a heading above the claim names a
    script for an unrelated reason, and it does not read the flag. A scope that
    reached the parent section would report accurate prose as drift.
    """
    doc = (
        "## Agent Spawning\n\n"
        "`scripts/bash-guard.py` blocks the dangerous shapes it knows about.\n\n"
        f"{SECTION_HEADING}\n\n"
        f"`state/{AUDIT_FLAG}` is read by `scripts/skill-verify-gate.py`.\n"
    )
    scopes = flag_claim_scopes(doc)
    assert len(scopes) == 1
    assert NAMED_SCRIPT.findall(scopes[0]) == ["skill-verify-gate.py"]


def test_widening_the_scope_loses_the_check_in_both_directions():
    """What actually settles the scope at the innermost section.

    Not the current contents of the documents: measured, the enclosing section
    of every real mention names nothing extra, so the parent would pass too.
    What settles it is that a wider scope is a superset of text, so it can only
    shrink the unnamed set the forward check reports and only grow the names
    the reverse check has to justify. One document shows both losses at once.
    """
    doc = (
        "## Agent Spawning\n\n"
        "`scripts/bash-guard.py` blocks the dangerous shapes it knows about.\n"
        "The installer registers `scripts/action-gate.py`,\n"
        "`scripts/context-nudge.py`, `scripts/rules-compliance-check.py`,\n"
        "`scripts/skill-verify-gate.py` and `scripts/verify-gate-cmd.py`.\n\n"
        f"{SECTION_HEADING}\n\n"
        f"`state/{AUDIT_FLAG}` is a leftover and nothing reads it.\n"
    )
    lines = doc.splitlines()
    mention = next(i for i, line in enumerate(lines) if AUDIT_FLAG in line)
    inner_start, inner_end = scope_bounds(lines, mention)
    inner = "\n".join(lines[inner_start:inner_end])
    parent = "\n".join(lines[0:inner_end])

    assert lines[inner_start] == SECTION_HEADING
    assert unnamed_readers(inner, SAMPLE_READERS) == sorted(SAMPLE_READERS)
    assert unnamed_readers(parent, SAMPLE_READERS) == [], (
        "the forward check goes quiet on the same denial once the scope widens")

    assert NAMED_SCRIPT.findall(inner) == []
    assert "bash-guard.py" in NAMED_SCRIPT.findall(parent), (
        "and the reverse check picks up a name the claim never made")


def test_a_setext_heading_bounds_a_scope_the_way_a_hash_one_does():
    """A name underlined with dashes is a heading, so it starts a new scope.

    Missing this collapsed a whole document into one region, which is the
    file-wide hole in a different disguise: the denial names nobody, and an
    unrelated later section lists all five readers.
    """
    doc = (
        "Old Section\n-----------\n\n"
        f"`state/{AUDIT_FLAG}` is dead and nothing reads it.\n\n"
        "Installed hooks\n----------------\n\n"
        "The installer registers `scripts/action-gate.py`,\n"
        "`scripts/context-nudge.py`, `scripts/rules-compliance-check.py`,\n"
        "`scripts/skill-verify-gate.py` and `scripts/verify-gate-cmd.py`.\n"
    )
    assert unnamed_readers(doc, SAMPLE_READERS) == [], (
        "the whole file really does name all five, which is what made this pass")

    scopes = flag_claim_scopes(doc)
    assert [s.splitlines()[0] for s in scopes] == ["Old Section"]
    assert "Installed hooks" not in scopes[0]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == sorted(SAMPLE_READERS)


def test_an_equals_underline_is_shallower_than_a_dashed_one():
    """`===` is depth 1 and `---` is depth 2, so a dashed section nests inside.

    Same rule as `#` against `##`: the reader list one level down is still part
    of the claim above it, and accurate prose passes.
    """
    doc = (
        "Fan-out mode\n============\n\n"
        f"Fan out mode does not set `state/{AUDIT_FLAG}`, which is load bearing.\n\n"
        "What reads it\n-------------\n\n"
        "`scripts/skill-verify-gate.py`, `scripts/verify-gate-cmd.py`,\n"
        "`scripts/context-nudge.py`, `scripts/rules-compliance-check.py` and\n"
        "`scripts/action-gate.py`.\n"
    )
    lines = doc.splitlines()
    depths = heading_depths(lines)
    assert [(lines[i], d) for i, d in enumerate(depths) if d] == [
        ("Fan-out mode", 1), ("What reads it", 2)]

    scopes = flag_claim_scopes(doc)
    assert [s.splitlines()[0] for s in scopes] == ["Fan-out mode"]
    assert "What reads it" in scopes[0]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == []


def test_a_dash_run_after_a_blank_line_is_a_thematic_break_not_a_heading():
    """Only a paragraph can be underlined, so a rule does not split a section.

    Reading a horizontal rule as a heading would cut the section in two and
    fail the accurate prose above it.
    """
    doc = (
        f"{SECTION_HEADING}\n\n"
        "`scripts/skill-verify-gate.py`, `scripts/verify-gate-cmd.py`,\n"
        "`scripts/context-nudge.py`, `scripts/rules-compliance-check.py` and\n"
        "`scripts/action-gate.py` read it.\n\n"
        "---\n\n"
        f"`state/{AUDIT_FLAG}` is therefore load bearing.\n"
    )
    scopes = flag_claim_scopes(doc)
    assert [s.splitlines()[0] for s in scopes] == [SECTION_HEADING]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == []


def test_an_underline_heads_a_section_only_when_a_paragraph_is_above_it():
    """Every line kind a run of dashes below it leaves alone, and why it matters.

    A blank line is the case above. These are the rest, and each row moves if
    the guard behind it is dropped: the section then starts at a list bullet, a
    closing fence, a stray underline or an indented code line, which is the
    file-wide hole in miniature, since a reader list above such a line stops
    counting as part of the claim below it. Every expectation here is what
    markdown-it-py resolves the same document to.
    """
    for label, doc, expected in (
        ("a bullet item", ["- item one", "---", "after"], [0, 0, 0]),
        ("a block quote", ["> quoted", "---", "after"], [0, 0, 0]),
        ("an ordered item", ["1. item", "---", "after"], [0, 0, 0]),
        ("a closing fence", ["```", "body", "```", "---", "after"], [0, 0, 0, 0, 0]),
        ("another underline", ["Name", "===", "---", "after"], [1, 0, 0, 0]),
        ("an indented code line", ["    code line", "---", "after"], [0, 0, 0]),
        ("an ATX heading", ["# Heading", "---", "after"], [1, 0, 0]),
        ("no line at all", ["---", "after"], [0, 0]),
    ):
        assert heading_depths(doc) == expected, f"{label} is not underlined by `---`"


def test_a_rule_below_a_bulleted_reader_list_does_not_split_the_section():
    """Accurate prose in list form passes too, which is the risk in this file.

    A `---` directly below the last bullet is a thematic break, so the readers
    stay in the same section as the claim. Underlining the bullet instead heads
    a section at it, and the claim is then in a scope naming one reader of five.
    """
    doc = (
        f"{SECTION_HEADING}\n\n"
        "What reads it:\n\n"
        "- `scripts/action-gate.py`\n"
        "- `scripts/context-nudge.py`\n"
        "- `scripts/rules-compliance-check.py`\n"
        "- `scripts/skill-verify-gate.py`\n"
        "- `scripts/verify-gate-cmd.py`\n"
        "---\n\n"
        f"`state/{AUDIT_FLAG}` is read by all five.\n"
    )
    scopes = flag_claim_scopes(doc)
    assert [s.splitlines()[0] for s in scopes] == [SECTION_HEADING]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == []


def test_a_hash_inside_a_fenced_block_is_a_comment_not_a_heading():
    """A shell comment in an example used to truncate the scope around it.

    Every reader is named directly above the denial in the same section, so the
    document is accurate and must pass. Reading the comment as a heading put
    the denial in a section of its own and reported all five as unnamed.
    """
    doc = (
        f"{SECTION_HEADING}\n\n"
        "Readers: `scripts/action-gate.py`, `scripts/context-nudge.py`,\n"
        "`scripts/rules-compliance-check.py`, `scripts/skill-verify-gate.py`,\n"
        "`scripts/verify-gate-cmd.py`.\n\n"
        "```bash\n# not a real heading, just a shell comment\necho done\n```\n\n"
        f"`state/{AUDIT_FLAG}` is read by all five.\n"
    )
    scopes = flag_claim_scopes(doc)
    assert [s.splitlines()[0] for s in scopes] == [SECTION_HEADING]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == []


def test_a_fence_ends_only_on_a_run_that_really_closes_it():
    """A quoted fence inside a longer fence does not end the block early.

    A closing run has to use the same character, be at least as long, and carry
    nothing after it. Getting any of the three wrong lets a `#` line in a
    Markdown example escape the block and read as a heading.
    """
    doc = (
        f"{SECTION_HEADING}\n\n"
        "`scripts/action-gate.py`, `scripts/context-nudge.py`,\n"
        "`scripts/rules-compliance-check.py`, `scripts/skill-verify-gate.py`\n"
        "and `scripts/verify-gate-cmd.py` read it.\n\n"
        "````markdown\n"
        "```python\n"
        "# a hash inside a nested fence\n"
        "```\n"
        "~~~\n"
        "# and inside a run of the other character\n"
        "~~~\n"
        "``` still inside, this run has trailing text\n"
        "````\n\n"
        f"`state/{AUDIT_FLAG}` is read by all five.\n"
    )
    lines = doc.splitlines()
    assert [i for i, depth in enumerate(heading_depths(lines)) if depth] == [0], (
        "only the real heading heads a section")

    scopes = flag_claim_scopes(doc)
    assert [s.splitlines()[0] for s in scopes] == [SECTION_HEADING]
    assert unnamed_readers(scopes[0], SAMPLE_READERS) == []

    # A `#` line has to sit directly below each near-close or nothing escapes:
    # in the document above the next fence opener immediately reopens the gap a
    # wrong rule would have made, which is why it passes with any one of the
    # three rules deleted. This one fails with any one of them deleted.
    isolating = [
        "````markdown",
        "```python",
        "x = 1",
        "```",
        "# only a shorter closing run exposes this",
        "~~~~",
        "# only the other fence character exposes this",
        "```` json",
        "# only a trailing info string exposes this",
        "````",
        "",
        "# after the real close",
    ]
    assert [i for i, depth in enumerate(heading_depths(isolating)) if depth] == [11], (
        "nothing between the outer fences heads a section")


def test_a_backtick_run_with_a_backtick_after_it_opens_no_fence():
    """An info string may not hold a backtick, so this line is an inline span.

    Reading it as a fence opener swallows the rest of the document, the heading
    below it included. markdown-it-py reads the heading here too.
    """
    assert heading_depths(["```json```", "# after"]) == [0, 1]


def test_three_spaces_of_indent_are_prose_and_four_are_a_code_block():
    """Three spaces of indent is still prose here, and a fourth makes it code.

    `CODE_FENCE` and `SETEXT_UNDERLINE` allow up to three, `CODE_INDENT` claims
    four, and moving either bound by one space in either direction changes what
    one of the six documents below resolves to. Past the bound the fence opens
    nothing, the underline heads nothing, and the line above an underline is no
    longer a paragraph. Widening the fence bound hides a heading inside a block
    that never opened; narrowing it reads an indented example's contents as
    headings. markdown-it-py resolves all six the same way this does.
    """
    assert heading_depths(["   ```", "# inside", "   ```", "# after"]) == [0, 0, 0, 1]
    assert heading_depths(["    ```", "# after", "    ```"]) == [0, 1, 0]
    assert heading_depths(["Name", "   ---", "after"]) == [2, 0, 0]
    assert heading_depths(["Name", "    ---", "after"]) == [0, 0, 0]
    assert heading_depths(["   Name", "---", "after"]) == [2, 0, 0]
    assert heading_depths(["    Name", "---", "after"]) == [0, 0, 0]


def test_the_places_this_reads_markdown_more_loosely_than_commonmark():
    """The four simplifications the module docstring names, pinned down.

    Each was compared line by line against markdown-it-py, which is CommonMark
    compliant, and none of them changes what the real copies resolve to. They
    are recorded here so a later reader finds the divergence in a test rather
    than only in prose, and so widening any of them is a deliberate act.
    """
    assert heading_depths(["#Foo"]) == [1], "CommonMark needs a space after the run"
    assert heading_depths(["####### Deep"]) == [7], "CommonMark stops at six"
    assert heading_depths(["one", "two", "---"]) == [0, 2, 0], (
        "CommonMark heads the section at the first line of the paragraph")
    assert heading_depths(
        ["- item", "  ```", "  code", "```", "# after"]) == [0, 0, 0, 0, 1], (
        "CommonMark keeps that fence open, because a run at column 0 does not "
        "close one opened inside a list item, so markdown-it-py finds no heading")


def test_a_heading_quoted_inside_a_fence_is_not_the_section():
    """An example of the section is not the section, in either direction."""
    doc = (
        "## Style\n\n"
        "Write the heading like this:\n\n"
        f"```markdown\n{SECTION_HEADING}\nthe example body\n```\n\n"
        f"{SECTION_HEADING}\n\nthe real body\n"
    )
    assert extract_section(doc, SECTION_HEADING) == f"{SECTION_HEADING}\n\nthe real body"


def test_a_backup_file_is_not_a_mention_of_the_script_it_copies():
    """`action-gate.py.bak` names a backup, not a reader.

    The end of a sentence is not a longer filename, though, so a name followed
    by a full stop still counts as named.
    """
    assert unnamed_readers(
        "`scripts/action-gate.py.bak` is a leftover backup, ignore it.\n",
        {"action-gate.py"}) == ["action-gate.py"]
    assert unnamed_readers(
        "The flag is read by `scripts/action-gate.py`.\n", {"action-gate.py"}) == []
    assert unnamed_readers(
        "The flag is read by scripts/action-gate.py.\n", {"action-gate.py"}) == []


def test_a_longer_filename_does_not_stand_in_for_a_shorter_one():
    """`bash-guard.py` and `quick-cop-bash-guard.py` are both real files here."""
    borrowed = "`scripts/quick-cop-bash-guard.py` reads the flag.\n"
    assert "bash-guard.py" in borrowed, "a substring test would call this named"
    assert unnamed_readers(borrowed, {"bash-guard.py"}) == ["bash-guard.py"]
    assert unnamed_readers("`scripts/bash-guard.py` reads it.\n", {"bash-guard.py"}) == []


def test_flag_readers_finds_a_reader_and_ignores_a_bystander(tmp_path):
    reader = tmp_path / "gate.py"
    reader.write_text(f'FLAG = HOME / "state" / "{AUDIT_FLAG}"\n', encoding="utf-8")
    (tmp_path / "unrelated.py").write_text("x = 1\n", encoding="utf-8")

    found = [p for p in sorted(tmp_path.rglob("*.py"))
             if AUDIT_FLAG in p.read_text(encoding="utf-8")]
    assert found == [reader]
