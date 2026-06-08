"""Embedding service using sentence-transformers. Lazy-loaded singleton."""

import logging
import threading
from typing import Union

from rag_server.ports.embedding_port import EmbeddingPort

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"


def _resolve_device() -> Union[str, "torch.device"]:
    """Return the torch device to pass to SentenceTransformer/CrossEncoder constructors.

    "onnx-dml" uses OnnxDirectMLEmbedding (separate path, not SentenceTransformer).
    "dml" (legacy torch-directml) returns a torch_directml.device() object.
    All other DEVICE values are valid torch device strings.
    """
    from rag_server.config import DEVICE
    if DEVICE == "onnx-dml":
        return "cpu"   # SentenceTransformer isn't used when device=onnx-dml
    if DEVICE == "dml":
        try:
            import torch_directml
            return torch_directml.device()
        except Exception:
            return "cpu"
    return DEVICE

# Task-specific prefixes: (query_prefix, document_prefix)
# Required for asymmetric retrieval models — query and document must use different prefixes.
_TASK_PREFIX_MODELS = {
    # BGE: asymmetric retrieval — queries need the instruction prefix, docs don't.
    "BAAI/bge-base-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "BAAI/bge-large-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "BAAI/bge-small-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "nomic-ai/nomic-embed-text-v1":   ("search_query: ", "search_document: "),
    "nomic-ai/nomic-embed-text-v1.5": ("search_query: ", "search_document: "),
    "jinaai/jina-code-embeddings-0.5b": (
        "Represent the following query to retrieve code: ",
        "Represent the following code: ",
    ),
    "jinaai/jina-code-embeddings-1.5b": (
        "Represent the following query to retrieve code: ",
        "Represent the following code: ",
    ),
}

# Models that require trust_remote_code=True (custom pooling / architecture)
_TRUST_REMOTE_CODE_MODELS = {
    "jinaai/jina-embeddings-v2-base-code",
    "jinaai/jina-embeddings-v2-small-en",
    "nomic-ai/nomic-embed-code",
    "nomic-ai/nomic-embed-text-v1",
    "nomic-ai/nomic-embed-text-v1.5",
}


class SentenceTransformerEmbedding(EmbeddingPort):
    """Embedding service backed by sentence-transformers.

    Model is loaded lazily on first use (~2s cold start, ~200MB RAM).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None
        self._batch_size = 32  # updated after load with EMBED_BATCH_SIZE
        prefixes = _TASK_PREFIX_MODELS.get(model_name, ("", ""))
        self._query_prefix, self._doc_prefix = prefixes
        self._trust_remote = model_name in _TRUST_REMOTE_CODE_MODELS
        self._load_lock = threading.Lock()

    def _load_model(self):
        # Fast path — model already loaded (no lock needed for a read).
        if self._model is not None:
            return
        with self._load_lock:
            # Re-check inside the lock: another thread may have loaded while we waited.
            if self._model is None:
                from rag_server.config import DEVICE, EMBED_BATCH_SIZE
                device = _resolve_device()
                logger.info("Loading embedding model: %s (device=%s, batch_size=%d)",
                            self._model_name, DEVICE, EMBED_BATCH_SIZE)
                from sentence_transformers import SentenceTransformer
                kwargs: dict = {"device": device}
                if self._trust_remote:
                    kwargs["trust_remote_code"] = True
                try:
                    self._model = SentenceTransformer(self._model_name, local_files_only=True, **kwargs)
                except Exception:
                    # Model not cached locally — download on first use, then enforce local-only.
                    logger.info("Model not cached locally, downloading: %s", self._model_name)
                    self._model = SentenceTransformer(self._model_name, **kwargs)
                self._batch_size = EMBED_BATCH_SIZE
                # Don't call self.dimensions() here — it calls _load_model() which
                # tries to re-acquire _load_lock, deadlocking since this is non-reentrant.
                get_dim = getattr(self._model, "get_embedding_dimension",
                                  self._model.get_sentence_embedding_dimension)
                logger.info("Model loaded. Dimensions: %d", get_dim())

    @property
    def is_loaded(self) -> bool:
        """Check if the model has been loaded without triggering a load."""
        return self._model is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        if self._doc_prefix:
            texts = [self._doc_prefix + t for t in texts]
        embeddings = self._model.encode(texts, show_progress_bar=False, batch_size=self._batch_size)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        self._load_model()
        if self._query_prefix:
            text = self._query_prefix + text
        embedding = self._model.encode(text, show_progress_bar=False, batch_size=self._batch_size)
        return embedding.tolist()

    def dimensions(self) -> int:
        self._load_model()
        get_dim = getattr(self._model, "get_embedding_dimension",
                          self._model.get_sentence_embedding_dimension)
        return get_dim()


class OnnxDirectMLEmbedding(EmbeddingPort):
    """ONNX Runtime DirectML embedding — any DirectX 12 GPU without torch version constraints.

    Works on Intel HD/UHD/Iris/Xe integrated, AMD Radeon integrated, and any DX12 GPU.
    No conflict with CUDA torch versions. Falls back to CPU if DML is unavailable.

    Requires: pip install onnxruntime-directml optimum
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._ort_model = None
        self._tokenizer = None
        self._dim: int | None = None
        self._load_lock = threading.Lock()
        prefixes = _TASK_PREFIX_MODELS.get(model_name, ("", ""))
        self._query_prefix, self._doc_prefix = prefixes

    @property
    def is_loaded(self) -> bool:
        return self._ort_model is not None

    def _load_model(self):
        if self._ort_model is not None:
            return
        with self._load_lock:
            if self._ort_model is not None:
                return
            logger.info("Loading ONNX DirectML model: %s", self._model_name)
            try:
                from optimum.onnxruntime import ORTModelForFeatureExtraction
                from transformers import AutoTokenizer
                self._ort_model = ORTModelForFeatureExtraction.from_pretrained(
                    self._model_name,
                    export=True,
                    provider="DmlExecutionProvider",
                )
                logger.info("ONNX DirectML model loaded (DmlExecutionProvider)")
            except Exception as e:
                logger.warning("DirectML unavailable (%s) — falling back to CPU ONNX", e)
                from optimum.onnxruntime import ORTModelForFeatureExtraction
                self._ort_model = ORTModelForFeatureExtraction.from_pretrained(
                    self._model_name,
                    export=True,
                    provider="CPUExecutionProvider",
                )
                logger.info("ONNX model loaded (CPUExecutionProvider)")
            from transformers import AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)

    def _mean_pool(self, token_embeddings, attention_mask):
        import numpy as np
        mask = attention_mask[:, :, None].astype(float)
        summed = (token_embeddings * mask).sum(axis=1)
        counts = mask.sum(axis=1).clip(min=1e-9)
        embeddings = summed / counts
        # L2 normalise
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True).clip(min=1e-9)
        return (embeddings / norms).tolist()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        import numpy as np
        inputs = self._tokenizer(texts, padding=True, truncation=True,
                                  return_tensors="np", max_length=512)
        outputs = self._ort_model(**inputs)
        token_embeddings = outputs.last_hidden_state
        return self._mean_pool(token_embeddings, inputs["attention_mask"])

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        if self._doc_prefix:
            texts = [self._doc_prefix + t for t in texts]
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        self._load_model()
        if self._query_prefix:
            text = self._query_prefix + text
        return self._encode([text])[0]

    def dimensions(self) -> int:
        self._load_model()
        if self._dim is None:
            self._dim = self._ort_model.config.hidden_size
        return self._dim
