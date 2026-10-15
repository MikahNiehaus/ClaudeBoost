"""Render a deck file's slides to stills, one per narration beat, and narrate them to an mp4.

Usage: python narrate.py DECK.py [video]
DECK.py defines BRAND and slides(); see ../example_deck.py.
"""
import asyncio
import html
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pptx_env

HERE = Path(__file__).resolve().parent
VOICE, RATE = "en-US-BrianMultilingualNeural", "-10%"
BEAT_GAP, SLIDE_GAP, CF_BEAT, CF_SLIDE = 0.35, 0.9, 0.35, 0.6
WPM = 150


def need(ok, msg):
    """A check that python -O cannot skip."""
    if not ok:
        raise ValueError(msg)


def section(text, start, stop=None):
    """Lines from the first one starting with `start` up to the first after it starting with `stop`."""
    lines = text.splitlines()
    i = next((n for n, l in enumerate(lines) if l.startswith(start)), None)
    need(i is not None, f"no line starts with {start!r}")
    j = next((n for n, l in enumerate(lines[i + 1:], i + 1) if stop and l.startswith(stop)), len(lines))
    return "\n".join(lines[i:j])


def page(path, start, stop=None):
    """A markdown file's section as HTML, with its relative images pointed at real files."""
    import markdown
    path = Path(path)
    h = markdown.markdown(section(path.read_text(encoding="utf-8"), start, stop), extensions=["tables"])
    return re.sub(r'src="(?!https?:|file:)([^"]+)"', lambda m: f'src="{(path.parent / m[1]).resolve().as_uri()}"', h)


def mark(h, text, beat):
    """Highlight the first occurrence of text from this beat on."""
    need(text in h, f"not on the slide: {text!r}")
    return h.replace(text, f'<mark data-b="{beat}">{text}</mark>', 1)


def mark_row(h, cell, beat):
    """Highlight the table row whose first cell starts with `cell`."""
    new, n = re.subn(rf"<tr>(\s*<td>{re.escape(cell)})", rf'<tr class="row" data-b="{beat}">\1', h, count=1)
    need(n, f"no row starts with {cell!r}")
    return new


def img(src):
    return Path(src).resolve().as_uri()


def crop(src, box, dest):
    """Crop (left, top, right, bottom) in source pixels and return the crop's file uri."""
    from PIL import Image
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Image.open(src).crop(box).save(dest)
    return img(dest)


def shot(src, boxes=(), caption=""):
    """A screenshot with outline boxes; each box is (beat, left%, top%, width%, height%) of the image."""
    marks = "".join(f'<i class="box" data-b="{b}" style="left:{l}%;top:{t}%;width:{w}%;height:{h}%"></i>'
                    for b, l, t, w, h in boxes)
    cap = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
    return f'<figure><div class="shot"><img src="{src}">{marks}</div>{cap}</figure>'


def terminal(lines, size="mid"):
    """Real command output. Each line is text, or (text, beat) to highlight it from that beat."""
    rows = []
    for line in lines:
        text, beat = line if isinstance(line, tuple) else (line, 0)
        cls = "cmd" if text.startswith("$ ") else ""
        body = html.escape(text)
        rows.append(f'<div class="{cls}">' + (f'<mark data-b="{beat}">{body}</mark>' if beat else body) + "</div>")
    return f'<div class="term {size}">{"".join(rows)}</div>'


def chrome():
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    found = pptx_env.find_browser()
    if not found:
        sys.exit("No Chrome, Edge or Chromium found. Set CHROME to its path.")
    return found


