"""Configuration for the clean-rag server."""

import os
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent          # clean-rag/server/


def _load_env_files() -> None:
    """Load config from .env files, so a machine can be configured without
    touching settings.json or exporting shell vars.

    Separated and conjoined: clean-rag reads its OWN clean-rag/.env first
    (separated), then falls back to a ClaudeBoost/.env one level up when it's
    bundled there (conjoined). Precedence, highest wins:

        real env vars (settings.json)  >  clean-rag/.env  >  ClaudeBoost/.env  >  code defaults

    Real env vars win because setdefault never overwrites an already set key.
    clean-rag/.env wins over ClaudeBoost/.env because it's loaded first, and the
    first file to set a key keeps it.

    Both .env files are gitignored, so each machine has its own. The committed
    templates are .env.example. Hand rolled on purpose, a KEY=VALUE reader isn't
    worth a python-dotenv dependency.
    """
    clean_rag_root = _MODULE_DIR.parent                # clean-rag/
    for env_path in (clean_rag_root / ".env", clean_rag_root.parent / ".env"):
        if not env_path.is_file():
            continue
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
        except OSError:
            # A missing or unreadable .env is not fatal, defaults still apply.
            pass


_load_env_files()

# clean-rag home: the root of the clean-rag installation.
# Set via CLEAN_RAG_HOME env var, or derive from this file's location.
CLEAN_RAG_HOME = Path(os.environ.get(
    "CLEAN_RAG_HOME",
    str(_MODULE_DIR.parent),                           # clean-rag/
))

# Subdirectories
DATABASES_DIR = CLEAN_RAG_HOME / "databases"
STATE_DIR = CLEAN_RAG_HOME / "state"

# Embedding model for project codebase indexing.
# CodeRankEmbed (768d) trained on CodeSearchNet code-query pairs.
CODE_EMBEDDING_MODEL = os.environ.get(
    "CLEAN_RAG_CODE_EMBEDDING_MODEL",
    "nomic-ai/CodeRankEmbed",
)

# Bumped when the chunking or embedding pipeline changes in a way that
# requires a full re-index. When a project's manifest records a different
# version, the next index_project run forces a rebuild automatically.
PIPELINE_VERSION = 2

# Server port: 8613 standalone, 8612 routes when bundled with ClaudeBoost
STANDALONE_PORT = int(os.environ.get("CLEAN_RAG_PORT", "8613"))

# Chunking defaults
MAX_CHUNK_TOKENS = 500
MIN_CHUNK_TOKENS = 50
CHUNK_OVERLAP_TOKENS = int(os.environ.get("CLEAN_RAG_CHUNK_OVERLAP", "50"))

# Search defaults
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_MIN_SCORE = 0.5

# Degenerate chunk filter: skip chunks with fewer tokens than this
DEGENERATE_CHUNK_MIN_TOKENS = 10

# Embedding batch size
EMBED_BATCH_SIZE = int(os.environ.get("CLEAN_RAG_EMBED_BATCH_SIZE", "32"))

def _detect_device() -> str:
    """Detect the best available compute device."""
    override = os.environ.get("CLEAN_RAG_DEVICE", "").strip()
    if override:
        return override
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


DEVICE: str = _detect_device()

# ---------------------------------------------------------------------------
# CPU budget
#
# Embedding is the only genuinely CPU hungry thing this server does, and torch
# defaults to every core it can see, which makes the machine unusable during a
# rebuild. Two independent limits, because neither is sufficient alone:
#
#   CPU_MAX_PERCENT is the ceiling on TOTAL system CPU. A background sweep
#   checks it between files and waits while the machine is busier than this,
#   which is what accounts for load this process did not create.
#
#   TORCH_THREADS is the structural cap on this process. It holds even when
#   nothing is sampling, and it is what stops a single embed call from
#   saturating every core between samples.
#
# The two must not be derived from the same number, which is the bug this
# comment now exists to prevent. TORCH_THREADS used to be CPU_MAX_PERCENT of
# the cores, so on a 14 core machine the process was allowed 11 threads (79%)
# against an 80% ceiling. Embedding at full tilt then tripped the ceiling on
# its own, with nothing else running: pause, CPU falls, resume, spike, pause.
#
# Measured cost of that oscillation: 406 pauses on one project, 64 s/file, and
# a log line reading "DONE 4 files, 477.5 min". The sweep was not yielding to
# other work, it was yielding to itself.
# ---------------------------------------------------------------------------

