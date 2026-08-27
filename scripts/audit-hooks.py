"""Audit registered hooks for the failures that stay invisible until they bite.

Run it:

    python scripts/audit-hooks.py            # report
    python scripts/audit-hooks.py --json     # machine readable

Exits 1 when it finds a problem, so it works in CI or a pre commit hook.

What it checks, and why each one was worth writing
--------------------------------------------------
1. **Command hooks point at a script that exists and compiles.** A hook whose
   script is missing or has a syntax error fails on every single event, and
   Claude Code does not surface that. The protection you think you have is
   simply absent, and nothing tells you.

2. **Prompt hooks do not instruct a route the server does not serve.** A
   `type: "prompt"` hook injects text into the model's context every time it
   fires. If that text names an endpoint that was deleted, the model is told to
   call it on every session, gets a 404, and the failure looks like the model
   being unreliable rather than the config being stale. Routes are probed
   against the live server rather than compared to a hardcoded list, so this
   check does not itself go stale.

3. **Prompt hooks do not name an agent that is not installed.** Same failure
   shape: "always use X-agent" is useless advice if X-agent is not in the
   agents directory. The installed set is read from disk, not assumed.

4. **No mojibake.** Text that has been UTF-8 encoded and then decoded as
   cp1252 leaves sequences that render as garbage. It is injected verbatim into
   context on every session, and on a Windows console it can even raise
   UnicodeEncodeError when you try to print it.

Nothing here is specific to one machine or one checkout. Paths come from
Path.home() and from this file's own location.
"""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_FILES = [
    CLAUDE_DIR / "settings.json",
    REPO_ROOT / ".claude" / "settings.json",
    REPO_ROOT / ".claude" / "settings.local.json",
]

#: Sequences left behind when UTF-8 bytes are decoded as cp1252. The first is a
#: double encoded em dash, by far the most common because an em dash is the
#: character people paste most often from a word processor.
MOJIBAKE = ["â€”", "â€™", "â€œ", "Â ", "�", "\x9d"]

#: A route is only recognised where it is unambiguously one: directly after the
#: server URL, or directly after an HTTP verb.
#:
#: The obvious pattern, "any /word in the text", does not work. Measured on this
#: repo's own hooks it reported /127 (from inside 127.0.0.1), plus /state,
#: /error, /logging and /validation lifted out of file paths and ordinary prose.
#: Eleven findings, all false. An audit that cries wolf gets ignored, which is
#: worse than not having one.
ROUTE_AFTER_VERB = re.compile(r"\b(?:POST|GET|PUT|PATCH|DELETE)\s+(/[a-z0-9][a-z0-9-]*)")

#: A prompt naming a route to say it is GONE is correct, not a fault. These
#: read as documentation rather than instruction.
NEGATION_NEAR = ("there is no", "was removed", "were removed", "returns 404",
                 "no longer", "does not exist", "deleted")


def _load_settings() -> list[tuple[Path, dict]]:
    found = []
    for path in SETTINGS_FILES:
        if not path.exists():
            continue
        try:
            # utf-8-sig: a BOM is common on Windows and json.loads rejects it.
            found.append((path, json.loads(path.read_text(encoding="utf-8-sig"))))
        except (OSError, ValueError) as e:
            found.append((path, {"__error__": f"{type(e).__name__}: {e}"}))
    return found


def _expand(text: str, env: dict) -> str:
    out = text
    # Longest first, so a short key does not eat a longer one that starts with it.
    for key in sorted(env, key=len, reverse=True):
        out = out.replace(f"${{{key}}}", env[key]).replace(f"${key}", env[key])
    home = str(Path.home())
    for name in ("HOME", "USERPROFILE"):
        out = out.replace(f"${{{name}}}", home).replace(f"${name}", home)
        out = out.replace(f"%{name}%", home)
    return out


def _installed_agents() -> set[str]:
    """Agent names available to spawn, read from disk rather than assumed."""
    names = set()
    for base in (CLAUDE_DIR / "agents", REPO_ROOT / ".claude" / "agents"):
        if base.is_dir():
            names |= {p.stem for p in base.glob("*.md")}
    return names


def _live_routes(base_url: str, candidates: set[str]) -> tuple[set[str], set[str]]:
    """Split *candidates* into (alive, dead) by asking the server.

    404 means the route does not exist. Anything else, including 400 for a bad
    payload and 405 for the wrong method, means it does. A server that is down
    yields no verdict at all, which is reported rather than guessed at.
    """
    alive, dead = set(), set()
    for route in sorted(candidates):
        req = urllib.request.Request(
            base_url.rstrip("/") + route,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=3)
            alive.add(route)
        except urllib.error.HTTPError as e:
            (dead if e.code == 404 else alive).add(route)
        except Exception:
            # Server unreachable. Say nothing rather than call every route dead.
            return set(), set()
    return alive, dead


def _server_url(text: str) -> str | None:
    m = re.search(r"https?://127\.0\.0\.1:\d+|https?://localhost:\d+", text)
    return m.group(0) if m else None


def _mentions_as_gone(prompt: str, route: str) -> bool:
    """Is *route* named only to say it is gone?"""
    for line in prompt.splitlines():
        if route in line:
            low = line.lower()
            if not any(n in low for n in NEGATION_NEAR):
                return False
    return True


