"""Config files that carry live credentials must never reach the index.

`.json`, `.yaml` and `.xml` are all in CODE_EXTENSIONS and the scan has no
gitignore or secrets awareness, so before SKIP_NAME_GLOBS existed these went
straight in. Measured on one real project mid indexing: 14 files with populated
sensitive values, including four `ConnectionStrings.*` entries of 150 plus
characters and an Azure Functions `local.settings.json` holding a database
connection, a SignalR endpoint and a ServiceBus namespace.

Nothing was leaving the machine (the index is localhost only, and those files
were already tracked in git). The real exposure is a `/search` hit lifting a
live connection string into an agent's context.
"""

import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server.file_scan import SKIP_NAME_GLOBS, scan_project  # noqa: E402

#: Names taken from a real .NET solution, not invented for the test.
MUST_BE_SKIPPED = [
    "appsettings.json",
    "appsettings.Development.json",
    "appsettings.Staging.json",
    "appsettings.Test.json",
    "appsettings.Production.json",
    "AppSettings.json",          # Windows is case insensitive, fnmatch is not
    "local.settings.json",
    "secrets.json",
    "db.secrets.json",
    "prod.secrets.yaml",
]

#: Config shaped names that are ordinary source and must survive.
MUST_SURVIVE = [
    "package.json",
    "tsconfig.json",
    "launchSettings.json",
    "settings.json",             # not local.settings.json
    "app.json",
    "appsettings.md",            # right stem, wrong kind of file
    "myappsettings_helper.py",
]


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / "Api").mkdir(parents=True)
    for name in MUST_BE_SKIPPED + MUST_SURVIVE:
        # Real content, so nothing is skipped for being empty or degenerate.
        (root / "Api" / name).write_text(
            '{"ConnectionStrings": {"Db": "Server=x;Password=hunter2"}}\n'
            "# padding so the file is not trivially small\n" * 4,
            encoding="utf-8",
        )
    (root / "Api" / "Program.cs").write_text(
        "public class Program { static void Main() { } }\n", encoding="utf-8"
    )
    return root


def _names(root: Path) -> set[str]:
    return {Path(p).name for p in scan_project(str(root))}


class TestSecretConfigIsSkipped:
    @pytest.mark.parametrize("name", MUST_BE_SKIPPED)
    def test_it_never_reaches_the_scan(self, project, name):
        assert name not in _names(project), (
            f"{name} is indexable, so its contents can surface in a search "
            f"result and be lifted into an agent's context"
        )

    @pytest.mark.parametrize("name", MUST_SURVIVE)
    def test_ordinary_config_is_untouched(self, project, name):
        """Over blocking is its own failure. package.json and tsconfig.json
        carry no credentials and are genuinely useful to search."""
        assert name in _names(project), (
            f"{name} was skipped, but it holds no credentials and the glob "
            f"should not have matched it"
        )

    def test_real_source_still_indexed(self, project):
        assert "Program.cs" in _names(project)

    def test_the_globs_are_lowercase(self):
        """The scan lowercases the filename before matching, so an uppercase
        glob could never fire. Pin it rather than rely on nobody adding one."""
        for glob in SKIP_NAME_GLOBS:
            assert glob == glob.lower(), (
                f"{glob!r} can never match: the name is lowercased first"
            )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
