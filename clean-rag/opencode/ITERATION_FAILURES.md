# OpenCode build quality: iteration log

Goal: get an OpenCode free model build of Flappy Bird as good as the Claude Code
reference at C:/prj/New folder/injection. Gather every failure each round.

## The bar (injection reference)

- Pure engine module (game.js): `step(state, dt, input, rng = Math.random)`, no
  React or DOM imports, rng injected so tests are deterministic.
- Fixed timestep accumulator in the loop: `while (acc >= STEP_MS) step(...)`, plus
  render interpolation `draw(ctx, state, acc / STEP_MS)`. NOT variable dt.
- Frame dt clamped (MAX_FRAME_MS) so a backgrounded tab can't tunnel the bird.
- Hitbox inset: BIRD_R = 75% of the sprite, forgiving hitbox honest visuals.
- Separate render.js, draw only, never mutates state.
- 4+ vitest unit tests, including frame rate independence (one step at 1/30 ==
  two steps at 1/60) and gap-safe vs pipe-clip collision.

## Iteration 1 (deepseek-v4-flash-free, grounding + strong gate)

Build produced a runnable game with correct run.bat, but below the bar:

1. Variable dt (`Math.min((t-last)/1000, 0.05)`), not a fixed timestep accumulator. FAIL.
2. `Math.random()` inline in the engine, no injected rng. Untestable. FAIL.
3. Hitbox is a magic `HITBOX_R = 12`, not derived as a % inset of the sprite. PARTIAL.
4. No separate render module, drawing lives in App.jsx. FAIL.
5. No unit tests, no test script. The auto-test loop had nothing to run. FAIL (biggest).
6. `update(game, dt)` mutates in place, not a pure `step` returning new state. FAIL.

Root cause: the model spawned research-agent (which unlocked the gate) but the
research findings did not translate into the specific patterns, and it skipped
tests entirely despite AGENTS.md asking for them.

Fix applied for iteration 2: make the grounding prescriptive. The OpenCode
research-agent, for a game or simulation genre, must return the concrete patterns
(fixed timestep, injected rng, pure state function, separate render, the specific
tests to write). AGENTS.md gets a hard done-condition: not done until a unit test
exists AND run_tests passes.

## Iteration 2 (prescriptive AGENTS.md + web-search-unlock + "call web_search" prompt)

WORSE than iteration 1. The model called web_search_fallback 13 times in a row,
all 13 returned 0 results (DuckDuckGo rate limits rapid repeated scraping), the
gate never unlocked, it wrote nothing, and it timed out. A regression.

Root cause: the web-search-unlock change plus a prompt telling the model to call
web_search made a weak model fixate on web_search and spam it. Iteration 1's
forced research-agent path was actually better, because research-agent does ONE
proper search and reasons, instead of the weak primary model hammering the
scraper.

Fix for iteration 3: the block message and AGENTS.md lead with "spawn
research-agent" as the primary path (reliable, one search, more capable), and say
web_search is a single fallback, never a loop. The web-search-unlock stays as an
option but is no longer what the model is steered toward first.

## Iteration 3 (research-agent-first path)

The model correctly spawned research-agent this time (no web_search spam), and
research-agent emitted a COVERS line. But the build still failed: research-agent
covered a NESTED structure (src/engine/engine.js, src/components/Game.jsx), while
the model wrote a FLAT one (src/engine.js, src/render.js, src/Game.jsx). The
per-file gate blocked engine.js, render.js, Game.jsx because the exact paths
didn't match. On a fresh project the research-agent is guessing filenames it can't
know, and the builder picks different ones.

Root cause: per-file COVERS is right for editing existing files, wrong for
creating new ones where filenames aren't known yet.

