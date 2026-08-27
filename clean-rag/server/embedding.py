"""Embedding service using sentence-transformers. Lazy-loaded singleton.

Extracted from ClaudeBoost mcp-rag-server (self-contained, no external imports).
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"

# Task-specific prefixes: (query_prefix, document_prefix)
# Required for asymmetric retrieval models.
_TASK_PREFIX_MODELS = {
    "BAAI/bge-base-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "BAAI/bge-large-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "BAAI/bge-small-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
    "nomic-ai/CodeRankEmbed": ("search_query: ", "search_document: "),
}

# Models that require trust_remote_code=True.
#
# Every model the language router can select must be listed here if it ships a
# custom architecture, or it fails to load and silently falls back. SFR was
# missing: it is built on Alibaba-NLP/new-impl and raises "Please pass the
# argument `trust_remote_code=True`" from AutoConfig, which is the model the
# router hands every C# project. Keep this in sync with lang_router's routing
# table, not with whichever model happened to be tested last.
_TRUST_REMOTE_CODE_MODELS: set[str] = {
    "nomic-ai/CodeRankEmbed",
    "jinaai/jina-embeddings-v2-base-code",
    "Salesforce/SFR-Embedding-Code-400M_R",
}


_thread_cap_applied = False
_thread_cap_lock = threading.Lock()


def _apply_torch_thread_cap() -> None:
    """Cap torch's intra op thread pool before any model loads.

    torch otherwise takes every core it can see, which is what made a rebuild
    lock up the whole machine. This is the structural half of the CPU budget:
    it holds continuously, including inside a single long embed call, where the
    sweep's between files sampling cannot see anything.

    Must run before the first torch operation to take effect reliably, and only
    once: calling set_num_threads while work is in flight is not safe.
    """
    global _thread_cap_applied
    if _thread_cap_applied:
        return
    with _thread_cap_lock:
        if _thread_cap_applied:
            return
        try:
            import torch

            from server.config import TORCH_THREADS

            torch.set_num_threads(TORCH_THREADS)
            # The inter op pool raises RuntimeError once parallel work has
            # started, so it is best effort and must not take the cap down
            # with it.
            try:
                torch.set_num_interop_threads(max(1, TORCH_THREADS // 2))
            except RuntimeError:
                pass
            logger.info(
                "Capped torch to %d of %d cores", TORCH_THREADS, os.cpu_count() or 1,
            )
        except Exception:
            logger.warning("Could not cap torch threads", exc_info=True)
        _thread_cap_applied = True


def _repair_snapshot(model_name: str) -> None:
    """Fetch anything missing from *model_name*'s cached snapshot.

    Best effort. A failure here must not stop the load attempt that follows,
    because the cache may already be good enough and the network may simply be
    down; let the real load decide.

    Deliberately not gated on a completeness pre check. huggingface_hub 0.36.2
    has no API for "is this snapshot complete": scan_cache_dir() reports what is
    on disk, not what is missing versus the remote, and it treats a snapshot
    with valid symlinks and fewer files than the repo as healthy, which is
    precisely the corruption seen here. Calling snapshot_download and letting it
    reconcile IS the check at this version.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return
    try:
        snapshot_download(repo_id=model_name)
        logger.info("Snapshot for %s reconciled against the remote file list", model_name)
    except Exception as exc:
        logger.warning(
            "Could not reconcile the snapshot for %s (%s: %s); trying the load anyway",
            model_name, type(exc).__name__, exc,
        )


