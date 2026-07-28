"""Environment helper for the powerpoint skill.

The skill's prose decides what the deck says. This file handles the three
things that are easy to get subtly wrong on a machine that isn't the one the
instructions were written on: finding LibreOffice and the ffmpeg/poppler
binaries wherever the OS put them, resolving the active workspace, and opening
a finished file in the default application.

The per-OS branches are pure functions that take the platform as an argument,
so all three can be tested from one machine. The impure wrappers around them
are thin on purpose.

CLI:
    python pptx_env.py doctor            report every dependency, exit 1 if a required one is missing
    python pptx_env.py workspace         active workspace as JSON
    python pptx_env.py soffice           absolute path to LibreOffice, exit 1 if absent
    python pptx_env.py ffmpeg            absolute path to ffmpeg, exit 1 if absent
    python pptx_env.py pdftoppm          absolute path to pdftoppm, exit 1 if absent
    python pptx_env.py topdf <pptx> <outdir>   render a deck to PDF
    python pptx_env.py open <file>       open a file in the default application
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
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
    if cmd in ("soffice", "ffmpeg", "ffprobe", "pdftoppm"):
        found = find_soffice() if cmd == "soffice" else find_media(cmd)
        if not found:
            print(f"{cmd} not found", file=sys.stderr)
            return 1
        print(found)
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
