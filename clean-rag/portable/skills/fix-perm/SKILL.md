---
name: fix-perm
description: Paste a permission prompt you just hit and get the right rule to stop it recurring. Works out which rule actually fired, proposes the narrowest rule that covers the whole class of safe commands like it, refuses the dangerous broad option the prompt itself offers, tests the proposal against your live settings, and applies it with a backup. Use whenever Claude Code asks for permission and you want that class of command to stop asking. Also for "add a permission", "stop asking me for X", "fix this prompt".
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# /fix-perm

Paste the permission prompt. Get back a rule that is as wide as the safe class
and no wider.

The prompt itself offers you a shortcut and it is usually wrong. In this real
example the offered option was `cd *`, which is both too broad and aimed at the
wrong command entirely:

```
Bash command · from the good-cop agent
  cd /c/<repo>/clean-rag 2>/dev/null; npx --yes pyright ... | tail -20

Ask rule Bash(npx **) overrides auto mode for this command.

❯ 1. Yes
  2. Yes, and don't ask again for: cd *
  3. No
```

`cd` never triggered anything. `npx **` did. Approving `cd *` adds a useless
rule and leaves the prompt firing next time.

## The rules this depends on

All from `code.claude.com/docs/en/permissions`, quoted rather than remembered.

Evaluation order is deny, then ask, then allow, first match wins, and "rule
specificity doesn't change the order". A broad ask beats a narrow allow, so
adding an allow under a matching ask does nothing.

Lists merge across settings files. Your new rule joins the others, it does not
replace them.

`*` matches text including spaces. A trailing ` *` also matches the bare
command. Put the `*` after the fixed words: "Claude Code matches everything
before the first `*` as written, so those words are what limit the rule."

Compound commands split on `&&`, `||`, `;`, `|`, `|&`, `&` and newlines, and "a
rule must match each subcommand independently".

An allow rule does not match past a leading assignment of a variable that is not
on the safe list. Deny and ask do match past it.

**Environment runners are the trap.** Claude Code strips `timeout`, `time`,
`nice`, `nohup`, `stdbuf`, `command`, `builtin` and `noglob` before matching, so
`Bash(npm test *)` already covers `timeout 30 npm test`. It does not strip
`npx`, `devbox run`, `mise exec`, `direnv exec` or `docker exec`. The docs are
explicit:

> Because these tools execute their arguments as a command, a rule like
> `Bash(devbox run *)` matches whatever comes after `run`, including
> `devbox run rm -rf .`. To approve work inside an environment runner, write a
> specific rule that includes both the runner and the inner command, such as
> `Bash(devbox run npm test)`. Add one rule per inner command you want to allow.

## Procedure

### 1. Find the rule that actually fired

The prompt names it on a line like `Ask rule Bash(npx **) overrides auto mode`
or `Deny rule ... blocks`. That line is the answer. Do not infer the rule from
the first word of the command.

If the prompt has no such line, the command matched nothing and fell through to
the default prompt. Then the fix is an allow rule, not a change to an existing
one.

**If a deny rule fired, stop.** Say which deny rule it was and that you are not
loosening it. A deny is someone's deliberate hard block. Offer to explain what
it covers; do not offer to remove it.

### 2. Split the command

Break it on the separators above. Each piece needs its own rule, or the allow
never fires. A pipeline of four commands with three already allowed still
prompts on the fourth.

Report the split before proposing anything. If a piece is a leading variable
assignment, say so: an allow rule will never match past it, and the real fix is
to write the value inline rather than to add a rule.

### 3. Judge each piece

For each subcommand that is not already allowed, decide the cut point.

**Is the binary an environment runner?** `npx`, `bunx`, `uvx`, `pipx run`,
`yarn dlx`, `pnpm dlx`, `devbox run`, `mise exec`, `direnv exec`, `docker exec`,
`docker run`, `kubectl exec`, `ssh`, `wsl`. If yes, the rule must name the inner
command too. `Bash(npx --yes pyright *)`, never `Bash(npx *)`.

**Is the binary an execution wrapper?** `xargs`, `find` with `-exec`, `awk`,
`sed`, `eval`, `sh -c`, `bash -c`, `parallel`, `watch`, `env`, `start`. Do not
widen these. A rule for `find **` is a rule for everything, because `-exec` runs
whatever follows. Propose a rule for the inner command instead, or say the
command should stay a prompt.

**Does it write, delete, install, or reach the network?** `rm`, `mv`, `cp`,
`tee`, a redirect into a file, `pip install`, `npm install`, `curl`, `wget`,
`ssh`, `scp`, anything git that changes the repo. Do not propose an allow.
Propose an ask rule scoped to the exact shape, or leave it alone. Say plainly
that you are refusing to widen it.

