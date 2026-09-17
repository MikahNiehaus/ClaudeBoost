"""
The security boundary in scripts/bash-guard.py: the verb gate, the guard's own
files, .env, shell routing, and the fail safe behaviour.

Everything here is a string handed to the hook as JSON on stdin. The subprocess
argv is always [python, bash-guard.py] and never the command under test, so a
case reading `git commit -am x` is parsed and classified, never run. No repo,
remote, file or process is touched by this file. Keep it that way.

Paths are built from the hook's own location rather than written as literals,
so the file works on a machine where this project lives somewhere else.
"""
from __future__ import annotations

import importlib.util
import time

import pytest

from helpers import pretooluse, run_hook, SCRIPTS_DIR

PROJECT = SCRIPTS_DIR.parent
GUARD = (SCRIPTS_DIR / "bash-guard.py").as_posix()
GUARD_TEST = (SCRIPTS_DIR / "tests" / "test_bash_guard.py").as_posix()
RESEARCH_GATE = (PROJECT / "clean-rag" / "hooks" / "research-gate.py").as_posix()
SETTINGS = (PROJECT / ".claude" / "settings.json").as_posix()
ENV_FILE = (PROJECT / "clean-rag" / ".env").as_posix()


def _bash(command: str) -> dict:
    return pretooluse("Bash", {"command": command})


def allow(command: str):
    result = run_hook("bash-guard.py", _bash(command))
    assert result.returncode == 0, (
        f"Expected ALLOW but got BLOCK.\nCommand: {command!r}\n"
        f"stderr: {result.stderr.decode()}"
    )


def block(command: str) -> str:
    result = run_hook("bash-guard.py", _bash(command))
    assert result.returncode == 2, (
        f"Expected BLOCK but got ALLOW.\nCommand: {command!r}"
    )
    return result.stderr.decode()


