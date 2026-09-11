# Pattern catalog: full audit

The P2 and judgment-only rules, the stylometric and structure tests, and the
decision to rewrite rather than patch. Read this after `patterns.md` for a full
audit. A quick pass stops at `patterns.md`.

The corroboration gate in `patterns.md` ("Before you act on a pattern") governs
every rule here, and most of them are the weak-alone kind that needs company.

Restored from [conorbronsdon/avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing)
`references/patterns.md`, MIT. Section bodies are upstream's; the header and
entries marked **Added here** are local.

### Transition phrases to remove or rewrite
- "Moreover" / "Furthermore" / "Additionally" → restructure so the connection is obvious, or use "and," "also," "on top of that"
- "In today's [X]" / "In an era where" → cut or state specific context
- "It's worth noting that" / "Notably" → just state the fact
- "Here's what's interesting" / "Here's what caught my eye" / "Here's what stood out" → reader-steering frames. Let the content signal its own importance. If you need a lead-in, make it specific: "The revenue number matters because..." not "Here's the interesting part."
- "In conclusion" / "In summary" / "To summarize" → your conclusion should be obvious
- "When it comes to" → just talk about the thing directly
- "At the end of the day" → cut
- "That said" / "That being said" → cut or use "but," "yet," or "however." Don't overuse any one of them.

