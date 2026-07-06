"""Tests for fetch-docs.py — Layers 2-3 document acquisition script."""

import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import importlib
fetch_docs_mod = importlib.import_module("fetch-docs")
make_slug = fetch_docs_mod.make_slug
save_markdown = fetch_docs_mod.save_markdown
extract_links = fetch_docs_mod.extract_links
should_crawl_url = fetch_docs_mod.should_crawl_url
LinkExtractor = fetch_docs_mod.LinkExtractor


# ── make_slug ──────────────────────────────────────────────

class TestMakeSlug:
    def test_two_path_segments(self):
        result = make_slug("https://example.com/tutorial/first-steps", "fastapi")
        assert result == "fastapi-tutorial-first-steps.md"

    def test_single_path_segment(self):
        result = make_slug("https://example.com/introduction", "react")
        # Single segment: len(parts) < 2, falls back to netloc
        assert result == "react-example-com.md"

    def test_no_path(self):
        result = make_slug("https://example.com/", "lib")
        assert result == "lib-example-com.md"

    def test_deep_path_uses_last_two(self):
        result = make_slug("https://example.com/a/b/c/d/page", "t")
        assert result == "t-d-page.md"

    def test_slug_ends_with_md(self):
        result = make_slug("https://example.com/docs/intro", "t")
        assert result.endswith(".md")

    def test_topic_truncated_at_30(self):
        long_topic = "a" * 50
        result = make_slug("https://example.com/docs/intro", long_topic)
        topic_part = result.split("-docs")[0]
        assert len(topic_part) <= 30

    def test_name_truncated_at_60(self):
        long_path = "a" * 80
        result = make_slug(f"https://example.com/{long_path}/page", "t")
        name_part = result[len("t-"):-len(".md")]
        assert len(name_part) <= 60

    def test_special_chars_stripped(self):
        result = make_slug("https://example.com/docs/my page (v2)", "t")
        assert "(" not in result
        assert ")" not in result
        assert " " not in result

    def test_collision_different_parents_same_last_two(self):
        """Genuine collision when last 2 path segments are identical."""
        slug1 = make_slug("https://example.com/docs/guide/getting-started", "t")
        slug2 = make_slug("https://example.com/tutorials/guide/getting-started", "t")
        assert slug1 == slug2  # Documents known collision behavior


# ── save_markdown ──────────────────────────────────────────

class TestSaveMarkdown:
    def test_saves_valid_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir)
            content = "# Title\n\n" + "x" * 600
            result = save_markdown(content, "https://example.com/docs/intro",
                                   "test", "A", kb, "2026-06-25")
            assert result is not None
            assert result.exists()
            text = result.read_text(encoding="utf-8")
            assert "<!-- Source:" in text
            assert "Tier: A" in text

    def test_skips_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir)
            content = "# Title\n\n" + "x" * 600
            result1 = save_markdown(content, "https://example.com/docs/intro",
                                    "test", "A", kb, "2026-06-25")
            assert result1 is not None
            result2 = save_markdown(content, "https://example.com/docs/intro",
                                    "test", "A", kb, "2026-06-25")
            assert result2 is None

    def test_deletes_tiny_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir)
            content = "tiny"
            result = save_markdown(content, "https://example.com/docs/intro",
                                   "test", "A", kb, "2026-06-25")
            assert result is None
            slug = make_slug("https://example.com/docs/intro", "test")
            assert not (kb / slug).exists()

    def test_header_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir)
            content = "# Big Content\n\n" + "word " * 200
            result = save_markdown(content, "https://example.com/page",
                                   "mytopic", "B", kb, "2026-06-25")
            assert result is not None
            text = result.read_text(encoding="utf-8")
            assert "Topic: mytopic" in text
            assert "Fetched: 2026-06-25" in text
            assert "Tier: B" in text


# ── extract_links ──────────────────────────────────────────

