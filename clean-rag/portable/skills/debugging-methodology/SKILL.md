---
name: debugging-methodology
description: How to pick a debugging technique instead of guessing, and the tools and CLI recipes for every stack. Read this when a bug is not yielding after two or three attempts, when you are about to add another print statement, or before debugging a stack you have not touched before (React Native, .NET, native, browser). Also the rule for databases — understand the schema, never execute against a live one.
---

# Debugging methodology

The failure mode this exists to stop: trying the same technique harder. Two or
three iterations with no new information is not a signal to add more logging, it
is a signal that the technique is wrong for this bug. Pick a different one, by
name, from the table below.

## Pick the technique from the symptom

| Symptom | Technique | Why this one |
|---|---|---|
| It worked at some past commit | **`git bisect`** | O(log n) checkouts instead of reading history. `git bisect start`, `git bisect bad`, `git bisect good <sha>`, then `git bisect run <cmd>` to automate it entirely |
| Large input that fails, small ones don't | **Delta debugging (ddmin)** | Binary search the *input*, not the history, down to the minimal failing case. Zeller's algorithm |
| Long call chain, one bad value in it | **Binary search on state** | Assert the invariant halfway down. Bad above or below? Halve again. Beats stepping every frame |
| A working case and a failing case | **Differential debugging** | Diff the two executions. The one dimension they differ in is the bug. Far cheaper than reasoning about the failing case alone |
| Reproducible, cause unclear | **Hypothesis-first** | Write the hypothesis down, then design the smallest test that would *falsify* it. Guess-and-check without a falsifiable claim is how hours vanish |
| Intermittent, races, "can't reproduce" | **Record-replay** (`rr`, Replay.io) | Record once, then replay the exact failing execution deterministically, backwards if needed. The only real answer for heisenbugs |
| Haven't explained it out loud yet | **Rubber duck** | Costs a minute. Catches the wrong assumption before you spend an hour tooling up |
| No reliable reproduction at all | **Stop. Get the repro first** | A fix without a reproduction is a guess you cannot validate. Reproducing *is* the task until it's done |

Grounding: Agans, *Debugging: The 9 Indispensable Rules*; Zeller, *Why Programs
Fail* (delta debugging, systematic isolation). Cite them, don't paraphrase them
as your own reasoning.

## The stall rule

At **two to three iterations without new information**:

1. Say which technique you have been using and why it isn't producing signal.
2. Pick a different one from the table by name.
3. If nothing in the table fits, that is the moment to **research** — search for
   how this class of bug is debugged in this stack. Do not invent a method.

Retrying the same static-reading / live-stepping split harder is the thing to
avoid. Switching between "read the code again" and "add another print" is one
technique, not two.

## Tools

Step-through debugging is `mcp-debugger` (Python, Ruby, Node, Go, Java, .NET,
Rust). Reach for it over print statements when you need a value at a moment:
`create_debug_session` → `set_breakpoint` → `start_debugging` or
`attach_to_process` → `get_variables` / `evaluate_expression`.

Browser, network and performance is `chrome-devtools`. Coverage is
`test-coverage`. Native C/C++ is `mdb` (GDB/LLDB), if registered.

Not everything has an MCP server. These are CLIs — drive them with Bash:

### React Native

RN DevTools replaced Flipper (removed from templates in RN 0.74) and talks CDP
to Hermes. So the JS side is reachable through `chrome-devtools` at the URL
Metro prints on start — there is no RN-specific MCP server worth installing.

```bash
npx react-native log-android          # Metro + native log tail
npx react-native log-ios
adb logcat *:S ReactNative:V ReactNativeJS:V    # Android, filtered to RN
xcrun simctl spawn booted log stream --predicate 'processImagePath contains "<AppName>"'
```

### .NET

`mcp-debugger` covers stepping and attach via netcoredbg. For everything past
that, the diagnostics tools (`dotnet tool install --global <name>`):

```bash
dotnet-trace collect --process-id <PID>     # CPU / event traces
dotnet-dump collect --process-id <PID>      # crash + process dumps, then: dotnet-dump analyze
dotnet-gcdump collect --process-id <PID>    # GC heap, for leak hunting
dotnet-counters monitor --process-id <PID>  # live perf counters
```

### Python

```bash
py-spy dump --pid <PID>                       # instant stack of a live/hung process
py-spy record -o profile.svg --pid <PID>      # sampling flamegraph, no code changes
```

`py-spy` is `benfred/py-spy` (`pip install py-spy`). It attaches to a running
process without restarting it, which makes it the right tool for a hang or a
production-shaped slowdown.

## Databases: read the schema, never run against one

Understand the structure from the project's own artifacts, not by querying a
live server:

- **.NET / EF Core** — the `DbContext`, the entity classes, and `Migrations/`.
  Migrations are the authoritative history of the schema.
- **Python** — `models.py`, SQLAlchemy/Django model definitions, Alembic
  versions, `schema.sql`.
- **Anywhere** — committed `schema.sql`, seed files, ORM definitions.

When advising on a query:

- Parameterized queries only. Never string concatenation.
- `SELECT` and `EXPLAIN` are the diagnostic verbs. Transactions for anything
  multi-step.
- Never propose a destructive statement as a debugging step.

**Hard rule: do not execute against a live database, and do not automate SSMS or
any equivalent GUI client.** Read the schema, reason about the query, hand it to
the human to run. The blast radius of a wrong statement against real data is not
recoverable by a retry, which is exactly why this is a rule and not a preference.
