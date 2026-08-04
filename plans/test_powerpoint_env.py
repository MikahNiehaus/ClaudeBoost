"""Test the powerpoint skill: SKILL.md contract, the cross platform branching
in scripts/pptx_env.py, and the installer wiring in clean-rag/install.py.

The per-OS functions take the platform as an argument specifically so all
three branches can be checked from one machine. That is the point of these
tests: a Windows developer never exercises the xdg-open path by running it.

Three sections carry named regression guards for defects found in review:

  REGRESSION 1  SKILL.md must not drift back into paraphrasing Anthropic's
                proprietary pptx skill.
  REGRESSION 2  Every command SKILL.md documents must be one that actually
                runs; it used to reference $CLAUDE_SKILL_DIR, which is not a
                real Claude Code variable and expands to nothing.
  REGRESSION 3  install_pptx_tools() must always terminate. Its "already
                installed?" probe used to be an unbounded subprocess.

Run with: python plans/test_powerpoint_env.py
"""

import ast
import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def quiet(fn, *args, **kwargs):
    """Run fn with its progress chatter swallowed; the assertions are the proof."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)

passed = 0
failed = 0


def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  PASS  {name}")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL  {name}")
        print(f"        {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001  an exception is a failure, not a crash
        print(f"  FAIL  {name}")
        print(f"        unexpected {type(e).__name__}: {e}")
        failed += 1


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "clean-rag" / "portable" / "skills" / "powerpoint"
SKILL_MD = SKILL_DIR / "SKILL.md"
HELPER = SKILL_DIR / "scripts" / "pptx_env.py"
INSTALL_PY = REPO / "clean-rag" / "install.py"

SCRATCH = Path(tempfile.mkdtemp(prefix="pptx_test_"))


def parse_frontmatter(path):
    content = Path(path).read_text(encoding="utf-8")
    if not content.startswith("---"):
        return None, content
    end = content.index("\n---\n", 3)
    fm = {}
    for line in content[4:end].splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            fm[k.strip()] = v.strip()
    return fm, content[end + 5:]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bash_blocks(text):
    return re.findall(r"```bash\n(.*?)```", text, re.DOTALL)


def function_source(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


print("\npowerpoint skill\n")

# --- layout and frontmatter -------------------------------------------------

test("SKILL.md exists", lambda: assert_true(SKILL_MD.is_file(), f"missing {SKILL_MD}"))
test("helper script exists", lambda: assert_true(HELPER.is_file(), f"missing {HELPER}"))

SKILL_TEXT = SKILL_MD.read_text(encoding="utf-8")
FM, BODY = parse_frontmatter(SKILL_MD)


def t_frontmatter():
    assert_true(FM is not None, "no frontmatter block")
    assert_true(FM.get("name") == "powerpoint",
                f"name must match the directory, got {FM.get('name')!r}")
    assert_true(len(FM.get("description", "")) > 20,
                "description too short to trigger reliably")
    assert_true("allowed-tools" in FM, "missing allowed-tools")
    assert_true(len(BODY.strip()) > 500, "body is too thin to be useful")


def t_allowed_tools_cover_the_body():
    """Property 7: allowed-tools must list every tool the body asks for."""
    allowed = {t.strip() for t in FM["allowed-tools"].split(",")}
    needed = {
        "Bash": bool(bash_blocks(BODY)),
        "Write": "Write a Python script" in BODY or "generator script" in BODY,
        "Read": re.search(r"\bRead\b (?:every|the) image", BODY) is not None,
        "Glob": re.search(r"\bGlob\b", BODY) is not None,
        "Edit": "Fix the generator" in BODY,
    }
    for tool, is_needed in needed.items():
        if is_needed:
            assert_true(tool in allowed,
                        f"body asks for {tool} but allowed-tools is {sorted(allowed)}")


test("frontmatter contract", t_frontmatter)
test("allowed-tools covers every tool the body uses", t_allowed_tools_cover_the_body)


# --- REGRESSION 1: no derivative of Anthropic's proprietary pptx skill -------
#
# The first draft of SKILL.md paraphrased Anthropic's pptx skill closely enough
# to be a derivative work, which its licence forbids. These guards assert the
# specific paraphrases are gone and the warning that explains why is present.
# They deliberately match on OUR removed wording, never on Anthropic's text.

def t_licence_warning():
    low = SKILL_TEXT.lower()
    assert_true("licence" in low or "license" in low,
                "SKILL.md must carry the warning against copying Anthropic's pptx skill")
    assert_true("derivative" in low,
                "the warning must name derivative works, which is the actual restriction")


def t_no_paraphrased_design_advice():
    """The removed paraphrases must not come back."""
    banned = [
        "sandwich",            # "sandwich the structure", dark/light slide ordering
        "repeating motif",     # "commit to one repeating motif"
        "visual motif",
        "accent lines under titles",
        "colour bars",
        "color bars",
        "accent stripes",
        "visual signature of a generated deck",
        "hallmark",
        "ai-generated",
    ]
    low = SKILL_TEXT.lower()
    hits = [phrase for phrase in banned if phrase in low]
    assert_true(not hits, f"paraphrased wording is back in SKILL.md: {hits}")


def t_qa_checklist_is_not_a_cloned_six_item_list():
    """The QA list was a six item ordered list matching theirs item for item."""
    numbered = re.findall(r"^\d+\. ", BODY, re.MULTILINE)
    # the narration recipe is legitimately a numbered procedure; the render
    # inspection list must not be a numbered checklist at all.
    render_section = BODY[BODY.index("## Step 4"):BODY.index("## Design decisions")]
    assert_true(not re.search(r"^\d+\. ", render_section, re.MULTILINE),
                "the render inspection list must not be a numbered checklist")
    assert_true(len(numbered) <= 5,
                f"unexpected numbered list growth in the body ({len(numbered)} items)")


def t_library_claims_are_attributed():
    """Factual python-pptx claims must cite the library's own tracker/docs."""
    for issue in ("python-pptx#1141", "python-pptx#973", "python-pptx#885"):
        assert_true(issue in SKILL_TEXT,
                    f"library behaviour claim is unattributed: expected {issue}")


