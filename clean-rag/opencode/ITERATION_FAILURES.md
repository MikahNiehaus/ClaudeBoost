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
