"""Environment helper for the powerpoint skill.

The skill's prose decides what the deck says. This file handles the things that
are easy to get subtly wrong on a machine that isn't the one the instructions
were written on: finding LibreOffice, the ffmpeg/poppler binaries and a
Chromium wherever the OS put them, resolving the active workspace, rendering a
mermaid diagram, and opening a finished file in the default application.

The per-OS branches are pure functions that take the platform as an argument,
so they can all be tested from one machine. The impure wrappers around them are
thin on purpose.

CLI:
    python pptx_env.py doctor            report every dependency, exit 1 if a required one is missing
    python pptx_env.py workspace         active workspace as JSON
    python pptx_env.py soffice           absolute path to LibreOffice, exit 1 if absent
    python pptx_env.py ffmpeg            absolute path to ffmpeg, exit 1 if absent
    python pptx_env.py ffprobe           absolute path to ffprobe, exit 1 if absent
    python pptx_env.py pdftoppm          absolute path to pdftoppm, exit 1 if absent
    python pptx_env.py browser           absolute path to a Chromium mermaid-cli can drive, exit 1 if absent
    python pptx_env.py topdf <pptx> <outdir>   render a deck to PDF
    python pptx_env.py mermaid <in.mmd> <out.png> [scale] [theme]   render a diagram, exit 1 if it produced nothing usable
    python pptx_env.py open <file>       open a file in the default application
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

# LibreOffice and the media tools are optional: a deck still gets built without
# them, you just lose the render and the video. python-pptx is not optional.
REQUIRED = ("python-pptx",)


# ---------------------------------------------------------------------------
# Per-OS search paths
#
# shutil.which covers the common case on all three platforms. These globs are
# the fallback for the installers that don't touch PATH, which on Windows is
# most of them. Path shapes follow unoconv's detection algorithm (GPLv2, so
# the shapes are reproduced, not its code).
# ---------------------------------------------------------------------------
def soffice_candidates(platform: str | None = None, env: dict | None = None) -> list[str]:
    """Glob patterns for the LibreOffice binary, highest priority first."""
    plat = platform if platform is not None else sys.platform
    env = env if env is not None else os.environ

    if plat.startswith("win"):
        pats = []
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432"):
            root = env.get(var)
            if root:
                pats.append(rf"{root}\LibreOffice*\program\soffice.exe")
                pats.append(rf"{root}\OpenOffice*\program\soffice.exe")
        return pats
    if plat == "darwin":
        return [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/Applications/OpenOffice.app/Contents/MacOS/soffice",
        ]
    return [
        "/usr/bin/soffice",
        "/usr/lib*/libreoffice*/program/soffice",
        "/opt/libreoffice*/program/soffice",
        "/snap/bin/libreoffice",
        "/usr/local/lib/libreoffice*/program/soffice",
    ]


def media_candidates(binary: str, platform: str | None = None, env: dict | None = None) -> list[str]:
    """Glob patterns for ffmpeg/ffprobe/pdftoppm, highest priority first."""
    plat = platform if platform is not None else sys.platform
    env = env if env is not None else os.environ

    if plat.startswith("win"):
        pats = []
        local = env.get("LOCALAPPDATA")
        if local:
            # winget drops these under a versioned package directory
            pats.append(rf"{local}\Microsoft\WinGet\Packages\*\**\bin\{binary}.exe")
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            root = env.get(var)
            if root:
                pats.append(rf"{root}\*\bin\{binary}.exe")
        return pats
    if plat == "darwin":
        return [f"/opt/homebrew/bin/{binary}", f"/usr/local/bin/{binary}"]
    return [f"/usr/bin/{binary}", f"/usr/local/bin/{binary}", f"/snap/bin/{binary}"]


def _resolve(names: tuple[str, ...], patterns: list[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for pat in patterns:
        # recursive=True so the ** in the winget pattern actually descends
        for hit in sorted(glob.glob(pat, recursive=True), reverse=True):
            if os.path.isfile(hit):
                return hit
    return None


def browser_candidates(platform: str | None = None, env: dict | None = None) -> list[str]:
    """Glob patterns for a Chromium mermaid-cli can drive, highest priority first.

    mermaid-cli bundles puppeteer but not a browser, and puppeteer only accepts
    the exact build it was pinned against. On this machine `mmdc` is installed,
    its cache holds 150.x and 151.x, and it demands 152.0.7977.42, so a plain
    invocation fails with "Could not find chrome-headless-shell". Any recent
    Chromium works when handed over explicitly, and Playwright has usually
    already downloaded one, so look there before asking anyone to fetch 150MB.

    Every directory here is version numbered and differs per machine, which is
    why this resolves rather than hardcodes. The glob sorts reverse so the
    newest build wins.
    """
    plat = platform if platform is not None else sys.platform
    env = env if env is not None else os.environ

    if plat.startswith("win"):
        pats = []
        local = env.get("LOCALAPPDATA")
        if local:
            pats.append(rf"{local}\ms-playwright\chromium-*\chrome-win\chrome.exe")
            pats.append(rf"{local}\ms-playwright\chromium_headless_shell-*\*\headless_shell.exe")
        home = env.get("USERPROFILE")
        if home:
            pats.append(rf"{home}\.cache\puppeteer\chrome\*\chrome-win64\chrome.exe")
            pats.append(rf"{home}\.cache\puppeteer\chrome-headless-shell\*\*\chrome-headless-shell.exe")
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = env.get(var)
            if root:
                pats.append(rf"{root}\Google\Chrome\Application\chrome.exe")
                pats.append(rf"{root}\Microsoft\Edge\Application\msedge.exe")
        return pats

    home = env.get("HOME", "")
    if plat == "darwin":
        return [
            f"{home}/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
            f"{home}/.cache/puppeteer/chrome/*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    return [
        f"{home}/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        f"{home}/.cache/puppeteer/chrome/*/chrome-linux64/chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/snap/bin/chromium",
    ]


def find_browser() -> str | None:
    """A Chromium mmdc can drive, or None. PUPPETEER_EXECUTABLE_PATH wins."""
    override = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    if override and os.path.isfile(override):
        return override
    return _resolve((), browser_candidates())


def find_soffice() -> str | None:
    return _resolve(("soffice", "libreoffice"), soffice_candidates())


def find_media(binary: str) -> str | None:
    """Locate ffmpeg, ffprobe or pdftoppm."""
    return _resolve((binary,), media_candidates(binary))


# ---------------------------------------------------------------------------
# Opening a file in the default application
# ---------------------------------------------------------------------------
def open_command(path, platform: str | None = None) -> list[str] | None:
    """argv that opens path, or None on Windows where os.startfile has no argv.

    webbrowser.open() is deliberately not used: CPython's own docs say opening
    a filename with it "is neither supported nor portable".
    """
    plat = platform if platform is not None else sys.platform
    if plat.startswith("win"):
        return None
    if plat == "darwin":
        return ["open", str(path)]
    return ["xdg-open", str(path)]


def open_file(path) -> bool:
    """Open path in the default application. False if the platform refused."""
    path = str(Path(path).resolve())
    argv = open_command(path)
    try:
        if argv is None:
            os.startfile(path)  # noqa: S606  Windows only, guarded by open_command
        else:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:  # noqa: BLE001  an unopenable file must not kill the skill
        return False


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------
def active_workspace() -> dict:
    """Resolve the active workspace via ClaudeBoost's own resolver.

    Never guesses workspace/<id>/ relative to cwd: get-active-workspace.py has
    per-instance and registry fallbacks precisely because that guess breaks
    with concurrent sessions.

    Always returns workspace_id, workspace_path and project_path, so callers
    don't have to care which resolution path answered. The resolver returns
    more fields than that; they're passed through untouched.
    """
    resolved = {}
    home = os.environ.get("CLAUDEBOOST_HOME")
    if home:
        resolver = Path(home) / "scripts" / "get-active-workspace.py"
        if resolver.is_file():
            try:
                r = subprocess.run(
                    [sys.executable, str(resolver)],
                    capture_output=True, text=True, timeout=20,
                )
                if r.returncode == 0 and r.stdout.strip():
                    resolved = json.loads(r.stdout)
            except Exception:  # noqa: BLE001  fall through to the cwd answer
                resolved = {}

    if not isinstance(resolved, dict):
        resolved = {}
    out = dict(resolved)
    out.setdefault("workspace_id", resolved.get("workspace"))
    out.setdefault("workspace_path", None)
    out.setdefault("project_path", None)
    if not out["project_path"]:
        out["project_path"] = os.getcwd()
    return out


def output_dir() -> Path:
    """Where a generated deck should land: the active workspace, else cwd."""
    ws = active_workspace().get("workspace_path")
    return Path(ws) if ws and Path(ws).is_dir() else Path.cwd()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def to_pdf(pptx, outdir) -> Path | None:
    """Render a deck to PDF with LibreOffice. None if it isn't installed.

    Invokes soffice directly rather than through a socket-based conversion
    daemon: --headless --convert-to is the one entry point that behaves the
    same on Windows, macOS and Linux.
    """
    soffice = find_soffice()
    if not soffice:
        return None
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [soffice, "--headless", "--norestore", "--convert-to", "pdf",
         "--outdir", str(outdir), str(pptx)],
        capture_output=True, text=True, timeout=300,
    )
    pdf = outdir / (Path(pptx).stem + ".pdf")
    return pdf if r.returncode == 0 and pdf.is_file() else None


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
def _have_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def render_mermaid(src: str, out: str, scale: int = 3, theme: str = "default",
                   background: str = "white") -> str | None:
    """Render a .mmd to PNG. Returns the path, or None with a reason on stderr.

    Fails loudly on purpose. mermaid-cli can exit 0 having written nothing, and
    it can write a file that is not a PNG, so an exit code alone is not evidence
    a diagram exists. A deck with a silently missing diagram is the failure this
    checks for: the same shape as a narration step that produced no audio and
    no error, which took an adversarial pass to catch.
    """
    mmdc = shutil.which("mmdc") or shutil.which("mmdc.cmd")
    if not mmdc:
        print("mermaid: mmdc not found  ->  npm i -g @mermaid-js/mermaid-cli",
              file=sys.stderr)
        return None
    if not os.path.isfile(src):
        print(f"mermaid: no such source file: {src}", file=sys.stderr)
        return None

    env = dict(os.environ)
    browser = find_browser()
    if browser:
        env["PUPPETEER_EXECUTABLE_PATH"] = browser

    try:
        proc = subprocess.run(
            [mmdc, "-i", src, "-o", out, "-s", str(scale),
             "-t", theme, "-b", background],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, env=env,
        )
    except subprocess.TimeoutExpired:
        print("mermaid: mmdc did not finish within 180s", file=sys.stderr)
        return None

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        first = detail[0] if detail else f"exit {proc.returncode}"
        print(f"mermaid: render failed: {first}", file=sys.stderr)
        if not browser:
            print("mermaid: no Chromium found for mermaid-cli. Install one, or set "
                  "PUPPETEER_EXECUTABLE_PATH, or run: "
                  "npx puppeteer browsers install chrome-headless-shell",
                  file=sys.stderr)
        return None

    # Exit 0 is not evidence. Check the file is really there and really a PNG.
    if not os.path.isfile(out):
        print(f"mermaid: mmdc exited 0 but wrote no file: {out}", file=sys.stderr)
        return None
    if os.path.getsize(out) < 512:
        print(f"mermaid: output is {os.path.getsize(out)} bytes, too small to be "
              f"a diagram: {out}", file=sys.stderr)
        return None
    with open(out, "rb") as fh:
        if fh.read(8) != _PNG_MAGIC:
            print(f"mermaid: output is not a PNG: {out}", file=sys.stderr)
            return None

    # mermaid-cli writes no pHYs chunk, so the PNG does not say how big it is
    # meant to be. python-pptx then falls back to 72 dpi, and a 945x2046
    # diagram lands on the slide at 13.1 x 28.4 inches: four slides tall, at
    # 72 ppi. Measured, not guessed. Stamping the real density makes an
    # unsized add_picture place it at its true size instead.
    _stamp_png_dpi(out, 96 * max(1, int(scale)))
    return out


def _stamp_png_dpi(path: str, dpi: int) -> bool:
    """Write a pHYs chunk declaring `dpi`, replacing one if it is already there.

    96 dpi is one CSS pixel, which is what mermaid renders at scale 1, so the
    honest density for a render at scale N is 96*N. That makes the PNG's own
    stated size equal the diagram's natural size, which is what every consumer
    (python-pptx, browsers, Word) reads to place it.

    Best effort. A diagram that is merely the wrong size still beats no diagram,
    so a failure here returns False and leaves the file exactly as it was
    rather than raising into the caller's abandon path.
    """
    try:
        data = Path(path).read_bytes()
        if data[:8] != _PNG_MAGIC:
            return False

        ppu = int(round(dpi / 0.0254))  # pixels per metre, pHYs unit 1
        body = b"pHYs" + struct.pack(">IIB", ppu, ppu, 1)
        chunk = struct.pack(">I", 9) + body + struct.pack(">I", zlib.crc32(body))

        out_parts, i, n = [data[:8]], 8, len(data)
        inserted = False
        while i < n - 8:
            length = struct.unpack(">I", data[i:i + 4])[0]
            ctype = data[i + 4:i + 8]
            end = i + 12 + length
            if ctype == b"pHYs":
                out_parts.append(chunk)          # replace an existing one
                inserted = True
            else:
                if ctype == b"IDAT" and not inserted:
                    out_parts.append(chunk)      # pHYs must precede IDAT
                    inserted = True
                out_parts.append(data[i:end])
            i = end
        if not inserted:
            return False

        tmp = f"{path}.dpi.tmp"
        with open(tmp, "wb") as fh:
            fh.write(b"".join(out_parts))
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _mermaid_works() -> bool:
    """Actually render something. 'mmdc is installed' does not mean it renders."""
    if not (shutil.which("mmdc") or shutil.which("mmdc.cmd")):
        return False
    tmp = Path(tempfile.mkdtemp(prefix="pptx_mermaid_probe_"))
    try:
        src = tmp / "probe.mmd"
        src.write_text("flowchart LR\n  A[a] --> B[b]\n", encoding="utf-8")
        return render_mermaid(str(src), str(tmp / "probe.png")) is not None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def doctor() -> int:
    """Report every dependency. Exit code 1 if a required one is missing."""
    rows = [
        ("python-pptx", "required", "yes" if _have_module("pptx") else None,
         "pip install python-pptx"),
        ("LibreOffice", "render + video", find_soffice(),
         "https://libreoffice.org  (winget install TheDocumentFoundation.LibreOffice)"),
        ("pdftoppm", "slide images", find_media("pdftoppm"),
         "winget install oschwartz10612.Poppler  |  apt install poppler-utils  |  brew install poppler"),
        ("ffmpeg", "narrated video", find_media("ffmpeg"),
         "winget install Gyan.FFmpeg  |  apt install ffmpeg  |  brew install ffmpeg"),
        ("edge-tts", "narration voice", "yes" if _have_module("edge_tts") else None,
         "pip install edge-tts"),
        # Probed by rendering, not by presence. mmdc installs without a browser
        # and then fails at render time, so "installed" answers the wrong question.
        ("mermaid", "diagrams", "yes" if _mermaid_works() else None,
         "npm i -g @mermaid-js/mermaid-cli, plus a Chromium "
         "(npx puppeteer browsers install chrome-headless-shell)"),
    ]

    width = max(len(r[0]) for r in rows)
    missing_required = 0
    for name, purpose, found, how in rows:
        if found:
            print(f"  OK    {name.ljust(width)}  {purpose}")
        else:
            required = purpose == "required"
            missing_required += required
            print(f"  {'MISS ' if required else 'warn '} {name.ljust(width)}  {purpose}  ->  {how}")

    ws = active_workspace()
    print(f"\n  workspace: {ws.get('workspace_path') or '(none active, will use cwd)'}")
    print(f"  output to: {output_dir()}")
    return 1 if missing_required else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]

    if cmd == "doctor":
        return doctor()
    if cmd == "workspace":
        print(json.dumps(active_workspace(), indent=2))
        return 0
    if cmd in ("soffice", "ffmpeg", "ffprobe", "pdftoppm", "browser"):
        if cmd == "soffice":
            found = find_soffice()
        elif cmd == "browser":
            found = find_browser()
        else:
            found = find_media(cmd)
        if not found:
            print(f"{cmd} not found", file=sys.stderr)
            return 1
        print(found)
        return 0
    if cmd == "mermaid":
        if len(rest) < 2:
            print("usage: pptx_env.py mermaid <in.mmd> <out.png> [scale] [theme]",
                  file=sys.stderr)
            return 2
        scale = int(rest[2]) if len(rest) > 2 else 3
        theme = rest[3] if len(rest) > 3 else "default"
        png = render_mermaid(rest[0], rest[1], scale=scale, theme=theme)
        if not png:
            return 1
        print(png)
        return 0
    if cmd == "topdf":
        if len(rest) < 2:
            print("usage: pptx_env.py topdf <pptx> <outdir>", file=sys.stderr)
            return 2
        pdf = to_pdf(rest[0], rest[1])
        if not pdf:
            print("LibreOffice not available or conversion failed", file=sys.stderr)
            return 1
        print(pdf)
        return 0
    if cmd == "open":
        if not rest:
            print("usage: pptx_env.py open <file>", file=sys.stderr)
            return 2
        return 0 if open_file(rest[0]) else 1

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
