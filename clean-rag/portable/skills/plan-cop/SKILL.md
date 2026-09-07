---
name: plan-cop
description: Run the /workshop adversarial loop on a PLAN or a decision, with counterparty safety rules on top. You write the plan, bad-cop attacks it, good-cop revises it with cited grounding, and the loop repeats until bad-cop stamps VERIFIED on a clean pass. Use for any consequential non code decision, an email or letter going to a counterparty, a negotiating position, a migration or rollout plan, a vendor choice, anything where being wrong is expensive and nobody else is going to check you.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent, Skill, WebSearch
---

# /plan-cop

This is `/workshop` with the stakes turned up. The loop is identical, so it is
not restated here: **invoke the `workshop` skill and follow it in full.** Every
rule there applies unchanged, including the two that matter most, that every
round is a brand new agent, and that the reviewers never receive your rationale.

What this adds is everything that only applies when a real counterparty is on the
other side of the decision, where being wrong is expensive and unrecoverable
rather than merely annoying.

`$ARGUMENTS` is the plan, the decision, or the path to a draft. Empty means the
plan under discussion in this session.

## What changes in Step 1

Workshop's four part write up, unchanged, except part 1 is **the decision**: what
will actually be done, in one or two sentences. The plan file lives in the active
`workspace/<task-id>/`, not the scratchpad, because it is part of the record.

## What changes in the agent prompts

**Everything below goes into the prompt for `bad-cop` and `good-cop` verbatim,
every single time, in full**, on top of what workshop already requires. Not
paraphrased, not summarized, not assumed from a previous round, because there are
no previous rounds for a fresh agent. An agent that was not told is an agent that
will do it.

### The mailbox is READ ONLY. No agent sends anything, ever.

**No subagent spawned by this skill sends an email, replies to one, forwards one,
drafts into a Sent folder, or transmits anything to any counterparty. Not to
verify a fact, not to ask a question, not on its own judgment, not for any
reason.** Sending is the human's decision and it happens outside this loop.

There is no such thing as a small exception here. The counterparty in these plans
is usually a collector, an employer, an agency, or a lawyer. One unauthorized
message from a review agent is unrecoverable: it cannot be unsent, it becomes
part of the written record the plan is being built around, and it can concede in
one line what the whole plan exists to preserve.

Permitted mailbox operations, and only these:

- `node scripts/email.mjs list [folder] [limit]`
- `node scripts/email.mjs read <uid> [folder]`
- `node scripts/email.mjs unread [folder]`
- Reading attachments already saved to disk, or downloading one to read it

Forbidden, with no exceptions: `send`, `forward`, `reply`, any `send-*.mjs`
script, any SMTP call, any MCP mail tool that writes, and marking messages read,
starred, spam, or deleted. **Reading must not change mailbox state.** If a script
would flag a message as seen, say so in the report rather than working around it.

State it in the prompt as a flat prohibition, not a preference. Then say it again
in the deliverable section. Both places.

### Read every folder, not just the inbox

A reply that contradicts the plan is worth exactly as much sitting in Spam as it
is in the Inbox, and this workspace has already been burned by unread mail:
the full 19 toll picture arrived on 2026-06-02 and sat unopened for 85 days while
the plan was built on a wrong toll count.

Sweep, at minimum: `INBOX`, `[Gmail]/Spam`, `[Gmail]/All Mail`,
`[Gmail]/Sent Mail`, `[Gmail]/Trash`, and every user label. `All Mail` catches
anything archived past the inbox; `Sent Mail` is how you confirm what was
actually sent and when, which is often the fact the plan turns on.

Search by counterparty domain and by account or reference number, not only by
subject, because reply subjects get rewritten and threads fork.

### Give them the workspace, all of it

Workshop already says to hand over the history rather than a summary. Name the
paths here: the active `context.md`, every sub folder `context.md`, `evidence/`,
prior `SENT-*.md` files, and the earlier drafts.

The history is where the standing decisions live, where the retracted arguments
are recorded, and where the corrections to earlier mistakes sit. In the founding
run, the reviewer found a retracted argument, a documented falsehood, and a prior
correction that way, none of which were in the prompt.

### What bad-cop checks that workshop does not

- **Every claim gets tested for whether the counterparty can refute it in under a
  minute** from records they already hold. A refutable claim in a letter does not
  merely fail, it discredits the claims next to it that were true.
- **Every first person assertion gets checked against the documentation.** If the
  workspace records an approximation and the plan states a fact, that is a
  finding, even when nobody can currently disprove it.

### What good-cop is barred from

Repeat in its deliverable section: **it edits the plan file and nothing else. It
does not send the letter, the email, or anything to anyone, and it does not
change mailbox state.** Its job ends at a revised draft on disk.

## A note on guards for prose

If good-cop wants to write a script that checks the document, require that every
check fail on a rephrase carrying the same forbidden meaning, not just on the
original wording. In the founding run, a check named "body promises no payment
before an answer" was a regex over two specific phrasings; a reworded version
with the identical forbidden meaning passed the whole suite green.

A check that cannot fail is worse than no check, because it launders a defect as
verified. For a one off document, no guard at all is usually the right answer.

## What this is not

Not `/workshop` itself. That is the same loop for any subject, an idea, a design
question, "what is the best way to X", where a wrong answer costs you rework.
This one is for when a wrong answer costs you something you cannot take back, and
it carries mailbox rules that a general purpose skill has no business enforcing.

Not `/grill-me`. That is an interview that asks *you* questions to sharpen a
plan you are still forming. This attacks a plan you have already formed, using
agents, and you answer nothing.

Not for code. A diff has tests and an interpreter, and running it is a better
signal than any review. Use `/bad-cop` and `/good-cop` directly there.

Not for reversible, cheap decisions. Three agent rounds on something you can undo
in a minute costs more than being wrong would.