# CPU THROTTLING IS OFF by default, by explicit request after the history above.
#
# 100 or more means disabled, and sample_pressure skips the CPU check entirely
# rather than comparing against an unreachable number. Set a real percentage
# here (or CLEAN_RAG_CPU_MAX_PERCENT) to turn pausing back on.
#
# What this gives up: the sweep no longer yields to other work on the machine.
# What it keeps: MIN_FREE_RAM_MB below, and the RSS ceiling in the batch driver.
# Those are not throttles, they are the guards against the failure that actually
# hurt, a machine driven to 0.2 GB free with 16.8 GB paged out. CPU contention
# makes a machine slow; memory exhaustion makes it stop.
CPU_MAX_PERCENT = float(os.environ.get("CLEAN_RAG_CPU_MAX_PERCENT", "100"))

# Fraction of cores torch may use. 1.0 means every core.
#
# This was 0.55 to keep the process clear of the pause ceiling it was checked
# against. With pausing off there is nothing to stay clear of, so the reason for
# holding cores back is gone too. Half a machine sitting idle was only ever the
# price of politeness, and politeness is now off.
TORCH_CORE_FRACTION = float(os.environ.get("CLEAN_RAG_TORCH_CORE_FRACTION", "1.0"))

#: How many embedding models may sit in RAM at once.
#:
#: Two, matching ModelCache.DEFAULT_MAX_RESIDENT. This was 1, and 1 is what
#: makes a large index never finish.
#:
#: The old reasoning for 1 was that the query side used to embed with the global
#: CODE_EMBEDDING_MODEL while indexing used whatever the router picked, and that
#: search now resolves the model from each project's own provenance, so the two
#: no longer alternate. The first half is still true. The conclusion was not:
#: fixing search did not stop the alternation, because the 10 minute auto
#: reindex sweep walks every registered project and therefore touches every
#: model group whether or not anything needs indexing.
#:
#: Measured on a real run, at a cap of 1:
#:
#:   15:34:31 [server.lang_router] ModelCache: evicting
#:            Salesforce/SFR-Embedding-Code-400M_R to stay within 1 resident
#:
#: That eviction landed in the middle of a C# index run, so the run reloaded a
#: 400M model to continue. SFR costs 135s to reload. Observed throughput was
#: 6 files per 30 minutes, and two projects stayed stuck at __incomplete__
#: across many sweeps because a resumed run spent its time reloading rather
#: than embedding.
#:
#: Measured resident: CodeRankEmbed 1069 MB, SFR-Embedding-Code-400M_R 2161 MB.
#: Holding both is 3.2 GB, and embedding roughly doubles the active one at the
#: peak, so budget about 5.4 GB. That is real, and it is the price of the
#: indexes finishing at all. MIN_FREE_RAM_MB below is the other half of the same
#: budget, sized from the same measured model cost, and it was left at the number
#: a cap of 1 implied when this went to 2. Change one, read the other.
#:
#: Drop it to 1 only for a batch job that processes one model group at a time
#: and runs with the sweep off, which is the case ModelCache documents.
MAX_RESIDENT_MODELS = max(
    1, int(os.environ.get("CLEAN_RAG_MAX_RESIDENT_MODELS", "") or 2)
)

#: Measured resident cost of the largest routable embedder,
#: Salesforce/SFR-Embedding-Code-400M_R. CodeRankEmbed is 1069 MB. Both numbers
#: come from the measurements recorded on ModelCache.DEFAULT_MAX_RESIDENT in
#: lang_router.py, and a budget has to assume the larger one.
LARGEST_MODEL_RESIDENT_MB = 2161.0


def _default_min_free_ram_mb() -> float:
    """Free RAM a background reindex needs before it may start or continue.

    Derived from the model budget rather than picked on its own. The flat
    3072 MB this replaces was set while MAX_RESIDENT_MODELS was 1; raising the
    cap to 2 without touching it left the gate below the growth a single project
    can still add after passing it, which is the
    "DefaultCPUAllocator: not enough memory" failure in state/server.log.

    The number covers growth after the check, not the whole 5.4 GB steady state:
    psutil's available RAM already excludes whatever models are resident when the
    sample is taken. Between two checks a sweep can load one model
    (LARGEST_MODEL_RESIDENT_MB) and then peak while embedding with it, and
    embedding roughly doubles the active model, so twice the largest model is the
    worst case. Checks happen between projects and, via PressureCheckpoint,
    between files during a project; nothing can interrupt a single file's embed,
    which is why the gate has to leave room for a whole peak rather than react to
    one.

    It does not scale with MAX_RESIDENT_MODELS, on purpose. Models already
    resident are already missing from the available reading, and at most one
    project starts between two checks, so a third slot would not add a third
    load to cover here. What the cap changes is how much of the machine is gone
    before the sample is even taken, which this gate then sees directly.

    Higher is not automatically safer. A gate the machine cannot clear skips the
    sweep instead, and an index that never runs never finishes, which is the
    failure the cap of 2 exists to fix. This is the smallest number that covers
    the measured peak.
    """
    return LARGEST_MODEL_RESIDENT_MB * 2


