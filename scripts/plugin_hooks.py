"""Builds hooks/hooks.json from HOOKS. Run with --check to exit 1 when it is stale."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOKS_JSON = REPO / "hooks" / "hooks.json"

EDITS = "Edit|Write|MultiEdit"
AGENTS = "Agent|Task"

# A plugin agent's agent_type is "claudeboost:bad-cop"; a user agent's is "bad-cop".
SUBAGENT_REVIEWERS = "(^|:)(bad-cop|good-cop)$"

WORKSPACE_PROMPT = (
    "WORKSPACE CREATION CHECK: You are creating a workspace directory. "
    "Before proceeding:\n"
    "1. Call POST http://127.0.0.1:8613/search with "
    "{\"query\":\"<task description>\",\"sources\":[\"project:<abs path>\"],\"mode\":\"both\"} "
    "to find relevant knowledge\n"
    "2. Ensure you have a task ID and will create context.md after this\n"
    "This is the start of complex work. RAG should be active."
)

KILL_PROMPT = (
    "PROCESS KILL SAFETY — STOP and check:\n\n"
    "You are about to run a process-killing command. Broad name-pattern kills "
    "(pkill NAME, killall NAME, Stop-Process -Name NAME, taskkill /IM NAME) "
    "can kill the user's unrelated processes. This has burned the user before.\n\n"
    "REQUIRED:\n"
    "- If you have a specific PID, use it: kill PID, Stop-Process -Id PID, "
    "taskkill /PID pid.\n"
    "- If targeting a container, use the explicit container name: docker stop NAME.\n"
    "- If you have only a name pattern and no PID, STOP and ask the user first. "
    "Never assume it is safe to broad-match.\n\n"
    "Reason: prior incidents where broad kills hit unrelated processes. Specific "
    "PIDs or explicit container names only; never broad name patterns without "
    "explicit user approval."
)

PRESERVE_PROMPT = (
    "CONTEXT PRESERVATION — quality-first routing:\n"
    "1. Agent spawns: call POST http://127.0.0.1:8613/search with "
    "{\"query\":\"...\",\"sources\":[\"project:<abs path>\"],\"mode\":\"both\"}, "
    "route by type (full/standard/lightweight)\n"
    "2. Finding verification: ALWAYS quick-cop, never self-verify "
    "(confirmation bias)\n"
    "3. Decision flow: simple (just do it) vs complex (workspace + agents)\n"
    "4. Rework costs more than ceremony. Do it right the first time."
)

# A matcher like "Bash(pkill*)" is a regex on the tool name and never fires.
MKDIR_WORKSPACE = "Bash(mkdir *workspace*)"
KILL_RULES = ("Bash(pkill *)", "Bash(killall *)", "Bash(*Stop-Process*)", "Bash(*taskkill*/IM*)")

CR_HOOKS = "clean-rag/hooks"
CR_SCRIPTS = "clean-rag/scripts"


def _cmd(event, script, why, matcher=None, base="scripts", timeout=None, status=None):
    return {"event": event, "matcher": matcher, "script": script, "base": base,
            "timeout": timeout, "status": status, "why": why}


def _prompt(event, prompt, why, matcher=None, cond=None, status=None):
    return {"event": event, "matcher": matcher, "prompt": prompt, "if": cond,
            "status": status, "why": why}


HOOKS = [
    _cmd("SessionStart", "compaction-restore.py", "puts working state back after a compaction",
         timeout=5, status="Restoring context after compaction..."),
    _cmd("SessionStart", "workspace-primer.py", "briefs the session on the active workspace",
         timeout=5, status="Loading workspace tier briefing..."),
    _cmd("SessionStart", "rag-session-reset.py", "makes each session recheck the search server",
         timeout=3, status="Resetting RAG sentinel for fresh session verification..."),
    _cmd("SessionStart", "telemetry-session.py", "opens the per session telemetry record",
         timeout=3, status="Opening telemetry session..."),
    _cmd("SessionStart", "session-restore-ledger.py", "lists open sessions so a reboot can reopen them",
         timeout=3, status="Recording session for restore..."),

    _cmd("PreToolUse", "research-gate.py", "nudges when a code edit has no research behind it",
         matcher=EDITS, base=CR_HOOKS),
    _cmd("PreToolUse", "research-gate-bash.py", "same nudge for code written through the shell",
         matcher="Bash", base=CR_HOOKS),
    _cmd("PreToolUse", "graph-context-inject.py", "adds caller context from the import graph before an edit",
         matcher=EDITS, base=CR_HOOKS),
    _cmd("PreToolUse", "code-pattern-inject.py", "adds matching code patterns from the index before an edit",
         matcher=EDITS, base=CR_HOOKS),
    _cmd("PreToolUse", "agent-spawn-gate.py", "checks agent spawns against the search and proposal rules",
         matcher=AGENTS, base=CR_HOOKS),
    _cmd("PreToolUse", "skill-verify-gate.py", "nudges before an action skill while findings are unchecked",
         matcher="Skill"),
    {**_cmd("PreToolUse", "workspace-boost-gate.py", "checks /boost ran before a workspace is created",
            matcher="Bash"), "if": MKDIR_WORKSPACE},
    _prompt("PreToolUse", WORKSPACE_PROMPT, "asks for a search when a workspace is created",
            matcher="Bash", cond=MKDIR_WORKSPACE,
            status="Enforcing RAG lookup on workspace creation..."),
    _cmd("PreToolUse", "tdd-guard.py", "nudges when source changes without a test change",
         matcher=EDITS),
    _cmd("PreToolUse", "bash-guard.py", "blocks dangerous and prompt triggering shell commands",
         matcher="Bash"),
    *[_prompt("PreToolUse", KILL_PROMPT, "stops broad name pattern process kills",
              matcher="Bash", cond=rule, status="Process kill safety check...")
      for rule in KILL_RULES],

    _cmd("PostToolUse", "research-record.py", "records which files a researcher or swiper run covered",
         matcher=AGENTS, base=CR_HOOKS),
    _cmd("PostToolUse", "verifier-record.py", "records which files a reviewer verified",
         matcher=AGENTS, base=CR_HOOKS),
    _cmd("PostToolUse", "verify-gate-cmd.py", "flags agent findings that still need checking",
         matcher=AGENTS, timeout=3, status="Checking agent output for findings..."),
    _cmd("PostToolUse", "context-nudge.py", "nudges when the context is filling up",
         matcher=".*", timeout=3),
    _cmd("PostToolUse", "telemetry-hook.py", "logs each tool call for /telemetry",
         matcher=".*", timeout=3, status="Logging tool call..."),
    _cmd("PostToolUse", "comment-humanness-check.py", "flags machine sounding code comments",
         matcher=EDITS, timeout=5),
    _cmd("PostToolUse", "reindex-after-edit.py", "keeps the search index current after each edit",
         matcher=EDITS, base=CR_HOOKS),
    _cmd("PostToolUse", "verify-after-edit.py", "nudges to run a check after writing code",
         matcher=EDITS, base=CR_HOOKS),
    _cmd("PostToolUse", "record-edit.py", "records edited files so the Stop gates see them",
         matcher=EDITS, base=CR_HOOKS),
    _cmd("PostToolUse", "lint-gate.py", "runs the project linter after code writes",
         matcher=EDITS, base=CR_HOOKS),

    _cmd("SubagentStop", "verifier-record.py", "records a reviewer's stamp when it ran in the background",
         matcher=SUBAGENT_REVIEWERS, base=CR_HOOKS),

    _prompt("PreCompact", PRESERVE_PROMPT, "restates the routing rules before compaction",
            status="Preserving RAG awareness before compaction..."),
    _cmd("PreCompact", "compaction-save.py", "saves working state before compaction",
         timeout=5, status="Saving working state before compaction..."),

    _cmd("UserPromptSubmit", "session-primer.py", "checks the search server at the start of a session",
         timeout=10),
    _cmd("UserPromptSubmit", "speak-stop.py", "stops text to speech when you type", timeout=3),
    _cmd("UserPromptSubmit", "prompt-rules-injector.py", "adds search locations and standing rules to each prompt",
         timeout=5),
    _cmd("UserPromptSubmit", "rag-enforce.py", "runs a real search on each prompt and indexes the repo",
         base=CR_HOOKS),

    _cmd("Stop", "human-voice-guard.py", "blocks banned filler words in replies"),
    _cmd("Stop", "rules-compliance-check.py", "checks each reply against the standing rules"),
    _cmd("Stop", "auto-clear.py", "runs /clear after /clear-safe asks for it"),
    _cmd("Stop", "speak-tts.py", "speaks replies when /speak is on"),
    _cmd("Stop", "spec-compliance-gate.py", "checks a technology named in the task shows up in the change",
         base=CR_SCRIPTS),
    _cmd("Stop", "auto-test-gate.py", "runs the tests and hands back failures before stopping",
         base=CR_HOOKS),
    _cmd("Stop", "verifier-gate.py", "nudges for a fresh review of unverified code", base=CR_HOOKS),

    _cmd("SessionEnd", "session-clear-save.py", "saves a handoff when the session ends"),
    _cmd("SessionEnd", "telemetry-session.py", "closes the telemetry record", timeout=3),
    _cmd("SessionEnd", "session-restore-ledger.py", "takes the session off the restore list", timeout=3),
]

PROMPT_SENTINELS = ("WORKSPACE CREATION CHECK", "PROCESS KILL SAFETY", "CONTEXT PRESERVATION")


def plugin_command(base: str, script: str) -> str:
    """setup.py's _py_cmd fallback chain, rooted at the plugin instead of $CLAUDEBOOST_HOME."""
    launch = (f'"${{CLAUDE_PLUGIN_ROOT}}/clean-rag/portable/hook-run.py" '
              f'"${{CLAUDE_PLUGIN_ROOT}}/{base}/{script}"')
    return (
        f'if command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; then "$CLAUDEBOOST_PYTHON" {launch}; '
        f'elif command -v python3 >/dev/null 2>&1; then python3 {launch}; '
        f'elif command -v python >/dev/null 2>&1; then python {launch}; '
        f'else py {launch}; fi'
    )


