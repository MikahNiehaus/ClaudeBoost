# spec

Deferred work. Nothing here is a bug report and nothing here is scheduled.

Each file is one architectural item that a review found, judged too large to
apply in the review that found it, and wrote down for a human decision instead.
The three folders are the three kinds:

| Folder | What goes in it |
|---|---|
| `bloat/` | Something that should be removed entirely or simplified. Dead paths, duplicated subsystems, a feature carrying more cost than it returns. |
| `architecture-changes/` | Something that exists and should be built differently. A contract, a layer, a state model that is wrong in a way a local fix cannot reach. |
| `architecture-addons/` | Something that does not exist and should. A missing layer, a missing guard, a missing test surface. |

## The bar for writing a file here instead of fixing it

A reviewer that finds a real defect **fixes it**. That is the default and it is
not negotiable. A file lands here only when the fix would require at least one
of these:

- Changing a public interface or a contract other files depend on.
- Deleting or merging a whole module or subsystem.
- Adding a new dependency, or a new architectural layer.
- A change spanning more than roughly five files that is not a mechanical
  rename.
- Removing a feature entirely.

If the fix fits in one file and breaks no contract, it gets fixed. Writing it
here instead is the failure this bar exists to prevent. A spec folder that fills
up while obvious defects stay in the tree is worse than no spec folder.

## The deprecation exception

The bar above assumes the thing being removed is still doing something. When it
is not, the bar does not apply.

**Obviously deprecated work gets done, not filed.** Removing or repointing
something that names a subsystem which no longer exists is a fix, whatever its
file count. A constant pointing at a deleted server, a docstring describing a
removed route, a shim whose own comment says it can be deleted, instruction text
steering an agent at an endpoint that returns connection refused: none of these
need a decision, because the decision was already made when the thing they name
was removed. Finishing the sweep is completing that decision, not making a new
one.

Two things still come here even when the deprecation is obvious:

- **A behaviour a user would notice.** Removing a documented entry point,
  turning a block into a non-block, changing what a command prints. The code may
  be dead; the expectation is not.
- **A live guard, gate, or hook.** Even a guard whose stated reason is stale is
  still refusing things today. Removing one changes what gets through.

The recorded example is `bloat/scripts-boost-command-surface.md`. Its health
check targets a deleted port, which is obvious debt, but one of its files is a
hard block wired into the user's settings, which is a decision.

## File naming

`<area>-<slug>.md`, where `<area>` is the part of the tree it concerns:
`server-`, `hooks-`, `scripts-`, `cli-`, `mcp-`, `opencode-`, `agents-`,
`docs-`, `security-`, `tests-`.

The prefix keeps parallel reviewers from colliding on a filename and makes the
folder sortable by subsystem.

## File format

Copy `TEMPLATE.md`. Every claim in a spec file cites `file:line`. A spec with no
citations is an opinion, and an opinion does not survive six months well enough
to act on.

## Keeping this current

A spec file is written when the item is found and **updated when the item moves**.
Three things change a file's status and all three belong in the file itself, not
only in a conversation:

- **Done.** Say what was done, when, and what evidence confirmed it. Leave the
  file; a removed spec file loses the reasoning that justified the change.
- **Superseded.** Something else fixed it, or it turned out not to be real. Say
  which, and why.
- **Measured.** A spec that estimates a cost and later gets a real number should
  carry the number. `architecture-addons/server-exec-route-capability-boundary.md`
  described indexing as a meaningful cost to an attacker until it was timed at
  0.605 seconds, which changed the decision it was asking for.
