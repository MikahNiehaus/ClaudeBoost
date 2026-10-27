"""
`py`, `pythonw` and flagged `python -c` run source. `git init --template`
installs hooks. Commands are strings handed to the hook, never run.
"""
from __future__ import annotations

import time

import pytest

from helpers import run_hook, pretooluse


def _run(command: str):
    return run_hook("bash-guard.py", pretooluse("Bash", {"command": command}))


_PUSH = "\"import os; os.system('git push origin main')\""


@pytest.mark.parametrize("command", [
    f"py -c {_PUSH}",
    f"py -3 -c {_PUSH}",
    f"py -3.14 -c {_PUSH}",
    f"py -V:3.14 -c {_PUSH}",
    f"py.exe -c {_PUSH}",
    f"pythonw -c {_PUSH}",
    f"python -u -c {_PUSH}",
    f"python -I -c {_PUSH}",
    f"python -Ic {_PUSH}",
    f"python3 -X utf8 -c {_PUSH}",
    f"python -W ignore -c {_PUSH}",
    f"/usr/bin/python3 -c {_PUSH}",
    f"py -3.14-arm64 -c {_PUSH}",
    f"PY -c {_PUSH}",
    f"Py.EXE -3 -c {_PUSH}",
    f"python -R -c {_PUSH}",
    f"python -i -c {_PUSH}",
    f"python -uW ignore -c {_PUSH}",
    f"python -X frozen_modules=off -c {_PUSH}",
    f"python3.14t -c {_PUSH}",
    f"python3.13t.exe -I -c {_PUSH}",
    f"python3.14d -c {_PUSH}",
    f"python3.14td -c {_PUSH}",
    f"pypy -c {_PUSH}",
    f"pypy3 -c {_PUSH}",
    f"pypy3.10.exe -I -c {_PUSH}",
])
def test_interpreter_source_with_a_push_is_blocked(command):
    assert _run(command).returncode == 2, command


@pytest.mark.parametrize("command", [
    "py -3 script.py",
    "py script.py -c x",
    "python -m pytest",
    "python -u script.py",
    "node -r ts-node/register app.js",
    "./script.py -c foo",
    "copy -c x",
    'echo "py -c"',
    "py -3 -c \"print(1)\"",
    "python -m pytest -c pytest.ini",
    "python -mpytest -c pytest.ini",
    "py -3 -m pip install -c constraints.txt foo",
    "python -W ignore script.py -c x",
    "python -u foo.py -c 'git push'",
    f"python -m foo -c {_PUSH}",
    f"python -- -c {_PUSH}",
    "pyw -c x",
    "pycharm -c x",
    "pypy3 -m pytest",
    "pypy3 script.py -c x",
    "python script.py <<'EOF'\nimport os\nos.system('git push')\nEOF",
    "git log | py script.py",
])
def test_ordinary_interpreter_use_is_allowed(command):
    result = _run(command)
    assert result.returncode == 0, f"{command!r}: {result.stderr.decode()}"


_SRC = "import os; os.system('git push origin main')"


@pytest.mark.parametrize("command", [
    f"python - <<'EOF'\n{_SRC}\nEOF",
    f"python <<EOF\n{_SRC}\nEOF",
    f"python <<EOF 2>err.log\n{_SRC}\nEOF",
    f"py -3 - <<'EOF'\n{_SRC}\nEOF",
    f"python -X utf8 - <<'EOF'\n{_SRC}\nEOF",
    f"python3.14t <<'EOF'\n{_SRC}\nEOF",
    f"cat <<'EOF' | python -\n{_SRC}\nEOF",
    "node <<'EOF'\nrequire('child_process').execSync('git push')\nEOF",
    "perl <<'EOF'\nsystem('git push');\nEOF",
    f"python - <<< \"{_SRC}\"",
    f"python <<<\"{_SRC}\"",
    f"echo \"{_SRC}\" | python",
    f"printf '%s' \"{_SRC}\" | python -",
])
def test_source_fed_to_an_interpreter_on_stdin_is_blocked(command):
    assert _run(command).returncode == 2, command