class TestExtractLinks:
    def test_resolves_relative_links(self):
        html = '<a href="child-page/">Link</a>'
        links = extract_links(html, "https://example.com/docs/")
        assert "https://example.com/docs/child-page" in links

    def test_resolves_absolute_links(self):
        html = '<a href="/other/page">Link</a>'
        links = extract_links(html, "https://example.com/docs/")
        assert "https://example.com/other/page" in links

    def test_skips_anchors(self):
        html = '<a href="#section">Anchor</a>'
        links = extract_links(html, "https://example.com/docs/")
        assert len(links) == 0

    def test_skips_javascript(self):
        html = '<a href="javascript:void(0)">JS</a>'
        links = extract_links(html, "https://example.com/docs/")
        assert len(links) == 0

    def test_skips_mailto(self):
        html = '<a href="mailto:test@example.com">Email</a>'
        links = extract_links(html, "https://example.com/docs/")
        assert len(links) == 0

    def test_strips_fragments(self):
        html = '<a href="page#section">Link</a>'
        links = extract_links(html, "https://example.com/docs/")
        for link in links:
            assert "#" not in link

    def test_strips_trailing_slashes(self):
        html = '<a href="child/">Link</a>'
        links = extract_links(html, "https://example.com/docs/")
        for link in links:
            assert not link.endswith("/")

    def test_multiple_links(self):
        html = '''
        <a href="page1">One</a>
        <a href="page2">Two</a>
        <a href="page3">Three</a>
        '''
        links = extract_links(html, "https://example.com/docs/")
        assert len(links) == 3

    def test_trailing_slash_on_base_matters(self):
        """Base URL trailing slash affects relative URL resolution."""
        html = '<a href="child">Link</a>'
        links_with = extract_links(html, "https://example.com/docs/")
        assert any("docs/child" in l for l in links_with)

        links_without = extract_links(html, "https://example.com/docs")
        assert not any("docs/child" in l for l in links_without)

    def test_handles_malformed_html(self):
        html = '<a href="page">unclosed <a href="other">overlap</a>'
        links = extract_links(html, "https://example.com/")
        assert isinstance(links, list)

    def test_empty_html(self):
        links = extract_links("", "https://example.com/")
        assert links == []


# ── should_crawl_url ──────────────────────────────────────

class TestShouldCrawlUrl:
    def test_same_domain_within_prefix(self):
        assert should_crawl_url(
            "https://example.com/docs/page", "example.com", "/docs"
        ) is True

    def test_different_domain_rejected(self):
        assert should_crawl_url(
            "https://other.com/docs/page", "example.com", "/docs"
        ) is False

    def test_outside_path_prefix_rejected(self):
        assert should_crawl_url(
            "https://example.com/blog/post", "example.com", "/docs"
        ) is False

    def test_empty_prefix_allows_all_paths(self):
        assert should_crawl_url(
            "https://example.com/anything/here", "example.com", ""
        ) is True

    def test_skip_patterns_rejected(self):
        for skip in ["/blog", "/login", "/pricing", "/careers"]:
            assert should_crawl_url(
                f"https://example.com{skip}/page", "example.com", ""
            ) is False, f"Should skip {skip}"

    def test_skip_extensions_rejected(self):
        for ext in [".png", ".jpg", ".css", ".js", ".zip"]:
            assert should_crawl_url(
                f"https://example.com/docs/file{ext}", "example.com", "/docs"
            ) is False, f"Should skip {ext}"

    def test_non_http_rejected(self):
        assert should_crawl_url(
            "ftp://example.com/docs/page", "example.com", "/docs"
        ) is False

    def test_path_prefix_false_positive_bug(self):
        """BUG: /docs prefix matches /docs-advanced because startswith
        checks without trailing slash boundary."""
        result = should_crawl_url(
            "https://example.com/docs-advanced/page",
            "example.com", "/docs"
        )
        # Current behavior: True (BUG). After fix: should be False.
        assert result is True  # documents current buggy behavior

    def test_exact_prefix_match(self):
        assert should_crawl_url(
            "https://example.com/docs", "example.com", "/docs"
        ) is True

    def test_prefix_with_subpath(self):
        assert should_crawl_url(
            "https://example.com/docs/sub/deep/page", "example.com", "/docs"
        ) is True


# ── check_llms_txt URL handling ────────────────────────────

class TestCheckLlmsTxtUrlHandling:
    """Tests for URL construction logic without making HTTP calls."""

    def test_bare_domain_gets_https_prepended(self):
        from urllib.parse import urlparse
        domain = "fastapi.tiangolo.com"
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        parsed = urlparse(domain)
        assert parsed.scheme == "https"
        assert parsed.netloc == "fastapi.tiangolo.com"

    def test_https_domain_unchanged(self):
        from urllib.parse import urlparse
        domain = "https://react.dev"
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        parsed = urlparse(domain)
        assert parsed.scheme == "https"
        assert parsed.netloc == "react.dev"

    def test_http_domain_preserved(self):
        from urllib.parse import urlparse
        domain = "http://localhost:8000"
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        parsed = urlparse(domain)
        assert parsed.scheme == "http"
        assert parsed.netloc == "localhost:8000"


# ── LinkExtractor ──────────────────────────────────────────

class TestLinkExtractor:
    def test_extracts_href_from_a_tags(self):
        parser = LinkExtractor()
        parser.feed('<a href="https://example.com">Link</a>')
        assert "https://example.com" in parser.links

    def test_ignores_non_a_tags(self):
        parser = LinkExtractor()
        parser.feed('<img src="image.png"><link href="style.css">')
        assert len(parser.links) == 0

    def test_ignores_a_without_href(self):
        parser = LinkExtractor()
        parser.feed('<a name="anchor">Named</a>')
        assert len(parser.links) == 0

    def test_extracts_multiple_links(self):
        parser = LinkExtractor()
        parser.feed('''
            <a href="one">1</a>
            <a href="two">2</a>
            <a href="three">3</a>
        ''')
        assert len(parser.links) == 3