def slide_html(s, n, total, brand, css):
    labels = "".join(f'<p class="label" data-b="{b}">{html.escape(t)}</p>' for b, t in s.get("labels", {}).items())
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Atkinson+Hyperlegible+Mono:wght@400;600&display=block" rel="stylesheet">
<style>{css}</style></head><body class="{s.get('kind', '')}">
<aside><div class="brand">{html.escape(brand)}</div><h1>{html.escape(s['title'])}</h1><div class="labels">{labels}</div>
<div class="count">{n} of {total}</div></aside>
<main>{s['body']}</main>
<script>const b=+new URLSearchParams(location.search).get('b');
const sc={json.dumps(s.get('scroll', {}))}[b];if(sc)document.querySelector('.scroll').style.transform=`translateY(-${{sc}}px)`;
document.querySelectorAll('[data-b]').forEach(e=>{{const k=+e.dataset.b;
if(k<=b)e.classList.add('on');if(k===b)e.classList.add('now');}});</script></body></html>"""


def check(items):
    """Every highlight and label must belong to a beat that exists, or it never shows."""
    for n, s in enumerate(items, 1):
        beats = len(s["say"])
        need(beats, f"slide {n} has no narration")
        used = {int(b) for b in re.findall(r'data-b="(\d+)"', s["body"])} | set(s.get("labels", {}))
        bad = sorted(b for b in used if not 1 <= b <= beats)
        need(not bad, f"slide {n} ({s['title']}) highlights beat {bad}, but has {beats} beats")
        for b in s.get("scroll", {}):
            need(1 <= b <= beats, f"slide {n} scrolls on beat {b}, but has {beats} beats")


def render(items, out_dir, brand, css):
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    exe, stills = chrome(), []
    for n, s in enumerate(items, 1):
        page_file = out_dir / f"_slide{n:02}.html"
        page_file.write_text(slide_html(s, n, len(items), brand, css), encoding="utf-8")
        try:
            for b in range(1, len(s["say"]) + 1):
                png = out_dir / f"s{n:02}-b{b}.png"
                subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                "--virtual-time-budget=4000", "--window-size=1920,1080", f"--screenshot={png}",
                                page_file.as_uri() + f"?b={b}"], check=True, timeout=90, capture_output=True)
                need(png.exists() and png.stat().st_size > 0, f"missing still {png.name}")
                stills.append((n, b, png, s["say"][b - 1]))
        finally:
            page_file.unlink(missing_ok=True)
    contact(stills, out_dir / "contact.png")
    return stills


def contact(stills, dest, cols=4):
    """All stills on one sheet, so order and highlights can be checked in one look."""
    from PIL import Image
    w, h = 480, 270
    rows = -(-len(stills) // cols)
    sheet = Image.new("RGB", (cols * w, rows * h), "white")
    for k, (_, _, png, _) in enumerate(stills):
        sheet.paste(Image.open(png).convert("RGB").resize((w, h)), ((k % cols) * w, (k // cols) * h))
    sheet.save(dest)


def tool(name):
    found = pptx_env.find_media(name)
    if not found:
        sys.exit(f"{name} not found. Run pptx_env.py doctor for the install command.")
    return found


def ff(*args):
    subprocess.run([tool("ffmpeg"), "-y", "-v", "error", *map(str, args)], check=True)


def probe(path, stream="a:0"):
    r = subprocess.run([tool("ffprobe"), "-v", "error", "-select_streams", stream, "-show_entries", "stream=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def video(stills, mp4, voice=VOICE, rate=RATE):
    import edge_tts

    with tempfile.TemporaryDirectory(dir=mp4.parent) as tmp:
        tmp = Path(tmp)
        wavs, durs = [], []
        for i, (n, b, _, say) in enumerate(stills):
            last_of_slide = i + 1 == len(stills) or stills[i + 1][0] != n
            mp3, wav = tmp / f"{i:03}.mp3", tmp / f"{i:03}.wav"
            asyncio.run(asyncio.wait_for(edge_tts.Communicate(say, voice, rate=rate).save(str(mp3)), timeout=60))
            gap = SLIDE_GAP if last_of_slide else BEAT_GAP
            ff("-i", mp3, "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
               f"silenceremove=start_periods=1:start_threshold=-50dB,areverse,adelay=150:all=1,apad=pad_dur={gap}",
               "-ar", 24000, "-ac", 1, wav)
            wavs.append(wav)
            durs.append(probe(wav))
        listing = tmp / "a.txt"
        listing.write_text("".join(f"file '{w.as_posix()}'\n" for w in wavs), encoding="utf-8")
        audio = tmp / "audio.wav"
        ff("-f", "concat", "-safe", 0, "-i", listing, "-c", "copy", audio)

        args, parts = [], []
        cfs = [CF_BEAT if stills[k][0] == stills[k - 1][0] else CF_SLIDE for k in range(1, len(stills))]
        for k, ((_, _, png, _), d) in enumerate(zip(stills, durs)):
            pad = cfs[k] if k < len(cfs) else 0
            args += ["-loop", 1, "-t", f"{d + pad:.3f}", "-i", png]
            parts.append(f"[{k}:v]scale=1920:1080,fps=30,format=yuv420p[v{k}]")
        last = "v0"
        length = durs[0] + (cfs[0] if cfs else 0)
        for k in range(1, len(stills)):
            off = length - cfs[k - 1]
            parts.append(f"[{last}][v{k}]xfade=transition=fade:duration={cfs[k - 1]}:offset={off:.3f}[x{k}]")
            last = f"x{k}"
            length = off + durs[k] + (cfs[k] if k < len(cfs) else 0)
        out = tmp / mp4.name
        ff(*args, "-i", audio, "-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", f"{len(stills)}:a",
           "-c:v", "libx264", "-crf", 18, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags",
           "+faststart", out)
        v, a, total = probe(out, "v:0"), probe(out, "a:0"), sum(durs)
        print(f"video {v:.2f}s  audio {a:.2f}s  narration {total:.2f}s")
        need(abs(v - total) < 0.2 and abs(a - total) < 0.2, "video and audio lengths disagree")
        os.replace(out, mp4)
    print(f"wrote {mp4}")


def script_md(items, dest):
    """The narration as one file, beat by beat, for the fact check."""
    out = []
    for n, s in enumerate(items, 1):
        out.append(f"## {n}. {s['title']}\n")
        out += [f"{b}. {say}\n" for b, say in enumerate(s["say"], 1)]
    dest.write_text("\n".join(out), encoding="utf-8")


def main():
    if len(sys.argv) < 2 or sys.argv[2:] not in ([], ["video"]):
        sys.exit(__doc__)
    deck_path = Path(sys.argv[1]).resolve()
    deck = runpy.run_path(str(deck_path))
    items, brand = deck["slides"](), deck["BRAND"]
    css = (HERE / "slide.css").read_text(encoding="utf-8") + deck.get("CSS", "")
    check(items)
    stem = deck.get("NAME", deck_path.stem)
    base = deck_path.parent
    script_md(items, base / f"{stem}.script.md")
    words = sum(len(" ".join(s["say"]).split()) for s in items)
    print(f"{len(items)} slides, {words} words, about {words / WPM:.1f} min")
    stills = render(items, base / f"{stem}-render", brand, css)
    print(f"rendered {len(stills)} stills; contact sheet {base / f'{stem}-render' / 'contact.png'}")
    if sys.argv[2:] == ["video"]:
        video(stills, base / f"{stem}.mp4", deck.get("VOICE", VOICE), deck.get("RATE", RATE))


if __name__ == "__main__":
    main()
