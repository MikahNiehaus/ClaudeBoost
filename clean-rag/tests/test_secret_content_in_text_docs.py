"""Secret bearing content in a plain .txt/.md file reaches the index and is
returned by search.

test_secret_config_not_indexed.py already covers config SHAPED filenames
(appsettings.json, secrets.yaml, ...) via SKIP_NAME_GLOBS. This covers the gap
next to it: SKIP_NAME_GLOBS only matches config file NAME patterns, and
``.txt``/``.md`` are both in CODE_EXTENSIONS with no content aware secret
check anywhere in the pipeline. A file merely named ``credentials.txt``,
``notes.md``, or ``TODO.md`` -- exactly where a developer jots a real value
"for now" -- passes every filter scan_project has, gets chunked and embedded
like ordinary prose, and its content comes back verbatim in a /search result.

file_scan.py's own module docstring states the risk this is supposed to guard
against: "a /search hit can lift a live connection string into an agent's
context, and agents send their context onward." That reasoning does not stop
at the JSON/YAML boundary -- a credential in a .txt or .md file is the same
exposure through a different extension, and this test proves it end to end
through the real indexing and search path, not just at the filename filter.

Confirmed manually against the real embedding model too: a fake AWS key and DB
password placed in credentials.txt came back as a top-3 result for every one
of five unrelated test queries -- including "quantum physics and butterflies"
-- at similarity scores (0.62-0.70) comfortably above DEFAULT_MIN_SCORE (0.5).
This test uses the lightweight StubEmbedder (same harness as
test_search_incomplete_index.py) so it never loads a real model; the assertion
is content reaching a chunk that any query can retrieve, not a particular
score.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.file_scan import scan_project  # noqa: E402

SECRET_MARKER = "AKIAIOSFODNN7EXAMPLEFAKESECRETVALUE1234567890"

CONTENT = (
    f"AWS_SECRET_ACCESS_KEY={SECRET_MARKER}\n"
    "DB_PASSWORD=SuperSecretProdPassword!2026\n"
)

#: Names a developer plausibly uses for a scratch note that still carries a
#: real secret. None look like a config file and none match SKIP_NAME_GLOBS.
SECRET_BEARING_TEXT_FILES = ["credentials.txt", "notes.md", "TODO.md"]


class StubEmbedder:
    model_name = "stub-embedder"

    def embed(self, texts):
        return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def _names(root: Path) -> set[str]:
    return {Path(p).name for p in scan_project(str(root))}


class TestScanLayer:
    """File selection must decide on content, not just on the filename."""

    def test_secret_bearing_txt_and_md_never_pass_the_scan(self, tmp_path):
        for name in SECRET_BEARING_TEXT_FILES:
            (tmp_path / name).write_text(CONTENT, encoding="utf-8")
        (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")

        names = _names(tmp_path)
        leaked = [n for n in SECRET_BEARING_TEXT_FILES if n in names]
        assert leaked == [], (
            f"these files carry a live credential and are still indexable, so "
            f"their contents can surface in a /search result and be lifted into "
            f"an agent's context: {leaked}"
        )
        assert "main.py" in names, "ordinary source must be unaffected"

    def test_real_source_carrying_a_credential_is_also_excluded(self, tmp_path):
        """The rule is about content, so the extension must not decide it.

        A credential pasted into a .py is the same exposure as one in a .txt,
        and a check keyed on ``.txt``/``.md`` would miss it.
        """
        (tmp_path / "settings.py").write_text(
            f'AWS_SECRET_ACCESS_KEY = "{SECRET_MARKER}"\n', encoding="utf-8",
        )
        assert "settings.py" not in _names(tmp_path)

    def test_code_that_reads_a_secret_from_config_is_still_indexed(self, tmp_path):
        """The correct pattern must stay searchable.

        Measured on a real .NET project, matching an unquoted right hand side
        dropped 26 files of 1668 and 24 of them were this: code fetching a
        credential out of configuration rather than holding one. That is both
        the pattern you want and the code people most need to find.
        """
        (tmp_path / "Startup.cs").write_text(
            "public class Startup {\n"
            "    public void Configure(IConfiguration configuration) {\n"
            '        var apiKey = configuration.GetValue<string>("Ai:ApiKey");\n'
            '        var connectionString = Environment.GetEnvironmentVariable("DB_CONN");\n'
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        assert "Startup.cs" in _names(tmp_path)

    def test_copy_and_identifiers_that_merely_mention_a_secret_are_indexed(self, tmp_path):
        """A name can contain a credential word without holding a credential.

        Both shapes are from real projects: validation copy shown to a user,
        and the name of an identity policy.
        """
        (tmp_path / "Input.tsx").write_text(
            'const passwordErrorMessage = "Passwords must contain a '
            'non-alphanumeric character";\n'
            'const CHANGE_PASSWORD_POLICY_NAME = "B2C_1A_NEIGHBORCHANGEPASSWORD";\n',
            encoding="utf-8",
        )
        assert "Input.tsx" in _names(tmp_path)

    def test_placeholder_credentials_are_not_treated_as_secrets(self, tmp_path):
        """Over blocking is its own failure: docs telling a reader where to put
        their own key must stay searchable."""
        (tmp_path / "SETUP.md").write_text(
            "# Setup\n\n"
            "Set `API_KEY=<your-api-key-here>` in your shell.\n"
            "Then export `DB_PASSWORD=${DB_PASSWORD}` from your secret store.\n"
            "For local work `password = changeme_please` is fine.\n",
            encoding="utf-8",
        )
        assert "SETUP.md" in _names(tmp_path)

    def test_ordinary_txt_and_md_still_survive(self, tmp_path):
        """A blanket ban on .txt/.md would be its own regression: most of
        that content is genuinely useful to search (README, design notes)."""
        (tmp_path / "README.md").write_text(
            "# My Project\n\nThis project does useful things.\n", encoding="utf-8",
        )
        (tmp_path / "notes.txt").write_text(
            "Remember to refactor the parser module next sprint.\n",
            encoding="utf-8",
        )
        names = _names(tmp_path)
        assert "README.md" in names
        assert "notes.txt" in names


class TestSecretsUnderAQuotedKey:
    """A credential keyed the way JSON keys it must not reach the index.

    JSON quotes its keys: ``{"password": "value"}``. That closing quote sits
    between the name and the colon, so a rule anchored straight to ``:`` or
    ``=`` never starts matching, and content based detection did not fire on
    any .json file at all. YAML's ``password: "value"`` has no such quote and
    always matched, which is why testing only YAML or .env shaped input misses
    this entirely, as the rest of this file did (SKIP_NAME_GLOBS-matched
    ``appsettings.json`` in TestEndToEndThroughSearch, never a JSON filename
    outside that glob list).

    This is the shape file_scan.py's own module docstring names as the
    original incident: "four ConnectionStrings.* entries" in a real project's
    JSON config. Content based detection exists to catch a secret in a file
    whose NAME does not signal it, and ``config.json``, ``db_config.json`` and
    ``settings.json`` are all ordinary names outside the five glob patterns.
    """

    def test_a_json_password_key_is_detected(self, tmp_path):
        (tmp_path / "config.json").write_text(
            '{"password": "Kx7mQ2vTpL9wRz4nJh8bYc3d"}\n', encoding="utf-8",
        )
        (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")

        names = _names(tmp_path)
        assert "config.json" not in names, (
            "config.json holds a real-shaped password under a JSON key and "
            "was still indexed, so a /search hit can return it verbatim"
        )
        assert "main.py" in names, (
            "the neighbouring source file was dropped too: the rule is now "
            "excluding more than the file that carries the credential"
        )

    def test_a_json_connection_string_key_is_detected(self, tmp_path):
        (tmp_path / "db_config.json").write_text(
            '{"connectionString": "Server=tcp:prod;User=admin;'
            'Password=Kx7mQ2vTpL9wRz4n;"}\n',
            encoding="utf-8",
        )
        names = _names(tmp_path)
        assert "db_config.json" not in names, (
            "a JSON connectionString key with a real-shaped password was "
            "still indexed, the same exposure the appsettings.json "
            "SKIP_NAME_GLOBS entry exists to prevent, just under a filename "
            "that glob does not cover"
        )

    def test_the_same_value_in_yaml_syntax_is_caught(self, tmp_path):
        """Control: the unquoted-key syntax was never the broken one, so a
        regression here means the shared rule broke rather than the JSON half."""
        (tmp_path / "settings.yaml").write_text(
            'password: "Kx7mQ2vTpL9wRz4nJh8bYc3d"\n', encoding="utf-8",
        )
        names = _names(tmp_path)
        assert "settings.yaml" not in names, (
            "sanity check failed: the YAML control case should already be "
            "caught by _QUOTED_SECRET_ASSIGNMENT_RE, which would mean the "
            "JSON failures above are not about the syntax after all"
        )


class TestEndToEndThroughSearch:
    """The real defect: the secret does not just pass the scan, it comes back
    out of /search. Written to assert the desired end state (no chunk
    containing the secret marker is ever returned), so it currently FAILS
    against the real pipeline -- the same red-first shape as
    test_search_broken_index_no_signal.py and test_index_lock_race.py.
    """

    def test_secret_marker_must_never_be_returned_by_search(self, tmp_path, monkeypatch):
        from server import indexing, search

        monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
        monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
        monkeypatch.setattr(search, "DATABASES_DIR", tmp_path / "databases")

        project = tmp_path / "proj"
        project.mkdir()
        (project / "credentials.txt").write_text(CONTENT, encoding="utf-8")
        (project / "main.py").write_text(
            "def handler(payload):\n    return len(payload)\n", encoding="utf-8",
        )

        result = indexing.index_project(str(project), StubEmbedder(), force=True)
        assert result["files_indexed"] == 1, (
            "main.py must be indexed and credentials.txt must not; "
            f"files_indexed={result['files_indexed']}"
        )

        # index_project only records __model_id__ when given a real ModelCache
        # (indexing.py's plain-embedder backward-compat branch leaves it
        # unset). Patch it in directly so the provenance gate does not refuse
        # the search and mask whether the secret-leak defect exists -- same
        # workaround test_search_incomplete_index.py uses.
        import json
        _root, _pid, _idx, _chroma, manifest_path = indexing._project_paths(str(project))
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw["__model_id__"] = "stub-embedder"
        manifest_path.write_text(json.dumps(raw), encoding="utf-8")

        meta_out = {}
        results = search.search(
            "completely unrelated query about quantum physics and butterflies",
            [f"project:{project}"],
            StubEmbedder(),
            mode="vector",
            min_score=0.0,
            meta_out=meta_out,
        )

        leaking = [r for r in results if SECRET_MARKER in r.get("content", "")]
        assert not leaking, (
            f"a query with nothing to do with credentials.txt returned a "
            f"chunk containing the fake AWS secret marker: {leaking}. All "
            f"embedders return the same fixed vector here, so this is not an "
            f"artifact of a coincidentally close embedding -- with a real "
            f"embedder every candidate scores 'close enough' for a small "
            f"project (see test_confident_wrong_answers.py), and there is no "
            f"content-aware gate anywhere in the pipeline to catch it before "
            f"it is returned."
        )

    def test_the_per_edit_reindex_path_refuses_it_too(self, tmp_path, monkeypatch):
        """reindex_file is the path that actually runs most of the time.

        The per edit hook calls it directly and it never goes through
        scan_project, so a rule enforced only there leaves the common path
        open: index the project first, then write the credential file and let
        the edit hook pick it up.
        """
        from server import indexing, search

        monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
        monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
        monkeypatch.setattr(search, "DATABASES_DIR", tmp_path / "databases")

        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text(
            "def handler(payload):\n    return len(payload)\n", encoding="utf-8",
        )
        indexing.index_project(str(project), StubEmbedder(), force=True)

        credentials = project / "credentials.txt"
        credentials.write_text(CONTENT, encoding="utf-8")
        result = indexing.reindex_file(str(project), str(credentials), StubEmbedder())

        assert result.get("skipped") is True, (
            f"reindex_file indexed a file holding a live credential: {result}"
        )
        assert result.get("chunks_created") is None

    def test_the_per_edit_reindex_path_applies_the_config_globs(self, tmp_path, monkeypatch):
        """Same divergence, for the rule that shipped before this one.

        appsettings.json is refused by scan_project via SKIP_NAME_GLOBS, and
        was indexed anyway whenever somebody edited it.
        """
        from server import indexing, search

        monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
        monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
        monkeypatch.setattr(search, "DATABASES_DIR", tmp_path / "databases")

        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text(
            "def handler(payload):\n    return len(payload)\n", encoding="utf-8",
        )
        indexing.index_project(str(project), StubEmbedder(), force=True)

        appsettings = project / "appsettings.json"
        appsettings.write_text(
            '{\n  "ConnectionStrings": {\n'
            + "".join(
                f'    "Db{i}": "Server=prod{i};User Id=sa;Pwd=hunter{i}",\n'
                for i in range(40)
            )
            + '  }\n}\n',
            encoding="utf-8",
        )
        result = indexing.reindex_file(str(project), str(appsettings), StubEmbedder())

        assert result.get("skipped") is True, (
            f"reindex_file indexed a config file SKIP_NAME_GLOBS refuses: {result}"
        )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
