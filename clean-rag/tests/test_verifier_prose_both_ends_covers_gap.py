"""Closing re-check on the spaced-path fix in verifier_state.py.

_is_file_token now accepts a token containing interior whitespace when its
FIRST and LAST whitespace-split segments each read as a file on their own
(_is_bare_file_token). The stated reasoning: a real path's space is interior,
so both ends stay path shaped, while an ordinary prose sentence opens on a
plain word and fails the first-segment check.

That holds for the sentences test_verifier_spaced_path_covers_gap.py and
test_verifier_covers_scoping_gap.py already assert against ("I reviewed the
src/app.py entry point.", "src/app.py was the only file that mattered.", and
similar), because each of those opens or closes on an ordinary word ("I",
"mattered.") that is not file shaped.

It does not hold in general. A sentence that happens to both open and close
on a file-shaped word passes the same check a real spaced path does, because
_is_bare_file_token only ever looks at the two end segments, never the words
between them:

    "app.py breaks config.py"
    "foo.py was replaced by bar.py"
    "src/a.py imports src/b.py"
    "Makefile calls Dockerfile"

Each of these is accepted by _is_file_token and recorded into the covers list
verbatim, interior words and all, exactly the "sentence below the marker" the
whitespace check exists to keep out.

The practical blast radius is bounded, and this file proves the bound rather
than just asserting the accept: file_in_scope compares a queried file's full
normalized path against each covered entry as one indivisible string (or, if
the entry contains "*", as a glob built from that whole string). A multi-word
sentence recorded verbatim therefore never equals a real single-file path and
never ends with "/" + a real single-file path, so it cannot mark an unrelated
real file verified. It is inert garbage in the record, not a verification
bypass. That is what the last two tests below establish, end to end through
record_verifier and check_file_verified.

Still a real defect: it violates the guard's own documented purpose (keep
prose out of the covers list) on an input shape the current tests never
construct, and it pollutes the audit trail with a nonsense "file" entry a
human has to read past. Filed as a currently-reachable gap, not a regression
in the fix under review, and not a false-verification risk given the
bound proven here.
"""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"


def _load(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, HOOKS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vs = _load("verifier_state.py", "vs_prose_both_ends_gap")


class TestSentenceThatOpensAndClosesOnAFileShapedWord:
    """The class of prose the whitespace check was not written to catch."""

    def test_is_file_token_accepts_it(self):
        assert vs._is_file_token("app.py breaks config.py") is True, (
            "documents the current (unwanted) behavior: a plain sentence "
            "that happens to open and close on a .py-suffixed word passes "
            "the same shape check a real spaced path does"
        )

    def test_covered_files_in_block_records_it_verbatim(self):
        block = ["VERIFIED: real.py", "app.py breaks config.py"]
        assert vs.covered_files_in_block(block) == [
            "real.py",
            "app.py breaks config.py",
        ]

    def test_known_bare_filenames_at_both_ends_of_a_sentence_also_pass(self):
        block = ["VERIFIED: real.py", "Makefile calls Dockerfile"]
        assert vs.covered_files_in_block(block) == [
            "real.py",
            "Makefile calls Dockerfile",
        ]


class TestTheGarbageEntryCannotVerifyARealFile:
    """The bound: recorded verbatim, but inert against file_in_scope because
    it is compared as one indivisible string, never split back apart."""

    def test_file_in_scope_never_matches_a_real_single_file_path(self):
        covers = ["real.py", "app.py breaks config.py"]
        for candidate in ("app.py", "config.py", "src/app.py", "breaks"):
            assert vs.file_in_scope(candidate, covers) is False, (
                f"the garbage covers entry unexpectedly matched {candidate!r}"
            )

    def test_end_to_end_check_file_verified_stays_false_for_the_real_files(
        self, tmp_path, monkeypatch
    ):
        app = tmp_path / "app.py"
        config = tmp_path / "config.py"
        app.write_text("# app\n")
        config.write_text("# config\n")
        time.sleep(0.05)

        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        vs.record_verifier(
            "prose-both-ends-session",
            "$ pytest -q\n1 passed in 0.10s\n\n"
            "VERIFIED: real.py\n"
            "app.py breaks config.py\n",
            agent_type="bad-cop",
        )

        for f in (app, config):
            ok, reason = vs.check_file_verified("prose-both-ends-session", str(f))
            assert ok is False, (
                f"{f} was marked verified by the garbage sentence entry, "
                f"which would be a real guard bypass: {reason!r}"
            )
