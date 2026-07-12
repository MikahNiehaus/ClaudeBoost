"""Metrics injection hook: prepend code quality metrics to prompts.

Runs on UserPromptSubmit, injects cached metrics for files in context.
Also detects project context: if in a git repo, injects indexed project info
or queues background indexing if not yet indexed.
"""

import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from metrics import get_metrics, format_metrics_for_context


def _find_git_root(start_path: str = ".") -> str | None:
    """Walk up directory tree to find .git root, or None if not in a repo."""
    current = Path(start_path).resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent
    return None


def _format_call_graph(metrics: dict) -> str:
    """Format call graph as context section."""
    call_graph = metrics.get("call_graph", {})
    if not call_graph or (not call_graph.get("functions") and not call_graph.get("classes")):
        return ""

    lines = ["## Code Structure\n"]

    functions = call_graph.get("functions", [])
    if functions:
        lines.append(f"**Functions:** {', '.join(functions[:5])}")

    classes = call_graph.get("classes", [])
    if classes:
        lines.append(f"**Classes:** {', '.join(classes[:5])}")

    imports = call_graph.get("imports", [])
    if imports:
        lines.append(f"**Imports:** {', '.join(imports[:5])}\n")

    return "\n".join(lines)


def _get_project_context() -> str:
    """Build project context section if in a git repo."""
    git_root = _find_git_root()
    if not git_root:
        return ""

    try:
        # Check if project is indexed by querying RAG server status
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8612/status"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            import json
            status = json.loads(result.stdout)
            indexed_projects = status.get("indexed_projects", [])
            is_indexed = git_root in indexed_projects or any(git_root in p for p in indexed_projects)

            if is_indexed:
                return f"\n## Project Context\nFile analyzed in context of indexed project at {git_root}. RAG search available for codebase references."
            else:
                # Queue background indexing
                try:
                    subprocess.Popen(
                        [
                            sys.executable, "-c",
                            f"import subprocess; subprocess.run(['curl', '-X', 'POST', 'http://127.0.0.1:8612/index-project', '-H', 'Content-Type: application/json', '-d', 'json.dumps({{\\\"project_path\\\": \\\"{git_root}\\\"}}))'], timeout=60)"
                        ],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass
                return f"\n## Project Context\nFile in project at {git_root} (indexing queued in background)."
    except Exception:
        pass

    return ""


def hook_user_prompt_submit(context: dict, message: str) -> dict:
    """Inject code quality metrics into prompt context."""
    metrics_enabled = os.environ.get("CLEAN_RAG_METRICS_INJECT", "true").lower() in ("true", "1", "yes")

    if not metrics_enabled:
        return context

    # Extract file paths from context (if available)
    files_in_context = context.get("files", [])
    if not files_in_context:
        return context

    # Collect metrics for each file
    all_metrics = []
    for filepath in files_in_context[:10]:  # Limit to first 10 files
        try:
            metrics = get_metrics(filepath, force_recompute=False)
            all_metrics.append(metrics)
        except Exception:
            pass

    # Format and inject metrics
    sections = []
    if all_metrics:
        metrics_section = format_metrics_for_context(all_metrics)
        if metrics_section:
            sections.append(metrics_section)

        # Add call graph for first file (unindexed project context)
        first_metric = all_metrics[0] if all_metrics else {}
        call_graph_section = _format_call_graph(first_metric)
        if call_graph_section:
            sections.append(call_graph_section)

    # Add project context if in a git repo
    project_context = _get_project_context()
    if project_context:
        sections.append(project_context)

    if sections:
        context["prepended_content"] = "\n".join(sections)

    return context
