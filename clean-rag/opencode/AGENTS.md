# clean-rag rules for OpenCode

OpenCode reads this file. It is the soft enforcement layer that sits next to the
research gate plugin. The plugin blocks code edits mechanically. This file tells
you the workflow the plugin is trying to hold you to, so you follow it on purpose
rather than only when a block stops you.

## Before you write code, research it

Call the clean-rag `rag_search` tool with a query about what you are changing. It
searches the indexed project and its import graph, so you find what already exists
and what your change touches.

If `rag_search` returns zero results, the project is not indexed yet. That is not
"nothing to find". Call `web_search_fallback` and research from the web instead.
Either way, do the research before the edit. A zero result search does not open
the gate, and it should not stop you either.

For anything beyond a trivial change, spawn `research-agent`. It covers depth and
breadth, checks whether the thing already exists, and ends with a `COVERS:` line
naming the files it researched. The gate reads that line and only then lets you
edit those files.

## For a known genre, ground it in a real reference first

If what you are building is a known genre, a game (Flappy Bird, Snake, Tetris), a
common algorithm, or a standard widget, do not build it from memory. Call
`web_search_fallback` for one real working implementation (GitHub first), read it,
and copy the patterns that are easy to get wrong: physics constants, collision
math, game loop timing, edge cases. A weak model guessing gravity and jump
velocity produces a game that feels wrong. Handed real numbers from a working
repo, it does not. This grounding step helps a weak model most, so it is worth
the one search.

## Quality bar for a game or simulation (hit every one of these)

A game or physics simulation is only good if it has all of this. Build to it, do
not settle for less. This is what separates a real game from a toy that feels
wrong and cannot be tested:

- **Pure engine module, no React and no DOM.** One file exports a pure function
  `step(state, dt, input, rng)` that takes the old state and returns the NEW state.
  It does not mutate its input and it does not import react, document, or window.
  This is what makes it testable.
- **Inject the random source.** `step(..., rng = Math.random)`. Pipe gaps and
  spawns call `rng()`, not `Math.random()` directly, so a test can pass a fixed
  rng and get reproducible pipes. `Math.random()` inside the engine makes it
  untestable, which is a fail.
- **Fixed timestep accumulator, not variable dt.** The loop accumulates real
  elapsed time and runs `step(state, FIXED_DT)` in a `while (acc >= STEP) { ...;
  acc -= STEP }` loop, then renders once. Clamp the raw frame dt (about 250ms) so
  a backgrounded tab cannot tunnel through a wall. `pos += vel * dt` with a
  variable dt is the weak version, it is non deterministic and cannot be unit
  tested for frame rate independence.
- **Forgiving hitbox.** The collision box is smaller than the sprite, about 75%,
  derived from the sprite size, not a magic constant. A hitbox that matches the
  sprite makes deaths feel unfair.
- **Rendering separate from logic.** A draw only module or function reads state
  and draws, never mutates it.

## Tests you must write for a game (before you are done)

- Frame rate independence: one `step` at 1/30s lands the same place as two `step`
  calls at 1/60s (within a small tolerance). This is the test that proves the
  fixed timestep is real.
- Scoring: passing a pipe increments the score exactly once.
- Collision: a bird in the gap does not collide, a bird clipping the pipe does.
- Inject the rng so pipes are deterministic in these tests.

## Research the whole problem, not the happy path

One search is not research. Cover the quality lenses every time:

- Correctness and edge cases: what inputs break this? Empty, zero, huge, null.
- Security: injection, untrusted input, secrets, auth. See the standards below.
- Test quality: how will you prove this works?

If you only asked "how do I build X" and never "how does X break", you have not
finished researching.

## After you write non trivial code, test it for real

Write a test, then call the `run_tests` tool on the project. It runs the project's
tests (npm test, vitest, jest, or pytest, auto detected) and hands you back the
real failure output: the assertion diff and the stack trace. Fix from that actual
output, not from reading your own code and deciding it looks right. Do not self
review in place of running something. The reminder the gate appends to a block
("you wrote X and run_tests has not passed") is there because OpenCode cannot nudge
you passively. Beat it to the punch: run the tests yourself.

Trivial one liners do not need a test. Anything with a branch, a loop, a parser, or
a money or security path does.

**You are not done until a real test exists AND `run_tests` comes back passed.**
For a game that means the frame rate independence, scoring, and collision tests
above actually run and pass. If you write the code and stop without a passing
test, the job is not finished, no matter how right the code looks to you.

## Standards that are never optional

These apply automatically. They are not up for debate and not something research
decides:

- Parameterized queries. Never build SQL by string concatenation.
- `logger.error` (or the language equivalent) in every catch or error block.
- No secrets in logs, URLs, or source.
- Validate input at the boundary.
- Auth and authorization checks on every endpoint.