@pytest.mark.parametrize("command", [
    f"python script.py <<'EOF'\n{_SRC}\nEOF",
    f"node -e 'console.log(1)' <<'EOF'\n{_SRC}\nEOF",
    f"python -m json.tool <<'EOF'\n{_SRC}\nEOF",
    f"node app.js <<'EOF'\n{_SRC}\nEOF",
    f"perl -ne 'print' <<'EOF'\n{_SRC}\nEOF",
    "python - <<'EOF'\nprint('hello')\nEOF",
    "cat data.txt | python -",
    f"echo \"{_SRC}\" | python script.py",
    f"echo \"{_SRC}\" | grep git",
])
def test_stdin_that_is_data_is_allowed(command):
    result = _run(command)
    assert result.returncode == 0, f"{command!r}: {result.stderr.decode()}"


@pytest.mark.parametrize("command", [
    f"python 0<<'EOF'\n{_SRC}\nEOF",
    f"python 1<<'EOF'\n{_SRC}\nEOF",
    f"python 2>err.log 0<<'EOF'\n{_SRC}\nEOF",
    f"python {{fd}}<<'EOF'\n{_SRC}\nEOF",
    f"python 0<<-EOF\n\t{_SRC}\n\tEOF",
    f"python3.14t 0<<'EOF'\n{_SRC}\nEOF",
    "node 0<<'EOF'\nrequire('child_process').execSync('git push')\nEOF",
])
def test_heredoc_with_a_descriptor_prefix_still_reaches_the_interpreter(command):
    assert _run(command).returncode == 2, command


@pytest.mark.parametrize("command", [
    f"python script.py 0<<'EOF'\n{_SRC}\nEOF",
    f"python -m json.tool 0<<'EOF'\n{_SRC}\nEOF",
    f"python 0 <<'EOF'\n{_SRC}\nEOF",
    f"python s0<<'EOF'\n{_SRC}\nEOF",
    f"cat 0<<'EOF'\n{_SRC}\nEOF",
])
def test_descriptor_prefix_does_not_turn_data_into_source(command):
    result = _run(command)
    assert result.returncode == 0, f"{command!r}: {result.stderr.decode()}"


@pytest.mark.parametrize("command", [
    f"{{ python <<'EOF'\n{_SRC}\nEOF\n}}",
    f"{{ python <<'EOF'\n{_SRC}\nEOF\n; }}",
    f"{{ {{ python <<'EOF'\n{_SRC}\nEOF\n}} }}",
    f"! python <<'EOF'\n{_SRC}\nEOF",
    f"! {{ python <<'EOF'\n{_SRC}\nEOF\n}}",
    f"time ! python <<'EOF'\n{_SRC}\nEOF",
    f"true && ! python <<'EOF'\n{_SRC}\nEOF",
    f"if python <<'EOF'\n{_SRC}\nEOF\nthen :; fi",
    f"if false; then :; elif python <<'EOF'\n{_SRC}\nEOF\nthen :; fi",
    f"while python <<'EOF'\n{_SRC}\nEOF\ndo :; done",
    f"until python <<'EOF'\n{_SRC}\nEOF\ndo :; done",
    f"coproc python <<'EOF'\n{_SRC}\nEOF",
    f"coproc NAME {{ python <<'EOF'\n{_SRC}\nEOF\n}}",
    f"function f {{ python <<'EOF'\n{_SRC}\nEOF\n}}",
    f"{{ python <<< \"{_SRC}\"; }}",
    f"! python <<< \"{_SRC}\"",
    f"echo \"{_SRC}\" | {{ python; }}",
    f"echo \"{_SRC}\" | ! python -",
    "cat <<'EOF' | { \"bash\"; }\ngit push\nEOF",
    "echo 'git push' | { bash; }",
])
def test_reserved_word_or_group_in_front_still_reaches_the_command(command):
    assert _run(command).returncode == 2, command


