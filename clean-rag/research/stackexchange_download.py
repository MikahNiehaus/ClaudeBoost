"""Downloads StackExchange data dump archives for the dev-relevant subset.

Real sizes confirmed via direct fetch of archive.org's stackexchange
collection listing (not guessed): stackoverflow.com's Posts.7z alone is
21.4GB. Only Posts.xml is needed per site (questions + answers) — skips
PostHistory (edit history), Comments, Votes, Badges, PostLinks, which are
not needed to build a Q&A knowledge base and would multiply the download
size for no benefit here.

Usage: python stackexchange_download.py
"""

import sys
from pathlib import Path

import httpx

ARCHIVE_BASE = "https://archive.org/download/stackexchange"

# (archive filename, local site slug). Stack Overflow ships Posts.7z as a
# separate file; the smaller sites bundle everything into one archive
# named after the site, so extraction pulls just Posts.xml out of it.
SITES = [
    ("stackoverflow.com-Posts.7z", "stackoverflow"),
    ("serverfault.com.7z", "serverfault"),
    ("superuser.com.7z", "superuser"),
    ("security.stackexchange.com.7z", "security-stackexchange"),
    ("softwareengineering.stackexchange.com.7z", "softwareengineering"),
    ("dba.stackexchange.com.7z", "dba-stackexchange"),
    ("unix.stackexchange.com.7z", "unix-stackexchange"),
    ("askubuntu.com.7z", "askubuntu"),
    ("webmasters.stackexchange.com.7z", "webmasters-stackexchange"),
]

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "state" / "stackexchange-raw"


def download_all() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for archive_name, slug in SITES:
        dest = DOWNLOAD_DIR / archive_name
        if dest.exists():
            print(f"[skip] {archive_name} already downloaded ({dest.stat().st_size / 1e6:.0f}MB)")
            continue

        url = f"{ARCHIVE_BASE}/{archive_name}"
        print(f"[download] {archive_name} <- {url}")

        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                tmp_dest = dest.with_suffix(dest.suffix + ".part")
                with open(tmp_dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total * 100
                            print(f"\r  {downloaded / 1e6:.0f}MB / {total / 1e6:.0f}MB ({pct:.1f}%)", end="", flush=True)
                tmp_dest.rename(dest)
                print(f"\n[ok] {archive_name} complete ({dest.stat().st_size / 1e6:.0f}MB)")
        except Exception as e:
            print(f"\n[error] {archive_name} failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    download_all()
