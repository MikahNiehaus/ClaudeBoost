# Reproducing this setup on another machine

Everything needed is in the repo. Clone it, run the installer, done.

```bash
git clone <repo> ClaudeBoost
python ClaudeBoost/clean-rag/install.py
```

That's it. Below is what the installer actually does and why, so nothing here is
a black box.

## The thing that used to break

Half of what makes clean-rag work does not live in the repo. Claude Code reads
agents from `~/.claude/agents`, skills from `~/.claude/skills`, and hook commands
from `~/.claude/settings.json`. So those pieces have to end up under `~/.claude`,
not in a cloned repo directory.

Before this was wired up, cloning the repo on a new machine gave you a broken
setup: the hooks were registered to run a launcher (`hook-run.py`) that nothing
created, and the research gate would block every edit while waiting for a
`research-agent` and `triage-agent` that didn't exist. Unrecoverable without
knowing the trick.

## How it's fixed

The repo holds the canonical copies under `clean-rag/portable/`:

```
clean-rag/portable/
  hook-run.py                     the branch safety launcher
  agents/research-agent.md        Sonnet, does the actual research
  agents/triage-agent.md          Haiku, cheap NONE/RESEARCH first pass
  skills/research/SKILL.md         the /research on demand skill
  skills/research-routing/SKILL.md  depth vs breadth routing, preloaded by research-agent
```

`install.py` step 1b (`install_user_assets`) copies those into `~/.claude/`. It's
idempotent, and it will NOT overwrite a copy you've edited to be newer than the
repo's, so a local tweak survives a re-run (it prints a warning and skips).

The hook registrations (also written by `install.py`) route every hook through
`~/.claude/hook-run.py`, which now exists because step 1b created it.

## After installing, the setup is

- **Research gate**: every code edit blocked until a research or triage agent has
  run and declared it covered that file (`COVERS:` line). Markdown and non code
  files are exempt.
- **Two agents**: triage (Haiku, cheap, returns NONE for trivial work) and
  research (Sonnet). Neither can write files; their Bash is caged to localhost.
- **Audit log**: hash chained record of every edit and whether research covered
  it. `python clean-rag/cli/audit.py verify`.
- **Server**: headed, single instance on port 8613, auto reindexes every project
  every 60 minutes. `python clean-rag/cli/server_ctl.py start` or double click
  `runragserver.bat`.
- **Branch safety**: `hook-run.py` no ops a missing hook script instead of
  bricking Claude, so switching to a branch that lacks a script is harmless.

## If you edit an agent or skill

Edit the copy under `~/.claude/` to try it live. When it's right, copy it back
into `clean-rag/portable/` and commit, so the repo stays the source of truth and
the next machine gets your change. The installer treats the repo copy as
canonical unless your local copy is newer.

## What is NOT carried over, on purpose

- `~/.claude/settings.json` env vars and permissions that are specific to your
  machine (paths, API config). The installer writes the hook registrations it
  owns, it does not clone your whole settings file.
- Indexed project databases (`clean-rag/databases/_projects/`). Those rebuild
  themselves: index a project once with `/index-project`, and the 10 minute loop
  keeps it fresh.