test("carries the licence warning", t_licence_warning)
test("REGRESSION 1: no paraphrased design advice", t_no_paraphrased_design_advice)
test("REGRESSION 1: QA guidance is not a cloned six item list",
     t_qa_checklist_is_not_a_cloned_six_item_list)
test("REGRESSION 1: python-pptx claims cite the upstream tracker",
     t_library_claims_are_attributed)


# --- REGRESSION 2: every documented command actually resolves ---------------

CANONICAL_HELPER = Path.home() / ".claude" / "skills" / "powerpoint" / "scripts" / "pptx_env.py"


def t_no_invented_env_var():
    """CLAUDE_SKILL_DIR may be named as a warning, never expanded as a variable."""
    assert_true(not re.search(r"\$\{?CLAUDE_SKILL_DIR", SKILL_TEXT),
                "CLAUDE_SKILL_DIR is not a Claude Code variable; it expands to nothing "
                "and every command using it fails")
    for block in bash_blocks(BODY):
        assert_true("CLAUDE_SKILL_DIR" not in block,
                    f"command block still mentions CLAUDE_SKILL_DIR:\n{block.strip()}")


def t_every_shell_var_in_a_command_is_real():
    """Any ${VAR} a command block relies on must exist where the command runs.

    The blocks run in bash, so HOME is guaranteed by POSIX regardless of
    whether this Python process inherited it (Windows does not always set it
    outside Git Bash). Every other variable has to be really present.
    """
    posix_guaranteed = {"HOME", "PWD"}
    for block in bash_blocks(BODY):
        for var in set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", block)):
            assert_true(var in posix_guaranteed or var in os.environ,
                        f"command block references ${{{var}}}, which is not set; "
                        f"it will expand to an empty string:\n{block.strip()}")


def t_every_helper_path_is_the_canonical_install_path():
    refs = re.findall(r'"([^"]*pptx_env\.py)"', BODY)
    assert_true(refs, "SKILL.md documents no helper invocation at all")
    for ref in refs:
        # bash expands ${HOME} even where this process did not inherit it
        resolved = Path(os.path.expandvars(ref.replace("${HOME}", str(Path.home()))))
        assert_true(resolved == CANONICAL_HELPER,
                    f"documented path {ref!r} expands to {resolved}, "
                    f"not the install location {CANONICAL_HELPER}")


def t_documented_helper_path_is_quoted():
    """Unquoted paths break on a home directory containing a space."""
    for block in bash_blocks(BODY):
        for line in block.splitlines():
            if "pptx_env.py" not in line:
                continue
            assert_true(re.search(r'"[^"]*pptx_env\.py"', line),
                        f"helper path must be double quoted:\n{line}")


