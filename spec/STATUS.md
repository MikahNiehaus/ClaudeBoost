# Status

Where every spec item stands. Updated when an item moves, not on a schedule.

## Open, waiting on a human decision

| Item | The decision |
|---|---|
| [bloat/scripts-boost-command-surface](bloat/scripts-boost-command-surface.md) | Does anyone want a hard block on workspace creation? Its health check targets a deleted port, which is settled debt, but `workspace-boost-gate.py` is a live `exit 2` wired into `settings.json`. |
| [bloat/hooks-reading-a-port-number-imports-torch](bloat/hooks-reading-a-port-number-imports-torch.md) | **DONE 2026-09-16, moved to the Done table below.** Left here only so the audit items that cite its 18.4s headline are not read as current. |
| [bloat/commands-share-a-broken-index-preflight](bloat/commands-share-a-broken-index-preflight.md) | Should the preflight exist at all? Nine commands open with it, it reads a `/status` field the server does not return, and its remedy calls a skill that does not exist. Both halves have been dead for some time and nothing noticed. |
| [bloat/commands-rag-surface-targets-the-deleted-server](bloat/commands-rag-surface-targets-the-deleted-server.md) | Delete `/rag` and `/index-boost`, and rewrite or delete `/rag-health`? All three drive the 8612 server. `/rag` names two scripts that are not on disk, and both CLAUDE.md files tell people to run it when search breaks. |
| [bloat/commands-reimplement-each-other](bloat/commands-reimplement-each-other.md) | Which of `/xray` and the cop loop is authoritative for "review my diff"? `/xray` emits a letter grade and zero `VERIFIED:` lines, so it satisfies no gate, and nothing says so. Separately: `/workspace` should call `/graph` rather than pasting it. |
| [bloat/install-drift-between-shipped-and-installed](bloat/install-drift-between-shipped-and-installed.md) | Should the installer prune? It only ever merges, so shipped and installed have drifted both ways: `plan-cop` and `workshop` ship and are not installed, `traps` and `pr-mp4` are installed and do not ship. Turns on whether `~/.claude/skills/` is user editable, which nothing states. |
| [bloat/agents-bad-cop-carries-two-agents-in-one-file](bloat/agents-bad-cop-carries-two-agents-in-one-file.md) | Split Mode B out? bad-cop is 1255 lines holding two disjoint agents with disjoint stamps, and every spawn loads both. The cost is changing a `MODE:` string to an agent name at each call site. |
| [bloat/scripts-two-dead-files-in-the-hook-directory](bloat/scripts-two-dead-files-in-the-hook-directory.md) | Register `telemetry-skill-hook.py` or delete it? It is finished, imports the shared writer correctly, and is registered in neither settings file. `research-task-nudge.py` is 0 bytes and `DEPRECATION_PLAN.md` already schedules its removal. |
| [bloat/instruction-files-pay-reference-material-every-turn](bloat/instruction-files-pay-reference-material-every-turn.md) | Move the recorded decisions out of the file that loads every turn? Also corrects the Model Routing line, which names three agents that do not exist and is triplicated across the three CLAUDE.md copies. |
| [architecture-addons/agents-quick-cop-trigger](architecture-addons/agents-quick-cop-trigger.md) | quick-cop's dispatch has no mechanical anchor, unlike the research and verifier gates. Confirmed in the live session: six completion claims, zero dispatches. The fix is a new hook. |
| [architecture-changes/agents-bad-cop-capability-model](architecture-changes/agents-bad-cop-capability-model.md) | bad-cop has `Write`, `Edit` and general Bash with no hook on any of them. Every other agent is caged. swiper has researched the fix down to a clone-and-patch from three existing files. |
| [architecture-addons/agents-good-cop-can-weaken-the-tests-that-judge-it](architecture-addons/agents-good-cop-can-weaken-the-tests-that-judge-it.md) | Who runs the test-diff check, good-cop or bad-cop's re-check? `good-cop.md:410-415` authorises it to rewrite the tests its own stamp rests on, and nothing records that it did. The mutation endpoint is the only backstop and covers three runners, though `mutation.py`'s dispatch takes a new stack in one branch, so widening it may be the cheaper fix. Companion to the bad-cop capability row above. |
| [architecture-addons/hooks-verify-loop-has-no-round-cap](architecture-addons/hooks-verify-loop-has-no-round-cap.md) | How many rounds is too many, and does the cap nudge or block? `MAX_BLOCKS_PER_SESSION = 6` counts Stop nudges and resets on any round that ends in a stamp, so a loop making apparent progress is unbounded. `workshop/SKILL.md:247-273` already caps its own loop at three normal, five stop and ask. `maxTurns` does not reach across `Task` calls and is unenforced anyway (`anthropics/claude-code#41143`). |
| [architecture-changes/docs-instruction-file-duplication](architecture-changes/docs-instruction-file-duplication.md) | Six instruction documents exist in two copies each and drift in both directions. `install.py` syncs them but skips silently once either side is hand edited. |
| [architecture-changes/opencode-research-gate-block-policy](architecture-changes/opencode-research-gate-block-policy.md) | The OpenCode gate throws an unbounded blocking error with no session cap, the enforcement shape the Python side tried and reverted twice. |
| [architecture-changes/server-docs-ingest-topic-kb-reincarnation](architecture-changes/server-docs-ingest-topic-kb-reincarnation.md) | `/docs-ingest` and `docs_store.py` are a persistent topic-scoped document pipeline, the same shape as the topic KB that was deleted on measured evidence. Undocumented in the file that records that decision. |
| [architecture-addons/server-exec-route-capability-boundary](architecture-addons/server-exec-route-capability-boundary.md) | `/index-project` still takes its path from a request body, so index-then-execute survives. **Measured at 0.605 seconds with `files_indexed=0`**, so the indexing step is not a meaningful cost. |
| [bloat/scripts-duplicate-csharp-benchmark-downloaders](bloat/scripts-duplicate-csharp-benchmark-downloaders.md) | Two unreferenced scripts write the same output file two different ways. Which to keep needs provenance judgement. |
| [architecture-addons/lint-159-suppressions-for-a-linter-that-never-runs](architecture-addons/lint-159-suppressions-for-a-linter-that-never-runs.md) | Adopt ruff or delete the comments? 159 `# noqa:` suppressions sit in 86 tracked files (115 E402, 38 BLE001), no lint config is tracked, and ruff is not installed, so every one is inert. `BLE001` is the only mechanical check that would enforce the blocker-severity logging rule both CLAUDE.md copies already state. Do not adopt it expecting bugs: measured the same day, installed static tools caught 0 of 9 real findings. |
| [architecture-changes/hooks-shell-guard-denylist-ceiling](architecture-changes/hooks-shell-guard-denylist-ceiling.md) | quick-cop's guard is a denylist whose docstring describes an allowlist, so an unrecognized command is allowed. Invert it, keep verify-loop as a denylist, do not adopt `bashlex`. Needs a measurement of what quick-cop actually runs before the allowlist can be written. |