def handler(row: dict, command=plugin_command) -> dict:
    if "prompt" in row:
        out = {"type": "prompt", "prompt": row["prompt"]}
    else:
        out = {"type": "command", "command": command(row["base"], row["script"])}
    if row.get("if"):
        out["if"] = row["if"]
    if row.get("timeout"):
        out["timeout"] = row["timeout"]
    if row.get("status"):
        out["statusMessage"] = row["status"]
    return out


def entry(row: dict, command=plugin_command) -> dict:
    group = {"matcher": row["matcher"]} if row["matcher"] else {}
    group["hooks"] = [handler(row, command)]
    return group


def build() -> dict:
    events: dict[str, list] = {}
    for row in HOOKS:
        events.setdefault(row["event"], []).append(entry(row))
    return {
        "description": "ClaudeBoost hooks. Generated by scripts/plugin_hooks.py; edit the table there.",
        "hooks": events,
    }


def render() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def summary_lines() -> list[str]:
    """One line per hook for the installer's Replace or Keep question."""
    lines = []
    for row in HOOKS:
        name = row.get("script") or row["prompt"].split(":")[0].split(" —")[0].lower()
        line = f"{row['event']:<17} {name:<28} {row['why']}"
        if line not in lines:
            lines.append(line)
    return lines


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        current = HOOKS_JSON.read_text(encoding="utf-8") if HOOKS_JSON.exists() else ""
        if current != text:
            print("hooks/hooks.json is stale; run python scripts/plugin_hooks.py", file=sys.stderr)
            return 1
        return 0
    HOOKS_JSON.parent.mkdir(exist_ok=True)
    HOOKS_JSON.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {HOOKS_JSON.relative_to(REPO).as_posix()} ({len(HOOKS)} hooks)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