**Otherwise** take the longest fixed prefix that still covers the class the user
means, and put ` *` after it. `Bash(pyright *)`, not `Bash(pyright --outputjson
"C:/one/exact/file.py")`, and not `Bash(py* *)`.

### 4. Check the proposal before offering it

Run the checker. It resolves the command against the live merged rule set with
and without your proposed rule, so you find out whether the rule actually fires
rather than assuming it.

```
python ~/.claude/skills/fix-perm/check_rule.py \
  --command '<the full command from the prompt>' \
  --rule '<the rule you propose>'
```

It reports, for every subcommand: what happens today, what happens with the rule
added, and whether a deny or ask rule still wins. A proposal that does not change
the verdict is a proposal that does not work, usually because an ask rule
outranks it. Say so and find the ask rule instead of shipping a rule that does
nothing.

Also ask it what else the rule would let through:

```
python ~/.claude/skills/fix-perm/check_rule.py \
  --rule '<the rule>' --blast
```

That prints a set of commands the rule would newly permit. Read them. If any one
of them would worry you, the rule is too wide.

### 5. Present, then apply

Show the user:

- which rule fired, quoted from their prompt
- the subcommand split, if there was one
- the proposed rule or rules, and which file each goes in
- what else the rule permits, from `--blast`
- anything you refused to widen, and why

Wait for a yes. Then apply with `--apply`, which backs the file up first and
prints the backup path.

Global rules go in `~/.claude/settings.json`. A rule specific to one project
goes in that project's `.claude/settings.local.json`, which is gitignored.
Prefer the project file when the command names a path inside that project.

## What this skill will not do

It will not remove or weaken a deny rule.

It will not propose a bare environment runner, a bare execution wrapper, or a
rule whose first character is `*`.

It will not add a rule for a command that writes, deletes, installs or reaches
the network. Those stay prompts on purpose, and a prompt you see three times a
week is cheaper than one you never see again.

It will not touch `scripts/bash-guard.py` or any hook. Hooks tighten and never
loosen, so a permission rule cannot undo one. If the guard is what blocked you,
the message says so and names the check; that is a different conversation.

## Most of the time the answer is not a rule

This is the part people skip. A permission prompt is a signal that something is
wrong with the command, and widening a rule is only one of the ways to fix it,
usually the worst one. Work through these first, and only reach for a rule when
none of them applies.

**The command cannot work.** Check before proposing anything. A real case:
`npm run test` prompted, and the repo had no `test` script in `package.json`, so
it would have failed with `Missing script: "test"` whatever the rule said. The
fix was the working command, `npx jest <suite>`, not a permission. Run the cheap
check: does the script exist, does the file exist, is the binary installed.

**The prompt came from the command's shape, not its content.** Three shapes
cause most prompts and none of them need a rule:

- a leading `VAR="..."` assignment, because an allow rule never matches past one.
  Write the value inline instead.
- a chain of unrelated commands, because every subcommand must match its own
  rule. Split it into separate calls.
- a redirect that leaves a stray token. `2>&1 |` splits on the `&`, leaving a
  bare `1` that matches nothing and prompts by itself. Even a perfect rule for
  the real command would not have silenced that line.

**The right fix is a narrower command.** If the prompt fired because the command
reached wider than it needed to, tighten the command. A path scoped invocation
beats a rule that permits the untargeted one forever.

**It is a one off.** It will not recur, so nothing needs to change.

### Write it down instead of widening

When the fix is a habit rather than a rule, record it so it stops happening,
then say which file you wrote to and why. Pick by scope:

- **A rule about how to write commands here**, such as never opening with a
  variable assignment, goes in `CLAUDE.md` under the project's existing
  conventions. That is the layer that changes behaviour on every future turn.
- **A fact about this project**, such as "this repo has no `test` script, CI
  runs `npx jest <suite>` directly", goes in memory as a `project` entry, with
  the command that proves it. That is exactly the kind of thing that costs an
  hour the second time nobody remembers it.
- **A correction the human gave you** goes in memory as a `feedback` entry with
  the reason, not just the instruction.

Memory lives at `~/.claude/projects/<project-slug>/memory/`, one fact per file
with frontmatter, plus a one line pointer in `MEMORY.md`. Check for an existing
file covering the same ground and update that rather than adding a duplicate.

Do not write a memory entry for something the repo already records. "The test
command is X" belongs in memory only when the obvious answer is wrong, which is
precisely the case worth saving.

### Say what you did either way

Every run of this skill ends with one of four outcomes, named plainly:

1. a rule, applied, with the backup path
2. no rule, because an ask or deny outranks it, naming the rule that won
3. no rule, because the command was broken or badly shaped, with the working
   command instead
4. no rule, and something written to `CLAUDE.md` or memory, naming the file

Never end with a rule applied and a habit unrecorded. If the same prompt would
fire again tomorrow for the same reason, the skill has not finished.
