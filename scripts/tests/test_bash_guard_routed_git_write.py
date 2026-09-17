"""
Tests for check_routed_git_write in scripts/bash-guard.py.

Claude Code matches permission rules against the raw command string by prefix,
so Bash(git push **) catches `git push origin main` but not `xargs git push`,
`GIT_SSH_COMMAND=x git push`, or `git add . && git push`. Each of those reaches
the same remote with no prompt. No glob pattern can close it, because the
bypass lives in shell semantics the matcher never parses.

The check finds a git or gh write anywhere in the command and blocks it unless
the command starts with it, since that is the only shape the permission engine
can see and prompt on.

BLOCK cases are the real bypasses. ALLOW cases are the two things that must
keep working: a direct write (so the ask rule fires, not this hook) and any
read only command or one that merely mentions a write inside a string.

Nothing here runs. Every command below is a STRING handed to the hook as JSON
on stdin; the subprocess argv is always [python, bash-guard.py] and never the
command under test. So a case reading `git push --force origin main` is parsed
and classified, never executed, and no remote, repo, or process is touched.
Keep it that way: a test for a guard against dangerous commands must never be
able to run one.

Paths in the cases are deliberately generic (/some/repo, /usr/bin/git,
C:\\tools\\...). They are regex input, not locations on disk, and none of them
is read or written. Do not put a real checkout path here; it makes the file
machine specific for no gain.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from helpers import hook_env, run_hook, pretooluse, SCRIPTS_DIR


def _bash(command: str) -> dict:
    return pretooluse("Bash", {"command": command})


def allow(command: str):
    result = run_hook("bash-guard.py", _bash(command))
    assert result.returncode == 0, (
        f"Expected ALLOW but got BLOCK.\nCommand: {command!r}\n"
        f"stderr: {result.stderr.decode()}"
    )


def _stderr_of(result) -> str:
    return result.stderr.decode()


# A git write is now refused by the verb gate, so a test whose subject is
# something else (message prose, a cd compound, a quoted mention) can no longer
# expect returncode 0 when its vehicle is `git commit -m "..."`. The bite is
# unchanged: the refusal must come from the verb gate and not from the check
# under test, so a curl or backslash false positive still fails the assertion.
_VERB_GATE_REFUSAL = "read-only allowlist"


def allow_except_git_write(command: str):
    result = run_hook("bash-guard.py", _bash(command))
    if result.returncode == 0:
        return
    stderr = _stderr_of(result)
    assert _VERB_GATE_REFUSAL in stderr, (
        f"Expected ALLOW, or a refusal from the git verb gate and nothing else.\n"
        f"Command: {command!r}\nstderr: {stderr!r}"
    )


def block(command: str):
    result = run_hook("bash-guard.py", _bash(command))
    assert result.returncode == 2, (
        f"Expected BLOCK but got ALLOW.\nCommand: {command!r}"
    )
    return result.stderr.decode()


# ===========================================================================
# BLOCK: a write routed through something the permission prefix cannot see
# ===========================================================================

class TestRoutedWritesAreBlocked:
    @pytest.mark.parametrize("command", [
        'echo "origin main" | xargs git push',
        'xargs -I{} git push {}',
        'GIT_SSH_COMMAND=x git push origin main',
        'GIT_DIR=/x git push',
        'git add . && git push origin main',
        'git add . ; git push',
        'for r in a b; do git push $r main; done',
    ])
    def test_routed_git_push(self, command):
        block(command)

    @pytest.mark.parametrize("command", [
        'echo hi && gh pr merge 12',
        'true; gh repo delete foo/bar',
        'xargs gh issue comment',
        'cat f | gh pr review --approve',
    ])
    def test_routed_gh_write(self, command):
        block(command)

    def test_routed_gh_api(self):
        """gh api is denied outright in settings, so any route to it is a bypass."""
        block('FOO=1 gh api -X POST /repos/x/y/issues')

    def test_message_names_the_route_and_says_what_to_do(self):
        stderr = block('echo "origin main" | xargs git push')
        assert "git push" in stderr
        assert "as its own Bash call" in stderr

    @pytest.mark.parametrize("command", [
        'eval "git push origin main"',
        'bash -c "git push origin main"',
        'sh -c "git push origin main"',
    ])
    def test_shell_wrapper_with_quoted_write_is_still_blocked(self, command):
        """_strip_quoted empties a double-quoted string before the write regex
        runs, so a write wrapped in eval/bash -c/sh -c and double-quoted
        vanishes entirely from the scan. The command still reaches the remote
        when the shell actually runs it, and no ask rule matches an "eval " or
        "bash -c " prefix in settings.json, so this must not silently pass."""
        block(command)

    @pytest.mark.parametrize("command", [
        'git --git-dir=/x push origin main',
        'git --work-tree=/x push origin main',
    ])
    def test_global_flag_between_git_and_write_verb_is_recognized_as_routed(self, command):
        """settings.json has no ask/deny/allow rule matching a literal
        "git --git-dir=... push" or "git --work-tree=... push" prefix (only
        "git push" and "git -C ** push" are covered), so treating this as a
        position-0 direct write that the permission engine will prompt on is
        false: nothing in settings.json prompts on it, and the bare "Bash"
        catch-all that used to cover it is gone."""
        block(command)


# ===========================================================================
# ALLOW: a direct write must reach the ask rule, not this hook
# ===========================================================================

class TestDirectWritesAreRefusedByTheVerbGate:
    @pytest.mark.parametrize("command", [
        'git push origin main',
        'git push --force origin main',
        'git -C "/repo/with a space" push origin main',
        'gh pr create --title x',
        'gh api /repos/x/y',
    ])
    def test_direct_write_is_refused(self, command):
        """These used to pass through so the permission prompt could fire.

        They no longer do. A prompt is an approval the session can give itself,
        and the requirement is that a git or gh write cannot run at all and is
        handed to the human instead. check_routed_git_write still leaves a
        direct write alone; the verb gate behind it is what refuses this."""
        block(command)


# ===========================================================================
# ALLOW: read only commands and mentions inside strings
# ===========================================================================

class TestNoFalsePositives:
    @pytest.mark.parametrize("command", [
        'git status',
        'git diff --stat',
        'git -C /some/repo log --oneline -5',
        'gh pr view 12',
        'gh pr list',
        'gh repo view',
        'gh release download v1',
    ])
    def test_read_only_commands(self, command):
        allow(command)

    @pytest.mark.parametrize("command", [
        'git commit -m "then git push to origin later"',
        'echo "remember to git push"',
        'git log --grep="gh pr merge"',
    ])
    def test_a_write_named_inside_a_quoted_string_is_not_a_write(self, command):
        """_strip_quoted removes the quoted body first, so a commit message or
        a grep pattern that mentions a push does not trip the check.

        The first case is a real `git commit`, which the verb gate refuses on
        its own account. What must not happen is a refusal naming the push."""
        allow_except_git_write(command)

    def test_grep_for_a_push_in_source(self):
        allow('grep -rn "git push" scripts/')

    @pytest.mark.parametrize("command", [
        # A path is only a command when it is in command position. Named as an
        # argument to something else it is just a path.
        'echo /usr/bin/git push',
        'echo "/usr/bin/git push"',
        'ls /usr/bin/git',
        'which git',
        'file /usr/bin/git',
    ])
    def test_a_path_to_git_named_as_an_argument_is_not_a_write(self, command):
        """Walking back over a path must not turn every mention of one into a
        command. After the path is stripped from `echo /usr/bin/git push` what
        remains is `echo `, which is not a command boundary."""
        allow(command)

    @pytest.mark.parametrize("command", [
        # The words are an argument to something else, never the command run.
        'echo git push',
        'echo gh pr merge',
    ])
    def test_a_write_named_as_a_bare_argument_is_not_a_write(self, command):
        """`echo git push` prints two words. Only a write in command position
        (start of the command, or after a separator, or handed to a runner like
        xargs) is actually running."""
        allow(command)

    @pytest.mark.parametrize("command", [
        # A heredoc body bound for a non shell is that program's input, not
        # shell to execute. Writing a script or a note that mentions a push
        # must not read as running one.
        "python - <<'EOF'\nprint('git push')\nEOF",
        "python - <<'EOF'\ncases = ['bash -c \"git push\"']\nEOF",
        "python - <<'PYEOF'\ns = \"gh pr merge\"\nPYEOF",
        # `cat > file <<EOF` is deliberately blocked by check_cat_heredoc, a
        # different guard, so this uses the form that guard leaves alone.
        # The write sits first on the body line on purpose: an earlier version
        # of this case opened with the word "run", which the command-position
        # check reads as making the write an argument, so the case passed
        # while the heredoc classifier below it was broken.
        "cat <<EOF 2>&1\ngh pr merge\nEOF",
    ])
    def test_a_heredoc_body_for_a_non_shell_is_data(self, command):
        """Found by running the guard against this very repo's own tooling: a
        heredoc writing a Python file that merely quotes these commands was
        blocked as though it ran them."""
        allow(command)

    def test_a_heredoc_with_a_trailing_redirect_is_still_data(self):
        """`<<tag` is one redirection operator, not the whole line.

        POSIX 2.7.4 puts the body after the next newline, so a second
        redirection is legal between the tag and that newline: the heredoc
        feeds cat's stdin while `> f.txt` governs its stdout. Requiring the
        newline immediately after the tag matched nothing here, and the body
        was then scanned as command text and refused.
        """
        allow("cat <<EOF > f.txt\ngh pr merge\nEOF")

    def test_a_heredoc_piped_to_a_reader_is_still_data(self):
        """The same operator line, reached through a trailing pipe instead of
        a trailing redirect. `cat <<EOF | grep x` feeds cat's stdin while grep
        reads cat's stdout; nothing about the pipe changes what the body is."""
        allow("cat <<EOF | grep x\ngh pr merge\nEOF")

    def test_a_heredoc_line_that_looks_like_a_command_is_still_data(self):
        """Isolates the heredoc blanking specifically.

        A newline counts as a command separator, so a bare `git push` on its
        own line inside the body sits in command position and every other
        layer would read it as a real command. Only recognising the body as
        data prevents this, which makes it the case that fails if the blanking
        is removed. Without it, writing a shell script through a heredoc is
        blocked.
        """
        allow("python - <<'EOF'\nx = 1\ngit push\nEOF")

    def test_a_quoted_argument_inside_a_shell_payload_is_still_data(self):
        """Isolates the inner quote stripping specifically.

        The `;` inside the commit message puts the following `git push` in
        command position, so the position rule alone would block it. Only
        stripping the payload's own quotes first, exactly as the top level
        command is stripped, keeps this honest commit working.
        """
        allow_except_git_write(
            """bash -c "git commit -m 'fix; git push now'" """.strip())

    @pytest.mark.parametrize("command", [
        # An unrelated executor earlier in the command (nothing to do with git)
        # plus a write only ever mentioned inside quotes later on. The raw
        # second-pass scan no longer strips quotes once an executor is present
        # anywhere in the command, so the quoted mention gets read as a real
        # write even though the executor's own argument never touches git.
        'bash -c "ls -la" ; git commit -m "remember to git push later"',
        'eval "echo hi"; git commit -m "note: git push is dangerous, be careful"',
        'sh -c "echo test" && git log --grep="git push"',
        'bash -c "npm test" ; git commit -am "fix: document that gh pr merge needs review"',
    ])
    def test_unrelated_executor_plus_quoted_mention_is_not_a_routed_write(self, command):
        """The actual git action in each of these is `git commit` or a read
        (`git log`), never a push or a gh write. The executor is real but has
        nothing to do with git. A refusal naming the quoted push is a false
        positive: nothing in the command reaches a remote outside a permission
        rule's view."""
        allow_except_git_write(command)

    @pytest.mark.parametrize("command", [
        # _executor_payloads returns the executor's own argument RAW, quotes
        # intact, and _GIT_WRITE_RE / _GH_WRITE_RE are searched against that
        # raw text with no inner-quote stripping. So a write phrase sitting
        # inside a nested quoted literal *within* the executor's own argument
        # (a grep pattern, a --grep value, an echoed string) reads as a real
        # command the same way the top-level scan used to misread a commit
        # message before _strip_quoted existed.
        'bash -c "grep \'git push\' file"',
        'bash -c "echo git push"',
        'bash -c "git log --grep=\'gh pr merge\'"',
    ])
    def test_write_phrase_nested_inside_the_executor_payload_is_not_a_write(self, command):
        """None of these reach a remote: the first two never call git or gh
        at all (grep/echo just handle the words as data), the third is a
        read-only `git log --grep`. The executor's argument is real, but the
        phrase inside it is quoted data, not a command being run — same
        distinction _strip_quoted already draws at the top level."""
        allow(command)

    def test_quoted_write_split_across_adjacent_quoted_segments_is_still_a_write(self):
        """Adjacent quoted segments with no separator between them
        concatenate into one shell word: `bash -c "git ""push"` really runs
        `bash -c "git push"` (verified: `bash -c "echo pre""fix"` prints
        `prefix`). _executor_payloads takes only the first quoted span
        (`rest.find(quote, 1)`), so the payload extracted is `git ` with the
        `push` verb silently dropped, and the write regex never sees it."""
        block('bash -c "git ""push"')

    @pytest.mark.parametrize("command", [
        # bash -o pipefail -c "..." is an ordinary, common invocation
        # (verified: `bash -o pipefail -c "echo works"` runs normally).
        # _EXECUTOR_HEAD_RE's flag-absorbing group `(?:\s+--?[\w-]+)*` only
        # eats dash-prefixed tokens, so it stops at "pipefail" (no leading
        # dash, it's -o's value) and the required `\s+-[a-zA-Z]*c\b` right
        # after never matches because "pipefail" sits in between.
        'bash -o pipefail -c "git push origin main"',
        'bash -eo pipefail -c "git push origin main"',
        'bash -e -o pipefail -c "git push origin main"',
    ])
    def test_bash_o_pipefail_c_is_still_a_routed_write(self, command):
        """A write inside `bash -o pipefail -c "..."` still reaches the
        remote; no permission rule's prefix matches it either."""
        block(command)


