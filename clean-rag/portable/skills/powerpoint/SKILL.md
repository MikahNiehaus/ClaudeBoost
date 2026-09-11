---
name: powerpoint
description: WHEN the user asks for a slide deck, a presentation, a PowerPoint, a .pptx, or asks to turn an explanation of any topic into slides; build the deck into the active workspace with python-pptx, render every slide and actually look at it before handing it over, then open it. Also covers narrating a finished deck to an mp4 with per slide voiceover and crossfades. USE whenever a .pptx is an input or an output, whatever the subject matter.
allowed-tools: Read, Write, Edit, Bash, Glob
---

# powerpoint

Builds a deck on any topic into the active workspace, checks it by rendering it
and looking at the images, and opens it. Optionally narrates it to an mp4.

Topic agnostic. Nothing here knows or cares what the deck is about; the subject
comes from the user.

## The helper script

Every command below calls one bundled script. It is installed alongside this
file, so the path is stable:

```
${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py
```

Use that path verbatim, in braces and inside double quotes, exactly as written
in each block below. There is no `CLAUDE_SKILL_DIR` environment variable in
Claude Code; a command written against one resolves to nothing and fails. If
this skill was installed somewhere other than `~/.claude/skills` (a plugin
marketplace checkout, for instance), find it once with Glob on
`**/skills/powerpoint/scripts/pptx_env.py` and substitute that path throughout.

Run `pptx_env.py --help` for the full command list.

## Step 1: check the environment

```bash
python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" doctor
```

Prints each dependency, what it is for, the install command if it is missing,
and where output will land. Only `python-pptx` is required. LibreOffice,
poppler, ffmpeg and edge-tts each gate one later step; when one is absent, say
which step the user loses and carry on rather than stopping.

## Step 2: decide where the file goes

```bash
python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" workspace
```

Prints JSON with `workspace_path` and `project_path`. Write the deck to
`workspace_path`. Do not compute `workspace/<id>/` from the current directory:
that guess picks the wrong workspace when more than one session is open, which
is why the helper goes through ClaudeBoost's resolver instead. If no workspace
is active the helper falls back to the current directory; that is fine, but
tell the user where the file went.

## Step 3: write a generator script

Write a Python script that builds the deck, run it, and keep it. Two reasons:
the first render always needs corrections, and a script re-runs while a
sequence of individual tool calls does not. Do not hand-write the XML.

```python
from pptx import Presentation
from pptx.util import Inches, Pt

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)   # 16:9
blank = prs.slide_layouts[6]        # layout 6 is named "Blank" in the default template
slide = prs.slides.add_slide(blank)
```

The default template is 10 x 7.5in (4:3), so set the slide size explicitly
unless the user wants 4:3.

Behaviour of the library that costs time if you learn it from a broken render
instead (all four confirmed against python-pptx 1.0.2):

- Assigning `text_frame.text` throws away run-level formatting. It rewrites the
  frame from scratch, splitting on `\n` into one paragraph per line with a
  single unformatted run each; a bold run set beforehand comes back with
  `font.bold is None`. Build paragraphs with `add_paragraph()` and runs with
  `add_run()`, then set `run.text`, whenever the formatting matters.
