"""
fetch-docs.py — download URLs and save as markdown to a project KB.

Three modes:
  1. Queue mode (default): fetch individual URLs from a JSON queue file
  2. llms.txt mode (--llms-txt): check a domain for llms-full.txt / llms.txt
     before fetching anything. If found, use the curated content directly.
  3. Crawl mode (--crawl): BFS crawl from a starting URL, following same-domain
     links up to a configurable depth and page limit.

Used by /research-project and /research-task. No AI tokens used.

Usage:
  # Queue mode (original behavior)
  python fetch-docs.py --project-path C:/path --queue /path/to/urls.json

  # llms.txt mode: check domain first
  python fetch-docs.py --project-path C:/path --llms-txt "https://fastapi.tiangolo.com"
      --kb-dir /path/to/kb --topic "fastapi"

  # Crawl mode: BFS crawl a documentation site
  python fetch-docs.py --project-path C:/path --crawl "https://fastapi.tiangolo.com/tutorial/"
      --kb-dir /path/to/kb --topic "fastapi" --max-pages 200 --depth 3

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
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

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

# Paths to skip when crawling (navigation noise, not documentation)
CRAWL_SKIP_PATTERNS = {
    "/blog", "/changelog", "/releases", "/news", "/press",
    "/login", "/signup", "/register", "/account", "/pricing",
    "/about", "/careers", "/jobs", "/contact", "/privacy",
    "/terms", "/legal", "/cookie", "/support/tickets",
    "/search", "/sitemap", "/rss", "/feed", "/atom",
}

# File extensions to skip when crawling
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".mp4", ".mp3", ".wav",
    ".exe", ".dmg", ".deb", ".rpm",
}


# ──────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────

def make_slug(url: str, topic: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    raw = "-".join(parts[-2:]) if len(parts) >= 2 else parsed.netloc.replace(".", "-")
    name = re.sub(r"[^a-z0-9\-]", "", raw.lower())[:60]
    topic_slug = re.sub(r"[^a-z0-9\-]", "", topic.lower().replace(" ", "-"))[:30]
    return f"{topic_slug}-{name}.md"


def make_converter():
    converter = html2text_lib.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0
    converter.ignore_tables = False
    return converter


def save_markdown(content: str, url: str, topic: str, tier: str,
                  kb_dir: pathlib.Path, fetched_date: str) -> pathlib.Path | None:
    """Save markdown content to a file in kb_dir. Returns path or None."""
    filename = make_slug(url, topic)
    out_path = kb_dir / filename

    if out_path.exists():
        return None  # already exists

    header = (
        f"<!-- Source: {url} | Tier: {tier} | "
        f"Topic: {topic} | Fetched: {fetched_date} -->\n\n"
    )
    out_path.write_text(header + content, encoding="utf-8")

    file_size = out_path.stat().st_size
    if file_size < 500:
        out_path.unlink()
        return None  # too small, likely error page

    return out_path


# ──────────────────────────────────────────────────────────────
# Mode 1: Queue mode (original behavior)
# ──────────────────────────────────────────────────────────────

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

        converter = make_converter()
        md = converter.handle(resp.text)

        header = (
            f"<!-- Source: {url} | Tier: {tier} | "
            f"Topic: {topic} | Fetched: {fetched_date} -->\n\n"
        )
        out_path.write_text(header + md, encoding="utf-8")
        file_size = out_path.stat().st_size
        if file_size < 500:
            out_path.unlink()
            print(f"  FAIL (too small, likely error page): {url}")
            return False
        size_kb = file_size // 1024
        print(f"  OK ({size_kb}KB): {filename}")
        return True

    except Exception as exc:
        print(f"  FAIL: {url} — {exc}")
        return False


def run_queue_mode(queue_path: pathlib.Path, kb_dir: pathlib.Path, batch_size: int):
    if not queue_path.exists():
        print(f"Queue file not found: {queue_path}")
        sys.exit(1)

    urls = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(urls, list):
        print("Queue file must be a JSON array.")
        sys.exit(1)

    fetched_date = time.strftime("%Y-%m-%d")
    ok, fail, skip = 0, 0, 0

    print(f"Fetching {len(urls)} URLs (batch size: {batch_size})...\n")

    for idx, item in enumerate(urls):
        url = item.get("url", "")
        topic = item.get("topic", "misc")
        print(f"[{idx+1}/{len(urls)}] [{topic}] {url}")
        result = fetch_one(item, kb_dir, fetched_date)
        if result:
            filename = kb_dir / make_slug(url, topic)
            if filename.exists():
                ok += 1
            else:
                skip += 1
        else:
            fail += 1

        if (idx + 1) % batch_size == 0:
            print(f"\n  Progress: {ok} saved, {fail} failed, "
                  f"{skip} skipped (total: {idx+1}/{len(urls)})\n")

    print(f"\n{'=' * 60}")
    print(f"Done: {ok} saved, {skip} skipped (already existed), {fail} failed")
    print(f"Files in KB: {len(list(kb_dir.glob('*.md')))}")


# ──────────────────────────────────────────────────────────────
# Mode 2: llms.txt checking
# ──────────────────────────────────────────────────────────────

def check_llms_txt(domain_url: str, kb_dir: pathlib.Path,
                   topic: str, fetched_date: str) -> dict:
    """Check a domain for llms-full.txt and llms.txt.

    Returns a summary dict with what was found.
    """
    if not domain_url.startswith(("http://", "https://")):
        domain_url = f"https://{domain_url}"
    parsed = urlparse(domain_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    stats = {"found": None, "files_saved": 0, "urls_discovered": []}

    # Try llms-full.txt first (complete content in one file)
    full_url = f"{base}/llms-full.txt"
    print(f"Checking {full_url}...")
    try:
        resp = httpx.get(full_url, timeout=30, follow_redirects=True, headers=HEADERS)
        if resp.status_code == 200 and len(resp.text) > 500:
            out_path = kb_dir / f"{topic}-llms-full.md"
            header = (
                f"<!-- Source: {full_url} | Tier: A | "
                f"Topic: {topic} | Fetched: {fetched_date} -->\n\n"
            )
            out_path.write_text(header + resp.text, encoding="utf-8")
            size_kb = out_path.stat().st_size // 1024
            print(f"  FOUND llms-full.txt ({size_kb}KB) — complete docs in one file")
            stats["found"] = "llms-full.txt"
            stats["files_saved"] = 1
            return stats
        else:
            print(f"  Not found or too small ({resp.status_code})")
    except Exception as exc:
        print(f"  Error: {exc}")

    # Try llms.txt (index of URLs)
    index_url = f"{base}/llms.txt"
    print(f"Checking {index_url}...")
    try:
        resp = httpx.get(index_url, timeout=30, follow_redirects=True, headers=HEADERS)
        if resp.status_code == 200 and len(resp.text) > 100:
            # Parse URLs from llms.txt (markdown format with links)
            urls_found = re.findall(r'https?://[^\s\)>\]"\']+', resp.text)
            # Filter to same domain
            urls_found = [u for u in urls_found
                          if urlparse(u).netloc == parsed.netloc]
            # Deduplicate
            urls_found = list(dict.fromkeys(urls_found))

            if urls_found:
                print(f"  FOUND llms.txt with {len(urls_found)} same-domain URLs")
                stats["found"] = "llms.txt"
                stats["urls_discovered"] = urls_found

                # Save the llms.txt itself as a doc
                out_path = kb_dir / f"{topic}-llms-index.md"
                header = (
                    f"<!-- Source: {index_url} | Tier: A | "
                    f"Topic: {topic} | Fetched: {fetched_date} -->\n\n"
                )
                out_path.write_text(header + resp.text, encoding="utf-8")
                stats["files_saved"] = 1
                return stats
            else:
                print(f"  llms.txt found but no same-domain URLs extracted")
        else:
            print(f"  Not found ({resp.status_code})")
    except Exception as exc:
        print(f"  Error: {exc}")

    print(f"  No llms.txt available for {parsed.netloc}")
    stats["found"] = None
    return stats


# ──────────────────────────────────────────────────────────────
# Mode 3: BFS crawl
# ──────────────────────────────────────────────────────────────

class LinkExtractor(HTMLParser):
    """Extract href links from HTML."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract and resolve all links from HTML content."""
    parser = LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        return []

    resolved = []
    for link in parser.links:
        # Skip anchors, javascript, mailto
        if link.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        # Resolve relative URLs
        full_url = urljoin(base_url, link)
        # Strip fragment
        full_url = full_url.split("#")[0]
        # Strip trailing slash for dedup
        full_url = full_url.rstrip("/")
        if full_url:
            resolved.append(full_url)

    return resolved