# ===========================================================================
# BLOCK: executor forms _SHELL_EXECUTOR_RE currently misses
# ===========================================================================

class TestExecutorFormsStillUncovered:
    def test_bash_login_dash_c_is_still_a_routed_write(self):
        """_SHELL_EXECUTOR_RE requires `sh` directly followed by whitespace
        then `-[a-zA-Z]*c`, so inserting any flag between the shell name and
        -c (a completely ordinary way to invoke bash) breaks the match. The
        write still reaches the remote; no permission rule's prefix matches
        `bash --login -c "..."`."""
        block('bash --login -c "git push origin main"')

    def test_bash_here_string_is_still_a_routed_write(self):
        """`bash <<< "cmd"` runs cmd as a real shell command with no -c flag
        at all, so _SHELL_EXECUTOR_RE never matches it and the quoted write
        is stripped by _strip_quoted before the first scan runs, same failure
        mode the fix was written to close for the -c forms."""
        block('bash <<< "git push origin main"')

    @pytest.mark.parametrize("command", [
        # Windows binaries. settings.json asks on the literal prefix
        # "git push", which "git.exe push" does not start with, so nothing
        # downstream prompts on these.
        'git.exe push origin main | cat',
        'echo x && git.exe push',
        'echo y && gh.exe pr merge 1',
        r'C:\tools\git\bin\git.exe push origin main',
    ])
    def test_a_windows_exe_spelling_is_still_routed(self, command):
        block(command)

    @pytest.mark.parametrize("command", [
        # A case branch runs its body, and `)` closes the pattern, so the text
        # before the write is a command boundary like any separator.
        'case "$1" in prod) git push origin main ;; esac',
        'case $x in a) gh pr merge 1 ;; esac',
    ])
    def test_a_write_inside_a_case_branch_is_still_routed(self, command):
        block(command)

    def test_stacked_flags_before_dash_c_do_not_escape(self):
        """The flag run is bounded, so the bound has to be generous enough that
        stacking ordinary flags is not a way out."""
        block('bash -e -u -x -o pipefail -o errexit -o nounset -c "git push"')

    @pytest.mark.parametrize("command", [
        'bash -o pipefail -c "git push origin main"',
        'bash -eo pipefail -c "git push origin main"',
        'bash -e -o pipefail -c "git push origin main"',
    ])
    def test_a_flag_with_a_bare_value_does_not_hide_the_executor(self, command):
        """Absorbing only dash prefixed tokens between the shell name and -c
        was not enough. -o takes a bare value, and that value ended the run
        before it reached the -c. `bash -o pipefail -c` is an ordinary idiom
        anywhere a script cares about pipeline exit codes, not an evasion."""
        block(command)

    def test_adjacent_quoted_segments_are_one_argument(self):
        """The shell concatenates adjacent quoted segments, so
        `bash -c "git ""push"` runs `git push` and really does push. Reading
        only as far as the first closing quote saw `git ` and let it through."""
        block('bash -c "git ""push"')

    def test_an_unbalanced_quote_cannot_hide_the_tail(self):
        """An unterminated argument is read to the end rather than dropped.
        Blocking here is deliberate: the alternative lets a stray quote be an
        escape hatch."""
        block('bash -c "git push')

    @pytest.mark.parametrize("command", [
        "bash <<'EOF'\ngit push origin main\nEOF",
        "sh <<EOF\ngit push\nEOF",
        "/bin/bash <<'EOF'\ngit push\nEOF",
        # The shell is named AFTER the tag, so reading only the text before
        # the << misses it. cat writes the body to stdout and bash runs it.
        "cat <<'EOF' | bash\ngit push\nEOF",
        "cat <<'EOF' | /bin/sh\ngit push\nEOF",
        # A pipe needs no whitespace around it, so splitting the operator line
        # on whitespace alone reads this as the single word "cat|bash".
        "cat <<'EOF'|bash\ngit push\nEOF",
        "cat|bash <<EOF\ngit push\nEOF",
        # Quotes are removed before the first field becomes the command name
        # (POSIX 2.6 then 2.9.1), so every one of these runs the body. Testing
        # the split word with its quotes still attached matches none of them.
        'cat <<EOF | "ba"sh\ngit push\nEOF',
        'cat <<EOF | "bash\ngit push\nEOF',
        # An assignment or a hand-off runner may precede the command name, so
        # the shell is still what reads the body.
        'cat <<EOF | VAR=1 "bash"\ngit push\nEOF',
        'cat <<EOF | xargs "bash"\ngit push\nEOF',
    ])
    def test_a_heredoc_fed_to_a_shell_is_executed(self, command):
        """A shell really does run its heredoc body, so a write in there is
        routed exactly like one behind -c."""
        block(command)

    def test_a_quoted_shell_name_counts_only_at_the_command_name(self):
        """Pins the quoting asymmetry, which is the whole reason the dequoted
        check is confined to a command name rather than applied line-wide.

        Both lines contain the characters `"bash"`. In the first it is grep's
        argument and nothing executes the body, so blanking it is correct. In
        the second it is the command name and the body really is executed.
        Dequoting every word on the line collapses the pair and refuses
        ordinary `grep "bash"` work; dequoting none of it reopens the bypass.
        """
        allow('cat <<EOF | grep "bash"\ngit push\nEOF')
        block('cat <<EOF | "bash"\ngit push\nEOF')

    def test_only_the_shell_in_the_tail_decides_the_pipe_case(self):
        """Pins WHY `cat <<EOF | bash` is refused, not just that it is.

        Both commands here are the same shape and differ in one word. Before
        the operator line was read past the tag, neither was recognized as a
        heredoc at all, so both bodies were scanned raw and both blocked --
        the refusal below was right by accident and the allow above it was a
        false positive. Recognizing the heredoc is what splits them: the body
        is data when a reader follows the pipe and source when a shell does.
        Any change that stops reading the tail collapses the pair again.
        """
        allow("cat <<EOF | grep x\ngit push\nEOF")
        block("cat <<EOF | bash\ngit push\nEOF")

    def test_a_herestring_is_not_a_heredoc_body(self):
        """`<<<` is a herestring: the word after it IS the input, and there is
        no body to blank. Reading it as a heredoc opener lets the rest of the
        command be blanked as though it were data."""
        block("cat <<<EOF | grep x\ngit push\nEOF")

    @pytest.mark.parametrize("command", [
        # Flags between the shell name and -c.
        'bash -lc "git push origin main"',
        'sh -lc "git push origin main"',
        'bash --login <<< "git push"',
        # Other shells.
        'zsh -c "git push"',
        'ksh -c "git push"',
        # Windows shells.
        'powershell -Command "git push origin main"',
        'pwsh -c "git push"',
        'cmd.exe /c "git push origin main"',
        # Interpreters that shell out. Same class: the argument is executed.
        'python -c "os.system(\'git push\')"',
        'python3 -c "os.system(\'git push\')"',
        'perl -e "system(\'git push\')"',
        'ruby -e "system(\'git push\')"',
        'node -e "require(\'child_process\').exec(\'git push\')"',
        # Single quoted argument, and an unquoted one.
        "eval 'git push origin main'",
        'eval git push',
        # gh writes reached the same way.
        'bash -c "gh pr merge 12"',
        'bash -c "gh api -X POST /repos/x/y"',
        # Nested and stacked routing.
        'bash -c "cd /x && git push"',
        'bash -c "eval \'git push\'"',
        'xargs bash -c "git push"',
    ])
    def test_every_executor_form_reaching_a_write_is_blocked(self, command):
        """Each of these actually executes its argument, so a write inside it
        reaches the remote while the permission engine sees only the wrapper's
        prefix. One flag or one syntax form should not be the difference
        between blocked and silent."""
        block(command)

    @pytest.mark.parametrize("command", [
        'echo "bash -c git push"',
        'git commit -m "use bash -c to push"',
        'grep -rn "bash -c" scripts/',
    ])
    def test_an_executor_named_inside_a_string_is_not_an_executor(self, command):
        """The executor head has to sit outside quotes to be running anything.
        Quoted, it is just text being echoed, committed, or searched for."""
        allow_except_git_write(command)

    @pytest.mark.parametrize("command", [
        'bash -c "ls -la"',
        'bash -c "pytest" ; git diff --stat',
        'bash -c "ls" && git status',
        'python -c "print(1)"',
    ])
    def test_an_executor_running_something_harmless_is_left_alone(self, command):
        """Only the executor's own argument is scanned, and only for a git or
        gh write. An executor by itself is not suspicious."""
        allow(command)


