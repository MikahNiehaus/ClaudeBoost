# clean-rag rules for OpenCode

OpenCode reads this file. It is the soft enforcement layer that sits next to the
research gate plugin. The plugin blocks code edits mechanically. This file tells
you the workflow the plugin is trying to hold you to, so you follow it on purpose
rather than only when a block stops you.

## Before you write code, research it

Call the clean-rag `rag_search` tool with a query about what you are changing. It
searches the indexed project and its import graph, so you find what already exists
and what your change touches.

**If `rag_search` returns zero results (a fresh, unindexed project), spawn
`research-agent`.** It is the reliable way to research: it does the web search
itself, once, ranks the sources, reasons over them, and ends with a `COVERS:` line
naming the files it researched. The gate reads that line and unlocks those files.
This is the primary path for a fresh project, use it.

Do NOT sit in a loop calling `web_search_fallback` yourself. You may call it ONCE
as a quick check, but if it comes back empty (the scraper rate limits rapid
repeats), do not call it again, spawn `research-agent` instead. Hammering
web_search gets you rate limited and gets you nowhere.

## Ground anything not trivial in a real reference, then derive the bar

Do not build from memory. Whatever it is, an API, an auth flow, a payment path, a
parser, a game, find ONE real, production-grade reference for this class of thing
(GitHub and official docs first, via `web_search_fallback` or by spawning
`research-agent`) and study what it does that you would not think of yourself. A
real reference is where the non-obvious correctness rules of a domain live: a
payment service shows idempotency keys and row locks, an auth flow shows token
handling and constant-time comparison, a game loop shows the fixed timestep and
how input is fed. You are not expected to already know a domain's rules. You find
the reference and copy the decisions it made.

Grounding helps a weak model more than a strong one. A model guessing a domain's
specifics from memory produces something that looks right and is subtly wrong;
handed the real decisions from a working system, the same model does not. So this
system does not hand you a per-domain checklist, that would only ever fit one kind
of thing. It makes you go derive the bar for THIS thing from a real reference.

## Derive the correctness properties, then prove your tests bite

This is what separates code that looks right from code that is right, and it is
the same move in every domain:

1. **State the properties as invariants, before you write the code.** From the
   reference and from how this class of thing actually FAILS (not how it works on
   the happy path), write down what must hold for ALL valid inputs and what must
   never happen. Phrase them as "for any X, Y holds" or "A then B returns to the
   start," not as a feature list. A transfer: never goes negative, atomic,
   idempotent on retry, no double spend under concurrency. An endpoint: rejects
   unauthenticated calls, rejects malformed input, parameterized queries. A
   real-time sim: the same inputs give the same result. You DERIVE these from
   research; there is deliberately no list of them here, because a list would fit
   one domain and mislead on the next.
2. **Sensitivity check each property: name the wrong implementation it catches.**
   If you cannot name a plausible broken version this property would flag, the
   property is decorative, drop it. A property that only ever holds on the happy
   path proves nothing.
3. **Write one adversarial test per property**, feeding the bad input, the
   concurrent call, the replay, the missing auth, the empty and the huge and the
   null, asserting the property still holds. Assert the CONTRACT, never the exact
   output your current code happens to produce, a test pinned to your
   implementation passes just as happily on a broken one.
4. **Prove each test bites by breaking the code on purpose.** Flip a comparison,
   drop a guard, use the wrong sign, delete the validation branch, then confirm
   the test FAILS. A test that still passes on the deliberately broken version is
   worthless, no matter that it is green on your real code. This mutation check is
   the one defence against shallow tests that needs zero domain knowledge, so it
   applies to everything. Put the code back once you have seen the test fail.

The damning mistake to avoid: writing a test that asserts the buggy behavior you
just wrote. The test comes from the property, and it must fail on wrong code.

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

**You are not done until a real test exists, `run_tests` comes back passed, AND
that test fails on a deliberately broken version of the code.** A green test that
you never proved can go red is not evidence. If you write the code and stop
without a passing, biting test, the job is not finished, no matter how right the
code looks to you.

## Standards that are never optional

These apply automatically. They are not up for debate and not something research
decides:

- Parameterize or escape every query language you touch (SQL, shell, HTML,
  GraphQL, a path). Never build one by string concatenation.
- `logger.error` (or the language equivalent) in every catch or error block.
- No secrets in logs, URLs, or source.
- Validate input at every trust boundary.
- Authorize every entry point, whatever its shape: an endpoint, a command, a
  handler, a job.