def should_crawl_url(url: str, base_netloc: str, path_prefix: str) -> bool:
    """Check if a URL should be crawled (same domain, within path prefix)."""
    parsed = urlparse(url)

    # Must be same domain
    if parsed.netloc != base_netloc:
        return False

    # Must be http(s)
    if parsed.scheme not in ("http", "https"):
        return False

    # Skip known noise paths (not documentation)
    path_lower = parsed.path.lower()
    for skip in CRAWL_SKIP_PATTERNS:
        if path_lower.startswith(skip):
            return False

    # Skip file extensions that aren't documents
    for ext in SKIP_EXTENSIONS:
        if path_lower.endswith(ext):
            return False

    # Must be within the path prefix (if specified)
    if path_prefix and not parsed.path.startswith(path_prefix):
        return False

    return True


def bfs_crawl(start_url: str, kb_dir: pathlib.Path, topic: str,
              max_pages: int = 200, max_depth: int = 3,
              delay: float = 0.5) -> dict:
    """BFS crawl from start_url, staying within the same domain and path prefix.

    Returns a summary dict.
    """
    parsed_start = urlparse(start_url)
    base_netloc = parsed_start.netloc
    # Use the starting path as the prefix to scope the crawl
    path_prefix = parsed_start.path.rstrip("/")
    # If the path is just "/" or empty, don't restrict
    if len(path_prefix) <= 1:
        path_prefix = ""

    fetched_date = time.strftime("%Y-%m-%d")
    converter = make_converter()

    # BFS state
    queue = deque()
    queue.append((start_url, 0))  # (url, depth) — keep trailing slash for urljoin
    visited = {start_url.rstrip("/")}
    stats = {
        "pages_crawled": 0,
        "pages_saved": 0,
        "pages_skipped": 0,
        "pages_failed": 0,
        "bytes_total": 0,
        "max_depth_reached": 0,
    }

    print(f"BFS crawl: {start_url}")
    print(f"  Domain: {base_netloc}")
    print(f"  Path prefix: {path_prefix or '(none, full domain)'}")
    print(f"  Max pages: {max_pages}, Max depth: {max_depth}")
    print()

    while queue and stats["pages_crawled"] < max_pages:
        url, depth = queue.popleft()

        if depth > max_depth:
            continue

        stats["max_depth_reached"] = max(stats["max_depth_reached"], depth)
        stats["pages_crawled"] += 1

        # Check if already saved (but still fetch for link discovery)
        slug = make_slug(url, topic)
        out_path = kb_dir / slug
        already_saved = out_path.exists()
        if already_saved:
            stats["pages_skipped"] += 1
            print(f"  [{stats['pages_crawled']}/{max_pages}] SKIP (exists) d={depth}: {url}")

        try:
            if delay > 0 and stats["pages_crawled"] > 1:
                time.sleep(delay)

            resp = httpx.get(url, timeout=30, follow_redirects=True, headers=HEADERS)

            if resp.status_code != 200:
                stats["pages_failed"] += 1
                print(f"  [{stats['pages_crawled']}/{max_pages}] FAIL {resp.status_code} "
                      f"d={depth}: {url}")
                continue

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                # Not HTML, skip (PDFs handled separately in future)
                stats["pages_skipped"] += 1
                continue

            html = resp.text

            if not already_saved:
                md = converter.handle(html)
                result = save_markdown(md, url, topic, "A", kb_dir, fetched_date)
                if result:
                    stats["pages_saved"] += 1
                    stats["bytes_total"] += result.stat().st_size
                    size_kb = result.stat().st_size // 1024
                    print(f"  [{stats['pages_crawled']}/{max_pages}] OK ({size_kb}KB) "
                          f"d={depth}: {slug}")
                else:
                    stats["pages_skipped"] += 1
                    print(f"  [{stats['pages_crawled']}/{max_pages}] SKIP (too small) "
                          f"d={depth}: {url}")

            # Extract links and add to queue (only if we haven't hit max depth)
            if depth < max_depth:
                # Use resp.url as base so redirects (adding trailing slash) are honored
                links = extract_links(html, str(resp.url))
                new_links = 0
                for link in links:
                    normalized = link.rstrip("/")
                    if normalized not in visited and should_crawl_url(
                        normalized, base_netloc, path_prefix
                    ):
                        visited.add(normalized)
                        # Queue with original form for correct urljoin in children
                        queue.append((link, depth + 1))
                        new_links += 1

        except Exception as exc:
            stats["pages_failed"] += 1
            print(f"  [{stats['pages_crawled']}/{max_pages}] ERROR d={depth}: "
                  f"{url} — {exc}")

        # Progress report every 25 pages
        if stats["pages_crawled"] % 25 == 0:
            print(f"\n  Progress: {stats['pages_saved']} saved, "
                  f"{stats['pages_failed']} failed, "
                  f"{stats['pages_skipped']} skipped, "
                  f"queue: {len(queue)} remaining\n")

    return stats


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch/crawl docs into project KB")
    parser.add_argument("--project-path", required=True,
                        help="Absolute path to the project")
    parser.add_argument("--queue",
                        help="Path to JSON queue file (queue mode)")
    parser.add_argument("--kb-dir",
                        help="KB directory (default: {project_path}/.claudeboost/knowledge/)")
    parser.add_argument("--date", default="",
                        help="Fetch date string to embed in file headers")
    parser.add_argument("--batch-size", type=int, default=30,
                        help="URLs per progress report in queue mode (default: 30)")

    # Layer 2: llms.txt
    parser.add_argument("--llms-txt",
                        help="Check this domain URL for llms-full.txt / llms.txt")

    # Layer 3: BFS crawl
    parser.add_argument("--crawl",
                        help="BFS crawl starting from this URL")
    parser.add_argument("--max-pages", type=int, default=200,
                        help="Max pages to crawl in BFS mode (default: 200)")
    parser.add_argument("--depth", type=int, default=3,
                        help="Max crawl depth in BFS mode (default: 3)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between requests in seconds (default: 0.5)")

    # Shared
    parser.add_argument("--topic", default="misc",
                        help="Topic name for file prefixing")

    args = parser.parse_args()

    project = pathlib.Path(args.project_path)
    kb_dir = pathlib.Path(args.kb_dir) if args.kb_dir else project / ".claudeboost" / "knowledge"
    kb_dir.mkdir(parents=True, exist_ok=True)

    fetched_date = args.date or time.strftime("%Y-%m-%d")

    # ── Layer 2: llms.txt mode ──
    if args.llms_txt:
        print(f"{'=' * 60}")
        print(f"Layer 2: llms.txt check for {args.llms_txt}")
        print(f"{'=' * 60}\n")

        result = check_llms_txt(args.llms_txt, kb_dir, args.topic, fetched_date)

        if result["found"] == "llms-full.txt":
            print(f"\nComplete docs obtained via llms-full.txt. "
                  f"No further fetching needed for {args.topic}.")
        elif result["found"] == "llms.txt":
            # Write discovered URLs as a queue for follow up fetching
            queue_items = [
                {"url": u, "topic": args.topic, "tier": "A", "title": ""}
                for u in result["urls_discovered"]
            ]
            queue_path = kb_dir / "pending-urls.json"
            queue_path.write_text(
                json.dumps(queue_items, indent=2), encoding="utf-8"
            )
            print(f"\nWrote {len(queue_items)} URLs to {queue_path}")
            print("Run again without --llms-txt to fetch them, or use --crawl.")
        else:
            print("\nNo llms.txt found. Try --crawl or queue mode instead.")

        print(f"\nFiles in KB: {len(list(kb_dir.glob('*.md')))}")
        return

    # ── Layer 3: BFS crawl mode ──
    if args.crawl:
        print(f"{'=' * 60}")
        print(f"Layer 3: BFS crawl from {args.crawl}")
        print(f"{'=' * 60}\n")

        stats = bfs_crawl(
            start_url=args.crawl,
            kb_dir=kb_dir,
            topic=args.topic,
            max_pages=args.max_pages,
            max_depth=args.depth,
            delay=args.delay,
        )

        size_mb = stats["bytes_total"] / (1024 * 1024)
        print(f"\n{'=' * 60}")
        print(f"Crawl complete: {stats['pages_saved']} saved, "
              f"{stats['pages_skipped']} skipped, "
              f"{stats['pages_failed']} failed")
        print(f"Total size: {size_mb:.1f}MB")
        print(f"Max depth reached: {stats['max_depth_reached']}")
        print(f"Files in KB: {len(list(kb_dir.glob('*.md')))}")
        print(f"\nIndex into RAG:")
        print(
            f'  curl -s -X POST http://127.0.0.1:8612/index '
            f'-H "Content-Type: application/json" '
            f"-d '{{\"project_path\":\"{project}\",\"force\":true}}'"
        )
        return

    # ── Layer 4: Queue mode (original behavior) ──
    queue_path = pathlib.Path(args.queue) if args.queue else kb_dir / "pending-urls.json"
    run_queue_mode(queue_path, kb_dir, args.batch_size)

    print(f"\nIndex into RAG:")
    print(
        f'  curl -s -X POST http://127.0.0.1:8612/index '
        f'-H "Content-Type: application/json" '
        f"-d '{{\"project_path\":\"{project}\",\"force\":true}}'"
    )


if __name__ == "__main__":
    main()
