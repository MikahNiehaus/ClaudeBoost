"""
Measure what ClaudeBoost injects into context, per prompt and per session.

Every UserPromptSubmit command hook writes its text into the conversation as
additionalContext. That text is not free once: it stays in the transcript and
gets re-read by every later request in the session, so N prompts worth of a
fixed block costs on the order of N squared to carry. This script gives the
number an objective before and after, so a change to any injector can be shown
to have worked instead of assumed to have.

Usage:
  python3 scripts/measure-injection.py                 human readable table
  python3 scripts/measure-injection.py --json          machine readable
  python3 scripts/measure-injection.py --save FILE     write JSON to FILE
  python3 scripts/measure-injection.py --compare FILE  diff against a saved run
  python3 scripts/measure-injection.py --prompt "..."  drive with a real prompt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_PROMPT = "please refactor the search module and add tests for it"

# Roughly 4 characters per token for English prose. Not exact, but the same
# approximation applies on both sides of a before and after comparison, which
# is all this script is for.
CHARS_PER_TOKEN = 4


def _home() -> Path:
    return Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)


def _settings_files(home: Path) -> list[tuple[str, Path]]:
    return [
        ("global", Path.home() / ".claude" / "settings.json"),
        ("project", home / ".claude" / "settings.json"),
    ]


def _est_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _expand(cmd: str, home: Path) -> str:
    """
    Resolve the shell variables the hook commands are written with.

    CLEAN_RAG_HOME matters as much as CLAUDEBOOST_HOME: clean-rag registers all
    of its own hooks under that variable, so leaving it unexpanded reports every
    one of them as MISSING and silently drops them from the total.
    """
    python = os.environ.get("CLAUDEBOOST_PYTHON") or sys.executable
    clean_rag = os.environ.get("CLEAN_RAG_HOME") or str(home / "clean-rag")
    out = cmd.replace("$CLEAN_RAG_HOME", clean_rag)
    out = out.replace("$CLAUDEBOOST_HOME", str(home))
    out = out.replace("$CLAUDEBOOST_PYTHON", python)
    out = out.replace("$HOME", str(Path.home()))
    return out


def _script_path(cmd: str, home: Path) -> Path | None:
    """
    Pull the .py a hook command actually runs out of its argv.

    Two things have to be skipped: the interpreter, and hook-run.py. clean-rag's
    installer wraps every registration as `<python> hook-run.py <real script>`
    so a missing target no-ops instead of blocking the tool call. Taking the
    first .py in the command would measure the wrapper on every wrapped hook and
    report a uniform zero.
    """
    expanded = _expand(cmd, home)
    hits = re.findall(r'["\']?([^"\'\s]+\.py)["\']?', expanded)
    python = os.environ.get("CLAUDEBOOST_PYTHON") or sys.executable
    real = [
        h for h in hits
        if os.path.normpath(h) != os.path.normpath(python)
        and "hook-run.py" not in h
    ]
    if not real:
        return None
    return Path(real[-1])


def _extract_context(stdout: str) -> str:
    """
    Pull additionalContext out of a hook's stdout.

    Claude Code accepts it at the top level and nested under
    hookSpecificOutput. Plain stdout on UserPromptSubmit is injected as context
    verbatim, so that counts too.
    """
    text = stdout.strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except Exception:
        return text
    if not isinstance(data, dict):
        return text
    ctx = data.get("additionalContext")
    if isinstance(ctx, str):
        return ctx
    nested = data.get("hookSpecificOutput")
    if isinstance(nested, dict) and isinstance(nested.get("additionalContext"), str):
        return nested["additionalContext"]
    return ""


def _run_hook(cmd: str, home: Path, prompt: str, timeout: float = 30.0) -> dict:
    script = _script_path(cmd, home)
    name = script.name if script else cmd[:40]
    row = {"name": name, "command": cmd, "chars": 0, "tokens": 0, "status": "ok"}

    if script is None:
        row["status"] = "unparsed"
        return row
    if not script.exists():
        row["status"] = "MISSING"
        return row
    if script.stat().st_size == 0:
        row["status"] = "EMPTY FILE"
        return row

    env = dict(os.environ)
    env["CLAUDEBOOST_HOME"] = str(home)
    payload = json.dumps({
        "prompt": prompt,
        "session_id": "measure-injection",
        "cwd": str(home),
        "hook_event_name": "UserPromptSubmit",
    })
    python = os.environ.get("CLAUDEBOOST_PYTHON") or sys.executable
    try:
        proc = subprocess.run(
            [python, str(script)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            cwd=str(home),
        )
    except subprocess.TimeoutExpired:
        row["status"] = "TIMEOUT"
        return row
    except Exception as exc:
        row["status"] = f"ERROR {exc}"
        return row

    ctx = _extract_context(proc.stdout)
    row["chars"] = len(ctx)
    row["tokens"] = _est_tokens(ctx)
    row["rc"] = proc.returncode
    return row


def collect(home: Path, prompt: str) -> dict:
    per_prompt: list[dict] = []
    per_session: list[dict] = []

    for scope, path in _settings_files(home):
        if not path.exists():
            continue
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        for event, entries in (settings.get("hooks") or {}).items():
            for entry in entries:
                matcher = entry.get("matcher", "")
                for hook in entry.get("hooks", []):
                    kind = hook.get("type")
                    if kind == "prompt":
                        # Static text the harness injects. Once per event, so it
                        # never compounds the way a per prompt hook does.
                        text = hook.get("prompt", "")
                        per_session.append({
                            "scope": scope,
                            "event": event,
                            "matcher": matcher or "any",
                            "name": "(prompt hook)",
                            "chars": len(text),
                            "tokens": _est_tokens(text),
                            "status": "ok",
                        })
                    elif kind == "command" and event == "UserPromptSubmit":
                        row = _run_hook(hook.get("command", ""), home, prompt)
                        row["scope"] = scope
                        row["event"] = event
                        row["matcher"] = matcher or "any"
                        per_prompt.append(row)

    claude_md = home / "CLAUDE.md"
    md_tokens = _est_tokens(claude_md.read_text(encoding="utf-8")) if claude_md.exists() else 0

    return {
        "prompt": prompt,
        "per_prompt": per_prompt,
        "per_session": per_session,
        "claude_md_tokens": md_tokens,
        "per_prompt_total": sum(r["tokens"] for r in per_prompt),
        "per_session_total": sum(r["tokens"] for r in per_session),
    }


def _table(rows: list[dict], title: str) -> None:
    print(title)
    if not rows:
        print("  (none)")
        return
    width = max(len(r["name"]) for r in rows)
    for r in rows:
        note = "" if r["status"] == "ok" else f"  [{r['status']}]"
        print(f"  {r['name']:<{width}}  {r['scope']:<7}  {r['tokens']:>6} tok  "
              f"{r['chars']:>7} ch{note}")


def report(data: dict) -> None:
    print(f"prompt: {data['prompt']!r}\n")
    _table(data["per_prompt"], "PER PROMPT (compounds across the session)")
    print(f"  TOTAL: {data['per_prompt_total']} tokens on every prompt\n")
    _table(data["per_session"], "PER SESSION (static prompt hooks, injected once per event)")
    print(f"  TOTAL: {data['per_session_total']} tokens\n")
    print(f"CLAUDE.md: {data['claude_md_tokens']} tokens (cached prefix, once per session)")

    n = data["per_prompt_total"]
    if n:
        print()
        print("Carried cost of the per prompt block alone, if nothing else changed:")
        for turns in (20, 40, 60):
            print(f"  after {turns:>2} prompts: {n * turns:>7} tokens sitting in context")


def compare(old: dict, new: dict) -> None:
    o, n = old["per_prompt_total"], new["per_prompt_total"]
    delta = n - o
    pct = (delta / o * 100) if o else 0.0
    print(f"per prompt: {o} to {n} tokens  ({delta:+d}, {pct:+.1f}%)")
    o_s, n_s = old["per_session_total"], new["per_session_total"]
    print(f"per session prompt hooks: {o_s} to {n_s} tokens  ({n_s - o_s:+d})")
    print(f"CLAUDE.md: {old['claude_md_tokens']} to {new['claude_md_tokens']} tokens "
          f"({new['claude_md_tokens'] - old['claude_md_tokens']:+d})")
    if o:
        print()
        print("Carried cost after 60 prompts:")
        print(f"  before: {o * 60} tokens")
        print(f"  after:  {n * 60} tokens")
        print(f"  saved:  {(o - n) * 60} tokens")


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure ClaudeBoost context injection.")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--save", metavar="FILE", help="write the JSON result to FILE")
    ap.add_argument("--compare", metavar="FILE", help="diff against a previously saved run")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT, help="prompt text to drive the hooks with")
    args = ap.parse_args()

    home = _home()
    data = collect(home, args.prompt)

    if args.save:
        Path(args.save).write_text(json.dumps(data, indent=2), encoding="utf-8")

    if args.compare:
        try:
            old = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"could not read {args.compare}: {exc}", file=sys.stderr)
            return 1
        compare(old, data)
        return 0

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        report(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
