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
        """An escaped quote mid-string shouldn't confuse _strip_quoted, so a real
        bare $VAR after the string is still detected and blocked."""
        cmd = r'git commit -m "fix \"quote\" issue" && ls $HOME'
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


# ===========================================================================
# INLINE-ASSIGNED VARS — a var you define and use in the same command is
# locally scoped, not an environment expansion, so don't block it.
# ===========================================================================

class TestInlineAssignedVars:

    def test_sha_assigned_then_referenced(self):
        """The reported case: SHA=$(git rev-parse HEAD) then $SHA in a query."""
        cmd = (
            "SHA=$(git rev-parse HEAD); until az pipelines runs list "
            "--organization https://dev.azure.com/org --project App --top 6 "
            "--query \"[?sourceVersion=='$SHA']\" -o tsv; do sleep 10; done"
        )
        allow(cmd)

    def test_sha_used_in_double_quotes(self):
        allow('SHA=$(git rev-parse HEAD); echo "checking $SHA"')

    def test_for_loop_variable_bare(self):
        allow("for hook in SessionStart Stop; do echo $hook; done")

    def test_base_assigned_used_in_diff(self):
        allow('BASE=main && git diff "origin/$BASE...HEAD"')

    def test_read_loop_variable(self):
        allow("while read -r line; do echo $line; done < /tmp/f")

    def test_multiple_inline_assignments(self):
        allow("A=1 B=2; echo $A $B")

    def test_assigned_var_does_not_exempt_real_env_var(self):
        """X is assigned, but $TEMP in the same command is still an env expansion."""
        block("X=$(date); ls $TEMP")

    def test_comparison_equals_is_not_an_assignment(self):
        """`= ` here is a test comparison, not an assignment, so $x stays blocked."""
        block('test "$x" = "$y"')


# ===========================================================================
# CD COMPOUND — only `cd <path> && <cmd>` immediate compounds block. A
# semicolon-separated cd, or a && that joins two later commands, is fine.
# ===========================================================================

class TestCdCompound:

    def test_cd_semicolon_then_git_add_and_commit(self):
        """cd /path; git add X && git commit — the && joins the gits, not the cd."""
        cmd = (
            "cd /Users/geoff/repo; "
            "git add a.ts b.ts && git commit -m \"fix: thing\""
        )
        allow(cmd)

    def test_cd_semicolon_then_git_commit_heredoc(self):
        """The reported case: cd ; git add && git commit -m \"$(cat <<'EOF' ...)\"."""
        cmd = (
            "cd /Users/geoff/repo; git add x.ts && "
            "git commit -m \"$(cat <<'EOF'\nfix: mfa\nEOF\n)\""
        )
        allow(cmd)

    def test_cd_semicolon_standalone(self):
        """cd /path; git status — cd ended by ; is standalone, no compound."""
        allow("cd /repo; git status")

    def test_cd_compound_inside_quoted_message_is_not_a_real_cd(self):
        """`cd /x && y` buried in a commit message must not trip the cd check."""
        allow('git commit -m "ran cd /tmp && rm -rf x by mistake"')

    def test_real_cd_compound_still_blocks(self):
        block("cd /repo && git status", message_contains="git -C")

    def test_real_cd_compound_with_quoted_path_still_blocks(self):
        block('cd "/path with spaces" && git log')


# ===========================================================================
# || echo fallbacks are NO LONGER blocked — ClaudeBoost's catch-all "Bash"
# allow entry means echo never prompts, so the old block was pure noise.
# ===========================================================================

class TestCompoundFallbackAllowed:

    def test_or_echo_fallback_allowed(self):
        allow("cat /tmp/somefile 2>/dev/null || echo missing")

    def test_or_print_fallback_allowed(self):
        allow("cmd || print result")

    def test_and_echo_or_echo_idiom_allowed(self):
        allow('[ -f "/tmp/somefile" ] && echo yes || echo no')

    def test_token_check_idiom_allowed(self):
        allow('[ -n "${GH_TOKEN}" ] && echo set || echo unset')


# ===========================================================================
# OFF SWITCH — CLAUDEBOOST_BASH_GUARD=off lets everything through.
# ===========================================================================

class TestOffSwitch:

    def _run(self, command, value):
        return run_hook("bash-guard.py", _bash(command), env_overrides={"CLAUDEBOOST_BASH_GUARD": value})

    def test_off_lets_a_normally_blocked_command_through(self):
        for value in ("off", "0", "false", "disabled", "no", "OFF"):
            r = self._run("cd /repo && git status", value)
            assert r.returncode == 0, f"CLAUDEBOOST_BASH_GUARD={value!r} should disable the guard"

    def test_unset_or_on_still_guards(self):
        # empty / "on" / anything else keeps the guard active
        for value in ("", "on", "1", "true"):
            r = self._run("cd /repo && git status", value)
            assert r.returncode == 2, f"CLAUDEBOOST_BASH_GUARD={value!r} should keep the guard on"
