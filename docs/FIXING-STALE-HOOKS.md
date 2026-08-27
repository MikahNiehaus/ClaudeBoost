# Fixing stale hooks

Hooks fail quietly. That is the whole problem.

A hook whose script was renamed, or whose prompt names an endpoint you deleted
six months ago, does not raise an error you will see. It just stops protecting
you, or it feeds the model instructions that cannot work. Everything keeps
looking normal, and the damage shows up later as "Claude has been unreliable
lately".

Run this to find out where you stand:

```bash
python scripts/audit-hooks.py
```

It exits 1 when it finds something, so it drops into CI or a pre commit hook
unchanged. `--json` gives machine readable output.

## The four failures it looks for

### 1. A command hook pointing at a script that is missing or broken

The most common cause is a rename or a moved directory. The second most common
is a syntax error introduced while editing the hook itself: the script is right
there, it just cannot run.

Either way Claude Code does not tell you. The hook is registered, it fires, it
fails, and the event proceeds. If that hook was your only guard against some
class of mistake, that guard is gone and nothing said so.

The audit resolves every `.py` path in every hook command, expanding
environment variables the way the hook process will see them, then checks the
file exists and compiles.

### 2. A prompt hook instructing a route the server does not serve

A `type: "prompt"` hook injects text straight into the model's context every
time it fires. That text is treated as instruction. If it says

> Key endpoints: POST /context (load agent context), POST /index (reindex files)

and those routes were removed, then every session begins by being told to call
two endpoints that return 404. The model tries, fails, and works around it. You
see flaky behaviour and blame the model.

The audit probes each route against the live server instead of comparing
against a hardcoded list, so the check cannot itself go stale. A 404 means the
route is gone. A 400 or a 405 means it exists and you simply sent it an empty
body, which is not a fault.

A route named in order to say it is **gone** is correct and is not flagged:

```
There is no /context route; it returns 404.
```

If the server is not running, the audit reports no verdict on routes rather
than declaring all of them dead.

### 3. A prompt hook naming an agent that is not installed

`"Always use evaluator-agent to verify findings"` is worse than useless if
`evaluator-agent` is not in your agents directory. It reads as authoritative,
and the instruction cannot be followed.

The audit reads the installed set from disk (both the user level and the
project level agents directories) rather than assuming which ones exist.

### 4. Mojibake

Text that was UTF-8 encoded and then decoded as cp1252 leaves sequences that
render as garbage. An em dash is the usual victim, because it is the character
most often pasted in from a word processor or a chat client.

It matters more than it looks. The corruption is injected verbatim into context
on every session, and on a Windows console it can raise `UnicodeEncodeError`
when a script merely tries to print it.

## Fixing what it finds

Back up first. `settings.json` is the file that configures everything, and a
bad write is felt immediately:

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak
```

Then edit `~/.claude/settings.json`, or your project's
`.claude/settings.json`, and re-run the audit.

Three things are worth knowing before you write that file by hand.

**Do not let PowerShell add a BOM.** On Windows PowerShell 5.1,
`Set-Content -Encoding UTF8` writes a byte order mark, and it breaks JSON
parsing. Write bytes instead:

```powershell
[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
```

Or edit with a script that writes UTF-8 without a BOM, which is what Python's
`Path.write_bytes` does naturally.

**Match hooks by content, not by position.** If you script the fix, find each
hook by a distinctive substring of its command or prompt and assert that
exactly one matched. Patching by array index silently edits the wrong hook the
first time somebody reorders the file.

**Re-parse after writing.** Read the file back and `json.loads` it before you
walk away. A JSON file that no longer parses disables every hook at once.

## Keeping it from coming back

Run the audit whenever you change hooks, and any time behaviour gets strange
for no reason you can name. It takes a second.

The deeper habit: when you delete a route, rename a script, or remove an agent,
grep your hook config for it in the same change. A hook is config that gives
instructions, so it goes stale exactly like documentation does, except nothing
ever reads it aloud to you.

Two related checks already in this repo:

- `python scripts/check-hooks.py` verifies PreToolUse registration specifically.
- `pytest tests/test_no_machine_specific_paths.py` fails if tracked source
  hardcodes one developer's home directory or one clone's absolute path, which
  is the other way a working setup turns out to work on exactly one machine.

## A note on what belongs in a hook prompt

Hook prompts are the least reviewed text in the whole system. Nobody reads
`settings.json` for pleasure, and its contents reach the model on every single
session. Treat it like source, because that is what it is:

- Keep it short. It is paid for on every event.
- Keep it accurate. A wrong instruction is worse than no instruction, because
  the model will follow it.
- Keep secrets out of it entirely. Hook prompts get pasted into bug reports and
  shared configs. No tokens, no keys, no internal hostnames, no customer names.
- Prefer naming the contract over naming the answer. `POST /search takes
  sources and mode` survives a refactor; a worked example with one project's
  absolute path does not.
