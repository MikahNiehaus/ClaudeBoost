---
name: grill-me
description: A relentless interview to sharpen a plan or design. Ask the whole answerable frontier at once, each question with a recommended answer, and send researcher and swiper after any fact instead of asking the human for it. Ends with a mermaid diagram of what got settled and what is genuinely still open.
allowed-tools: Read, Grep, Glob, Bash, AskUserQuestion, Agent, Skill
---

# grill-me

Run a `/grilling` session.

Two things this project adds on top of it, and nothing else:

**Send `researcher` and `swiper` for the facts, by name.** `/grilling` already
says finding facts is your job and never the user's, and to dispatch a sub agent
rather than asking for something you could look up. In this project those agents
are `researcher` (the codebase, the import graph, the general engineering
standard) and `swiper` (does this already exist, in the project, the stdlib, a
dependency, GitHub, StackOverflow). Spawn them in the foreground. Do not block
the whole frontier on them: a running exploration is an unsettled prerequisite,
so only the questions downstream of it wait, and the rest of the frontier gets
asked now.

**Draw the tree at the end.** The design tree with a settled frontier is already
the data structure `/grilling` works in, so the diagram is a rendering of it, not
a second model. Emit a fenced ```mermaid block: a `graph TD` with one node per
question, and a `style` line per node coloured by state. Three states, and they
have to stay distinguishable: settled by a research agent (say which one, and
name the file or source), settled by the human's answer, and genuinely still open
with your suggested default attached. The per node `style` idiom, rather than
`classDef`, matches `clean-rag/server/kanban.html:1621-1644`, the one working
mermaid builder in this repo.

Say plainly that the diagram may render as source text rather than a picture.
Inline mermaid rendering in Claude Code is an open feature request
(`anthropics/claude-code#14375`), and the community skills that exist for it
exist because the base product does not reliably draw it.

## What this is not

Not a PRD. If a written document is what you need afterwards, run `/create-prd`,
which already has its own clarifying questions phase and does not need this one
to duplicate it.

Not a substitute for reading the code. A question you could have answered by
opening a file is a question you should never have asked.

## Attribution

`grill-me` and `grilling` are taken from
[mattpocock/skills](https://github.com/mattpocock/skills), MIT licensed,
Copyright (c) 2026 Matt Pocock. The interview procedure is theirs. The two
additions above are the only local changes.