## Done

| Item | What happened |
|---|---|
| Reading a port number no longer imports torch | `DEVICE = _detect_device()` at module scope became `get_device()`, resolved on first use and `@functools.cache`d. Re-measured warm on the same machine: `import server.config` 4.7s to **0.19s**, the six per-edit hooks together 18.4s to **2.15s**. Read those as warm. The same six cold, on a session's first edit, are 5.72s, because filesystem cache and bytecode compilation dominate what is left. A bare interpreter start is 0.07s, so about a third of the remainder is process startup nothing in that file can reach. The file's open question, whether the constants should live in a module with no runtime behaviour at all, is untouched and still stands. |
| `/register-project` removed | It wrote the project registry from a request body with no auth, which was the precondition for a remote code execution. No callers; a `state/proof-log.jsonl:74` entry from 2026-07-06 records it was built for the deleted 8612 server. Removed 2026-09-07, verified 404 on the live server after restart. |
| `scripts/telemetry-writer.py` deleted | Eight lines, its own docstring said "not used and can safely be deleted". Zero references repo-wide, confirmed independently three times. Deleted 2026-09-08. |
| Hook state corruption under concurrency | `_write_lock` in `research_state.py` was a `nullcontext`, importing a real lock from a `mcp-rag-server/` directory that does not exist. Reproduced on a scratch tree: 8 processes wrote a **torn** state file (`JSONDecodeError`) and forked the audit chain (151 of 200 entries, 60 breaks). Fixed with three mechanisms, not one, because it was three bugs: a real `O_CREAT\|O_EXCL` lock, `os.replace` atomic writes, and verify-then-retry on stamps. The atomic write is what fixes the reproduced symptom; a lock alone would not, because the reader takes no lock. Now 160/160 stamps and 200/200 entries, chain intact. |
| Five hooks crashed on payload shapes their docstrings excluded | `json.loads` accepts any JSON value, so `null` or a bare list reached `.get()`. Exit 1 is a crash, not a block, so the failure was silent. Fixed at the root (shape check) plus the wrapper as backstop. 420 runs across 20 scripts and 21 shapes: `{0: 396, 2: 24}`, zero ones. The 24 are Bash guards failing closed, which is their contract. |
| MCP server died on one malformed line | `clean-rag/mcp/opencode_mcp_server.py` called `.get()` on a non-dict. One bad line killed a long-lived server. Now answers `-32600` and continues. |
| `code_metrics` called a route that does not exist | Called `POST /metrics`, which 404s. Now an in-process call to `server.metrics.get_metrics()`. |
| PowerPoint visuals rule | The skill now says mermaid for explanation, annotated screenshots for proof, and that a slide asserting something happened while showing only a diagram of it carries no evidence. The screenshot half swipes `walkthrough/SKILL.md`'s driver.js highlight and callout badge rather than restating them. Both artifacts go in the narration section's scratch directory. |
| PowerPoint helper: installed copy had no mermaid support | The installed `pptx_env.py` was 11645 bytes against the portable 18550 and lacked all four mermaid functions, while the skill text names the installed path. Any user following the documented command would have hit a missing command. Function sets diffed first to confirm the installed copy was a strict subset, then synced. Its CLI docstring also never listed `browser`, `mermaid` or `ffprobe`, all three implemented. |
| `clean-rag/install.py` crashed at import on Python 3.9 | Three PEP 604 unions at lines 271, 499 and 552. Fixed with `from __future__ import annotations`, commented with the crash rather than with house style, since the import is present in only 127 of 300 tracked `.py` files. Verified: `py -3.9` imports and runs `--help` at exit 0, and the default interpreter is unchanged. |
| `triage-agent.md`, `verifier-agent.md` deleted | Both orphaned in `~/.claude/agents/`. `clean-rag/CLAUDE.md:39` already documented triage-agent as removed; the file had never been deleted. verifier-agent was unreferenced by any CLAUDE.md, ended with `VERDICT:` rather than `VERIFIED:`, and so satisfied no gate while reading like a review. Deleted 2026-09-07 with the human's approval. |