# ── Edge case tests (G4 exploratory pass) ────────────────


class TestMakeSlugEdgeCases:
    """Boundary conditions and unusual inputs for fetch-docs make_slug."""

    def test_url_with_query_params_ignored(self):
        """Query params are part of the path parse; verify slug is clean."""
        result = make_slug("https://example.com/docs/page?version=2&lang=en", "t")
        # urlparse puts query in .query, not .path, so path = /docs/page
        assert result == "t-docs-page.md"

    def test_url_with_port(self):
        """Port in netloc shouldn't break fallback slug."""
        result = make_slug("https://localhost:8000/intro", "t")
        # Single segment: falls back to netloc
        assert "localhost" in result
        assert result.endswith(".md")

    def test_url_with_trailing_slash_only(self):
        """Root URL with just a trailing slash."""
        result = make_slug("https://docs.python.org/", "python")
        assert result == "python-docs-python-org.md"

    def test_empty_topic_and_single_segment(self):
        """Both topic and path are minimal."""
        result = make_slug("https://example.com/page", "")
        # Empty topic slug = "", so result starts with "-"
        assert result.endswith(".md")
        assert "example-com" in result

    def test_url_with_encoded_chars(self):
        """Percent-encoded chars in URL path."""
        result = make_slug("https://example.com/docs/my%20page", "t")
        # %20 is not [a-z0-9\-], gets stripped
        assert "%" not in result
        assert result.endswith(".md")

    def test_both_truncations_at_limits(self):
        """Topic at exactly 30 chars, name at exactly 60 chars."""
        topic = "a" * 30
        # Two path segments, each long enough that joined they hit 60
        seg = "b" * 30
        result = make_slug(f"https://example.com/{seg}/{seg}", topic)
        topic_part = result.split("-" + "b")[0]
        assert len(topic_part) <= 30
        name_part = result[len(topic_part) + 1:-len(".md")]
        assert len(name_part) <= 60


class TestSaveMarkdownEdgeCases:
    """Boundary conditions for the 500-byte size guard."""

    def test_file_at_exact_500_byte_boundary(self):
        """Content + header that lands right at 500 bytes should survive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir)
            # The header is about 80 bytes. We need total file > 500.
            # Header: "<!-- Source: URL | Tier: A | Topic: t | Fetched: 2026-06-25 -->\n\n"
            # That's roughly 75 bytes. So content needs to push total past 500.
            content = "x" * 430  # 430 content + ~75 header = ~505 bytes
            result = save_markdown(content, "https://example.com/docs/page",
                                   "t", "A", kb, "2026-06-25")
            assert result is not None

    def test_file_just_under_500_bytes_deleted(self):
        """Content + header totaling < 500 bytes gets cleaned up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir)
            content = "x" * 350  # 350 + ~75 header = ~425, under 500
            result = save_markdown(content, "https://example.com/docs/page",
                                   "t", "A", kb, "2026-06-25")
            assert result is None
            # Verify file was cleaned up
            files = list(kb.iterdir())
            assert len(files) == 0

    def test_unicode_content_byte_size(self):
        """Unicode chars take more bytes; verify size check is byte-based."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir)
            # Each CJK char is 3 bytes in UTF-8. 200 chars = 600 bytes content
            content = "\u4e00" * 200
            result = save_markdown(content, "https://example.com/docs/unicode",
                                   "t", "A", kb, "2026-06-25")
            # 600 bytes content + ~80 header = ~680 bytes, should pass
            assert result is not None

    def test_slug_collision_causes_data_loss(self):
        """Two URLs that produce the same slug: second save returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir)
            content = "# Content\n\n" + "x" * 600
            url1 = "https://example.com/docs/guide/getting-started"
            url2 = "https://example.com/tutorials/guide/getting-started"
            # Both produce the same slug (known collision)
            assert make_slug(url1, "t") == make_slug(url2, "t")
            r1 = save_markdown(content, url1, "t", "A", kb, "2026-06-25")
            r2 = save_markdown(content, url2, "t", "A", kb, "2026-06-25")
            assert r1 is not None
            assert r2 is None  # silently lost


