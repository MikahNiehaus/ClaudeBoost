"""
A hook must be registered with an interpreter that exists on the machine.

clean-rag/install.py registered all 14 of its hooks as a bare `python`. macOS
ships python3 and no `python`, and a modern Linux often does the same, so every
one of them died with:

    /bin/sh: python: command not found

The noise is the harmless part. The part that matters is that the hook never
ran, so the research gate, the verifier gate, the auto test gate and rag-enforce
were all silently absent on any machine without a `python` shim, while
settings.json listed them as installed.

Nothing caught it because the failure is in the registration string, not in any
script. The scripts were fine and the command around them was not, which is the
same shape as the hook-run.py wrapping bug in
tests/test_hook_wrapping_shell_safe.py.

Run: python -m pytest tests/test_hook_interpreter_exists.py -v
"""

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "clean-rag" / "install.py"

#: Names that are not guaranteed to exist. `python` is absent on macOS; `py` is
#: the Windows launcher and absent everywhere else.
UNSAFE_BARE = ("python", "py")


@pytest.fixture(scope="module")
def install_mod():
    spec = importlib.util.spec_from_file_location("cr_install", INSTALL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_installer_resolves_a_real_interpreter(install_mod):
    resolved = install_mod.HOOK_PYTHON
    assert resolved, "HOOK_PYTHON is empty"
    assert Path(resolved).exists() or shutil.which(resolved), (
        f"HOOK_PYTHON={resolved!r} does not exist, so every hook registered "
        "with it will fail with 'command not found'"
    )
    assert Path(resolved).name not in UNSAFE_BARE, (
        f"HOOK_PYTHON={resolved!r} is a bare name that is not guaranteed to "
        "resolve. Registrations need an interpreter known to exist."
    )


def test_no_registration_in_the_installer_uses_a_bare_interpreter():
    """
    Read the source, because these are string literals built at import time and
    a passing HOOK_PYTHON says nothing about a literal that ignores it.
    """
    src = INSTALL.read_text(encoding="utf-8")
    offenders = []
    for lineno, line in enumerate(src.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        m = re.search(r"""hook_command\s*=\s*f?['"]([a-zA-Z][\w.]*)\s""", line)
        if m and m.group(1) in UNSAFE_BARE:
            offenders.append((lineno, line.strip()[:90]))

    assert not offenders, (
        "clean-rag/install.py registers hook(s) with a bare interpreter name:\n"
        + "\n".join(f"  line {n}: {ctx}" for n, ctx in offenders)
    )


def test_every_hook_command_names_a_resolvable_interpreter():
    """
    The live check, across both settings files.

    Skipped rather than failed when a settings file is absent, because a fresh
    clone has not been installed yet and that is not a defect.
    """
    checked = 0
    bad = []
    for path in (Path.home() / ".claude" / "settings.json",
                 REPO / ".claude" / "settings.json"):
        if not path.exists():
            continue
        import json
        settings = json.loads(path.read_text(encoding="utf-8"))
        for event, entries in (settings.get("hooks") or {}).items():
            for entry in entries:
                for h in entry.get("hooks", []):
                    cmd = (h.get("command") or "").strip()
                    if not cmd or h.get("type") != "command":
                        continue
                    checked += 1
                    # A compound command carries its own `command -v` fallbacks.
                    if re.match(r"^\s*(if|for|while)\s", cmd):
                        continue
                    first = cmd.split()[0].strip('"')
                    name = Path(first).name
                    if name in UNSAFE_BARE and not shutil.which(first):
                        bad.append((event, first))

    if not checked:
        pytest.skip("no settings.json on this machine yet")

    assert not bad, (
        "hook(s) registered with an interpreter that does not resolve here, so "
        "they fail with 'command not found' and their gate is silently absent:\n"
        + "\n".join(f"  [{e}] {f}" for e, f in bad)
    )
