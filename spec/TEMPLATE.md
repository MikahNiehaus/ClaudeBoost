# <one line naming the thing, not the symptom>

- **Kind:** bloat | architecture-change | architecture-addon
- **Area:** <server | hooks | scripts | cli | mcp | opencode | tests>
- **Found by:** <reviewer> on <date>
- **Why it was not fixed in place:** <which bar it crossed, from spec/README.md>

## What is there now

What the code does today, with `file:line` for every claim. Quote the lines that
matter. Someone reading this in six months has not read the code.

## Why it is a problem

The concrete cost. A bug it causes, a class of bug it invites, work it makes
slower, a contract it makes impossible to hold. Not "this is not clean".

If it has already caused a real failure, say so and name it. That is the
strongest form of this section and the only one that is not a prediction.

## What to do instead

The shape of the change. Enough that someone can judge the size of it without
re-deriving the analysis. Name the files it would touch.

## What it would break

Every caller, test, and contract that depends on the current behavior. This is
the section that decides whether the change is worth it, so it is the one to be
honest in. `file:line` for each.

## Open questions

What the reviewer could not settle. A decision the human has to make, an
unknown that needs measuring first, a tradeoff with no obvious winner.

Leave this section in place even when empty. "None" is information.