Fix for iteration 4: the research-agent, for a NEW project or module, emits an
AREA glob (COVERS: src/**, tests/**, *.config.*, index.html, run.bat) instead of
predicted filenames. Still scoped (won't cover outside those areas), but covers
whatever structure the builder actually picks. Applied to both the OpenCode and
Claude Code research-agent prompts.

## Iteration 4 (glob COVERS)

Better but still failed. The research-agent used globs now, but STRUCTURE
specific ones (src/engine/*.js nested), while the model wrote flat (src/engine.js).
A nested glob does not match a flat file, so engine.js, render.js, Game.jsx still
blocked. The research-agent keeps guessing a structure the builder does not follow.

Root cause: any prediction of the layout by the research-agent is brittle, glob or
not, because it cannot know what structure the builder picks for files that do not
exist yet.

Fix for iteration 5: distinguish CREATING a new file from EDITING an existing one.
In research-gate.js, if the target file does not exist on disk yet AND a
research-agent ran this session (emitted any COVERS), allow it. Existing files
keep the strict per-file COVERS check. You cannot per-file-cover a file that does
not exist, so a completed research-agent is the right signal for new files.

## Iteration 5 (new-file allow) — PERFECT, VERIFIED

Success. No blocks. Research-agent ran, emitted COVERS with flat filenames that
matched, and the new-file backstop covered anything else. The build hit every bar
marker, verified by RUNNING it, not by trusting the model:

- Pure engine.js: `export function step(state, dt, input, rng = Math.random)`.
- Injected rng: `gapY = PIPE_MARGIN_TOP + rng() * range`, not Math.random inline.
- Fixed timestep accumulator: `let accumulator = 0; accumulator += frameTime`.
- Forgiving hitbox: BIRD_H * 0.7.
- Separate render.js.
- engine.test.js with a real frame rate independence test
  (`one step at 1/30 equals two steps at 1/60`) plus 4 more.
- `npm test`: 5 passed (5), run by hand.
- `npm run build`: built in 136ms. Dev server: HTTP 200, engine.js transforms.
- run.bat correct: `cd /d %~dp0` + `start "Flappy" cmd /k npm run dev`.

A FREE model (deepseek-v4-flash-free) matched a build a capable model produced,
because the gate forced real research, the research-agent grounded it, and the
prescriptive AGENTS.md plus the new-file gate removed the friction that made
earlier rounds fail. Five iterations, five real setup bugs fixed, all kept.

## Closing the last gap: test-suite parity

Deep side by side against injection found one difference, and only one: injection
had a "does not mutate the state it is given" purity test, iter5 did not. The
iter5 `step` IS pure (it clones `state.bird` and `state.pipes` and never reassigns
`state`), it just wasn't tested for it. Added that test through the real loop:
research-gate blocked the edit, triage-agent returned NONE and stamped
`COVERS: src/engine.test.js`, edit went through, `npm test` = 6 passed (6). Now
the OpenCode build has literal test-suite parity with injection plus one extra
test (deterministic rng). Done.

## The real correction: chasing Flappy Bird parity WAS the bandaid

Everything above optimized the wrong target. The system is not meant to be good at
making Flappy Bird, it is meant to make a weak model produce correct code in ANY
domain: an API, an auth flow, a banking path. Every game specific rule that got
added to the bar (input model, flap sets velocity, render interpolation, pipe gap
tuning) was a bandaid. It made the harness good at one game and taught it nothing
general, and worse, it hid the real gap: a weak model ships plausible but wrong
code that passes its own shallow tests, in every domain, not just games.

So all of that was ripped back out. The bar no longer carries a per domain
checklist (the whole point: a checklist fits one domain and misleads on the next).
The general mechanism, the same in every domain and grounded in research (CodeT
arXiv 2207.10397, PGS arXiv 2506.18315, Meta ACH mutation testing arXiv
2501.12862):

1. Ground the build in ONE real reference and derive the domain's correctness
   rules FROM it, never from a baked in list. Physics falls out of reading a real
   game the same way idempotency falls out of reading a real payment service.
2. State the properties as invariants ("for any X, Y holds"), and sensitivity
   check each: name the wrong implementation it would catch, or drop it as
   decorative.
3. Write the adversarial test per property, asserting the contract, not the exact
   output the code happens to produce.
4. Prove each test bites by breaking the code on purpose (flip a comparison, drop
   a guard, wrong sign) and confirming it goes red. This mutation check is the one
   defence against shallow tests that needs zero domain knowledge, so it is the
   generalizable fix, not a game rule.

Applied to both Claude Code and OpenCode: AGENTS.md, both research-agent.md
copies, and the research-routing skill. Do not re-add a per genre quality bar. If
a build needs domain specifics, research derives them per task; the harness stays
domain blind on purpose.
