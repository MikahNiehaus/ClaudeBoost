#!/usr/bin/env python3
"""
MCP Server for OpenCode: RAG + Metrics + Web Search Injection

This server bridges OpenCode (any model: DeepSeek, Claude, LocalAI) to clean-rag services.
Provides semantic search, code metrics, web search fallback, and context injection.

Install: register in OpenCode settings as an MCP server pointing to this script.
"""

import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

_CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
_LOG_DIR = _CLEAN_RAG_HOME / "state"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(str(_LOG_DIR / "opencode_mcp_server.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class OpenCodeRAGServer:
    """MCP-compliant RAG server for OpenCode."""

    def __init__(self, rag_port: int = 8613):
        self.rag_port = rag_port
        self.tools = self._build_tools()

    def _build_tools(self) -> list:
        """Define MCP tools."""
        return [
            {
                "name": "rag_search",
                "description": "Search an indexed project's vector database and import graph together (semantic similarity plus structural neighbours, mode both). Requires project_path, an absolute path to an indexed project. Returns nothing for a project that is not indexed, which is the signal to fall back to web search, not an error.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'error handling patterns', 'SQL injection prevention')",
                        },
                        "project_path": {
                            "type": "string",
                            "description": "Absolute path to the indexed project to search. Required: without it there is nothing to search.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default 3)",
                            "default": 3,
                        },
                        "min_score": {
                            "type": "number",
                            "description": "Minimum relevance score 0.0-1.0 (default 0.5)",
                            "default": 0.5,
                        },
                    },
                    "required": ["query", "project_path"],
                },
            },
            {
                "name": "code_metrics",
                "description": "Analyze code quality: LOC, complexity, maintainability index, call graph",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Path to Python/JS/TS/Go file to analyze",
                        },
                    },
                    "required": ["filepath"],
                },
            },
            {
                "name": "web_search_fallback",
                "description": "Search the web when RAG returns weak results (score < 0.5)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Max results to return (default 3)",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "run_tests",
                "description": "Run the project's tests and return the REAL failure output (assertion diff, stack trace). Call this after writing code, then fix from the actual output, not by rereading your own diff.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "Absolute path to the project to test (its test command is auto detected: npm test, vitest, jest, or pytest)",
                        },
                    },
                    "required": ["project_path"],
                },
            },
            {
                "name": "inject_full_context",
                "description": "Process a prompt and inject RAG + metrics + web context in one call",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "User prompt or question",
                        },
                        "filepath": {
                            "type": "string",
                            "description": "Optional: filepath for code metrics injection",
                        },
                        "model": {
                            "type": "string",
                            "description": "Model name (DeepSeek, Claude, etc.) - for logging",
                        },
                    },
                    "required": ["prompt"],
                },
            },
        ]

    def _ensure_server_up(self, timeout_s: float = 30.0) -> bool:
        """Reachable check, and start the clean-rag server if it isn't.

        OpenCode users don't run server_ctl by hand, so a search that hits a
        dead server is a dead end. Start it for them, once, lazily on the first
        search that needs it. Bounded: if it won't come up we log and let the
        caller fall through to its "unavailable" path rather than hang.
        """
        import subprocess
        import time

        status_url = f"http://127.0.0.1:{self.rag_port}/status"

        def _reachable() -> bool:
            try:
                with urllib.request.urlopen(status_url, timeout=2) as r:
                    return r.status == 200
            except Exception:
                return False

        if _reachable():
            return True

        logger.info("clean-rag server not reachable on port %s, starting it", self.rag_port)
        try:
            server_ctl = _CLEAN_RAG_HOME / "cli" / "server_ctl.py"
            subprocess.Popen(
                [sys.executable, str(server_ctl), "start"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error("could not launch clean-rag server: %s", e)
            return False

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(2)
            if _reachable():
                logger.info("clean-rag server is up")
                return True
        logger.error("clean-rag server did not come up within %.0fs", timeout_s)
        return False

    def rag_search(
        self, query: str, limit: int = 3, min_score: float = 0.5, project_path: str = ""
    ) -> dict:
        """Search the indexed project.

        Used to search "all_topics", the topic knowledge base, which no longer
        exists. That source now falls through to the unknown-specifier branch in
        search() and returns nothing, so this tool was quietly dead.

        Searches the project index instead, with mode "both" so a caller gets
        the import graph neighbours alongside the vector matches. Without a
        project_path there's nothing to search, so say so rather than returning
        an empty list that looks like "no matches".
        """
        if not project_path:
            return {
                "results": [],
                "search_id": "",
                "total": 0,
                "error": "project_path is required. The topic knowledge base is gone; "
                         "there is nothing to search without an indexed project.",
            }

        # Start the server if it's down. If it still can't come up, the request
        # below fails and we return the existing unavailable response.
        self._ensure_server_up()

        try:
            payload = json.dumps(
                {
                    "query": query,
                    "sources": [f"project:{project_path}"],
                    "mode": "both",
                    "limit": limit,
                    "min_score": min_score,
                }
            ).encode("utf-8")

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.rag_port}/search",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                logger.info(
                    f"RAG search '{query}' returned {len(data.get('results', []))} results"
                )
                return {
                    "results": data.get("results", []),
                    "search_id": data.get("search_id", ""),
                    "total": len(data.get("results", [])),
                }
        except urllib.error.URLError as e:
            logger.error(f"RAG connection failed: {e}")
            return {
                "results": [],
                "search_id": "",
                "error": "RAG server unavailable",
            }
        except Exception as e:
            logger.error(f"RAG search error: {e}")
            return {"results": [], "search_id": "", "error": str(e)}

    def run_tests(self, project_path: str) -> dict:
        """Run the project's tests via the clean-rag /run-tests endpoint.

        Hands the model the real failure text, which is the execution feedback a
        weak model actually needs to fix its own code. Starts the server if it is
        down, same as rag_search. Without a project_path there is nothing to run.
        """
        if not project_path:
            return {"has_tests": False, "passed": None, "error": "project_path is required"}

        self._ensure_server_up()

        try:
            payload = json.dumps({"project_path": project_path}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.rag_port}/run-tests",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # The run is capped at 120s server side, so give it a little more.
            with urllib.request.urlopen(req, timeout=140) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                logger.info(
                    "run_tests %s: has_tests=%s passed=%s",
                    project_path, data.get("has_tests"), data.get("passed"),
                )
                return data
        except urllib.error.URLError as e:
            logger.error(f"run_tests connection failed: {e}")
            return {"has_tests": False, "passed": None, "error": "RAG server unavailable"}
        except Exception as e:
            logger.error(f"run_tests error: {e}")
            return {"has_tests": False, "passed": None, "error": str(e)}

    def code_metrics(self, filepath: str) -> dict:
        """Get code metrics for a file."""
        try:
            payload = json.dumps({"file_path": filepath}).encode("utf-8")

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.rag_port}/metrics",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=2) as resp:
                metrics = json.loads(resp.read().decode("utf-8"))
                logger.info(f"Metrics for {filepath}: LOC={metrics.get('lines_of_code', '?')}")
                return metrics
        except Exception as e:
            logger.error(f"Metrics fetch failed: {e}")
            return {"error": str(e)}

    def web_search_fallback(self, query: str, max_results: int = 3) -> dict:
        """Trigger web search fallback.

        There is no HTTP /web-search route on the server (confirmed by
        scanning every registered handler in app.py). The server's web
        fallback lives inside /search itself, keyed off its own score
        threshold, and only fires there. This calls server/web_search.py's
        web_search() directly, in-process, as the explicit fallback path
        for callers (like this MCP tool) that want to force a web search
        regardless of what /search's internal threshold decided.
        """
        try:
            server_dir = _CLEAN_RAG_HOME / "server"
            if str(server_dir) not in sys.path:
                sys.path.insert(0, str(server_dir))
            from web_search import web_search as _do_web_search

            result = _do_web_search(query, max_results=max_results, timeout=5.0)
            if result.get("error"):
                logger.error(f"Web search returned error: {result['error']}")
            logger.info(
                f"Web search '{query}' returned {len(result.get('results', []))} results"
            )
            return result
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return {"results": [], "error": str(e)}

    def inject_full_context(
        self, prompt: str, filepath: str = None, model: str = "unknown"
    ) -> dict:
        """Complete context injection: RAG + metrics + web fallback."""
        logger.info(f"Injecting context for {model}: {prompt[:60]}...")

        # Step 1: Search RAG
        rag_result = self.rag_search(prompt)
        rag_results = rag_result.get("results", [])

        # Step 2: Get metrics if filepath provided
        metrics = None
        if filepath:
            metrics = self.code_metrics(filepath)

        # Step 3: Check if fallback needed (weak RAG score or no results)
        web_results = []
        fallback_triggered = False
        if not rag_results:
            logger.info("RAG returned no results, triggering web search fallback")
            fallback_triggered = True
            web_result = self.web_search_fallback(prompt)
            web_results = web_result.get("results", [])
        elif rag_results:
            best_score = rag_results[0].get("score", 0)
            if best_score < 0.4:
                logger.info(
                    f"RAG score {best_score} < 0.4, triggering web search fallback"
                )
                fallback_triggered = True
                web_result = self.web_search_fallback(prompt)
                web_results = web_result.get("results", [])

        # Step 4: Format injected context
        context_lines = []

        if rag_results:
            context_lines.append("## Research Context (RAG Knowledge Base)\n")
            for i, result in enumerate(rag_results[:3], 1):
                topic = result.get("topic", "unknown")
                score = result.get("score", 0)
                content = result.get("content", "")[:200]
                context_lines.append(
                    f"**{i}. {topic}** (relevance: {score:.2f})"
                )
                context_lines.append(f"{content}...\n")

        if metrics and "lines_of_code" in metrics:
            context_lines.append("## Code Quality Metrics\n")
            context_lines.append(
                f"- **Lines of Code**: {metrics.get('lines_of_code', 0)}"
            )
            context_lines.append(
                f"- **Cyclomatic Complexity**: {metrics.get('cyclomatic_complexity', 0)}"
            )
            context_lines.append(
                f"- **Maintainability Index**: {metrics.get('maintainability_index', 0)}"
            )

            if "call_graph" in metrics:
                call_graph = metrics["call_graph"]
                if call_graph:
                    context_lines.append("\n**Dependencies & Structure**:")
                    if call_graph.get("functions"):
                        context_lines.append(
                            f"- Functions: {', '.join(call_graph['functions'][:5])}"
                        )
                    if call_graph.get("classes"):
                        context_lines.append(
                            f"- Classes: {', '.join(call_graph['classes'][:5])}"
                        )
            context_lines.append("")

        if web_results:
            context_lines.append("## Web Search Results (Fallback)\n")
            for i, result in enumerate(web_results[:3], 1):
                title = result.get("title", "Unknown")
                snippet = result.get("snippet", "")[:150]
                url = result.get("url", "")
                context_lines.append(f"**{i}. {title}**")
                if url:
                    context_lines.append(f"_Source: {url}_")
                context_lines.append(f"{snippet}...\n")

        injected_context = "\n".join(context_lines)

        return {
            "injected_context": injected_context,
            "rag_results": rag_results,
            "metrics": metrics,
            "web_results": web_results,
            "fallback_triggered": fallback_triggered,
        }

    def handle_tool_call(self, tool_name: str, tool_input: dict) -> Any:
        """Execute a tool call."""
        logger.info(f"Tool call: {tool_name} with {list(tool_input.keys())}")

        if tool_name == "rag_search":
            return self.rag_search(
                tool_input.get("query", ""),
                tool_input.get("limit", 3),
                tool_input.get("min_score", 0.5),
                tool_input.get("project_path", ""),
            )

        elif tool_name == "run_tests":
            return self.run_tests(tool_input.get("project_path", ""))

        elif tool_name == "code_metrics":
            return self.code_metrics(tool_input.get("filepath", ""))

        elif tool_name == "web_search_fallback":
            return self.web_search_fallback(
                tool_input.get("query", ""), tool_input.get("max_results", 3)
            )

        elif tool_name == "inject_full_context":
            return self.inject_full_context(
                tool_input.get("prompt", ""),
                tool_input.get("filepath"),
                tool_input.get("model", "unknown"),
            )

        else:
            return {"error": f"Unknown tool: {tool_name}"}