class SentenceTransformerEmbedding:
    """Embedding service backed by sentence-transformers.

    Model is loaded lazily on first use (~2s cold start, ~200MB RAM).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None
        self._batch_size = 32
        prefixes = _TASK_PREFIX_MODELS.get(model_name, ("", ""))
        self._query_prefix, self._doc_prefix = prefixes
        self._trust_remote = model_name in _TRUST_REMOTE_CODE_MODELS
        self._load_lock = threading.Lock()

    def _load_model(self):
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is None:
                from server.config import DEVICE, EMBED_BATCH_SIZE
                logger.info("Loading embedding model: %s (device=%s)", self._model_name, DEVICE)
                _apply_torch_thread_cap()
                from sentence_transformers import SentenceTransformer
                kwargs: dict = {"device": DEVICE}
                if self._trust_remote:
                    kwargs["trust_remote_code"] = True
                # Offline first, fall back to download.
                #
                # The retry must trigger on ValueError as well as OSError. A
                # partially downloaded snapshot (model weights present, tokenizer
                # files missing) does not raise OSError: transformers falls back
                # to resolving the tokenizer class from the model config, and for
                # a custom architecture that is not in TOKENIZER_MAPPING it raises
                # "ValueError: Unrecognized configuration class ... to build an
                # AutoTokenizer". Catching only OSError let that escape, so the
                # download retry never ran and nomic-ai/CodeRankEmbed failed every
                # load for three days while the server reported "warming_up".
                # transformers raises ValueError for the local_files_only cache
                # miss case generally (huggingface/transformers#9147), so this is
                # the documented type, not a workaround for one model.
                try:
                    self._model = SentenceTransformer(
                        self._model_name, local_files_only=True, **kwargs
                    )
                except NotImplementedError as meta_exc:
                    # "Cannot copy out of meta tensor; no data!" Weights were
                    # left on the meta device and .to(device) cannot move them.
                    #
                    # This is huggingface/transformers#41782, still open, and
                    # it fires when two model loads run in different threads at
                    # once. ModelCache._construct_lock now serializes every
                    # construction in the server, so this should not be
                    # reachable from that path any more. It stays because this
                    # class is importable on its own: nothing stops another
                    # caller from building two of these on two threads without
                    # going through ModelCache.
                    #
                    # A plain retry, NOT the _repair_snapshot path below. The
                    # cache is not damaged here, the race is, so re downloading
                    # several GB would cost minutes and fix nothing.
                    if "meta tensor" not in str(meta_exc):
                        raise
                    logger.warning(
                        "Model %s hit the meta tensor load race (%s). Retrying "
                        "the load once.",
                        self._model_name, meta_exc,
                    )
                    self._model = SentenceTransformer(
                        self._model_name, local_files_only=True, **kwargs
                    )
                except (OSError, ValueError) as first_exc:
                    logger.warning(
                        "Model %s failed to load from cache (%s: %s). Re downloading "
                        "from HuggingFace (~1 min).",
                        self._model_name, type(first_exc).__name__, first_exc,
                    )
                    # Reconcile the whole snapshot against the repo's real file
                    # list first. This is the actual repair, and it is stronger
                    # than force_download because it needs no guess about WHICH
                    # files are missing: it fetches the repo's tree and pulls
                    # whatever is absent, resumably and idempotently.
                    #
                    # It matters because a partial cache is the expected case,
                    # not a freak one. sentence-transformers 3.4.1 fetches each
                    # config file individually through util.load_file_path,
                    # whose body is `try: hf_hub_download(...) except Exception:
                    # return None`. Any interruption during the tokenizer fetch
                    # is swallowed silently and leaves exactly the weights
                    # present, tokenizer missing shape that wedged this server
                    # for three days.
                    _repair_snapshot(self._model_name)

                    try:
                        # Belt and braces behind the preflight: if the snapshot
                        # is complete but a cached file is corrupt, only
                        # force_download refetches it, since snapshot_download
                        # trusts a file whose metadata already matches.
                        # SentenceTransformer has no top level force_download
                        # parameter, so it has to go through all three kwargs
                        # dicts it forwards; passing it directly raises
                        # TypeError, and passing only model_kwargs would miss
                        # the tokenizer, which is the part actually missing.
                        forced = {"force_download": True}
                        self._model = SentenceTransformer(
                            self._model_name,
                            local_files_only=False,
                            model_kwargs=forced,
                            tokenizer_kwargs=forced,
                            config_kwargs=forced,
                            **kwargs,
                        )
                    except Exception as e:
                        logger.exception(
                            "Failed to download/load model %s: %s: %s",
                            self._model_name, type(e).__name__, e,
                        )
                        raise
                self._batch_size = EMBED_BATCH_SIZE
                get_dim = getattr(
                    self._model, "get_embedding_dimension",
                    self._model.get_sentence_embedding_dimension,
                )
                logger.info("Model loaded. Dimensions: %d", get_dim())

    @property
    def model_name(self) -> str:
        """The HuggingFace id of the model backing this embedder.

        Search compares this against the model recorded in a project's manifest
        so it can refuse to answer from an index built in a different embedding
        space.
        """
        return self._model_name

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        if self._doc_prefix:
            texts = [self._doc_prefix + t for t in texts]
        embeddings = self._model.encode(
            texts, show_progress_bar=False, batch_size=self._batch_size
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        self._load_model()
        if self._query_prefix:
            text = self._query_prefix + text
        embedding = self._model.encode(
            text, show_progress_bar=False, batch_size=self._batch_size
        )
        return embedding.tolist()

    def dimensions(self) -> int:
        self._load_model()
        get_dim = getattr(
            self._model, "get_embedding_dimension",
            self._model.get_sentence_embedding_dimension,
        )
        return get_dim()

    @property
    def max_tokens(self) -> int:
        """The model's real max sequence length (e.g. 512 for bge-base).

        Text longer than this is silently truncated at encode time, so it's
        the hard ceiling the docs chunker must keep every chunk under.
        """
        self._load_model()
        return self._model.max_seq_length

    def count_tokens(self, text: str) -> int:
        """Real subword token count for `text`, using the model's own
        tokenizer and including the special tokens (`[CLS]`/`[SEP]`) the
        encoder always adds.

        The docs chunker uses this instead of the 4-chars-per-token estimate,
        which under-counts dense legal text (measured ~3.7 chars/token on real
        eCFR regulation prose) and let oversized chunks slip past the guard.
        The document prefix, if any, is included so the count matches what
        embed() actually encodes.
        """
        self._load_model()
        measured = (self._doc_prefix + text) if self._doc_prefix else text
        return len(self._model.tokenizer(measured)["input_ids"])