def t_documented_commands_run():
    """Run each documented subcommand against the real script, as written."""
    target = CANONICAL_HELPER if CANONICAL_HELPER.is_file() else HELPER
    for args in (["--help"], ["doctor"], ["workspace"]):
        r = subprocess.run([sys.executable, str(target), *args],
                           capture_output=True, text=True, timeout=120)
        assert_true(r.returncode == 0,
                    f"`pptx_env.py {' '.join(args)}` exited {r.returncode}: {r.stderr[:300]}")
        assert_true(r.stdout.strip(), f"`pptx_env.py {' '.join(args)}` printed nothing")


def t_pdftoppm_is_resolved_not_assumed_on_path():
    """poppler is routinely installed without landing on PATH."""
    assert_true("pptx_env.py\" pdftoppm)" in BODY,
                "the pdftoppm command must take its binary from the helper's "
                "resolver, not assume `pdftoppm` is on PATH")


test("REGRESSION 2: no invented CLAUDE_SKILL_DIR variable", t_no_invented_env_var)
test("REGRESSION 2: every shell variable used by a command exists",
     t_every_shell_var_in_a_command_is_real)
test("REGRESSION 2: helper paths resolve to the install location",
     t_every_helper_path_is_the_canonical_install_path)
test("REGRESSION 2: helper paths are quoted against spaces",
     t_documented_helper_path_is_quoted)
test("REGRESSION 2: documented commands exit zero when run",
     t_documented_commands_run)
test("REGRESSION 2: pdftoppm is resolved through the helper",
     t_pdftoppm_is_resolved_not_assumed_on_path)


# --- the cross platform branches -------------------------------------------

env = load_module(HELPER, "pptx_env")


def t_open_command_windows():
    assert_true(env.open_command("d.pptx", platform="win32") is None,
                "Windows must signal os.startfile by returning None")


def t_open_command_macos():
    argv = env.open_command("d.pptx", platform="darwin")
    assert_true(argv == ["open", "d.pptx"], f"got {argv}")


def t_open_command_linux():
    argv = env.open_command("d.pptx", platform="linux")
    assert_true(argv == ["xdg-open", "d.pptx"], f"got {argv}")


test("open_command: windows", t_open_command_windows)
test("open_command: macos", t_open_command_macos)
test("open_command: linux", t_open_command_linux)


def t_soffice_windows_uses_env():
    pats = env.soffice_candidates(platform="win32",
                                  env={"PROGRAMFILES": r"C:\PF"})
    assert_true(any(r"C:\PF" in p for p in pats),
                f"must expand PROGRAMFILES, got {pats}")
    assert_true(all(p.endswith(".exe") for p in pats),
                f"windows candidates must be .exe, got {pats}")


def t_soffice_windows_uses_programw6432():
    pats = env.soffice_candidates(platform="win32", env={"PROGRAMW6432": r"C:\PF64"})
    assert_true(any(r"C:\PF64" in p for p in pats),
                f"PROGRAMW6432 is the 64 bit root on a WOW64 process, got {pats}")


def t_soffice_windows_no_env():
    # a stripped environment must not crash or emit a "None\..." path
    pats = env.soffice_candidates(platform="win32", env={})
    assert_true(pats == [], f"no env vars means no candidates, got {pats}")


def t_soffice_macos():
    pats = env.soffice_candidates(platform="darwin", env={})
    assert_true(any("LibreOffice.app" in p for p in pats), f"got {pats}")
    assert_true(all(p.startswith("/") and p.endswith("/soffice") for p in pats),
                f"macOS candidates must be absolute paths to the bundle binary, got {pats}")


def t_soffice_linux():
    pats = env.soffice_candidates(platform="linux", env={})
    assert_true("/usr/bin/soffice" in pats,
                f"the distro package path must be a candidate, got {pats}")
    assert_true(all(p.startswith("/") for p in pats),
                f"linux candidates must be absolute, got {pats}")


test("soffice_candidates: windows expands env", t_soffice_windows_uses_env)
test("soffice_candidates: windows uses PROGRAMW6432", t_soffice_windows_uses_programw6432)
test("soffice_candidates: windows empty env is safe", t_soffice_windows_no_env)
test("soffice_candidates: macos", t_soffice_macos)
test("soffice_candidates: linux", t_soffice_linux)