# Minimum free RAM, in MB, before a background reindex is allowed to start or
# continue. A sweep observed here grew to a 43 GB virtual commit and drove the
# machine to 0.2 GB free with 16.8 GB paged out, which is worse than the CPU
# problem: CPU contention makes the machine slow, memory exhaustion makes it
# stop. Checked on the same schedule as the CPU ceiling.
MIN_FREE_RAM_MB = float(
    os.environ.get("CLEAN_RAG_MIN_FREE_RAM_MB", "") or _default_min_free_ram_mb()
)


def _default_torch_threads() -> int:
    """Cap torch at TORCH_CORE_FRACTION of the machine's cores, at least one.

    Sized against the core count, NOT against CPU_MAX_PERCENT: deriving it from
    the ceiling is what made the process throttle itself. Leaving a real gap
    between the two is the whole point.
    """
    cores = os.cpu_count() or 1
    return max(1, int(cores * TORCH_CORE_FRACTION))


TORCH_THREADS = int(
    os.environ.get("CLEAN_RAG_TORCH_THREADS", "") or _default_torch_threads()
)

# ---------------------------------------------------------------------------
# Background reindex schedule
#
# Hourly is fine, but only because the sweep now backs off: it waits while the
# machine is busy and it refuses to start when the previous sweep is still
# running. Without both of those, an hourly timer against a sweep that takes
# longer than an hour stacks sweeps until nothing else can run.
# ---------------------------------------------------------------------------

SWEEP_INTERVAL_S = int(os.environ.get("CLEAN_RAG_SWEEP_INTERVAL_S", str(10 * 60)))

# How long to wait before re-sampling when the machine is over CPU_MAX_PERCENT.
CPU_BACKOFF_S = float(os.environ.get("CLEAN_RAG_CPU_BACKOFF_S", "5"))

# Give up waiting for a quiet machine after this long and skip the sweep
# entirely rather than queue behind sustained load.
CPU_BACKOFF_MAX_WAIT_S = float(
    os.environ.get("CLEAN_RAG_CPU_BACKOFF_MAX_WAIT_S", str(30 * 60))
)

# How often a running index stops to ask whether it should give the machine
# back. This is the checkpoint *inside* one project's index, which is the only
# thing that bounds how long a single large project can hold the machine: the
# between-projects check can only refuse to start the next one. 15s means the
# user waits at most one more file plus 15s to get their cores back, while the
# sample itself costs one psutil read per 15s.
INDEX_PRESSURE_CHECK_S = float(
    os.environ.get("CLEAN_RAG_INDEX_PRESSURE_CHECK_S", "15")
)

# How often a running index flushes its manifest to disk.
#
# index_project used to write the manifest exactly once, at the end. A graceful
# abort still saved (marked incomplete, and the next sweep resumed from it), but
# a hard kill saved nothing at all, so every file read as changed on the next
# pass, tripped FULL_REINDEX_THRESHOLD, and forced a rebuild from zero. That is
# not theoretical: it cost hours on a real run.
#
# An interval rather than a file count because per file cost here is nowhere
# near uniform, milliseconds for a small file against seconds for a large one,
# so "every N files" bounds the lost work unpredictably while an interval bounds
# it directly. Same reasoning as INDEX_PRESSURE_CHECK_S above.
#
# 30s against a manifest measured at 55 to 60KB for ~790 files, so roughly
# 1.2MB per write on a 16,000 file project. At this interval that is a couple of
# writes a minute, against the multi gigabyte total that saving per file would
# cost over a full run.
INDEX_MANIFEST_CHECKPOINT_S = float(
    os.environ.get("CLEAN_RAG_INDEX_MANIFEST_CHECKPOINT_S", "30")
)

# Web search fallback config
WEB_SEARCH_ENABLED = os.environ.get("CLEAN_RAG_WEB_SEARCH", "true").lower() in ("true", "1", "yes")
WEB_SEARCH_TIMEOUT = float(os.environ.get("CLEAN_RAG_WEB_SEARCH_TIMEOUT", "4.0"))
WEB_SEARCH_MAX_RESULTS = int(os.environ.get("CLEAN_RAG_WEB_SEARCH_MAX_RESULTS", "3"))
WEB_SEARCH_SCORE_THRESHOLD = float(os.environ.get("CLEAN_RAG_WEB_SEARCH_THRESHOLD", "0.4"))
