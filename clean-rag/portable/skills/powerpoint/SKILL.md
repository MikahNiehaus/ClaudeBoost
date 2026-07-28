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
"$(python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" pdftoppm)" -jpeg -r 110 ./render/deck.pdf ./render/slide
```

The second command asks the helper for poppler's absolute path first, because
`pdftoppm` is frequently installed without going on `PATH`. Then Glob
`./render/slide-*.jpg` and Read every image.

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
  `slide.shapes.add_chart`, a table, a diagram assembled from shapes, or a
  single large figure.
- Anything the deck asserts as fact must come from the user or from something
  you actually looked up. Do not invent statistics to fill a chart.

## Narrating it to an mp4

Only when the user asks. Requires `edge-tts`, ffmpeg and LibreOffice; `doctor`
reports all three.

Write the narration first, as prose meant to be heard, one entry per slide.
Speaker notes are the starting point but are usually too compressed: a viewer
cannot see the presenter, so the audio has to carry the whole point of the
slide.

1. Synthesise each slide's audio to its own file, so you know each duration:
   `edge_tts.Communicate(text, "en-US-AndrewMultilingualNeural", rate="-4%")`.
   The Multilingual voices sound the most natural, and slightly under default
   pace suits explanatory content.
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
crossfades rather than cuts.

For audio only, skip the video work and concatenate the narration to an mp3
with a chapter marker per slide.

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
