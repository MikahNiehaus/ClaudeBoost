# Global instructions: background notes

Detail moved out of the global CLAUDE.md. Each part keeps a short stub or a
pointer there. The stub holds the rule; this file holds the reasons and
history.

## The research gate: history

The gate used to block the edit. It doesn't now. The first block attempt also
predated the session scoping, so coverage was wiped by every follow-up message
and the gate fired on files swiper had just covered.

The spawn paragraph used to say "spawn it in the foreground
(`run_in_background: false`), never backgrounded". That instruction asked for
something the agent tool does not offer. Its inputs are `description`,
`isolation`, `model`, `prompt` and `subagent_type`, and nothing else;
`run_in_background` is a `Bash` input, not an agent one. Verified 2026-09-18 by
reading the live tool schema.

good-cop's opening used to say the opposite of its repro rule, that its job was
not to re-litigate whether bad-cop's findings were real, while a passage near
the end of the same file told it to disprove false positives. An instruction at
the top of a file outweighs one at the bottom, so the contradiction resolved
the wrong way.

## Recorded decision: no blocking external model reviewer on Stop

Considered and declined, 2026-08-18. The proposal was a Stop hook that shells a
separate model (`claude -p`, `codex exec`, `gemini`) at `git diff HEAD` and
blocks the turn on a FAIL verdict. Do not build it. The reasons, in order of
weight:

- A hard blocking reviewer was already built on this exact surface and reverted
  twice. `clean-rag/hooks/verifier-gate.py` records both reverts in its own
  docstring.
- Anthropic's own `security-guidance` plugin does this, and it only works
  because of three things a hand rolled version has none of: `asyncRewake`
  instead of a synchronous block, a `MAX_STOP_HOOK_FIRINGS` cap, and a
  continuation suffix so the model does not abandon the user's original request
  after being blocked.
- `abiswas97/gemini-plugin-cc` warns in its own README that this class of hook
  "can create a long-running Claude/Gemini loop. Only enable it when actively
  monitoring the session."
- Claude Code re-runs every Stop hook on every Stop event. A new blocking hook
  without a `stop_hook_active` guard loops against `auto-test-gate.py` and
  `stop-context-guard.py`.
- The review responsibility is already owned by bad-cop and good-cop, which are
  fresh context subagents. A second reviewer on the same Stop event duplicates
  or contradicts them.

If the goal ever becomes security specific review, adopt the whole plugin
(`/plugin install security-guidance@claude-plugins-official`,
`SECURITY_REVIEW_MODEL` selects the reviewer) rather than writing a hook. If
only a Stop hook loop guard is wanted for some other purpose,
`hamelsmu/claude-review-loop`'s `stop-hook.sh` is the reference for the retry
and fail open state machine, MIT licensed.

Two corrections to the advice that prompted this, for anyone who reads it later:
the Stop payload carries `transcript_path` but no changed files list, so a hook
must derive that itself with `git status --porcelain`; and launching `claude -p`
from inside a live session requires unsetting `CLAUDECODE` in the child env
(`scripts/chat-watcher.py` does this).

## What the rm rules do, and why they are shaped that way

Reworked 2026-09-16. `rm` is split by whether the command is recursive, because
that is where nearly all of the danger lives. Deleting a named file is ordinary
work; deleting a tree is not.

- **Allowed, no prompt**: non recursive `rm`, such as `rm build.log` or
  `rm -f render/s-01.png`.
- **Ask**: anything recursive. `rm -r*`, `rm -R*`, `rm -fr*`, `rm -fR*`,
  `rm -f -r*`, `rm --recursive*`, and a couple of catch alls for odd flag orders.
- **Deny**: sixteen catastrophic shapes that should never run at all, including
  `rm -rf /`, `~`, `.`, `..`, `$HOME`, `C:*` and the Git Bash drive paths `/c`
  and `/c/*`.

Do not replace this with a single broad `Bash(rm **)` in `ask`. That was the old
shape and it prompted on every scratch file, which trains people to approve
without reading. Do not try to carve a safe directory out of a broad rule
either, because it cannot be done: permission rules evaluate deny, then ask,
then allow, first match wins, and "rule specificity doesn't change the order",
so a narrower `allow` never fires. Bash patterns have no `!` negation; that
exists only for Read and Edit. A PreToolUse hook cannot help either, since "a
matching ask rule still prompts even when the hook returned `allow`". Hooks
tighten, never loosen. All three quotes are from
`code.claude.com/docs/en/permissions.md`.

Splitting on the recursive flag is the one cut that IS expressible, which is
why the rules look like this.

## Plugins: tuning detail

**ponytail** walks this ladder before writing code: does this need to exist,
does the stdlib do it, is there a native platform feature, is it already a
dependency, can it be one line. Validation, error handling, security and
accessibility are never on the chopping block.

**pipe-down** covers 30 plus languages from its own `Lang` table, including
`/* */` blocks, which our extractor does not reach. In
`comment-humanness-check.py` only the dash rule ever blocked.

Two env vars are set for it, with `setdefault` in both installers so a retune
survives a re-run. `PIPE_DOWN_MAX_WORDS` is 20, not its shipped 25, matching
the cap our own hook already used. `PIPE_DOWN_LLM` is `0` because left on it
spawns a `claude -p` Haiku subprocess per write, with a 40 second timeout, to
judge borderline comments. Turn it back on only if the regex rules prove too
blunt.

It fails open on a malformed payload and caps itself at
`PIPE_DOWN_MAX_DENIALS = 2` per file, so it cannot wedge a session. Verified
by driving the real hook rather than reading it: the same 22 word comment is
denied at a cap of 20 and allowed at 25, so the setting does real work.

## Plain writing: why comment-humanness-check was built, not installed

Nothing external covers it. The narration rule is ported from
`no-redundant-comments` in `pertrai1/eslint-plugin-llm-core` (MIT), which is
JS and TS only through ESLint's AST and cannot run against the C# and Python
here. No Roslyn equivalent exists. The port trades the AST for line matching,
so the failure mode to watch is a false positive on a comment that genuinely
explains something; `tests/test_comment_humanness_check.py` pins that
boundary.