def t_media_all_platforms():
    for plat, needle in (("win32", ".exe"), ("darwin", "/bin/ffmpeg"), ("linux", "/bin/ffmpeg")):
        pats = env.media_candidates("ffmpeg", platform=plat,
                                    env={"LOCALAPPDATA": r"C:\LA", "PROGRAMFILES": r"C:\PF"})
        assert_true(pats, f"{plat} produced no candidates")
        assert_true(any(needle in p for p in pats), f"{plat}: got {pats}")


def t_media_binary_name_is_honoured():
    for binary in ("ffmpeg", "ffprobe", "pdftoppm"):
        for plat in ("win32", "darwin", "linux"):
            pats = env.media_candidates(binary, platform=plat,
                                        env={"LOCALAPPDATA": r"C:\LA", "PROGRAMFILES": r"C:\PF"})
            assert_true(all(binary in p for p in pats),
                        f"{plat}/{binary}: candidates must name the requested binary, got {pats}")


test("media_candidates: all platforms", t_media_all_platforms)
test("media_candidates: honours the requested binary name", t_media_binary_name_is_honoured)


# --- workspace resolution ---------------------------------------------------

FAKE_HOME = SCRATCH / "fakehome"
(FAKE_HOME / "scripts").mkdir(parents=True, exist_ok=True)
RESOLVER = FAKE_HOME / "scripts" / "get-active-workspace.py"

WORKSPACE_KEYS = ("workspace_id", "workspace_path", "project_path")


def with_env(name, value, fn):
    saved = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        fn()
    finally:
        if saved is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = saved


def with_resolver(body, fn):
    RESOLVER.write_text(body, encoding="utf-8")
    with_env("CLAUDEBOOST_HOME", str(FAKE_HOME), fn)


def assert_workspace_contract(ws):
    assert_true(isinstance(ws, dict), f"must return a dict, got {type(ws)}")
    for key in WORKSPACE_KEYS:
        assert_true(key in ws, f"missing key {key!r} in {ws}")
    assert_true(ws["project_path"], f"project_path must never be empty: {ws}")


def t_workspace_shape():
    assert_workspace_contract(env.active_workspace())


def t_workspace_survives_bad_home():
    with_env("CLAUDEBOOST_HOME", str(REPO / "no-such-dir-xyz"),
             lambda: assert_workspace_contract(env.active_workspace()))


def t_workspace_survives_no_home():
    with_env("CLAUDEBOOST_HOME", None,
             lambda: assert_workspace_contract(env.active_workspace()))


def t_output_dir_is_real():
    d = env.output_dir()
    assert_true(d.is_dir(), f"output_dir returned a non directory: {d}")


test("active_workspace returns the expected keys", t_workspace_shape)
test("active_workspace survives a bad CLAUDEBOOST_HOME", t_workspace_survives_bad_home)
test("active_workspace survives no CLAUDEBOOST_HOME at all", t_workspace_survives_no_home)
test("output_dir is a real directory", t_output_dir_is_real)


# malformed resolver output: every one of these must still satisfy the contract
MALFORMED_RESOLVERS = {
    "a JSON list": "import json; print(json.dumps(['not', 'a', 'dict']))",
    "invalid JSON": "print('not json at all {{{')",
    "empty stdout": "pass",
    "a bare JSON number": "print('42')",
    "JSON null": "print('null')",
    "nonzero exit with valid stdout":
        "import sys; print('{\"workspace\": \"x\"}'); sys.exit(1)",
    "a traceback on stderr":
        "import sys; sys.stderr.write('boom\\n'); sys.exit(3)",
}

for label, script in MALFORMED_RESOLVERS.items():
    test(f"active_workspace survives resolver returning {label}",
         (lambda s=script: with_resolver(
             s, lambda: assert_workspace_contract(env.active_workspace())))
         )


def t_resolver_passthrough():
    def check():
        ws = env.active_workspace()
        assert_workspace_contract(ws)
        assert_true(ws["workspace_id"] == "abc123", f"workspace_id must pass through: {ws}")
        assert_true(ws["workspace_path"] == "/some/path", f"workspace_path must pass through: {ws}")
    with_resolver(
        "import json; print(json.dumps({'workspace_id': 'abc123', "
        "'workspace_path': '/some/path', 'project_path': '/proj'}))",
        check,
    )


test("active_workspace passes a well formed resolver response through", t_resolver_passthrough)


