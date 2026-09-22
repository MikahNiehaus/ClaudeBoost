"""Round 4 adversarial recheck on the identity based registry watch.

Everything here was proven live against the real check
(test_exec_routes_require_registered_project.py's _RegistryWatch / _file_key /
_same_object) before being written down. Kept as regression coverage for two
attack shapes the existing suite did not carry: a UNC alias to the same file,
and a spread of device shaped paths (NUL, CON, a raw physical volume, a raw
drive handle) that must never be mistaken for the registry.

The third thing this round's recheck asked was whether the ino==0 guard,
moved this round from _file_key into _same_object, is still load bearing.
is not encoded here as a permanent test, because doing that means baking a
mutated _same_object into the suite, which asserts the mutant's behaviour
forever rather than the real code's. That check was run once, live, with the
guard removed: removing it makes
test_an_alias_with_no_file_id_is_refused_rather_than_missed in
test_registry_writer_check_soundness.py go from raising "could not watch" to
raising nothing at all, which is the guard doing real work. The existing test
already pins the real code; nothing new belongs here for it.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_exec_routes_require_registered_project import (  # noqa: E402
    _FileKey,
    _file_key,
    _keys_added_by,
    _same_object,
)
from test_registry_writer_check_soundness import _scratch_registry  # noqa: E402


def test_a_transient_add_through_a_unc_alias_is_still_caught(tmp_path):
    """\\\\localhost\\C$\\... names the same file NTFS side, os.stat proves it.

    A writer that opens the registry through its UNC form rather than its
    local drive letter form is still watched: os.stat reports the same
    (dev, ino) pair through either spelling, so identity, not string
    comparison, is what has to catch this, and does.
    """
    _, registry_path = _scratch_registry(tmp_path)
    resolved = registry_path.resolve()
    drive = str(resolved)[0]
    unc_path = f"\\\\localhost\\{drive}$" + resolved.as_posix().replace("/", "\\")[2:]

    try:
        os.stat(unc_path)
    except OSError as exc:
        pytest.skip(f"UNC loopback share not reachable in this environment: {exc}")

    def transient_via_unc():
        registry = json.loads(open(unc_path, encoding="utf-8").read())
        registry["new-pid"] = {"project_path": "C:/never"}
        with open(unc_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(registry))
        del registry["new-pid"]
        with open(unc_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(registry))

    added = _keys_added_by(transient_via_unc, registry_path)

    assert added == {"new-pid"}, (
        f"a transient add through the registry's UNC alias was not reported: "
        f"{sorted(added)}. String comparison would miss this; identity must not."
    )


@pytest.mark.parametrize("candidate", [
    r"\\.\NUL",
    r"\\.\CON",
    r"\\.\PhysicalDrive0",
    r"\\.\C:",
])
def test_device_and_raw_volume_paths_are_never_the_registry(tmp_path, candidate):
    """Property 4: fail closed must not become fail on everything.

    Each of these reports a real _FileKey (not WILL_NOT_SAY/NAMES_NOTHING) but
    with a different S_IFMT kind than a regular file, so _same_object has to
    say False outright rather than falling through to the ino==0 'undecidable'
    branch, which would wrongly treat every device on the box as a possible
    alias of the registry.
    """
    _, registry_path = _scratch_registry(tmp_path)
    registry_key = _file_key(str(registry_path))
    assert isinstance(registry_key, _FileKey)

    candidate_key = _file_key(candidate)
    if not isinstance(candidate_key, _FileKey):
        pytest.skip(f"{candidate} is not reachable via os.stat in this environment")

    assert _same_object(registry_key, candidate_key) is not True, (
        f"{candidate} was identified as the registry file, so any writer that "
        f"merely touches this device during its run would fail the check for "
        f"a file it never went near."
    )