- `Slides` exposes exactly one method that creates a slide: `add_slide(layout)`.
  There is no copy, duplicate, move or reorder (still an open feature request,
  scanny/python-pptx#1141). Emit repeated slide types from a loop over data in
  your script.
- `add_picture` reads the raster formats `Image` understands: PNG, JPEG, GIF,
  BMP, TIFF. SVG is not among them (scanny/python-pptx#885, #394). Rasterise
  vector art before you place it.
- `MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE` is written into the file but nothing
  computes the resulting font size, so it has no effect until PowerPoint itself
  reflows the shape (scanny/python-pptx#973). Size text boxes for the longest
  string you will actually put in them and confirm in step 4.

Place shapes yourself with explicit `Inches()` coordinates rather than relying
on placeholder positions from the built-in layouts.

Put the spoken version of each slide in
`slide.notes_slide.notes_text_frame.text`. It is useful on its own and it is
the starting point for narration if a video follows.

## Step 4: render it and look at the images

Not optional, and not replaceable by re-reading the generator. Overlap and
overflow are geometric facts about the rendered output; they are not visible in
the code that produced it.

```bash
python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" topdf deck.pptx ./render
"$(python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" pdftoppm)" -png -r 200 ./render/deck.pdf ./render/slide
```

The second command asks the helper for poppler's absolute path first, because
`pdftoppm` is frequently installed without going on `PATH`. Then Glob
`./render/slide-*.png` and Read every image.

**200 dpi and PNG, not 110 and JPEG.** This used to be `-jpeg -r 110`, which
made every deck look like the images in it were broken. At 110 dpi a 13.33 inch
slide is only 1467 pixels wide, so a 1269 pixel diagram is resampled down to
roughly 409 pixels and then JPEG compressed. Vector text survives that because
it is re-rendered at the new size; an embedded raster image does not. The result
is a preview with crisp titles and a smeared diagram, which reads as "the deck
is blurry" when the deck is fine. Measured on a real render, not assumed. 200
dpi gives 2667 pixels across and keeps a raster image legible; PNG removes the
compression artefacts on top of that.

If a diagram still looks soft at 200 dpi, the image really is too small and the
fix belongs upstream in the render, not here.

Check each rendered slide for:

- text pushed outside its box, or any element crossing the slide boundary;
- shapes drawn on top of each other where that was not the intent;
- text whose contrast against what is behind it falls under WCAG 1.4.3 AA,
  4.5:1 for body text and 3:1 at 18pt and above (W3C, Understanding SC 1.4.3);
- one region packed while another is empty, when the slide was meant to balance.

LibreOffice substitutes any font the machine does not have, and the substitute
rarely has identical metrics, so treat a line that only just fits in the render
as a line that does not fit. Leave slack rather than tuning to the millimetre.

Fix the generator and re-run it. Never edit the .pptx directly: the next run of
the script would discard the edit. If LibreOffice is missing, `topdf` returns
nothing; say plainly that the deck went out unrendered and ask the user to look
at it.

## Design decisions this skill leaves to you

Short list, because these are the ones a render can actually confirm:

- Choose type sizes far enough apart that the hierarchy is unambiguous at a
  glance. Titles around 36-44pt against body text around 14-16pt reads as
  deliberate; a 4pt gap reads as a mistake.
- Prefer fonts that ship with the operating system or with a perpetual Office
  install. Aptos is a Microsoft 365 cloud font (Microsoft, "Cloud fonts in
  Office"), so it is absent on older Office and on LibreOffice, and both your
  render and the user's copy will silently substitute something else.
- Pick colours from the subject rather than from a default. Give one colour the
  majority of the surface area and keep the accent rare enough to mean
  something.
- Give each slide one element that is not a paragraph of text: a chart from
  `slide.shapes.add_chart`, a table, a rendered mermaid diagram, an annotated
  screenshot, or a single large figure. The next section covers the last two,
  which carry most of the visual weight in a technical deck.
- Anything the deck asserts as fact must come from the user or from something
  you actually looked up. Do not invent statistics to fill a chart.

## What never goes in the deck

Two rules, both from repeated feedback on real decks. They pull in opposite
directions and both are load bearing.

**Cut the process. Keep the finding.** The reader wants the conclusion and the
evidence, not the route. Delete every sentence about how you got there:

- Agent and tool names. No "swiper found", "researcher reported", "bad-cop
  flagged", "the RAG search returned". Internal machinery means nothing to the
  audience and reads as filler.
- The investigation. How many files were read, what was grepped, what order
  things surfaced in, which hypothesis was tried first and abandoned.
- Self-congratulation about rigour. "Verified by execution" as a standalone
  claim is not evidence. The number is the evidence.

Evidence is a measurement, a command's output, a file and line, a screenshot.
Evidence is never a description of the work that produced it. A slide that
spends half its space on method has half a slide left for the point.

**Keep the exact technical term, and say why.** This is not a contradiction of
the rule above. Cutting process narration frees the words to spend here.

Name the pattern, the principle, or the tradeoff precisely: "fail-open guard",
"denylist versus allowlist", "read-modify-write race", "atomic replace",
"capability removal rather than input sanitising", "idempotent write". Then give
the plain meaning in one line, then why it applies to this decision rather than
the alternative.

The term alone teaches nothing. The plain meaning alone leaves the reader without
the vocabulary to reason about the next decision or to discuss it with another
engineer. Give both, in that order, and name the alternative you rejected.

A deck explaining a design is also teaching the design. Vague-but-friendly is the
worse failure here, not the safer one.

## Visuals: mermaid to explain, screenshots to prove

Two kinds of picture, and they do not substitute for each other. Picking the
wrong one is the common failure. A hand drawn box diagram of something that
already exists is weaker than a capture of it. A screenshot of an architecture
that has no single screen is weaker than a diagram.

- **Mermaid explains.** Anything whose subject is a shape rather than a surface:
  architecture, a flow, a state machine, a sequence, a decision tree, a
  dependency graph.
- **An annotated screenshot proves.** Anything the deck asserts is real: the
  feature works, the test passed, the number came out, the page looks like this.

A slide that claims something happened and shows only a diagram of it happening
carries no evidence. That is the same standard the QA rules apply to a test
report, for the same reason: a drawing of a result is not a result.

### Mermaid

Render to PNG and place the image. Do not rebuild the diagram out of pptx
shapes.

```bash
python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" mermaid diagram.mmd out.png 3
```

The third argument is a scale factor, and 3 holds up at projector size. `doctor`
reports a `mermaid` row that performs a real render rather than checking whether
`mmdc` is on `PATH`, because those two answers differ in practice: mermaid-cli
bundles puppeteer but not a browser, so an install whose puppeteer cache has
gone stale has a working `mmdc` that renders nothing.

The helper resolves a Chromium itself, in order: `PUPPETEER_EXECUTABLE_PATH`,
Playwright's cache, puppeteer's cache, then an installed Chrome or Edge, with a
separate candidate list per platform. Never hardcode a browser path into a
generator script. Every one of those directories is version numbered and differs
per machine, which is why this resolves rather than assumes.

It fails loudly on purpose. mermaid-cli can exit 0 having written nothing, or
having written a zero byte file, so the helper returns a path only after
confirming the file exists, is at least 512 bytes, and starts with the PNG magic
number. Treat `None` from it as a failed step under the abandon rule below, not
as a slide to build without its diagram. A deck with a silently missing diagram
is exactly what this check exists to prevent, because nobody notices until the
meeting.

One idea per diagram. A mermaid graph with thirty nodes renders at a size nobody
in the room can read.

**Placing it without making it blurry.** Two rules, both measured on a real
deck rather than reasoned about.

Give `add_picture` one dimension and let the other follow, computed from the
PNG's own pixel ratio:

```python
from pptx.util import Emu, Inches
pw, ph = 945, 2046                      # the PNG's real pixels
target_h = Inches(6.0)                  # the space you have
pic = slide.shapes.add_picture(
    png, Inches(0.5), Inches(0.75),
    width=Emu(int(pw * (target_h / ph))), height=target_h)
```

Passing both dimensions independently is how a diagram gets stretched. Passing
neither used to be worse: mermaid-cli writes no `pHYs` chunk, so the PNG never
said how big it was, python-pptx fell back to 72 dpi, and a 945x2046 diagram
landed at **13.1 x 28.4 inches**, nearly four slides tall. `pptx_env.py mermaid`
now stamps the real density (96 dpi per unit of scale), so the same call places
it at 3.3 x 7.1 inches at 288 ppi. An unsized `add_picture` is therefore safe
now, but sizing it deliberately is still better, because you know how much room
the slide has and the PNG does not.

Aim for at least 150 ppi at final size, and 220 or more if it will be
projected. Effective ppi is the PNG's pixel width divided by the inches you
place it across. At scale 3 a diagram has roughly 1300 pixels, so it stays crisp
up to about 6 inches wide and starts to soften past 8. Re-render at a higher
scale rather than stretching.

### Screenshots

Capture the real thing, then mark what the slide is pointing at. An unannotated
screenshot makes the audience hunt for the point, and they will look at the
wrong part of it while you talk.

The annotation machinery already exists in the `walkthrough` skill. Swipe it
rather than rewriting it. Both run through `browser_evaluate` against the page
before the capture:

- A highlight with a popover, driver.js, under "Highlight an element with a
  popover" in `walkthrough/SKILL.md`.
- A numbered callout badge, no library at all, just an outline and a positioned
  div, under "Add a numbered callout badge". Use this when several points on one
  capture need calling out in order.

Browser capture is localhost only, the same rule as everywhere else here.

Crop to the region that matters. A 4K desktop capture scaled into a content
placeholder renders the thing you are pointing at about eight pixels tall.

### Both go in the scratch directory

A mermaid render and a screenshot are pipeline steps that write a file and can
fail partway, the same as the narration steps below. Write them into the same
`tempfile.TemporaryDirectory(dir=workspace_path)` and let only the finished deck
leave it. A PNG written straight into the workspace by a step that then fails
leaves a partial file behind, which is the defect that scratch directory rule
exists to prevent.

Tearing the directory down does not endanger the deck. python-pptx reads and
embeds the image during `add_picture`, not lazily at `save`, so the PNG only has
to exist at the moment it is placed. Verified by deleting the file between
`add_picture` and `save`: the save succeeds and the image is in the package.

## Narrating it to an mp4

On request, and on every `/start` (its step 2c). Requires `edge-tts`, ffmpeg
and LibreOffice; `doctor` reports all three.

`doctor` only reports that a dependency is installed, never that it responds.
`edge_tts.Communicate` sets `sock_connect=10` and `sock_read=60` but leaves
`total=None`, so a TTS endpoint that answers and never finishes holds the call
open with no overall bound — measured past 100 seconds against a socket that
pings and sends no audio. `/start` narrates unattended, so the bound has to
come from the caller.

Write the narration first, as prose meant to be heard, one entry per slide.
Speaker notes are the starting point but are usually too compressed: a viewer
cannot see the presenter, so the audio has to carry the whole point of the
slide.

Every file the steps below produce is an intermediate until the last check
passes: the per-slide mp3s, the concatenated audio stream, the stills, and the
mp4 itself. Write all of them into one scratch directory and move only the
finished artifact out of it. Both halves of the pipeline stream their output to
disk, so an interruption anywhere in it leaves a real partial file rather than
nothing:

- `edge_tts`'s `save()` opens the destination and writes each chunk as it
  arrives (edge-tts 7.2.8, `communicate.py`: `with ... open(audio_fname, "wb")
  as audio`), so cancelling it mid-stream leaves a truncated mp3.
- ffmpeg writes its output the same way, so a missing encoder, a broken input
  or a killed process leaves a truncated, unplayable file at the output path.
  immich hit this on a real transcode pipeline and fixed it exactly here: "On
  ffmpeg success, rename (.tmp) — atomic within the same filesystem. On
  failure, unlink .tmp and rethrow" (immich-app/immich#27973).

Open the scratch directory as `tempfile.TemporaryDirectory(dir=workspace_path)`,
using `workspace_path` from step 2, and do the whole of steps 1 to 5 and the
`ffprobe` check inside it. Two reasons for that exact form. As a context manager
it removes the directory and everything in it on every exit path including an
exception, rather than only on the abandon branch you remembered to write
(Python docs, `tempfile`: "On completion of the context or destruction of the
temporary directory object, the newly created temporary directory and all its
contents are removed from the filesystem"). And siting it under the workspace
rather than the system temp directory keeps the final move on one filesystem, so
it can be an atomic `os.replace`; a cross-device `shutil.move` falls back to a
copy, and a copy interrupted halfway leaves the partial file this rule exists to
prevent.

Abandon on the first failure at any step, not only on a TTS timeout: let the
scratch directory go, keep the deck, name the step and the slide that failed,
and say plainly that no mp4 was produced. Abandoned narration then leaves what a
missing dependency leaves: the deck, and no video.

1. Synthesise each slide's audio to its own file, so you know each duration:
   `edge_tts.Communicate(text, "en-US-AndrewMultilingualNeural", rate="-4%")`.
   The Multilingual voices sound the most natural, and slightly under default
   pace suits explanatory content. Wrap each call in
   `asyncio.wait_for(..., timeout=60)`, and treat the first timeout or error as
   the abandon trigger above rather than paying that bound once per slide.
2. Append about a second of silence to each track (`-af apad=pad_dur=1.0`),
   then concatenate the tracks into one audio stream.
3. Render one still per slide from step 4's JPEGs, each held for its own audio
   duration plus the crossfade length.
4. Chain ffmpeg `xfade` filters. Crossfade *k* goes at
   `sum(durations[:k+1]) - crossfade`, which places the transition inside the
   trailing silence, so each slide has finished appearing before its narration
   begins. That offset also makes the final video length equal the total audio
   length. Assert that equality in the script instead of assuming it.
5. Encode with `libx264 -crf 20 -pix_fmt yuv420p` and `aac` audio.

Afterwards check with `ffprobe` that the video and audio stream durations
agree, and extract a frame from the middle of a transition to confirm it
crossfades rather than cuts. That check is the gate on the move: the mp4 leaves
the scratch directory only after it passes, so a file in the workspace is always
one that was checked.

For audio only, skip the video work and concatenate the narration to an mp3
with a chapter marker per slide. Same scratch directory, same gate: check the
mp3's duration against the sum of the tracks before moving it.

## Step 5: open it

```bash
python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" open deck.pptx
```

`os.startfile` on Windows, `open` on macOS, `xdg-open` elsewhere. Exits
non-zero instead of raising when the platform has no handler, so a headless
machine does not take the run down with it.

## Do not

Copy from Anthropic's `pptx` skill, which is under
`~/.claude/plugins/marketplaces/` when the document-skills plugin is installed.
Its licence forbids reproducing it, copying it, or creating derivative works
from it outside Anthropic's own services. Reading it to learn is fine; its
wording, its structure and its code must not end up in this file or in anything
this skill produces. Everything above is written from python-pptx's own API and
issue tracker and from cited public sources. Its `scripts/office/soffice.py` is
also Linux-only: it talks to LibreOffice over an `AF_UNIX` socket, which does
not exist on Windows, so it would not work here anyway.
