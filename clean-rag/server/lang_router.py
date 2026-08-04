"""Dynamic language-based embedding model routing.

Detects the dominant programming language in a project at index time and
selects the best embedding model for that language family.

  CSN family   (Python, JS, TS, Java, Go, PHP, Ruby) -> CodeRankEmbed 137M
  Systems      (C#, Rust, Kotlin, Swift, C, C++)     -> SFR-Code 400M (COIR #1)
  Broad        (30+ others: Scala, Haskell, Lua ...) -> jina-v2-base-code 161M
  Fallback     (unknown / exotic)                    -> StarEncoder 137M (86 langs)

Text/doc files (.md, .rst, .txt, PDF) do not influence language selection --
they are embedded with whatever model the project's code selects.

Ported from mcp-rag-server/src/rag_server/indexing/lang_router.py.
"""

from __future__ import annotations

import gc
import logging
import threading
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language families
# ---------------------------------------------------------------------------

#: CodeSearchNet family -- CodeRankEmbed fine-tuned on exactly these languages.
CSN_FAMILY: frozenset[str] = frozenset({
    "python", "javascript", "typescript", "java", "go", "php", "ruby",
})

#: Systems/compiled languages -- SFR-Embedding-Code-400M_R (COIR #1) excels here.
SFR_FAMILY: frozenset[str] = frozenset({
    "csharp", "rust", "kotlin", "swift", "c", "cpp",
})

#: Broad coverage -- jina-embeddings-v2-base-code supports 30 languages.
JINA_FAMILY: frozenset[str] = frozenset({
    "scala", "haskell", "lua", "bash", "shell", "sql", "r", "dart",
    "elixir", "erlang", "perl", "powershell", "groovy", "objective-c",
    "clojure", "fortran", "matlab", "coffeescript", "verilog", "vhdl",
    "prolog", "ocaml", "fsharp", "scheme", "racket", "crystal",
    "nim", "zig", "asm", "assembly",
})

#: Doc/config languages excluded from dominant-language detection.
#:
#: "unknown" belongs here even though it is not a language. indexing.py buckets
#: every extension missing from edge_extraction._EXT_TO_LANG under that name,
#: and that map only covers 24 code extensions, so .html, .yml, .cshtml, .json,
#: .xml, .md, .sql and .css all land in it. Without this entry that bucket wins
#: the vote on any project with a lot of markup and config: Nectar counted 3138
#: "unknown" against 1323 real csharp files and routed to the fallback model
#: instead of the C# one. Excluding it means the vote is decided only by files
#: whose language is actually known, which is what the vote was ever for.
#: Languages that support an application without being what it is written in:
#: markup, styling, config, schemas, build files, query and template files.
#:
#: These do NOT win the dominant language vote while any application language
#: is present, because the vote decides one thing, which embedding model the
#: whole project gets, and that should follow the code. Measured failures:
#: python 10 / sql 100 routed to jina instead of CodeRankEmbed; csharp 50 /
#: proto 200 routed to CodeRankEmbed instead of SFR; rust 30 / starlark 150
#: the same way.
#:
#: They are NOT banned from the vote though, only deprioritised. A schema only
#: repo, a Vue component library, a protobuf contracts repo all really exist,
#: and for those the supporting language IS the language. See
#: detect_dominant_language: the second tier exists so those still route on
#: what they are made of rather than falling back.
#:
#: Most of these only became reachable when the extension map moved to
#: grep-ast. Before that they resolved to "unknown", which this set already
#: caught, so the swap did not create the hole, it revealed it.
#: This set has to be maintained by hand, and that is the accepted cost.
#:
#: An allowlist was tried instead (only languages in ROUTING_TABLE win tier 1)
#: to make the maintenance disappear. It made things worse: it treats every
#: language we have no model for as a supporting file, so one csharp file beat
#: 500 julia files and a Julia project got a C# tuned model. Application versus
#: supporting is a real distinction about what a FILE TYPE is for, and no
#: property of the routing table encodes it.
#:
#: The saving grace is scope. New markup, config and build FORMATS appear far
#: more slowly than new programming languages, so this list moves rarely. When
#: it does miss one, the symptom is a project routed on its config files, which
#: is how sql, vue, proto, starlark, scss, po and meson were each found.
SECONDARY_LANGUAGES: frozenset[str] = frozenset({
    # prose and docs
    "markdown", "text", "rst", "pdf", "org", "asciidoc",
    # config and data
    "json", "yaml", "toml", "xml", "ini", "properties", "csv", "tsv", "psv",
    "jsonnet",
    # localisation. A translated app has one catalogue per locale, so these
    # outnumber source files in any project that ships in more than a few
    # languages: measured, go 10 / po 50 routed on po.
    "po", "gettext",
    # markup, styling, templates
    "html", "css", "scss", "sass", "less", "cshtml", "vue", "svelte",
    "handlebars", "jinja2", "twig", "erb", "haml", "pug", "liquid", "mustache",
    # schemas and query
    "sql", "graphql", "proto", "thrift", "capnp",
    # build and infrastructure
    "starlark", "bazel", "cmake", "make", "makefile", "meson", "ninja",
    "dockerfile", "gomod", "gosum", "requirements", "gitignore",
    "gitattributes", "hcl", "terraform",
    # the bucket for anything the extension map cannot name
    "unknown",
})