@pytest.mark.parametrize("command", [
    f"{{ python script.py <<'EOF'\n{_SRC}\nEOF\n}}",
    f"! python -m json.tool <<'EOF'\n{_SRC}\nEOF",
    f"{{ cat <<'EOF'\n{_SRC}\nEOF\n}}",
    f"echo \"{_SRC}\" | {{ cat; }}",
    "if git status; then :; fi",
    "! git diff --quiet",
    "while true; do git log -1; done",
])
def test_reserved_word_or_group_in_front_of_data_is_allowed(command):
    result = _run(command)
    assert result.returncode == 0, f"{command!r}: {result.stderr.decode()}"


@pytest.mark.parametrize("command", [
    f"python3.14td <<'EOF'\n{_SRC}\nEOF",
    f"python3.14d - <<'EOF'\n{_SRC}\nEOF",
    f"pypy3 <<'EOF'\n{_SRC}\nEOF",
])
def test_debug_and_pypy_builds_read_stdin_as_source(command):
    assert _run(command).returncode == 2, command


# Several heredocs on one line take their bodies in order (POSIX 2.7.4).
@pytest.mark.parametrize("command", [
    f"cat <<A; python <<'B'\nx\nA\n{_SRC}\nB",
    f"python <<A; python <<B\nprint(1)\nA\n{_SRC}\nB",
    f"python <<A; cat <<B\n{_SRC}\nA\nhello\nB",
    f"cat <<A; cat <<B; python <<C\nx\nA\ny\nB\n{_SRC}\nC",
    f"cat <<A <<B | python -\nx\nA\n{_SRC}\nB",
    f"cat <<A; python 0<<B\nx\nA\n{_SRC}\nB",
    f"cat <<A; node <<B\nx\nA\nrequire('child_process').execSync('git push')\nB",
    "cat <<A; bash <<B\nx\nA\ngit push origin main\nB",
    "bash <<A; bash <<B\nx\nA\ngit push origin main\nB",
])
def test_every_heredoc_on_a_line_that_feeds_an_interpreter_is_blocked(command):
    assert _run(command).returncode == 2, command


@pytest.mark.parametrize("command", [
    f"cat <<A; python script.py <<B\n{_SRC}\nA\n{_SRC}\nB",
    f"cat <<A; python <<B\n{_SRC}\nA\nprint(1)\nB",
    f"python <<A; cat <<B\nprint(1)\nA\n{_SRC}\nB",
    "cat <<A >a.txt; cat <<B >b.txt\ngit push\nA\ngit push\nB",
    f"cat <<A; python 0 <<B\nx\nA\n{_SRC}\nB",
])
def test_data_heredoc_beside_another_on_its_line_is_allowed(command):
    result = _run(command)
    assert result.returncode == 0, f"{command!r}: {result.stderr.decode()}"


def test_many_heredocs_on_one_line_stay_within_the_hook_bound():
    count = 2000
    command = ("; ".join(f"cat <<T{i}" for i in range(count)) + "; python <<Z\n"
               + "".join(f"x\nT{i}\n" for i in range(count)) + f"{_SRC}\nZ")
    start = time.perf_counter()
    result = _run(command)
    assert time.perf_counter() - start < 3.0
    assert result.returncode == 2


@pytest.mark.parametrize("command", [
    "git init --template=/some/dir",
    "git init --template /some/dir",
    "git init --templ=/some/dir",
])
def test_git_init_with_a_template_is_blocked(command):
    assert _run(command).returncode == 2, command


def test_git_init_without_a_template_is_not_refused_as_unsafe():
    stderr = _run("git init").stderr.decode()
    assert "writes a file or runs an external program" not in stderr


@pytest.mark.parametrize("command", [
    "python " + "<<< x " * 4000,
    "echo " + "<<< a " * 4000,
    "; ".join("python <<< x" for _ in range(4000)),
    "python <<< \"" + "python <<< x; " * 4000 + "\"",
], ids=["interpreter", "non_interpreter", "separate_commands", "nested_in_quotes"])
def test_many_here_strings_on_one_line_stay_within_the_hook_bound(command):
    start = time.perf_counter()
    _run(command)
    assert time.perf_counter() - start < 3.0
