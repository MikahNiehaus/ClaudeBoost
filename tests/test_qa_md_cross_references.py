"""
Adversarial tests for qa.md prompt cross-reference consistency.

Checks that all step cross-references in the LLM skill prompt match the
actual step names as-defined — a stale reference is a real failure because
an LLM following the prompt literally will look in the wrong step for
variables that were never set there.
"""
import re
import pathlib

QA_MD = pathlib.Path(__file__).parent.parent / ".claude" / "commands" / "qa.md"


def read_qa_md():
    return QA_MD.read_text(encoding="utf-8")


def get_defined_steps(text):
    """Return all steps defined with the pattern **0a-i — ...**"""
    return set(re.findall(r"\*\*(0a-[ivx]+)\b", text))


def get_referenced_steps(text):
    """Return all (step_ref, line_no) pairs referenced inside prose."""
    refs = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"Phase (0a-[ivx]+)", line):
            refs.append((m.group(1), i, line.strip()))
    return refs


def test_all_phase_references_point_to_defined_steps():
    """Every 'Phase 0a-X' reference must match a defined '0a-X' heading."""
    text = read_qa_md()
    defined = get_defined_steps(text)
    refs = get_referenced_steps(text)

    stale = [(ref, lineno, line) for ref, lineno, line in refs if ref not in defined]
    assert stale == [], (
        "Stale cross-references found — these point to steps that do not exist:\n"
        + "\n".join(f"  line {lineno}: references '{ref}' — '{line}'" for ref, lineno, line in stale)
    )


def test_ticket_id_captured_in_correct_step():
    """
    TICKET_ID must be attributed to the step that actually captures it (0a-iii).
    After the rename, the prose at line 170 incorrectly says 'Phase 0a-ii'.
    This test finds every line claiming TICKET_ID is captured and asserts
    it names 0a-iii, not 0a-ii.
    """
    text = read_qa_md()
    lines = text.splitlines()

    bad_lines = []
    for i, line in enumerate(lines, 1):
        if "TICKET_ID" in line and re.search(r'0a-ii(?!i)', line):
            bad_lines.append((i, line.strip()))

    assert bad_lines == [], (
        "TICKET_ID is wrongly attributed to Phase 0a-ii (URL auto-detect), "
        "but it is captured in Phase 0a-iii (ticket tracing):\n"
        + "\n".join(f"  line {no}: {ln}" for no, ln in bad_lines)
    )


def test_ticket_tracing_step_name():
    """Confirm 0a-iii is defined as the ticket tracing step."""
    text = read_qa_md()
    assert "0a-iii — Ticket tracing" in text, (
        "Expected '0a-iii — Ticket tracing' heading not found — step may have been renamed or removed"
    )


def test_general_mode_skip_references_correct_step():
    """
    The general-mode skip at line 85 must reference 0a-iii for ticket tracing,
    not 0a-ii.
    """
    text = read_qa_md()
    # Find the MODE=general skip line
    for i, line in enumerate(text.splitlines(), 1):
        if "MODE = `general`" in line and "skip" in line and "ticket tracing" in line:
            assert "0a-iii" in line, (
                f"Line {i}: general-mode skip should name '0a-iii' for ticket tracing, got: {line.strip()!r}"
            )
            return
    # If we reach here the line format changed — that itself is a finding
    # but don't fail silently; just pass (the above test would catch renamed steps)


def get_defined_top_level_phases(text):
    """Return the set of top-level phase numbers defined as '## Phase N' headings."""
    return set(re.findall(r"^#{2,3} Phase (\d+)\b", text, re.MULTILINE))


def test_all_top_level_phase_references_exist():
    """
    Every 'Phase N' reference in prose must name a phase that actually has a
    heading. Renumbering or inserting a top-level phase was previously guarded
    by nothing — only the 0a-X sub-steps were checked — so a reference to a
    phase that no longer exists sent the model to a section that isn't there.
    """
    text = read_qa_md()
    defined = get_defined_top_level_phases(text)
    assert defined, "No '## Phase N' headings found — the heading format changed"

    stale = []
    for i, line in enumerate(text.splitlines(), 1):
        if re.match(r"^#{2,3} Phase \d+", line):
            continue  # the heading itself defines the phase
        for m in re.finditer(r"Phase (\d+)(?![\d\w.-])", line):
            if m.group(1) not in defined:
                stale.append((m.group(1), i, line.strip()))

    assert stale == [], (
        "References to phases with no heading:\n"
        + "\n".join(f"  line {no}: 'Phase {ph}' — {ln}" for ph, no, ln in stale)
        + f"\n  defined phases: {sorted(defined, key=int)}"
    )