#: Kept as the old name so nothing that imported it breaks. Same set.
DOC_LANGUAGES = SECONDARY_LANGUAGES

# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------

MODEL_CSN = "nomic-ai/CodeRankEmbed"
MODEL_SFR = "Salesforce/SFR-Embedding-Code-400M_R"
MODEL_JINA = "jinaai/jina-embeddings-v2-base-code"

#: Used when no known code language is present. Was bigcode/starencoder, which
#: is a gated HuggingFace repo: without accepted terms the config fetch 401s and
#: surfaces as "Can't load the configuration of 'bigcode/starencoder'", so the
#: fallback could never load and every project routed here silently fell through
#: to CODE_EMBEDDING_MODEL anyway. Naming that outcome directly is honest about
#: what actually runs, and it keeps the fallback on a model known to load here.
MODEL_FALLBACK = "nomic-ai/CodeRankEmbed"

ROUTING_TABLE: dict[str, str] = {
    **{lang: MODEL_CSN for lang in CSN_FAMILY},
    **{lang: MODEL_SFR for lang in SFR_FAMILY},
    **{lang: MODEL_JINA for lang in JINA_FAMILY},
}


def get_model_for_language(language: str) -> str:
    """Return the best embedding model ID for *language*.

    Falls back to MODEL_FALLBACK for languages not in the routing table.
    The lookup is case-insensitive.
    """
    return ROUTING_TABLE.get(language.lower(), MODEL_FALLBACK)


def detect_dominant_language(files_by_language: dict[str, int]) -> str | None:
    """Return the dominant CODE language in *files_by_language*.

    Doc/config languages (markdown, JSON, YAML, ...) are excluded so that a
    Python project with extensive README files still routes to CodeRankEmbed
    rather than a text model.

    Returns ``None`` if only doc/config files were found.
    """
    counts = {
        lang: count for lang, count in files_by_language.items() if count > 0
    }

    # First tier: everything that is real code, routable or not.
    #
    # This was briefly an allowlist (`lang in ROUTING_TABLE`), on the theory
    # that a language with no model cannot inform a choice between models. That
    # was wrong, and measurably so: it conflated "we have no model tuned for
    # this" with "this is a supporting file". Most of the languages with no
    # ROUTING_TABLE entry are real application languages, and under the
    # allowlist a SINGLE csharp file beat 500 julia files, sending a 99.8%
    # Julia project to a model tuned for C# and Rust. The denylist's answer,
    # julia wins and routes to the generalist fallback, is better.
    #
    # So the distinction that matters is application versus supporting, which
    # is genuine classification and cannot be derived from the routing table.
    # SECONDARY_LANGUAGES carries it, and it does need maintaining when a new
    # markup or build format appears. That is a real cost, accepted knowingly:
    # the set of supporting FORMATS is small and slow moving, while the
    # alternative silently mis-routes whole languages.
    application = {
        lang: n for lang, n in counts.items() if lang.lower() not in SECONDARY_LANGUAGES
    }
    if application:
        return max(application, key=lambda lang: application[lang])

    # Second tier: nothing but supporting languages, so one of them genuinely
    # IS the language. A migrations repo, a protobuf contracts repo, a Vue
    # component library. Excluding them outright here was a real regression:
    # a pure sql checkout stopped routing to the model sql maps to and got the
    # generic fallback instead.
    #
    # "unknown" is the exception, since it names nothing. It only wins when
    # there is literally nothing else, and get_model_for_project treats a None
    # return and an unroutable name the same way.
    nameable = {lang: n for lang, n in counts.items() if lang.lower() != "unknown"}
    if nameable:
        return max(nameable, key=lambda lang: nameable[lang])
    return None


