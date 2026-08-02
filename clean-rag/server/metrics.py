"""Code metrics collection and caching for context injection.

Collects complexity, maintainability, and quality metrics via AST analysis.
Results cached and lazy-loaded, injected into RAG context.
"""

import ast
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import logging

logger = logging.getLogger(__name__)

try:
    from radon.complexity import cc_visit, cc_rank
    from radon.metrics import mi_visit
    _HAS_RADON = True
except ImportError:
    _HAS_RADON = False
    logger.warning(
        "radon not installed -- cyclomatic_complexity falls back to a line scan "
        "and maintainability_index is unavailable"
    )

from .edge_extraction import get_language

METRICS_CACHE_DIR = Path(os.environ.get("METRICS_CACHE_DIR", "state/metrics-cache"))
CACHE_TTL_SECONDS = int(os.environ.get("METRICS_CACHE_TTL", "3600"))

# Bumped when a metric's definition changes, so that a value cached by the old
# definition is no longer served for unchanged file content. Same mechanism as
# config.PIPELINE_VERSION / manifest["__pipeline_version__"] in indexing.py: an
# entry stamped with a different version is discarded, and so is every entry
# written before the stamp existed, since those have no version key at all.
#
# 2: a file that exhausts the parser's or radon's stack now yields real
#    lines_of_code and a call graph, where version 1 cached {"file", "error"}.
METRICS_SCHEMA_VERSION = 2


def _get_file_hash(filepath: str) -> str:
    """Compute hash of file contents for cache invalidation."""
    try:
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:8]
    except Exception as e:
        logger.warning(f"Failed to hash {filepath}: {e}")
        return "unknown"


def _no_python_metrics(filepath: str, step: str, exc: Exception) -> None:
    """Record that a file yielded no Python-only metrics, and why.

    Both analysis steps route their failures through here, so the two reasons a
    file can be refused stay distinguishable in the log:

    * The source is not valid Python. ``SyntaxError`` (which covers
      ``IndentationError``, and the embedded-null-byte case from CPython 3.12
      on) and ``ValueError`` (that same case on earlier versions) are the
      documented classes. Routine input, so INFO.
    * Anything else, which in practice means valid source that a step could not
      process. The ``ast`` docs warn that "it is possible to crash the Python
      interpreter with a sufficiently large/complex string due to stack depth
      limitations in Python's AST compiler", and CPython reports that as
      whichever stage ran out of stack first: ``MemoryError("Parser stack
      overflowed")`` from the PEG parser, ``RecursionError`` from the AST
      compiler or from radon's own recursive visitors. Despite the class names,
      neither is an out-of-memory nor a runaway recursion in this process --
      both are a stack limit being reported on a pathological file. Logged at
      WARNING naming the exception class, so an unrecognised failure is visible
      rather than silently downgraded to "no Python metrics".
    """
    # SyntaxError and ValueError are the documented "this is not parseable
    # Python" classes. That is routine input for a scanner pointed at a whole
    # tree, so INFO. Anything else is a step that could not process source which
    # DID parse, which is the case the docstring above says must stay visible,
    # so WARNING naming the class.
    if isinstance(exc, (SyntaxError, ValueError)):
        logger.info("No Python metrics for %s: source does not parse (%s)", filepath, exc)
    else:
        logger.warning(
            "No Python metrics for %s: %s could not analyse it (%s: %s)",
            filepath,
            step,
            type(exc).__name__,
            exc,
        )


def _parse_python(content: str, filepath: str) -> ast.Module | None:
    """Parse Python source, or return None when the parser cannot handle it.

    Every radon entry point parses the source itself and raises on anything that
    is not valid Python (``cc_visit`` -> ``code2ast``, ``mi_visit`` ->
    ``mi_parameters`` -> ``ast.parse``). A file with a ``.py`` extension can
    still hold content the parser refuses, so the same stdlib parse runs here
    first and radon is only ever handed source that is known to compile.

    The guard is deliberately ``except Exception`` rather than a class tuple.
    ``ast.parse`` reports a refusal as whichever internal limit it hit, and
    those classes share no base beyond ``Exception``: ``SyntaxError`` for
    invalid syntax and for too-deep parentheses, ``ValueError`` for null bytes
    on older CPython, ``RecursionError`` from the AST compiler, ``MemoryError``
    from the PEG parser, and per CPython gh-150001 that last one can escalate
    again. Enumerating them is what let this leak once already. The try body is
    a single stdlib call, so the only thing a broader guard can hide is a wrong
    argument type from this module, which ``_no_python_metrics`` surfaces at
    WARNING. That trade is the standard per-file isolation point: record the
    failure and carry on, exactly as radon's own harvester does per file
    (``radon/cli/harvest.py``) rather than aborting the run.
    """
    try:
        return ast.parse(content)
    except Exception as e:
        _no_python_metrics(filepath, "ast.parse", e)
        return None


def _extract_call_graph(tree: ast.Module | None) -> dict:
    """Extract function/class definitions and imports from a parsed Python AST.

    ``tree`` is None for a file that is not Python or does not parse, which has
    no call graph to walk rather than being a failure.
    """
    if tree is None:
        return {"functions": [], "classes": [], "imports": []}

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