def test_requirements_capture_step_is_defined_and_not_skipped():
    """
    0a-iv writes requirements.md, which is the scope of record the Phase 5d
    judge is measured against. General mode's skip list jumps from 0a-iii to
    0c, so 0a-iv must be named as explicitly required there or general-mode
    sessions silently run with no captured scope.
    """
    text = read_qa_md()
    assert "0a-iv — Capture the full requirements verbatim" in text, (
        "0a-iv requirements-capture step missing — Phase 5d has nothing to judge against"
    )

    for line in text.splitlines():
        if "MODE = `general`" in line and "skip" in line:
            assert "0a-iv" in line, (
                "The general-mode skip list does not mention 0a-iv. It skips from "
                "0a-iii to 0c, so 0a-iv must be called out as required in both "
                f"modes or it is skipped: {line.strip()!r}"
            )
            return
    raise AssertionError("Could not find the MODE = general skip line")


def test_requirements_capture_step_is_actually_run_not_just_mentioned():
    """
    The general-mode skip line must say to RUN 0a-iv, not merely contain the
    string "0a-iv" somewhere in a sentence about skipping other steps.
    test_requirements_capture_step_is_defined_and_not_skipped only checks
    substring presence, so a regression that flips "Run 0a-iv" to "skip
    0a-iv" (or folds 0a-iv into the same skip clause as 0a-iii/0b/0g) would
    still contain the substring "0a-iv" and pass that check while silently
    reintroducing exactly the bug 0a-iv exists to prevent: a general-mode
    session with no captured scope for Phase 5d to judge against.
    """
    text = read_qa_md()
    line = None
    for candidate in text.splitlines():
        if "MODE = `general`" in candidate and "skip" in candidate:
            line = candidate
            break
    assert line is not None, "Could not find the MODE = general skip line"

    # Split on sentence-ish boundaries so "skip Phase 0g" and "Run 0a-iv"
    # are judged as separate clauses even though they share one line.
    clauses = re.split(r"(?<=[.,])\s+", line)
    owning_clauses = [c for c in clauses if "0a-iv" in c]
    assert owning_clauses, f"0a-iv not found in any clause of: {line.strip()!r}"

    for clause in owning_clauses:
        assert not re.search(r"\bskip\b", clause, re.IGNORECASE), (
            "0a-iv is named in a clause that tells the model to skip it, not "
            f"run it: {clause.strip()!r}"
        )
        assert re.search(r"\brun\b", clause, re.IGNORECASE), (
            f"0a-iv's clause never says to run it: {clause.strip()!r}"
        )


THREE_JUDGE_INPUTS = [
    "THE FULL REQUIREMENTS, VERBATIM",
    "PROOF ARTIFACTS (verified to exist on disk)",
    "TOOL INVENTORY",
]


def test_evidence_judge_prompt_sends_only_the_three_documented_inputs():
    """
    5d-i and the Mode B contract both say the judge gets exactly three things
    (requirements, proof artifact paths, tool inventory) and explicitly NOT the
    QA session's own confidence or verdict about itself. Anything else in the
    spawn template is a fourth input. The one that was there, the /audit
    checklist result, carries /audit's own VERDICT and CONFIDENCE lines
    (audit.md's output format), which is the self-assessment a judge must never
    read: a judge fed the session's own verdict inherits the session's blind
    spot, and that bias is what the three-things rule exists to prevent.

    Asserts the whole block list, not the absence of one heading, so renaming
    the fourth block cannot slip it back in.
    """
    text = read_qa_md()
    start = text.index("#### 5d-ii — Spawn the judge")
    end = text.index("#### 5d-iii", start)
    spawn_section = text[start:end]

    body = re.search(r'prompt="""(.*?)"""', spawn_section, re.DOTALL)
    assert body, "Could not find the judge's spawn prompt body in 5d-ii"
    prompt = body.group(1)

    blocks = [b.strip() for b in re.findall(r"^=== (.+?) ===\s*$", prompt, re.MULTILINE)]
    assert blocks == THREE_JUDGE_INPUTS, (
        "The judge spawn prompt does not carry exactly the three documented "
        f"inputs.\n  found:    {blocks}\n  expected: {THREE_JUDGE_INPUTS}"
    )

    for banned in ("/audit", "confidence"):
        assert banned not in prompt.lower(), (
            f"The judge spawn prompt mentions {banned!r}. The judge must not "
            "receive the QA session's own assessment of itself."
        )


def test_evidence_judge_is_bad_cop_in_judge_mode():
    """
    Phase 5d must spawn bad-cop with the MODE: evidence-judge marker. bad-cop
    routes on that exact string; without it the agent runs Mode A and tries to
    write adversarial tests against a diff that may not exist.
    """
    text = read_qa_md()
    assert "MODE: evidence-judge" in text, (
        "Phase 5d does not pass 'MODE: evidence-judge' — bad-cop would default to Mode A"
    )
    assert 'subagent_type="bad-cop"' in text, (
        "Phase 5d does not spawn bad-cop as the evidence judge"
    )