def get_model_for_project(files_by_language: dict[str, int]) -> str:
    """Detect dominant language and return the best embedding model ID.

    Convenience wrapper over :func:`detect_dominant_language` +
    :func:`get_model_for_language`.
    """
    lang = detect_dominant_language(files_by_language)
    if lang is None:
        logger.debug("No code files detected -- using fallback model %s", MODEL_FALLBACK)
        return MODEL_FALLBACK
    model = get_model_for_language(lang)
    logger.info("Lang router: dominant_language=%r -> model=%s", lang, model)
    return model


# ---------------------------------------------------------------------------
# Model cache
# ---------------------------------------------------------------------------

class ModelCache:
    """Thread-safe lazy cache of embedding model instances keyed by model ID.

    Embedders are created on first request and reused on subsequent calls.
    Thread safety is per-slot: only one thread loads a given model at a time,
    but two different models can load concurrently.

    Usage::

        cache = ModelCache()
        embedder = cache.get("nomic-ai/CodeRankEmbed")
        vectors = embedder.embed(["def foo(): pass"])
    """

    #: How long a failed load is remembered before another attempt is allowed.
    #: A model load is expensive (roughly 10s warm, minutes cold) and a
    #: deterministic failure repeats exactly, so retrying it on every request
    #: turns one broken model into a request queue that never drains. Long
    #: enough to stop a hot loop, short enough that repairing the cache on disk
    #: takes effect without restarting the server.
    FAILURE_TTL_S: float = 60.0

    #: How many embedders may be resident at once. These are not small: 1069 MB
    #: for CodeRankEmbed (137M params) and 2161 MB for SFR (400M), measured, and
    #: embedding roughly doubles that at the activation peak. Holding two for no
    #: reason is 2 GB of nothing. One is the right default because a project is
    #: indexed with a single model and search embeds the query with that same
    #: one; a second slot only helps if two projects on different models are
    #: interleaved, which is a caller choosing to thrash.
    #:
    #: Eviction is LRU via OrderedDict.move_to_end + popitem(last=False), the
    #: recipe in the stdlib's own collections docs. functools.lru_cache does not
    #: fit: it has no eviction hook, so there is nowhere to drop a 2 GB model.
    #:
    #: Two, not one, because the server genuinely alternates: a search embeds
    #: its query with CODE_EMBEDDING_MODEL while indexing uses whatever the
    #: router picked for that project. At a cap of one those evict each other on
    #: every alternation, and reloading SFR costs 135 seconds, so a cap of one
    #: would turn a bounded cache into a thrashing one. Two holds that pair
    #: without letting all three routable models pile up. A batch job that
    #: processes one model group at a time should pass max_resident=1.
    DEFAULT_MAX_RESIDENT = 2

    def __init__(self, max_resident: int | None = None) -> None:
        self._cache: OrderedDict = OrderedDict()
        self._slot_locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._max_resident = max_resident or self.DEFAULT_MAX_RESIDENT
        #: model_id -> (failed_at_monotonic, exception). Consulted before a
        #: retry so a doomed load is attempted at most once per FAILURE_TTL_S.
        self._failures: dict[str, tuple[float, BaseException]] = {}

    def _slot_lock(self, model_id: str) -> threading.Lock:
        """Return (creating if needed) the per-model load lock."""
        with self._global_lock:
            if model_id not in self._slot_locks:
                self._slot_locks[model_id] = threading.Lock()
            return self._slot_locks[model_id]

    def get(self, model_id: str):
        """Return the embedder for *model_id*, loading it lazily.

        The first call for a given model_id triggers a download + load from
        HuggingFace (cached on disk after the first run). Subsequent calls
        return the cached instance immediately.

        If the requested model fails to load, logs a warning and falls back
        to CODE_EMBEDDING_MODEL so indexing continues rather than failing.
        """
        if model_id in self._cache:
            with self._global_lock:
                # Most recently used goes to the end; eviction pops the front.
                if model_id in self._cache:
                    self._cache.move_to_end(model_id)
            return self._cache[model_id]
        with self._slot_lock(model_id):
            if model_id not in self._cache:
                from .embedding import SentenceTransformerEmbedding
                from .config import CODE_EMBEDDING_MODEL

                # A recent failure short circuits before paying for the load
                # again. Without this, making the request handlers retry a
                # failed startup warmup (so the server can recover without a
                # restart) would mean every request re attempts a load that is
                # known to fail.
                recent = self._failures.get(model_id)
                if recent is not None:
                    failed_at, exc = recent
                    age = time.monotonic() - failed_at
                    if age < self.FAILURE_TTL_S:
                        logger.debug(
                            "ModelCache: %s failed %.0fs ago, not retrying for another %.0fs",
                            model_id, age, self.FAILURE_TTL_S - age,
                        )
                        raise exc
                    del self._failures[model_id]

                logger.info("ModelCache: loading %s", model_id)
                try:
                    emb = SentenceTransformerEmbedding(model_name=model_id)
                    # Force the lazy _load_model() now so any incompatibility
                    # surfaces here where we can catch it, rather than later
                    # inside embed().
                    emb.embed(["warmup"])
                    self._cache[model_id] = emb
                    self._failures.pop(model_id, None)
                    self._enforce_max_resident(keep=model_id)
                except Exception as exc:
                    self._failures[model_id] = (time.monotonic(), exc)
                    fallback = CODE_EMBEDDING_MODEL
                    if model_id != fallback:
                        logger.warning(
                            "ModelCache: %s failed to load (%s) -- falling back to %s",
                            model_id, exc, fallback,
                        )
                        # Load or reuse the fallback, then cache under both names
                        # so we never retry the failing model.
                        if fallback not in self._cache:
                            try:
                                fb_emb = SentenceTransformerEmbedding(model_name=fallback)
                                fb_emb.embed(["warmup"])
                            except Exception as fb_exc:
                                # Both the requested model and the fallback are
                                # down. Memoize the fallback too, or the next
                                # caller pays for both failed loads again.
                                self._failures[fallback] = (time.monotonic(), fb_exc)
                                raise
                            self._cache[fallback] = fb_emb
                            self._failures.pop(fallback, None)
                        self._cache[model_id] = self._cache[fallback]
                        # Serving from the fallback is a success for this id, so
                        # the cache hit at the top of get() takes over from here.
                        self._failures.pop(model_id, None)
                    else:
                        raise
        return self._cache[model_id]

    def _enforce_max_resident(self, keep: str | None = None) -> None:
        """Drop least recently used embedders until the cache fits.

        Callers must never reach into ``_cache`` to do this themselves: dropping
        a reference is only half of it, the collection afterwards is the half
        that matters, and a caller that forgets it leaks a whole model.
        """
        with self._global_lock:
            while len(self._cache) > self._max_resident:
                victim, _emb = self._cache.popitem(last=False)
                if victim == keep:
                    # Never evict the entry we were just asked for, even if the
                    # cap is 0 or 1. Put it back and stop.
                    self._cache[victim] = _emb
                    self._cache.move_to_end(victim)
                    break
                logger.info("ModelCache: evicting %s to stay within %d resident",
                            victim, self._max_resident)
                del _emb
        # Outside the lock: gc can be slow and holds nothing anyone needs.
        gc.collect()

    def evict(self, model_id: str) -> bool:
        """Drop one embedder. True if it was resident."""
        with self._global_lock:
            emb = self._cache.pop(model_id, None)
        if emb is None:
            return False
        del emb
        gc.collect()
        logger.info("ModelCache: evicted %s", model_id)
        return True

    def evict_all(self) -> None:
        """Drop every embedder.

        torch does not hand CPU memory back, so this does not return RSS to
        where it started (measured: 2161 MB settles to ~1752 MB after dropping
        SFR). It frees what can be freed; bounding the rest is the caller's job,
        by not living forever.
        """
        with self._global_lock:
            victims = list(self._cache.keys())
            self._cache.clear()
        for _ in range(2):
            gc.collect()
        if victims:
            logger.info("ModelCache: evicted all (%s)", ", ".join(victims))

    def loaded_models(self) -> list[str]:
        """Return model IDs that have been instantiated."""
        return list(self._cache.keys())

    def warmed_models(self) -> list[str]:
        """Return model IDs whose underlying model is fully loaded into memory."""
        return [mid for mid, emb in self._cache.items() if emb.is_loaded]

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, model_id: str) -> bool:
        return model_id in self._cache