## The shell guard surface: four rounds, four different classes

Worth recording as a pattern, because no single round's report shows it. The
guards that cage bad-cop, good-cop and quick-cop have been fixed four times, and
each round found a genuinely different defect rather than a variation of the
previous one:

| Round | The defect | The layer it modelled |
|---|---|---|
| 1 | `shlex` does not split on an unspaced `;` `\|` `&`, so `true;git push` fused into one token | operator delimitation |
| 2 | an escaped quote inside `$'...'` or `"..."` mislocated where the span ENDS | quote termination |
| 3 | the span ended correctly, but `"$(git push)"` inside it is executed by the shell and copied through as inert data | what is executable inside a span |
| 3b | `git -C <path> commit` walked past a loop that skips flags but not their values | argument structure |

Every round passed its own tests. Rounds two and three each killed every mutant
they wrote. Round three brute-forced two million strings to prove one mutant
equivalent. None of that prevented the next layer from being exposed.

Two observations follow, and the second is the one that matters:

**Command substitution is not an exotic input.** `echo "$(git push origin main)"`
is ordinary syntax that a shell executes and both guards allowed. The remaining
unmodelled layers, parameter expansion, process substitution, `eval`, here-docs,
are equally ordinary.

**The approach has a ceiling, and it is not where it looked.** Round two's own
report said "a regex denylist over a shell cannot be complete". Round four
answered where the incompleteness actually lives, in
[architecture-changes/hooks-shell-guard-denylist-ceiling](architecture-changes/hooks-shell-guard-denylist-ceiling.md):
not in the grammar. A shell parser would have closed rounds one to three and
none of round four, because a value-taking flag is per-binary semantics rather
than syntax, and `eval "$x"`, `sh -c "$x"` and `G=git; $G push` all parse
perfectly and were all measured as ALLOW against the fixed guard. The
recommendation is to invert quick-cop to an allowlist, leave verify-loop a
denylist because bad-cop and good-cop genuinely need broad Bash, decline
`bashlex`, and put a push restriction on the remote where a string parser cannot
be talked out of it. Which of those to do is the human's call.

Worth keeping in proportion: these guards protect against an agent's mistake, not
a determined attacker with a shell. The agent they cage is one this project runs
on purpose. That is why the honest ceiling matters more than the next patch.

## The 8612 sweep: done, and what it cost

Port 8612 was a second RAG server. It was deleted and nothing swept what named
it. That single unfinished removal produced **five** separate live defects, four
of which are now closed:

1. `/register-project` survived, writing the project registry from any request,
   which became the precondition for a remote code execution. Route removed.
2. Eight sites injected instruction text into every session steering the model at
   the dead port, six of them at `POST /context`, a route with no successor.
   Repointed or deleted per site.