# --- to_pdf / open_file must not raise --------------------------------------

def t_to_pdf_missing_pptx():
    result = env.to_pdf(str(SCRATCH / "does-not-exist.pptx"), str(SCRATCH / "out"))
    assert_true(result is None, f"expected None for a missing pptx, got {result}")


def t_open_file_nonexistent():
    ok = env.open_file(str(SCRATCH / "no-such-file-xyz.pptx"))
    assert_true(isinstance(ok, bool), f"open_file must return a bool, got {type(ok)}")


test("to_pdf returns None on a missing pptx instead of raising", t_to_pdf_missing_pptx)
test("open_file returns a bool on a nonexistent path instead of raising", t_open_file_nonexistent)


# --- installer wiring -------------------------------------------------------

inst = load_module(INSTALL_PY, "clean_rag_install")
INSTALL_TREE = ast.parse(INSTALL_PY.read_text(encoding="utf-8"))


def t_installer_wired():
    src = INSTALL_PY.read_text(encoding="utf-8")
    assert_true("def install_pptx_tools" in src, "install_pptx_tools is not defined")
    after_main = src[src.index("def main("):]
    assert_true("install_pptx_tools()" in after_main,
                "install_pptx_tools is not called inside main()")


test("installer defines and calls install_pptx_tools", t_installer_wired)


def t_install_user_assets_copies_the_scripts_subfolder():
    """Property 6: the skill's scripts/ subfolder must reach ~/.claude/skills."""
    dest = SCRATCH / "claude_dir"
    saved = inst.CLAUDE_DIR
    inst.CLAUDE_DIR = dest
    try:
        quiet(inst.install_user_assets)
    finally:
        inst.CLAUDE_DIR = saved
    landed = dest / "skills" / "powerpoint" / "scripts" / "pptx_env.py"
    assert_true(landed.is_file(), f"helper script did not reach {landed}")
    assert_true((dest / "skills" / "powerpoint" / "SKILL.md").is_file(),
                "SKILL.md did not reach the install location")
    caches = list((dest / "skills").rglob("__pycache__"))
    assert_true(not caches, f"bytecode caches must not ship: {caches}")


test("install_user_assets copies the skill including scripts/",
     t_install_user_assets_copies_the_scripts_subfolder)


# --- REGRESSION 3: install_pptx_tools always terminates ---------------------
#
# The "already installed?" check used to be `subprocess.run([python, "-c",
# "import <mod>"])` with no timeout, so a package that blocks at import time
# hung the installer forever. The contract, shared with install_npm_qa_tools,
# is best effort: warn and continue, never abort.

def t_probe_does_not_spawn_an_interpreter():
    node = function_source(INSTALL_TREE, "install_pptx_tools")
    assert_true(node is not None, "install_pptx_tools not found in install.py")
    for call in [n for n in ast.walk(node) if isinstance(n, ast.Call)]:
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "run":
            continue
        args = call.args[0] if call.args else None
        if isinstance(args, ast.List) and len(args.elts) >= 2:
            second = args.elts[1]
            assert_true(not (isinstance(second, ast.Constant) and second.value == "-c"),
                        "the import probe must not spawn `python -c import ...`; "
                        "use _module_available (importlib.util.find_spec) instead")


def t_every_subprocess_in_install_pptx_tools_has_a_timeout():
    node = function_source(INSTALL_TREE, "install_pptx_tools")
    assert_true(node is not None, "install_pptx_tools not found in install.py")
    runs = [n for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "run"]
    assert_true(runs, "expected at least one subprocess.run in install_pptx_tools")
    for call in runs:
        kwargs = {kw.arg for kw in call.keywords}
        assert_true("timeout" in kwargs,
                    f"subprocess.run at install.py line {call.lineno} has no timeout; "
                    "an unbounded spawn can hang the installer forever")


