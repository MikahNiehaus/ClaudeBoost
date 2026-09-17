# Two dead files in scripts/, one empty and one never wired up

- **Kind:** bloat
- **Area:** scripts
- **Found by:** audit of the skill and capability surface, 2026-09-11
- **Why it was not fixed in place:** neither crosses the bar. Both should just
  be dealt with. Filed so the second one gets a decision rather than a delete,
  because it is a working feature nobody connected.

## What is there now

```
scripts/research-task-nudge.py        0 bytes
scripts/telemetry-skill-hook.py    1378 bytes, registered nowhere
```

**`research-task-nudge.py` is empty.** Zero bytes on disk.
`clean-rag/DEPRECATION_PLAN.md:80-83` schedules it for removal under "Phase 1:
safe now, clearly redundant, no decision needed", together with "its install
block in `setup.py:820-823`, and its test".

Most of that is already done, and the plan has not caught up. `setup.py` has no
install block for it any more, only a comment at line 953 recording the removal:

```python
# research-task-nudge removed: the /research-task command it advertised was
# retired in favor of the clean-rag research setup.
```

There is no test for it either. So the plan names two artifacts that are gone
and points at a line range that no longer holds what it says.

What is left is the empty file. `clean-rag/install.py:612` and `:1395` mention
it, both as a cautionary example of what a stale registration does, not as a
caller.

**`telemetry-skill-hook.py` is finished and connected to nothing.** It tracks
`/skill-name` invocations into `skill-invocations.jsonl` and imports the shared
`telemetry_writer.py` correctly. It appears in neither `~/.claude/settings.json`
nor `.claude/settings.json`, count 0 in both.

It is also absent from `DEPRECATION_PLAN.md`, unlike the empty file. So it is
not a thing being retired. It is a thing that was built and never plugged in.

## Why it is a problem

The empty file is the sharper risk, and the reason is specific to how hooks
fail. A PreToolUse hook whose script is missing makes python exit 2, and Claude
Code reads exit 2 from PreToolUse as "block this tool call". That is why this
repo keeps deliberate stubs: `clean-rag/hooks/proof-gate.py` and
`clean-rag/hooks/rag-search-on-edit.py` both `sys.exit(0)` and both explain in
their own docstrings that deleting them would brick a machine whose settings
still point at them.

An empty file is not a stub. It exits 0 by having nothing to run, which happens
to be safe, but it reads as an accident rather than a decision, and the next
person to see a zero byte file will either delete it or fill it in.

The telemetry hook is a milder waste: a maintained file paying review and
migration cost while producing nothing.

## What to do instead

Delete the empty `research-task-nudge.py`. Its install block and test are
already gone, so that is the whole remaining step.
`install.py:607`'s `heal_stale_hooks()` prunes registrations pointing at deleted
scripts, which is the mechanism that makes it safe.

Then correct `DEPRECATION_PLAN.md:80-83`, which still instructs a reader to
remove an install block at `setup.py:820-823` that is not there. A plan that
describes finished work as pending is the same defect this audit found in the
commands, in the file that exists to track the cleanup.

Decide `telemetry-skill-hook.py`. Register it if skill invocation telemetry is
wanted, since `/telemetry` already exists to read this class of data. Delete it
if not. Leaving it is the only option with no upside.

Files: `scripts/research-task-nudge.py`, `scripts/setup.py`,
`scripts/telemetry-skill-hook.py`, one settings file if it is registered.

## What it would break

Nothing calls either file.

For the empty one, the branch safety concern that keeps the other stubs alive
applies in reverse: it has no registration in either settings file now, so there
is no hook pointing at it to break. Check a second machine's settings before
deleting if one exists, since that is the exact failure the stubs guard against.

Registering the telemetry hook adds a process to UserPromptSubmit, which this
audit has just shown is the most expensive event in the system at 8.24 seconds.
It measured 0.13s in isolation, so the cost is small, but it is not zero and
that event is the wrong one to add to casually.

## Open questions

Whether `scripts/` should have a test that fails when a file is empty or when a
hook shaped script has no registration. This audit found both by hand. The same
class already produced `action-gate.py`, which is unregistered on purpose and
recorded as such, so a naive check would flag it. Any such test needs an
allowlist, and an allowlist is the thing that rots.
