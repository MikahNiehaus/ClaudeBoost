"""Real gaps in tests/test_no_machine_specific_paths.py's leak detector, found
by attacking it with real-world shapes rather than the fixtures it ships with.

Each was confirmed by planting a real leak in a real tracked file (README.md,
clean-rag/server/kanban.html), running the full suite green, and reverting.

Written by bad-cop to prove the gaps; inverted here to assert they are closed.
The detector carries its own fixtures for the same cases; these stay because
they are the record of which evasion was tried and what it cost to close.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

DETECTOR = Path(__file__).resolve().parent / "test_no_machine_specific_paths.py"


def _load_detector():
    spec = importlib.util.spec_from_file_location("leak_detector_mod", DETECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


det = _load_detector()


class TestMarkupIsScanned:
    def test_html_is_scanned(self):
        assert ".html" in det.SCANNED_SUFFIXES

    def test_the_tracked_html_file_that_proved_the_gap_is_now_covered(self):
        """clean-rag/server/kanban.html is tracked, and .html was unscanned, so
        a home directory or client hostname planted there was invisible.
        Confirmed live: adding
        '<!-- C:\\Users\\jdoe\\Documents and api-test.someclient.com -->'
        to that file left the full suite green (6 passed)."""
        repo_root = DETECTOR.resolve().parents[1]
        target = repo_root / "clean-rag" / "server" / "kanban.html"
        assert target.is_file()
        assert target.suffix.lower() in det.SCANNED_SUFFIXES

    def test_the_planted_leak_shape_is_detected(self):
        line = "<!-- C:\\Users\\jdoe\\Documents and api-test.someclient.com -->"
        assert det._home_hits(line) == ["jdoe"]
        assert det._env_host_hits(line) == ["api-test.someclient.com"]


class TestEnvironmentWordListCoversCommonSpellings:
    """Each of these is a real, common lower-environment naming convention
    that the detector missed."""

    def test_development_spelled_out(self):
        assert det._env_host_hits("api-development.someclient.com")

    def test_stg_abbreviation(self):
        assert det._env_host_hits("manager-stg.someclient.com")

    def test_int_abbreviation(self):
        assert det._env_host_hits("api-int.someclient.com")

    def test_acc_abbreviation(self):
        assert det._env_host_hits("portal-acc.someclient.net")

    def test_the_widening_did_not_cost_a_public_citation(self):
        """The reason the detector stayed narrow: a noisy checker gets switched
        off. Every host here is a real public site that matching these four
        words in any position would have claimed."""
        for benign in (
            "https://www.acc.org/guidelines",
            "https://www.stg.co.jp/",
            "https://stg-labs.com/",
            "https://acc-ltd.co.uk/",
            "https://www.int-evry.fr/x",
            "https://docs.acc-systems.io/",
            "https://www.development-bank.org/",
            "https://accounts.google.com/signin",
            "https://developer.mozilla.org/en-US/docs/Web",
            "https://developers.googleblog.com/z",
            "https://dev.azure.com/org/project",
        ):
            assert det._env_host_hits(benign) == [], benign


class TestNumberedEnvironmentsAreStillEnvironments:
    """A second copy of an environment gets a number, and exact membership in
    _ENV_WORDS made every one of them invisible."""

    def test_numbered_test_environment(self):
        assert det._env_host_hits("api-test1.someclient.com")

    def test_numbered_dev_environment(self):
        assert det._env_host_hits("api-dev2.someclient.com")

    def test_a_number_does_not_invent_an_environment(self):
        for benign in ("https://www.s3.amazonaws.com/bucket",
                       "https://web1.example.org/",
                       "https://api2.github.com/"):
            assert det._env_host_hits(benign) == [], benign


class TestTheInstanceNumberLandsAnywhere:
    """Stripping a trailing run of digits reads api-test1 and nothing else.
    Each of these returned [] while the strip was the whole rule."""

    def test_a_number_inside_the_label(self):
        assert det._env_host_hits("api-test10x.someclient.com")

    def test_a_number_in_front_of_the_word(self):
        assert det._env_host_hits("api-2test.someclient.com")

    def test_a_number_in_front_of_the_whole_label(self):
        assert det._env_host_hits("01dev.someclient.com")

    def test_a_plural_is_not_an_instance(self):
        """The cost of reading a digit-then-letter suffix is that a bare
        trailing letter must not count, or every plural becomes a tier."""
        for benign in ("https://devs.someclient.com/docs",
                       "https://demos.someorg.net/",
                       "https://tests.someorg.io/"):
            assert det._env_host_hits(benign) == [], benign


class TestAnAllowedHostIsNotAnAllowedZone:
    """paypal.com sat in the allowlist so one public sandbox host would pass,
    and it exempted every name under the domain with it."""

    def test_a_named_environment_under_an_allowed_domain_is_caught(self):
        assert det._env_host_hits("api-test.paypal.com")
        assert det._env_host_hits("manager-stg.paypal.com")

    def test_the_documentation_zones_still_exempt_their_subdomains(self):
        """Fixtures need a realistic environment hostname that implicates
        nobody, which is what contoso.com and example.com are for."""
        assert det._env_host_hits("api-test.contoso.com") == []
        assert det._env_host_hits("manager-stg.example.org") == []


class TestAPublicSandboxIsNotALeak:
    def test_paypals_documented_sandbox_host(self):
        """api-m.sandbox.paypal.com appears verbatim in PayPal's own samples.
        Claiming it as a client environment is the noise that gets a checker
        switched off."""
        assert det._env_host_hits("https://api-m.sandbox.paypal.com/v2/x") == []

    def test_a_client_sandbox_is_still_caught(self):
        assert det._env_host_hits("api-sandbox.someclient.com")


class TestTemplateFilesAreScanned:
    def test_dot_example_is_scanned(self):
        """.env.example is tracked and carried the same hostnames and username
        as the file it is a template for, with nothing reading it."""
        assert ".example" in det.SCANNED_SUFFIXES

    def test_the_tracked_templates_are_in_the_scan_set(self):
        scanned = {p.name for p in det._scannable()}
        assert ".env.example" in scanned


class TestPlaceholderNameCollisionWithARealUsername:
    def test_a_real_developer_named_test_is_no_longer_skipped(self):
        """'test' is an ordinary Windows account name on a shared QA machine,
        so treating it as a stand-in silently accepted a real leak."""
        assert det._home_hits(r"C:\Users\test\Documents\client-notes.txt") == ["test"]

    def test_testuser_is_still_a_placeholder(self):
        """Dropping 'test' must not drag the obvious stand-ins with it."""
        assert det._home_hits(r"C:\Users\testuser\project") == []
