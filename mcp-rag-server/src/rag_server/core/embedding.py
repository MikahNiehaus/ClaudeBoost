"""Embedding service using sentence-transformers. Lazy-loaded singleton."""

import logging
import threading
from typing import Union

from rag_server.ports.embedding_port import EmbeddingPort

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"

# Minimum texts in a batch before splitting across GPU + CPU in parallel.
# Below this, thread-spawn overhead outweighs the speedup.
_CPU_GPU_SPLIT_THRESHOLD = 8


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
    "nomic-ai/CodeRankEmbed",
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
                # Offline first — a cached load is fast and skips a network HEAD on every
                # start. If the cache is missing or partial (fresh install, interrupted
                # download, a swapped model that was never fetched), fall back to an online
                # load so the model self-heals instead of cascading into HTTP 500s on every
                # /index and silent 0-result searches. FileNotFoundError (which
                # LocalEntryNotFoundError subclasses) and the offline OSError both land here.
                try:
                    logger.info("Loading embedding model (offline): %s", self._model_name)
                    self._model = SentenceTransformer(self._model_name, local_files_only=True, **kwargs)
                except OSError:
                    logger.warning(
                        "Embedding model %s not in local cache — downloading once from "
                        "HuggingFace (needs internet, ~1 min). Later loads stay offline.",
                        self._model_name,
                    )
                    self._model = SentenceTransformer(self._model_name, local_files_only=False, **kwargs)
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

    def embed(self, texts: list[str], *, language: str | None = None) -> list[list[float]]:  # noqa: ARG002
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

    Uses pre-exported ONNX models from ~/.cache/rag-onnx/<model-name>/model.onnx.
    Requires: pip install onnxruntime-directml
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._ort_model = None
        self._cpu_model = None       # parallel CPU-only session (created when DML is active)
        self._has_dml = False        # True when DmlExecutionProvider loaded successfully
        self._gpu_fraction = 0.5     # fraction of large batches routed to GPU (calibrated at load)
        self._tokenizer = None
        self._dim: int | None = None
        self._load_lock = threading.Lock()
        self._input_names: set[str] = set()  # ONNX model expected input names
        prefixes = _TASK_PREFIX_MODELS.get(model_name, ("", ""))
        self._query_prefix, self._doc_prefix = prefixes

    @property
    def is_loaded(self) -> bool:
        return self._ort_model is not None

    def _resolve_onnx_path(self) -> str:
        import pathlib, os
        cache_dir = (
            pathlib.Path(os.path.expanduser("~"))
            / ".cache" / "rag-onnx"
            / self._model_name.replace("/", "--")
        )
        onnx_path = cache_dir / "model.onnx"
        if not onnx_path.exists():
            logger.info(
                "ONNX model not found at %s — exporting now (one-time, ~1-2 min)…",
                onnx_path,
            )
            self._export_onnx(cache_dir, onnx_path)
        return str(onnx_path)

    def _export_onnx(self, cache_dir, onnx_path) -> None:
        """Export the HuggingFace model to ONNX format.

        Uses a wrapper module so torch.onnx.export receives explicit positional args
        instead of **kwargs, which avoids the 'multiple values for argument' TorchScript
        tracing error that occurs with newer transformers BertModel signatures.
        """
        import torch
        import torch.nn as nn
        from transformers import AutoModel, AutoTokenizer

        cache_dir.mkdir(parents=True, exist_ok=True)

        class _OnnxWrapper(nn.Module):
            def __init__(self, bert):
                super().__init__()
                self.bert = bert

            def forward(self, input_ids, attention_mask, token_type_ids):
                out = self.bert(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                    return_dict=False,
                )
                return out[0], out[1]  # last_hidden_state, pooler_output

        logger.info("Loading base model for ONNX export: %s", self._model_name)
        bert = AutoModel.from_pretrained(self._model_name)
        tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        bert.eval()
        wrapper = _OnnxWrapper(bert)
        wrapper.eval()

        enc = tokenizer(
            ["export calibration"],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=64,
        )
        dummy = (
            enc["input_ids"],
            enc["attention_mask"],
            enc.get("token_type_ids", torch.zeros_like(enc["input_ids"])),
        )
        dynamic_axes = {
            "input_ids":         {0: "batch", 1: "seq"},
            "attention_mask":    {0: "batch", 1: "seq"},
            "token_type_ids":    {0: "batch", 1: "seq"},
            "last_hidden_state": {0: "batch", 1: "seq"},
            "pooler_output":     {0: "batch"},
        }

        import warnings
        with torch.no_grad(), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            torch.onnx.export(
                wrapper,
                dummy,
                str(onnx_path),
                input_names=["input_ids", "attention_mask", "token_type_ids"],
                output_names=["last_hidden_state", "pooler_output"],
                dynamic_axes=dynamic_axes,
                opset_version=14,
                do_constant_folding=True,
                dynamo=False,
            )

        size_mb = onnx_path.stat().st_size / 1024 / 1024
        logger.info("ONNX export complete: %s (%.0f MB)", onnx_path, size_mb)

    def _load_model(self):
        if self._ort_model is not None:
            return
        with self._load_lock:
            if self._ort_model is not None:
                return
            logger.info("Loading ONNX DirectML model: %s", self._model_name)
            import onnxruntime as ort

            onnx_path = self._resolve_onnx_path()
            available = ort.get_available_providers()

            try:
                if "DmlExecutionProvider" not in available:
                    raise RuntimeError("DmlExecutionProvider not in available providers")
                self._ort_model = ort.InferenceSession(
                    onnx_path,
                    providers=["DmlExecutionProvider", "CPUExecutionProvider"],
                )
                if self._ort_model.get_providers()[0] != "DmlExecutionProvider":
                    raise RuntimeError(
                        f"DML provider not active, got: {self._ort_model.get_providers()[0]}"
                    )
                self._has_dml = True
                # Parallel CPU session — shares the same ONNX file, no re-export needed.
                self._cpu_model = ort.InferenceSession(
                    onnx_path,
                    providers=["CPUExecutionProvider"],
                )
                logger.info("ONNX model loaded — GPU: DmlExecutionProvider + CPU session ready")
            except Exception as e:
                logger.warning("DirectML unavailable (%s) — falling back to CPU ONNX", e)
                self._ort_model = ort.InferenceSession(
                    onnx_path,
                    providers=["CPUExecutionProvider"],
                )
                self._has_dml = False
                self._cpu_model = None
                logger.info(
                    "ONNX model loaded (%s)", self._ort_model.get_providers()[0]
                )

            from transformers import AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)

            # Cache expected input names to filter tokenizer output safely.
            self._input_names = {inp.name for inp in self._ort_model.get_inputs()}

            # Resolve hidden dimension via a minimal test inference.
            import numpy as _np
            test_enc = self._tokenizer(["d"], return_tensors="np", max_length=4)
            # Export uses return_tensors="pt", which is always int64. return_tensors="np"
            # can hand back int32 depending on the tokenizers backend/padding path — cast
            # explicitly so the dtype always matches what the ONNX graph was traced with.
            test_in = {k: v.astype(_np.int64) for k, v in dict(test_enc).items() if k in self._input_names}
            # RoBERTa tokenizers don't produce token_type_ids; the ONNX export wrapper
            # always includes it as a required input — fill with zeros when absent.
            if "token_type_ids" in self._input_names and "token_type_ids" not in test_in:
                test_in["token_type_ids"] = _np.zeros_like(test_in["input_ids"])
            out = self._ort_model.run(["last_hidden_state"], test_in)
            self._dim = out[0].shape[2]
            logger.info("ONNX model ready. Dimensions: %d", self._dim)

            if self._has_dml and self._cpu_model is not None:
                self._calibrate_split()

    def _calibrate_split(self) -> None:
        """Benchmark GPU vs CPU to set the optimal batch-split fraction.

        Runs 1 warm-up + 2 timed passes on each session with a small batch.
        GPU fraction = gpu_tps / (gpu_tps + cpu_tps), clamped to [0.2, 0.9].

        This adapts automatically:
        - Powerful discrete GPU (NVIDIA, AMD RX) → ~75-85% GPU
        - Weak integrated GPU (Intel UHD, AMD integrated) → ~40-55% GPU
        - GPU barely faster than CPU → ~50% GPU
        """
        import time
        import numpy as _np_cal
        bench_enc = self._tokenizer(
            ["Calibration sentence for throughput measurement."] * 4,
            padding=True, truncation=True, return_tensors="np", max_length=64,
        )
        bench = {k: v.astype(_np_cal.int64) for k, v in dict(bench_enc).items() if k in self._input_names}
        if "token_type_ids" in self._input_names and "token_type_ids" not in bench:
            bench["token_type_ids"] = _np_cal.zeros_like(bench["input_ids"])

        def _tps(session) -> float:
            session.run(["last_hidden_state"], bench)  # warm-up (first DML call has JIT overhead)
            times = []
            for _ in range(2):
                t = time.perf_counter()
                session.run(["last_hidden_state"], bench)
                times.append(time.perf_counter() - t)
            return 4.0 / min(times)  # texts/sec (best of 2 runs)

        try:
            gpu_tps = _tps(self._ort_model)
            cpu_tps = _tps(self._cpu_model)

            if cpu_tps >= gpu_tps:
                # CPU is faster than the GPU (common on integrated graphics / weak DX12 adapters).
                # Drop the DML session entirely — no split, no dual-session RAM cost.
                import gc
                logger.info(
                    "GPU/CPU calibration — CPU: %.0f t/s beats GPU: %.0f t/s → "
                    "releasing DML session, running CPU-only ONNX",
                    cpu_tps, gpu_tps,
                )
                _dml_sess = self._ort_model   # hold reference until after swap
                self._ort_model = self._cpu_model
                self._cpu_model = None
                self._has_dml = False
                del _dml_sess                 # release DML session memory
                gc.collect()
                return

            total = gpu_tps + cpu_tps
            self._gpu_fraction = max(0.2, min(0.9, gpu_tps / total))
            logger.info(
                "GPU/CPU calibration — GPU: %.0f t/s, CPU: %.0f t/s → GPU gets %.0f%% of each batch",
                gpu_tps, cpu_tps, self._gpu_fraction * 100,
            )
        except Exception as e:
            logger.warning("GPU/CPU calibration failed (%s) — using 50/50 split", e)
            self._gpu_fraction = 0.5

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
        enc = self._tokenizer(texts, padding=True, truncation=True,
                              return_tensors="np", max_length=512)
        # Cast to int64 to match the dtype the ONNX graph was exported with
        # (export uses return_tensors="pt", always int64; "np" can be int32).
        inputs = {k: v.astype(np.int64) for k, v in dict(enc).items() if k in self._input_names}
        # RoBERTa tokenizers omit token_type_ids; pad with zeros when ONNX model needs them.
        if "token_type_ids" in self._input_names and "token_type_ids" not in inputs:
            inputs["token_type_ids"] = np.zeros_like(inputs["input_ids"])

        if self._cpu_model is not None and len(texts) >= _CPU_GPU_SPLIT_THRESHOLD:
            # Split batch: GPU gets _gpu_fraction (calibrated to relative throughput),
            # CPU gets the remainder — both run simultaneously via thread pool.
            from concurrent.futures import ThreadPoolExecutor
            mid = max(1, round(len(texts) * self._gpu_fraction))
            gpu_in = {k: v[:mid] for k, v in inputs.items()}
            cpu_in = {k: v[mid:] for k, v in inputs.items()}

            def _run(session, inp):
                return np.asarray(session.run(["last_hidden_state"], inp)[0])

            with ThreadPoolExecutor(max_workers=2) as pool:
                f_gpu = pool.submit(_run, self._ort_model, gpu_in)
                f_cpu = pool.submit(_run, self._cpu_model, cpu_in)
                token_embeddings = np.concatenate([f_gpu.result(), f_cpu.result()], axis=0)
        else:
            out = self._ort_model.run(["last_hidden_state"], inputs)
            token_embeddings = np.asarray(out[0])

        return self._mean_pool(token_embeddings, enc["attention_mask"])

    def embed(self, texts: list[str], *, language: str | None = None) -> list[list[float]]:  # noqa: ARG002
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
        return self._dim