# ===========================================================================
# BLOCK: a git/gh binary reached through a path is still the command running
# ===========================================================================

class TestPathQualifiedBinaryIsStillCommandPosition:
    @pytest.mark.parametrize("command", [
        '/usr/bin/git push origin main',
        './git push origin main',
        'bin/git push origin main',
        '/usr/local/bin/git push',
        '/usr/bin/gh pr merge 12',
    ])
    def test_path_qualified_write_is_still_routed(self, command):
        """`\\bgit\\b` matches the "git" tail of a path like "/usr/bin/git", so
        _GIT_WRITE_RE finds the write at a non-zero offset. _in_command_position
        then looks at the text immediately before that offset ("/usr/bin/"),
        which is neither "^", a separator, nor a known router, so the write is
        wrongly classified as "just an argument to something else" the same
        way `echo git push` is. It is not: `/usr/bin/git push origin main`
        genuinely runs git and reaches the remote, exactly like a bare
        `git push`, and settings.json's ask rule only matches a command that
        literally starts with "git push" — this exact prefix does not, so
        nothing downstream prompts on it either."""
        block(command)

    @pytest.mark.parametrize("command", [
        'xargs /usr/bin/git push',
        'sudo /usr/bin/git push',
        'bash -c "/usr/bin/git push origin main"',
    ])
    def test_path_qualified_write_stays_routed_behind_a_real_router(self, command):
        """Even with a genuine router immediately in front of it, the bug is
        the same: the match offset lands mid-token on the "git" tail of the
        path, not right after the router, so _CMD_START_RE's lookbehind still
        sees "/usr/bin/" instead of the router and misses it."""
        block(command)

    def test_write_inside_a_case_branch_is_still_routed(self):
        """A case arm is a real command position — `case "$1" in prod) git
        push ;; esac` genuinely runs the push when $1 is "prod". The `)` that
        ends a case pattern is not in _CMD_START_RE's separator set, so this
        reads as an argument mention and passes through unblocked."""
        block('case "$1" in prod) git push origin main ;; esac')


