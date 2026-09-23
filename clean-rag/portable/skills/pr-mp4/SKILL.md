---
name: pr-mp4
description: WHEN a ticket is finished and the user wants a narrated video for the pull request, or asks for a PR walkthrough, PR mp4, proof video, or "show me it works" recording; build a deck covering only architecture and proof, embed the real QA screenshots at full size, narrate it, and verify the encode. USE at the end of a ticket, before or just after opening the PR.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# pr-mp4

A narrated video for a pull request. Two questions only: how is it built, and how do we know it works.

## Build it on the powerpoint skill, do not reimplement

`~/.claude/skills/powerpoint/SKILL.md` already knows how to build a deck, render it, look at it, narrate it
and open it. Read it first and use its helper for every environment question:

```bash
python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" doctor
python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" workspace
```

This file only adds what is specific to a PR video. Everything about python-pptx behaviour, slide sizing and
the narration pipeline lives in that skill, including the traps that cost time.

## What goes in, and nothing else

**Architecture.** How the change is put together. The request path end to end. Where the decision is made and
why there. Any rule that is shared across call sites, because that is what stops the paths drifting.

**Proof.** Tests with real counts. The real screenshots. Database evidence if the change touches data.

**One slide for anything proven by test rather than by capture,** if such a thing exists. Say it plainly.

### What must not go in

The reviewer wants the end state, not the journey.

- No discovery narrative. Not "most of this already existed", not "a reviewer found the second half".
- No account of what went wrong on the way, no mistakes, no corrections, no "my own comment claimed".
- No feature tour of things the ticket already describes.
- No status, roadmap or open items list. Those belong in the PR description.

A useful test on every line: does this say what is true now, or what happened? Cut the second kind.

## The screenshots are the point, so make them legible

This is the mistake that ruins a PR video, and it is invisible until you look at a frame.

**Full width, one per slide.** Modern captures are around 2560 px wide. On a 13.333 in slide, place at about
12.1 in and nothing else beside it.

**Do not repeat the annotation text next to the image.** Annotated captures already state what was measured.
Repeating it forces the image small enough to be unreadable, which defeats the whole slide. Give the slide a
short headline, the picture, and the filename.

**Take the numbers from the page, not from the picture.** An overlay saying "toolbar class is d-none, and
offsetParent is null" is evidence. An arrow pointing at empty space is not. Where a claim is about something
absent, count it: wrapping the ajax layer and asserting zero requests proves a Cancel button did nothing in a
way no screenshot can.

## Resolution, the part that goes wrong quietly

**Render above the encode target, never below it.** Both quality failures come from resampling twice.

Work out the render dpi from the widest embedded image, not from the slide:

```
needed dpi  =  image native width in px  /  its placed width in inches
```

A 2560 px capture placed at 12.1 in needs 212 dpi minimum. Use 288 to be safe, which puts a 13.333 in slide at
3840 px, then downsample to 1920.

```bash
PDFTOPPM="$(python "${HOME}/.claude/skills/powerpoint/scripts/pptx_env.py" pdftoppm)"
"$PDFTOPPM" -png -r 288 deck.pdf render/slide
```

**PNG, not JPEG.** A JPEG intermediate adds compression before x264 sees it.

Then encode down, with settings meant for still frames:

```
scale=1920:-2:flags=lanczos,format=yuv420p
libx264 -crf 18 -preset slow -tune stillimage
```

`-tune stillimage` matters. Without it x264 spends bitrate as though the frames were moving.

## Narration

Write it as the deck's own speaker notes, then read them back out of the file when building audio. One source,
so the words on screen and the words spoken cannot drift.

Written to be heard, not read. The viewer cannot see a presenter, so each entry has to carry the whole point of
its slide on its own.

Voice and pacing, plus the crossfade offset maths and the duration assertion, are all in the powerpoint skill.
Follow it rather than inventing a second pipeline.

## Verify before handing it over

Three checks, all cheap, and each catches something the others miss.

**Look at the rendered slides.** Overlap and overflow are facts about the output, not about the generator.

**Extract a frame from the middle of a transition** and confirm two slides are blended rather than cut.

**Compare the stream durations with ffprobe** and assert they agree within a second. Drift means the crossfade
offsets are wrong.

Then read one screenshot slide at full size and ask whether you could actually read it as a reviewer. If not,
the video has failed at its only job.

## Then

Report the path, size, resolution, length and drift. Say which requirement, if any, is carried by test rather
than by capture, so nobody mistakes the video for complete coverage.

Keep the generator scripts next to the deck. The first render always needs a correction, and a script can be
run again while a sequence of one off tool calls cannot.
