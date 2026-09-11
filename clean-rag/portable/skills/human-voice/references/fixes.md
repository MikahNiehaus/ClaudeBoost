# Repairs by flag type

Each flag maps to a specific fix. Flagging without repairing is what makes most style checkers useless.

Whether a flag deserves a fix at all is a separate question, answered by
"Before you act on a pattern" in `patterns.md`. This file assumes you already
decided to edit.

## em_dash_connector

Split the sentence at the dash, or use a colon if the second half explains the first.

Before: "Governance creates risk — and that risk compounds quickly."
After: "Governance creates risk. That risk compounds quickly."

Before: "There are two options — build or buy."
After: "There are two options: build or buy."

Keep the dash for a true range with an en dash (2019-2024), and for a genuine
parenthetical aside where commas would be ambiguous. Those are rare.

**How that squares with patterns.md**, which says "a mid-sentence splice still
counts": the two rules describe different shapes, and the number of dashes tells
them apart. One dash joining two clauses is the splice, and it gets fixed. Two
dashes bracketing a short phrase are a parenthetical, which the corroboration
gate protects as "a genuine aside", and it stays. `lint.py` draws the same line:
a pair reports as `em_dash_aside`, a note rather than a flag.

## em_dash_aside

Usually nothing. A paired-dash parenthetical is weak alone, so act only if other
tells share the passage. If you do edit, commas or parentheses carry the same
aside without the drama.

Never *add* one during a rewrite. SKILL.md's "Never inject these" forbids
em-dash theatrics outright, and this note existing is not permission.

## low_sentence_variance / clustered_sentence_length

The fix is not rewording. It is changing lengths.

Find the longest paragraph. Cut one sentence in half. Then find a place where a four-word sentence lands hard and write one. Aim for a spread from three words to thirty within the same piece.

A useful test: read the paragraph aloud. If your breathing pattern is identical across every sentence, the variance is too low.

## opening_restates_title / generic_opening

Delete the first sentence. Check whether the piece still makes sense. Usually it improves.

Then open with the most specific thing you know: a number, a name, a date, a rule, or the conclusion itself.

Before: "In today's evolving digital landscape, content teams need governance."
After: "Twelve concurrent campaigns ran for two years with no quality failures. The framework was three rules."

## closing_restatement / summary_opener

Delete the final paragraph. Read the new ending.

If the piece now ends abruptly on a useful fact, you are done. If it genuinely needs a closing move, make it forward-looking and new: what to do next, what to watch for, what you would do differently. Never a recap.

## repeated_sentence_opening / repeated_first_word

Change the subject of one sentence in the run, or merge two of them.

Before: "Setting boundaries helps teams. Defining limits prevents drift. Establishing checkpoints catches errors."
After: "Boundaries help teams understand scope. Limits prevent drift, and checkpoints catch errors before they reach a client."

## repeated_paragraph_opening

Same repair, one level up: the repeat lands once per paragraph, so no two of the
offending sentences are adjacent and reading them in sequence hides it. Read
only the first words of every paragraph in a column, then rewrite the openings
that match.

Before: five paragraphs each opening "So the worker pool...", "So why five...",
"So the shard assignment...".
After: keep at most one. The rest open on their subject: "The worker pool spins
up five processes on boot." A discourse marker that survives should be doing
real work, not starting a paragraph out of habit.

## title_case_heading

Lowercase every word except the first and any proper noun.

Before: "## Why Cache Invalidation Breaks Most Caching Strategies"
After: "## Why cache invalidation breaks most caching strategies"

Rewording a heading to fix its case is one of the two carve-outs to the
preservation check, so this edit is allowed even in a mode that otherwise leaves
heading text alone. A top-level `#` title reports as a note, not a flag:
patterns.md permits title case there "if at all".

## contrast_construction

Keep one per piece, at the point where it earns the emphasis. Convert the rest into plain statements.

Before: "The solution is not more oversight, but better oversight."
After: "Better oversight beats more oversight."

The trailing form is the common one and the easiest to miss, because the negation arrives after the point rather than before it. Cut the negated half. The assertion almost always survives alone.

Before: "We treat the road to writing as art for now, not drills."
After: "We treat the road to writing as art for now."

Before: "Fresh, home-style food during the day, not out of a packet."
After: "Fresh, home-style food, cooked that morning."

Watch for it clustering. A run of them across one section usually means that block was drafted in a single sitting under a different instinct, and the whole block needs the pass rather than individual lines.

## trailing_negation_density

A count, not a list of violations, because "X, not Y" is weak alone and ordinary
English produces it constantly. Measured on hand-written prose in this repo it
runs about 4 per 1,000 words, so a rate near that is a voice, not a defect.

Act only where several sit in one passage. Then apply the trailing-form repair
above to the ones that are padding and leave the ones carrying a real contrast.

## stacked_adjectives

Three adjectives stacked before a noun ("a scalable, flexible, and robust
solution") almost always means none of them was measured. Keep the one that
carries information and delete the others, or replace all three with the fact
they were standing in for.

Before: "a scalable, flexible, and comprehensive framework"
After: "a framework that handles 40 sites and covers all nine steps"

If no fact is available, cut to one adjective. Do not invent the number: SKILL.md's
"Never inject these" treats a fabricated specific as worse than the vague phrasing.

## hedge_structure

Pick a side. If both sides genuinely matter, state each as its own sentence without the balancing frame.

Before: "While automation is valuable, it is also important to consider the human element."
After: "Automation handles volume. Humans still own the calls a model should never make."

## rhetorical_opener

Answer the question instead of asking it.

Before: "So what does this mean for your team?"
After: "Your team loses two days a week to this."

## banned_word / banned_word_figurative

Substitute the concrete verb or noun that the abstraction was standing in for. Do not reach for a synonym of the banned word, because that moves the tell rather than removing it.

- leverage -> use, run on, build with
- navigate (figurative) -> handle, work through, get through
- landscape (figurative) -> market, industry, rules, competitors
- robust -> name the property: fast, tested, survives load
- holistic -> name the scope: covers billing and support
- comprehensive -> give the count: covers all nine steps
- delve / deep dive / unpack -> look at, go through, break down

## participle_tail

A result clause bolted onto the end of a sentence with a comma and an -ing verb. One is fine. Three in a row is the strongest tell in this file, because it makes every sentence resolve on the same falling beat.

Before: "We begin with compliance-first scripting, ensuring all claims are accurate."
After: "We script compliance first. Every claim gets checked against the source."

Before: "The team reviews each frame against the brief, allowing stakeholders to sign off early."
After: "The team reviews each frame against the brief. Stakeholders sign off before animation starts."

The repair is always the same: make the result its own sentence, or cut it. If the result is obvious from the first half, it was padding.

## over_cap_word

Cut every instance except the one that matters most. If three things in a piece are crucial, none of them are.

## banned_phrase

Delete the phrase. The sentence almost always works without it.

"It is worth noting that most teams fail here" becomes "Most teams fail here."

## short_form_too_long

Cut to the answer plus at most one line of context. Move anything else to a follow-up message.

## emoji_spam / over_apology

Remove all but one emoji. Delete the apology unless something actually went wrong.
