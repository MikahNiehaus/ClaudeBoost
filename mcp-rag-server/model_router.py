"""Dynamic per-language model router with idle-based unloading.

Maintains a pool of embedding models, each keyed by model name.
Models are loaded on demand and automatically unloaded after IDLE_TIMEOUT seconds
of inactivity (default: 7200 seconds = 2 hours).

Usage:
    router = ModelRouter()
    embs = router.encode("go", texts)   # loads best model for Go, returns embeddings
    router.shutdown()                   # stop background thread before exit

The per-language model config lives in:
    mcp-rag-server/tests/data/best_model_config.json

If that file is absent, falls back to all-MiniLM-L6-v2 for everything.

All models are CPU-only. Query time for a single string is essentially instant
regardless of model size. The idle-unload thread checks every 5 minutes.
"""

import threading
import time
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    HAS_ST = True
except ImportError:
    HAS_ST = False

import json

IDLE_TIMEOUT = 7200          # seconds of inactivity before a model is unloaded
CHECK_INTERVAL = 300         # how often the cleanup thread checks (5 min)
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_CONFIG_PATH = Path(__file__).parent / "tests" / "data" / "best_model_config.json"


def _load_config() -> dict[str, str]:
    """Return {lang: model_name} from the benchmark config, or {} if not found."""
    if not _CONFIG_PATH.exists():
        return {}
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return {lang: info["model"] for lang, info in raw.items()}
    except Exception:
        return {}


class ModelRouter:
    """Thread-safe pool of SentenceTransformer models with idle unloading."""

    def __init__(self, idle_timeout: int = IDLE_TIMEOUT):
        if not HAS_ST:
            raise ImportError("sentence-transformers not installed")
        self._idle_timeout = idle_timeout
        self._lang_to_model: dict[str, str] = _load_config()
        self._loaded: dict[str, SentenceTransformer] = {}
        self._last_used: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cleaner = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleaner.start()

    def model_for_lang(self, lang: str) -> str:
        """Return the best model name for a language (or default)."""
        return self._lang_to_model.get(lang, DEFAULT_MODEL)

    def _get_model(self, model_name: str) -> "SentenceTransformer":
        """Return a loaded model, loading it on first use."""
        with self._lock:
            if model_name not in self._loaded:
                print(f"[ModelRouter] Loading {model_name} ...", flush=True)
                t0 = time.time()
                self._loaded[model_name] = SentenceTransformer(model_name)
                print(f"[ModelRouter] {model_name} ready in {time.time()-t0:.1f}s", flush=True)
            self._last_used[model_name] = time.time()
            return self._loaded[model_name]

    def encode(
        self,
        lang: str,
        texts: list[str],
        batch_size: int = 256,
        normalize: bool = True,
    ):
        """Encode texts using the best model for lang. Returns numpy array."""
        model_name = self.model_for_lang(lang)
        model = self._get_model(model_name)
        return model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
        )

    def encode_query(self, lang: str, query: str):
        """Encode a single query string. Near-instant for all model sizes."""
        return self.encode(lang, [query])[0]

    def loaded_models(self) -> list[str]:
        with self._lock:
            return list(self._loaded.keys())

    def _cleanup_loop(self):
        while not self._stop_event.wait(CHECK_INTERVAL):
            now = time.time()
            to_unload = []
            with self._lock:
                for name, last in list(self._last_used.items()):
                    if now - last > self._idle_timeout:
                        to_unload.append(name)
            for name in to_unload:
                with self._lock:
                    if name in self._loaded:
                        del self._loaded[name]
                        del self._last_used[name]
                        print(f"[ModelRouter] Unloaded idle model: {name}", flush=True)

    def shutdown(self):
        """Stop background thread. Call before process exit."""
        self._stop_event.set()
        self._cleaner.join(timeout=2)


# Module-level singleton — import and use directly
_router: ModelRouter | None = None
_router_lock = threading.Lock()


def get_router() -> ModelRouter:
    """Return the module-level singleton ModelRouter, creating it if needed."""
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = ModelRouter()
    return _router


def encode(lang: str, texts: list[str], **kwargs):
    """Convenience wrapper: encode texts using the best model for lang."""
    return get_router().encode(lang, texts, **kwargs)


def encode_query(lang: str, query: str):
    """Convenience wrapper: encode a single query string."""
    return get_router().encode_query(lang, query)
