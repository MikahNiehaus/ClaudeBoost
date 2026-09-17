# The installer never deletes, so shipped and installed have drifted both ways

- **Kind:** bloat
- **Area:** scripts
- **Found by:** audit of the skill and capability surface, 2026-09-11
- **Why it was not fixed in place:** the fix is a decision about what the
  installer should do on removal, which changes install behaviour for every
  existing user.

## What is there now

`clean-rag/install.py:198-203` copies the shipped tree over the installed one:

```python
shutil.copytree(portable / "skills", CLAUDE_DIR / "skills",
                dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
```

`dirs_exist_ok=True` merges. Nothing is ever removed. So the two trees diverge
in both directions and neither is authoritative.

**Skills.** Shipped at `clean-rag/portable/skills/`, installed at
`~/.claude/skills/`:

| Skill | Shipped | Installed | Effect |
|---|---|---|---|
| `plan-cop` | yes | no | not runnable here |
| `workshop` | yes | no | not runnable here |
| `traps` | no | yes | a fresh install loses it |
| `pr-mp4` | no | yes | a fresh install loses it |
| `code-quality-metrics` | no | no | lives in `.claude/skills/`, repo only |

`plan-cop/SKILL.md:9` says "invoke the `workshop` skill and follow it in full".
Both are shipped and neither is installed, so that dependency is intact in the
source and absent from this machine.

**Agents.** Shipped at `clean-rag/portable/agents/`, installed at
`~/.claude/agents/`. Six files each, and not the same six:

```
shipped:    bad-cop  fact-medic  good-cop  quick-cop  researcher  swiper
installed:  bad-cop  good-cop    quick-cop research-agent researcher swiper
```

`fact-medic` ships and is never installed. `research-agent` is installed and is
not in the shipped tree, so a fresh install does not produce it, yet both
CLAUDE.md files describe it as the agent that reads untrusted web content.

**The drift is not only about which directories exist. Two skills present in
both trees have different content.**

| Skill | Shipped | Installed | Which is ahead |
|---|---|---|---|
| `human-voice` | 467 | 360 | shipped, by 107 lines |
| `skill-from-memory` | 163 | 165 | installed, by 2 lines |

The shipped `human-voice` carries a whole section the installed copy lacks, "The
fact diff: did the rewrite change what it SAYS", along with `scripts/fact_diff.py`
and the line "Pair it with `fact-medic`" at `portable/skills/human-voice/SKILL.md:143`.
The installed copy has none of it, which is why the `fact-medic` reference is
invisible on this machine and the feature is simply absent.

`skill-from-memory` drifts the other way: the installed copy has two lines the
shipped one does not.

That second direction is the dangerous one. `copytree(dirs_exist_ok=True)`
overwrites files. So the next install would correctly repair `human-voice` and
silently destroy whatever those two lines in `skill-from-memory` are.

## Why it is a problem

Every claim about what exists is now machine specific. This audit hit it three
times: a skill that is documented and not installed, an agent referenced by a
skill and not installed, and an agent that works here and would not survive a
reinstall.

The direction that actually loses work is shipped-but-not-installed reversed:
`traps` and `pr-mp4` exist only on this machine. They are not in the repo's
portable tree, so they are not backed up by the install path and a fresh setup
on another machine silently lacks them.

The other direction is quieter and worse to debug. A reader follows a documented
skill, it is not there, and nothing says whether it was removed on purpose or
never installed.

`traps` compounds this with a false claim about itself.
`~/.claude/skills/traps/SKILL.md:17` says "This is what bad-cop does on every
diff", and its frontmatter description repeats it. `~/.claude/agents/bad-cop.md`
contains zero occurrences of the string `traps`. Nothing wires it in.

## What to do instead

Decide what the installer does about removal, then make the trees match.

The narrow version: make `install.py` report what is installed but not shipped,
rather than silently leaving it. A list at the end of a run is enough to catch
this class, and it breaks nothing.

The full version: make the shipped tree authoritative and have the installer
prune what is no longer in it. That is a real behaviour change, because anything
a user added by hand under `~/.claude/skills/` would be removed.

Independently of that decision:

- Add `traps` and `pr-mp4` to `clean-rag/portable/skills/`, or accept that they
  are local only and say so in them.
- Add `research-agent.md` to `clean-rag/portable/agents/`.
- Diff `skill-from-memory`'s two copies and decide which two lines survive,
  before any install run overwrites the installed one.
- Decide `fact-medic`: install it, or delete it and drop the reference at
  `portable/skills/human-voice/SKILL.md:143`. Note the reference exists only in
  the shipped copy, so on this machine nothing points at the missing agent yet.
- Fix the `traps` self description, then either wire it into `bad-cop.md` for
  real or stop claiming it is wired.

Files: `clean-rag/install.py`, the two portable trees, `traps/SKILL.md`,
`human-voice/SKILL.md`.

## What it would break

Pruning would delete anything a user put in `~/.claude/skills/` by hand. On this
machine that is `traps` and `pr-mp4`, which is exactly the work the prune would
destroy, so they have to be shipped before any prune lands.

`plan-cop` depends on `workshop` (`plan-cop/SKILL.md:9`). Installing one without
the other leaves plan-cop with no loop logic of its own.

Installing `fact-medic` adds a seventh agent, which contradicts every count of
six now in `README.md`, `docs/CLAUDEBOOST-REFERENCE.md`,
`docs/USING-CLAUDEBOOST.md` and `.claude/commands/workspace.md`. Deleting it
instead keeps those correct.

## Open questions

Whether `~/.claude/skills/` is meant to be user editable at all. The whole
question of pruning turns on that and nothing in the repo states it. If users
are expected to add their own skills there, an installer must never prune and
the reporting version is the only safe option.

Whether `fact-medic` was meant to ship. It is the only agent in the shipped tree
with no counterpart in the installed one, and the only agent no CLAUDE.md
mentions.