@pytest.fixture(scope="module")
def guard():
    """The hook imported as a module, for the checks that are easier to drive
    in process than through a subprocess."""
    spec = importlib.util.spec_from_file_location("bash_guard_under_test", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ===========================================================================
# A command that runs another command is the command that runs.
#
# Every case here resolved to ALLOW before the parsing layer existed, because
# permission rules match the raw command by prefix and `Bash(find **)`,
# `Bash(xargs **)`, `Bash(awk **)` and `Bash(sed **)` are unscoped: the engine
# never sees the inner command at all.
# ===========================================================================

class TestWrapperRouting:
    @pytest.mark.parametrize("command", [
        r"find . -maxdepth 0 -exec git commit -am x \;",
        r"find . -maxdepth 0 -execdir git commit -am x \;",
        "timeout 5 git commit -am x",
        "nohup git commit -am x",
        "env git commit -am x",
        "env GIT_SSH_COMMAND=x git push origin main",
        "watch -n1 git commit -am x",
        "nice -n 10 git push",
        "stdbuf -oL git push",
        "setsid git push",
        "start git commit -am x",
        "echo x | xargs git commit -am",
        "( git commit -am x )",
        "echo $(git commit -am x)",
        "echo `git commit -am x`",
        "/usr/bin/git commit -am x",
    ])
    def test_a_write_behind_a_wrapper_is_blocked(self, command):
        block(command)

    @pytest.mark.parametrize("command", [
        "echo 'git commit -am x' | xargs -I{} bash -c '{}'",
        "echo 'git push' | sh",
        "echo 'git push' | bash",
        "cat script.sh | bash",
    ])
    def test_piping_into_a_shell_is_blocked(self, command):
        """What runs is text produced at runtime, so no check that reads the
        command can see it. The refusal has to be the shape, not the content."""
        stderr = block(command)
        assert "pipes into" in stderr or "read-only allowlist" in stderr

    @pytest.mark.parametrize("command", [
        'awk \'BEGIN{system("git commit -am x")}\'',
        'awk \'BEGIN{print "x" | "git commit -am x"}\'',
    ])
    def test_awk_reaching_a_shell_is_blocked(self, command):
        assert "awk" in block(command)

    @pytest.mark.parametrize("command", [
        "sed '1e git commit -am x' file.txt",
        "sed 's/.*/git commit -am x/e' file.txt",
        "sed -e '1e git commit -am x' file.txt",
    ])
    def test_sed_executing_its_argument_is_blocked(self, command):
        assert "sed" in block(command)


# ===========================================================================
# An argument feeder supplies the verb the gate wants to read.
#
# POSIX says xargs "shall construct a command line consisting of the utility
# and argument operands specified followed by as many arguments read in
# sequence from standard input as fit". So `xargs git` really runs
# `git <whatever stdin holds>`, and the verb that decides read from write is
# in data the guard never sees. Reading the words after `git` in the static
# text finds nothing there and passed the command.
# ===========================================================================

class TestArgumentFeeders:
    @pytest.mark.parametrize("command", [
        'printf "%s\\n" push origin main | xargs git',
        "xargs -a args.txt git",
        "cat args | xargs -n3 git",
        "cat args | xargs --arg-file=args.txt git",
        "cat list | xargs -0 git",
        "echo push | xargs gh",
        "cat f | xargs gh pr",
        "parallel git push origin main ::: 1",
        "parallel ::: 'git push origin main'",
        'parallel ::: "gh pr merge 1"',
        "parallel -j2 git push ::: origin",
    ])
    def test_a_fed_vcs_binary_is_blocked(self, command):
        block(command)

    @pytest.mark.parametrize("command", [
        "cat f | xargs python",
        "cat f | xargs bash",
        "cat f | xargs sh",
        "xargs -a args.txt bash",
        "xargs -a args.txt python",
    ])
    def test_a_fed_interpreter_is_blocked(self, command):
        """An interpreter whose script name arrives from stdin runs code the
        guard cannot read, and no permission rule can match the real argv
        either, since those match the raw command by prefix. That is the same
        reason a wrapped `git fetch` is refused rather than prompted."""
        block(command)

    def test_parallel_runs_its_payload_as_a_shell_command(self):
        """GNU parallel's own design document describes it running
        `$SHELL -c $COMMAND`, so the text after ::: is judged as shell source
        rather than as an opaque argument. A harmless payload stays harmless,
        and a wrapper nested inside the payload is still descended into."""
        allow("""parallel ::: 'python -c "import os"'""")
        allow("parallel ::: 'git status'")
        allow("parallel ::: 'wc -l *.py'")
        block("""parallel ::: "bash -c 'git push'" """.strip())
        block("""parallel ::: "eval 'git commit -am x'" """.strip())

    @pytest.mark.parametrize("command", [
        "git ls-files -z | xargs -0 wc -l",
        "xargs -a files.txt grep -l TODO",
        "echo hello | xargs echo",
        "find . -name '*.py' | xargs grep -n TODO",
        "git ls-files | xargs wc -l",
    ])
    def test_feeding_an_ordinary_tool_still_works(self, command):
        """The rule is about which binary is being fed, not about the feeder.
        xargs into wc, grep or echo is ordinary read-only work and the
        transcripts are full of it."""
        allow(command)

    def test_a_bare_git_that_is_not_being_fed_still_works(self):
        """`git` on its own prints usage and writes nothing. Only a feeder
        turns a missing verb into an unknown one."""
        allow("git")
        allow("git --version")

    @pytest.mark.parametrize("command", [
        "xargs -a args.txt git config",
        "cat keys | xargs git config user.email",
        "cat names | xargs git branch",
        "cat names | xargs git tag",
        "cat urls | xargs git remote",
    ])
    def test_a_verb_that_writes_only_with_an_operand_is_blocked_when_fed(self, command):
        """These verbs read with no operand and write with one, so the feeder
        decides which they are. `git config user.email` reads the key and
        `git config user.email x@y` sets it; `git branch` lists and
        `git branch <name>` creates. The guard stands in two unknown arguments
        rather than one, because one cannot tell that pair apart."""
        block(command)

    @pytest.mark.parametrize("command", [
        "git ls-files | xargs git log --oneline --",
        "cat paths | xargs git diff --",
    ])
    def test_appending_paths_to_a_read_verb_is_still_a_read(self, command):
        """The counterpart: a verb that reads whatever operands it is given
        stays a read however many the feeder appends."""
        allow(command)


# ===========================================================================
# git: a positive allowlist of read verbs.
# ===========================================================================

class TestGitVerbGate:
    @pytest.mark.parametrize("command", [
        # The four the 820-entry deny list still missed.
        "git commit-graph write",
        "git multi-pack-index write",
        "git maintenance run",
        "git credential approve",
        "git credential reject",
        # Plumbing that stages or writes objects.
        "git update-index --add x.py",
        "git hash-object -w x.py",
        "git write-tree",
        "git symbolic-ref HEAD refs/heads/x",
        # Refs created by a bare positional, which no literal rule can tell
        # apart from the listing form.
        "git branch newbranch",
        "git tag v1.0",
        "git branch -D old",
        "git branch -f main HEAD~1",
        # Config written with no scope flag at all.
        'git config user.email "x@y.z"',
        "git config --global core.editor vim",
        # Mixed verbs, write side.
        "git stash",
        "git stash push -m wip",
        "git submodule foreach 'echo x'",
        "git remote add origin https://example.com/x.git",
        "git reflog expire --all",
        "git worktree add ../wt",
        # A user alias resolves to anything, so an unknown verb is not safe.
        "git co main",
        "git please-just-do-it",
    ])
    def test_a_git_write_is_blocked(self, command):
        block(command)

    @pytest.mark.parametrize("command", [
        "Git commit -am x",
        "GIT COMMIT -am x",
        "git.exe commit -am x",
        "Git.EXE push origin main",
    ])
    def test_spelling_does_not_change_the_verdict(self, command):
        """The permission engine matches literal text, so `Git commit` and
        `git.exe commit` fell to a prompt rather than a deny. The shell does
        not care about either spelling and neither does this gate."""
        block(command)

    @pytest.mark.parametrize("command", [
        "git -c pager.log=evil log",
        "git -c pager.diff=evil diff",
        "git -c sequence.editor=evil rebase -i HEAD~2",
        "git -c core.pager=evil log",
        "git -c core.editor=evil log",
        "git -c diff.external=evil diff --ext-diff",
        "git -c alias.x=!evil x",
        "git -calias.x=!evil x",
        "git -c credential.helper=evil fetch",
    ])
    def test_an_unlisted_config_key_is_blocked(self, command):
        """`git -c <key>=<value>` runs a program named in configuration.
        Verified on this machine: `git -c diff.external=<cmd> diff --ext-diff`
        and `git -c alias.x='!<cmd>' x` both executed the command. Enumerating
        the dangerous keys is the shape that already missed pager.<cmd> and
        sequence.editor, so the safe keys are listed instead."""
        assert "-c" in block(command)

    @pytest.mark.parametrize("command", [
        "git --git-dir=/other/.git log",
        "git --work-tree=/other log",
        "git --exec-path=/tmp/evil status",
        "git diff --output=/tmp/x.diff",
        "git grep -O 'sh -c evil' pattern",
    ])
    def test_a_flag_that_redirects_or_writes_is_blocked(self, command):
        block(command)

    @pytest.mark.parametrize("command", [
        "git status",
        "git status --porcelain",
        "git log --oneline -5",
        'git log --grep="git push"',
        "git diff HEAD~1",
        "git diff --stat",
        "git show HEAD",
        "git describe --tags",
        "git blame x.py",
        "git grep -n pattern",
        "git rev-parse HEAD",
        "git rev-list --count HEAD",
        "git ls-files",
        "git ls-tree -r HEAD",
        "git ls-remote --heads origin",
        "git merge-base main HEAD",
        "git cat-file -p HEAD",
        "git for-each-ref --format='%(refname)'",
        "git check-ignore -v x.py",
        "git count-objects -v",
        "git shortlog -sn",
        "git branch",
        "git branch -a",
        "git branch -vv",
        "git branch --show-current",
        "git branch --list 'feature/*'",
        "git branch --contains HEAD",
        "git tag",
        "git tag -l 'v1.*'",
        "git tag --list",
        "git stash list",
        "git stash show",
        "git remote",
        "git remote -v",
        "git remote show origin",
        "git remote get-url origin",
        "git reflog",
        "git reflog show HEAD",
        "git submodule status",
        "git worktree list",
        "git notes list",
        "git bisect log",
        "git config --get user.email",
        "git config --list",
        "git config user.email",
        "git version",
        "git status && git log --oneline -3",
        "git log --oneline | head -5",
        'git -C "/some/repo" log -1',
        "git -c color.ui=always log",
    ])
    def test_read_only_git_still_runs_with_no_prompt(self, command):
        """Requirement 6, as a test rather than an intention. Every verb here
        appears in this machine's own transcripts."""
        allow(command)

    def test_git_fetch_is_allowed_directly_and_refused_when_routed(self):
        """A recorded decision: fetch stays a prompt because it writes only
        remote-tracking refs and ran 47 times in the transcripts. Routing it is
        what removes the prompt, so routing it is what this refuses."""
        allow("git fetch")
        allow("git fetch --all --prune")
        block("xargs git fetch")
        block("timeout 30 git fetch")

    @pytest.mark.parametrize("command", [
        "git branch -a 2>/dev/null",
        "git branch --show-current 2>/dev/null",
        "git branch -r --sort=-committerdate 2>&1",
        "git remote -v 2>/dev/null",
        "git branch -a > out.txt",
        "git tag -l 2>/dev/null",
        "git fetch 2>/dev/null",
    ])
    def test_a_redirect_is_not_a_ref_name(self, command):
        """`git branch -a 2>/dev/null` splits to [git, branch, -a, 2, >,
        /dev/null] and the bare file descriptor read as a branch name, so the
        guard refused a listing as a ref creation. 23 of these spellings run in
        the transcripts. A redirect must also not read as a wrapper, or the
        same command loses its fetch prompt for a route nothing takes."""
        allow(command)

    def test_stripping_a_redirect_does_not_hide_a_real_ref_write(self):
        """The strip removes the operator and its target, never an operand."""
        block("git branch newthing")
        block("git branch newthing 2>/dev/null")
        block("git tag v1.0.0 2>/dev/null")


class TestGhVerbGate:
    @pytest.mark.parametrize("command", [
        "gh pr create --title x",
        "gh pr merge 1",
        "gh issue close 4",
        "gh release create v1",
        "gh repo fork",
        "gh secret set FOO -b bar",
        "gh variable set FOO -b bar",
        "gh auth login",
        "gh auth token",
        "gh api repos/x/y",
        "gh api -X POST repos/x/y/issues",
        # Verbs no denylist of gh write words had reached.
        "gh extension install someone/thing",
        "gh alias set co 'pr checkout'",
        "gh config set editor vim",
        "gh ssh-key add key.pub",
    ])
    def test_a_gh_write_is_blocked(self, command):
        block(command)

    @pytest.mark.parametrize("command", [
        "gh pr view 12",
        "gh pr list",
        "gh pr diff 12",
        "gh pr checks 12",
        "gh issue list",
        "gh repo view",
        "gh release list",
        "gh release download v1",
        "gh auth status",
        "gh --version",
        "gh search repos cli",
    ])
    def test_read_only_gh_still_runs(self, command):
        allow(command)


# ===========================================================================
# The guard's own files, and every .env.
#
# Edit and Write tool rules cover two tools. Bash is a third, and it reached
# all of these with no prompt at all.
# ===========================================================================

class TestSelfProtection:
    @pytest.mark.parametrize("template", [
        'cp payload.py "{path}"',
        'mv /tmp/payload.py "{path}"',
        'tee "{path}"',
        'echo evil > "{path}"',
        'echo evil >> "{path}"',
        'cat payload.py > "{path}"',
        'dd if=payload.py of="{path}"',
        'install payload.py "{path}"',
        'truncate -s 0 "{path}"',
        'chmod 777 "{path}"',
        'rm -f "{path}"',
        'sed -i s/a/b/ "{path}"',
    ])
    @pytest.mark.parametrize("path", [GUARD, GUARD_TEST, RESEARCH_GATE, SETTINGS])
    def test_a_write_to_a_control_file_is_blocked(self, template, path):
        block(template.format(path=path))

    def test_a_relative_path_to_the_guard_is_blocked(self):
        """A relative path has no root to check against the project, so it is
        refused rather than resolved against whatever the cwd happens to be."""
        block("cp payload.py scripts/bash-guard.py")
        block("echo x > ./scripts/tests/test_bash_guard.py")

    def test_the_write_then_run_chain_is_broken_at_the_write(self):
        """`cp x.py <project>/scripts/x.py` then `python <project>/scripts/x.py`
        is unprompted arbitrary execution, and the interpreter allow on that
        path is what makes the second half silent. The first half is the half
        that can be stopped."""
        block('cp /tmp/payload.py "%s/x.py"' % SCRIPTS_DIR.as_posix())

    def test_a_write_routed_through_a_shell_is_still_blocked(self):
        block('bash -c "echo evil > %s"' % GUARD)
        block('python -c "open(\'%s\', \'w\').write(1)"' % GUARD)

    def test_a_write_named_in_interpreter_source_is_blocked(self):
        block("""python -c "import os; os.system('git commit -am x')\"""")
        block("""perl -e "system('gh pr merge 1')\"""")

    def test_php_source_arrives_on_dash_r(self):
        """php was listed with the interpreters but only -c and -e were matched,
        so every php one liner was unscanned source. node keeps its own -r,
        which preloads a module and is an operand rather than a program."""
        block("""php -r "system('git push');\"""")
        block("""php -r "echo file_get_contents('.env');\"""")
        allow("node -r ts-node/register app.js")

    def test_a_read_verb_named_in_interpreter_source_is_not_blocked(self):
        """Shell word rules do not apply inside interpreter source, so a verb's
        arguments cannot be read there. A verb that reads with no arguments has
        to pass, or ordinary subprocess code stops working."""
        allow("""python -c "import subprocess; subprocess.run(['git','status'])\"""")
        allow("""python -c "import os; os.system('git branch')\"""")

    @pytest.mark.parametrize("command", [
        'cat "{env}"',
        'type "{env}"',
        'head -20 "{env}"',
        'tail "{env}"',
        'grep API "{env}"',
        'less "{env}"',
        'cat < "{env}"',
        'bash -c "cat {env}"',
        'xargs cat < "{env}"',
    ])
    def test_reading_an_env_file_through_bash_is_blocked(self, command):
        block(command.format(env=ENV_FILE))

    @pytest.mark.parametrize("command", [
        "cat .env",
        "cat .env.local",
        "cat .env.production",
        "cat ../other/.env",
    ])
    def test_every_env_spelling_is_covered(self, command):
        block(command)

    @pytest.mark.parametrize("command", [
        "git show HEAD:.env",
        'git show HEAD:".env"',
        "git show HEAD~3:.env",
        "git show HEAD:config/.env",
        "git show :.env",
        "git cat-file blob HEAD:.env",
        "git show abc1234:.env.production",
    ])
    def test_reading_an_env_file_out_of_a_git_object_is_blocked(self, command):
        """`git show <ref>:<path>` prints the file's real bytes from any commit
        that ever held it, which is the same secret by a different route. The
        path sits after a colon, so a word-level check never saw it."""
        block(command)

    @pytest.mark.parametrize("command", [
        'git log --all -- "*.env"',
        'git diff HEAD~1 HEAD -- "*.env"',
        'git log -p --all -- "**/.env"',
        'git log --all -- "*.env.production"',
    ])
    def test_a_glob_pathspec_reaching_an_env_file_is_blocked(self, command):
        """`git log -p -- "*.env"` dumps the content of every .env the history
        holds. The literal spelling was refused and the glob was not."""
        block(command)

    @pytest.mark.parametrize("command", [
        'rg --glob "*.env" TODO',
        "rg --glob .env PASSWORD",
        "grep -r --include=.env PASSWORD .",
        "grep -r --include .env PASSWORD .",
        "find . -name .env -exec cat {} ;",
        "find . -name .env -execdir cat {} ;",
        "find . -name .env -delete",
    ])
    def test_a_filter_that_selects_an_env_file_to_read_is_blocked(self, command):
        """An inclusion filter names the files the tool then opens, so it is a
        read and not a search for a name. Measured rather than reasoned:
        `rg --glob '*.env' SECRET` printed `SECRET_TOKEN=hunter2` from a `.env`
        in a scratch tree with no `--hidden`, because an explicit --glob
        overrides ripgrep's own skipping of dotfiles. `grep -r --include=.env`
        printed it too. A find predicate really does only locate, so it stays
        allowed below, but that holds only while nothing consumes the match:
        `-exec cat {}` printed the same secret that bare `-name` did not."""
        block(command)

    @pytest.mark.parametrize("command", [
        "cat .env.example",
        "cat docs/dotenv.md",
        "docker run --env-file prod.list img",
        "cat src/environment.ts",
        'grep -rn "process.env" src/',
        "npm run build -- --env-file=x",
        'git log --all -- "*.environment.ts"',
        "find . -name .env",
        "find . -name .env -print",
        "grep -r --exclude=.env PASSWORD .",
        "grep -r --exclude .env PASSWORD .",
        "rg --glob '!.env' PASSWORD",
        "node -r ts-node/register app.js",
    ])
    def test_a_name_that_merely_contains_env_is_judged_on_its_own(self, command):
        """Widening the .env match to catch a glob must not widen it to every
        token holding the three letters, nor to a command that opens nothing.
        `.env.example` is a committed template and stays refused with the rest
        of the `.env.*` family. The rest divide in two: most name no env file
        at all, while the find predicates and the exclusion flags do name one
        and still read nothing, which is the whole reason they stay allowed."""
        if ".env.example" in command:
            block(command)
        else:
            allow(command)

    def test_a_constructed_path_cannot_reach_a_control_file(self):
        """Every direct spelling was refused and `$(echo ...)` was not, because
        the word handed to the matcher was the substitution rather than the
        path it produces. A substitution can emit any string, including a
        leading directory, so the write target is unbounded and nothing about
        the visible text bounds it."""
        block("cp payload.py $(echo scripts/bash-guard.py)")
        block("cp payload.py `echo scripts/bash-guard.py`")
        block("cp payload.py $(cat target.txt)")
        block("cat payload.py > $(echo scripts/bash-guard.py)")
        block("mv payload.py $(printf %s scripts/bash-guard.py)")

    def test_a_literal_backup_suffix_is_still_not_a_substitution(self):
        """The narrowing that keeps the rule above affordable: an operand with
        no substitution in it is read exactly as before."""
        allow('cp "%s" "%s.bak"' % (SETTINGS, SETTINGS))
        allow('cp "%s" "%s.bak-20260916"' % (SETTINGS, SETTINGS))

    def test_a_substitution_that_writes_nothing_protected_still_works(self):
        """The refusal is scoped to a write. A substitution that only chooses
        what to read, or writes somewhere the protection does not reach, is
        ordinary work and the transcripts are full of it."""
        allow('grep -n TODO $(ls *.py)')
        allow('echo "$(date +%s)"')
        allow('python "$(command -v pytest)" --version')

    @pytest.mark.parametrize("command", [
        'cat "{guard}"',
        'head -40 "{guard}"',
        'grep -n "def check" "{guard}"',
        'wc -l "{guard}"',
        'python "{scripts}/check_hooks.py"',
        'python -m pytest "{scripts}/tests" -q',
        'ls -la "{scripts}"',
    ])
    def test_reading_and_running_the_project_scripts_still_works(self, command):
        """Protecting a file from being overwritten is not protecting it from
        being read, and running this project's own scripts is the workflow the
        protection exists to keep honest, not one to break."""
        allow(command.format(guard=GUARD, scripts=SCRIPTS_DIR.as_posix()))

    def test_searching_for_an_env_file_by_name_is_not_reading_one(self):
        allow('find "%s" -name ".env"' % PROJECT.as_posix())
        allow('grep -rn PORT --exclude ".env" "%s"' % SCRIPTS_DIR.as_posix())

    def test_a_search_pattern_is_not_a_filename(self):
        r"""`git ls-files | grep -i "\.env"` reads stdin and opens nothing.
        Measured: this shape appeared in a real audit for committed secrets."""
        allow(r'grep -i "\.env"')
        allow(r'grep -rn "\.env" ' + '"%s"' % SCRIPTS_DIR.as_posix())

    def test_a_pager_read_of_a_control_file_is_not_a_write(self):
        """sed without an in place flag prints. Treating every sed operand as
        written refused 86 real transcript commands, almost all of them
        `sed -n '<range>p' <file>` used as a pager."""
        allow("sed -n '340,400p' \"%s\"" % GUARD)
        allow("sed -n '1,40p' \"%s\"" % RESEARCH_GATE)
        block("sed -i 's/a/b/' \"%s\"" % GUARD)

    def test_backing_up_a_control_file_is_not_overwriting_one(self):
        """`cp a b` reads a and writes b. Flagging both refused an ordinary
        backup of settings.json in the transcripts."""
        allow('cp "%s" "%s.bak"' % (SETTINGS, SETTINGS))
        block('cp "%s.bak" "%s"' % (SETTINGS, SETTINGS))

    def test_a_substitution_containing_an_s_is_not_a_sed_exec(self):
        """sed's `s` takes any delimiter, so an unanchored matcher read
        `s(serialise(data, indent, crlf))/PROJ.write_bytes` out of the middle
        of a replacement string and refused the command."""
        allow(r"sed -n 's/PROJ\.write_bytes(serialise(data, crlf))/x(y(z))/p' f.py")


# ===========================================================================
# Fail safe, and what the off switch may still switch off.
# ===========================================================================

class TestFailSafe:
    def test_a_crashing_security_check_blocks(self, guard, monkeypatch):
        """Exit 1 is neither allow nor block under this hook contract, so an
        uncaught exception runs the command anyway. A check that cannot decide
        has no basis to allow, so it refuses and says which check broke."""
        def explode(_command):
            raise RuntimeError("synthetic failure")

        monkeypatch.setattr(guard, "_SECURITY_CHECKS", (explode,))
        message = guard.evaluate("git status")
        assert message is not None
        assert "crashed" in message
        assert "explode" in message

    def test_a_crashing_ergonomic_check_does_not_block(self, guard, monkeypatch):
        """An ergonomic check exists to avoid a prompt. Failing one costs a
        prompt, and blocking every command instead is the worse trade."""
        def explode(_command):
            raise RuntimeError("synthetic failure")

        monkeypatch.setattr(guard, "_ERGONOMIC_CHECKS", (explode,))
        assert guard.evaluate("git status") is None

    def test_the_off_switch_no_longer_disables_the_boundary(self):
        """It used to disable everything. One environment variable that turns
        off the whole boundary is not a boundary."""
        for value in ("off", "0", "false", "disabled", "no", "OFF"):
            result = run_hook(
                "bash-guard.py", _bash("git commit -am x"),
                env_overrides={"CLAUDEBOOST_BASH_GUARD": value})
            assert result.returncode == 2, (
                f"CLAUDEBOOST_BASH_GUARD={value!r} must not disable the verb gate")

    def test_the_off_switch_still_disables_the_ergonomic_half(self):
        """That half is why the switch exists: it unblocks a workflow that the
        prompt-avoidance rules obstruct, and costs only an extra prompt."""
        result = run_hook(
            "bash-guard.py", _bash("cd /repo && git status"),
            env_overrides={"CLAUDEBOOST_BASH_GUARD": "off"})
        assert result.returncode == 0

    @pytest.mark.parametrize("command", [
        "git commit -am 'unterminated",
        'git commit -am "unterminated',
        "git commit -am $(",
        "git `",
        "|||",
        "git commit -am x >",
    ])
    def test_a_command_that_does_not_parse_cleanly_never_crashes(self, guard, command):
        """Unbalanced quotes are why this does not use shlex.split, which
        raises on them. Whatever the verdict, it has to be a verdict."""
        assert guard.evaluate(command) is None or isinstance(guard.evaluate(command), str)


class TestLatency:
    def test_the_guard_stays_fast_on_a_large_command(self, guard):
        """It runs before every single Bash call, and this file records three
        separate regexes that went quadratic on this exact surface."""
        command = "echo " + ("a" * 20000)
        start = time.perf_counter()
        guard.evaluate(command)
        assert time.perf_counter() - start < 1.0

    def test_the_guard_stays_fast_on_a_large_git_command(self, guard):
        command = "git log --oneline " + " ".join("path/to/file%d.py" % i for i in range(2000))
        start = time.perf_counter()
        guard.evaluate(command)
        assert time.perf_counter() - start < 1.0

    def test_a_deeply_nested_wrapper_terminates(self, guard):
        command = "bash -c " + ('"eval ' * 30) + "git push" + ('"' * 30)
        start = time.perf_counter()
        guard.evaluate(command)
        assert time.perf_counter() - start < 1.0