def t_module_available_never_imports_the_module():
    """find_spec locates without executing, which is why it cannot hang."""
    pkg_dir = SCRATCH / "slowmod_site"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    sentinel = SCRATCH / "slow_mod_was_imported"
    if sentinel.exists():
        sentinel.unlink()
    (pkg_dir / "slow_mod.py").write_text(
        "import time, pathlib\n"
        f"pathlib.Path(r'{sentinel}').write_text('imported')\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(pkg_dir))
    try:
        start = time.monotonic()
        found = inst._module_available("slow_mod")
        elapsed = time.monotonic() - start
    finally:
        sys.path.remove(str(pkg_dir))
        sys.modules.pop("slow_mod", None)
    assert_true(found is True, "an importable module must be reported as available")
    assert_true(not sentinel.exists(),
                "the probe executed the module; it must only locate it")
    assert_true(elapsed < 5.0,
                f"the probe took {elapsed:.1f}s on a module that sleeps 30s at import")


def t_module_available_on_a_missing_module():
    assert_true(inst._module_available("no_such_module_xyz_123") is False,
                "a missing module must be reported unavailable, not raise")


def t_install_pptx_tools_bounds_every_spawn_at_runtime():
    """Every spawn the function actually makes must carry a timeout."""
    calls = []

    class FakeResult:
        returncode = 0
        stdout = "/fake/path"
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert "timeout" in kwargs, f"unbounded spawn: {argv}"
        return FakeResult()

    saved_run, saved_probe = inst.subprocess.run, inst._module_available
    inst.subprocess.run = fake_run
    inst._module_available = lambda _m: False   # force the pip install branch
    try:
        quiet(inst.install_pptx_tools)
    finally:
        inst.subprocess.run = saved_run
        inst._module_available = saved_probe

    assert_true(calls, "install_pptx_tools made no subprocess calls at all")
    for argv, kwargs in calls:
        assert_true(kwargs.get("timeout"), f"spawn without a timeout: {argv}")


def t_install_pptx_tools_never_raises_when_a_spawn_fails():
    """Best effort contract: a timeout or an OS error must warn, not abort."""
    for boom in (subprocess.TimeoutExpired(cmd="x", timeout=1),
                 OSError("no such executable"),
                 MemoryError()):
        def fake_run(argv, **kwargs):
            raise boom

        saved_run, saved_probe = inst.subprocess.run, inst._module_available
        inst.subprocess.run = fake_run
        inst._module_available = lambda _m: False
        try:
            quiet(inst.install_pptx_tools)
        except BaseException as e:  # noqa: BLE001  SystemExit counts as a failure here
            raise AssertionError(
                f"install_pptx_tools raised {type(e).__name__} when a spawn "
                f"raised {type(boom).__name__}; it must warn and continue"
            ) from None
        finally:
            inst.subprocess.run = saved_run
            inst._module_available = saved_probe


def t_install_pptx_tools_terminates():
    """End to end wall clock bound, with nothing stubbed out."""
    start = time.monotonic()
    try:
        quiet(inst.install_pptx_tools)
    except BaseException as e:  # noqa: BLE001
        raise AssertionError(f"install_pptx_tools raised {type(e).__name__}: {e}") from None
    elapsed = time.monotonic() - start
    assert_true(elapsed < 120, f"install_pptx_tools took {elapsed:.0f}s")


test("REGRESSION 3: the import probe does not spawn an interpreter",
     t_probe_does_not_spawn_an_interpreter)
test("REGRESSION 3: every subprocess.run in install_pptx_tools has a timeout",
     t_every_subprocess_in_install_pptx_tools_has_a_timeout)
test("REGRESSION 3: _module_available locates without importing",
     t_module_available_never_imports_the_module)
test("REGRESSION 3: _module_available on a missing module returns False",
     t_module_available_on_a_missing_module)
test("REGRESSION 3: every runtime spawn is bounded",
     t_install_pptx_tools_bounds_every_spawn_at_runtime)
test("REGRESSION 3: a failing spawn warns instead of aborting",
     t_install_pptx_tools_never_raises_when_a_spawn_fails)
test("REGRESSION 3: install_pptx_tools terminates", t_install_pptx_tools_terminates)


# --- no machine specific paths anywhere in the shipped skill ----------------

def t_no_machine_specific_paths():
    """Property 1: nothing shipped may hardcode this developer's machine."""
    for path in sorted(SKILL_DIR.rglob("*")):
        if not path.is_file() or path.suffix == ".pyc":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in ("C:/Users/", "C:\\Users\\", "/Users/", "/home/"):
            assert_true(needle not in text,
                        f"{path.name} hardcodes a user specific path: {needle}")


test("no machine specific absolute paths in the shipped skill", t_no_machine_specific_paths)

if __name__ == "__main__":
    shutil.rmtree(SCRATCH, ignore_errors=True)

    print(f"\n  {passed} passed, {failed} failed\n")
    sys.exit(1 if failed else 0)
