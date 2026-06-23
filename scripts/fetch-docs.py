"""
fetch-docs.py — download a URL queue and save as markdown to a project KB.

Used by /research-project and /research-task instead of AI-powered WebFetch agents.
No AI tokens used. Pure httpx + html2text.

Usage:
  python fetch-docs.py --project-path C:/path/to/project
      Reads pending-urls.json from {project_path}/.claudeboost/knowledge/ and fetches them.

  python fetch-docs.py --project-path C:/path/to/project --queue /path/to/urls.json
      Reads from the specified JSON queue file instead.

  python fetch-docs.py --project-path C:/path/to/project --kb-dir /custom/kb/dir
      Saves to a custom KB directory (defaults to {project_path}/.claudeboost/knowledge/).

Queue file format (pending-urls.json):
  [
    {"url": "https://...", "topic": "playwright-python", "tier": "A", "title": "optional"},
    ...
  ]

deps: pip install httpx html2text
"""

import argparse
import json
import pathlib
import re
import sys
import time

try:
    import httpx
    import html2text as html2text_lib
except ImportError:
    print("Missing deps. Run: pip install httpx html2text")
    sys.exit(1)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def make_slug(url: str, topic: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    raw = "-".join(parts[-2:]) if len(parts) >= 2 else parsed.netloc.replace(".", "-")
    name = re.sub(r"[^a-z0-9\-]", "", raw.lower())[:60]
    topic_slug = re.sub(r"[^a-z0-9\-]", "", topic.lower().replace(" ", "-"))[:30]
    return f"{topic_slug}-{name}.md"


def fetch_one(item: dict, kb_dir: pathlib.Path, fetched_date: str) -> bool:
    url = item.get("url", "")
    topic = item.get("topic", "misc")
    tier = item.get("tier", "B")

    if not url.startswith("http"):
        print(f"  SKIP (bad url): {url}")
        return False

    filename = make_slug(url, topic)
    out_path = kb_dir / filename

    if out_path.exists():
        print(f"  SKIP (exists): {filename}")
        return True

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True, headers=HEADERS)
        if resp.status_code != 200:
            print(f"  FAIL {resp.status_code}: {url}")
            return False

        converter = html2text_lib.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0
        converter.ignore_tables = False
        md = converter.handle(resp.text)

        header = (
            f"<!-- Source: {url} | Tier: {tier} | "
            f"Topic: {topic} | Fetched: {fetched_date} -->\n\n"
        )
        out_path.write_text(header + md, encoding="utf-8")
        size_kb = out_path.stat().st_size // 1024
        print(f"  OK ({size_kb}KB): {filename}")
        return True

    except Exception as exc:
        print(f"  FAIL: {url} — {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Fetch URL queue into project KB")
    parser.add_argument("--project-path", required=True, help="Absolute path to the project")
    parser.add_argument("--queue", help="Path to JSON queue file (default: {kb_dir}/pending-urls.json)")
    parser.add_argument("--kb-dir", help="KB directory (default: {project_path}/.claudeboost/knowledge/)")
    parser.add_argument("--date", default="", help="Fetch date string to embed in file headers")
    args = parser.parse_args()

    project = pathlib.Path(args.project_path)
    kb_dir = pathlib.Path(args.kb_dir) if args.kb_dir else project / ".claudeboost" / "knowledge"
    kb_dir.mkdir(parents=True, exist_ok=True)

    queue_path = pathlib.Path(args.queue) if args.queue else kb_dir / "pending-urls.json"

    if not queue_path.exists():
        print(f"Queue file not found: {queue_path}")
        sys.exit(1)

    urls = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(urls, list):
        print("Queue file must be a JSON array.")
        sys.exit(1)

    fetched_date = args.date or time.strftime("%Y-%m-%d")
    ok, fail, skip = 0, 0, 0

    for item in urls:
        url = item.get("url", "")
        topic = item.get("topic", "misc")
        print(f"\n[{topic}] {url}")
        result = fetch_one(item, kb_dir, fetched_date)
        if result:
            filename = kb_dir / make_slug(url, topic)
            if filename.exists():
                ok += 1
            else:
                skip += 1
        else:
            fail += 1

    print(f"\n{'=' * 60}")
    print(f"Done: {ok} saved, {skip} skipped (already existed), {fail} failed")
    print(f"Files in KB: {len(list(kb_dir.glob('*.md')))}")
    print(f"\nIndex into RAG:")
    print(
        f'  curl -s -X POST http://127.0.0.1:8612/index '
        f'-H "Content-Type: application/json" '
        f"-d '{{\"project_path\":\"{project}\",\"force\":true}}'"
    )


if __name__ == "__main__":
    main()
