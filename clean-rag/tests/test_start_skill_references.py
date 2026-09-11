"""Everything /start tells a session to run must actually exist and be in order.

`/start` is a procedure a model follows literally, so a subcommand that was
renamed, or a step that drifted out of sequence, becomes a wrong action rather
than a typo. Two things are pinned:

* every `pptx_env.py <subcommand>` named in prose, in either skill that names
  one, is a subcommand the script dispatches, read out of `main()` rather than
  mirrored into a list here. `/start` delegates its step 2c to the `powerpoint`
  skill, so a stale subcommand in either file breaks the same run
* the steps stay in the order the procedure depends on — the teaching video is
  built from both research reports and shown before the consult, so it has to
  sit after 2b and before 3

Same approach as test_skill_rag_routes.py: the truth comes from the real file.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PORTABLE = REPO / "clean-rag" / "portable"
START_SKILL = PORTABLE / "skills" / "start" / "SKILL.md"
POWERPOINT_SKILL = PORTABLE / "skills" / "powerpoint" / "SKILL.md"
PPTX_ENV = PORTABLE / "skills" / "powerpoint" / "scripts" / "pptx_env.py"

#: Both files name subcommands, in two conventions each: `pptx_env.py doctor`
#: inside one code span, and `"${HOME}/.../pptx_env.py" doctor` where the quote
#: closes the interpolated path and the command continues. A closing backtick
#: means the code span ended, so the next word is prose ("`pptx_env.py` and
#: substitute that path") and must not be read as a subcommand.
NAMED_SUBCOMMAND = re.compile(r'pptx_env\.py"?\s+([a-z][a-z0-9_-]*)')

#: Every skill file that tells a session to run the helper.
SKILLS_NAMING_SUBCOMMANDS = (START_SKILL, POWERPOINT_SKILL)


def dispatched_subcommands(source: str) -> set[str]:
    """The subcommands main() actually accepts: `cmd == "x"` and `cmd in (...)`."""
    found = set(re.findall(r'cmd\s*==\s*"([a-z0-9_-]+)"', source))
    for group in re.findall(r'cmd\s+in\s+\(([^)]*)\)', source):
        found.update(re.findall(r'"([a-z0-9_-]+)"', group))
    return found


def test_every_named_pptx_subcommand_is_dispatched():
    real = dispatched_subcommands(PPTX_ENV.read_text(encoding="utf-8"))
    assert real, "parsed no subcommands out of pptx_env.py main()"

    offenders = []
    for skill in SKILLS_NAMING_SUBCOMMANDS:
        named = set(NAMED_SUBCOMMAND.findall(skill.read_text(encoding="utf-8")))
        assert named, f"{skill.name} names no pptx_env.py subcommand; the regex missed them"
        for unknown in sorted(named - real):
            offenders.append(f"{skill.name} names {unknown}")

    assert not offenders, (
        "These skills name pptx_env.py subcommands that do not exist: "
        f"{'; '.join(offenders)}. Real ones: {', '.join(sorted(real))}"
    )


def test_teaching_video_step_sits_between_the_summary_and_the_consult():
    text = START_SKILL.read_text(encoding="utf-8")
    positions = {}
    for label in ("**2b.", "**2c.", "**3."):
        index = text.find(label)
        assert index != -1, f"{START_SKILL.name} has no step {label}"
        positions[label] = index

    assert positions["**2b."] < positions["**2c."] < positions["**3."], positions


# ---------------------------------------------------------------------------
# Proof the parser above sees what it claims to see, rather than passing on an
# empty set.
# ---------------------------------------------------------------------------
def test_dispatcher_parser_reads_both_equality_and_membership_forms():
    source = '''
    if cmd == "doctor":
        return doctor()
    if cmd in ("soffice", "ffmpeg", "ffprobe"):
        return 0
    '''
    assert dispatched_subcommands(source) == {"doctor", "soffice", "ffmpeg", "ffprobe"}


def test_a_renamed_subcommand_is_caught():
    real = dispatched_subcommands('if cmd == "diagnose":\n    pass\n')
    named = set(NAMED_SUBCOMMAND.findall("Run `pptx_env.py doctor` first."))
    assert named - real == {"doctor"}


def test_subcommand_regex_reads_both_quoting_conventions():
    """start/SKILL.md writes it bare; powerpoint/SKILL.md closes a quoted path first."""
    bare = 'Run `pptx_env.py doctor` first.'
    quoted = 'python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" topdf deck.pptx'
    assert set(NAMED_SUBCOMMAND.findall(bare)) == {"doctor"}
    assert set(NAMED_SUBCOMMAND.findall(quoted)) == {"topdf"}


def test_subcommand_regex_ignores_prose_and_flags():
    """A closed code span ends the command; the next word is English, not a subcommand."""
    prose = "find it once with Glob on `**/scripts/pptx_env.py` and substitute that path"
    assert NAMED_SUBCOMMAND.findall(prose) == []
    assert NAMED_SUBCOMMAND.findall("Run `pptx_env.py --help` for the full list.") == []
