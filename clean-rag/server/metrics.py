"""Code metrics collection and caching for context injection.

Collects complexity, maintainability, and quality metrics via AST analysis.
Results cached and lazy-loaded, injected into RAG context.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import logging

try:
    from radon.complexity import cc_visit, cc_rank
    _HAS_RADON = True
except ImportError:
    _HAS_RADON = False

logger = logging.getLogger(__name__)

METRICS_CACHE_DIR = Path(os.environ.get("METRICS_CACHE_DIR", "state/metrics-cache"))
CACHE_TTL_SECONDS = int(os.environ.get("METRICS_CACHE_TTL", "3600"))


def _get_file_hash(filepath: str) -> str:
    """Compute hash of file contents for cache invalidation."""
    try:
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:8]
    except Exception as e:
        logger.warning(f"Failed to hash {filepath}: {e}")
        return "unknown"


def _extract_call_graph(filepath: str) -> dict:
    """Extract function/class definitions and imports via AST."""
    try:
        import ast

        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        functions = []
        classes = []
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        return {
            "functions": list(set(functions))[:10],  # Top 10
            "classes": list(set(classes))[:10],
            "imports": list(set(imports))[:10],
        }
    except Exception:
        return {"functions": [], "classes": [], "imports": []}


def _compute_metrics(filepath: str) -> dict:
    """Compute metrics for a file (AST-based complexity, LOC, etc.)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

        # Cyclomatic complexity via radon (real McCabe on AST), with fallback
        complexity_rank = None
        complexity_warning = None
        if _HAS_RADON:
            results = cc_visit(content)
            if results:
                complexity = max(r.complexity for r in results)
                complexity_rank = cc_rank(complexity)
                # Warn on any function exceeding C rank (complexity > 20)
                bad = [r for r in results if r.complexity > 20]
                if bad:
                    worst = max(bad, key=lambda r: r.complexity)
                    complexity_warning = (
                        f"Function {worst.name} has complexity {worst.complexity} "
                        f"(rank {cc_rank(worst.complexity)}), consider refactoring"
                    )
            else:
                complexity = 1
                complexity_rank = "A"
        else:
            # Fallback: simplified line scan estimate
            complexity = 1 + sum(1 for line in lines if any(kw in line for kw in ["if ", "elif ", "for ", "while ", "except "]))

        # Maintainability index (simplified: based on LOC and complexity)
        maintainability = max(0, min(100, 171 - 5.2 * (complexity ** 0.4) - 0.23 * loc + 50 * (loc ** -0.5)))

        # Extract call graph
        call_graph = _extract_call_graph(filepath)

        result = {
            "file": filepath,
            "lines_of_code": loc,
            "cyclomatic_complexity": complexity,
            "complexity_rank": complexity_rank,
            "maintainability_index": round(maintainability, 1),
            "call_graph": call_graph,
            "computed_at": datetime.now().isoformat(),
        }
        if complexity_warning is not None:
            result["complexity_warning"] = complexity_warning
        return result
    except Exception as e:
        logger.warning(f"Failed to compute metrics for {filepath}: {e}")
        return {"file": filepath, "error": str(e)}


def get_metrics(filepath: str, force_recompute: bool = False) -> dict:
    """Get cached metrics, recompute if missing/stale."""
    METRICS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_file = METRICS_CACHE_DIR / f"{hashlib.sha256(filepath.encode()).hexdigest()[:8]}.json"
    file_hash = _get_file_hash(filepath)

    # Check cache
    if cache_file.exists() and not force_recompute:
        try:
            with open(cache_file) as f:
                cached = json.load(f)

            if cached.get("file_hash") == file_hash:
                cached_time = datetime.fromisoformat(cached["cached_at"])
                if datetime.now() - cached_time < timedelta(seconds=CACHE_TTL_SECONDS):
                    return cached["metrics"]
        except Exception as e:
            logger.warning(f"Failed to read cache for {filepath}: {e}")

    # Recompute and cache
    metrics = _compute_metrics(filepath)
    cache_entry = {
        "file": filepath,
        "file_hash": file_hash,
        "cached_at": datetime.now().isoformat(),
        "metrics": metrics,
    }

    try:
        with open(cache_file, "w") as f:
            json.dump(cache_entry, f)
    except Exception as e:
        logger.warning(f"Failed to write cache for {filepath}: {e}")

    return metrics


def format_metrics_for_context(metrics_list: list[dict]) -> str:
    """Format metrics as markdown for prompt injection."""
    if not metrics_list:
        return ""

    lines = ["## Code Quality Metrics", ""]
    for m in metrics_list:
        if "error" in m:
            continue
        rank = m.get("complexity_rank", "")
        rank_str = f" ({rank})" if rank else ""
        lines.append(f"- **{m['file']}**: LOC={m['lines_of_code']}, Complexity={m['cyclomatic_complexity']}{rank_str}, Maintainability={m['maintainability_index']}")
        warning = m.get("complexity_warning")
        if warning:
            lines.append(f"  - Warning: {warning}")

    return "\n".join(lines)
