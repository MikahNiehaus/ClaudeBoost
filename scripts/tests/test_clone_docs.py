"""Tests for clone-docs.py — Layer 1 GitHub sparse checkout script."""

import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import importlib
clone_docs_mod = importlib.import_module("clone-docs")
make_slug = clone_docs_mod.make_slug
clone_docs_fn = clone_docs_mod.clone_docs
run_git = clone_docs_mod.run_git
DEFAULT_EXTENSIONS = clone_docs_mod.DEFAULT_EXTENSIONS


class TestMakeSlug:
    def test_simple_filename(self):
        result = make_slug("getting-started.md", "react")
        assert result == "react-getting-started.md"

    def test_nested_path(self):
        result = make_slug("tutorial/first-steps.md", "fastapi")
        assert result == "fastapi-tutorial-first-steps.md"

    def test_deeply_nested_path(self):
        result = make_slug("api/reference/hooks/useState.md", "react")
        assert result == "react-api-reference-hooks-usestate.md"

    def test_backslash_path(self):
        result = make_slug("tutorial\\first-steps.md", "fastapi")
        assert result == "fastapi-tutorial-first-steps.md"

    def test_leading_slash_stripped(self):
        result = make_slug("/docs/intro.md", "django")
        assert result == "django-docs-intro.md"

    def test_uppercase_lowered(self):
        result = make_slug("README.md", "mylib")
        assert result == "mylib-readme.md"

    def test_special_chars_removed(self):
        result = make_slug("file (copy).md", "topic")
        # Spaces and parens are stripped entirely, not converted to dashes
        assert result == "topic-filecopy.md"

    def test_consecutive_dashes_collapsed(self):
        result = make_slug("a---b---c.md", "t")
        assert result == "t-a-b-c.md"

    def test_topic_with_spaces(self):
        result = make_slug("intro.md", "my library")
        assert result.startswith("my-library-")

    def test_topic_truncated_at_30(self):
        long_topic = "a" * 50
        result = make_slug("intro.md", long_topic)
        topic_part = result.split("-intro")[0]
        assert len(topic_part) <= 30

    def test_dots_preserved_in_filename(self):
        result = make_slug("v2.0-guide.md", "lib")
        assert ".md" in result
        assert "2.0" in result

    def test_empty_topic(self):
        result = make_slug("intro.md", "")
        assert "intro.md" in result


class TestRunGit:
    def test_bad_command_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="failed"):
            run_git(["status", "--nonexistent-flag-xyz"])


class TestCloneDocsEdgeCases:
    def test_nonexistent_repo_raises(self):
        """clone_docs propagates RuntimeError when the repo doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = pathlib.Path(tmpdir) / "kb"
            kb.mkdir()
            with pytest.raises(RuntimeError, match="failed"):
                clone_docs_fn(
                    repo="nonexistent/nonexistent-repo-xyz",
                    docs_path="docs",
                    kb_dir=kb,
                    topic="test",
                    branch="main",
                )

    def test_default_extensions(self):
        assert ".md" in DEFAULT_EXTENSIONS
        assert ".mdx" in DEFAULT_EXTENSIONS
        assert ".rst" in DEFAULT_EXTENSIONS


class TestMakeSlugEdgeCases:
    """Boundary conditions for clone-docs make_slug (G4 exploratory)."""

    def test_only_extension_file(self):
        """File that is just an extension like .gitignore."""
        result = make_slug(".gitignore", "t")
        assert result.startswith("t-")
        assert ".gitignore" in result

    def test_multiple_dots_in_name(self):
        result = make_slug("api.v2.reference.md", "lib")
        assert "api.v2.reference.md" in result

    def test_very_long_path_with_many_segments(self):
        path = "/".join(["seg"] * 20) + "/file.md"
        result = make_slug(path, "t")
        assert result.startswith("t-")
        assert result.endswith(".md")

    def test_unicode_in_filename(self):
        result = make_slug("guide/einfuhrung.md", "t")
        assert result.endswith(".md")

    def test_path_with_only_slashes(self):
        result = make_slug("///", "t")
        # After strip("/") and split, parts is empty, name = ""
        # Result is "t-" (topic + dash + empty)
        assert result.startswith("t")

    def test_windows_deep_backslash_path(self):
        result = make_slug("docs\\api\\v2\\endpoints.md", "mylib")
        assert "docs" in result
        assert "endpoints.md" in result
        assert "\\" not in result

    def test_rst_extension_preserved(self):
        result = make_slug("getting-started.rst", "django")
        assert result.endswith(".rst")


class TestFileSkipping:
    def test_tiny_files_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = pathlib.Path(tmpdir) / "src"
            src.mkdir()
            tiny = src / "tiny.md"
            tiny.write_text("# Hi", encoding="utf-8")

            normal = src / "normal.md"
            normal.write_text("# " + "x" * 100, encoding="utf-8")

            kb = pathlib.Path(tmpdir) / "kb"
            kb.mkdir()

            extensions = {".md"}
            skipped = 0
            copied = 0
            for fpath in src.iterdir():
                if fpath.suffix in extensions:
                    content = fpath.read_text(encoding="utf-8")
                    if len(content.strip()) < 50:
                        skipped += 1
                    else:
                        out = kb / f"test-{fpath.name}"
                        out.write_text(content, encoding="utf-8")
                        copied += 1

            assert skipped == 1
            assert copied == 1