# The MCP protocol version we speak. OpenCode's client sends its own in the
# initialize request; we answer with the one we implement.
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "clean-rag-opencode", "version": "1.0.0"}


def _result(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _send(response: dict) -> None:
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def main():
    """MCP server main loop, speaking JSON-RPC 2.0 over stdio.

    The old loop read bare {id, method, params} frames and answered without a
    "jsonrpc" field or an initialize handshake, so a real MCP client (OpenCode's
    included) rejected it before ever listing a tool. This handles the full
    handshake: initialize, the notifications/initialized ack, then tools/list and
    tools/call. Notifications carry no id and get no reply, per JSON-RPC. Anything
    else comes back as a -32601 method-not-found error.
    """
    server = OpenCodeRAGServer()
    logger.info("OpenCode RAG MCP Server starting...")

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            # No id to echo, so per spec send a parse error with a null id.
            _send(_error(None, -32700, f"Parse error: {e}"))
            continue

        request_id = request.get("id")
        method = request.get("method")
        # A request with no "id" is a notification and must never get a response.
        is_notification = "id" not in request

        try:
            if method == "initialize":
                response = _result(request_id, {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": SERVER_INFO,
                    "capabilities": {"tools": {}},
                })

            elif method == "notifications/initialized":
                # Client's ack that the handshake finished. It's a notification, so
                # we stay silent and wait for the first real request.
                continue

            elif method == "tools/list":
                response = _result(request_id, {"tools": server.tools})

            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name")
                tool_input = params.get("arguments", {})
                result = server.handle_tool_call(tool_name, tool_input)
                is_error = isinstance(result, dict) and bool(result.get("error"))
                response = _result(request_id, {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                    "isError": is_error,
                })

            elif is_notification:
                # Some other notification we don't act on. Silence is the correct
                # answer to a notification.
                continue

            else:
                response = _error(request_id, -32601, f"Unknown method: {method}")

            if is_notification:
                # A handled method that arrived without an id: still no reply.
                continue

            _send(response)

        except Exception as e:
            logger.error(f"Unhandled error handling {method}: {e}")
            if not is_notification:
                _send(_error(request_id, -32603, f"Internal error: {e}"))


if __name__ == "__main__":
    main()
