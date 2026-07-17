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


if __name__ == "__main__":
    # Run inline so a single `python tests/test_qa_md_cross_references.py` proves the bug
    import sys

    failures = []

    for fn_name in [
        "test_all_phase_references_point_to_defined_steps",
        "test_ticket_id_captured_in_correct_step",
        "test_ticket_tracing_step_name",
        "test_general_mode_skip_references_correct_step",
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