def _python_metrics(content: str, lines: list[str], filepath: str) -> dict | None:
    """Compute the Python-only metrics, or None when they cannot be computed.

    Returns just those fields, so the caller keeps one place where the full
    schema is assembled. ``complexity_warning`` is present only when a function
    actually warrants one.

    Parsing successfully is not enough to guarantee radon can measure the
    result: ``cc_visit`` and ``mi_visit`` walk the tree with recursive visitors,
    which exhaust Python's recursion limit at a far shallower nesting than the
    C parser's own limit. So source that ``_parse_python`` accepted can still
    take radon down, and it gets the same treatment for the same reason. The
    guard is separate from the parse guard on purpose: ``ast.walk`` is
    deque-based rather than recursive, so the call graph is still fully
    recoverable for a file radon cannot measure, and merging the two guards
    would throw it away.
    """
    if not _HAS_RADON:
        # Fallback: simplified line scan estimate
        keywords = ("if ", "elif ", "for ", "while ", "except ")
        return {
            "cyclomatic_complexity": 1
            + sum(1 for line in lines if any(kw in line for kw in keywords)),
            "complexity_rank": None,
            "maintainability_index": None,
        }

    try:
        return _radon_metrics(content)
    except Exception as e:
        _no_python_metrics(filepath, "radon", e)
        return None


def _radon_metrics(content: str) -> dict:
    """Run radon over source already known to parse. Raises what radon raises."""
    blocks = cc_visit(content)
    complexity = max((b.complexity for b in blocks), default=1)
    metrics = {
        "cyclomatic_complexity": complexity,
        "complexity_rank": cc_rank(complexity),
        # Real Maintainability Index, Halstead volume included. The formula this
        # replaced dropped the Halstead term and substituted complexity**0.4,
        # which is a different metric wearing the same name.
        "maintainability_index": round(mi_visit(content, True), 1),
    }

    # Warn on any function exceeding C rank (complexity > 20)
    over_budget = [b for b in blocks if b.complexity > 20]
    if over_budget:
        worst = max(over_budget, key=lambda b: b.complexity)
        metrics["complexity_warning"] = (
            f"Function {worst.name} has complexity {worst.complexity} "
            f"(rank {cc_rank(worst.complexity)}), consider refactoring"
        )
    return metrics


def _compute_metrics(filepath: str) -> dict:
    """Compute metrics for a file (AST-based complexity, LOC, etc.)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

        # radon only works on Python, and only on Python that parses. Check both
        # before calling it: the extension via edge_extraction's map, so there is
        # only one such table in the tree, then the source itself. Letting a
        # SyntaxError from inside radon reach the outer handler would throw away
        # lines_of_code and call_graph along with it.
        tree = None
        python_metrics = None
        if get_language(filepath) == "python":
            tree = _parse_python(content, filepath)
            if tree is not None:
                python_metrics = _python_metrics(content, lines, filepath)

        result = {
            "file": filepath,
            "lines_of_code": loc,
            # None for anything radon cannot measure, so the schema is the same
            # for every language rather than gaining and losing keys.
            "cyclomatic_complexity": None,
            "complexity_rank": None,
            "maintainability_index": None,
            # Extracted from the AST already parsed above
            "call_graph": _extract_call_graph(tree),
            "computed_at": datetime.now().isoformat(),
        }
        if python_metrics is not None:
            result.update(python_metrics)
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

            # The file hash alone cannot tell an entry computed by an older
            # definition of these metrics apart from a current one, because the
            # same bytes now yield a different maintainability_index. Require the
            # version stamp to match too; entries written before the stamp
            # existed have no such key and so are recomputed here.
            if (
                cached.get("__metrics_version__") == METRICS_SCHEMA_VERSION
                and cached.get("file_hash") == file_hash
            ):
                cached_time = datetime.fromisoformat(cached["cached_at"])
                if datetime.now() - cached_time < timedelta(seconds=CACHE_TTL_SECONDS):
                    return cached["metrics"]
        except Exception as e:
            logger.warning(f"Failed to read cache for {filepath}: {e}")

    # Recompute and cache
    metrics = _compute_metrics(filepath)
    cache_entry = {
        "file": filepath,
        "__metrics_version__": METRICS_SCHEMA_VERSION,
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
        # Complexity and maintainability are None for files that are not Python,
        # where radon cannot run. Omit them rather than printing "None" as a score.
        parts = [f"LOC={m['lines_of_code']}"]
        if m.get("cyclomatic_complexity") is not None:
            parts.append(f"Complexity={m['cyclomatic_complexity']}{rank_str}")
        if m.get("maintainability_index") is not None:
            parts.append(f"Maintainability={m['maintainability_index']}")
        lines.append(f"- **{m['file']}**: {', '.join(parts)}")
        warning = m.get("complexity_warning")
        if warning:
            lines.append(f"  - Warning: {warning}")

    return "\n".join(lines)
