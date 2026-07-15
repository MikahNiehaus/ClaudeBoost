"""
Adversarial tests for xray.md port and API shape correctness.
Tests the four changed locations against the live clean-rag servers.

Port assignments:
  8612 = ClaudeBoost KB server (rag_server), scope-based API
  8613 = clean-rag project index server, sources[] API
"""
import json
import urllib.request
import urllib.error

BASE_8612 = "http://127.0.0.1:8612"
BASE_8613 = "http://127.0.0.1:8613"
PROJECT_PATH = "C:/Development/ClaudeBoost"


def _post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


# -- Test 1: Line 49 -- 8613/status must report indexed projects ---------------

def test_line49_status_on_8613():
    """GET http://127.0.0.1:8613/status must exist and return project list."""
    r = _get(f"{BASE_8613}/status")
    assert "projects" in r, f"8613/status missing 'projects' key: {list(r.keys())}"
    print("PASS test_line49_status_on_8613")


def test_line49_status_schema_difference():
    """
    Verify 8612/status uses 'indexed_projects' while 8613 uses 'projects'.
    If 8613 was accidentally left on 8612, the xray PROJECT_PATH check would
    look in the wrong key and always fail the index check.
    """
    r8612 = _get(f"{BASE_8612}/status")
    r8613 = _get(f"{BASE_8613}/status")
    assert "indexed_projects" in r8612, f"8612 status shape unexpected: {list(r8612.keys())}"
    assert "projects" in r8613, f"8613 status shape unexpected: {list(r8613.keys())}"
    assert "indexed_projects" not in r8613, "8613 unexpectedly has 'indexed_projects' key"
    print("PASS test_line49_status_schema_difference")


# -- Test 2: Lines 216-217 -- 8613 Phase 1 pattern search ---------------------

def test_line216_phase1_vector_search_8613():
    """Phase 1 vector: POST 8613/search with sources[] shape must work."""
    r = _post(f"{BASE_8613}/search", {
        "query": "research gate hook",
        "sources": [f"project:{PROJECT_PATH}"],
        "mode": "vector",
        "limit": 3,
    })
    assert "results" in r, f"8613 vector search missing 'results': {list(r.keys())}"
    assert "error" not in r, f"8613 vector search returned error: {r['error']}"
    print(f"PASS test_line216_phase1_vector_search_8613 ({len(r['results'])} results)")


def test_line217_phase1_graph_search_8613():
    """Phase 1 graph: POST 8613/search with mode=graph must work."""
    r = _post(f"{BASE_8613}/search", {
        "query": "research gate hook",
        "sources": [f"project:{PROJECT_PATH}"],
        "mode": "graph",
        "limit": 3,
    })
    assert "results" in r, f"8613 graph search missing 'results': {list(r.keys())}"
    assert "error" not in r, f"8613 graph search returned error: {r['error']}"
    print(f"PASS test_line217_phase1_graph_search_8613 ({len(r['results'])} results)")


def test_OLD_scope_shape_on_8613_returns_no_local_results():
    """
    The old shape (scope='codebase', no sources[]) must NOT return local project results
    on 8613. If it did, the port fix would be a no-op.
    """
    r = _post(f"{BASE_8613}/search", {
        "query": "research gate hook",
        "scope": "codebase",
        "project_path": PROJECT_PATH,
        "mode": "vector",
        "limit": 3,
    })
    results = r.get("results", [])
    fallback = r.get("fallback_triggered", False)
    # A correct project search returns local .py/.md files; scope=codebase on 8613 should not
    local_hits = [
        res for res in results
        if "Development/ClaudeBoost" in str(res.get("source", "")) or
           "Development\\ClaudeBoost" in str(res.get("source", ""))
    ]
    assert len(local_hits) == 0 or fallback, (
        f"Old scope=codebase shape on 8613 returned local ClaudeBoost results "
        f"-- API boundary is broken: {[r.get('source') for r in local_hits[:2]]}"
    )
    print(f"PASS test_OLD_scope_shape_on_8613_returns_no_local_results "
          f"(fallback={fallback}, local_hits={len(local_hits)})")


# -- Test 3: Lines 352-358 -- Agent priming block Steps 3 & 4 ----------------

def test_line353_step3_vector_8613():
    """Step 3 in priming block: vector search on 8613 with correct JSON body."""
    r = _post(f"{BASE_8613}/search", {
        "query": "reviewer agent pattern",
        "sources": [f"project:{PROJECT_PATH}"],
        "mode": "vector",
        "limit": 5,
    })
    assert "results" in r and "error" not in r
    print(f"PASS test_line353_step3_vector_8613 ({len(r['results'])} results)")


