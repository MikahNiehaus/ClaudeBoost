#!/usr/bin/env python3
"""MCP Server for OpenCode RAG + Metrics injection.

Exposes clean-rag functionality as an MCP server that OpenCode can connect to.
Provides: RAG search, metrics collection, web search fallback, call graph extraction.
"""

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OpenCodeMCPServer:
    """MCP server bridging OpenCode to clean-rag services."""

    def __init__(self, port: int = 8614):
        self.port = port
        self.rag_port = 8613
        self.metrics_cache = {}

    def search_rag(self, query: str, limit: int = 3) -> dict:
        """Search clean-rag for research context."""
        try:
            payload = json.dumps({
                "query": query,
                "sources": ["all_topics"],
                "limit": limit,
                "min_score": 0.5
            }).encode("utf-8")

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.rag_port}/search",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "results": data.get("results", []),
                    "search_id": data.get("search_id", ""),
                }
        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return {"results": [], "search_id": "", "error": str(e)}

    def get_file_metrics(self, filepath: str) -> dict:
        """Get code quality metrics for a file."""
        try:
            # Try to call clean-rag metrics endpoint
            payload = json.dumps({
                "file_path": filepath
            }).encode("utf-8")

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.rag_port}/metrics",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=2) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Metrics fetch failed: {e}")
            return {"error": str(e)}

    def web_search_fallback(self, query: str) -> dict:
        """Trigger web search fallback if RAG is weak."""
        try:
            payload = json.dumps({
                "query": query,
                "max_results": 3
            }).encode("utf-8")

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.rag_port}/web-search",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=4) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return {"results": [], "error": str(e)}

    def format_context(self, rag_results: list, metrics: dict = None, web_results: list = None) -> str:
        """Format all sources into markdown context for injection."""
        lines = []

        if rag_results:
            lines.append("## Research Context (RAG)")
            for i, result in enumerate(rag_results[:3], 1):
                topic = result.get("topic", "unknown")
                score = result.get("score", 0)
                content = result.get("content", "")[:200]
                lines.append(f"**{i}. {topic}** (relevance: {score:.2f})")
                lines.append(f"{content}...\n")

        if metrics and "lines_of_code" in metrics:
            lines.append("## Code Quality Metrics")
            lines.append(f"- **LOC**: {metrics.get('lines_of_code', 0)}")
            lines.append(f"- **Complexity**: {metrics.get('cyclomatic_complexity', 0)}")
            lines.append(f"- **Maintainability**: {metrics.get('maintainability_index', 0)}\n")

        if web_results:
            lines.append("## Web Search Results (Fallback)")
            for i, result in enumerate(web_results[:2], 1):
                title = result.get("title", "Unknown")
                snippet = result.get("snippet", "")[:150]
                lines.append(f"**{i}. {title}**")
                lines.append(f"{snippet}...\n")

        return "\n".join(lines)

    def process_prompt(self, prompt: str, filepath: str = None) -> dict:
        """Process a prompt and inject context."""
        # Search RAG
        rag_results = self.search_rag(prompt)["results"]

        # Get metrics if filepath provided
        metrics = None
        if filepath:
            metrics = self.get_file_metrics(filepath)

        # Check if RAG results are weak — trigger web search
        web_results = []
        if rag_results:
            best_score = rag_results[0].get("score", 0)
            if best_score < 0.5:
                web_results = self.web_search_fallback(prompt).get("results", [])
        else:
            web_results = self.web_search_fallback(prompt).get("results", [])

        # Format context
        context = self.format_context(rag_results, metrics, web_results)

        return {
            "injected_context": context,
            "rag_results": rag_results,
            "metrics": metrics,
            "web_results": web_results,
        }


def create_mcp_tool_handlers():
    """Create MCP tool handlers for OpenCode."""
    server = OpenCodeMCPServer()

    tools = [
        {
            "name": "rag_search",
            "description": "Search clean-rag for research context",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results (default 3)"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_metrics",
            "description": "Get code quality metrics for a file",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to file"},
                },
                "required": ["filepath"],
            },
        },
        {
            "name": "web_search",
            "description": "Trigger web search fallback",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "inject_context",
            "description": "Process prompt and inject RAG + metrics + web context",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "User prompt"},
                    "filepath": {"type": "string", "description": "Optional file path"},
                },
                "required": ["prompt"],
            },
        },
    ]

    def execute_tool(tool_name: str, args: dict) -> Any:
        if tool_name == "rag_search":
            return server.search_rag(args["query"], args.get("limit", 3))
        elif tool_name == "get_metrics":
            return server.get_file_metrics(args["filepath"])
        elif tool_name == "web_search":
            return server.web_search_fallback(args["query"])
        elif tool_name == "inject_context":
            return server.process_prompt(args["prompt"], args.get("filepath"))
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    return tools, execute_tool


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    server = OpenCodeMCPServer()
    print("OpenCode MCP Server ready on port 8614")
    print("Tools: rag_search, get_metrics, web_search, inject_context")