# ===========================================================================
# BLOCK: shell word concatenation across an *unquoted* infix, not just ""
# ===========================================================================

class TestUnquotedInfixBetweenQuotedSegmentsStillConcatenates:
    @pytest.mark.parametrize("command", [
        # Verified against a real shell first: `bash -c 'echo p"u"sh test'`
        # and `bash -c "echo p"u"sh test"` both print "push test", because
        # adjacent quoted/unquoted segments with no separating whitespace are
        # ONE shell word regardless of which segments are quoted. This round's
        # fix only concatenates when the segments are directly quote-adjacent
        # ("..."\"...\""); the moment an unquoted character sits between two
        # quoted spans, _read_executed_argument's while loop condition
        # `rest[i] in ("\"", "'")` is false and it stops, silently dropping
        # everything after that point.
        'bash -c "git p"u"sh origin main"',
        'bash -c "git "push" origin main"',
        'bash -c "gi"t" push origin main"',
    ])
    def test_write_split_by_an_unquoted_character_is_still_one_argument(self, command):
        block(command)


# ===========================================================================
# Robustness: the check must not hang on an ordinary long command
# ===========================================================================

class TestNoCatastrophicBacktrackingOnLongInput:
    @pytest.mark.parametrize("length", [500, 1000, 2000])
    def test_a_long_plain_command_with_no_heredoc_completes_quickly(self, length):
        """`echo <N a's>` has no "<<" anywhere in it, so _HEREDOC_RE should
        fail its match fast. Instead `(?P<recv>\\S+)?[^\\n<]*` are two greedy
        quantifiers over overlapping character classes (both match a plain
        "a"), so on a failing search the engine tries every way to split the
        run between them at every starting offset -- 500 chars: ~0.1s, 1000:
        ~0.85s, 2000: ~7s (measured directly against _HEREDOC_RE.finditer in
        isolation, confirming the heredoc regex and not some other part of
        the check). This runs unconditionally on every Bash call that reaches
        check_routed_git_write, which is every call now that it is in the
        default check list, so an ordinary multi-KB echo, commit message, or
        pasted blob hangs the hook rather than a crafted adversarial string.
        A hard 5s subprocess timeout proves the hang rather than just
        asserting a wall clock bound, since a slow CI box could flake on a
        soft bound but a genuine hang always trips a fixed timeout.
        """
        command = "echo " + "a" * length
        script = SCRIPTS_DIR / "bash-guard.py"
        try:
            subprocess.run(
                [sys.executable, str(script)],
                input=json.dumps(pretooluse("Bash", {"command": command})).encode(),
                capture_output=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"bash-guard.py hung for over 5s on an {length}-char plain "
                "echo with no heredoc syntax at all -- catastrophic "
                "backtracking in _HEREDOC_RE, not an adversarial input."
            )

    def test_a_long_word_run_beside_a_bare_operator_completes_quickly(self):
        """The same defect as above, reached through the delimiter instead.

        `echo <N a's> << <N b's>` contains a "<<", so the cheap reject cannot
        help, and the b-run sits astride the tag and the trailing content.
        `\\w*` and `[^\\n]*` both match a "b", so with no boundary between them
        the engine tries every way to split that one run and rescans the tail
        each time. End to end through the hook, with and without the `\\b`
        after the tag: 2000 chars 199ms / 439ms, 8000 406ms / 1.2s, 16000
        295ms / 3.9s, 24000 251ms / 6.8s -- flat against quadratic.

        One length rather than a sweep, and a large one, because a shorter
        input does not separate the two: at 2000 the broken form still answers
        in under half a second, so a case at that size passes either way and
        pins nothing. 32000 puts the broken form at 14.5s against a 5s
        timeout, while the correct one stays near 400ms.
        """
        length = 32000
        command = "echo " + "a" * length + " << " + "b" * length
        script = SCRIPTS_DIR / "bash-guard.py"
        try:
            subprocess.run(
                [sys.executable, str(script)],
                input=json.dumps(pretooluse("Bash", {"command": command})).encode(),
                capture_output=True,
                env=hook_env(),
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"bash-guard.py hung for over 5s on a {length}-char word run "
                "beside a bare '<<' -- the tag and the trailing content are "
                "backtracking against each other in _HEREDOC_RE."
            )

    def test_many_quoted_shell_names_on_an_operator_line_stay_linear(self):
        """The quoted-name check must not judge each candidate against the
        text to its left.

        Every `"sh"` here dequotes to a real shell name, and none is a command
        name, so a check that anchors on the text before each one copies a
        growing prefix per candidate. Measured through the hook: 8000
        candidates on a 40KB line took 4299ms that way against 96ms
        segment-locally, and 32000 took 434ms segment-locally while the
        prefix-copying form was already past the timeout at 16000.
        """
        n = 32000
        command = "cat <<EOF | grep " + '"sh" ' * n + "\ngit push\nEOF"
        script = SCRIPTS_DIR / "bash-guard.py"
        try:
            subprocess.run(
                [sys.executable, str(script)],
                input=json.dumps(pretooluse("Bash", {"command": command})).encode(),
                capture_output=True,
                env=hook_env(),
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"bash-guard.py hung for over 5s on {n} quoted shell names on "
                "one operator line -- the command-name check is quadratic in "
                "the number of candidates."
            )