def test_line356_step4_graph_8613():
    """Step 4 in priming block: graph search on 8613 with correct JSON body."""
    r = _post(f"{BASE_8613}/search", {
        "query": "reviewer agent pattern",
        "sources": [f"project:{PROJECT_PATH}"],
        "mode": "graph",
        "limit": 5,
    })
    assert "results" in r and "error" not in r
    print(f"PASS test_line356_step4_graph_8613 ({len(r['results'])} results)")


# -- Test 4: Line 543 -- Evaluator search ------------------------------------

def test_line543_evaluator_graph_8613():
    """Evaluator BLOCKER verification: graph search on 8613."""
    r = _post(f"{BASE_8613}/search", {
        "query": "research gate hook",
        "sources": [f"project:{PROJECT_PATH}"],
        "mode": "graph",
        "limit": 3,
    })
    assert "results" in r and "error" not in r
    print(f"PASS test_line543_evaluator_graph_8613 ({len(r['results'])} results)")


# -- Test 5: Lines kept on 8612 must still work --------------------------------

def test_line43_context_still_on_8612():
    """Line 43: POST 8612/context must still work (unchanged)."""
    r = _post(f"{BASE_8612}/context", {
        "agent": "reviewer-agent",
        "task_description": "code xray test",
        "project_path": PROJECT_PATH,
        "workspace_path": "",
        "max_tokens": 100,
    })
    assert "error" not in r, f"8612/context error: {r}"
    print("PASS test_line43_context_still_on_8612")


def test_line350_knowledge_search_still_on_8612():
    """Step 2: scope=knowledge search stays on 8612."""
    r = _post(f"{BASE_8612}/search", {
        "query": "reviewer agent",
        "scope": "knowledge",
        "limit": 3,
    })
    assert "results" in r and "error" not in r
    print(f"PASS test_line350_knowledge_search_still_on_8612 ({r.get('total_found')} found)")


# -- Test 6: Step 5 (line 359) -- workspace KB on 8612 with scope=codebase ---

def test_line359_step5_workspace_kb_on_8612():
    """
    Step 5: scope='codebase' + project_path=<workspace>/knowledge on 8612.
    This is the one remaining 8612/search scope=codebase call. Verify it works.
    """
    workspace_kb = (
        "C:/Development/ClaudeBoost/workspace"
        "/better-research-task-project-2026-06-24/knowledge"
    )
    r = _post(f"{BASE_8612}/search", {
        "query": "research agent",
        "scope": "codebase",
        "project_path": workspace_kb,
        "mode": "vector",
        "limit": 3,
    })
    assert "results" in r and "error" not in r, f"Step 5 workspace KB search failed: {r}"
    print(f"PASS test_line359_step5_workspace_kb_on_8612 ({r.get('total_found')} found)")


# -- Test 7: Regression -- knowledge search must not leak to 8613 -------------

def test_knowledge_scope_NOT_on_8613():
    """
    scope=knowledge on 8613 must NOT return KB content (8613 has no scope concept).
    Guards against accidentally moving knowledge searches to the wrong port.
    """
    r = _post(f"{BASE_8613}/search", {
        "query": "reviewer agent",
        "scope": "knowledge",
        "limit": 3,
    })
    # Without 'sources', 8613 falls back to web search or returns empty local results
    fallback = r.get("fallback_triggered", False)
    results = r.get("results", [])
    # Local knowledge hits would have source paths inside ClaudeBoost knowledge dir
    kb_hits = [
        res for res in results
        if "knowledge" in str(res.get("source", "")).lower() and
           "Development" in str(res.get("source", ""))
    ]
    assert len(kb_hits) == 0 or fallback, (
        f"8613 incorrectly returned KB results for scope=knowledge: "
        f"{[r.get('source') for r in kb_hits[:2]]}"
    )
    print(f"PASS test_knowledge_scope_NOT_on_8613 (fallback={fallback})")


if __name__ == "__main__":
    tests = [
        test_line49_status_on_8613,
        test_line49_status_schema_difference,
        test_line216_phase1_vector_search_8613,
        test_line217_phase1_graph_search_8613,
        test_OLD_scope_shape_on_8613_returns_no_local_results,
        test_line353_step3_vector_8613,
        test_line356_step4_graph_8613,
        test_line543_evaluator_graph_8613,
        test_line43_context_still_on_8612,
        test_line350_knowledge_search_still_on_8612,
        test_line359_step5_workspace_kb_on_8612,
        test_knowledge_scope_NOT_on_8613,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