3. `scripts/rag-index-safe.py` POSTed to `8612/index` with an unconditional
   `force: true`. Nothing referenced it. Deleted rather than repointed, because
   repointing would have created a live 30-plus-minute reindex entry point that
   nothing calls.
4. `scripts/boost-run.py:38 PORT = 8612`, so `/boost verify` can never report a
   healthy system. **Still open**, held behind the boost decision above.
5. `scripts/uninstall.py:472 stop_rag_server()` silently does nothing: it shells
   a script whose process pattern matches nothing. **Still open.**

**A sixth defect the sweep exposed, worse than any of the above.**
`scripts/session-primer.py` read `rag_status['indexed_projects']`, the retired
server's key. The live server returns `projects.entries`. So every session was
told `CODEBASE NOT INDEXED - run index-project as your FIRST action` for
projects that were fully indexed. Verified against the live server: there is no
`indexed_projects` key, and `projects.entries` holds 12 entries.

Its two tests could not catch it. They asserted
`"READY" in result or "task-codebase" in result`, and the workspace id is always
present, so the right side made the assertion vacuous.

**What now stops it recurring.** `clean-rag/tests/test_skill_rag_routes.py` was
extended from `.claude/commands/` markdown to the runtime string literals of
`scripts/`, `clean-rag/hooks/` and `clean-rag/server/`, checked against the live
aiohttp router. Docstrings and comments are exempt by construction, so the
historical record of the retirement survives without an allowlist. Proven
non-vacuous by reintroducing the dead port and watching two tests go red.

The pattern is the finding, not any one item: **a subsystem was deleted without a
sweep of what named it.** Worth a check the next time anything is removed.

## The `evaluator-agent` sweep: done, and it was hiding two live defects

`evaluator-agent` was named in 25 tracked files including instruction text
injected into every session. No such agent has ever existed. Every site now
names the agent that does that job: `quick-cop` for checking whether a finding
or a completion claim is true, `bad-cop` with `MODE: evidence-judge` for judging
QA artifacts.

The name was the smaller half. Two live defects sat underneath it, both in
`scripts/skill-verify-gate.py`, a **registered PreToolUse hook that refused
work**:

1. **A block whose escape route could not be taken.** It exited 2 for `/qa`,
   `/debug`, `/explore`, `/workspace` and others, and told the operator to spawn
   `evaluator-agent`. The flag it waited on cleared only when a Task description
   happened to contain the literal word "evaluator" or "verdict", so following
   the instruction verbatim did nothing. Reproduced on a scratch tree: exit 2,
   and a real `bad-cop` spawn described as "Re-check hooks round" left the flag
   set. It now nudges rather than refuses, per the standing decision that
   verifier gates nudge and only security guards refuse.
2. **A crash on four ordinary payload shapes.** `json.loads` accepts `null`,
   `[]`, `"a string"` and `17`; each produced `AttributeError` at exit 1. Exit 1
   is not a block, so it failed open with a traceback on every Skill call. Same
   class as the five hooks fixed in the concurrency round; this one was outside
   that scope and had **no test file at all**. It has one now, 18 tests, and
   the first run of it is what found the crash.

`verify-gate-cmd.py` now identifies the agent by `subagent_type`, using the same
resolution order as `research-record.py` and `verifier-record.py`, so all three
hooks agree on what a payload says the agent was. Verified in both directions:
`quick-cop`, `bad-cop` and `good-cop` clear the flag whatever the description
says; `researcher` and `swiper` do not.

**The detector already existed and nothing ran it.** `scripts/audit-hooks.py`
flags any `*-agent` or `*-cop` name in a hook prompt that is not installed. Run
by hand for the first time, it found the live site immediately and reported
clean after the fix. Nothing in the test suite, the installer or any hook
invokes it. Same shape as the dead port: the check was not missing, it was
unwired. Wiring it is part of the recommendation in
[bloat/docs-phantom-agent-roster](bloat/docs-phantom-agent-roster.md).

## Open: eighteen more agents that do not exist

Filed as [bloat/docs-phantom-agent-roster](bloat/docs-phantom-agent-roster.md).
`evaluator-agent` was not alone. `README.md` listed 23 agents and only six are
real. `CLAUDE.md` names `architect-agent`, `reviewer-agent` and
`ticket-analyst-agent` in its Model Routing section, and tells the model that
"specialist agents (architect, reviewer, debug, security, performance,
refactor, ui, docs, test, and the rest) are available". They are not.

README corrected. `CLAUDE.md` and `docs/CLAUDEBOOST-REFERENCE.md` not, because
that reaches instruction text the human may want worded their own way.

