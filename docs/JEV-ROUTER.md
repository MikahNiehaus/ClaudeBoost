# jev-router in ClaudeBoost

**Subject:** [gargpratyush/jev-router](https://github.com/gargpratyush/jev-router), a
per-prompt model router for Claude Code. It is an npm package (`jev-router` v0.3.0,
MIT licence).
**Added:** 2026-09-29, as an **opt-in** install step. It is off by default.
**Verdict:** It fills a real gap, because ClaudeBoost has no per-prompt routing.
It is opt-in because it sends prompt text to a third party, and because its cost
savings have not been measured.

---

## 1. What it is

jev-router gives you a `jev-claude` command to use instead of `claude`. It starts
the real `claude` CLI behind a loopback proxy. For each request, the proxy sends
the prompt text to TypeSafe's hosted Jev service. Jev scores the task on
complexity, reasoning, tool use and context size, then picks a model tier:

| Tier | Model |
|---|---|
| fast | Haiku |
| balanced | Sonnet |
| strong | Opus |
| long | Fable (only when `JEV_ALLOW_FABLE` is set) |

Your Anthropic auth headers pass through unchanged. You can pause routing by
choosing another model in the `/model` picker, and resume it by choosing
"Jev Router". The package also installs `jev-codex` and `jev-explain`.

## 2. How it compares to ClaudeBoost

| | ClaudeBoost | jev-router |
|---|---|---|
| What gets routed | Each **agent**, to a fixed model (Opus for architect, reviewer and good-cop; Sonnet for the rest) | Each **prompt** in the main conversation |
| How the model is chosen | Static, written in the agent definitions | Picked per request by a hosted classifier |
| Where prompts go | Stay local, apart from the Anthropic API | Also sent to TypeSafe's Jev service |
| Setup | None | npm install, a `JEV_API_KEY`, and launching with `jev-claude` |

The two don't overlap. Agent routing and main-loop routing solve different
problems, and ClaudeBoost's hooks keep running under `jev-claude` because
`jev-claude` starts the real `claude` CLI.

## 3. Why it is opt-in

1. **Prompts leave the machine.** Every prompt goes to TypeSafe's service,
   including any pasted code and file contents. ClaudeBoost otherwise keeps
   web-facing work inside one capability-stripped research agent, and this is a
   wider outbound path than anything else in the repo.
2. **The savings are unmeasured.** The project publishes no cost figures.
   Changing the model mid-session also throws away the prompt cache, which is
   separate for each model. A turn routed to Haiku with a cold cache can cost
   more than staying on a warm Sonnet or Opus cache.
3. **Nothing needs vendoring.** It is a standalone CLI. The only integration
   ClaudeBoost needs is an install step.

## 4. Enabling it

```bash
CLAUDEBOOST_WITH_JEV_ROUTER=1 ./install.sh
echo "JEV_API_KEY=..." > ~/.jev-router.env
jev-claude
```

On Windows, run `set CLAUDEBOOST_WITH_JEV_ROUTER=1` and then `.\install.bat`.
You need Node.js 20.12 or later.

The values `""`, `0`, `false`, `no` and `off` (in any case, ignoring surrounding
whitespace) leave it **off**. That's deliberate: this setting controls whether
prompts go to a third party, so a value that looks like "off" must never turn it
on.

## 5. Implementation

`install_jev_router()` in `scripts/setup.py` is called from `main()` right after
`install_mermaid_cli()`, and it copies that function's structure:

- If the variable isn't set to an "on" value, it prints `[SKIP]` and returns
  without touching PATH or running any subprocess.
- If `jev-claude` is already on PATH, it prints `[OK]`.
- If npm is missing, it warns and returns.
- Otherwise it runs `npm install -g jev-router`. If that fails, it warns with
  the tail of npm's output. If npm succeeds but `jev-claude` still isn't on
  PATH, it warns about PATH.
- On success it warns about the prompt exposure, the `JEV_API_KEY`
  requirement and the Node version.
- It never writes the API key.
- It checks for the binary with **`shutil.which` only**. `jev-claude` passes its
  arguments straight to `claude`, so `jev-claude --version` would start a Claude
  session. `shutil.which` also respects PATHEXT, so the `.CMD` shims on Windows
  are found.

**Known limitation:** `run_cmd` catches only `FileNotFoundError`. A
`PermissionError` from a broken npm shim would propagate and stop setup. This
already affects `install_mermaid_cli` too, and belongs in a separate fix to
`run_cmd`.

## 6. Verification

- `scripts/tests/test_setup_jev_router.py` has 10 tests. They cover: off by
  default, the four "off" values staying off, already installed with no
  subprocess run, npm missing, install failure, installed but not on PATH, and
  a clean install. All 10 pass in a scrubbed environment
  (`env -i PATH=... HOME=...`).
- Hand-applied mutants were all caught:
  - inverting the opt-in gate: 10 of 10 failed
  - adding a `jev-claude --version` probe: 1 of 10 failed
  - dropping the post-install PATH re-check: 1 of 10 failed
  - reducing the gate to `== ""`: 4 of 10 failed
- Adversarial review: the first pass found two nits. The falsy-value one was
  fixed. The `run_cmd` one is the known limitation in §5. The re-check was
  clean.
- **Not verified:** a real `npm install -g jev-router`, a real routed session,
  and any cost comparison. Before relying on the savings, compare `/cost`
  across several sessions run with and without `jev-claude`.
