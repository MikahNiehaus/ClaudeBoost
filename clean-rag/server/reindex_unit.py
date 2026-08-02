"""The unit of work both reindex drivers share, and the plan that orders it.

Two drivers sweep the same projects for different reasons:

  * ``auto_reindex.auto_reindex_loop`` runs inside the server, hourly, forever,
    and is incremental: it diffs against the manifest and touches only what
    changed.
  * ``cli/reindex_batch.py`` runs once, exhaustively, rebuilding every project
    because the embedding model changed, and exits when it is done.

They are different SCHEDULES over the same WORK. Keeping the work in one place
is the point of this module: the last time "sweep every project" existed twice,
a bug where per file reindex silently erased ``__pipeline_version__`` and
``__model_id__`` from the manifest survived unnoticed, because fixing one copy
did nothing to the other.

What deliberately does NOT live here:

  * The incremental full-rebuild heuristic (``FULL_REINDEX_THRESHOLD``). It asks
    "has this drifted enough that per file calls stop being cheap", which is
    meaningless to a batch job that is always full by design.
  * The memory ceiling and the exit-and-relaunch. torch never returns CPU
    memory, so the only real reclaim is process exit, and the server cannot
    exit. That is genuinely a driver level difference, not shared policy.
"""

from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass
from pathlib import Path

# STATE_DIR only. DATABASES_DIR is deliberately NOT imported here: binding it
# at module load froze it at whatever it was when this module first imported,
# so anything that repoints it later (a test harness, a different
# CLEAN_RAG_HOME) was ignored and the eviction below targeted a path nothing
# was cached under. Every use of it in this file resolves it at call time.
from .config import STATE_DIR
from .indexing import _project_paths, read_project_provenance

logger = logging.getLogger(__name__)


class Outcome(enum.StrEnum):
    """Why a per project attempt stopped.

    The batch driver retries on PAUSED but not on ERRORED, and one shared
    counter for both meant a project that always errored burned the same
    attempt budget as one that was merely waiting for a quiet machine.

    ``StrEnum`` rather than bare string constants: the surrounding modules do
    use plain strings for statuses, but those are single valued flags, whereas
    these five are a closed set that gets compared and branched on. StrEnum IS
    a str, so it stays compatible with that house style while making the set
    explicit and typo proof.
    """

    COMPLETED = "completed"
    PAUSED = "paused"          # resource guard asked for the machine back
    OVER_MEMORY = "over_memory"  # driver must exit and be relaunched
    ERRORED = "errored"
    GAVE_UP = "gave_up"


@dataclass
class PlannedProject:
    """One project in a sweep plan.

    A dataclass because that is unanimously what this package already uses for
    small records: ``Chunk`` and ``SearchResult`` in store.py, ``RawChunk`` in
    code_chunker.py.
    """

    pid: str
    path: str
    model: str | None
    size: int
    #: True when ``size`` came from the registry rather than a real count. The
    #: registry's ``files_indexed`` is written only by ``index_project``, never
    #: by ``reindex_file``, so it drifts after incremental sweeps. Good enough
    #: to order by, not good enough to report as fact.
    size_is_estimate: bool = True


def read_registry() -> dict:
    """Load ``state/projects.json``.

    The canonical reader. There were three copies of this before
    (``auto_reindex._read_registry``, ``app._list_projects``, and one in
    hooks/reindex-after-edit.py) differing only in which exceptions they caught.
    This is the tighter of the two server side ones: a narrow except, and an
    error rather than a warning, because a corrupt registry is not routine.
    """
    path = STATE_DIR / "projects.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Could not read the project registry: %s", e)
        return {}


def release_project_resources(pid: str) -> None:
    """Close one project's cached SQLite handle and built graph, then collect.

    Best effort: failing to release memory must never abort a sweep that is
    otherwise working.
    """
    try:
        # Imported at call time, not module load. DATABASES_DIR is resolved from
        # config when this actually runs, so a harness or an environment that
        # repoints it is honored. Binding it at import froze the value at
        # whatever it was when this module first loaded, which silently made the
        # eviction target a path nothing was ever cached under.
        from .config import DATABASES_DIR
        from .graph_store import evict_graph_cache
        from .store import ChromaStore

        project_dir = DATABASES_DIR / "_projects" / pid
        ChromaStore.evict_cache(str(project_dir / "chroma"))
        evict_graph_cache(project_dir / "graph.db")
    except Exception:
        logger.debug("Could not evict store cache for %s", pid, exc_info=True)
    try:
        import gc

        gc.collect()
    except Exception:
        pass


def recorded_model(project_path: str) -> str | None:
    """The model that actually produced this project's existing vectors.

    One manifest read, no directory walk. Returns None for a project that has
    never been indexed, or one indexed before provenance was recorded.
    """
    try:
        return read_project_provenance(project_path).get("model_id")
    except Exception:
        logger.debug("Could not read provenance for %s", project_path, exc_info=True)
        return None


def routed_model(project_path: str) -> tuple[str | None, int]:
    """The model the router WOULD pick for this project, and its real file count.

    Costs a full directory walk, so it is only for callers that need the answer
    for a project whose recorded model is unknown or about to change. Returns
    (model, file_count); the count is exact and free once the walk has happened.
    """
    from .edge_extraction import _EXT_TO_LANG
    from .file_scan import scan_project
    from .lang_router import get_model_for_project

    counts: dict[str, int] = {}
    total = 0
    try:
        for fp in scan_project(project_path):
            total += 1
            counts[_EXT_TO_LANG.get(Path(fp).suffix.lower(), "unknown")] = (
                counts.get(_EXT_TO_LANG.get(Path(fp).suffix.lower(), "unknown"), 0) + 1
            )
    except Exception:
        logger.debug("Could not scan %s", project_path, exc_info=True)
        return None, 0
    return get_model_for_project(counts), total


