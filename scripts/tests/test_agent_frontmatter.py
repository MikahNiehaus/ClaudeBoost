"""
Agent definitions must have parseable YAML frontmatter.

Claude Code reads every `*.md` in an agents directory and registers it by the
`name:` in its frontmatter. A file whose frontmatter does not parse is dropped,
and nothing reports that it was dropped: the agent is simply absent from the
agent list, and a spawn fails with "Agent type '<name>' not found".

Two definitions carried a `description:` containing a colon followed by a
space (`MODE: evidence-judge`, `not a verifier: bad-cop is still...`). That
sequence is a mapping indicator in an unquoted YAML scalar, so both files
failed to parse while the other six in the same directory parsed fine.

The shipped copy under clean-rag/portable/agents/ is always checked. The
installed copy under ~/.claude/agents/ is checked only when it exists, so the
suite runs the same on a machine that has never installed ClaudeBoost.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PORTABLE_AGENTS = REPO_ROOT / "clean-rag" / "portable" / "agents"

REQUIRED_KEYS = ("name", "description", "tools")


def _installed_agents() -> Path | None:
    """The installed agents directory, or None when ClaudeBoost is not installed.

    Honours HOME and USERPROFILE so the test follows a tmp_path override the
    same way the other suites do, rather than reading the real home directory
    when a test redirects it.
    """
    home = os.environ.get("CLAUDE_CONFIG_DIR")
    if home:
        candidate = Path(home) / "agents"
    else:
        base = os.environ.get("USERPROFILE") or os.environ.get("HOME")
        if not base:
            return None
        candidate = Path(base) / ".claude" / "agents"
    return candidate if candidate.is_dir() else None


def _agent_files() -> list[Path]:
    files: list[Path] = []
    if PORTABLE_AGENTS.is_dir():
        files.extend(sorted(PORTABLE_AGENTS.glob("*.md")))
    installed = _installed_agents()
    if installed is not None:
        files.extend(sorted(installed.glob("*.md")))
    return files


def _split_frontmatter(path: Path) -> str:
    """Return the frontmatter block, or fail the test with a clear reason."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.startswith("---\n"), (
        f"{path} does not open with a --- frontmatter delimiter, so Claude Code "
        f"has no frontmatter to read and the agent will not register"
    )
    end = text.find("\n---", 3)
    assert end > 0, f"{path} has an unterminated frontmatter block"
    return text[3:end]


def _ids(files: list[Path]) -> list[str]:
    return [f"{p.parent.name}/{p.name}" for p in files]


AGENT_FILES = _agent_files()


@pytest.mark.skipif(not AGENT_FILES, reason="no agent definitions on this machine")
class TestAgentFrontmatter:
    @pytest.mark.parametrize("path", AGENT_FILES, ids=_ids(AGENT_FILES))
    def test_frontmatter_parses_as_yaml(self, path: Path):
        block = _split_frontmatter(path)
        try:
            parsed = yaml.safe_load(block)
        except yaml.YAMLError as exc:
            pytest.fail(
                f"{path} frontmatter is not valid YAML, so Claude Code drops the "
                f"whole agent and it never registers.\n{exc}\n"
                f"The usual cause is an unquoted description containing ': '. "
                f"Wrap the value in double quotes."
            )
        assert isinstance(parsed, dict), (
            f"{path} frontmatter parsed as {type(parsed).__name__}, not a mapping"
        )

    @pytest.mark.parametrize("path", AGENT_FILES, ids=_ids(AGENT_FILES))
    def test_required_keys_present(self, path: Path):
        parsed = yaml.safe_load(_split_frontmatter(path))
        missing = [k for k in REQUIRED_KEYS if k not in parsed]
        assert not missing, f"{path} frontmatter is missing {missing}"

    @pytest.mark.parametrize("path", AGENT_FILES, ids=_ids(AGENT_FILES))
    def test_name_matches_filename(self, path: Path):
        parsed = yaml.safe_load(_split_frontmatter(path))
        assert parsed["name"] == path.stem, (
            f"{path} declares name={parsed['name']!r} but is filed as "
            f"{path.stem!r}. The name is what a spawn resolves, so a mismatch "
            f"means the agent is not spawnable under the name people use."
        )

    @pytest.mark.parametrize("path", AGENT_FILES, ids=_ids(AGENT_FILES))
    def test_description_is_a_usable_string(self, path: Path):
        parsed = yaml.safe_load(_split_frontmatter(path))
        description = parsed["description"]
        assert isinstance(description, str) and description.strip(), (
            f"{path} description must be a non-empty string; the router reads "
            f"it to decide when the agent applies"
        )
