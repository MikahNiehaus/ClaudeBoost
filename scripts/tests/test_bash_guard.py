"""
Tests for scripts/bash-guard.py (PreToolUse/Bash hook).

The hook reads {"tool_input": {"command": "..."}} on stdin and exits:
  0  — allow
  2  — block (reason on stderr)

Groups:
  ALLOW — regression cases that were false positives (should never block)
  BLOCK — intentional blocks (should always block, message checked where noted)
  EDGE  — _strip_quoted corner cases
"""
from __future__ import annotations

import pytest

from helpers import run_hook, pretooluse


def _bash(command: str) -> dict:
    return pretooluse("Bash", {"command": command})


def _stderr(result) -> str:
    return result.stderr.decode()


# ---------------------------------------------------------------------------
# Helpers so parametrize IDs stay readable
# ---------------------------------------------------------------------------

def allow(command: str):
    result = run_hook("bash-guard.py", _bash(command))
    assert result.returncode == 0, (
        f"Expected ALLOW but got BLOCK.\nCommand: {command!r}\nstderr: {_stderr(result)}"
    )


def block(command: str, *, message_contains: str | None = None):
    result = run_hook("bash-guard.py", _bash(command))
    assert result.returncode == 2, (
        f"Expected BLOCK but got ALLOW.\nCommand: {command!r}"
    )
    if message_contains is not None:
        stderr = _stderr(result)
        assert message_contains in stderr, (
            f"Block message missing expected text.\n"
            f"Expected: {message_contains!r}\nGot: {stderr!r}"
        )


# ===========================================================================
# ALLOW — regression cases (false positives that were being blocked)
# ===========================================================================

class TestAllow:
    def test_pipe_or_echo_in_single_quoted_curl_body(self):
        """|| echo inside a -d '...' body is not a shell operator — don't block it."""
        cmd = """curl -X POST http://127.0.0.1:8612/search -d '{"query":"|| echo test"}'"""
        allow(cmd)

    def test_pipe_or_echo_in_double_quoted_commit_message(self):
        """|| echo inside a git commit -m "..." is just text in the message."""
        cmd = 'git commit -m "fix: handle || echo fallback case"'
        allow(cmd)

    def test_dollar_var_in_single_quoted_grep_pattern(self):
        """$VAR inside single quotes never expands — scanner shouldn't care."""
        cmd = r"grep -r '\$TEM[P]' /some/path"
        allow(cmd)

    def test_dollar_var_in_single_quoted_echo(self):
        """echo '$CLAUDEBOOST_PYTHON ...' is quoting for display, not expansion."""
        cmd = "echo '$CLAUDEBOOST_PYTHON $CLAUDEBOOST_HOME/scripts/foo.py'"
        allow(cmd)

    def test_brace_form_var_is_allowed(self):
        """${VAR} brace form is explicitly excluded by the scanner — don't block it."""
        cmd = "echo ${SOME_VAR}"
        allow(cmd)

    def test_brace_var_in_path(self):
        """${HOME} in a path argument — brace form, should be allowed."""
        cmd = "ls ${HOME}/projects"
        allow(cmd)

    def test_python3_singleline_c_string(self):
        """Single-line python3 -c is fine — only multiline triggers the scanner."""
        cmd = 'python3 -c "import sys; print(sys.version)"'
        allow(cmd)

    def test_python_singleline_c_with_semicolons(self):
        """Multiple statements on one line joined with ; — still a single line."""
        cmd = 'python3 -c "import json; import sys; print(json.dumps({}))"'
        allow(cmd)

    def test_curl_localhost_127(self):
        """curl to 127.0.0.1 is explicitly allowed."""
        cmd = "curl -s http://127.0.0.1:8612/status"
        allow(cmd)

    def test_curl_localhost_name(self):
        """curl to localhost is explicitly allowed."""
        cmd = "curl -X POST http://localhost:3000/api/test"
        allow(cmd)

    def test_curl_localhost_with_data(self):
        """curl with JSON body to localhost — the body text shouldn't trip url check."""
        cmd = """curl -s -X POST http://127.0.0.1:8612/context -H "Content-Type: application/json" -d '{"agent":"test"}'"""
        allow(cmd)

    def test_plain_ls(self):
        allow("ls -la /tmp")

    def test_git_status(self):
        allow("git status")

    def test_npm_test(self):
        allow("npm test")

    def test_git_log(self):
        allow("git log --oneline -10")

    def test_git_diff(self):
        allow("git diff HEAD~1")


# ===========================================================================
# BLOCK — intentional behavior (must never be weakened)
# ===========================================================================

