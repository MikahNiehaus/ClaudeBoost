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

CPU_MAX_PERCENT = float(os.environ.get("CLEAN_RAG_CPU_MAX_PERCENT", "80"))

# Fraction of cores torch may use. Deliberately well below CPU_MAX_PERCENT so
# this process at full speed still leaves headroom under the ceiling it is
# checked against, instead of sitting exactly on it.
TORCH_CORE_FRACTION = float(os.environ.get("CLEAN_RAG_TORCH_CORE_FRACTION", "0.55"))

# Minimum free RAM, in MB, before a background reindex is allowed to start or
# continue. A sweep observed here grew to a 43 GB virtual commit and drove the
# machine to 0.2 GB free with 16.8 GB paged out, which is worse than the CPU
# problem: CPU contention makes the machine slow, memory exhaustion makes it
# stop. Checked on the same schedule as the CPU ceiling.
MIN_FREE_RAM_MB = float(os.environ.get("CLEAN_RAG_MIN_FREE_RAM_MB", "3072"))


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

SWEEP_INTERVAL_S = int(os.environ.get("CLEAN_RAG_SWEEP_INTERVAL_S", str(60 * 60)))

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

# Web search fallback config
WEB_SEARCH_ENABLED = os.environ.get("CLEAN_RAG_WEB_SEARCH", "true").lower() in ("true", "1", "yes")
WEB_SEARCH_TIMEOUT = float(os.environ.get("CLEAN_RAG_WEB_SEARCH_TIMEOUT", "4.0"))
WEB_SEARCH_MAX_RESULTS = int(os.environ.get("CLEAN_RAG_WEB_SEARCH_MAX_RESULTS", "3"))
WEB_SEARCH_SCORE_THRESHOLD = float(os.environ.get("CLEAN_RAG_WEB_SEARCH_THRESHOLD", "0.4"))