def test_judge_mode_marker_matches_bad_cop_router():
    """
    The marker qa.md sends and the marker bad-cop routes on must be the same
    string. These live in two files with no shared constant, so a reword in
    either one silently breaks the routing.
    """
    qa_text = read_qa_md()
    marker = "MODE: evidence-judge"
    assert marker in qa_text, f"qa.md no longer sends {marker!r}"

    checked = []
    for agent_path in (
        pathlib.Path(__file__).parent.parent
        / "clean-rag" / "portable" / "agents" / "bad-cop.md",
        pathlib.Path.home() / ".claude" / "agents" / "bad-cop.md",
    ):
        if not agent_path.exists():
            continue
        agent_text = agent_path.read_text(encoding="utf-8")
        assert marker in agent_text, (
            f"{agent_path} does not mention {marker!r}, so it cannot route into "
            "Mode B when qa.md sends it"
        )
        # Anchor to line start: the mode router near the top quotes
        # "## Mode B: QA evidence judge" as a pointer, and a plain substring
        # check is satisfied by that pointer even when the real section is gone.
        assert re.search(r"^# Mode B: QA evidence judge\s*$", agent_text, re.MULTILINE), (
            f"{agent_path} has no top-level '# Mode B: QA evidence judge' section "
            "to route into (a reference to it in the router does not count)"
        )
        checked.append(agent_path)

    assert checked, "Found no bad-cop.md in either the portable or installed location"


def test_judge_loop_requires_a_fresh_judge_each_round():
    """
    The loop's whole value is a new context per round. If it ever allows
    continuing the previous judge, the judge is reviewing whether its own
    argument was addressed, which is the bias the loop exists to avoid.
    """
    text = read_qa_md()
    assert "spawn a fresh judge" in text.lower(), (
        "Phase 5d does not require a fresh judge per round"
    )
    assert "SendMessage" in text, (
        "Phase 5d should explicitly forbid continuing the previous judge via "
        "SendMessage — without naming it, reusing the agent id looks allowed"
    )


def test_proof_deck_phase_only_uses_real_pptx_subcommands():
    """
    Phase 7 shells out to pptx_env.py. Every subcommand it names must actually
    be handled by that script, or the deck step dies on an unknown command.
    """
    text = read_qa_md()
    assert "## Phase 7: Proof Deck" in text, "Phase 7 proof deck missing"

    used = set(re.findall(r'pptx_env\.py" (\w+)', text))
    assert used, "Phase 7 names no pptx_env.py subcommands"

    script = pathlib.Path.home() / ".claude" / "skills" / "powerpoint" / "scripts" / "pptx_env.py"
    if not script.exists():
        return  # skill not installed on this machine; nothing to check against

    src = script.read_text(encoding="utf-8")
    handled = set(re.findall(r'cmd == "(\w+)"', src))
    for group in re.findall(r"cmd in \(([^)]*)\)", src):
        handled.update(re.findall(r'"(\w+)"', group))

    unknown = sorted(used - handled)
    assert unknown == [], (
        f"Phase 7 calls pptx_env.py subcommands that script does not handle: {unknown}\n"
        f"  handled: {sorted(handled)}"
    )


def test_proof_deck_does_not_redraw_over_annotated_screenshots():
    """
    TC-NNN-after.png already has a red box baked in by Phase 3 Step 4. Drawing
    a second box in python-pptx would land at the wrong place, because the
    element rect is in page pixels and the picture is rescaled on the slide.
    Phase 7 must say so.
    """
    text = read_qa_md()
    deck = text.split("## Phase 7: Proof Deck", 1)[1]
    assert "Place those as-is" in deck, (
        "Phase 7 does not tell the model to place pre-annotated screenshots unchanged"
    )
    assert "never off the raw" in deck or "never off raw" in deck, (
        "Phase 7 does not warn that the red-box overlay must scale off the placed "
        "picture rather than raw pixel dimensions"
    )


if __name__ == "__main__":
    # Run inline so a single `python tests/test_qa_md_cross_references.py` proves the bug
    import sys

    failures = []

    for fn_name in [
        "test_all_phase_references_point_to_defined_steps",
        "test_ticket_id_captured_in_correct_step",
        "test_ticket_tracing_step_name",
        "test_general_mode_skip_references_correct_step",
        "test_all_top_level_phase_references_exist",
        "test_requirements_capture_step_is_defined_and_not_skipped",
        "test_requirements_capture_step_is_actually_run_not_just_mentioned",
        "test_evidence_judge_prompt_sends_only_the_three_documented_inputs",
        "test_evidence_judge_is_bad_cop_in_judge_mode",
        "test_judge_mode_marker_matches_bad_cop_router",
        "test_judge_loop_requires_a_fresh_judge_each_round",
        "test_proof_deck_phase_only_uses_real_pptx_subcommands",
        "test_proof_deck_does_not_redraw_over_annotated_screenshots",
    ]:
        fn = globals()[fn_name]
        try:
            fn()
            print(f"  PASS  {fn_name}")
        except AssertionError as e:
            print(f"  FAIL  {fn_name}")
            print(f"        {e}")
            failures.append(fn_name)

    print()
    if failures:
        print(f"FAILED: {len(failures)} test(s)")
        sys.exit(1)
    else:
        print("All tests passed.")