def project_model(project_path: str, *, for_rebuild: bool = False) -> str | None:
    """Which model to GROUP this project under.

    The two drivers are asking different questions and the difference matters.

    An incremental sweep re-embeds a handful of changed files into an index that
    already exists, so it must use the model those vectors were built with:
    that is the recorded one, and using anything else would mix embedding
    spaces inside one index. It never walks the tree. There is deliberately no
    ``routed_model`` fallback here, because that fallback made the unattended
    hourly loop pay a full directory walk per unprovenanced project for an
    answer it could not use: nothing is recorded only when nothing is indexed,
    and ``auto_reindex.find_changed_files`` returns ([], []) off the missing
    manifest without scanning, so the sweep does no work on that project at
    all. Measured on a 400 file project: 0.0372s with the fallback, 0.0001s
    without, times every unprovenanced project, every hour, for zero benefit.

    Unprovenanced projects therefore all share the single ``None`` group. That
    is the right bucket rather than a regrettable one: a group of no-ops needs
    no ordering, and keeping them contiguous stops them from being interleaved
    among the real groups, where each one would trip ``auto_reindex_loop``'s
    ``model_cache.evict_all()`` between two projects that wanted the same
    embedder. The one case that loses a little locality is a project indexed
    before provenance was recorded: it lands in the ``None`` group even though
    it may have real changed files. That costs at most one extra model load,
    it cannot mix embedding spaces (``index_project`` and ``reindex_file``
    each resolve their own model, the plan is only a hint about ordering), and
    such an index is already refused by search's provenance gate.

    A rebuild throws the index away, so the recorded model is history. What it
    needs is the model the router will pick when it runs, which is the only
    thing that predicts which embedder will actually be resident, and it gets
    an exact file count out of the same walk. Grouping the rebuild by the
    recorded model looked cheap and was wrong: it put every project whose
    manifest predates provenance into one "unknown" bucket, which is exactly
    the ungrouped thrash the plan exists to prevent.
    """
    if for_rebuild:
        model, _count = routed_model(project_path)
        return model or recorded_model(project_path)
    return recorded_model(project_path)


def _registry_size(entry: dict) -> int:
    """Rough file count from the registry.

    ``files_indexed`` is written only by ``index_project``, never by
    ``reindex_file``, so it drifts after incremental sweeps and reads low for a
    project whose last full index stopped early. Fine for ordering, which only
    needs roughly smallest first; never report it as a fact.
    """
    raw = entry.get("files_indexed")
    return int(raw) if isinstance(raw, int) and raw > 0 else 0


def plan_sweep(
    registry: dict | None = None, *, for_rebuild: bool = False
) -> list[PlannedProject]:
    """Order the registry so a sweep holds one embedding model at a time.

    Grouped by model, cheapest group first, smallest project first inside a
    group. Not a named scheduling algorithm, just the ordering the memory
    budget implies: an embedder costs 1 to 2 GB resident, ``ModelCache`` keeps
    at most a couple, and walking the registry in arbitrary order makes a sweep
    evict and reload across projects for nothing.

    Cheapest group first so the largest number of projects becomes searchable
    soonest, rather than the machine disappearing into the biggest corpus.

    Projects whose directory is gone are dropped: they cannot be indexed and
    including them only produces a confusing failure per sweep.
    """
    if registry is None:
        registry = read_registry()
    entries = registry.get("projects", registry) if isinstance(registry, dict) else {}

    planned: list[PlannedProject] = []
    for pid, entry in (entries or {}).items():
        if not isinstance(entry, dict):
            continue
        path = entry.get("project_path")
        if not path or not Path(path).exists():
            logger.debug("Skipping %s, path missing: %s", pid, path)
            continue
        # A rebuild has to walk the tree anyway to know which model the router
        # will pick, so take the exact file count from that same walk. An
        # incremental sweep does not, and settles for the registry's number.
        if for_rebuild:
            model, counted = routed_model(path)
            if counted:
                size, exact = counted, True
            else:
                size, exact = _registry_size(entry), False
        else:
            model = project_model(path)
            size, exact = _registry_size(entry), False

        planned.append(
            PlannedProject(
                pid=pid, path=path, model=model, size=size, size_is_estimate=not exact,
            )
        )

    # Total per model group decides group order, so "cheapest" means the whole
    # group, not its smallest member.
    group_cost: dict[str | None, int] = {}
    for p in planned:
        group_cost[p.model] = group_cost.get(p.model, 0) + p.size

    planned.sort(key=lambda p: (group_cost[p.model], str(p.model), p.size, p.path))
    return planned


def model_groups(planned: list[PlannedProject]) -> list[tuple[str | None, list[PlannedProject]]]:
    """Split an ordered plan into contiguous per model runs.

    Built on the ordering above rather than ``itertools.groupby`` over an
    unsorted input: groupby only groups CONSECUTIVE equal keys, so it silently
    produces one group per run on unsorted data. Taking a plan that is already
    grouped and slicing it keeps that requirement visible.
    """
    groups: list[tuple[str | None, list[PlannedProject]]] = []
    for p in planned:
        if groups and groups[-1][0] == p.model:
            groups[-1][1].append(p)
        else:
            groups.append((p.model, [p]))
    return groups


def index_dir_for(pid: str) -> Path:
    """Where this project's index lives. Resolved at call time, see the note
    on the config import above."""
    from .config import DATABASES_DIR

    return DATABASES_DIR / "_projects" / pid


__all__ = [
    "Outcome",
    "PlannedProject",
    "read_registry",
    "release_project_resources",
    "project_model",
    "plan_sweep",
    "model_groups",
    "index_dir_for",
    "_project_paths",
]
