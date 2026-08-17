"""github_search returned an empty list for every query, and callers read that
as "nothing like this exists on GitHub".

Two measured causes. The default timeout was 6.0s while a successful
unauthenticated repository search takes ~7s, so the happy path timed out. And
there was no code search at all: /github-search hits
api.github.com/search/repositories, which matches name, description, README and
topics, so no query however good can find a file containing a given line.

That combination made a swipe check structurally unable to find prior art while
reporting a confident zero. These tests pin the behaviours that stop it
recurring. Every one of them monkeypatches httpx, so nothing here touches the
network or depends on GitHub being up.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import github_search as gs  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json


class FakeClient:
    """Stands in for httpx.Client. Serves one response per call from a queue."""

    def __init__(self, responses, calls, **kwargs):
        self._responses = responses
        self._calls = calls
        self.timeout = kwargs.get("timeout")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None):
        self._calls.append({"url": url, "params": params, "timeout": self.timeout})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture()
def http(monkeypatch):
    """Queue responses, then read back what was actually requested.

    Also removes the real backoff. Without this the retry tests would each sleep
    5.5s of wall clock for no added signal.
    """
    state = {"responses": [], "calls": []}
    monkeypatch.setattr(gs, "_BACKOFF_S", (0.0, 0.0))
    monkeypatch.setattr(
        gs.httpx, "Client",
        lambda **kw: FakeClient(state["responses"], state["calls"], **kw),
    )
    return state


def _repo_payload(n=1):
    return {
        "total_count": 4992,
        "items": [
            {"full_name": f"owner/repo{i}", "html_url": f"https://github.com/owner/repo{i}",
             "stargazers_count": 100 + i, "forks_count": i, "language": "Python",
             "updated_at": "2026-01-01T00:00:00Z", "archived": False,
             "description": f"repo {i}"}
            for i in range(n)
        ],
    }


# ── the bug that made every search look empty ────────────────────────────────

class TestTimeoutIsAboveMeasuredLatency:
    """A successful unauthenticated search measures ~7s. A 6.0s ceiling turned
    the happy path into {"results": [], "error": "timed out"}."""

    def test_default_timeout_clears_real_measured_latency(self):
        assert gs.DEFAULT_TIMEOUT >= 15.0, (
            f"DEFAULT_TIMEOUT is {gs.DEFAULT_TIMEOUT}s. A successful "
            "unauthenticated repo search was measured at 6.97s, so anything near "
            "6s times out on the happy path and reports an empty result set."
        )

    def test_the_default_is_the_timeout_actually_sent(self, http):
        http["responses"] = [FakeResponse(json_data=_repo_payload())]
        gs.github_search("anything")
        assert http["calls"][0]["timeout"] == gs.DEFAULT_TIMEOUT


# ── retries must actually wait ───────────────────────────────────────────────

class TestRetryOnTransientOnly:
    def test_a_transient_5xx_is_retried_then_succeeds(self, http):
        http["responses"] = [
            FakeResponse(status_code=503),
            FakeResponse(json_data=_repo_payload(2)),
        ]
        out = gs.github_search("q")
        assert out["error"] is None
        assert len(out["results"]) == 2
        assert len(http["calls"]) == 2, "should have retried exactly once"

    def test_a_404_is_answered_not_retried(self, http):
        http["responses"] = [FakeResponse(status_code=404, json_data={"message": "Not Found"})]
        out = gs.github_search("q")
        assert out["results"] == []
        assert "404" in out["error"]
        assert len(http["calls"]) == 1, "a 4xx is a real answer, retrying it wastes quota"

    def test_it_gives_up_after_max_attempts(self, http):
        http["responses"] = [FakeResponse(status_code=504) for _ in range(gs._MAX_ATTEMPTS)]
        out = gs.github_search("q")
        assert out["results"] == []
        assert len(http["calls"]) == gs._MAX_ATTEMPTS

    def test_retries_sleep_between_attempts(self, monkeypatch):
        """Three attempts inside one second re-ask a throttling server for the
        same reason it just refused. That is one request sent thrice, not a retry."""
        slept = []
        monkeypatch.setattr(gs.time, "sleep", lambda s: slept.append(s))
        calls = []
        responses = [FakeResponse(status_code=503), FakeResponse(status_code=503),
                     FakeResponse(json_data=_repo_payload())]
        monkeypatch.setattr(gs.httpx, "Client",
                            lambda **kw: FakeClient(responses, calls, **kw))

        gs.github_search("q")
        assert len(slept) == 2, f"expected a wait before attempts 2 and 3, got {slept}"
        assert all(s > 0 for s in slept), f"backoff must be non zero, got {slept}"
        assert slept[1] > slept[0], f"backoff should grow, got {slept}"


# ── failures must be legible ─────────────────────────────────────────────────

class TestErrorsSayWhatWentWrong:
    def test_a_non_json_body_does_not_surface_a_json_parser_message(self, http):
        """GitHub answers 403 and 451 with HTML. 'Expecting value: line 1
        column 1' tells the caller nothing about why the search failed."""
        http["responses"] = [FakeResponse(status_code=200, json_data=None,
                                          text="<html>rate limited</html>")]
        out = gs.github_search("q")
        assert out["results"] == []
        assert "Expecting value" not in out["error"]
        assert "non-JSON" in out["error"]
        assert "rate limited" in out["error"], "include the body so the cause is visible"

    def test_persistent_5xx_without_a_token_names_the_token(self, http):
        """Unauthenticated throttling arrives as 5xx, so the rate limit headers
        _rate_limit_error looks for are absent and its advice never fires."""
        http["responses"] = [FakeResponse(status_code=504) for _ in range(gs._MAX_ATTEMPTS)]
        out = gs.github_search("q")
        assert "GITHUB_TOKEN" in out["error"]

    def test_a_persistent_timeout_without_a_token_also_names_the_token(self, http, monkeypatch):
        """Distinct code path from the 5xx case above. Three 5xx responses return
        normally and the hint is added by the status branch; a timeout never
        yields a response at all, so _get_with_retry has to add it itself.
        A mutation check caught this path being unasserted."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        http["responses"] = [gs.httpx.TimeoutException("timed out")
                             for _ in range(gs._MAX_ATTEMPTS)]
        out = gs.github_search("q")
        assert out["results"] == []
        assert "GITHUB_TOKEN" in out["error"], out["error"]
        assert "attempts" in out["error"]

    def test_a_persistent_transport_error_reports_all_attempts_failed(self, http, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
        http["responses"] = [gs.httpx.ConnectError("no route")
                             for _ in range(gs._MAX_ATTEMPTS)]
        out = gs.github_search("q")
        assert out["results"] == []
        assert f"{gs._MAX_ATTEMPTS} attempts" in out["error"]
        assert "10 requests per minute" not in out["error"]

    def test_with_a_token_the_hint_is_not_bolted_on(self, http, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
        http["responses"] = [FakeResponse(status_code=504) for _ in range(gs._MAX_ATTEMPTS)]
        out = gs.github_search("q")
        assert "10 requests per minute" not in out["error"]

    def test_rate_limit_headers_still_win_when_present(self, http):
        http["responses"] = [FakeResponse(status_code=403,
                                          headers={"x-ratelimit-remaining": "0"})]
        out = gs.github_search("q")
        assert "rate limited" in out["error"].lower()

    def test_total_count_is_returned_so_zero_is_distinguishable(self, http):
        """0 results with total_count 4992 is a paging or permission problem.
        0 results with total_count 0 means nothing matched. Collapsing the two
        is what let a broken search read as a confident zero."""
        http["responses"] = [FakeResponse(json_data={"total_count": 4992, "items": []})]
        out = gs.github_search("q")
        assert out["results"] == []
        assert out["total_count"] == 4992


# ── the capability that was missing entirely ─────────────────────────────────

def _grep_payload(n=1, count=1234):
    return {
        "facets": {"count": count},
        "hits": {"hits": [
            {"repo": {"raw": f"owner/repo{i}"},
             "path": {"raw": f"hooks/stop{i}.py"},
             "content": {"snippet":
                         '<tr><td><div class="lineno">12</div></td><td><pre>'
                         'if payload.get(&quot;<mark>stop_hook_active</mark>&quot;):'
                         '</pre></td></tr>'}}
            for i in range(n)
        ]},
    }


class TestCodeSearchExists:
    def test_repo_search_and_code_search_hit_different_endpoints(self):
        """Repository search matches name, description, README and topics. It
        cannot find a file containing a line of code, so looking for an
        implementation there returns nothing however good the query."""
        assert gs.GITHUB_SEARCH_URL.endswith("/search/repositories")
        assert gs.GITHUB_CODE_SEARCH_URL.endswith("/search/code")

    def test_it_asks_for_match_fragments(self, http, monkeypatch):
        """A path with no matching line means opening every file to learn why it
        hit, which defeats the point of searching."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
        http["responses"] = [FakeResponse(json_data={"total_count": 0, "items": []})]
        gs.github_code_search("q")
        assert http["calls"][0]["url"] == gs.GITHUB_CODE_SEARCH_URL

    def test_it_returns_repo_path_and_fragments(self, http, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
        http["responses"] = [FakeResponse(json_data={
            "total_count": 1,
            "items": [{
                "path": "hooks/stop.py",
                "html_url": "https://github.com/o/r/blob/main/hooks/stop.py",
                "repository": {"full_name": "o/r", "stargazers_count": 42},
                "text_matches": [{"fragment": 'if payload.get("stop_hook_active"):'}],
            }],
        })]
        out = gs.github_code_search("q")
        assert out["error"] is None
        assert out["total_count"] == 1
        hit = out["results"][0]
        assert hit["repo"] == "o/r"
        assert hit["path"] == "hooks/stop.py"
        assert hit["stars"] == 42
        assert "stop_hook_active" in hit["matches"][0]

    def test_a_401_names_the_token_as_the_problem(self, http, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_expired")
        http["responses"] = [FakeResponse(status_code=401,
                                          json_data={"message": "Bad credentials"})]
        out = gs.github_code_search("q")
        assert "401" in out["error"]
        assert "expired" in out["error"] or "scope" in out["error"]

    def test_an_empty_query_is_rejected_before_a_request(self, http, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
        for bad in ("", "   ", None):
            out = gs.github_code_search(bad)
            assert out["error"] == "Invalid query", bad
        assert http["calls"] == []

    def test_a_rejected_token_flags_that_the_user_must_act(self, http, monkeypatch):
        """Distinct from a plain error. A caller should be able to branch on
        'you need to do something' without pattern matching on prose."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_expired")
        http["responses"] = [FakeResponse(status_code=401,
                                          json_data={"message": "Bad credentials"})]
        out = gs.github_code_search("q")
        assert out.get("needs_user_action") is True

    def test_a_successful_search_does_not_flag_user_action(self, http, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
        http["responses"] = [FakeResponse(json_data={"total_count": 0, "items": []})]
        out = gs.github_code_search("q")
        assert not out.get("needs_user_action")
        assert out["source"] == "github"


class TestFreeFallbackWhenNoToken:
    """GitHub's code search API returns 401 without a token. Refusing outright
    made the free path unavailable, so a swipe check with no token could not
    look for prior art at all. grep.app needs no key."""

    def test_no_token_falls_back_to_grep_app(self, http, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        http["responses"] = [FakeResponse(json_data=_grep_payload(2))]
        out = gs.github_code_search("stop_hook_active")
        assert out["error"] is None
        assert out["source"] == "grep.app"
        assert len(out["results"]) == 2
        assert out["total_count"] == 1234
        assert http["calls"][0]["url"] == gs.GREP_APP_URL

    def test_it_never_spends_a_request_that_must_401(self, http, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        http["responses"] = [FakeResponse(json_data=_grep_payload())]
        gs.github_code_search("q")
        urls = [c["url"] for c in http["calls"]]
        assert gs.GITHUB_CODE_SEARCH_URL not in urls

    def test_the_html_snippet_is_unwrapped_to_real_code(self, http, monkeypatch):
        """grep.app returns each hit as an HTML table row with <mark> tags. Handing
        that to a model as a 'code reference' is worse than handing it nothing."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        http["responses"] = [FakeResponse(json_data=_grep_payload())]
        out = gs.github_code_search("q")
        match = out["results"][0]["matches"][0]
        assert "stop_hook_active" in match
        assert "<mark>" not in match and "<pre>" not in match
        assert "&quot;" not in match, "HTML entities must be decoded"
        assert '"stop_hook_active"' in match

    def test_language_filter_is_passed_through(self, http, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        http["responses"] = [FakeResponse(json_data=_grep_payload())]
        gs.github_code_search("q", language="Python")
        assert http["calls"][0]["params"]["f.lang"] == "Python"

    def test_grep_app_throttling_says_so_and_names_the_token(self, http, monkeypatch):
        """Measured: grep.app answers a throttle with HTTP 429 and an HTML body.
        Both paths being down is the only case that is genuinely the user's to fix."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        http["responses"] = [FakeResponse(status_code=429, text="<html>429</html>")]
        out = gs.github_code_search("q")
        assert out["results"] == []
        assert out["needs_user_action"] is True
        assert "429" in out["error"]
        assert "GITHUB_TOKEN" in out["error"]

    def test_grep_app_returning_zero_hits_is_not_a_user_action(self, http, monkeypatch):
        """A working search that found nothing is an answer, not a problem to
        escalate. Conflating the two is what makes escalation get ignored."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        http["responses"] = [FakeResponse(json_data={"facets": {"count": 0},
                                                     "hits": {"hits": []}})]
        out = gs.github_code_search("nothing matches this")
        assert out["results"] == []
        assert out["error"] is None
        assert not out.get("needs_user_action")

    def test_a_malformed_grep_app_payload_does_not_raise(self, http, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        http["responses"] = [FakeResponse(json_data={"hits": None, "facets": None})]
        out = gs.github_code_search("q")
        assert out["results"] == []
        assert out["total_count"] == 0

    def test_strip_html_handles_empty_and_none(self):
        assert gs._strip_html("") == ""
        assert gs._strip_html(None) == ""
