"""URL fetch + BFS crawl for documentation sites.

Extracted from ClaudeBoost scripts/fetch-docs.py. Layers 2-3 of the
four-layer research waterfall.

Usage:
  # Check for llms.txt
  python -m clean_rag.research.fetch_docs --llms-txt "https://fastapi.tiangolo.com" --topic fastapi

  # BFS crawl
  python -m clean_rag.research.fetch_docs --crawl "https://fastapi.tiangolo.com/tutorial/" \
    --topic fastapi --max-pages 200

  # Queue mode
  python -m clean_rag.research.fetch_docs --queue /path/to/urls.json --topic misc
"""

import argparse
import json
import logging
import pathlib
import re
import sys
import time

logger = logging.getLogger(__name__)
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

try:
    import httpx
    import html2text as html2text_lib
except ImportError:
    print("Missing deps. Run: pip install httpx html2text")
    sys.exit(1)

from server.config import KNOWLEDGE_DIR

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

CRAWL_SKIP_PATTERNS = {
    "/blog", "/changelog", "/releases", "/news", "/press",
    "/login", "/signup", "/register", "/account", "/pricing",
    "/about", "/careers", "/jobs", "/contact", "/privacy",
    "/terms", "/legal", "/cookie", "/support/tickets",
    "/search", "/sitemap", "/rss", "/feed", "/atom",
}

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".mp4", ".mp3", ".wav",
}


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
    filename = make_slug(url, topic)
    out_path = kb_dir / filename
    if out_path.exists():
        return None
    header = (
        f"<!-- Source: {url} | Tier: {tier} | "
        f"Topic: {topic} | Fetched: {fetched_date} -->\n\n"
    )
    out_path.write_text(header + content, encoding="utf-8")
    if out_path.stat().st_size < 500:
        out_path.unlink()
        return None
    return out_path


# ── llms.txt mode ──