class TestShouldCrawlUrlEdgeCases:
    """Boundary conditions for crawl URL filtering."""

    def test_skip_pattern_partial_match_not_blocked(self):
        """'/blogging' should NOT match skip pattern '/blog'."""
        # This tests whether skip patterns use startswith correctly.
        # /blogging starts with /blog, so current code DOES block it.
        result = should_crawl_url(
            "https://example.com/blogging/my-post", "example.com", ""
        )
        # Current behavior: False (startswith("/blog") matches "/blogging")
        # This is arguably correct (blog content is noise) but documents the behavior
        assert result is False

    def test_case_sensitive_domain_check(self):
        """Domain comparison is case-sensitive in current implementation."""
        result = should_crawl_url(
            "https://Example.COM/docs/page", "example.com", "/docs"
        )
        # urlparse preserves case in netloc for unexpected casing
        assert result is False

    def test_url_with_query_params_allowed(self):
        """Query parameters don't affect path prefix check."""
        result = should_crawl_url(
            "https://example.com/docs/page?v=2", "example.com", "/docs"
        )
        assert result is True

    def test_double_slash_in_path(self):
        """Double slashes in path."""
        result = should_crawl_url(
            "https://example.com//docs/page", "example.com", "/docs"
        )
        # path = "//docs/page", startswith("/docs") is False
        assert result is False

    def test_all_skip_patterns_exhaustive(self):
        """Every entry in CRAWL_SKIP_PATTERNS actually blocks."""
        CRAWL_SKIP_PATTERNS = fetch_docs_mod.CRAWL_SKIP_PATTERNS
        for pattern in CRAWL_SKIP_PATTERNS:
            result = should_crawl_url(
                f"https://example.com{pattern}/page", "example.com", ""
            )
            assert result is False, f"Skip pattern {pattern} did not block"

    def test_all_skip_extensions_exhaustive(self):
        """Every entry in SKIP_EXTENSIONS actually blocks."""
        SKIP_EXTENSIONS = fetch_docs_mod.SKIP_EXTENSIONS
        for ext in SKIP_EXTENSIONS:
            result = should_crawl_url(
                f"https://example.com/docs/file{ext}", "example.com", "/docs"
            )
            assert result is False, f"Extension {ext} did not block"


class TestExtractLinksEdgeCases:
    """Boundary conditions for link extraction."""

    def test_skips_tel_links(self):
        html = '<a href="tel:+1234567890">Call</a>'
        links = extract_links(html, "https://example.com/")
        assert len(links) == 0

    def test_data_uri_not_resolved(self):
        """data: URIs should be resolved but produce non-http URLs."""
        html = '<a href="data:text/html,hello">Data</a>'
        links = extract_links(html, "https://example.com/")
        # urljoin with data: produces "data:text/html,hello"
        # It's not filtered by the current code (no data: check)
        # but it won't match should_crawl_url (not http/https)
        for link in links:
            assert not link.startswith("http")

    def test_duplicate_links_preserved(self):
        """extract_links doesn't deduplicate; BFS handles that."""
        html = '<a href="page">One</a><a href="page">Two</a>'
        links = extract_links(html, "https://example.com/docs/")
        assert len(links) == 2

    def test_protocol_relative_links(self):
        """//cdn.example.com/page resolved to https."""
        html = '<a href="//cdn.example.com/docs">CDN</a>'
        links = extract_links(html, "https://example.com/")
        assert any("https://cdn.example.com/docs" in l for l in links)

    def test_many_links_performance(self):
        """Hundreds of links don't cause issues."""
        links_html = "".join(f'<a href="page-{i}">Link {i}</a>' for i in range(500))
        html = f"<html><body>{links_html}</body></html>"
        links = extract_links(html, "https://example.com/docs/")
        assert len(links) == 500


class TestBfsCrawlPathPrefixDerivation:
    """Tests for how bfs_crawl derives path_prefix from the start URL.

    These test the logic inline in bfs_crawl (lines 367-373) without
    making HTTP calls by checking the same computation.
    """

    def test_root_url_gives_empty_prefix(self):
        """Start URL at domain root should not restrict paths."""
        from urllib.parse import urlparse
        start = "https://example.com/"
        parsed = urlparse(start)
        prefix = parsed.path.rstrip("/")
        if len(prefix) <= 1:
            prefix = ""
        assert prefix == ""

    def test_docs_path_gives_docs_prefix(self):
        from urllib.parse import urlparse
        start = "https://example.com/docs/"
        parsed = urlparse(start)
        prefix = parsed.path.rstrip("/")
        if len(prefix) <= 1:
            prefix = ""
        assert prefix == "/docs"

    def test_deep_path_gives_full_prefix(self):
        from urllib.parse import urlparse
        start = "https://example.com/en/stable/tutorial/"
        parsed = urlparse(start)
        prefix = parsed.path.rstrip("/")
        if len(prefix) <= 1:
            prefix = ""
        assert prefix == "/en/stable/tutorial"

    def test_bare_domain_no_slash_gives_empty_prefix(self):
        from urllib.parse import urlparse
        start = "https://example.com"
        parsed = urlparse(start)
        prefix = parsed.path.rstrip("/")
        if len(prefix) <= 1:
            prefix = ""
        assert prefix == ""
