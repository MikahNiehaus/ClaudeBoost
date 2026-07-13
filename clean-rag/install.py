#!/usr/bin/env python3
"""clean-rag installer. Registers hooks and sets up the environment.

Usage:
  python clean-rag/install.py                # full install
  python clean-rag/install.py --skip-deps    # skip pip install
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CLEAN_RAG_HOME = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"

# Hook sentinels: unique strings in hook commands for idempotent registration
RAG_ENFORCE_SENTINEL = "rag-enforce.py"
REINDEX_SENTINEL = "reindex-after-edit.py"
SESSION_SENTINEL = "CLEAN-RAG ENFORCEMENT"
GRAPH_CONTEXT_SENTINEL = "graph-context-inject.py"
SPEC_COMPLIANCE_GATE_SENTINEL = "spec-compliance-gate.py"
CODE_PATTERN_INJECT_SENTINEL = "code-pattern-inject.py"
RESEARCH_GATE_SENTINEL = "research-gate.py"
RESEARCH_RECORD_SENTINEL = "research-record.py"


def _say(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERROR] {msg}")


def read_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 1: Create directories
# ---------------------------------------------------------------------------
def ensure_directories() -> None:
    dirs = ["knowledge", "databases", "databases/_projects", "state",
            "server", "hooks", "cli"]
    for d in dirs:
        (CLEAN_RAG_HOME / d).mkdir(parents=True, exist_ok=True)
    _ok("Directories created")


def ensure_env_file() -> None:
    """Seed clean-rag/.env from the template on first install.

    The .env is gitignored, so a fresh checkout has none. Copy the committed
    .env.example over, but never clobber an existing .env, that's the machine's
    own config. config.py reads it (and a ClaudeBoost/.env one level up) at
    startup.
    """
    env = CLEAN_RAG_HOME / ".env"
    example = CLEAN_RAG_HOME / ".env.example"
    if env.exists():
        _ok(".env already present, left as is")
        return
    if not example.is_file():
        _warn(".env.example missing, skipping .env seed")
        return
    shutil.copy2(example, env)
    _ok("created clean-rag/.env from template")


# ---------------------------------------------------------------------------
# Copy the pieces that have to live under ~/.claude, not in the repo.
#
# The research agents, the two skills, and the hook launcher can't stay only in
# the repo: Claude Code reads agents from ~/.claude/agents, skills from
# ~/.claude/skills, and the launcher is referenced from ~/.claude/settings.json.
# So the repo holds the canonical copies under clean-rag/portable/, and this
# copies them into place. A clone plus one install run reproduces the whole
# setup on a new machine, which it could not before: the hooks were wired to run
# a launcher that nothing created and to satisfy a gate with agents that didn't
# exist.
# ---------------------------------------------------------------------------
def install_user_assets() -> None:
    portable = CLEAN_RAG_HOME / "portable"
    if not portable.is_dir():
        _warn("clean-rag/portable not found, skipping user asset install")
        return

    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)

    def _copy_file(src: Path, dst: Path) -> None:
        if not src.is_file():
            _warn(f"missing bundled file: {src.name}")
            return
        # Don't silently stomp a copy the user edited to be newer than the repo's.
        # Note it and skip, so a local tweak survives a re-run.
        if dst.exists() and dst.stat().st_mtime > src.stat().st_mtime:
            _warn(f"{dst.name} in ~/.claude is newer than the repo copy, leaving it")
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        _ok(f"installed {dst.relative_to(CLAUDE_DIR.parent)}")

    # The branch safety launcher. Lives outside the repo on purpose, so a branch
    # switch can't remove it out from under a live hook registration.
    _copy_file(portable / "hook-run.py", CLAUDE_DIR / "hook-run.py")

    # Agents. research-agent (Sonnet) and triage-agent (Haiku).
    for md in (portable / "agents").glob("*.md"):
        _copy_file(md, CLAUDE_DIR / "agents" / md.name)

    # Skills. Copied whole so a skill can carry more than one file later.
    skills_src = portable / "skills"
    if skills_src.is_dir():
        shutil.copytree(skills_src, CLAUDE_DIR / "skills", dirs_exist_ok=True)
        _ok("installed .claude/skills (research, research-routing)")


# ---------------------------------------------------------------------------
# Step 2: Install Python deps
# ---------------------------------------------------------------------------
def install_deps() -> None:
    req_file = CLEAN_RAG_HOME / "requirements.txt"
    if not req_file.exists():
        _warn("requirements.txt not found, skipping pip install")
        return
    _say("Installing Python dependencies...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        _ok("Dependencies installed")
    else:
        _warn(f"pip install returned {result.returncode}: {result.stderr[:200]}")


# ---------------------------------------------------------------------------
# Hook registration helpers
# ---------------------------------------------------------------------------

# Lives in ~/.claude/, deliberately outside the repo, because that's the whole
# point of it.
HOOK_RUNNER = Path.home() / ".claude" / "hook-run.py"


def _wrap_command(command: str) -> str:
    """Route a hook command through hook-run.py so a branch switch can't brick Claude.

    Hook commands are registered in the global settings.json, which does not
    change when you check out a different branch. The scripts they point at do
    live in the repo. So a branch that predates a hook leaves a live registration
    aimed at nothing, python exits 2, and Claude Code reads exit 2 from a
    PreToolUse hook as "block this tool call". Not a warning. Every Edit, Write,
    and Bash refused until you switch back.

    Measured on this repo's real branches: switching to main breaks 4 live hooks,
    2 of them blocking. The two feature branches break 11, with 4 blocking.

    hook-run.py runs the script if it's there, exits 0 if it isn't, and passes
    real exit codes straight through so a genuine gate can still block a genuine
    edit. It only swallows absence.
    """
    if not command or ".py" not in command or "hook-run.py" in command:
        return command

    runner = str(HOOK_RUNNER).replace("\\", "/")

    # Split the interpreter off the front, keep whatever it was.
    match = re.match(r'^\s*("[^"]*"|\S+)\s+(.*)$', command)
    if not match:
        return command

    interpreter, rest = match.group(1), match.group(2).strip()
    return f'{interpreter} "{runner}" {rest}'


def _hook_target_script(command: str) -> Path | None:
    """The .py a hook command actually runs (ignoring the hook-run.py wrapper)."""
    scripts = [m for m in re.findall(r'"([^"]*\.py)"', command)
               if "hook-run.py" not in m]
    if not scripts:
        scripts = [m for m in re.findall(r'(\S+\.py)', command)
                   if "hook-run.py" not in m]
    if not scripts:
        return None
    raw = scripts[-1]
    expanded = os.path.expandvars(os.path.expanduser(raw))
    return Path(expanded.replace("\\", "/"))


def heal_stale_hooks() -> None:
    """Make a re-install repair a broken or stale settings.json.

    Two failure modes this fixes, both seen for real:

    1. A registration left over from an older install points at a script that no
       longer exists (research-task-nudge was the one that bit). If that command
       isn't wrapped, the missing script exits nonzero and, on a PreToolUse hook,
       blocks the tool. So any registration whose target script is gone gets
       pruned here.

    2. A hook registered before the launcher existed runs the script directly,
       so a later branch switch or deletion breaks it. Every remaining command
       gets wrapped through hook-run.py, which no-ops a missing script instead of
       breaking. Idempotent: already wrapped commands are left alone.

    Runs near the end of install, and because ClaudeBoost's setup.py delegates to
    this installer as its last step, setup.py inherits the heal for free.
    """
    settings = read_json(SETTINGS_PATH)
    hooks = settings.get("hooks", {})
    if not hooks:
        return

    pruned = 0
    wrapped = 0
    for event, entries in list(hooks.items()):
        kept = []
        for entry in entries:
            drop_entry = False
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if not cmd or ".py" not in cmd:
                    continue
                target = _hook_target_script(cmd)
                if target is not None and not target.exists():
                    # Deleted or deprecated script. Drop the whole entry so it
                    # can't fire a missing file.
                    drop_entry = True
                    pruned += 1
                    break
                new_cmd = _wrap_command(cmd)
                if new_cmd != cmd:
                    h["command"] = new_cmd
                    wrapped += 1
            if not drop_entry:
                kept.append(entry)
        hooks[event] = kept

    if pruned or wrapped:
        write_json(SETTINGS_PATH, settings)
        _ok(f"healed hooks: pruned {pruned} dead, wrapped {wrapped} through hook-run.py")
    else:
        _ok("hooks healthy: none dead, all wrapped")


def _register_hook(
    settings: dict,
    hook_type: str,
    sentinel: str,
    hook_entry: dict,
    prepend: bool = False,
    label: str = "",
) -> None:
    """Register a hook in settings.json, idempotently.

    If a hook with the sentinel already exists, refresh its command.
    Otherwise, append (or prepend) the new entry.
    """
    hooks = settings.setdefault("hooks", {})
    hook_list = hooks.get(hook_type, [])
    if not isinstance(hook_list, list):
        hook_list = []

    # Every registration funnels through here, so wrapping in this one place
    # covers hooks that don't exist yet too.
    for h in hook_entry.get("hooks", []):
        if "command" in h:
            h["command"] = _wrap_command(h["command"])

    new_cmd = ""
    for h in hook_entry.get("hooks", []):
        if "command" in h:
            new_cmd = h["command"]
            break

    # Check if already registered
    for existing in hook_list:
        for h in existing.get("hooks", []):
            cmd = h.get("command", "")
            prompt = h.get("prompt", "")
            if sentinel in cmd or sentinel in prompt:
                # Refresh
                if new_cmd and cmd != new_cmd:
                    h["command"] = new_cmd
                    _ok(f"{label} hook path refreshed")
                elif "prompt" in h and sentinel in prompt:
                    # Refresh prompt text
                    for new_h in hook_entry.get("hooks", []):
                        if "prompt" in new_h:
                            h["prompt"] = new_h["prompt"]
                    _ok(f"{label} prompt refreshed")
                else:
                    _ok(f"{label} already registered")
                hooks[hook_type] = hook_list
                write_json(SETTINGS_PATH, settings)
                return

    if prepend:
        hook_list.insert(0, hook_entry)
    else:
        hook_list.append(hook_entry)
    hooks[hook_type] = hook_list
    write_json(SETTINGS_PATH, settings)
    _ok(f"{label} registered ({hook_type})")




# ---------------------------------------------------------------------------
# Step 3b: Register graph-context-inject hook (PreToolUse) -- plan Stage 5+7.
# Not prepend=True like proof-gate: this one only informs, never blocks, so
# order relative to proof-gate doesn't matter for correctness.
# ---------------------------------------------------------------------------
def register_graph_context_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/graph-context-inject.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PreToolUse", GRAPH_CONTEXT_SENTINEL,
        hook_entry, prepend=False, label="graph-context-inject",
    )


# ---------------------------------------------------------------------------
# Step 4: Set CLEAN_RAG_HOME env var in settings.json
# ---------------------------------------------------------------------------
def set_env_var() -> None:
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})
    env["CLEAN_RAG_HOME"] = CLEAN_RAG_HOME.as_posix()
    # Default proof-gate to batched (once-per-turn) checking everywhere, not
    # just for local models. proof-gate.py's own default is "pretooluse"
    # (blocks every Edit/Write/MultiEdit individually) unless this env var
    # says otherwise -- "stop" defers checking to the Stop hook instead.
    # Settings.json's env block is visible to hook subprocesses (confirmed
    # by LocalAI's manage-claude-settings.ps1, which sets this same var to
    # gate local-model burst writes), so no real OS-level env var is needed
    # here, unlike CLAUDE_CODE_AUTO_COMPACT_WINDOW which upstream Claude
    # Code's own autocompact logic can't see through settings.json.
    env.setdefault("CLEAN_RAG_GATE_MODE", "stop")
    write_json(SETTINGS_PATH, settings)
    _ok(f"CLEAN_RAG_HOME set to {CLEAN_RAG_HOME.as_posix()}")


def protect_research_state() -> None:
    """Deny the Edit/Write tools on the research gate's state directory.

    Front door lock for the tamper evidence. state/research/ holds the turn
    stamps and the hash chained audit log, all machine written. Nothing has a
    legitimate reason to edit them by hand, so denying the model's Edit/Write
    tools there stops the reflexive "just write the stamp" shortcut and shows a
    block message instead, which is the moment it should spawn research instead.

    This is a speed bump, not a wall. The harness enforces deny on its own file
    tools, but a python subprocess run through Bash can still open the file, so
    a determined bypass remains. That's fine: the hash chained audit
    (cli/audit.py verify) makes any bypass permanent and greppable. Cheap lock
    plus audit, the same shape as chattr +a over an append only log. Verified
    worth keeping via /research this session (defense in depth, non adversarial
    threat model, zero false positives).

    Idempotent: adds each rule only if absent.
    """
    settings = read_json(SETTINGS_PATH)
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    rules = [
        "Edit(**/clean-rag/state/research/**)",
        "Write(**/clean-rag/state/research/**)",
    ]
    added = 0
    for rule in rules:
        if rule not in deny:
            deny.append(rule)
            added += 1
    if added:
        write_json(SETTINGS_PATH, settings)
        _ok(f"research state protected ({added} deny rule(s) added)")
    else:
        _ok("research state deny rules already present")
    _ok("CLEAN_RAG_GATE_MODE defaulted to 'stop' (batched proof-checking once per turn)")


# ---------------------------------------------------------------------------
# Step 5: Register SessionStart — NO-OP (enforcement via UserPromptSubmit + Stop)
# ---------------------------------------------------------------------------
def register_session_prompt() -> None:
    # SessionStart: prompt-type hooks are NOT supported (SessionStart fires before any conversation)
    # Enforcement moved to:
    #   UserPromptSubmit: rag-enforce.py (real query search, web fallback, git auto index every turn)
    #   PreToolUse: code-pattern-inject.py, rag-search-on-edit.py (forced research before edits)
    # No hook registered here.
    _ok("SessionStart enforcement via UserPromptSubmit + PreToolUse hooks")


# ---------------------------------------------------------------------------
# Step 5b: Register rag-enforce UserPromptSubmit hook
# ---------------------------------------------------------------------------
def register_rag_enforce_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    # Use env var for portability across machines
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/rag-enforce.py"'
    hook_entry = {
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "UserPromptSubmit", RAG_ENFORCE_SENTINEL,
        hook_entry, label="rag-enforce",
    )


# ---------------------------------------------------------------------------
# Step 5c: Register reindex PostToolUse hook
# ---------------------------------------------------------------------------
def register_reindex_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    # Use env var for portability across machines
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/reindex-after-edit.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", REINDEX_SENTINEL,
        hook_entry, label="reindex-after-edit",
    )


# ---------------------------------------------------------------------------
# Step 5g: Register spec-compliance-gate hook (Stop) -- checks task keywords
# ---------------------------------------------------------------------------
def register_spec_compliance_gate_hook() -> None:
    """Register the spec-compliance Stop hook.

    Always registered, default on -- cheap (regex only, no LLM call) with
    no false-block risk beyond the fixed keyword list in
    scripts/spec-compliance-gate.py. Checks whether a technology named in
    the task prompt (react, vue, typescript, etc.) shows up anywhere in
    the files changed this session; proof-gate.py has no equivalent check
    since it only verifies edits are research-backed, not that they
    satisfy what was actually asked for.
    """
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/scripts/spec-compliance-gate.py"'
    hook_entry = {
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "Stop", SPEC_COMPLIANCE_GATE_SENTINEL,
        hook_entry, label="spec-compliance-gate",
    )


# ---------------------------------------------------------------------------
# Step 5i: Configure web search env vars
# ---------------------------------------------------------------------------
def configure_web_search_env() -> None:
    """Set web search configuration env vars in settings.json."""
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})

    env.setdefault("CLEAN_RAG_WEB_SEARCH", "true")
    env.setdefault("CLEAN_RAG_WEB_SEARCH_TIMEOUT", "4.0")
    env.setdefault("CLEAN_RAG_WEB_SEARCH_MAX_RESULTS", "3")
    env.setdefault("CLEAN_RAG_WEB_SEARCH_THRESHOLD", "0.4")

    write_json(SETTINGS_PATH, settings)
    _ok("Web search env vars configured (can be overridden in settings.json)")


# ---------------------------------------------------------------------------
# Step 5k: Configure metrics env vars
# ---------------------------------------------------------------------------
def configure_metrics_env() -> None:
    """Set code quality metrics configuration env vars in settings.json.

    METRICS_CACHE_DIR/TTL are genuinely used by server/metrics.py (real,
    working code behind the code_metrics MCP tool). CLEAN_RAG_METRICS_INJECT
    itself has no remaining consumer — metrics_inject.py was dead code
    (wrong hook signature, confirmed to never actually run) and has been
    removed; git-root auto-index detection was folded into rag-enforce.py.
    """
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})

    env.setdefault("METRICS_CACHE_DIR", "state/metrics-cache")
    env.setdefault("METRICS_CACHE_TTL", "3600")

    write_json(SETTINGS_PATH, settings)
    _ok("Metrics env vars configured (can be overridden in settings.json)")


# ---------------------------------------------------------------------------
# Step 5m: Register code pattern inject hook (PreToolUse) — enforce on Claude
# ---------------------------------------------------------------------------
def register_code_pattern_inject_hook() -> None:
    """Register hook to enforce pattern detection + research before edits.

    This blocks CLAUDE from editing without automatic pattern detection
    and research injection. Non-blocking in background threads.
    """
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/code-pattern-inject.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PreToolUse", CODE_PATTERN_INJECT_SENTINEL,
        hook_entry, label="code-pattern-inject",
    )


# ---------------------------------------------------------------------------
# The research gate. Blocks a code edit unless a research or triage agent has
# actually run and declared that it covered this file.
#
# Prepended, because it should refuse before the other pre edit hooks bother
# doing their searches. No point injecting research context into an edit that
# is about to be blocked anyway.
# ---------------------------------------------------------------------------
def register_research_gate_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/research-gate.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PreToolUse", RESEARCH_GATE_SENTINEL,
        hook_entry, prepend=True, label="research-gate",
    )


# ---------------------------------------------------------------------------
# The other half of the gate: stamps the turn record when a research or triage
# agent finishes. Without this the gate has nothing to check and blocks
# everything, so the two are useless apart.
# ---------------------------------------------------------------------------
def register_research_record_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/research-record.py"'
    hook_entry = {
        "matcher": "Task|Agent",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", RESEARCH_RECORD_SENTINEL,
        hook_entry, label="research-record",
    )


# ---------------------------------------------------------------------------
# Step 5n: Configure code pattern injection environment
# ---------------------------------------------------------------------------
def configure_code_pattern_inject_env() -> None:
    """Enable pattern-based research injection on all Claude edits."""
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})
    env.setdefault("CLEAN_RAG_PATTERN_INJECT", "true")
    write_json(SETTINGS_PATH, settings)
    _ok("Code pattern injection enabled (CLEAN_RAG_PATTERN_INJECT=true)")


def setup_gpu_memory_manager():
    """Configure GPU memory management for embeddings.

    Copies smart_gpu_indexing.py to LocalAI project and configures
    dynamic VRAM allocation based on available GPU memory.
    """
    try:
        # Check if LocalAI project exists
        localai_path = Path.cwd().parent / "LocalAI"
        if not localai_path.exists():
            _warn("LocalAI project not found, skipping GPU memory manager setup")
            return

        # Check if smart_gpu_indexing.py exists locally (in clean-rag)
        gpu_manager_src = CLEAN_RAG_HOME / "smart_gpu_indexing.py"
        if not gpu_manager_src.exists():
            _say("smart_gpu_indexing.py not found in clean-rag directory")
            _say("GPU memory manager must be set up separately in LocalAI project")
            return

        # Verify it exists in LocalAI
        gpu_manager_dst = localai_path / "smart_gpu_indexing.py"
        if gpu_manager_dst.exists():
            _ok("GPU memory manager already installed in LocalAI")
            return

        # Configure Python embedding settings with GPU memory awareness
        try:
            from server.embedding import configure_gpu_aware_embedding
            from server.config import CODE_EMBEDDING_MODEL
            configure_gpu_aware_embedding(CODE_EMBEDDING_MODEL)
            _ok("GPU-aware embedding configured for dynamic batch sizing")
        except Exception as e:
            _say(f"Optional: GPU-aware embedding setup: {e}")
            _say("Embeddings will use CPU fallback if GPU memory is insufficient")

    except Exception as e:
        _warn(f"GPU memory manager setup: {e}")
        _say("Embeddings will still function with CPU fallback")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Install clean-rag")
    parser.add_argument("--skip-deps", action="store_true",
                        help="Skip pip install")
    args = parser.parse_args()

    print("=" * 60)
    print("clean-rag installer")
    print("=" * 60)
    print()

    # Step 1
    print("Step 1: Creating directories...")
    ensure_directories()
    ensure_env_file()

    # Step 1b
    print("\nStep 1b: Installing agents, skills, and the hook launcher into ~/.claude...")
    install_user_assets()

    # Step 2
    if not args.skip_deps:
        print("\nStep 2: Installing dependencies...")
        install_deps()
    else:
        print("\nStep 2: Skipped (--skip-deps)")

    # Step 3
    print("\nStep 3: Registering the research gate...")
    register_research_gate_hook()
    register_research_record_hook()

    # Step 3b
    print("\nStep 3b: Registering graph-context-inject hook...")
    register_graph_context_hook()

    # Step 4
    print("\nStep 4: Setting environment variables...")
    set_env_var()
    protect_research_state()

    # Step 5
    print("\nStep 5: Registering session prompt...")
    register_session_prompt()

    # Step 5b
    print("\nStep 5b: Registering rag-enforce hook...")
    register_rag_enforce_hook()

    # Step 5c
    print("\nStep 5c: Registering reindex hook...")
    register_reindex_hook()

    # Step 5e
    print("\nStep 5e: Setting up GPU memory management...")
    setup_gpu_memory_manager()

    # Step 5f
    print("\nStep 5f: Registering spec-compliance-gate hook...")
    register_spec_compliance_gate_hook()

    # Step 5i
    print("\nStep 5i: Configuring web search environment variables...")
    configure_web_search_env()

    # Step 5k
    print("\nStep 5k: Configuring metrics environment variables...")
    configure_metrics_env()

    # Step 5m
    print("\nStep 5m: Registering code-pattern-inject hook (enforce on Claude)...")
    register_code_pattern_inject_hook()

    # Step 5n
    print("\nStep 5n: Configuring code pattern injection environment...")
    configure_code_pattern_inject_env()

    # Step 6: heal a stale settings.json from an older install. Runs LAST so it
    # sees every hook this run registered, prunes any that point at a deleted
    # script, and wraps the rest through hook-run.py. This is what stops a
    # re-install inheriting a broken hook (research-task-nudge was the real one).
    print("\nStep 6: Healing hook registrations...")
    heal_stale_hooks()

    print()
    print("=" * 60)
    print("clean-rag installed successfully!")
    print()
    print(f"  Home:    {CLEAN_RAG_HOME}")
    print(f"  Hooks:")
    print(f"    PreToolUse:        graph-context-inject.py (auto-fetches caller context)")
    print(f"    PreToolUse:        code-pattern-inject.py (forces research on Edit/Write/MultiEdit)")
    print(f"    UserPromptSubmit:  rag-enforce.py (real-query search, web fallback, git auto-index)")
    print(f"    PostToolUse:       reindex-after-edit.py (keeps index fresh)")
    print(f"  GPU Memory:  smart_gpu_indexing.py (dynamic VRAM allocation)")
    print(f"  Server:  python {CLEAN_RAG_HOME.as_posix()}/cli/server_ctl.py start")
    print()
    print("Start the server to enable RAG-backed research and code quality metrics injection.")
    print("GPU memory manager provides dynamic batch sizing for embeddings.")
    print("=" * 60)


if __name__ == "__main__":
    main()
