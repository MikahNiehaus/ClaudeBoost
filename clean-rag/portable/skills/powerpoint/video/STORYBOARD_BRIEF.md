# Storyboard brief

You write `storyboards/<name>.json` for a narrated talk. A Remotion composition turns it into an animated 1080p video that plays with the narration. The audio is the master. Your job is to put the right visual on screen at the right moment so the listener understands the topic faster.

Work in the video project folder. For each talk you are given:

1. Run `python outline.py <name>` to see every spoken paragraph, its start time, and its words with a word index marker `{n}` every five words.
2. Read `scripts/<name>.md` for context.
3. Write `storyboards/<name>.json`.
4. Run `python validate.py <name>` and fix every error until it prints OK.
5. Optionally render a still to check layout (see end).

## Format

```json
{"title":"Talk title with spoken spelling","scenes":[ {scene}, ... ]}
```

Every scene has `kind`, `para` (paragraph index from the outline), optional `w` (word index inside that paragraph where the scene starts, default 0), optional `heading` (short title above the card, shown for all kinds except title and quote), optional `cues` (word indexes inside the paragraph at which each list item appears; default is an even spread, so set cues whenever the narration names items at specific moments). A scene lasts until the next scene starts. The first scene is a `title` at para 0 w 0.

Kinds and fields:

- `title`: `title`, `subtitle?`
- `bullets`: `items` (3 to 5 short strings)
- `flow`: `nodes` (3 to 5 short strings, drawn left to right with animated arrows), `loop?` (short text on a return arrow)
- `compare`: `left` and `right`, each `{title, items:[2 to 4 strings]}`
- `stat`: `value` (a number or short figure that the narration actually says), `label`, `note?`
- `steps`: `items` (3 to 5 numbered steps)
- `term`: `term`, `definition`
- `graph`: `nodes` (strings), `edges` (pairs of node indexes), `layout` (`cycle`, `star` or `layers`)
- `quote`: `text`, `by?`
- `search` (worked example): `query`, `docs` (3 to 5 of `{text, score}`, score 0 to 1), `pick` (indexes of the top hits). Shows a query scoring documents. Cues reveal each document.
- `walk` (worked example): `nodes`, `edges`, `path` (node indexes visited in order, at least 2), `layout` (`cycle` or `star`). A highlight travels node by node along the path. Cues time each step.
- `trace` (worked example): `nodes` (3 to 4 stages), `data` (one short sample value per stage, same count). A packet moves through the stages and the sample value for each stage appears. Cues time each stage.
- `code` (worked example): `lines` (1 to 8 lines of at most 60 characters, one entry per line, indent with spaces, no tabs or line breaks inside an entry). Lines type in one by one. Cues time each line.
- `chat` (worked example): `messages` (list of `{who, text}`, who is `user`, `attacker`, `model` or `system`). Bubbles type out. Cues time each message.
- `bars` (worked example): `bars` (list of `{label, value}`), `max?`, `unit?`. Bars grow at their cues. Use only for numbers the narration says.

Worked examples. The user wants to SEE the concept working, not read about it. Every talk needs at least 4 worked example scenes (kinds search, walk, trace, code, chat, bars) placed where the narration explains a mechanism: a retrieval query scoring documents, a graph traversal, data passing through pipeline stages, a prompt injection exchange, a snippet of the real logic. Sample values in these scenes (made up queries, scores, vectors, code) are illustration and are exempt from the "number must be in the narration" rule, but they must be plausible, consistent with what the narration says, and never claim a real benchmark or product fact. A scene shows an EXAMPLE badge automatically. Text rules (no colons, dashes, hyphenated words) still apply. For `code`, avoid colons only where possible; `def f(x):` is fine because validate.py skips colons in `lines`.


## Rules, all enforced by validate.py or by review

- Cover the whole talk. A new scene about every 8 to 25 seconds, never longer than 45 seconds, never shorter than 2 seconds. A 480 second talk needs roughly 25 to 40 scenes. Use every paragraph.
- Only use spoken paragraphs. Never anchor to a paragraph marked UNSPOKEN.
- Visualise the mechanism, not the sentence. If the narration describes a pipeline, draw a `flow`. If it contrasts two approaches, use `compare`. If it lists what to check, use `steps` or `bullets`. If it explains a structure of linked things, use `graph`. If it gives a figure, use `stat`. If it defines a word, use `term`. Vary the kinds. Do not use `bullets` for more than a third of the scenes.
- Every card item is a short phrase of at most 7 words. Plain words. No sentences copied from the script.
- A scene must start when its subject starts being spoken. Pick `w` at the first word of the thing being named. Set `cues` so each item appears as it is spoken.
- Never put a number, name, tool, or claim on a card that the narration does not say in that paragraph or the next one. Do not add facts. Do not add sources the script lacks.
- No colons and no dashes (hyphen, en dash, em dash) anywhere in card text. No hyphens inside words: write "bi encoder", "re index", "R A G", "L L M" the way the script spells them for speech. Numbers on cards may be digits even when the script spells them out; validate.py matches `10` to `ten`.
- Never write how many videos exist or which number this one is.
- Text only, no emoji.

## Optional visual check

```
python render.py <name> --frames 450-451 --out chk.mp4
```
then `ffmpeg -y -i out/chk.mp4 -frames:v 1 out/chk.png` and read the PNG. Frame numbers are seconds times 30. Do this for at most three scenes with the longest text. The commands can take over a minute; run them with a Python subprocess if your shell times out at 120 seconds.

Report: the validate output for each talk, and any scene where you were unsure the card matches the narration.