def audit() -> tuple[list[dict], dict]:
    problems: list[dict] = []
    stats = {"settings_files": 0, "hook_entries": 0, "scripts": 0, "prompts": 0}

    agents = _installed_agents()
    script_cache: dict[str, bool] = {}
    loaded = _load_settings()

    # One merged environment, not one per file. A project level settings.json
    # usually has no env block of its own, yet its hook commands still reference
    # $CLAUDEBOOST_HOME, which is defined in the global file. Expanding per file
    # leaves those unexpanded and reports every one of them as a missing script.
    # The real process environment wins last, because that is what actually runs.
    #
    # Order: the ambient process environment is the base, and a settings `env`
    # block overrides it. That is the direction Claude Code itself applies them,
    # so auditing the other way round would resolve a path the hook will never
    # actually see.
    merged_env: dict[str, str] = {k: v for k, v in os.environ.items() if v}
    for _p, d in loaded:
        if isinstance(d, dict):
            merged_env.update({k: str(v) for k, v in d.get("env", {}).items()})

    for path, data in loaded:
        stats["settings_files"] += 1
        if "__error__" in data:
            problems.append({"kind": "UNPARSEABLE SETTINGS", "where": str(path),
                             "detail": data["__error__"]})
            continue

        env = merged_env

        for event, matchers in data.get("hooks", {}).items():
            for matcher in matchers:
                pattern = matcher.get("matcher", "")
                for hook in matcher.get("hooks", []):
                    stats["hook_entries"] += 1
                    where = f"{path.name} :: {event} matcher={pattern!r}"

                    prompt = hook.get("prompt")
                    if prompt:
                        stats["prompts"] += 1
                        _check_prompt(prompt, where, agents, problems)
                        continue

                    command = hook.get("command", "")
                    if not command:
                        problems.append({"kind": "EMPTY HOOK", "where": where,
                                         "detail": "no command and no prompt"})
                        continue

                    for script in _scripts_in(command, env):
                        if script in script_cache:
                            continue
                        script_cache[script] = True
                        stats["scripts"] += 1
                        _check_script(script, where, problems)

    return problems, stats


def _scripts_in(command: str, env: dict) -> set[str]:
    """Every .py path named in a hook command.

    A ClaudeBoost hook command is an if/elif shell chain that names its script
    several times to pick an interpreter, so this dedupes rather than reporting
    the same file four times.
    """
    found = set()
    for m in re.finditer(r'["\']?((?:[A-Za-z]:|\$\{?[A-Za-z_]+\}?|%[A-Za-z_]+%)[^"\'\s]*?\.py)["\']?', command):
        found.add(_expand(m.group(1), env).strip("\"'"))
    return found


def _check_script(script: str, where: str, problems: list[dict]) -> None:
    path = Path(script)
    if not path.exists():
        problems.append({"kind": "MISSING SCRIPT", "where": where, "detail": script})
        return
    try:
        py_compile.compile(
            str(path),
            cfile=os.path.join(tempfile.gettempdir(), "audit_hooks_check.pyc"),
            doraise=True,
        )
    except py_compile.PyCompileError as e:
        problems.append({"kind": "SYNTAX ERROR", "where": where,
                         "detail": f"{script}: {e}"})


def _check_prompt(prompt: str, where: str, agents: set[str],
                  problems: list[dict]) -> None:
    for bad in MOJIBAKE:
        if bad in prompt:
            problems.append({
                "kind": "MOJIBAKE",
                "where": where,
                "detail": f"contains {bad.encode('unicode_escape').decode('ascii')}; "
                          f"text was UTF-8 encoded then decoded as cp1252",
            })
            break

    # Agents. Only flag a name shaped like an agent that is genuinely absent,
    # so ordinary prose is not dragged in.
    # Zero or more inner hyphens, not one or more. Requiring one missed the
    # plain single word case, which is most of them: evaluator-agent,
    # architect-agent, debug-agent.
    for name in set(re.findall(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)*)-agent\b", prompt)):
        candidate = f"{name}-agent"
        if candidate not in agents:
            problems.append({"kind": "UNKNOWN AGENT", "where": where,
                             "detail": f"{candidate} is not installed; have: "
                                       f"{', '.join(sorted(agents)) or '(none)'}"})
    for candidate in set(re.findall(r"\b([a-z]+-cop)\b", prompt)):
        if candidate not in agents:
            problems.append({"kind": "UNKNOWN AGENT", "where": where,
                             "detail": f"{candidate} is not installed"})

    base = _server_url(prompt)
    if not base:
        return
    candidates = set(ROUTE_AFTER_VERB.findall(prompt))
    # Also anything written directly onto the server URL.
    candidates |= set(re.findall(re.escape(base) + r"(/[a-z0-9][a-z0-9-]*)", prompt))
    if not candidates:
        return
    alive, dead = _live_routes(base, candidates)
    if not alive and not dead:
        return  # server down; no verdict
    for route in sorted(dead):
        if _mentions_as_gone(prompt, route):
            continue
        problems.append({"kind": "DEAD ROUTE", "where": where,
                         "detail": f"{base}{route} returns 404 but the prompt "
                                   f"instructs using it"})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="machine readable output")
    args = ap.parse_args()

    problems, stats = audit()

    if args.json:
        print(json.dumps({"problems": problems, "stats": stats}, indent=2))
        return 1 if problems else 0

    print(f"settings files : {stats['settings_files']}")
    print(f"hook entries   : {stats['hook_entries']}")
    print(f"command scripts: {stats['scripts']}")
    print(f"prompt hooks   : {stats['prompts']}")
    print()

    if not problems:
        print("No problems found.")
        return 0

    print(f"PROBLEMS: {len(problems)}")
    for p in problems:
        print(f"  [{p['kind']}] {p['where']}")
        print(f"      {p['detail']}")
    print()
    print("See docs/FIXING-STALE-HOOKS.md for what each finding means.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