class TestBlock:

    # cd + && compound -------------------------------------------------

    def test_cd_npx_tsc_blocked_with_correct_message(self):
        """cd && npx tsc --noEmit should block AND tell Claude to use -p flag."""
        cmd = "cd /Users/demo/server && npx tsc --noEmit"
        block(cmd, message_contains="tsc --noEmit -p")

    def test_cd_git_blocked_with_git_C_hint(self):
        """cd && git should block AND hint at git -C."""
        cmd = "cd /some/repo && git status"
        block(cmd, message_contains="git -C")

    def test_cd_make_blocked(self):
        cmd = "cd /path/to/proj && make build"
        block(cmd, message_contains="make -C")

    def test_cd_generic_script_blocked(self):
        cmd = "cd /path && ./run.sh"
        block(cmd)

    def test_cd_npm_blocked(self):
        cmd = "cd /Users/demo/client && npm install"
        block(cmd)

    # || echo / || print fallbacks ---------------------------------------

    def test_real_or_echo_fallback_blocked(self):
        """cat file || echo missing — a genuine shell fallback, not quoted."""
        cmd = "cat /tmp/somefile 2>/dev/null || echo missing"
        block(cmd)

    def test_real_or_print_fallback_blocked(self):
        cmd = "cmd || print result"
        block(cmd)

    def test_conditional_or_echo_with_test_builtin(self):
        """[ -f file ] && echo yes || echo no — real shell operators."""
        cmd = '[ -f "/tmp/somefile" ] && echo yes || echo no'
        block(cmd)

    # $VAR bare env expansion -------------------------------------------

    def test_bare_dollar_temp_blocked(self):
        """$TEMP in shell position triggers simple_expansion scanner."""
        cmd = "ls $TEMP"
        block(cmd)

    def test_bare_dollar_home_blocked(self):
        cmd = "ls $HOME/projects"
        block(cmd)

    def test_dollar_var_in_double_quotes_blocked(self):
        """$TEMP inside double quotes still expands at runtime — still blocked."""
        cmd = 'ls "$TEMP/x"'
        block(cmd)

    def test_dollar_claudeboost_home_blocked(self):
        """$CLAUDEBOOST_HOME is the canonical case from the original ticket."""
        cmd = '"$CLAUDEBOOST_PYTHON" "$CLAUDEBOOST_HOME/scripts/foo.py"'
        block(cmd)

    # Multiline python -c -----------------------------------------------

    def test_multiline_python_c_blocked(self):
        """Actual newline in the command string — that's what triggers the scanner."""
        cmd = 'python3 -c "import sys\nprint(sys.argv)"'
        block(cmd)

    def test_multiline_python_c_with_comment_blocked(self):
        cmd = 'python3 -c "\nimport json\n# parse it\nprint(json.dumps({}))"'
        block(cmd)

    # cat heredoc -------------------------------------------------------

    def test_cat_heredoc_blocked(self):
        cmd = "cat > /tmp/foo.py << 'EOF'"
        block(cmd)

    def test_cat_heredoc_double_quote_blocked(self):
        cmd = 'cat > /tmp/bar.sh << "EOF"'
        block(cmd)

    # curl external URL -------------------------------------------------

    def test_curl_external_https_blocked(self):
        cmd = "curl https://api.example.com/data"
        block(cmd)

    def test_curl_external_http_blocked(self):
        cmd = "curl http://external-service.io/endpoint"
        block(cmd)

    # ssh / scp external -----------------------------------------------

    def test_ssh_external_host_blocked(self):
        cmd = "ssh user@example.com ls"
        block(cmd)

    def test_scp_external_host_blocked(self):
        cmd = "scp /tmp/file.txt user@remote.server:/home/user/"
        block(cmd)

    def test_nc_external_host_blocked(self):
        cmd = "nc evil.host 4444"
        block(cmd)

    def test_ssh_localhost_allowed(self):
        cmd = "ssh user@localhost echo hi"
        allow(cmd)

    def test_nc_localhost_allowed(self):
        cmd = "nc localhost 8080"
        allow(cmd)

    # Co-Authored-By trailer --------------------------------------------

    def test_coauthored_by_trailer_blocked(self):
        """The anti-attribution policy blocks this trailer in commit messages."""
        cmd = 'git commit -m "feat: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>"'
        block(cmd, message_contains="Co-Authored-By")

    def test_coauthored_by_case_insensitive_blocked(self):
        cmd = 'git commit -m "fix\n\nco-authored-by: Bot <bot@example.com>"'
        block(cmd)

    # Backslash-escaped spaces in paths ---------------------------------

    def test_backslash_spaces_in_path_blocked(self):
        cmd = "ls /Users/geoff/My\\ Documents/file.txt"
        block(cmd)

    def test_backslash_spaces_nested_path_blocked(self):
        cmd = "cd /path/F\\ and\\ B\\ PWA/"
        block(cmd)


# ===========================================================================
# EDGE — _strip_quoted corner cases
# ===========================================================================

class TestStripQuotedEdgeCases:

    def test_escaped_double_quote_inside_dq_string_does_not_break_stripping(self):
        """An escaped quote mid-string — e.g. "a\\"b" — shouldn't confuse the regex.
        If stripping breaks, the real || echo after the string might slip through."""
        # The outer single quotes here are Python quoting; the command has a
        # double-quoted string with an escaped double quote inside it.
        cmd = r'git commit -m "fix \"quote\" issue" || echo done'
        block(cmd)

    def test_real_pipe_or_echo_after_single_quoted_containing_pipe_or_echo(self):
        """A quoted literal with || echo is harmless, but a REAL || echo after it should block."""
        cmd = "grep 'foo || echo bar' /tmp/x || echo fallback"
        block(cmd)

    def test_dollar_var_in_double_quotes_blocks_even_with_single_quoted_var_earlier(self):
        """$VAR in double quotes still expands even though a '$OTHER' appeared earlier in single quotes."""
        cmd = "echo '$OTHER' && ls \"$TEMP/logs\""
        block(cmd)

    def test_single_quoted_dollar_var_followed_by_safe_command(self):
        """Only single-quoted $VAR — the rest of the command is safe, so allow it."""
        cmd = "echo '$CLAUDEBOOST_PYTHON script' && ls /tmp"
        allow(cmd)

    def test_pipe_or_echo_only_inside_double_quoted_commit_message(self):
        """|| echo buried in a double-quoted message — stripped, no block."""
        cmd = 'git commit -m "handle || echo case in parser"'
        allow(cmd)