## Open: README described a deleted feature as current

Corrected, recorded here because it is the same class. The README advertised
"109 XML files loaded automatically by the RAG server", 55 domain bases, 21
language guides, 33 framework guides. Measured: **zero `.xml` files exist in the
tree** outside the venv. That was the topic knowledge base, deleted on measured
evidence, and the README still sold it as a headline feature.

Three further claims in the same section were false and are now corrected:
`POST /context` (404, the deleted server's route), `triage-agent` building the
project KB (not installed), and `research-agent` writing those files (its tools
are `WebSearch, WebFetch, Bash, Grep, Glob, Read`, with no `Write` and no
`Edit`, deliberately). The 131 files under `.claudeboost/knowledge/` are real
but return 0 hits in search, matching the session primer's own instruction to
read that directory rather than search it.

## Open: nothing supervises the RAG server

The server died at 11:54:53 on 2026-09-08, mid-session, with no traceback. The
log ends on a successful search and the process is simply gone. Nothing noticed
until a request failed several minutes later, and nothing would have.

Cause unproven. Several agents that session ran `taskkill /F /T` and
process-tree termination, and one fixed an `os.kill(pid, 0)` that terminates
rather than probes on Windows (python/cpython#70538), so a stale copy of that
behaviour against the server's PID is the plausible candidate. The log gives
nothing either way.

Two separate questions for the human. Whether a locally-bound dev server should
restart itself or be supervised at all. And whether anything should notice: the
practical cost was that every search silently failed until someone checked by
hand.

## Open: 111 abandoned lock files in live state

`clean-rag/state/research/` and `clean-rag/state/verifier/` hold 111 zero byte
`.lock` files with mtimes going back to 2026-07-12, left by the lock
implementation that was deleted. They are gitignored, so they never show in a
diff and nothing has ever cleaned them up.

Not currently harmful. The new `_claim` checks staleness on its first failed
claim specifically so an abandoned lock costs two syscalls rather than a full
timeout stall, pinned by a test that asserts under one second against a month
old lock. Left in place rather than deleted, because deleting live state to tidy
it is not a call to make without the human. The question is whether anything
should sweep them.

## Open: no bandit config, and one new finding left unsuppressed

Bandit reports B311 on the backoff jitter at `clean-rag/hooks/research_state.py:238`
(`random` is not cryptographically secure). It is a false positive: that call
picks a sleep length and guards nothing.

Left unsuppressed deliberately. There is no `.bandit`, no `bandit.yaml` and no
`pyproject.toml` in the tree, and the only `# nosec` comments anywhere are
inside bandit's own vendored source in the venv. Introducing a suppression
convention the codebase does not have is a larger decision than the finding
warrants.

## In progress

Python 3.9 support, the Critical from the portability review. Files carrying a
bare `X | Y` annotation without `from __future__ import annotations` raise
`TypeError` at module import on the floor this project documents. The crash is
above `if __name__ == "__main__":`, so the `except Exception: sys.exit(0)`
wrappers never run.

Done so far: `research_state.py`, `reindex-after-edit.py`,
`opencode_mcp_server.py` (hooks round) and `clean-rag/install.py` (verified on
3.9.13 and on the default interpreter). The remainder is with one agent.

The installer's preflight is part of the same fix: `scripts/setup.py:113` is
labelled `"Python 3.9+"` and only checks that an interpreter named `python` or
`python3` exists. It never reads a version.

Still owed on the hooks round: a bad-cop adversarial re-check, which is the only
thing that ends the loop. good-cop stamping is not the terminal condition.

## The capability audit, 2026-09-11

Eight items above, from one fan out over every skill, command, agent and hook. Counted, not estimated: 36 commands at 12229 lines, 25 skills at 3278, 7 agent files at 2722, 52 hook registrations.

Three results worth stating on their own.

**The skills are clean.** Zero phantom agent names, zero references to 8612 or a dead route, across all 25. Almost every verdict was KEEP. The rot is in the commands and the docs, not in the skills.

**The hooks are mostly earned.** Every merge candidate the audit went looking for turned out to occupy a different lifecycle stage: research-gate covers Edit, research-gate-bash covers the shell path it structurally cannot see; verify-after-edit, verifier-gate and verifier-record are nudge at edit, nudge at stop, and stamp on completion. Two dead files, no redundant guards.

**The expensive defect was invisible.** Nothing about an 18.4 second edit turn appears in any transcript, because the four hooks that import `server.config` wrap it in `try/except` with a hardcoded fallback. The cost had no symptom other than the system feeling slow. An edit turn would be about 4.8 seconds of hooks without it.
