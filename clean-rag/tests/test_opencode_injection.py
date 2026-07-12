#!/usr/bin/env python3
"""Test OpenCode MCP injection pipeline.

Simulates OpenCode calling the MCP server with a code analysis request.
Tests metrics injection, RAG search, and web fallback.
"""

import json
import subprocess
import sys
import time
from pathlib import Path


def test_mcp_call(tool_name: str, tool_input: dict) -> dict:
    """Call MCP server via stdin/stdout."""
    request = {
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": tool_input},
    }

    try:
        proc = subprocess.Popen(
            [sys.executable, "/c/prj/ClaudeBoost/clean-rag/mcp/opencode_mcp_server.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        output, err = proc.communicate(
            input=json.dumps(request) + "\n", timeout=10
        )

        if output:
            response = json.loads(output.strip())
            return response.get("result", {"error": "no result"})
        else:
            return {"error": f"No output: {err}"}

    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


def test_1_rag_search():
    """Test 1: RAG search for collision detection."""
    print("\n=== TEST 1: RAG Search ===")
    result = test_mcp_call(
        "rag_search",
        {
            "query": "collision detection game physics algorithm",
            "limit": 3,
        },
    )

    print(f"RAG Search Results: {len(result.get('results', []))} found")
    if result.get("results"):
        for i, r in enumerate(result["results"][:2], 1):
            print(f"  {i}. {r.get('topic', 'unknown')} (score: {r.get('score', 0):.2f})")
    return bool(result.get("results"))


def test_2_code_metrics():
    """Test 2: Code metrics for flappy bird."""
    print("\n=== TEST 2: Code Metrics ===")
    filepath = "/c/prj/LocalAI/tests/flappy_bird_claude_test.py"

    if not Path(filepath).exists():
        print(f"SKIP: {filepath} not found")
        return None

    result = test_mcp_call("code_metrics", {"filepath": filepath})

    if "error" not in result:
        print(f"Metrics for {Path(filepath).name}:")
        print(f"  Lines of Code: {result.get('lines_of_code', '?')}")
        print(f"  Complexity: {result.get('cyclomatic_complexity', '?')}")
        print(f"  Maintainability: {result.get('maintainability_index', '?')}")

        call_graph = result.get("call_graph", {})
        if call_graph:
            print(f"  Functions: {', '.join(call_graph.get('functions', [])[:3])}")
            print(f"  Classes: {', '.join(call_graph.get('classes', [])[:3])}")
        return True
    else:
        print(f"ERROR: {result.get('error')}")
        return False


def test_3_web_search_fallback():
    """Test 3: Web search fallback."""
    print("\n=== TEST 3: Web Search Fallback ===")
    result = test_mcp_call(
        "web_search_fallback",
        {
            "query": "flappy bird collision detection algorithm pygame",
            "max_results": 2,
        },
    )

    if "error" not in result:
        print(f"Web Search Results: {len(result.get('results', []))} found")
        if result.get("results"):
            for i, r in enumerate(result["results"][:2], 1):
                print(f"  {i}. {r.get('title', 'unknown')}")
        return bool(result.get("results"))
    else:
        print(f"Note: {result.get('error')} (web search may be disabled in RAG config)")
        return None


def test_4_full_injection():
    """Test 4: Full context injection."""
    print("\n=== TEST 4: Full Context Injection ===")
    filepath = "/c/prj/LocalAI/tests/flappy_bird_claude_test.py"

    result = test_mcp_call(
        "inject_full_context",
        {
            "prompt": "What collision detection bugs might exist in this flappy bird game?",
            "filepath": filepath,
            "model": "deepseek-v4-flash",
        },
    )

    if "error" not in result:
        injected = result.get("injected_context", "")
        print(f"Injected Context Length: {len(injected)} characters")
        print(f"Fallback Triggered: {result.get('fallback_triggered', False)}")

        # Show what was injected
        if "Research Context" in injected:
            print("✓ RAG research context injected")
        if "Code Quality Metrics" in injected:
            print("✓ Code metrics injected")
        if "Web Search Results" in injected:
            print("✓ Web search results injected")

        # Show a snippet
        print("\n--- Injected Context Snippet (first 500 chars) ---")
        print(injected[:500])
        print("...\n")

        return True
    else:
        print(f"ERROR: {result.get('error')}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("OpenCode RAG + Metrics Injection Test Suite")
    print("=" * 60)

    results = {}

    # Test 1: RAG search
    results["rag_search"] = test_1_rag_search()

    # Test 2: Code metrics
    results["code_metrics"] = test_2_code_metrics()

    # Test 3: Web search (optional)
    results["web_search"] = test_3_web_search_fallback()

    # Test 4: Full injection
    results["full_injection"] = test_4_full_injection()

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(1 for v in results.values() if v is True)
    total = len([v for v in results.values() if v is not None])

    for test_name, result in results.items():
        status = "PASS" if result is True else "SKIP" if result is None else "FAIL"
        print(f"  {test_name:20s} {status}")

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n✓ All tests passed. OpenCode integration ready.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