### Aphorism formulas
- Slot-fill profundity: "X is the language of Y," "X is the currency of Z," "the architecture of trust," "X becomes a trap," "X is not a tool but a mirror." The formula turns an ordinary claim into something that sounds quotable without adding precision — the shape does the persuading instead of the evidence.
- Fix: replace the formula with the concrete claim it gestures at. "Symmetry is the language of trust" → "symmetric layouts feel more predictable to users."
- Distinct from significance inflation (which puffs up an event's importance) and from the persuasive-authority tropes under Confidence calibration (which announce depth): this pattern manufactures a general law out of a specific observation.
- Carve-out: quotations and established idioms ("time is money") are attributed speech or common coin — leave them. Adapted from `blader/humanizer` P32.

### Transformation crutch
- Flag repeated unexplained relabeling across a passage: "the concern turns into panic," "a feature turns into a strategy," "the risk becomes real." Ask what changed; read the surrounding passage before deciding the explanation is missing. Treat this as a P2 clarity judgment, not evidence of AI authorship.
- For a flagged passage, ask what changed. If the writer supplies the missing action, threshold, or consequence, use those supplied facts in the rewrite; never invent a mechanism or actor. If the explanation was already present, apply the pass conditions below instead of rewriting it under this rule.
- Preserve literal transformations ("water turns into ice"), supported metaphors, and changes explained anywhere in the passage ("the queue turns into a bottleneck" after a stated capacity limit). Deliberate summaries of explained changes pass, including multiple summaries in one passage. Repeated labels with no explanation still flag. Adapted from `welttowelt/stop-slop-refined` ([#108](https://github.com/conorbronsdon/avoid-ai-writing/issues/108)).

### Copula avoidance
- AI text avoids "is" and "has" by substituting fancier verbs: "serves as," "features," "boasts," "presents," "represents." These sound like a press release.
- Default to "is" or "has" unless a more specific verb genuinely adds meaning.

### Subjectless fragments and agentless passives
- Sentences with the subject dropped or the actor hidden: "No configuration file needed." "The results are preserved automatically." "Support for nested queries was added." The clipped no-subject form is a shape LLMs reach for when compressing feature descriptions, and the passive hides who does what.
- Fix: name the actor when it clarifies — "You don't need a configuration file. The CLI preserves results automatically." Prefer active voice unless the actor is irrelevant.
- Carve-out: terse reference registers where the fragment is the correct form — README feature lists, changelog entries, parameter docs, commit subjects ("No breaking changes"). Flag in flowing prose; skip in docs and casual registers (see the tolerance matrix). A single deliberate fragment for emphasis is rhythm, not a tell. Adapted from `blader/humanizer` P13.

### False agency
- Flag an obscured accountable decision-maker: "The decision emerged after the offsite" leaves unclear who made the choice. Apply only when a specific person or team exercised judgment or choice and naming them matters to the passage. This is a P2 clarity judgment, not evidence of AI authorship.
- Name the actor only when the source identifies them. If the passage identifies the board as the decision-maker, write "The board decided after the offsite." Otherwise ask who decided; do not invent "we," a team, or an interpreter for the data.
- Preserve conventional personification ("the data shows adoption is early"), literal system behavior, and collective shorthand ("the market rewards shipping"). "The culture shifted" may describe emergent change; "a bet lives or dies on distribution" expresses causal dependence. Neither alone establishes a hidden decision-maker. A consequential choice attributed to an abstraction, with its responsible actor missing, still flags. Adapted from `welttowelt/stop-slop-refined` ([#108](https://github.com/conorbronsdon/avoid-ai-writing/issues/108)).

### Filler phrases
- Strip mechanical padding that adds words without meaning:
  - "It is important to note that" → (just state it)
  - "In terms of" → (rewrite)
  - "The reality is that" → (cut or just state the claim)
- Note: "In order to," "Due to the fact that," and "At the end of the day" are covered in the word/phrase table and transition sections above — don't duplicate rules.

### Generic conclusions
- "The future looks bright," "Only time will tell," "One thing is certain," "As we move forward" — these are filler disguised as conclusions. Cut them. If the piece needs a closing thought, make it specific to the argument.

### Notability name-dropping
- AI text piles on prestigious citations to manufacture credibility: "cited in The New York Times, BBC, Financial Times, and The Hindu." If a source matters, use it with context: "In a 2024 NYT interview, she argued..." One specific reference beats four name-drops.
- Related — **historical analogy stacking**: rapid-fire lists of past technologies or companies to borrow their weight ("like the printing press, the telegraph, and the internet before it"). The montage substitutes for the argument. Name the one parallel that does analytical work and say what it explains, or cut. Source: tropes.fyi (Historical Analogy Stacking).

### Vague third-party validation
- AI manufactures credibility by pointing at an **unnamed** external authority, usually paired with a generic superlative: "an outside party measuring the same models everyone runs and putting us on top," "independent testing confirms," "third-party benchmarks show we lead," "analysts agree," "studies consistently show." The authority is faceless and the claim unfalsifiable — the reader can't tell who measured what, against whom, or go check.
- Fix: name the source, the test, and the result so a reader can verify it. "An outside party put us on top" becomes "On Stanford's HELM leaderboard (April 2026 run), we ranked first on reasoning latency." If you can't name it, cut the claim rather than dress it up as validation.
- Carve-out: specifically attributed, checkable validation is legitimate and stays unflagged — a named benchmark, a linked report, a dated audit ("SOC 2 Type II, audited by Prescient Assurance"). The tell is the *vagueness*, not the act of citing outside proof.
- Distinct from **Notability name-dropping**: that flags piling on *specific* prestigious names to borrow their weight; this is the inverse move — the authority is deliberately *unnamed*, which is both harder to check and easier to invent. A passage can run both at once (a vague authority plus a superlative); judge each on its own terms. Raised in #39.

### Superficial -ing analyses
- Strings of present participles used as pseudo-analysis: "symbolizing the region's commitment to progress, reflecting decades of investment, and showcasing a new era of collaboration." These say nothing. Replace with specific facts or cut entirely.
- The same move shows up without the -ing: declarative "meaning-telling" that glosses a mundane subject as if it were profound — "this represents a broader shift," "the decision symbolizes a commitment to excellence," "it speaks to a larger trend in the industry." If the significance is real, show it with a specific consequence; otherwise cut. Adapted from `Aboudjem/humanizer-skill` P40.

### Promotional language
- AI defaults to tourism-brochure prose: "nestled within the breathtaking foothills," "a vibrant hub of innovation," "a thriving ecosystem." Replace with plain description: "is a town in the Gonder region," "has 12 startups." If you wouldn't say it in conversation, cut it.

### Formulaic challenges
- "Despite challenges, [subject] continues to thrive" or "While facing headwinds, the organization remains resilient." This is a non-statement. Name the actual challenge and the actual response, or cut the sentence.

### Speculative scenario openers
- "Imagine a world where...", "Picture a future in which...", "Envision a world where..." AI opens an argument with a hypothetical that lists desirable outcomes instead of making a claim. The scenario does the persuading; no evidence is offered.
- Fix: cut the hypothetical and state the real claim. "Imagine a world where every deploy is instant" becomes "Instant deploys would cut our release cycle from a day to minutes."
- Carve-out: fiction, a thought experiment with a stated payoff, and instructional "imagine you have a sorted array" (a teaching device pointing at a concrete example, not a speculative world) are fine. Flag only the world/future-scenario opener that stands in for an argument. Source: tropes.fyi (Imagine a World Where).

### False ranges
- AI creates false breadth by pairing unrelated extremes: "from the Big Bang to dark matter," "from ancient civilizations to modern startups." These sound sweeping but say nothing. List the actual topics or pick the one that matters.

### Inline-header lists
- Bullet lists where each item starts with a bold header that repeats itself: "**Performance:** Performance improved by..." Strip the bold header and write the point directly. If the list items need headers, they should probably be paragraphs.

### List-label periods
- In bulleted lists where each item leads with a short label, LLMs end the label with a period and then run the explanation as a separate sentence. A person writing the same list almost always uses a colon instead. Strongest form: bold labels (`**Intros.**`, `**Content distribution.**`, `**Developer GTM.**` where a human writes `**Intros:**`). Weaker but still a tell: the same shape without bold (`- Intros. Years of conferences and operator network.`) — a short noun-phrase label terminated with a period at the start of a bullet, followed by a gloss. The colon reads as "here's what this label means"; the period reads as a sentence that the following clause then contradicts by continuing. Example tell: `- **Intros.** Years of conferences and operator network.` becomes `- **Intros:** years of conferences and operator network.` Fix the period to a colon and lowercase the start of the gloss, or drop the label and write the point as a plain sentence. Carve-outs: when the label span is a full sentence on its own (not a label introducing a gloss), the period is correct; and for the unbolded form, only flag when the leading fragment is clearly a label (a 1-4 word noun phrase, no verb) — a short complete sentence opening a bullet is fine.

### Title case headings
- AI over-capitalizes headings: "Strategic Negotiations And Key Partnerships" instead of "Strategic negotiations and key partnerships." Use sentence case for subheadings. Title case only for the piece's main title, if at all.

### Hyphenated modifier stacking
- AI stacks compound modifiers: "a high-quality, well-architected, future-proof solution." The individual hyphens may be correct; the tell is the density. Cut to the modifier that matters. Adapted from `blader/humanizer` P26.

### Unnecessary hyphenation
- Check welded open noun phrases: "research-impact aggregator" becomes "research impact aggregator," "data-source strategy" becomes "data source strategy," and "Python-package usage" becomes "Python package usage."
- Close compounds whose standard form is one word: "code-base," "data-set," "time-frame," and "road-map" become "codebase," "dataset," "timeframe," and "roadmap."
- Remove attributive hyphens when the phrase is used adverbially or as a noun: "in real-time" becomes "in real time" and "works out-of-the-box" becomes "works out of the box." Keep the same compounds before a noun: "real-time analytics," "long-term plan," and "out-of-the-box support."
- Preserve established and technical compounds such as "high-quality," "open-access," "third-party," "machine-readable," "server-side," "field-normalized," and "family-owned." Spelling varies by dialect and house style, so ambiguous pairs are judgment calls rather than automatic rewrites.
- Treat a clear hit as P2 copyediting, not evidence of machine authorship. The deterministic detector uses a curated list and excludes code, quoted material, URLs, paths, filenames, and command flags. General attributive-versus-predicate cases stay judgment-only.

### Speculative gap-filling
- When the model lacks a fact, it fills the gap with hedged speculation dressed up as background: "maintains a relatively low public profile," "is believed to have," "likely began his career in," "appears to have studied." These are guesses formatted as statements. Distinct from cutoff disclaimers, which *admit* the gap — this one hides it behind plausible-sounding filler, which is worse because the reader can't tell what's known from what's invented. Cut the speculation, or replace it with a sourced fact. Adapted from `blader/humanizer` P21.

### Unfilled placeholders
- Bracketed slot-fillers that were meant to be replaced before publishing: `[Your Name]`, `[INSERT SOURCE URL]`, `[Describe the specific section]`, `2025-XX-XX`, `<!-- Add citation if available -->`. These are near-definitive evidence that AI-generated boilerplate was pasted without editing. Humans use placeholders in templates too, but rarely ship them. Treat any visible placeholder as a publishing bug: fill it in with real content or delete the sentence entirely.
- Catch the obvious shapes: `\[(?:Your|Insert|Add|Enter|Describe|Specify|Choose)[^\]]+\]`, `\b\d{4}-XX-XX\b`, HTML/Markdown comments with placeholder verbs (`add`, `fill in`, `todo`, `insert`).

### Chatbot citation markup leaks
- Internal citation tokens that leak through when text is copy-pasted from chat UIs: `citeturn0search0`, `contentReference[oaicite:0]{index=0}`, `oai_citation`, `[attached_file:1]`, `grok_card`. These are not patterns — they are fingerprints. Their presence is essentially proof the text was generated by a specific chat tool and pasted without cleanup.
- The fix is mechanical: strip every markup token. If a citation was meaningful, replace it with a real reference. Don't try to humanize the markup — delete it.
- Adapted from `Aboudjem/humanizer-skill` P34. Worth catching even when nothing else in the text reads as AI — the token itself is enough.

### AI-tool URL parameters
- Tracking parameters that AI tools auto-append to URLs they generate, surviving copy-paste into published content: `utm_source=chatgpt.com`, `utm_source=copilot.com`, `utm_source=openai`, `utm_source=claude.ai`, `utm_source=perplexity.ai`, `referrer=grok.com`. Same logic as citation markup leaks — the presence of the parameter is the signature, regardless of what the surrounding text reads like.
- The fix: strip the AI-referrer tracking parameter from every URL that carries one, and leave the rest of the query string alone — the tracking parameter is the signature, and a functional parameter (`?page=2`, `?v=4`) is not evidence of anything. Keep the URL itself if the link is meaningful; lose only the parameter. Adapted from `Aboudjem/humanizer-skill` P35.

### Novelty inflation
- AI text treats established concepts as if the speaker invented or discovered them: "He introduced a term," "She coined the phrase," "a concept nobody's naming," "a failure mode nobody talks about." In reality, most ideas in a conversation are applications of existing concepts, not inventions.
- Two problems. First, it's factually risky: if the concept already has a Wikipedia page or conference talks from last year, claiming novelty makes the writer look uninformed. Second, it flatters the subject in a way that reads as promotional rather than analytical.
- The fix: describe what the person *did with* the concept, not that they discovered it. "Michel walked through how context poisoning works in practice" instead of "Michel introduced a term I hadn't heard before: context poisoning." If you're unsure whether something is novel, assume it isn't and frame accordingly.
- Related patterns to flag: "the failure mode nobody's naming," "a problem nobody talks about," "the insight everyone's missing," "what nobody tells you about." These are engagement-bait framings that claim scarcity of knowledge where none exists.
- Also flag invented labels: pseudo-analytical compound terms coined mid-sentence and never defined ("the supervision paradox," "the context-collapse problem," "a coordination tax"). Naming a concept is not explaining it. Define the term on first use or describe the mechanism instead of branding it. Source: tropes.fyi (Invented Labels).

### Launch-copy dramatic introductions
- "Enter Flowdesk." / "Meet Flowdesk, your new favorite treasury dashboard" / "Say hello to Flowdesk" / "Think Notion meets Figma" — the default LLM shape for product and launch posts, near-deterministic in short social copy. The move introduces the product like a game-show contestant instead of saying anything about it. Sits next to the stale social-ad tells (unlock, elevate, link in bio), but no other entry names the introduction move itself.
- Fix: say what the thing does and for whom. "Meet Flowdesk, your new favorite treasury dashboard" becomes "Flowdesk shows a fund's full treasury position on one screen."
- What the detector actually matches, stated exactly: a sentence-initial `Meet` or `Think`, then **one** capitalized token of 2-30 characters. After `Meet X,` it requires one of four launch-copy heads — "your new favorite", "your new go-to", or "the new home/way/standard", and those last three only when followed by "of" / "to" / "in|for" or by the end of the clause. After `Think X` it requires "meets" and a second capitalized token. Three surfaces stay judgment-only on purpose. "Say hello to X", because "Say hello to Grandma." is ordinary human prose. The bare "Meet X, your new [role]" form, which is how humans introduce colleagues, pets, and babies ("Meet Sarah, your new account manager") — the head list is what keeps that clean. And bare "Enter X.", because it is also how UI and documentation instructions are written: "Enter Password.", "Enter Amount.", "Enter Username — your work email." No terminator class or field-name denylist separates those from "Enter Flowdesk.", and the same shape carries stage directions in dramatic scripts ("Enter Hamlet.") and column-style narrative ("Enter Rashford."). Flag it here by judgment, in launch and announcement copy.
- Disclosed residue and misses, measured. Residue: the heads do not know a product name from a person, so "Meet Alice, your new favorite aunt" and "Think Alice meets Bob at noon" fire. Both are accepted — they are person-name variants of the two surfaces this rule exists to catch, and narrowing them would cost the surfaces themselves. Misses: the name is one token, so a two-token product name is not detected ("Meet North Star", "Think Google Docs meets Microsoft Word"). Before the head nouns required a tail, "Meet Rosa, the new home secretary" and "Meet Emma, the new way station manager" fired — the tail is what separates a launch-copy head from a compound noun. Source: `welttowelt/stop-slop-refined` ([#108](https://github.com/conorbronsdon/avoid-ai-writing/issues/108)).

### Fake-casual register
- The register models emit when asked for a lowercase-casual social voice. Infomercial engagement hooks (above) catch "Plot twist:" and the fake-candid openers; the rest of the kit is what survives cleanup, because it sits closest to an actual casual voice:
  - one-word verdict closers as the whole closing line: "wild." / "insane." / "unhinged."
  - stage directions: "*checks notes*", "*chef's kiss*", "*mic drop*"
  - wink asides: "(yes, really)", "(no, seriously)"
  - label-prefix openers beyond plot twist: "hot take", "fun fact", "pro tip", "PSA", "unpopular opinion" — with or without the colon
  - "because of course it does"
  - the self-QA volley: "Is it fast? Yes. Is it cheap? Also yes."
- The tell across all six props is that the drama is outsourced to the prop instead of carried by the content. A post can clear every vocabulary tier and still be wearing this costume, which is exactly why it slips through cleanup.
- Fix: delete the label and say the thing. Replace the verdict word with the specific surprise. Cut the wink and the stage business. An observation that lands needs no costume.
- Carve-out: a writer whose established voice runs on these props keeps them — the register is a tell for *imposed* casualness, not a ban on playfulness. The detector covers only the mechanical props, and both lists are closed: exactly six asterisk stage directions ("checks notes", "chef's kiss" — the apostrophe is required, straight or curly, because without it "*chefs kiss*" matches the ordinary sentence "At midnight, *chefs kiss* their spouses goodbye" — "mic drop", "takes a deep breath", "sips coffee/tea", "nervous laughter") and exactly four parentheticals, the full (yes|no) x (really|seriously) grid. Verdict closers, label-prefix openers, the self-QA volley and "because of course it does" need register judgment and stay skill-only — no tense gate separates the wink from the ordinary grumble, which uses the same form ("The build failed because of course it did."). Disclosed misses, measured: neighbours in the same register do not fire, including "*checks calendar*" and "(yes, honestly)". A closed list is the price of the precision. Source: `welttowelt/stop-slop-refined` ([#108](https://github.com/conorbronsdon/avoid-ai-writing/issues/108)).

### Emotional flatline
- AI claims emotions as a structural crutch without conveying them through the writing: "What surprised me most," "I was fascinated to discover," "What struck me was," "I was excited to learn," "The most interesting part," and the bare section-header variant: "Interesting part of the project:" / "Interesting thing here:" / "Interesting aspect:". The header form drops "the most" but does the same job — pre-announcing significance the writing hasn't earned.
- Two problems. First, it's tell-don't-show: if the thing is genuinely surprising, the reader should feel that from the content, not from the writer announcing it. Second, these phrases are massively overused as list introductions and transitions. They're filler wearing an emotion costume.
- This pattern isn't always AI. It's also a sign of lazy human writing on autopilot. Flag it either way.
- The fix isn't "never say surprised." It's: if you claim an emotion, the writing around it should earn it. Otherwise cut the claim and present the thing directly.
- Related pattern: "hit differently" / "hits different." AI uses trendy colloquialisms as a shortcut to sound relatable without earning the emotional beat. If something genuinely affected you, describe how. Otherwise cut.

### False concession structure
- "While X is impressive, Y remains a challenge" or "Although X has made strides, Y is still an open question." AI uses this to sound balanced without actually weighing anything. Both halves are vague. Either make the concession specific (name what's impressive, name the actual challenge) or pick a side and argue it.

### Rhetorical question openers
- "But what does this mean for developers?" / "So why should you care?" / "What's next?" — AI uses rhetorical questions to stall before the actual point. If you know the answer, just say it. Rhetorical questions are earned by strong setup, not dropped as section transitions.

### Parenthetical hedging
- "(and, increasingly, Z)" / "(or, more precisely, Y)" / "(and perhaps more importantly, W)" — AI inserts parenthetical asides to sound nuanced without committing. If the aside matters, give it its own sentence. If it doesn't, cut it.

### Numbered list inflation
- "Three key takeaways" / "Five things to know" / "Here are the top seven" — AI defaults to numbered lists because they're structurally safe. Only use numbered lists when the content genuinely has that many discrete, parallel items. If you're padding to hit a number, the list shouldn't exist.

### Reasoning chain artifacts
- "Let me think step by step," "Breaking this down," "To approach this systematically," "Step 1:," "Here's my thought process," "First, let's consider," "Working through this logically" — these are artifacts of chain-of-thought reasoning leaking into published prose. The reader doesn't need to see the scaffolding. State the conclusion, then the evidence.
- Also watch for numbered reasoning steps that read like an internal monologue rather than an argument meant for an audience.

### Sycophantic tone
- "Great question!", "Excellent point!", "You're absolutely right!", "That's a really insightful observation" — these are conversational rewards from chat interfaces, not writing. Remove entirely.
- Distinct from chatbot artifacts: sycophancy specifically validates the reader/questioner rather than just performing helpfulness.

### Acknowledgment loops
- "You're asking about," "The question of whether," "To answer your question," "That's a great question. The..." — AI restates the prompt before answering. In writing, this is pure filler. The reader knows what they asked. Just answer.
- Related pattern: opening a section by summarizing what the previous section said. If the structure is clear, the reader doesn't need a recap.

### Confidence calibration phrases
- "It's worth noting that," "Interestingly," "Surprisingly," "Importantly," "Significantly," "Notably," "Certainly," "Undoubtedly," "Without a doubt" — AI uses these to signal how the reader should feel about a fact instead of letting the fact speak for itself.
- "Here's what's interesting," "Here's the interesting part," "Here are the parts I found interesting" — reader-steering cue that pre-interprets importance. Works when followed by genuinely surprising data; fails when it introduces a restatement of something obvious (which is the AI default).
- One "notably" in a 2,000-word piece is fine. Three in 500 words is AI-style emphasis stacking. Flag by density.
- Related — **persuasive-authority tropes**: "the real question is," "at its core," "fundamentally," "make no mistake," "the truth is." Same move as the calibration phrases above, but they assert depth or stakes instead of feeling: they announce that what follows is important rather than showing it. Cut the trope and lead with the substance. Adapted from `blader/humanizer` P27.

- **Consequence-free explanation:** "This matters because" and "here's why that matters" flag only when they introduce a restatement of importance: "This matters because it is important." Preserve a concrete consequence: "This matters because retries can charge the customer twice." Cut an empty restatement or use an explanation already present; never invent stakes. This addition is a P2 judgment-only clarity check.

### Self-labeling significance
- After listing or describing several items, the writer points back at one and labels it as contrarian / clever / surprising / counterintuitive / key: "That last move is the contrarian one," "This is the interesting part," "That third bullet is the real story," "Here's where it gets clever," "The last bit is the counterintuitive one."
- The label does the work the content was supposed to do. If a move is genuinely contrarian, the reader recognizes it from the description; if it isn't recognizable without the label, the label is unearned. The pattern reads as the writer auditing their own list to flag which item should matter, instead of writing the list so the right item carries the weight on its own.
- Distinct from confidence calibration ("Notably," "Interestingly") which front-loads the cue, and from emotional flatline ("What surprised me most," "The most interesting part") which prefaces a single claim. This pattern back-points after the fact, usually as "[that / this / the Xth / the last] [noun] is the [adjective] one."
- Significance-adjectives that signal the pattern: contrarian, clever, surprising, counterintuitive, interesting, key, important, unusual, smart, brilliant, real, actual.
- Fix: cut the labeling sentence and let the explanation that follows do the work directly. Or restructure so the item you wanted to highlight is positioned first or expanded with specifics, making the label redundant.
- Example. Before: "→ Two separate indexes for tiered storage. That last move is the contrarian one. Co-locating related data usually helps cache locality." After: "→ Two separate indexes for tiered storage. Co-locating related data usually helps cache locality, but splitting the indexes is what makes the hot path cheap." The contrast carries itself; the label is gone.

### Dramatized contrast against the crowd
- A claim propped on an implied lagging crowd, usually stamped with a date: "shipped it in 2022, while everyone else was still debating timelines," "built it in a weekend, while the industry wrote thinkpieces." A strawman with a timestamp — the crowd is invented, so the contrast costs nothing.
- The never-inject list guards the rewrite side of this move (forced contrarianism); this entry flags it on input. Adjacent to significance inflation and self-labeling significance, but the detectable surface is its own: the trailing "while everyone else..." clause with a dismissive verb.
- Fix: state the fact and cut the crowd clause, or name the actual competitor and what they did. If the crowd can't be named, it was invented.
- Carve-out: literal simultaneity is ordinary narrative and stays unflagged — "she read while everyone else watched the movie," "others debated the amendment." The detector matches three branches, gated differently. The debate/speculation branch requires one of "was", "were", "is" or "are", then "still", then a dismissive verb in its **-ing** form, so wire copy, memoir, and fiction using those verbs literally stay clean, as do the adjective ("was still deliberate about"), the passive ("was still debated by pundits"), and the bare present. The think-pieces branch accepts "writing" or "wrote"; the catch-up branch accepts "play", "plays", "played" or "playing", with the auxiliary and "still" both optional. The other two branches carry no "was still" requirement because their wording is stereotyped on its own: "while everyone else wrote think-pieces" and "while everyone else played catch-up". Disclosed residue, measured rather than assumed: the first branch fires on any literal progressive use of its verbs, not just "was still debating" — "while the market was still speculating about the price" and "while others were still arguing about procedure" are ordinary wire copy and both fire. The other two branches fire on literal contrasts of their own: "while everyone else wrote think-pieces from Washington" (a real reporting contrast) and "while everyone else played catch-up in the spring" (sports and classroom narrative). All of that is accepted under precision-over-recall only because the surrounding clause is the tell far more often than not; it is not a gate. The crowd is a closed list too — "everyone else", "others", "the industry", "the market", "the competition" — so measured misses include "while every competitor was still debating timelines" and "while our rivals were still debating timelines". Source: `welttowelt/stop-slop-refined` ([#108](https://github.com/conorbronsdon/avoid-ai-writing/issues/108)).

### Wall-of-text replies (missing line breaks)
- In conversational registers — issue and PR comments, chat, DMs, casual email — humans break a reply at thought boundaries: one idea, then a break, then the next. LLMs default to a single dense block regardless of length. The tell: a reply-length text (roughly under 150 words) with four or more sentences delivered as one unbroken paragraph, no line break anywhere in it.
- Fix: break at thought boundaries. One idea per line-group, the way a person actually types a reply.
- Observed in the wild: a maintainer on a GitHub issue called out an assisted-sounding reply with "I prefer to talk human to human" — the dense block-paragraph shape was the tell, not any single word in it.
- Distinct from paragraph-length uniformity (which is about long-form prose where every paragraph is the same size): this rule is about short, reply-length text having *zero* breaks at all, not uneven ones.
- Carve-out: a single dense paragraph is the *correct* shape in formal, long-form registers — a blog intro, a docs paragraph, a deliberately tight one-paragraph email. This rule fires only in conversational reply registers; never flag continuous long-form prose just because it lacks internal breaks. That false-positive class is exactly why the structural detector was reverted (see `detector/CATEGORIES.md` §C), and why the tolerance matrix below is the wrong home for it: a plain issue comment auto-detects to the `blog` profile, so the scoping has to live in this rule's judgment, not in a per-profile strictness cell.

### Recap-flattery opener
- Replying to a person by summarizing their own work back at them with praise before getting to the point: "Thanks for all the legwork here — the migration script and the rollback plan you worked through are what made this possible." The reader already knows what they did; the recap performs appreciation instead of conveying information.
- Distinct from a genuine thank-you, which is short and moves on. The tell is the *recap* — restating specifics the other person already knows, dressed as gratitude, ahead of the actual point.
- Distinct also from two nearby conversational tells: **Sycophantic tone** (generic validation of the reader — "Great question!") and **Acknowledgment loops** (restating the prompt or the prior section). Those echo the *question or context*; recap-flattery echoes the other person's *own work* back at them, dressed as praise.
- Fix: substance first. If thanks is warranted, one plain clause without the recap: "Thanks for the legwork — this looks right to me, one comment below."
- Observed in the wild: the same exchange that surfaced the wall-of-text tell above — an assisted-sounding reply opened by recapping the maintainer's own prior work back at them before answering the actual question.

### Excessive structure
- Too many headers in short text: more than 3 headings in under 300 words is almost always AI trying to look organized. Merge sections or use prose transitions instead.
- Too many list items: 8+ bullet points in under 200 words means the content should be a paragraph, not a list.
- Formulaic section headers: "Overview," "Key Points," "Summary," "Conclusion," "Introduction" — these are default AI scaffolding. Use headers that tell the reader something specific about what follows.
- Fragmented headers: a heading followed by a one-line warm-up that restates it ("## Performance", then "Speed matters.") before the real content starts. Cut the warm-up; the heading already did that job. Adapted from `blader/humanizer` P29.

### Diff-anchored writing
- Documentation or comments narrating a change instead of describing the thing as it is: "This function was added to replace the previous approach of iterating through all items." A reader without the commit history gets archaeology, not documentation. The tell comes from how assistants work — they write docs in the context of the edit they just made, so the prose anchors to the diff; a person documenting later writes from the artifact.
- Fix: describe the current behavior and why it is that way — "This function uses a hash map for O(1) lookups." If the history matters, it belongs in the changelog or the commit message.
- Carve-out: documents that are inherently version-scoped — changelogs, release notes, migration guides, decision records — narrate change correctly and stay unflagged. Adapted from `blader/humanizer` P30.

### Performed-insight phrases
- A family of essayist tics that announce profundity instead of delivering it: "sit with that for a moment", "that's not nothing", "you already know the answer", "the punchline is", "worth naming", "don't take my word for it", "that's the whole point", "is the entire business model", "that's the part nobody mentions", "the only metric that matters", "X is dead; long live X", "that's why it mattered", and the sentence-initial "Turns out". Each stages a reveal; none adds a fact.
- One hit can be a stylistic choice — several in one piece is a tell. Fix: state the claim the phrase was gesturing at. "That's not nothing" becomes the actual size of the thing; "the punchline is" becomes the point, unannounced.
- Carve-out: quoted speech and genuinely comedic writing, where a punchline is literal. The deterministic detector omits "the punchline" and "worth naming" because their literal senses cannot be separated reliably by regex. Source: Simon Willison's [LLM cliché highlighter](https://tools.simonwillison.net/llm-cliche-highlighter).

### Negation chains
- Two or more "no ..." items in a row ("No fluff, no filler, no jargon."), two or more "didn't ..." clauses stacked for rhythm ("It didn't ask. It didn't wait."), and the negated-then-repeated verb ("Don't call it a pivot. Call it a correction."). The chain performs decisiveness; the items are rarely load-bearing.
- Fix: say what the thing *is*. One negation earns its place when the reader would otherwise assume the opposite; a chain of them is a drumroll.
- Distinct from Manufactured punchlines (same-shape *fragments* for drama) — this fires on the negation structure itself, fragments or not. Source: Simon Willison's LLM cliché highlighter.
- Carve-outs: mid-sentence factual inventories ("the endpoint takes no arguments, no headers, and no body") and sequential narration with restated subjects ("I did not sleep well. I did not eat breakfast.") are ordinary prose. The detector matches only sentence-initial chains of three or more short "no ..." items and comma-joined "did not ..." chains with the subject elided; two-item chains and everything outside those narrow forms are judgment calls.

### Dev-blog boilerplate
- Stock simplicity claims from developer marketing: "batteries included", "it just works", "zero config", "sane defaults", "small enough to fit in your head". Each substitutes a slogan for a property you could demonstrate.
- Fix: name the concrete behavior — "installs with no config file" beats "zero config"; "the whole API is six functions" beats "fits in your head".
- Carve-out: quoting a product's own tagline, or discussing the phrase itself. The deterministic detector omits "batteries included" because a software slogan and literal package contents have the same surface form. Source: Simon Willison's LLM cliché highlighter.

### Stacked rhetorical questions
- Two or more questions fired in a row, usually fragments after the first: "Do I know how it works? Where it breaks? Which corners it cut?" Extends Rhetorical question openers (one question stalling before a point) to the chain form, which reads as a performance of curiosity.
- Fix: keep at most one question, answer it, and convert the rest into the statements they were hiding. Judgment call rather than a detector: interviews, FAQs, and dialogue stack questions legitimately, and a regex can't read register. Source: Simon Willison's LLM cliché highlighter.

### Same-opener sentence runs
- Three or more consecutive sentences opening on the same word ("Maybe nobody needed it. Maybe it solved the wrong problem. Maybe the timing was off."), and its cousin: consecutive sentences built on the same repeated skeleton ("A cart is an object in the system. A chat room is an object in the system."). Deliberate anaphora is a rhetorical device; LLMs reach for it constantly, so a run that isn't doing persuasive work is a tell.
- Fix: keep the first, vary or merge the rest. Judgment-only: whether the repetition is earned is exactly what a pattern can't read, and pronoun-opener runs ("He... He... He...") are ordinary narration. Source: Simon Willison's LLM cliché highlighter.

### Stranded auxiliary contrast
- Landing a reversal on a bare auxiliary: "The tool died; the data didn't." / "Reading mostly passed. Writing didn't." One is a fine sentence; as a recurring rhythm it is a signature LLM move — the clipped contrast poses as earned insight.
- Fix: ration it. If the piece already has one, write the next contrast out in full. Judgment-only: the single instance is legitimate style, and only density across a piece distinguishes voice from tic. Source: Simon Willison's LLM cliché highlighter.

### Colon into a triple
- A colon opening onto exactly three comma-separated items: "separate ports, processes, and local state." The most common shape LLM prose uses to sound concrete — three is the default rhythm, whether or not the content has three parts.
- Fix: audit the list. If there are really two things, or four, write that; if the items are padding, cut to the one that matters. Judgment-only, and noisy by design in technical writing, where three-item lists are often just true — weigh it by genre, not per hit. Source: Simon Willison's LLM cliché highlighter.

### Manufactured punchlines and staccato drama
- A run of clipped fragments engineered so every beat lands like a quotable closer: "It had no preference for symmetry. No aesthetic prior. No nostalgia for human taste. The old rules were gone." Each fragment poses as a reveal; stacked, they read as a drumroll.
- This composes with Rhythm and uniformity below, which encourages fragments and varied lengths: variation is the human signal, and one short sentence that lands a point is exactly that. The tell here is the opposite of variation — three or more same-shape fragments in a row, each carrying manufactured drama.
- Fix: keep the one fragment that earns its emphasis and fold the rest into ordinary sentences with the claim stated: "AlphaEvolve did not favor symmetry or human-looking designs, which made some of the older assumptions less useful." Adapted from `blader/humanizer` P31.

- **Repeated empty concessions:** Pairs such as "Not always. Not perfectly." flag at P2 only when repeated across a passage to stage honesty without explaining where the claim fails. Preserve two meaningful concessions ("Not during failover. Not for expired tokens.") and an isolated intentional pair. Fold repeated empty concessions into a limitation already stated in the source, or cut them; never invent a failure case. Adapted from `welttowelt/stop-slop-refined` ([#108](https://github.com/conorbronsdon/avoid-ai-writing/issues/108)).

- **Repeated setup/reversal punchlines (P2, judgment-only).** A paraprosdokian reverses the expectation set up by the first part of a sentence. Review two or more such reversals in one piece, especially in hooks, closers, or final list items. Flag only when the repeated reversals replace concrete claims with generic surprise or deflation; repetition alone is not a finding. This subtype concerns setup and payoff across sentences, while the fragment rule above concerns three or more same-shape beats. Treat it as a clarity and rhythm edit, not proof of AI authorship. Adapted from [cland4449's contribution (#130)](https://github.com/conorbronsdon/avoid-ai-writing/pull/130).
- Flag example, in an otherwise unexplained passage: "We planned for every failure mode. Except the one that happened. The migration went smoothly, which is how we knew something was wrong." Both reversals stand in for the missing explanation. A repeated scale-then-deflate line such as "Four steps, and only one of them is yours" belongs here only when the passage never explains the steps or the reader's role. Nearby negative parallelism or staccato drama can support the judgment but does not override these conditions.
- Pass: one supported, voice-appropriate reversal, and repeated reversals that communicate concrete distinctions. "We rebuilt billing to group charges by project. Your invoice total didn't change" carries a specific contrast and stays. Intentional comedy, fiction, speeches, and quotations stay, including pieces with multiple reversals. Read the surrounding passage before deciding that an explanation is missing.
- Fix: keep the supported claim and remove the empty twist. "We planned for every failure mode. Except the one that happened" becomes "We missed a failure mode." If the writer has not named the failure, ask for it; do not invent disk failures, network partitions, clock skew, or other causes. Preserve supplied facts and intentional voice.

### Rhythm and uniformity

These aren't individual word or phrase problems — they're patterns in how the text flows as a whole. AI text is metronomic; human text has varied rhythm.

**Structure is the #1 detection signal.** AI detection tools (including Pangram, which trains a classifier on 28M human documents) weight structural regularity higher than vocabulary. Consistent sentence construction, uniform pacing, and symmetrical phrasing patterns are harder to mask than swapping out a few flagged words. If you fix every word on the Tier 1 list but leave the rhythm untouched, the text still reads as AI-generated.

- **Sentence length uniformity**: If most sentences are 15–25 words, the text sounds robotic. Mix short punchy sentences (3–8 words) with longer flowing ones (20+). Fragments work. Questions break the monotony.
- **Paragraph length uniformity**: If every paragraph is 3–5 sentences and roughly the same size, vary deliberately. Some paragraphs should be one sentence. Some should be longer.
- **Vocabulary repetition vs. synonym cycling**: AI either repeats the same word mechanically or cycles through synonyms conspicuously. Human writers repeat when the word is right and vary when it's natural — there's no formula.
- **Read-aloud test**: If the text sounds like it could be read by a text-to-speech engine without sounding weird, it's probably too uniform. Human writing has rhythm that resists robotic delivery.
- **Missing first-person perspective**: Where appropriate, the writer should have opinions, preferences, and reactions. AI is relentlessly neutral. If the piece is supposed to have a voice, the absence of "I think," "in my experience," or a stated preference is itself an AI tell.
- **Over-polishing**: Aggressively editing out every irregularity can push human writing *toward* AI statistical profiles. Natural disfluency, idiosyncratic word choices, and uneven pacing are what keep text out of the "AI-generated" classification. Don't sand away all personality in pursuit of clean prose. This skill should make writing sound more human, not less — if you apply every rule at maximum strictness, you risk creating the very uniformity you're trying to avoid.

### Vocabulary diversity (stylometric)

In longer pieces (200+ words), look at how much vocabulary the text actually uses. The type-token ratio (TTR) — distinct word types divided by total tokens — is a classical stylometric signal that's easy to read by eye. Human prose at this length usually lands somewhere around 0.50–0.65 in English. AI text trends flatter, sometimes drifting under 0.40 when the model gets locked on a small vocabulary loop.

A very low TTR is not by itself proof of AI authorship — narrow topics, technical reference material, and second-language writing all legitimately compress vocabulary. But on general prose where you'd expect range (essays, articles, social content over ~200 words), a TTR below 0.40 is worth a second look. The fix is rarely to thesaurus the text; it's to broaden the *what* — name specific things, cite specific cases, replace a re-used abstract noun with the concrete instance behind it.

This is the first of four stylometric signals on the roadmap. The others (sentence-length burstiness as a continuous measure, function-word z-scores against a human-prose reference, POS-bigram log-odds) require either a POS tagger or a reference distribution and aren't implemented as detector categories yet.

### Paragraph-reshuffle immunity (structure test)
- A writer-side diagnostic, not a regex: can you swap two body paragraphs without breaking the piece? If the order doesn't matter, you've written a list of points, not an argument that builds. AI prose often fails this — each paragraph is a self-contained module with no load-bearing connection to its neighbors.
- The fix is structural, not lexical: establish a through-line where each paragraph depends on the one before it. If the paragraphs are genuinely independent, decide whether the piece should be an explicit list, or whether it's missing a thesis. Adapted from `Aboudjem/humanizer-skill` P38.

### Treadmill effect / low information density (content test)
- Another writer-side test: read each paragraph and ask "what's actually new here?" AI prose frequently restates the premise in fresh words instead of advancing it — lots of motion, no distance covered. The tell is that you could cut 40-60% and lose no information.
- The fix: for each paragraph, name the one fact, claim, or turn it contributes. If there isn't one, cut it. If there is, lead with it and drop the throat-clearing. Adapted from `Aboudjem/humanizer-skill` P43.

### When to rewrite from scratch vs. patch

If the text has 5+ flagged vocabulary hits across multiple categories, 3+ distinct pattern categories triggered, and uniform sentence/paragraph length, patching individual phrases won't fix it — the structure itself is AI-generated. Advise a full rewrite: state the core point in one sentence, then rebuild from there.

---

### Vague connection or association

- **Added here** from `blader/humanizer` §14, absent upstream. Watch for
  `associated with`, `in association with`, `connected to`, `in connection with`,
  `linked to`, `tied to`. The text says two things are connected without saying
  how: "He was associated with the leadership of ExampleCorp" hides whether he
  was the CEO, a board member, or a consultant.
- Fix: name the relationship the source gives. "He is associated with the
  Rajhans Orchestra, which he founded and conducts" becomes "He founded and
  conducts the Rajhans Orchestra."
- Carve-out, and it is the important half: if the source does not say what the
  relationship was, keep the vague wording. Inventing a role is a fabricated
  specific, which "Never inject these" in SKILL.md forbids outright.

### A heading repeated in the first sentence

- **Added here** from `blader/humanizer` §24, absent upstream. A heading is
  followed by a one-line paragraph restating it before the real content starts:
  "## Performance" then "Speed matters." then the actual point.
- Fix: cut the restatement and let the heading stand once.
- This is the rule behind `lint.py`'s `opening_restates_title` flag. The check
  compares the first sentence against the document title, and it only means
  anything when the document has a real markdown heading, so read the flag
  against this rule rather than acting on it directly.
