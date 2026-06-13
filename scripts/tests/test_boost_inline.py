"""
Tests for scripts/boost-inline.py — inline terminal header/banner.

Simple script: prints HEADER without args, DONE_BANNER with --done.
"""
from __future__ import annotations

from helpers import run_script


class TestBoostInline:
    def test_exits_0_no_args(self):
        result = run_script("boost-inline.py")
        assert result.returncode == 0

    def test_prints_claudeboost_header(self):
        result = run_script("boost-inline.py")
        assert result.returncode == 0
        output = result.stdout.decode("utf-8", errors="replace")
        # ANSI box drawing present — script printed something
        assert len(output.strip()) > 0
        assert "======" in output  # box border

    def test_done_flag_prints_banner(self):
        result = run_script("boost-inline.py", args=["--done"])
        assert result.returncode == 0
        output = result.stdout.decode("utf-8", errors="replace")
        assert len(output.strip()) > 0
        assert "======" in output  # box border

    def test_done_and_no_done_differ(self):
        header = run_script("boost-inline.py")
        done = run_script("boost-inline.py", args=["--done"])
        # Both succeed but output different content
        assert header.stdout != done.stdout

    def test_no_stderr(self):
        result = run_script("boost-inline.py")
        assert result.stderr == b""