def check_llms_txt(domain_url: str, kb_dir: pathlib.Path,
                   topic: str, fetched_date: str) -> dict:
    if not domain_url.startswith(("http://", "https://")):
        domain_url = f"https://{domain_url}"
    parsed = urlparse(domain_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    stats = {"found": None, "files_saved": 0, "urls_discovered": []}

    full_url = f"{base}/llms-full.txt"
    print(f"Checking {full_url}...")
    try:
        resp = httpx.get(full_url, timeout=30, follow_redirects=True, headers=HEADERS)
        if resp.status_code == 200 and len(resp.text) > 500:
            out_path = kb_dir / f"{topic}-llms-full.md"
            header = f"<!-- Source: {full_url} | Tier: A | Topic: {topic} | Fetched: {fetched_date} -->\n\n"
            out_path.write_text(header + resp.text, encoding="utf-8")
            print(f"  FOUND llms-full.txt ({out_path.stat().st_size // 1024}KB)")
            stats["found"] = "llms-full.txt"
            stats["files_saved"] = 1
            return stats
    except Exception as exc:
        print(f"  Error: {exc}")

    index_url = f"{base}/llms.txt"
    print(f"Checking {index_url}...")
    try:
        resp = httpx.get(index_url, timeout=30, follow_redirects=True, headers=HEADERS)
        if resp.status_code == 200 and len(resp.text) > 100:
            urls_found = re.findall(r'https?://[^\s\)>\]"\']+', resp.text)
            urls_found = [u for u in urls_found if urlparse(u).netloc == parsed.netloc]
            urls_found = list(dict.fromkeys(urls_found))
            if urls_found:
                print(f"  FOUND llms.txt with {len(urls_found)} URLs")
                stats["found"] = "llms.txt"
                stats["urls_discovered"] = urls_found
                out_path = kb_dir / f"{topic}-llms-index.md"
                header = f"<!-- Source: {index_url} | Tier: A | Topic: {topic} | Fetched: {fetched_date} -->\n\n"
                out_path.write_text(header + resp.text, encoding="utf-8")
                stats["files_saved"] = 1
                return stats
    except Exception as exc:
        print(f"  Error: {exc}")

    stats["found"] = None
    return stats


# ── BFS crawl ──

class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def extract_links(html: str, base_url: str) -> list[str]:
    parser = LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        return []
    resolved = []
    for link in parser.links:
        if link.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full_url = urljoin(base_url, link).split("#")[0].rstrip("/")
        if full_url:
            resolved.append(full_url)
    return resolved


def should_crawl_url(url: str, base_netloc: str, path_prefix: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc != base_netloc:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    path_lower = parsed.path.lower()
    for skip in CRAWL_SKIP_PATTERNS:
        if path_lower.startswith(skip):
            return False
    for ext in SKIP_EXTENSIONS:
        if path_lower.endswith(ext):
            return False
    if path_prefix and not parsed.path.startswith(path_prefix):
        return False
    return True


def _load_robots(base_url: str) -> RobotFileParser | None:
    """Try to load robots.txt for the given base URL. Returns None on failure."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        resp = httpx.get(robots_url, timeout=10, follow_redirects=True, headers=HEADERS)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
            return rp
    except Exception as e:
        logger.debug("Failed to load robots.txt for %s: %s", base_url, e)
    return None


def bfs_crawl(start_url: str, kb_dir: pathlib.Path, topic: str,
              max_pages: int = 200, max_depth: int = 3,
              delay: float = 0.5) -> dict:
    parsed_start = urlparse(start_url)
    base_netloc = parsed_start.netloc
    path_prefix = parsed_start.path.rstrip("/")
    if len(path_prefix) <= 1:
        path_prefix = ""

    fetched_date = time.strftime("%Y-%m-%d")
    converter = make_converter()

    # Load robots.txt once per crawl
    robots = _load_robots(start_url)
    if robots:
        logger.info("robots.txt loaded for %s", base_netloc)
    else:
        logger.debug("No robots.txt found for %s, proceeding without restrictions", base_netloc)

    queue = deque()
    queue.append((start_url, 0))
    visited = {start_url.rstrip("/")}
    stats = {
        "pages_crawled": 0, "pages_saved": 0,
        "pages_skipped": 0, "pages_failed": 0,
        "bytes_total": 0, "max_depth_reached": 0,
        "robots_blocked": 0,
    }

    print(f"BFS crawl: {start_url} (max {max_pages} pages, depth {max_depth})")

    while queue and stats["pages_crawled"] < max_pages:
        url, depth = queue.popleft()
        if depth > max_depth:
            continue

        stats["max_depth_reached"] = max(stats["max_depth_reached"], depth)
        stats["pages_crawled"] += 1

        # Check robots.txt before fetching
        if robots and not robots.can_fetch(HEADERS["User-Agent"], url):
            stats["robots_blocked"] += 1
            continue

        slug = make_slug(url, topic)
        out_path = kb_dir / slug
        already_saved = out_path.exists()

        try:
            if delay > 0 and stats["pages_crawled"] > 1:
                time.sleep(delay)

            resp = httpx.get(url, timeout=30, follow_redirects=True, headers=HEADERS)
            if resp.status_code == 429:
                # Respect Retry-After header, then re-queue for retry
                retry_after = resp.headers.get("Retry-After", "")
                wait = min(int(retry_after), 60) if retry_after.isdigit() else 10
                logger.info("Rate limited on %s, waiting %ds then retrying", url, wait)
                time.sleep(wait)
                queue.appendleft((url, depth))
                continue
            if resp.status_code != 200:
                stats["pages_failed"] += 1
                continue

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                stats["pages_skipped"] += 1
                continue

            html = resp.text

            if not already_saved:
                md = converter.handle(html)
                result = save_markdown(md, url, topic, "A", kb_dir, fetched_date)
                if result:
                    stats["pages_saved"] += 1
                    stats["bytes_total"] += result.stat().st_size
                else:
                    stats["pages_skipped"] += 1
            else:
                stats["pages_skipped"] += 1

            if depth < max_depth:
                links = extract_links(html, str(resp.url))
                for link in links:
                    normalized = link.rstrip("/")
                    if normalized not in visited and should_crawl_url(
                        normalized, base_netloc, path_prefix
                    ):
                        visited.add(normalized)
                        queue.append((link, depth + 1))

        except Exception as e:
            logger.debug("Crawl failed for %s: %s", url, e)
            stats["pages_failed"] += 1

    return stats


# ── Queue mode ──

def fetch_queue(queue_path: pathlib.Path, kb_dir: pathlib.Path) -> dict:
    if not queue_path.exists():
        return {"error": f"Queue file not found: {queue_path}"}

    urls = json.loads(queue_path.read_text(encoding="utf-8"))
    fetched_date = time.strftime("%Y-%m-%d")
    ok, fail, skip = 0, 0, 0

    for item in urls:
        url = item.get("url", "")
        topic = item.get("topic", "misc")
        tier = item.get("tier", "B")

        if not url.startswith("http"):
            skip += 1
            continue

        filename = make_slug(url, topic)
        out_path = kb_dir / filename
        if out_path.exists():
            skip += 1
            continue

        try:
            resp = httpx.get(url, timeout=30, follow_redirects=True, headers=HEADERS)
            if resp.status_code != 200:
                fail += 1
                continue
            converter = make_converter()
            md = converter.handle(resp.text)
            result = save_markdown(md, url, topic, tier, kb_dir, fetched_date)
            if result:
                ok += 1
            else:
                skip += 1
        except Exception:
            fail += 1

    return {"saved": ok, "failed": fail, "skipped": skip}


def main():
    parser = argparse.ArgumentParser(description="Fetch docs into clean-rag knowledge")
    parser.add_argument("--topic", default="misc", help="Topic name")
    parser.add_argument("--kb-dir", default="", help="Output directory override")
    parser.add_argument("--llms-txt", help="Check domain for llms.txt")
    parser.add_argument("--crawl", help="BFS crawl from URL")
    parser.add_argument("--queue", help="Fetch from JSON queue file")
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.5)

    args = parser.parse_args()
    kb_dir = pathlib.Path(args.kb_dir) if args.kb_dir else KNOWLEDGE_DIR / args.topic
    kb_dir.mkdir(parents=True, exist_ok=True)
    fetched_date = time.strftime("%Y-%m-%d")

    if args.llms_txt:
        check_llms_txt(args.llms_txt, kb_dir, args.topic, fetched_date)
    elif args.crawl:
        bfs_crawl(args.crawl, kb_dir, args.topic,
                  max_pages=args.max_pages, max_depth=args.depth, delay=args.delay)
    elif args.queue:
        fetch_queue(pathlib.Path(args.queue), kb_dir)
    else:
        print("Specify --llms-txt, --crawl, or --queue")
        sys.exit(1)


if __name__ == "__main__":
    main()
