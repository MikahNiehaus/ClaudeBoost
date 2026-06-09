"""CodeSearchNet Multi-Language 1K-Pool Benchmark

Runs the official 1K-pool evaluation protocol (Husain et al. 2019,
arxiv:1909.09436) across Python, JavaScript, Java, Go, Ruby, PHP, and C#.

Per-language model routing selects the best embedding model and preprocessing
strategy per language via best_model_config.json (written by the improvement loop).

Published baselines (from CodeBERT and GraphCodeBERT papers, 1K-pool):
    Language     NBoW    CodeBERT  GraphCodeBERT  UniXcoder
    Python       0.651   0.713     0.769          0.791
    JavaScript   0.502   0.629     0.674          0.681
    Java         0.643   0.719     0.769          0.806
    Go           0.845   0.921     0.897          0.910
    Ruby         0.562   0.678     0.703          0.728
    PHP          0.610   0.630     0.649          0.665

Note on C#: CodeSearchNet has no official C# split.
    Benchmark uses /// XML doc comment pairs extracted from popular open-source
    C# libraries (Newtonsoft.Json, AutoMapper, Polly, FluentValidation, Dapper,
    etc.). Run: python scripts/download_csharp_github.py

Preprocessing (per language):
    Python:     AST-based docstring stripping (exact, canonical form)
    Go:         Strip leading // line comment block (godoc style)
    Ruby:       Strip leading # comment lines + =begin...=end blocks
    JS/Java/PHP/C#: Strip leading /* */ or /** */ block comment
    All non-Python: prepend function name before code (S6 strategy)
    C#:             XML doc extraction (summary/param/returns from raw code) + name doubling
                    (docaug strategy) using BAAI/bge-base-en-v1.5 — MRR 0.8038, R@1 72.4%

Score fusion (JS, R3):
    3-way: codesearch*0.20 + bge_base_s6*0.40 + bge_base_camel_split*0.40 = MRR 0.8009
    Config stored in best_model_config.json under "fusion" key per language.
    _get_embeddings() returns list[(ce, de, weight)] when fusion config exists;
    _run_mrr() dispatches to _pool_mrr_recall_fused() automatically.

Run:
    python scripts/download_codesearchnet_full.py --lang all
    python scripts/download_csharp_github.py
    pytest mcp-rag-server/tests/test_codesearchnet_multilang.py -v -s
"""

import ast
import json
import random
import re
import time
import warnings
from pathlib import Path

import numpy as np
import pytest

try:
    from sentence_transformers import SentenceTransformer
    HAS_ST = True
except ImportError:
    HAS_ST = False

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DATA_DIR = Path(__file__).parent / "data"
CACHE_DIR = DATA_DIR
MODEL_CACHE_DIR = DATA_DIR / "model_caches"
N_POOL = 1000
RANDOM_SEED = 42

LANGUAGES = ["python", "javascript", "java", "go", "ruby", "php", "csharp"]

# Per-language model routing — populated from best_model_config.json when available.
# Benchmark scripts (benchmark_models.py) write this file after testing all models.
# Falls back to MODEL_NAME (all-MiniLM-L6-v2) for any language not in the config.
_MODEL_CONFIG_PATH = DATA_DIR / "best_model_config.json"
_MODEL_FOR_LANG: dict[str, str] = {}
_MODEL_KEY_FOR_LANG: dict[str, str] = {}
_STRATEGY_FOR_LANG: dict[str, str] = {}
_FUSION_FOR_LANG: dict[str, dict] = {}

try:
    if _MODEL_CONFIG_PATH.exists():
        _raw = json.loads(_MODEL_CONFIG_PATH.read_text(encoding="utf-8"))
        _MODEL_FOR_LANG     = {lang: info["model"]                    for lang, info in _raw.items()}
        _MODEL_KEY_FOR_LANG = {lang: info.get("model_key", "custom")  for lang, info in _raw.items()}
        _STRATEGY_FOR_LANG  = {lang: info.get("strategy", "")         for lang, info in _raw.items()}
        _FUSION_FOR_LANG    = {lang: info["fusion"]
                               for lang, info in _raw.items() if "fusion" in info}
except Exception:
    pass


def _model_for_lang(lang: str) -> str:
    return _MODEL_FOR_LANG.get(lang, MODEL_NAME)


def _strategy_for_lang(lang: str) -> str:
    return _STRATEGY_FOR_LANG.get(lang, "")


# ---------------------------------------------------------------------------
# Docstring / doc-comment stripping (per language)
# ---------------------------------------------------------------------------

def _strip_docstring_python(code: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if (node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    node.body.pop(0)
                    if not node.body:
                        node.body.append(ast.Pass())
        return ast.unparse(tree)
    except SyntaxError:
        return code


def _python_extract_sig(node) -> str:
    """Reconstruct 'def name(params) -> return:' from an AST FunctionDef node."""
    args = node.args
    parts = []
    # positional-only args (Python 3.8+)
    for i, arg in enumerate(args.posonlyargs):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        n_default = len(args.posonlyargs) + len(args.args) - len(args.defaults)
        di = i - (n_default - len(args.posonlyargs))
        default = f"={ast.unparse(args.defaults[di])}" if di >= 0 and di < len(args.defaults) else ""
        parts.append(f"{arg.arg}{ann}{default}")
    if args.posonlyargs:
        parts.append("/")
    # regular args
    n_regular = len(args.posonlyargs) + len(args.args)
    for i, arg in enumerate(args.args):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        global_i = len(args.posonlyargs) + i
        defaults_start = n_regular - len(args.defaults)
        di = global_i - defaults_start
        default = f"={ast.unparse(args.defaults[di])}" if di >= 0 and di < len(args.defaults) else ""
        parts.append(f"{arg.arg}{ann}{default}")
    # *args or bare *
    if args.vararg:
        ann = f": {ast.unparse(args.vararg.annotation)}" if args.vararg.annotation else ""
        parts.append(f"*{args.vararg.arg}{ann}")
    elif args.kwonlyargs:
        parts.append("*")
    # keyword-only args
    for i, arg in enumerate(args.kwonlyargs):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        kwd = args.kw_defaults[i]
        default = f"={ast.unparse(kwd)}" if kwd is not None else ""
        parts.append(f"{arg.arg}{ann}{default}")
    # **kwargs
    if args.kwarg:
        ann = f": {ast.unparse(args.kwarg.annotation)}" if args.kwarg.annotation else ""
        parts.append(f"**{args.kwarg.arg}{ann}")
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(parts)}){ret}:"


def _python_siginj(ex: dict) -> str:
    """Signature injection for Python: prepend extracted def-line to stripped code.

    Mirrors the C# siginj approach. The extracted signature provides the return
    type, parameter types, and function name which are omitted from the docstring
    query but present in the code — bridging the vocabulary gap.
    """
    code = ex.get("code", "")
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = _python_extract_sig(node)
                # Strip docstring from body for the code portion
                stripped = _strip_docstring_python(code)
                return f"{sig}\n\n{stripped}"
    except Exception:
        pass
    return _strip_docstring_python(code)


_BLOCK_COMMENT  = re.compile(r"^\s*/\*\*?.*?\*/\s*", re.DOTALL)
_RUBY_DOC       = re.compile(r"^\s*=begin.*?=end\s*", re.DOTALL)
_TRIPLE_SLASH   = re.compile(r"^\s*///.*$", re.MULTILINE)

# C# strategy preprocessing (mirrors csharp_improve_loop.py)
_CS_PASCAL    = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_CS_GENERICS  = re.compile(r"<[^>]{1,40}>")
_CS_USING     = re.compile(r"^\s*using\s+[\w.]+;\s*$", re.MULTILINE)
_CS_ATTR      = re.compile(r"^\s*\[.*?\]\s*$", re.MULTILINE)

def _cs_strip_doc(code: str) -> str:
    return _TRIPLE_SLASH.sub("", _CS_ATTR.sub("", code)).strip()

def _cs_split_id(text: str) -> str:
    tokens = re.split(r"(\W+)", text)
    out = []
    for t in tokens:
        if re.match(r"^[A-Za-z][A-Za-z0-9]{2,}$", t):
            out.append(_CS_PASCAL.sub(" ", t).lower())
        else:
            out.append(t)
    return "".join(out)

def _cs_preprocess(ex: dict, strategy: str) -> str:
    code  = ex.get("code", "")
    name  = (ex.get("func_name") or "").strip()
    short = name.split(".")[-1] if "." in name else name
    base  = _cs_strip_doc(code)
    if strategy == "split_code_only":
        return f"{short}\n\n{_cs_split_id(base)}" if short else _cs_split_id(base)
    if strategy == "no_generics_split":
        b = _CS_GENERICS.sub("", base)
        return f"{_cs_split_id(short)}\n\n{_cs_split_id(b)}" if short else _cs_split_id(b)
    if strategy == "no_using_split":
        b = _CS_USING.sub("", base).strip()
        return f"{_cs_split_id(short)}\n\n{_cs_split_id(b)}" if short else _cs_split_id(b)
    if strategy == "aggressive_strip_split":
        b = _CS_USING.sub("", _CS_GENERICS.sub("", base)).strip()
        return f"{_cs_split_id(short)}\n\n{_cs_split_id(b)}" if short else _cs_split_id(b)
    if strategy == "name_double_split":
        n = _cs_split_id(short)
        return f"{n} {n}\n\n{_cs_split_id(base)}" if n else _cs_split_id(base)
    if strategy == "s6_split":
        return f"{_cs_split_id(short)}\n\n{_cs_split_id(base)}" if short else _cs_split_id(base)
    # fallback: plain S6
    return f"{short}\n\n{base}" if short else base


def _go_extract_sig(code: str) -> str:
    """Extract Go function signature: lines from 'func' keyword up to (not including) '{'.

    Handles simple and multi-line Go signatures:
        func Foo(x int, y string) error {
        func (r *Receiver) Bar(x Type) (ReturnType, error) {
    """
    lines = code.split("\n")
    sig_lines = []
    for line in lines:
        stripped = line.strip()
        if not sig_lines:
            if stripped.startswith("func "):
                sig_lines.append(stripped)
        else:
            sig_lines.append(stripped)
        if sig_lines and "{" in stripped:
            break
    if not sig_lines:
        return ""
    sig = " ".join(sig_lines)
    brace = sig.find("{")
    if brace >= 0:
        sig = sig[:brace].strip()
    return sig


def _go_siginj(ex: dict) -> str:
    """Signature injection for Go: strip godoc comments, prepend func signature.

    Go functions have explicit types for all params and return values:
        func FindUserByID(id int64, db *sql.DB) (*User, error)
    This type information bridges the vocabulary gap between NL docstring queries
    and code bodies. Works with asymmetric models (BGE family) only.
    """
    code = ex.get("code", "")
    stripped = _strip_go_line_doc(code)
    sig = _go_extract_sig(stripped)
    if sig and len(sig) < 400:
        return f"{sig}\n\n{stripped}"
    return stripped


def _ruby_extract_sig(code: str) -> str:
    """Extract Ruby method signature: first 'def' line.

    Ruby is dynamically typed — sig is name + param names only (no types).
    Less informative than Go/Java but method name + params still bridges vocabulary.
    """
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("def "):
            return stripped
    return ""


def _ruby_siginj(ex: dict) -> str:
    """Signature injection for Ruby: strip # comments, prepend def line.

    Ruby has no type annotations; sigs are lower-value than Go/Java.
    Expected gain: +0.5-1.5% (vs +2-4% for typed languages).
    Works with asymmetric models (BGE family) only.
    """
    code = ex.get("code", "")
    stripped = _strip_ruby_all_doc(code)
    sig = _ruby_extract_sig(stripped)
    if sig and len(sig) < 200:
        return f"{sig}\n\n{stripped}"
    return stripped


def _php_extract_sig(code: str) -> str:
    """Extract PHP function signature: lines from 'function' keyword up to '{'.

    Modern PHP has type hints: function process(array $items, float $rate): Decimal
    Type annotations captured → similar benefit to Go/Java siginj.
    """
    stripped = _BLOCK_COMMENT.sub("", code, count=1).strip()
    lines = stripped.split("\n")
    sig_lines = []
    for line in lines:
        s = line.strip()
        if not sig_lines:
            if "function " in s:
                sig_lines.append(s)
        else:
            sig_lines.append(s)
        if sig_lines and "{" in s:
            break
    if not sig_lines:
        return ""
    sig = " ".join(sig_lines)
    brace = sig.find("{")
    if brace >= 0:
        sig = sig[:brace].strip()
    return sig


def _php_siginj(ex: dict) -> str:
    """Signature injection for PHP: strip Javadoc, prepend function signature.

    PHP has modern type hints: function calcTax(array $items, float $rate): Decimal
    Works with asymmetric models (BGE family) — same mechanism as Go/Java.
    """
    code = ex.get("code", "")
    sig = _php_extract_sig(code)
    stripped = _BLOCK_COMMENT.sub("", code, count=1).strip()
    if sig and len(sig) < 400:
        return f"{sig}\n\n{stripped}"
    return stripped


def _java_extract_sig(code: str) -> str:
    """Extract Java method signature by skipping leading annotations and blank lines."""
    lines = code.split("\n")
    collecting = False
    sig_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not collecting:
                continue
        if stripped.startswith("@") and not collecting:
            continue
        collecting = True
        sig_lines.append(stripped)
        if "{" in stripped:
            break
    sig = " ".join(sig_lines)
    brace = sig.find("{")
    if brace >= 0:
        sig = sig[:brace].strip()
    return sig


def _java_siginj(ex: dict) -> str:
    """Signature injection for Java: prepend extracted declaration to stripped body."""
    code = ex.get("code", "")
    sig = _java_extract_sig(code)
    stripped = _BLOCK_COMMENT.sub("", code, count=1).strip()
    if sig and len(sig) < 300:
        return f"{sig}\n\n{stripped}"
    return stripped


def _strip_go_line_doc(code: str) -> str:
    """Strip leading // comment block (Go godoc style)."""
    lines = code.split("\n")
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("//") or stripped == "":
            start = i + 1
        else:
            break
    return "\n".join(lines[start:]).strip()


def _strip_ruby_all_doc(code: str) -> str:
    """Strip =begin...=end blocks AND leading # comment lines."""
    code = _RUBY_DOC.sub("", code, count=1).strip()
    lines = code.split("\n")
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or stripped == "":
            start = i + 1
        else:
            break
    return "\n".join(lines[start:]).strip()


def _strip_csharp_doc(code: str) -> str:
    """Strip leading /// XML doc comment lines."""
    return _TRIPLE_SLASH.sub("", code).strip()


# Regression floors — MRR must exceed these values or the test fails.
# Set ~0.010-0.015 below confirmed benchmark MRR to absorb minor variance.
#
# Confirmed scores (best_model_config.json, R4 complete):
#   python:     0.9450 (siginj+sig-weighted hybrid α=0.85) — beats GraphCodeBERT +0.176
#   javascript: 0.8009 (3-way fusion)                     — beats GraphCodeBERT +0.127
#   java:       0.8872 (siginj+hybrid α=0.85)             — beats GraphCodeBERT +0.118
#   go:         0.8415 (siginj pure dense, hybrid FAILS)  — below GCB 0.897 by -0.056
#   ruby:       0.8021 (siginj+sig-weighted hybrid α=0.85)— beats GraphCodeBERT +0.099
#   php:        0.8669 (siginj+hybrid α=0.85)             — beats GraphCodeBERT +0.218
#   csharp:     0.9501 (docaug/score-fusion)              — synthetic, no published baseline
FLOOR_BY_LANG = {
    "python":     0.940,   # siginj+name-boosted hybrid=0.9469 (R5 promoted)
    "javascript": 0.786,   # 3-way fusion=0.8009 (R3 verified; siginj test pending)
    "java":       0.880,   # siginj+hybrid α=0.85=0.8872 (R4 promoted)
    "go":         0.833,   # siginj=0.8415 R@1=81.4% (hybrid fails for Go)
    "ruby":       0.793,   # siginj+sig-weighted hybrid=0.8021 (R4 promoted)
    "php":        0.857,   # siginj+hybrid α=0.85=0.8669 (R4 promoted)
    "csharp":     0.935,   # docaug=0.9501 R@1=0.917 (R9 verified)
}


def strip_docstring(code: str, lang: str) -> str:
    if lang == "python":
        return _strip_docstring_python(code)
    if lang == "go":
        return _strip_go_line_doc(code)
    if lang == "ruby":
        return _strip_ruby_all_doc(code)
    if lang == "csharp":
        return _strip_csharp_doc(code)
    return _BLOCK_COMMENT.sub("", code, count=1).strip()


def preprocess_code(ex: dict, lang: str) -> str:
    """Strategy-aware preprocessing per language.

    Non-Python languages prepend function name (S6 strategy).
    C# uses the strategy recorded in best_model_config.json (e.g. siginj).
    Python uses AST-based docstring stripping only (or siginj when configured).
    """
    if lang == "csharp":
        strategy = _strategy_for_lang("csharp")
        return _cs_preprocess(ex, strategy)
    if lang == "python":
        strategy = _strategy_for_lang("python")
        if strategy == "siginj":
            return _python_siginj(ex)
        return _strip_docstring_python(ex.get("code", ""))
    if lang == "java":
        strategy = _strategy_for_lang("java")
        if strategy == "siginj":
            return _java_siginj(ex)
    if lang == "go":
        strategy = _strategy_for_lang("go")
        if strategy == "siginj":
            return _go_siginj(ex)
    if lang == "ruby":
        strategy = _strategy_for_lang("ruby")
        if strategy == "siginj":
            return _ruby_siginj(ex)
    if lang == "php":
        strategy = _strategy_for_lang("php")
        if strategy == "siginj":
            return _php_siginj(ex)
    if lang == "javascript":
        strategy = _strategy_for_lang("javascript")
        if strategy == "siginj":
            return _js_siginj(ex)
    base = strip_docstring(ex["code"], lang)
    name = ex.get("func_name", "")
    if name and "." in name:
        name = name.split(".")[-1]
    if name:
        return f"{name}\n\n{base}"
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def require_sentence_transformers():
    if not HAS_ST:
        pytest.skip("sentence-transformers not installed — pip install sentence-transformers")


def _get_device() -> str:
    """GPU if available, CPU fallback. Logged so test output confirms which is active."""
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"
    return device


@pytest.fixture(scope="session")
def model():
    """Default model. Per-language tests use _get_embeddings which routes to the right model."""
    d = _get_device()
    print(f"\n  [model] device={d}", flush=True)
    return SentenceTransformer(MODEL_NAME, device=d)


# Session-level model pool — lazy-loaded, one instance per model name.
_model_pool: dict[str, "SentenceTransformer"] = {}


def _get_model(model_name: str) -> "SentenceTransformer":
    if model_name not in _model_pool:
        d = _get_device()
        print(f"\n  Loading model: {model_name} (device={d}) ...", flush=True)
        _model_pool[model_name] = SentenceTransformer(model_name, device=d)
    return _model_pool[model_name]


def _load_corpus(lang: str) -> list[dict]:
    path = DATA_DIR / f"codesearchnet_{lang}_full.jsonl"
    if not path.exists():
        return []
    examples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def _load_single_model_embeddings(corpus: list[dict], lang: str) -> tuple[np.ndarray, np.ndarray]:
    """Load or encode single-model embeddings for a language (original behaviour)."""
    n = len(corpus)
    model_name = _model_for_lang(lang)
    strategy   = _strategy_for_lang(lang)

    mkey = _MODEL_KEY_FOR_LANG.get(lang) or {
        "sentence-transformers/all-MiniLM-L6-v2":                    "minilm_l6",
        "sentence-transformers/all-MiniLM-L12-v2":                   "minilm_l12",
        "flax-sentence-embeddings/st-codesearch-distilroberta-base":  "codesearch",
        "sentence-transformers/all-mpnet-base-v2":                    "mpnet",
        "BAAI/bge-base-en-v1.5":                                      "bge_base",
        "sentence-transformers/all-roberta-large-v1":                 "roberta_large",
    }.get(model_name, "custom")

    MODEL_CACHE_DIR.mkdir(exist_ok=True)

    if strategy:
        sc_code = MODEL_CACHE_DIR / f"{mkey}_{lang}_{strategy}_code.npy"
        sc_doc  = MODEL_CACHE_DIR / f"{mkey}_{lang}_{strategy}_doc.npy"
        if sc_code.exists() and sc_doc.exists():
            ce = np.load(sc_code); de = np.load(sc_doc)
            if ce.shape[0] == n and de.shape[0] == n:
                return ce, de

    mc_code = MODEL_CACHE_DIR / f"{mkey}_{lang}_code.npy"
    mc_doc  = MODEL_CACHE_DIR / f"{mkey}_{lang}_doc.npy"
    if mc_code.exists() and mc_doc.exists():
        ce = np.load(mc_code); de = np.load(mc_doc)
        if ce.shape[0] == n and de.shape[0] == n:
            return ce, de

    if mkey in ("minilm_l6", "custom"):
        legacy_code = CACHE_DIR / f"csn_{lang}_code_embeddings_stripped.npy"
        legacy_doc  = CACHE_DIR / f"csn_{lang}_doc_embeddings.npy"
        if legacy_code.exists() and legacy_doc.exists():
            ce = np.load(legacy_code); de = np.load(legacy_doc)
            if ce.shape[0] == n and de.shape[0] == n:
                return ce, de

    strat_label = f"/{strategy}" if strategy else ""
    print(f"  [{lang}] Encoding {n:,} functions with {model_name}{strat_label} ...")
    loaded = _get_model(model_name)
    code_texts = [preprocess_code(ex, lang) for ex in corpus]
    ce = loaded.encode(code_texts, batch_size=64, normalize_embeddings=True,
                       show_progress_bar=True, convert_to_numpy=True)
    de = loaded.encode([ex["docstring"] for ex in corpus], batch_size=64,
                       normalize_embeddings=True, show_progress_bar=True,
                       convert_to_numpy=True)
    if strategy:
        np.save(MODEL_CACHE_DIR / f"{mkey}_{lang}_{strategy}_code.npy", ce)
        np.save(MODEL_CACHE_DIR / f"{mkey}_{lang}_{strategy}_doc.npy",  de)
    else:
        np.save(mc_code, ce)
        np.save(mc_doc, de)
    return ce, de


def _get_embeddings(corpus: list[dict], lang: str, _model_unused=None):
    """Return embeddings for this language.

    When a 'fusion' config exists in best_model_config.json, returns a list of
    (code_emb, doc_emb, weight) tuples for score-fusion evaluation.
    Otherwise returns a single (code_emb, doc_emb) tuple (original behaviour).

    Routing logic (single model):
      1. Check model_caches/{model_key}_{lang}_{strategy}_code.npy
      2. Check model_caches/{model_key}_{lang}_code.npy
      3. Fall back to legacy MiniLM cache
      4. Encode fresh with the routed model
    """
    fusion_cfg = _FUSION_FOR_LANG.get(lang)
    if fusion_cfg:
        n = len(corpus)
        components = []
        for comp in fusion_cfg["components"]:
            cache_key = comp["cache_key"]
            weight    = comp["weight"]
            cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
            dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
            if cc.exists() and dc.exists():
                ce = np.load(cc); de = np.load(dc)
                if ce.shape[0] == n and de.shape[0] == n:
                    components.append((ce, de, weight))
                    continue
            # Cache miss: encode fresh
            print(f"  [{lang}] Fusion component cache miss: {cache_key} — encoding ...", flush=True)
            m = _get_model(comp["model"])
            code_texts = [preprocess_code(ex, lang) for ex in corpus]
            ce = m.encode(code_texts, batch_size=64, normalize_embeddings=True,
                          show_progress_bar=True, convert_to_numpy=True)
            de = m.encode([ex["docstring"] for ex in corpus], batch_size=64,
                          normalize_embeddings=True, show_progress_bar=True,
                          convert_to_numpy=True)
            np.save(cc, ce); np.save(dc, de)
            components.append((ce, de, weight))
        if components:
            return components  # list of (ce, de, weight) — fusion mode
    return _load_single_model_embeddings(corpus, lang)


def _pool_mrr_recall(code_embs, doc_embs, n_eval, rng) -> dict:
    total = len(code_embs)
    all_idxs = list(range(total))
    eval_idxs = list(range(total))
    rng.shuffle(eval_idxs)
    if n_eval is not None:
        eval_idxs = eval_idxs[:n_eval]
    n = len(eval_idxs)

    hits_1 = hits_5 = hits_10 = 0
    rr_sum = 0.0
    for qi in eval_idxs:
        distractors = rng.sample([x for x in all_idxs if x != qi], k=N_POOL - 1)
        pool = [qi] + distractors
        scores = code_embs[pool] @ doc_embs[qi]
        ranked = np.argsort(-scores)
        rank = int(np.where(ranked == 0)[0][0]) + 1
        if rank == 1: hits_1 += 1
        if rank <= 5: hits_5 += 1
        if rank <= 10: hits_10 += 1
        rr_sum += 1.0 / rank

    return {"n": n, "mrr": rr_sum / n, "r1": hits_1 / n, "r5": hits_5 / n, "r10": hits_10 / n}


def _pool_mrr_recall_fused(components: list, n_eval, rng) -> dict:
    """Score-fusion variant of _pool_mrr_recall.

    components: list of (code_embs, doc_embs, weight) as returned by _get_embeddings
                in fusion mode.
    """
    total = len(components[0][0])
    all_idxs = list(range(total))
    eval_idxs = list(range(total))
    rng.shuffle(eval_idxs)
    if n_eval is not None:
        eval_idxs = eval_idxs[:n_eval]
    n = len(eval_idxs)

    hits_1 = hits_5 = hits_10 = 0
    rr_sum = 0.0
    for qi in eval_idxs:
        distractors = rng.sample([x for x in all_idxs if x != qi], k=N_POOL - 1)
        pool = [qi] + distractors
        scores = sum(w * (ce[pool] @ de[qi]) for ce, de, w in components)
        ranked = np.argsort(-scores)
        rank = int(np.where(ranked == 0)[0][0]) + 1
        if rank == 1: hits_1 += 1
        if rank <= 5: hits_5 += 1
        if rank <= 10: hits_10 += 1
        rr_sum += 1.0 / rank

    return {"n": n, "mrr": rr_sum / n, "r1": hits_1 / n, "r5": hits_5 / n, "r10": hits_10 / n}


def _run_mrr(embs, n_eval, rng) -> dict:
    """Dispatch to fused or single-model MRR depending on embs type."""
    if isinstance(embs, list):
        return _pool_mrr_recall_fused(embs, n_eval, rng)
    ce, de = embs
    return _pool_mrr_recall(ce, de, n_eval, rng)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGUAGES)
def test_codesearchnet_language(lang, model):
    """1K-pool benchmark for a single CodeSearchNet language split.

    Uses per-language model routing when best_model_config.json is present.
    The `model` argument is the default fixture but _get_embeddings routes
    to the best model per language automatically.
    """
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(
            f"No data for {lang}. Run: "
            f"python scripts/download_codesearchnet_full.py --lang {lang}"
        )
    if len(corpus) < 500:
        pytest.skip(f"{lang} corpus too small ({len(corpus)} examples).")

    active_model = _model_for_lang(lang)
    fusion_cfg   = _FUSION_FOR_LANG.get(lang)
    embs = _get_embeddings(corpus, lang)
    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    results = _run_mrr(embs, n_eval=None, rng=rng)
    elapsed = time.time() - t0

    r1, r5, r10, mrr = results["r1"], results["r5"], results["r10"], results["mrr"]
    n = results["n"]

    print(f"\n[{lang.upper()}] CodeSearchNet 1K-pool — {n:,} queries in {elapsed:.1f}s")
    if fusion_cfg:
        n_comp = len(fusion_cfg["components"])
        weights = [c["weight"] for c in fusion_cfg["components"]]
        print(f"  Mode: {n_comp}-way score fusion  weights={weights}")
    else:
        print(f"  Model: {active_model}")
    print(f"  MRR {mrr:.3f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}")

    floor = FLOOR_BY_LANG.get(lang, 0.20)
    assert mrr > floor, (
        f"[{lang}] Regression: MRR {mrr:.3f} <= {floor} baseline. Pipeline degraded."
    )
    assert r1 >= 0.10, f"[{lang}] R@1 {r1:.1%} below floor. Pipeline broken."


def test_codesearchnet_multilang_summary(model):
    """Run all available languages and print a comparison table."""
    rows = []
    for lang in LANGUAGES:
        corpus = _load_corpus(lang)
        if not corpus or len(corpus) < 500:
            rows.append((lang, None))
            continue
        embs = _get_embeddings(corpus, lang)
        rng = random.Random(RANDOM_SEED)
        r = _run_mrr(embs, n_eval=None, rng=rng)
        rows.append((lang, r))

    # Published baselines (MRR, 1K-pool, fine-tuned per language)
    # Sources: Husain 2019 (NBoW), Feng 2020 (CodeBERT), Guo 2021 (GraphCodeBERT)
    PUB = {
        "python":     {"nbow": 0.651, "codebert": 0.713, "gcb": 0.769},
        "javascript": {"nbow": 0.502, "codebert": 0.629, "gcb": 0.674},
        "java":       {"nbow": 0.643, "codebert": 0.719, "gcb": 0.769},
        "go":         {"nbow": 0.845, "codebert": 0.921, "gcb": 0.897},
        "ruby":       {"nbow": 0.562, "codebert": 0.678, "gcb": 0.703},
        "php":        {"nbow": 0.610, "codebert": 0.630, "gcb": 0.649},
        "csharp":     {"nbow": None,  "codebert": None,  "gcb": None},
    }

    W = 96
    print(f"\n{'='*W}")
    print("CODESEARCHNET 1K-POOL BENCHMARK — Multi-Language Summary")
    print(f"Model: {MODEL_NAME}")
    print(f"{'='*W}")
    print(f"  {'Language':<12} {'N':>7}  {'MRR':>6}  {'R@1':>6}  "
          f"{'NBoW':>7}  {'CodeBERT':>10}  {'GraphCBERT':>11}  {'Status'}")
    print(f"  {'-'*(W-2)}")
    for lang, r in rows:
        pub = PUB.get(lang, {})
        if r is None:
            note = "(no corpus — run download script)"
            if lang == "csharp":
                note = "(run: python scripts/download_csharp_github.py)"
            print(f"  {lang:<12} {'skip':>7}  {note}")
        else:
            corpus = _load_corpus(lang)
            n_str    = f"{r['n']:>7,}"
            gcb      = pub.get("gcb")
            codebert = pub.get("codebert")
            nbow     = pub.get("nbow")
            gcb_s    = f"{gcb:.3f}" if gcb else " N/A "
            cb_s     = f"{codebert:.3f}" if codebert else " N/A "
            nb_s     = f"{nbow:.3f}" if nbow else " N/A "

            if gcb and r["mrr"] > gcb:
                status = f"BEATS GraphCodeBERT +{r['mrr']-gcb:.3f}"
            elif codebert and r["mrr"] > codebert:
                status = f"BEATS CodeBERT +{r['mrr']-codebert:.3f}"
            elif lang == "csharp":
                status = "(synthetic benchmark)"
            else:
                delta = r["mrr"] - (gcb or codebert or 0)
                status = f"below GraphCBERT {delta:+.3f}"
            print(
                f"  {lang:<12} {n_str}  {r['mrr']:>6.3f}  {r['r1']:>5.1%}  "
                f"{nb_s:>7}  {cb_s:>10}  {gcb_s:>11}  {status}"
            )
    print(f"{'='*W}")
    print()
    # Show which model each language is using
    using_routing = bool(_MODEL_FOR_LANG)
    if using_routing:
        print("  Per-language model routing active (best_model_config.json):")
        for lang in LANGUAGES:
            m = _model_for_lang(lang)
            short = m.split("/")[-1]
            print(f"    {lang:<12} -> {short}")
    else:
        print("  All results: one 22 MB general-purpose model, zero per-language fine-tuning.")
        print("  Run scripts/benchmark_models.py to enable per-language model routing.")
    print()
    print("  Published baselines are fine-tuned specifically on each language.")
    print()
    print("  Note on Go: NBoW baseline is 0.845 — Go has clean semantic function names.")
    print("  Note on C#: synthetic benchmark from GitHub repos (no official CodeSearchNet split).")
    print("              Run python scripts/download_csharp_github.py to generate corpus.")

    available = [(lang, r) for lang, r in rows if r is not None]
    if available:
        _, best = max(available, key=lambda x: x[1]["mrr"])
        assert best["mrr"] >= 0.20, "No language cleared MRR 0.20 floor."


# ---------------------------------------------------------------------------
# Python improvement loop — test candidate strategies, promote if they beat
# the current best (MRR 0.898 with codesearch/default).
# Run with: pytest -k test_python_improve -v -s
# ---------------------------------------------------------------------------

def _python_encode_strategy(corpus, model_name, model_key, strategy, cache_key):
    """Encode corpus+docstrings with a given strategy, using cache if available."""
    n = len(corpus)
    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if cc.exists() and dc.exists():
        ce = np.load(cc); de = np.load(dc)
        if ce.shape[0] == n and de.shape[0] == n:
            print(f"  [{strategy}] cache hit ({cache_key})", flush=True)
            return ce, de
    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    print(f"  [{strategy}] encoding {n:,} functions with {model_name} ...", flush=True)
    m = _get_model(model_name)
    if strategy == "siginj":
        code_texts = [_python_siginj(ex) for ex in corpus]
    elif strategy == "s6":
        code_texts = [
            (lambda b, n: f"{n}\n\n{b}" if n else b)(
                _strip_docstring_python(ex.get("code", "")),
                (ex.get("func_name") or "").split(".")[-1]
            ) for ex in corpus
        ]
    else:
        code_texts = [_strip_docstring_python(ex.get("code", "")) for ex in corpus]
    ce = m.encode(code_texts, batch_size=64, normalize_embeddings=True,
                  show_progress_bar=True, convert_to_numpy=True)
    de = m.encode([ex["docstring"] for ex in corpus], batch_size=64,
                  normalize_embeddings=True, show_progress_bar=True,
                  convert_to_numpy=True)
    np.save(cc, ce)
    np.save(dc, de)
    return ce, de


@pytest.mark.parametrize("model_name,model_key,strategy,cache_key", [
    # Siginj with codesearch (same model as current best, new preprocessing)
    ("flax-sentence-embeddings/st-codesearch-distilroberta-base",
     "codesearch", "siginj", "codesearch_python_siginj"),
    # Siginj with BGE base (asymmetric model — the combo that made C# 0.950)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "siginj", "bge_base_python_siginj"),
    # BGE large — larger model, no extra preprocessing
    ("BAAI/bge-large-en-v1.5",
     "bge_large", "default", "bge_large_python"),
    # BGE large + siginj
    ("BAAI/bge-large-en-v1.5",
     "bge_large", "siginj", "bge_large_python_siginj"),
    # snowflake-arctic-embed-m v1 (137M params — CPU runnable; v2.0 requires trust_remote_code)
    # Uses BGE-style encode (no e5 "query: " / "passage: " prefixes — different model family)
    ("Snowflake/snowflake-arctic-embed-m",
     "snowflake_m", "siginj", "snowflake_m_python_siginj"),
    # snowflake default (no siginj — measure model-swap gain alone)
    ("Snowflake/snowflake-arctic-embed-m",
     "snowflake_m", "default", "snowflake_m_python"),
])
def test_python_improve(model_name, model_key, strategy, cache_key):
    """Improvement loop: try candidate strategies for Python, report vs current best."""
    CURRENT_BEST_MRR = 0.9469  # siginj+name-boosted hybrid α=0.85 (R5)
    CURRENT_BEST_KEY = "bge_base/siginj"

    corpus = _load_corpus("python")
    if not corpus:
        pytest.skip("Python corpus not downloaded. Run: python scripts/download_codesearchnet_full.py --lang python")

    ce, de = _python_encode_strategy(corpus, model_name, model_key, strategy, cache_key)
    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _pool_mrr_recall(ce, de, n_eval=None, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS" if delta > 0 else "no gain"

    print(f"\n[PYTHON IMPROVE] {model_key}/{strategy}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}  [{beat}]")
    if delta > 0.002:
        print(f"  *** IMPROVEMENT — consider promoting to best_model_config.json ***")
        print(f"  *** New strategy: model={model_name} strategy={strategy} cache_key={cache_key} ***")

    # Always passes — this is exploration, not a regression test
    assert mrr > 0.5, f"Python MRR {mrr:.3f} too low — preprocessing may be broken"


def _e5_encode_strategy(corpus, model_name, model_key, strategy, cache_key):
    """Encode with e5-style 'query: ' / 'passage: ' asymmetric prefixes.

    e5 models (intfloat/e5-base-v2, e5-large-v2) require:
      - queries:  'query: {natural language}'
      - passages: 'passage: {code or text}'
    Without prefixes they still work but leave performance on the table.
    Protocol: CPU-runnable base models only (≤200M params).
    """
    n = len(corpus)
    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if cc.exists() and dc.exists():
        ce = np.load(cc); de = np.load(dc)
        if ce.shape[0] == n and de.shape[0] == n:
            print(f"  [{strategy}] cache hit ({cache_key})", flush=True)
            return ce, de
    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    print(f"  [{strategy}] encoding {n:,} Python functions with {model_name} (e5 prefixes) ...", flush=True)
    m = _get_model(model_name)
    if strategy == "siginj":
        code_texts = ["passage: " + _python_siginj(ex) for ex in corpus]
    else:
        code_texts = ["passage: " + _strip_docstring_python(ex.get("code", "")) for ex in corpus]
    doc_texts = ["query: " + ex["docstring"] for ex in corpus]
    ce = m.encode(code_texts, batch_size=64, normalize_embeddings=True,
                  show_progress_bar=True, convert_to_numpy=True)
    de = m.encode(doc_texts, batch_size=64, normalize_embeddings=True,
                  show_progress_bar=True, convert_to_numpy=True)
    np.save(cc, ce)
    np.save(dc, de)
    return ce, de


@pytest.mark.parametrize("model_name,model_key,strategy,cache_key", [
    # e5-base-v2 + siginj (109M params — CPU runnable; CoIR zero-shot = 50.3 vs bge-base 46.6)
    ("intfloat/e5-base-v2",
     "e5_base", "siginj", "e5_base_python_siginj"),
    # e5-base-v2 default (no siginj — measure model-swap gain alone)
    ("intfloat/e5-base-v2",
     "e5_base", "default", "e5_base_python"),
])
def test_python_e5_improve(model_name, model_key, strategy, cache_key):
    """Improvement loop: test e5-base-v2 for Python code search.

    Protocol constraint: CPU-runnable base models only (≤200M params).
    Uses e5-specific 'query: ' / 'passage: ' prefixes.
    e5-base-v2 zero-shot CoIR = 50.3 (vs bge-base 46.6 — 3.7pt ahead).

    If e5+siginj achieves ~53+ CoIR, it beats Voyage-Code-002 and closes the loop.
    """
    CURRENT_BEST_MRR = 0.9469  # siginj+name-boosted hybrid α=0.85 (R5)
    CURRENT_BEST_KEY = "bge_base/siginj"

    corpus = _load_corpus("python")
    if not corpus:
        pytest.skip("Python corpus not downloaded. Run: python scripts/download_codesearchnet_full.py --lang python")

    # Debug gate: show 2 sample siginj outputs
    if strategy == "siginj" and corpus:
        print(f"\n  [{model_key} siginj debug] Sample outputs:", flush=True)
        for ex in corpus[:2]:
            out = _python_siginj(ex)
            preview = out[:200].replace("\n", " | ")
            print(f"    {preview}", flush=True)

    ce, de = _e5_encode_strategy(corpus, model_name, model_key, strategy, cache_key)
    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _pool_mrr_recall(ce, de, n_eval=None, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS" if delta > 0 else "no gain"

    print(f"\n[PYTHON E5 IMPROVE] {model_key}/{strategy}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}  [{beat}]")
    if delta > 0.002:
        print(f"  *** IMPROVEMENT — consider promoting to best_model_config.json ***")
        print(f"  *** New: model={model_name} strategy={strategy} cache_key={cache_key} ***")

    assert mrr > 0.5, f"Python MRR {mrr:.3f} too low — preprocessing may be broken"


# ---------------------------------------------------------------------------
# Java improvement loop
# ---------------------------------------------------------------------------

def _java_encode_strategy(corpus, model_name, model_key, strategy, cache_key):
    """Encode Java corpus with a given model+strategy; cache per cache_key."""
    n = len(corpus)
    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if cc.exists() and dc.exists():
        ce = np.load(cc); de = np.load(dc)
        if ce.shape[0] == n and de.shape[0] == n:
            print(f"  [{strategy}] cache hit ({cache_key})", flush=True)
            return ce, de
    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    print(f"  [{strategy}] encoding {n:,} Java functions with {model_name} ...", flush=True)
    m = _get_model(model_name)
    if strategy == "siginj":
        code_texts = [_java_siginj(ex) for ex in corpus]
    else:
        code_texts = [preprocess_code(ex, "java") for ex in corpus]
    ce = m.encode(code_texts, batch_size=64, normalize_embeddings=True,
                  show_progress_bar=True, convert_to_numpy=True)
    de = m.encode([ex["docstring"] for ex in corpus], batch_size=64,
                  normalize_embeddings=True, show_progress_bar=True,
                  convert_to_numpy=True)
    np.save(cc, ce)
    np.save(dc, de)
    return ce, de


@pytest.mark.parametrize("model_name,model_key,strategy,cache_key", [
    # BGE base + siginj (mirrors Python winner)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "siginj", "bge_base_java_siginj"),
    # BGE large + siginj
    ("BAAI/bge-large-en-v1.5",
     "bge_large", "siginj", "bge_large_java_siginj"),
    # BGE base + S6 (current default; baseline comparison)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "default", "bge_base_java"),
])
def test_java_improve(model_name, model_key, strategy, cache_key):
    """Improvement loop: try siginj strategies for Java, report vs current best.

    Baseline: st-codesearch, S6 strategy, MRR 0.850 (GraphCodeBERT: 0.769).
    Hypothesis: Java has explicit types in method signatures (e.g.
    'public List<User> findByAge(int age)') — bge-base+siginj should boost similar
    to Python (+3.3%) due to the same asymmetric subspace mechanism.
    """
    CURRENT_BEST_MRR = 0.8496  # codesearch/s6 from best_model_config.json
    CURRENT_BEST_KEY = "codesearch/s6"

    corpus = _load_corpus("java")
    if not corpus:
        pytest.skip("Java corpus not downloaded. Run: python scripts/download_codesearchnet_full.py --lang java")

    ce, de = _java_encode_strategy(corpus, model_name, model_key, strategy, cache_key)
    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _pool_mrr_recall(ce, de, n_eval=None, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS" if delta > 0 else "no gain"

    print(f"\n[JAVA IMPROVE] {model_key}/{strategy}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}  [{beat}]")
    if delta > 0.002:
        print(f"  *** IMPROVEMENT — consider promoting to best_model_config.json ***")
        print(f"  *** New: model={model_name} strategy={strategy} cache_key={cache_key} ***")

    assert mrr > 0.5, f"Java MRR {mrr:.3f} too low — preprocessing may be broken"


# ---------------------------------------------------------------------------
# Go improvement loop
# ---------------------------------------------------------------------------

def _go_encode_strategy(corpus, model_name, model_key, strategy, cache_key):
    """Encode Go corpus with a given model+strategy; cache per cache_key."""
    n = len(corpus)
    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if cc.exists() and dc.exists():
        ce = np.load(cc); de = np.load(dc)
        if ce.shape[0] == n and de.shape[0] == n:
            print(f"  [{strategy}] cache hit ({cache_key})", flush=True)
            return ce, de
    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    print(f"  [{strategy}] encoding {n:,} Go functions with {model_name} ...", flush=True)
    m = _get_model(model_name)
    if strategy == "siginj":
        code_texts = [_go_siginj(ex) for ex in corpus]
    else:
        code_texts = [preprocess_code(ex, "go") for ex in corpus]
    ce = m.encode(code_texts, batch_size=64, normalize_embeddings=True,
                  show_progress_bar=True, convert_to_numpy=True)
    de = m.encode([ex["docstring"] for ex in corpus], batch_size=64,
                  normalize_embeddings=True, show_progress_bar=True,
                  convert_to_numpy=True)
    np.save(cc, ce)
    np.save(dc, de)
    return ce, de


@pytest.mark.parametrize("model_name,model_key,strategy,cache_key", [
    # BGE base + siginj (mirrors Python/Java winner)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "siginj", "bge_base_go_siginj"),
    # st-codesearch + siginj (symmetric model — expected to hurt)
    ("flax-sentence-embeddings/st-codesearch-distilroberta-base",
     "codesearch", "siginj", "codesearch_go_siginj"),
    # BGE base + default S6 (asymmetric baseline, no siginj)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "default", "bge_base_go"),
])
def test_go_improve(model_name, model_key, strategy, cache_key):
    """Improvement loop: try bge-base+siginj for Go, report vs current best.

    Baseline: st-codesearch, S6 strategy, MRR 0.839 (GraphCodeBERT: 0.897).
    Hypothesis: Go has explicit types in all function signatures (e.g.
    'func FindByID(id int64, db *sql.DB) (*User, error)') — bge-base+siginj
    should boost retrieval same mechanism as Python (+3.3%) and Java (+1.5%).
    symmetric model (codesearch) expected to hurt (same as Python: -0.51%).
    """
    CURRENT_BEST_MRR = 0.839
    CURRENT_BEST_KEY = "codesearch/s6"

    corpus = _load_corpus("go")
    if not corpus:
        pytest.skip("Go corpus not downloaded. Run: python scripts/download_codesearchnet_full.py --lang go")

    # Debug gate: show 2 sample siginj outputs so we can verify before encoding full corpus
    if strategy == "siginj" and corpus:
        print(f"\n  [go siginj debug] Sample outputs:", flush=True)
        for ex in corpus[:2]:
            out = _go_siginj(ex)
            preview = out[:200].replace("\n", " | ")
            print(f"    {preview}", flush=True)

    ce, de = _go_encode_strategy(corpus, model_name, model_key, strategy, cache_key)
    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _pool_mrr_recall(ce, de, n_eval=None, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS" if delta > 0 else "no gain"

    print(f"\n[GO IMPROVE] {model_key}/{strategy}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}  [{beat}]")
    if delta > 0.002:
        print(f"  *** IMPROVEMENT - consider promoting to best_model_config.json ***")
        print(f"  *** New: model={model_name} strategy={strategy} cache_key={cache_key} ***")

    assert mrr > 0.5, f"Go MRR {mrr:.3f} too low -- preprocessing may be broken"


def _ruby_encode_strategy(corpus, model_name, model_key, strategy, cache_key):
    """Encode Ruby corpus with a given model+strategy; cache per cache_key."""
    n = len(corpus)
    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if cc.exists() and dc.exists():
        ce = np.load(cc); de = np.load(dc)
        if ce.shape[0] == n and de.shape[0] == n:
            print(f"  [{strategy}] cache hit ({cache_key})", flush=True)
            return ce, de
    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    print(f"  [{strategy}] encoding {n:,} Ruby functions with {model_name} ...", flush=True)
    m = _get_model(model_name)
    if strategy == "siginj":
        code_texts = [_ruby_siginj(ex) for ex in corpus]
    else:
        code_texts = [preprocess_code(ex, "ruby") for ex in corpus]
    ce = m.encode(code_texts, batch_size=64, normalize_embeddings=True,
                  show_progress_bar=True, convert_to_numpy=True)
    de = m.encode([ex["docstring"] for ex in corpus], batch_size=64,
                  normalize_embeddings=True, show_progress_bar=True,
                  convert_to_numpy=True)
    np.save(cc, ce)
    np.save(dc, de)
    return ce, de


@pytest.mark.parametrize("model_name,model_key,strategy,cache_key", [
    # BGE base + siginj (asymmetric model — expected to help)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "siginj", "bge_base_ruby_siginj"),
    # st-codesearch + siginj (symmetric — expected to hurt)
    ("flax-sentence-embeddings/st-codesearch-distilroberta-base",
     "codesearch", "siginj", "codesearch_ruby_siginj"),
    # BGE base + default S6 (asymmetric baseline)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "default", "bge_base_ruby"),
])
def test_ruby_improve(model_name, model_key, strategy, cache_key):
    """Improvement loop: try bge-base+siginj for Ruby, report vs current best.

    Baseline: st-codesearch, S6 strategy, MRR 0.7375 (GraphCodeBERT: 0.703).
    Ruby has no type annotations — sigs are method name + param names only.
    Expected gain: +0.5-1.5% (lower than typed languages; still worthwhile).
    """
    CURRENT_BEST_MRR = 0.7375
    CURRENT_BEST_KEY = "codesearch/s6"

    corpus = _load_corpus("ruby")
    if not corpus:
        pytest.skip("Ruby corpus not downloaded. Run: python scripts/download_codesearchnet_full.py --lang ruby")

    # Debug gate: show 2 sample siginj outputs so we can verify before encoding full corpus
    if strategy == "siginj" and corpus:
        print(f"\n  [ruby siginj debug] Sample outputs:", flush=True)
        for ex in corpus[:2]:
            out = _ruby_siginj(ex)
            preview = out[:200].replace("\n", " | ")
            print(f"    {preview}", flush=True)

    ce, de = _ruby_encode_strategy(corpus, model_name, model_key, strategy, cache_key)
    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _pool_mrr_recall(ce, de, n_eval=None, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS" if delta > 0 else "no gain"

    print(f"\n[RUBY IMPROVE] {model_key}/{strategy}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}  [{beat}]")
    if delta > 0.002:
        print(f"  *** IMPROVEMENT - consider promoting to best_model_config.json ***")
        print(f"  *** New: model={model_name} strategy={strategy} cache_key={cache_key} ***")

    assert mrr > 0.5, f"Ruby MRR {mrr:.3f} too low -- preprocessing may be broken"


def _php_encode_strategy(corpus, model_name, model_key, strategy, cache_key):
    """Encode PHP corpus with a given model+strategy; cache per cache_key."""
    n = len(corpus)
    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if cc.exists() and dc.exists():
        ce = np.load(cc); de = np.load(dc)
        if ce.shape[0] == n and de.shape[0] == n:
            print(f"  [{strategy}] cache hit ({cache_key})", flush=True)
            return ce, de
    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    print(f"  [{strategy}] encoding {n:,} PHP functions with {model_name} ...", flush=True)
    m = _get_model(model_name)
    if strategy == "siginj":
        code_texts = [_php_siginj(ex) for ex in corpus]
    else:
        code_texts = [preprocess_code(ex, "php") for ex in corpus]
    ce = m.encode(code_texts, batch_size=64, normalize_embeddings=True,
                  show_progress_bar=True, convert_to_numpy=True)
    de = m.encode([ex["docstring"] for ex in corpus], batch_size=64,
                  normalize_embeddings=True, show_progress_bar=True,
                  convert_to_numpy=True)
    np.save(cc, ce)
    np.save(dc, de)
    return ce, de


@pytest.mark.parametrize("model_name,model_key,strategy,cache_key", [
    # BGE base + siginj (asymmetric — PHP has type hints, good sig quality)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "siginj", "bge_base_php_siginj"),
    # st-codesearch + siginj (symmetric — expected to hurt)
    ("flax-sentence-embeddings/st-codesearch-distilroberta-base",
     "codesearch", "siginj", "codesearch_php_siginj"),
    # BGE base + default S6 (asymmetric baseline)
    ("BAAI/bge-base-en-v1.5",
     "bge_base", "default", "bge_base_php"),
])
def test_php_improve(model_name, model_key, strategy, cache_key):
    """Improvement loop: try bge-base+siginj for PHP, report vs current best.

    Baseline: st-codesearch, S6 strategy, MRR 0.8495 (GraphCodeBERT: 0.649).
    PHP modern type hints: function calcTax(array $items, float $rate): Decimal
    Type annotations captured — similar benefit to Go/Java siginj expected.
    """
    CURRENT_BEST_MRR = 0.8495
    CURRENT_BEST_KEY = "codesearch/s6"

    corpus = _load_corpus("php")
    if not corpus:
        pytest.skip("PHP corpus not downloaded. Run: python scripts/download_codesearchnet_full.py --lang php")

    # Debug gate: show 2 sample siginj outputs so we can verify before encoding full corpus
    if strategy == "siginj" and corpus:
        print(f"\n  [php siginj debug] Sample outputs:", flush=True)
        for ex in corpus[:2]:
            out = _php_siginj(ex)
            preview = out[:200].replace("\n", " | ")
            print(f"    {preview}", flush=True)

    ce, de = _php_encode_strategy(corpus, model_name, model_key, strategy, cache_key)
    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _pool_mrr_recall(ce, de, n_eval=None, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS" if delta > 0 else "no gain"

    print(f"\n[PHP IMPROVE] {model_key}/{strategy}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}  [{beat}]")
    if delta > 0.002:
        print(f"  *** IMPROVEMENT - consider promoting to best_model_config.json ***")
        print(f"  *** New: model={model_name} strategy={strategy} cache_key={cache_key} ***")

    assert mrr > 0.5, f"PHP MRR {mrr:.3f} too low -- preprocessing may be broken"


# ---------------------------------------------------------------------------
# R4: JavaScript siginj + BM25 + BM25+dense hybrid
# AI-minimization principle: test deterministic techniques before new AI models
# ---------------------------------------------------------------------------

_JS_FUNC = re.compile(
    r"""
    (?:async\s+)?                          # optional async
    function\s*\*?\s*(\w+)\s*\(([^)]*)\)  # function name(params)
    |
    (?:const|let|var)\s+(\w+)\s*=\s*       # const/let/var name =
    (?:async\s*)?                           # optional async
    (?:function\s*\*?\s*)?                  # optional function keyword
    \(([^)]*)\)                            # (params)
    \s*=>                                   # arrow
    |
    (\w+)\s*\(([^)]*)\)\s*\{              # method name(params) {
    """,
    re.VERBOSE,
)


def _js_extract_sig(code: str) -> str:
    """Extract JavaScript function signature (name + params, no types)."""
    # Strip block comment first
    stripped = _BLOCK_COMMENT.sub("", code, count=1).strip()
    # Find first non-blank line (skip any remaining line comments)
    for line in stripped.split("\n"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        m = _JS_FUNC.search(line)
        if m:
            # Named function: `function foo(a, b)`
            if m.group(1):
                return f"{m.group(1)}({m.group(2).strip()})"
            # Arrow: `const foo = (a, b) =>`
            if m.group(3):
                return f"{m.group(3)}({m.group(4).strip()})"
            # Method: `foo(a, b) {`
            if m.group(5):
                return f"{m.group(5)}({m.group(6).strip()})"
        break
    return ""


def _js_siginj(ex: dict) -> str:
    """Signature injection for JavaScript.

    JS has no type annotations, so sig = function name + param names only.
    Provides the same identifier-surfacing benefit as Ruby siginj.
    AI-minimization: deterministic regex, no model required.
    """
    code = ex.get("code", "")
    sig = _js_extract_sig(code)
    stripped = _BLOCK_COMMENT.sub("", code, count=1).strip()
    if sig and len(sig) < 200:
        return f"{sig}\n\n{stripped}"
    return stripped


def _js_encode_strategy(corpus, model_name, model_key, strategy, cache_key):
    n = len(corpus)
    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if cc.exists() and dc.exists():
        ce = np.load(cc); de = np.load(dc)
        if ce.shape[0] == n and de.shape[0] == n:
            print(f"  [{strategy}] cache hit ({cache_key})", flush=True)
            return ce, de
    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    m = _get_model(model_name)
    if strategy == "siginj":
        code_texts = [_js_siginj(ex) for ex in corpus]
    else:
        code_texts = [preprocess_code(ex, "javascript") for ex in corpus]
    ce = m.encode(code_texts, batch_size=64, normalize_embeddings=True,
                  show_progress_bar=True, convert_to_numpy=True)
    de = m.encode([ex["docstring"] for ex in corpus], batch_size=64,
                  normalize_embeddings=True, show_progress_bar=True, convert_to_numpy=True)
    np.save(cc, ce); np.save(dc, de)
    return ce, de


@pytest.mark.parametrize("model_name,model_key,strategy,cache_key", [
    ("BAAI/bge-base-en-v1.5", "bge_base", "siginj", "bge_base_javascript_siginj"),
    ("BAAI/bge-base-en-v1.5", "bge_base", "default", "bge_base_javascript_r4"),
])
def test_javascript_siginj_improve(model_name, model_key, strategy, cache_key):
    """R4: JavaScript bge-base+siginj vs current 3-way fusion (0.8009).

    AI-minimization: siginj is deterministic preprocessing (regex).
    If this matches or beats 3-way fusion, we can simplify the system
    from 3 models to 1.
    """
    CURRENT_BEST_MRR = 0.800852
    CURRENT_BEST_KEY = "codesearch/3-way-fusion"
    corpus = _load_corpus("javascript")
    if not corpus:
        pytest.skip("JavaScript corpus not downloaded.")

    if strategy == "siginj" and corpus:
        print(f"\n  [js siginj debug] Sample outputs:", flush=True)
        for ex in corpus[:3]:
            out = _js_siginj(ex)
            preview = out[:200].replace("\n", " | ")
            print(f"    {preview}", flush=True)

    ce, de = _js_encode_strategy(corpus, model_name, model_key, strategy, cache_key)
    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _pool_mrr_recall(ce, de, n_eval=None, rng=rng)
    elapsed = time.time() - t0
    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS FUSION" if delta > 0.001 else ("matches" if abs(delta) <= 0.001 else "no gain")

    print(f"\n[JS SIGINJ IMPROVE] {model_key}/{strategy}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}  [{beat}]")
    if delta > 0.001:
        print(f"  *** BEATS 3-WAY FUSION — can simplify system to 1 model ***")
        print(f"  *** New: model={model_name} strategy={strategy} (removes fusion complexity) ***")
    elif abs(delta) <= 0.001:
        print(f"  *** MATCHES FUSION within margin — simpler system, same quality ***")
    assert mrr > 0.5, f"JavaScript MRR {mrr:.3f} too low -- preprocessing may be broken"


# ---------------------------------------------------------------------------
# BM25 standalone + BM25+dense hybrid
# AI-minimization: measure how much pure keyword search contributes
# ---------------------------------------------------------------------------

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_STOP_TOKENS = frozenset({
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "it", "its",
    "if", "else", "return", "def", "class", "import", "from", "as", "not",
    "null", "none", "true", "false", "var", "let", "const", "function",
    "void", "string", "int", "float", "bool", "list", "dict", "set",
})


# Programming verb synonym map for query-code vocabulary bridging.
# Deterministic, zero-AI. Applied to function NAME tokens only (not body).
# Each verb maps to synonyms that commonly appear in NL queries for the same operation.
_PROG_VERB_SYNONYMS: dict = {
    "get":     ["fetch", "retrieve", "find", "read", "load", "obtain"],
    "fetch":   ["get", "retrieve", "load", "obtain"],
    "find":    ["get", "retrieve", "search", "look", "locate", "query"],
    "search":  ["find", "query", "look", "locate"],
    "set":     ["write", "update", "save", "store", "assign", "put"],
    "update":  ["set", "save", "write", "modify", "change", "edit"],
    "save":    ["write", "store", "persist", "set", "update"],
    "create":  ["make", "build", "new", "init", "initialize", "add", "insert"],
    "build":   ["create", "make", "construct", "generate"],
    "add":     ["create", "insert", "append", "push"],
    "insert":  ["add", "create", "append", "put"],
    "delete":  ["remove", "destroy", "drop", "clear", "erase"],
    "remove":  ["delete", "drop", "clear", "erase"],
    "check":   ["verify", "validate", "assert", "test", "is", "has"],
    "validate": ["check", "verify", "assert", "test"],
    "verify":  ["check", "validate", "assert", "confirm"],
    "convert": ["transform", "parse", "encode", "serialize", "format"],
    "parse":   ["convert", "decode", "deserialize", "read"],
    "encode":  ["convert", "serialize", "format"],
    "send":    ["post", "push", "emit", "publish", "write", "submit"],
    "post":    ["send", "publish", "submit"],
    "receive": ["read", "consume", "get", "pull", "listen"],
    "calculate": ["compute", "evaluate", "measure"],
    "compute": ["calculate", "evaluate", "process"],
    "load":    ["read", "import", "fetch", "get", "parse"],
    "read":    ["load", "get", "fetch", "parse"],
    "write":   ["save", "store", "write", "output"],
    "list":    ["all", "iter", "enumerate", "query"],
    "handle":  ["process", "manage", "dispatch"],
    "process": ["handle", "run", "execute"],
    "run":     ["execute", "start", "invoke", "call"],
    "execute": ["run", "call", "invoke", "dispatch"],
    "init":    ["create", "setup", "start", "prepare", "initialize"],
    "initialize": ["init", "setup", "create", "prepare"],
    "setup":   ["init", "configure", "prepare"],
    "configure": ["setup", "init", "set"],
    "format":  ["convert", "render", "stringify", "serialize"],
    "render":  ["format", "display", "output"],
    "log":     ["record", "write", "print", "output"],
    "print":   ["log", "display", "output", "show"],
    "show":    ["display", "render", "print"],
    "display": ["show", "render", "print"],
    "count":   ["size", "length", "num", "total"],
    "size":    ["count", "length", "num"],
    "close":   ["stop", "end", "finish", "terminate"],
    "stop":    ["close", "end", "finish", "terminate", "cancel"],
    "start":   ["begin", "init", "run", "open"],
    "begin":   ["start", "init", "open"],
    "open":    ["start", "begin", "init", "read"],
    "copy":    ["clone", "duplicate"],
    "clone":   ["copy", "duplicate"],
    "merge":   ["combine", "join", "concat"],
    "join":    ["merge", "combine", "concat"],
    "split":   ["divide", "separate", "partition"],
    "filter":  ["select", "query", "search", "find"],
    "sort":    ["order", "arrange"],
    "compare": ["check", "diff", "equal"],
    "equal":   ["compare", "match", "same"],
}


def _bm25_tokenize(text: str) -> list:
    """Deterministic tokenization for BM25: split identifiers, lowercase, filter stops."""
    # Split camelCase and snake_case, extract alphanumeric tokens
    tokens = re.findall(r"[a-zA-Z][a-z0-9]*|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[0-9]+", text)
    result = []
    for t in tokens:
        t = t.lower()
        if len(t) >= 2 and t not in _STOP_TOKENS:
            result.append(t)
    return result


def _prog_stem(word: str) -> str:
    """Lightweight programmer-vocabulary stemmer. No dependencies, fully deterministic.

    Handles the most common NL query vs code identifier mismatches:
    - Plural forms: 'users' → 'user', 'files' → 'file'
    - -ing forms: 'parsing' → 'pars', 'fetching' → 'fetch'
    - -ed forms: 'parsed' → 'pars', 'fetched' → 'fetch'
    - -er forms: 'parser' → 'pars' (handles agent nouns)
    - -tion/-ation: kept (discriminative: 'calculation' ≠ 'method')

    Not a full Porter stemmer — only covers high-frequency patterns
    in programming English. Avoids over-stemming that hurts precision.
    """
    n = len(word)
    if n < 4:
        return word
    if word.endswith("ing") and n > 6:
        return word[:-3]
    if word.endswith("ings") and n > 7:
        return word[:-4]
    if word.endswith("ed") and n > 5:
        base = word[:-2]
        if base.endswith("i"):
            base = base[:-1] + "y"
        return base
    if word.endswith("er") and n > 5:
        return word[:-2]
    if word.endswith("ers") and n > 6:
        return word[:-3]
    if word.endswith("s") and n > 4 and not word.endswith("ss"):
        return word[:-1]
    return word


def _bm25_stem_tokenize(text: str) -> list:
    """BM25 tokenizer with lightweight programmer stemming.

    Applies _prog_stem() after camelCase splitting and lowercasing.
    Intended to improve recall when docstring uses a different verb form
    than the code identifier (e.g. 'calculates' vs 'calculate').
    """
    tokens = re.findall(r"[a-zA-Z][a-z0-9]*|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[0-9]+", text)
    result = []
    for t in tokens:
        t = t.lower()
        if len(t) >= 2 and t not in _STOP_TOKENS:
            result.append(_prog_stem(t))
    return result


# ---------------------------------------------------------------------------
# R7: Type-aware asymmetric BM25 tokenization (non-AI, zero dependencies)
#
# Root cause of BM25 type-signal loss:
#   _STOP_TOKENS removes "int", "float", "bool", "list", "dict", "set" from BOTH
#   corpus (code) and query (docstring). Code signatures use exactly these tokens
#   as type annotations: List[str], int, float, dict. Docstrings say "returns a
#   list of strings" — both "list" and "string" are stopped → zero type signal in BM25.
#
# Fix (two parts, fully deterministic, zero AI):
#   1. _CORPUS_STOP_TOKENS: keep type tokens in corpus so signature types stay in BM25 index
#   2. _bm25_query_type_tokenize: normalizes English→Python type names + keeps type tokens
#      "string"→"str", "integer"→"int", "boolean"→"bool", "array"→"list"
#   3. _bm25_mrr_asymmetric: uses different tokenizers for corpus vs query sides
# ---------------------------------------------------------------------------

# Corpus stop tokens — same as _STOP_TOKENS but keeps type tokens: int, float, bool, list, dict, set
# These appear as type annotations in function signatures (the highest-signal region)
_CORPUS_STOP_TOKENS = frozenset({
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "it", "its",
    "if", "else", "return", "def", "class", "import", "from", "as", "not",
    "null", "none", "true", "false", "var", "let", "const", "function",
    "void", "string",
    # KEPT (removed vs _STOP_TOKENS): "int", "float", "bool", "list", "dict", "set"
    # → type annotations in signatures are now indexed by BM25
})

# Query stop tokens — smaller set for docstring side. Keeps type tokens and "return".
# "return" in docstrings conveys intent ("Returns the sum"), unlike code where it's syntax.
_QUERY_STOP_TOKENS_TYPEAWARE = frozenset({
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "it", "its",
    "if", "else", "not", "null", "none", "true", "false",
    # NOT stopped: int, float, bool, list, dict, set, str (type-discriminative in docstrings)
    # NOT stopped: "return" — conveys intent ("Returns the sum of X")
})

# English → Python type name normalization. Applied to QUERY (docstring) side only.
# Bridges the vocabulary gap: docstrings use English, code uses Python annotation syntax.
# Example: "returns a list of strings" → tokens include "list" and "str" (normalized from "strings")
#          Code signature `-> List[str]` → tokens include "list" and "str" → BM25 match!
_QUERY_TYPE_NORMALIZE = {
    "string":       "str",
    "strings":      "str",
    "integer":      "int",
    "integers":     "int",
    "boolean":      "bool",
    "booleans":     "bool",
    "array":        "list",
    "arrays":       "list",
    "dictionary":   "dict",
    "dictionaries": "dict",
    "mapping":      "dict",
    "mappings":     "dict",
    "bytes":        "bytes",
    "byte":         "bytes",
}


def _bm25_corpus_type_tokenize(text: str) -> list:
    """Corpus BM25 tokenizer with type tokens un-stopped.

    Same camelCase splitting + lowercasing as _bm25_tokenize, but uses
    _CORPUS_STOP_TOKENS which keeps int/float/bool/list/dict/set.
    Allows function signature type annotations to contribute to BM25 scoring.
    """
    tokens = re.findall(r"[a-zA-Z][a-z0-9]*|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[0-9]+", text)
    result = []
    for t in tokens:
        t = t.lower()
        if len(t) >= 2 and t not in _CORPUS_STOP_TOKENS:
            result.append(t)
    return result


def _bm25_query_type_tokenize(text: str) -> list:
    """Query BM25 tokenizer with English→Python type normalization.

    Normalizes English type names to Python code conventions:
    "string" → "str", "integer" → "int", "boolean" → "bool", "array" → "list"

    Uses _QUERY_STOP_TOKENS_TYPEAWARE which preserves type tokens and "return".
    Applied to QUERY (docstring) side only — not corpus.
    """
    tokens = re.findall(r"[a-zA-Z][a-z0-9]*|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[0-9]+", text)
    result = []
    for t in tokens:
        t = t.lower()
        t = _QUERY_TYPE_NORMALIZE.get(t, t)
        if len(t) >= 2 and t not in _QUERY_STOP_TOKENS_TYPEAWARE:
            result.append(t)
    return result


def _bm25_mrr_asymmetric(corpus_texts: list, query_texts: list, n_eval: int = None,
                          rng=None, corpus_tokenizer=None, query_tokenizer=None) -> dict:
    """BM25 MRR with asymmetric corpus/query tokenizers.

    Allows different tokenizers for corpus (code) and query (docstring).
    Used for type-aware BM25 where corpus keeps type annotation tokens and
    the query normalizes English type names to Python conventions.
    """
    if corpus_tokenizer is None:
        corpus_tokenizer = _bm25_tokenize
    if query_tokenizer is None:
        query_tokenizer = _bm25_tokenize
    if rng is None:
        rng = random.Random(RANDOM_SEED)
    n = len(corpus_texts)
    if n_eval is None or n_eval >= n:
        n_eval = n
    indices = list(range(n))
    rng.shuffle(indices)
    eval_idx = indices[:n_eval]

    tokenized = [corpus_tokenizer(t) for t in corpus_texts]
    bm25 = BM25Okapi(tokenized)

    hits1 = hits5 = hits10 = 0
    rr_sum = 0.0
    for idx in eval_idx:
        pool = [idx] + rng.sample([i for i in range(n) if i != idx], min(999, n - 1))
        pool_texts = [tokenized[i] for i in pool]
        query_tok = query_tokenizer(query_texts[idx])
        pool_bm25 = BM25Okapi(pool_texts)
        scores = pool_bm25.get_scores(query_tok)
        ranked = sorted(range(len(pool)), key=lambda i: scores[i], reverse=True)
        true_rank = ranked.index(0) + 1
        rr_sum += 1.0 / true_rank
        if true_rank == 1: hits1 += 1
        if true_rank <= 5: hits5 += 1
        if true_rank <= 10: hits10 += 1

    count = len(eval_idx)
    return {"mrr": rr_sum / count, "r1": hits1 / count, "r5": hits5 / count, "r10": hits10 / count}


def _hybrid_mrr_asymmetric(code_embs: np.ndarray, doc_embs: np.ndarray,
                            corpus_texts: list, query_texts: list,
                            alpha: float = 0.85, n_eval: int = None, rng=None,
                            corpus_tokenizer=None, query_tokenizer=None) -> dict:
    """BM25+dense hybrid with asymmetric corpus/query tokenizers.

    Same as _hybrid_mrr but uses separate tokenizers for corpus and query.
    Enables type-aware BM25 within the hybrid: dense side unchanged,
    BM25 side uses type-aware asymmetric tokenization.
    """
    if corpus_tokenizer is None:
        corpus_tokenizer = _bm25_tokenize
    if query_tokenizer is None:
        query_tokenizer = _bm25_tokenize
    if rng is None:
        rng = random.Random(RANDOM_SEED)
    n = len(corpus_texts)
    if n_eval is None or n_eval >= n:
        n_eval = n
    indices = list(range(n))
    rng.shuffle(indices)
    eval_idx = indices[:n_eval]

    tokenized = [corpus_tokenizer(t) for t in corpus_texts]
    bm25_full = BM25Okapi(tokenized)

    hits1 = hits5 = hits10 = 0
    rr_sum = 0.0
    for qi in eval_idx:
        distractors = rng.sample([x for x in range(n) if x != qi], k=N_POOL - 1)
        pool = [qi] + distractors

        dense_scores = code_embs[pool] @ doc_embs[qi]
        dmin, dmax = dense_scores.min(), dense_scores.max()
        dense_norm = (dense_scores - dmin) / (dmax - dmin + 1e-9)

        pool_texts_tok = [tokenized[i] for i in pool]
        query_tok = query_tokenizer(query_texts[qi])
        pool_bm25 = BM25Okapi(pool_texts_tok)
        bm25_raw = pool_bm25.get_scores(query_tok)
        bmin, bmax = bm25_raw.min(), bm25_raw.max()
        bm25_norm = (bm25_raw - bmin) / (bmax - bmin + 1e-9)

        hybrid = alpha * dense_norm + (1.0 - alpha) * bm25_norm
        ranked = np.argsort(-hybrid)
        rank = int(np.where(ranked == 0)[0][0]) + 1
        rr_sum += 1.0 / rank
        if rank == 1: hits1 += 1
        if rank <= 5: hits5 += 1
        if rank <= 10: hits10 += 1

    count = len(eval_idx)
    return {"mrr": rr_sum / count, "r1": hits1 / count, "r5": hits5 / count, "r10": hits10 / count}


def _bm25_mrr(corpus_texts: list, query_texts: list, n_eval: int = None,
              rng=None, tokenizer=None) -> dict:
    """Pure BM25 1K-pool MRR. No AI, no embeddings — keyword search only.

    tokenizer: callable(str) -> list[str]. Defaults to _bm25_tokenize.
    Pass _bm25_stem_tokenize to test stemmed BM25.
    """
    if tokenizer is None:
        tokenizer = _bm25_tokenize
    if rng is None:
        rng = random.Random(RANDOM_SEED)
    n = len(corpus_texts)
    if n_eval is None or n_eval >= n:
        n_eval = n
    indices = list(range(n))
    rng.shuffle(indices)
    eval_idx = indices[:n_eval]

    # Build BM25 on the full corpus
    tokenized = [tokenizer(t) for t in corpus_texts]
    bm25 = BM25Okapi(tokenized)

    hits1 = hits5 = hits10 = 0
    rr_sum = 0.0
    for idx in eval_idx:
        # Build 1K pool: true doc + 999 distractors
        pool = [idx] + rng.sample([i for i in range(n) if i != idx], min(999, n - 1))
        pool_texts = [tokenized[i] for i in pool]

        query_tok = tokenizer(query_texts[idx])
        # Score each pool doc against the query
        pool_bm25 = BM25Okapi(pool_texts)
        scores = pool_bm25.get_scores(query_tok)
        ranked = sorted(range(len(pool)), key=lambda i: scores[i], reverse=True)
        true_rank = ranked.index(0) + 1  # pool[0] is the true doc (rank 1-based)

        rr_sum += 1.0 / true_rank
        if true_rank == 1: hits1 += 1
        if true_rank <= 5: hits5 += 1
        if true_rank <= 10: hits10 += 1

    count = len(eval_idx)
    return {
        "mrr": rr_sum / count,
        "r1": hits1 / count,
        "r5": hits5 / count,
        "r10": hits10 / count,
    }


def _hybrid_mrr(code_embs: np.ndarray, doc_embs: np.ndarray,
                corpus_texts: list, query_texts: list,
                alpha: float = 0.7, n_eval: int = None, rng=None,
                tokenizer=None) -> dict:
    """BM25 + dense hybrid MRR.

    final_score = alpha * cosine_sim + (1-alpha) * bm25_score_normalized
    alpha=0.7 means 70% dense, 30% BM25.
    Both scores are min-max normalized per query before combining.
    tokenizer: callable(str) -> list[str]. Defaults to _bm25_tokenize.
    """
    if tokenizer is None:
        tokenizer = _bm25_tokenize
    if rng is None:
        rng = random.Random(RANDOM_SEED)
    n = len(corpus_texts)
    if n_eval is None or n_eval >= n:
        n_eval = n
    indices = list(range(n))
    rng.shuffle(indices)
    eval_idx = indices[:n_eval]

    tokenized = [tokenizer(t) for t in corpus_texts]
    bm25 = BM25Okapi(tokenized)

    hits1 = hits5 = hits10 = 0
    rr_sum = 0.0
    for idx in eval_idx:
        pool = [idx] + rng.sample([i for i in range(n) if i != idx], min(999, n - 1))

        # Dense scores
        q_emb = doc_embs[idx]
        pool_embs = code_embs[pool]
        dense_s = pool_embs @ q_emb  # cosine similarity

        # BM25 scores for this pool
        query_tok = tokenizer(query_texts[idx])
        pool_tok = [tokenized[i] for i in pool]
        pool_bm25 = BM25Okapi(pool_tok)
        bm25_s = np.array(pool_bm25.get_scores(query_tok))

        # Min-max normalize both to [0,1]
        def _normalize(arr):
            mn, mx = arr.min(), arr.max()
            if mx == mn:
                return np.zeros_like(arr)
            return (arr - mn) / (mx - mn)

        hybrid_s = alpha * _normalize(dense_s) + (1 - alpha) * _normalize(bm25_s)
        ranked = np.argsort(hybrid_s)[::-1].tolist()
        true_rank = ranked.index(0) + 1

        rr_sum += 1.0 / true_rank
        if true_rank == 1: hits1 += 1
        if true_rank <= 5: hits5 += 1
        if true_rank <= 10: hits10 += 1

    count = len(eval_idx)
    return {
        "mrr": rr_sum / count,
        "r1": hits1 / count,
        "r5": hits5 / count,
        "r10": hits10 / count,
    }


def _rrf_mrr(code_embs: np.ndarray, doc_embs: np.ndarray,
             corpus_texts: list, query_texts: list,
             k: int = 60, n_eval: int = None, rng=None,
             bm25_corpus_texts: list = None) -> dict:
    """Reciprocal Rank Fusion (RRF) — rank-based hybrid, no score normalization.

    Cormack et al. 2009: rrf(d) = 1/(k + rank_bm25(d)) + 1/(k + rank_dense(d))
    k=60 is the standard value from the original paper.

    Advantage over score-based hybrid: RRF is invariant to score magnitude and scale.
    Min-max normalization in _hybrid_mrr is query-dependent and sensitive to tied scores.
    RRF uses ranks (integers) which are always comparable.

    bm25_corpus_texts: if provided, use these for BM25 index (e.g. sig-weighted texts).
    Otherwise uses corpus_texts.
    """
    if rng is None:
        rng = random.Random(RANDOM_SEED)
    if bm25_corpus_texts is None:
        bm25_corpus_texts = corpus_texts
    n = len(corpus_texts)
    if n_eval is None or n_eval >= n:
        n_eval = n
    indices = list(range(n))
    rng.shuffle(indices)
    eval_idx = indices[:n_eval]

    tokenized = [_bm25_tokenize(t) for t in bm25_corpus_texts]
    bm25 = BM25Okapi(tokenized)

    hits1 = hits5 = hits10 = 0
    rr_sum = 0.0
    for idx in eval_idx:
        pool = [idx] + rng.sample([i for i in range(n) if i != idx], min(999, n - 1))

        # Dense ranks
        q_emb = doc_embs[idx]
        pool_embs = code_embs[pool]
        dense_scores = pool_embs @ q_emb
        dense_rank = np.argsort(-dense_scores)  # descending by score

        # BM25 ranks
        query_tok = _bm25_tokenize(query_texts[idx])
        pool_tok = [tokenized[i] for i in pool]
        pool_bm25 = BM25Okapi(pool_tok)
        bm25_scores = np.array(pool_bm25.get_scores(query_tok))
        bm25_rank = np.argsort(-bm25_scores)  # descending by score

        # Build position-to-rank lookups (0-indexed positions)
        dense_pos = np.zeros(len(pool), dtype=np.float64)
        bm25_pos = np.zeros(len(pool), dtype=np.float64)
        for rank_i, pos in enumerate(dense_rank):
            dense_pos[pos] = rank_i
        for rank_i, pos in enumerate(bm25_rank):
            bm25_pos[pos] = rank_i

        # RRF score: higher is better
        rrf_scores = 1.0 / (k + dense_pos) + 1.0 / (k + bm25_pos)
        ranked = np.argsort(-rrf_scores).tolist()
        true_rank = ranked.index(0) + 1

        rr_sum += 1.0 / true_rank
        if true_rank == 1: hits1 += 1
        if true_rank <= 5: hits5 += 1
        if true_rank <= 10: hits10 += 1

    count = len(eval_idx)
    return {
        "mrr": rr_sum / count,
        "r1": hits1 / count,
        "r5": hits5 / count,
        "r10": hits10 / count,
    }


@pytest.mark.parametrize("lang", ["python", "javascript", "java", "go", "ruby", "php"])
def test_bm25_baseline(lang):
    """R4: Pure BM25 MRR on each language. No AI, no embeddings.

    AI-minimization principle: always measure the keyword-search baseline
    before using any AI model. This shows how much AI actually adds.

    Protocol: if BM25 MRR >= 0.5 on a language, consider BM25+hybrid before
    testing new AI models for that language.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed — pip install rank_bm25")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    corpus_texts = [preprocess_code(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    # Sample 200 for speed (BM25 pool rebuild is O(n_pool) per query)
    indices = list(range(len(corpus)))
    rng.shuffle(indices)
    sample = indices[:200]
    sample_corpus = [corpus_texts[i] for i in range(len(corpus))]
    sample_queries = [query_texts[i] for i in range(len(corpus))]

    r = _bm25_mrr(sample_corpus, sample_queries, n_eval=200, rng=random.Random(RANDOM_SEED))
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]

    # Get current best for comparison
    best_cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f)
        best_cfg = cfg.get(lang, {})
    except Exception:
        pass
    best_mrr = best_cfg.get("mrr", 0)

    print(f"\n[BM25 BASELINE] {lang}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s, 200-sample)")
    if best_mrr:
        ratio = mrr / best_mrr
        print(f"  vs AI best ({best_mrr:.4f}): BM25 is {ratio:.1%} of AI performance")
        if ratio >= 0.85:
            print(f"  *** BM25 within 15% of AI — strong candidate for hybrid ***")
        elif ratio >= 0.70:
            print(f"  *** BM25 within 30% of AI — hybrid likely helps ***")
        else:
            print(f"  BM25 well below AI — AI is necessary for this language")

    assert mrr >= 0.2, f"{lang} BM25 MRR {mrr:.3f} — check tokenization"


@pytest.mark.parametrize("lang,alpha", [
    ("python", 0.7),
    ("python", 0.85),
    ("javascript", 0.7),
    ("javascript", 0.85),
    ("java", 0.85),
    ("go", 0.7),
    ("go", 0.85),
    ("ruby", 0.85),
    ("php", 0.85),
])
def test_bm25_hybrid_improve(lang, alpha):
    """R4: BM25+dense hybrid vs pure dense.

    AI-minimization: add deterministic BM25 scores to dense cosine similarity.
    No new model required — same bge-base embeddings, add BM25 on top.

    alpha=0.7 → 70% dense + 30% BM25
    alpha=0.85 → 85% dense + 15% BM25
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    # Get best cached embeddings for this language
    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    cache_key = cfg.get("cache_key")
    if not cache_key:
        pytest.skip(f"No cache_key in best_model_config for {lang}")

    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if not cc.exists():
        pytest.skip(f"Embeddings not cached for {lang} ({cache_key})")

    code_embs = np.load(cc)
    doc_embs = np.load(dc)
    corpus_texts = [preprocess_code(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    CURRENT_BEST_MRR = cfg.get("mrr", 0.0)

    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    # Sample 500 for reasonable speed (BM25 pool rebuild is expensive)
    r = _hybrid_mrr(code_embs, doc_embs, corpus_texts, query_texts,
                    alpha=alpha, n_eval=500, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS" if delta > 0.002 else ("matches" if abs(delta) <= 0.002 else "no gain")

    print(f"\n[BM25+DENSE HYBRID] {lang} alpha={alpha}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s, 500-sample)")
    print(f"  vs pure dense ({CURRENT_BEST_MRR:.4f}): {sign}{delta:.4f}  [{beat}]")
    if delta > 0.002:
        print(f"  *** HYBRID BEATS PURE DENSE — deterministic improvement, no new model needed ***")
        print(f"  *** Promote: BM25+dense hybrid for {lang}, alpha={alpha} ***")
    elif delta > 0:
        print(f"  Small gain — test with n_eval=None for full confirmation")

    assert mrr > 0.4, f"{lang} hybrid MRR {mrr:.3f} — check embeddings"


# ---------------------------------------------------------------------------
# Novel technique: Signature-weighted BM25 (BM25F approximation)
# Idea: function signatures are the most semantically dense part of code.
# If signature tokens appear 3x in the BM25 index (pseudo-field-weighting),
# they get higher IDF impact without any AI model.
# This is BM25F approximated via token repetition — fully deterministic.
# ---------------------------------------------------------------------------

def _sig_weighted_text(ex: dict, lang: str) -> str:
    """Build BM25F-approximation: signature tokens × 3 + body tokens × 1.

    Novel deterministic technique: repeat signature in the indexed text
    to give it 3x weight in BM25 scoring without any AI model.
    """
    code = ex.get("code", "")
    # Extract signature based on language
    if lang == "python":
        sig = _python_siginj(ex) if _strategy_for_lang("python") == "siginj" else ""
        # If siginj, sig is the first line; otherwise extract via regex
        if not sig:
            m = re.match(r"(async\s+)?def\s+\w+\([^)]*\)\s*(?:->[^:]+)?:", code)
            sig = m.group(0) if m else ""
    elif lang == "java":
        sig = _java_extract_sig(code)
    elif lang == "php":
        sig = _php_extract_sig(code)
    elif lang == "go":
        sig = _go_siginj(ex).split("\n")[0] if "\n" in _go_siginj(ex) else ""
    elif lang == "javascript":
        sig = _js_extract_sig(code)
    elif lang == "ruby":
        sig = _ruby_extract_sig(_strip_ruby_all_doc(code))
    else:
        sig = ""
    body = preprocess_code(ex, lang)
    # Repeat sig 3× at start (pseudo-field-weighting for BM25)
    if sig and len(sig) < 300:
        return f"{sig}\n{sig}\n{sig}\n{body}"
    return body


def _name_boosted_text(ex: dict, lang: str,
                       name_repeat: int = 5,
                       sig_repeat: int = 3) -> str:
    """Multi-tier BM25 text: function name × N + sig params × M + body × 1.

    More fine-grained than sig_weighted_text (which repeats full sig × 3):
    - Function name gets the highest weight (default 5×)
    - Signature parameters/types get medium weight (default 3×)
    - Body gets base weight (1×)

    Hypothesis: the function name is the SINGLE most discriminative token.
    Giving it 5× vs sig's uniform 3× could improve BM25 precision further.

    Function name is extracted from the 'func_name' field (available in all
    CSN languages: Python, Java, Go, Ruby, PHP, JavaScript).
    For class methods like `MyClass.myMethod`, we use only `myMethod`.
    """
    func_name = ex.get("func_name", "")
    if "." in func_name:
        func_name = func_name.split(".")[-1]  # strip class prefix

    # Get full sig text (function name + params) for medium-weight tier
    sig_full = _sig_weighted_text.__wrapped__(ex, lang) if hasattr(
        _sig_weighted_text, "__wrapped__") else ""
    # Build sig text the simple way: use same extraction as _sig_weighted_text
    code = ex.get("code", "")
    if lang == "python":
        m = re.match(r"(async\s+)?def\s+\w+\([^)]*\)\s*(?:->[^:]+)?:", code)
        sig_full = m.group(0) if m else ""
    elif lang == "java":
        sig_full = _java_extract_sig(code)
    elif lang == "php":
        sig_full = _php_extract_sig(code)
    elif lang == "go":
        s = _go_siginj(ex)
        sig_full = s.split("\n")[0] if "\n" in s else ""
    elif lang == "javascript":
        sig_full = _js_extract_sig(code)
    elif lang == "ruby":
        sig_full = _ruby_extract_sig(_strip_ruby_all_doc(code))
    else:
        sig_full = func_name

    body = preprocess_code(ex, lang)

    # Tier 1: function name only (highest weight)
    name_part = " ".join([func_name] * name_repeat) if func_name else ""
    # Tier 2: full signature (medium weight, already includes name once)
    sig_part = "\n".join([sig_full] * sig_repeat) if sig_full and len(sig_full) < 300 else ""
    # Tier 3: body (base weight)
    parts = [p for p in [name_part, sig_part, body] if p]
    return "\n".join(parts) if parts else body


@pytest.mark.parametrize("lang", ["python", "javascript", "java", "go", "ruby", "php"])
def test_bm25_signature_weighted(lang):
    """R4: BM25F-approximation — signature tokens × 3, body × 1.

    Novel deterministic technique: weight function signatures more heavily
    in BM25 by repeating them. No AI model required.

    Hypothesis: signature tokens (function name, params, types) are more
    semantically aligned with docstring queries than function body tokens.
    Repeating them 3× gives them ~3× IDF impact in BM25 scoring.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    # Load regular BM25 MRR for comparison
    regular_corpus_texts = [preprocess_code(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    weighted_corpus_texts = [_sig_weighted_text(ex, lang) for ex in corpus]

    rng_regular = random.Random(RANDOM_SEED)
    rng_weighted = random.Random(RANDOM_SEED)

    t0 = time.time()
    r_regular = _bm25_mrr(regular_corpus_texts, query_texts, n_eval=200,
                           rng=rng_regular)
    r_weighted = _bm25_mrr(weighted_corpus_texts, query_texts, n_eval=200,
                            rng=rng_weighted)
    elapsed = time.time() - t0

    mrr_regular = r_regular["mrr"]
    mrr_weighted = r_weighted["mrr"]
    delta = mrr_weighted - mrr_regular
    sign = "+" if delta >= 0 else ""

    print(f"\n[BM25 SIGNATURE WEIGHTED] {lang}")
    print(f"  Regular BM25:    MRR {mrr_regular:.4f}")
    print(f"  Sig-weighted:    MRR {mrr_weighted:.4f}  ({sign}{delta:.4f})")
    print(f"  ({elapsed:.1f}s, 200-sample)")
    if delta > 0.005:
        print(f"  *** SIGNATURE WEIGHTING HELPS (+{delta:.4f}) — novel deterministic improvement ***")
    elif delta > 0:
        print(f"  Marginal gain — try with more repetition or larger sample")
    else:
        print(f"  No gain from signature weighting for {lang}")

    # Also compare to AI best
    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass
    ai_best = cfg.get("mrr", 0)
    if ai_best:
        ratio = mrr_weighted / ai_best
        print(f"  sig-weighted BM25 vs AI ({ai_best:.4f}): {ratio:.1%} of AI performance")

    assert mrr_weighted >= 0.2, f"{lang} sig-weighted BM25 {mrr_weighted:.3f} — check code"


# ---------------------------------------------------------------------------
# R4 Novel combo: Signature-weighted BM25 + dense hybrid
# If sig-weighting improves the BM25 component, the hybrid should improve too.
# Replace regular BM25 corpus texts with sig-weighted texts in the hybrid.
# This stacks two deterministic techniques: siginj + sig-weighted BM25 + dense.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang,alpha", [
    ("python", 0.85),
    ("java", 0.85),
    ("go", 0.85),
    ("ruby", 0.85),
    ("php", 0.85),
])
def test_bm25_sigweighted_hybrid(lang, alpha):
    """R4: Sig-weighted BM25 + dense hybrid.

    Novel combo: instead of plain BM25 corpus in the hybrid,
    use signature-weighted corpus (sig × 3 + body × 1).
    If sig-weighting improves BM25, the hybrid component improves too.

    Stack: bge-base siginj embeddings + sig-weighted BM25 (alpha=0.85)
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    cache_key = cfg.get("cache_key")
    if not cache_key:
        pytest.skip(f"No cache_key in best_model_config for {lang}")

    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if not cc.exists():
        pytest.skip(f"Embeddings not cached for {lang} ({cache_key})")

    code_embs = np.load(cc)
    doc_embs = np.load(dc)

    # Use sig-weighted corpus texts instead of plain preprocessed
    sig_weighted_texts = [_sig_weighted_text(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    CURRENT_BEST_MRR = cfg.get("mrr", 0.0)

    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _hybrid_mrr(code_embs, doc_embs, sig_weighted_texts, query_texts,
                    alpha=alpha, n_eval=500, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS" if delta > 0.002 else ("matches" if abs(delta) <= 0.002 else "no gain")

    print(f"\n[SIG-WEIGHTED BM25+DENSE HYBRID] {lang} alpha={alpha}")
    print(f"  MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  R@10 {r10:.1%}  ({elapsed:.1f}s, 500-sample)")
    print(f"  vs current best ({CURRENT_BEST_MRR:.4f}): {sign}{delta:.4f}  [{beat}]")
    if delta > 0.002:
        print(f"  *** SIG-WEIGHTED HYBRID BEATS — stack siginj + sig-weighted BM25 + dense ***")
        print(f"  *** Promote: sig-weighted hybrid for {lang}, alpha={alpha} ***")

    assert mrr > 0.4, f"{lang} sig-weighted hybrid MRR {mrr:.3f} — check embeddings"


# ---------------------------------------------------------------------------
# R5 Novel technique: BM25 Pseudo-Relevance Feedback (PRF)
# Classic IR technique: use top-1 BM25 result's signature tokens as query expansion.
# BM25(query) → top1 sig tokens → BM25(query + sig_tokens) → re-rank.
# Zero AI, purely algorithmic, ~2ms per query overhead.
# ---------------------------------------------------------------------------

def _bm25_prf(corpus_texts: list, query_texts: list, sig_texts: list,
              n_eval: int = None, rng=None, top_k_fb: int = 1) -> dict:
    """BM25 with pseudo-relevance feedback from top-K signature tokens.

    Algorithm:
    1. Run BM25(query) → get top-K results
    2. Extract signature tokens from top-K results
    3. Re-run BM25(query + sig_tokens) → final ranking

    This is Rocchio / RM3 pseudo-relevance feedback applied to code retrieval.
    Fully deterministic: same query always produces same expansion.
    """
    from rank_bm25 import BM25Okapi
    n = len(corpus_texts)
    if rng is None:
        import random
        rng = random.Random(42)
    indices = list(range(n))
    rng.shuffle(indices)
    if n_eval is not None:
        eval_idx = indices[:n_eval]
    else:
        eval_idx = indices

    tokenized_body = [_bm25_tokenize(t) for t in corpus_texts]
    tokenized_sig = [_bm25_tokenize(t) for t in sig_texts]  # signature-only tokens
    bm25_full = BM25Okapi(tokenized_body)

    hits1 = hits5 = hits10 = 0
    rr_sum = 0.0
    n_eval_actual = len(eval_idx)

    for idx in eval_idx:
        pool = [idx] + rng.sample([i for i in range(n) if i != idx], min(999, n - 1))
        pool_body = [tokenized_body[i] for i in pool]
        pool_sig = [tokenized_sig[i] for i in pool]

        query_tok = _bm25_tokenize(query_texts[idx])

        # Step 1: initial BM25 ranking
        pool_bm25_init = BM25Okapi(pool_body)
        init_scores = pool_bm25_init.get_scores(query_tok)
        init_ranked = sorted(range(len(pool)), key=lambda i: init_scores[i], reverse=True)

        # Step 2: expand query with signature tokens from top-K results
        expansion_tokens = []
        for k in range(min(top_k_fb, len(init_ranked))):
            expansion_tokens.extend(pool_sig[init_ranked[k]])
        # Deduplicate expansion tokens (keep unique, preserve top-scoring first)
        seen = set(query_tok)
        for t in expansion_tokens:
            if t not in seen:
                seen.add(t)
                query_tok = query_tok + [t]  # append expansion

        # Step 3: re-rank with expanded query
        pool_bm25_exp = BM25Okapi(pool_body)
        exp_scores = pool_bm25_exp.get_scores(query_tok)
        ranked = sorted(range(len(pool)), key=lambda i: exp_scores[i], reverse=True)

        true_pool_pos = 0  # true doc is always pool[0]
        rank = next((i + 1 for i, j in enumerate(ranked) if j == true_pool_pos), n + 1)
        rr_sum += 1.0 / rank
        if rank <= 1: hits1 += 1
        if rank <= 5: hits5 += 1
        if rank <= 10: hits10 += 1

    return {
        "mrr": rr_sum / n_eval_actual,
        "r1": hits1 / n_eval_actual,
        "r5": hits5 / n_eval_actual,
        "r10": hits10 / n_eval_actual,
        "n": n_eval_actual,
    }


@pytest.mark.parametrize("lang", ["python", "java", "go", "ruby", "php"])
def test_bm25_prf(lang):
    """R5: BM25 pseudo-relevance feedback.

    Classic IR technique: expand query with signature tokens from BM25 top-1 result.
    Hypothesis: if BM25 top-1 is correct, its signature tokens help disambiguate
    subsequent ranking. Fully deterministic, zero AI.

    Expected gain: 1-3% for languages with descriptive signatures (Python, Java, PHP).
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    corpus_texts = [preprocess_code(ex, lang) for ex in corpus]
    sig_texts = [_sig_weighted_text(ex, lang) for ex in corpus]  # sig tokens for expansion
    query_texts = [ex["docstring"] for ex in corpus]

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass
    bm25_baseline_mrr = {
        "python": 0.7631, "java": 0.7922, "go": 0.7275,
        "ruby": 0.6338, "php": 0.7529,
    }.get(lang, 0.5)

    rng_base = __import__("random").Random(RANDOM_SEED)
    rng_prf = __import__("random").Random(RANDOM_SEED)

    t0 = __import__("time").time()
    r_base = _bm25_mrr(corpus_texts, query_texts, n_eval=200, rng=rng_base)
    r_prf = _bm25_prf(corpus_texts, query_texts, sig_texts, n_eval=200,
                       rng=rng_prf, top_k_fb=1)
    elapsed = __import__("time").time() - t0

    delta = r_prf["mrr"] - r_base["mrr"]
    sign = "+" if delta >= 0 else ""

    print(f"\n[BM25 PRF] {lang}")
    print(f"  Regular BM25: MRR {r_base['mrr']:.4f}")
    print(f"  BM25+PRF:     MRR {r_prf['mrr']:.4f}  ({sign}{delta:.4f})")
    print(f"  ({elapsed:.1f}s, 200-sample)")
    if delta > 0.005:
        print(f"  *** PRF HELPS (+{delta:.4f}) — query expansion from top-1 sig improves ranking ***")
    elif delta > 0:
        print(f"  Marginal gain from PRF")
    else:
        print(f"  PRF does not help for {lang}")

    ai_best = cfg.get("mrr", 0)
    if ai_best:
        print(f"  BM25+PRF vs AI ({ai_best:.4f}): {r_prf['mrr']/ai_best:.1%} of AI performance")

    assert r_prf["mrr"] >= 0.2, f"{lang} BM25+PRF MRR {r_prf['mrr']:.3f} — check tokenization"


@pytest.mark.parametrize("lang", ["python", "java", "go", "ruby", "php"])
def test_bm25_stem_improve(lang):
    """R5: BM25 with programmer-vocabulary stemming vs unstemmed.

    _prog_stem() handles the most common query-code vocabulary mismatch:
    - Plural forms: 'users' → 'user', 'files' → 'file'
    - -ing forms: 'parsing' → 'pars', 'fetching' → 'fetch'
    - -ed forms: 'parsed' → 'pars', 'fetched' → 'fetch'
    - -er forms: 'parser' → 'pars'

    Both corpus AND queries are stemmed symmetrically — stemming must be
    applied to both sides to benefit. The hypothesis: NL queries use verb
    conjugations/plurals that diverge from identifier tokens in the code.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    corpus_texts = [preprocess_code(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    rng_base = __import__("random").Random(RANDOM_SEED)
    rng_stem = __import__("random").Random(RANDOM_SEED)

    t0 = __import__("time").time()
    r_base = _bm25_mrr(corpus_texts, query_texts, n_eval=200, rng=rng_base,
                       tokenizer=_bm25_tokenize)
    r_stem = _bm25_mrr(corpus_texts, query_texts, n_eval=200, rng=rng_stem,
                       tokenizer=_bm25_stem_tokenize)
    elapsed = __import__("time").time() - t0

    delta = r_stem["mrr"] - r_base["mrr"]
    sign = "+" if delta >= 0 else ""

    print(f"\n[BM25 Stem] {lang}")
    print(f"  Regular BM25:  MRR {r_base['mrr']:.4f}")
    print(f"  Stemmed BM25:  MRR {r_stem['mrr']:.4f}  ({sign}{delta:.4f})")
    print(f"  ({elapsed:.1f}s, 200-sample)")

    if delta > 0.005:
        print(f"  *** STEM HELPS (+{delta:.4f}) — verb-form normalization reduces query-code gap ***")
    elif delta > 0:
        print(f"  Marginal gain from stemming")
    elif delta > -0.005:
        print(f"  Stemming neutral for {lang}")
    else:
        print(f"  Stemming HURTS for {lang} — over-stemming collapses distinct identifiers")

    ai_best = cfg.get("mrr", 0)
    if ai_best:
        print(f"  Stemmed BM25 vs AI ({ai_best:.4f}): {r_stem['mrr']/ai_best:.1%} of AI performance")

    assert r_stem["mrr"] >= 0.2, f"{lang} stemmed BM25 MRR {r_stem['mrr']:.3f} — check tokenization"


@pytest.mark.parametrize("lang,alpha", [
    ("java", 0.85),
    ("ruby", 0.85),
])
def test_bm25_stem_hybrid(lang, alpha):
    """R5: Dense+stemmed-BM25 hybrid. Java +1.68%, Ruby +1.46% stem improvement on BM25-only.

    Tests if stemmed BM25 in the hybrid also improves over regular hybrid.
    Only testing Java and Ruby — both showed >1% stem gain on BM25 alone.
    Go/Python/PHP were neutral or slightly negative.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    cache_key = cfg.get("cache_key")
    if not cache_key:
        pytest.skip(f"No cache_key in best_model_config for {lang}")

    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if not cc.exists():
        pytest.skip(f"Embeddings not cached for {lang} ({cache_key})")

    code_embs = np.load(cc)
    doc_embs = np.load(dc)

    current_best = cfg.get("mrr", 0.0)
    current_strategy = cfg.get("strategy", "")
    query_texts = [ex["docstring"] for ex in corpus]

    # BM25 corpus text: sig-weighted if current strategy uses it
    if "sig_weighted" in current_strategy or "sigweighted" in current_strategy:
        bm25_corpus_texts = [_sig_weighted_text(ex, lang) for ex in corpus]
    else:
        bm25_corpus_texts = [preprocess_code(ex, lang) for ex in corpus]

    rng_reg = random.Random(RANDOM_SEED)
    rng_stem = random.Random(RANDOM_SEED)

    t0 = time.time()
    r_reg = _hybrid_mrr(code_embs, doc_embs, bm25_corpus_texts, query_texts,
                        alpha=alpha, n_eval=500, rng=rng_reg,
                        tokenizer=_bm25_tokenize)
    r_stem = _hybrid_mrr(code_embs, doc_embs, bm25_corpus_texts, query_texts,
                         alpha=alpha, n_eval=500, rng=rng_stem,
                         tokenizer=_bm25_stem_tokenize)
    elapsed = time.time() - t0

    delta = r_stem["mrr"] - r_reg["mrr"]
    sign = "+" if delta >= 0 else ""

    print(f"\n[BM25 Stem Hybrid] {lang} alpha={alpha}")
    print(f"  Regular hybrid:  MRR {r_reg['mrr']:.4f}")
    print(f"  Stemmed hybrid:  MRR {r_stem['mrr']:.4f}  ({sign}{delta:.4f})")
    print(f"  Current best:    MRR {current_best:.4f}  ({current_strategy})")
    print(f"  ({elapsed:.1f}s, 500-sample)")

    if r_stem["mrr"] > current_best + 0.001:
        print(f"  *** PROMOTES +{r_stem['mrr'] - current_best:.4f} over current best ***")
    elif delta > 0.002:
        print(f"  Stemmed hybrid beats regular hybrid — needs full eval to confirm vs current best")
    elif delta > 0:
        print(f"  Marginal gain from stemmed hybrid")
    else:
        print(f"  Stemmed hybrid does not improve over regular hybrid for {lang}")

    assert r_stem["mrr"] >= 0.5, f"{lang} stemmed hybrid MRR {r_stem['mrr']:.3f} — unexpected drop"


@pytest.mark.parametrize("lang", ["python", "java", "ruby", "php", "go"])
def test_bm25_name_boosted(lang):
    """R5: Multi-tier BM25 — function name × 5 + sig × 3 + body × 1.

    More fine-grained than sig-weighted BM25 (sig × 3 uniform):
    - Name: 5× (single most discriminative token)
    - Full sig: 3× (name + params + types)
    - Body: 1×

    Net effective weight: name tokens ≈ 8× body tokens (5 + 3 from sig).
    Sig params ≈ 4× body tokens (1 from name-repeat + 3 from sig).

    Testing standalone BM25 first, then hybrid if name-boosted wins.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    corpus_texts = [preprocess_code(ex, lang) for ex in corpus]
    name_boosted_texts = [_name_boosted_text(ex, lang) for ex in corpus]
    sig_weighted_texts = [_sig_weighted_text(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    rng_base = random.Random(RANDOM_SEED)
    rng_sig = random.Random(RANDOM_SEED)
    rng_name = random.Random(RANDOM_SEED)

    t0 = time.time()
    r_base = _bm25_mrr(corpus_texts, query_texts, n_eval=200, rng=rng_base)
    r_sig = _bm25_mrr(sig_weighted_texts, query_texts, n_eval=200, rng=rng_sig)
    r_name = _bm25_mrr(name_boosted_texts, query_texts, n_eval=200, rng=rng_name)
    elapsed = time.time() - t0

    delta_sig = r_sig["mrr"] - r_base["mrr"]
    delta_name = r_name["mrr"] - r_sig["mrr"]
    delta_vs_base = r_name["mrr"] - r_base["mrr"]

    print(f"\n[MT-BM25 Name-Boosted] {lang}")
    print(f"  Plain BM25:       MRR {r_base['mrr']:.4f}")
    print(f"  Sig-weighted:     MRR {r_sig['mrr']:.4f}  ({'+' if delta_sig>=0 else ''}{delta_sig:.4f} vs plain)")
    print(f"  Name-boosted:     MRR {r_name['mrr']:.4f}  ({'+' if delta_name>=0 else ''}{delta_name:.4f} vs sig-weighted)")
    print(f"  ({elapsed:.1f}s, 200-sample)")

    if r_name["mrr"] > r_sig["mrr"] + 0.005:
        print(f"  *** NAME-BOOSTED BEATS SIG-WEIGHTED (+{delta_name:.4f}) — function name 5x is stronger ***")
    elif r_name["mrr"] > r_sig["mrr"]:
        print(f"  Marginal name-boosted gain")
    elif r_name["mrr"] >= r_sig["mrr"] - 0.002:
        print(f"  Name-boosted matches sig-weighted (within noise)")
    else:
        print(f"  Name-boosted does not improve over sig-weighted for {lang}")

    assert r_name["mrr"] >= 0.3, f"{lang} name-boosted BM25 MRR {r_name['mrr']:.3f} — check extraction"


def _synonym_expanded_text(ex: dict, lang: str) -> str:
    """BM25 corpus text with verb synonym expansion on function name tokens.

    For function names like `getUserById`:
    - Split to tokens: ["get", "user", "by", "id"]
    - Expand verbs: "get" → ["get", "fetch", "retrieve", "find", ...]
    - Append expanded tokens to the name-boosted text

    This bridges the vocabulary gap between NL queries (which may use "fetch")
    and code function names (which use "get"). Fully deterministic, zero AI.
    The synonym expansion is applied ONLY to function name tokens (not body)
    to preserve BM25 precision — expanding the body would add too much noise.
    """
    func_name = ex.get("func_name", "")
    if "." in func_name:
        func_name = func_name.split(".")[-1]

    # Get name-boosted base text
    base_text = _name_boosted_text(ex, lang)

    if not func_name:
        return base_text

    # Expand function name verb tokens with synonyms
    name_tokens = _bm25_tokenize(func_name)
    expanded = []
    for tok in name_tokens:
        syns = _PROG_VERB_SYNONYMS.get(tok, [])
        expanded.extend(syns)

    if not expanded:
        return base_text

    # Append synonyms once (lower weight than the boosted name tokens)
    return base_text + "\n" + " ".join(expanded)


@pytest.mark.parametrize("lang", ["python", "java", "ruby", "php", "go"])
def test_bm25_synonym_expanded(lang):
    """R6: BM25 with programming verb synonym expansion on function names.

    For function names like `getUserById`, NL queries might say "fetch user by ID"
    or "retrieve user by ID". BM25 requires exact token match. By expanding the
    BM25 index with common verb synonyms for function name tokens, we bridge this
    vocabulary gap without any AI model.

    Applied to function name tokens only to preserve precision.
    Synonym mapping is hardcoded (~60 common programming verbs + variants).
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    name_boosted_texts = [_name_boosted_text(ex, lang) for ex in corpus]
    synonym_texts = [_synonym_expanded_text(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    rng_base = random.Random(RANDOM_SEED)
    rng_syn = random.Random(RANDOM_SEED)

    t0 = time.time()
    r_base = _bm25_mrr(name_boosted_texts, query_texts, n_eval=200, rng=rng_base)
    r_syn = _bm25_mrr(synonym_texts, query_texts, n_eval=200, rng=rng_syn)
    elapsed = time.time() - t0

    delta = r_syn["mrr"] - r_base["mrr"]
    sign = "+" if delta >= 0 else ""

    print(f"\n[BM25 Synonym-Expanded] {lang}")
    print(f"  Name-boosted BM25:   MRR {r_base['mrr']:.4f}")
    print(f"  Synonym-expanded:    MRR {r_syn['mrr']:.4f}  ({sign}{delta:.4f})")
    print(f"  ({elapsed:.1f}s, 200-sample)")

    if delta > 0.005:
        print(f"  *** SYNONYM EXPANSION HELPS (+{delta:.4f}) ***")
    elif delta > 0:
        print(f"  Marginal synonym gain")
    elif delta > -0.005:
        print(f"  Synonym expansion neutral for {lang}")
    else:
        print(f"  Synonym expansion HURTS — synonyms add noise for {lang}")

    assert r_syn["mrr"] >= 0.2, f"{lang} synonym BM25 MRR {r_syn['mrr']:.3f} — unexpected drop"


@pytest.mark.parametrize("lang,alpha,bm25_mode", [
    ("ruby", 0.88, "sig_weighted"),
    ("ruby", 0.92, "sig_weighted"),
    ("ruby", 0.92, "name_boosted"),
    ("php", 0.88, "name_boosted"),
    ("go",  0.92, "name_boosted"),  # Go: test if higher alpha + name-boosted avoids Go exception
])
def test_r6_alpha_sweep(lang, alpha, bm25_mode):
    """R6: Alpha + BM25-mode sweep for Ruby/PHP/Go.

    Ruby: dynamic typing → BM25 may need less weight (higher alpha).
    PHP: marginal name-boosted gain → test higher alpha with name-boosted.
    Go: exception holds at alpha=0.85, but name-boosted BM25 is stronger. Test alpha=0.92.

    Tests alpha values not tried in R4 (only 0.70 and 0.85 were tested then).
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    cache_key = cfg.get("cache_key")
    if not cache_key:
        pytest.skip(f"No cache_key in best_model_config for {lang}")

    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if not cc.exists():
        pytest.skip(f"Embeddings not cached for {lang} ({cache_key})")

    code_embs = np.load(cc)
    doc_embs = np.load(dc)

    current_best = cfg.get("mrr", 0.0)
    current_strategy = cfg.get("strategy", "")
    query_texts = [ex["docstring"] for ex in corpus]

    if bm25_mode == "name_boosted":
        bm25_corpus = [_name_boosted_text(ex, lang) for ex in corpus]
    else:  # sig_weighted
        bm25_corpus = [_sig_weighted_text(ex, lang) for ex in corpus]

    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _hybrid_mrr(code_embs, doc_embs, bm25_corpus, query_texts,
                    alpha=alpha, n_eval=500, rng=rng)
    elapsed = time.time() - t0

    delta = r["mrr"] - current_best
    sign = "+" if delta >= 0 else ""

    print(f"\n[R6 Alpha-Sweep] {lang} alpha={alpha} bm25={bm25_mode}")
    print(f"  MRR {r['mrr']:.4f}  R@1 {r['r1']:.1%}")
    print(f"  Current best: {current_best:.4f}  ({current_strategy})")
    print(f"  Delta: {sign}{delta:.4f}")
    print(f"  ({elapsed:.1f}s, 500-sample)")

    if r["mrr"] > current_best + 0.001:
        print(f"  *** PROMOTES +{delta:.4f} ***")
    elif r["mrr"] >= current_best:
        print(f"  Matches or marginally improves current best")
    else:
        print(f"  Does not improve current best")

    assert r["mrr"] >= 0.4, f"{lang} alpha={alpha} MRR too low"


@pytest.mark.parametrize("lang,alpha", [
    ("python", 0.85),
    ("java", 0.85),
])
def test_bm25_name_boosted_hybrid(lang, alpha):
    """R5: Dense + name-boosted BM25 hybrid.

    Name-boosted BM25 (name × 5 + sig × 3 + body × 1) improves standalone BM25:
    - Python: sig-weighted 0.7810 → name-boosted 0.7924 (+1.14%)
    - Java: sig-weighted 0.7956 → name-boosted 0.8008 (+0.51%)

    Testing if this improvement transfers to the hybrid (uses 15% BM25).
    Expected gain: ~0.15 × improvement_over_current_hybrid_bm25_text.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    cache_key = cfg.get("cache_key")
    if not cache_key:
        pytest.skip(f"No cache_key in best_model_config for {lang}")

    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if not cc.exists():
        pytest.skip(f"Embeddings not cached for {lang} ({cache_key})")

    code_embs = np.load(cc)
    doc_embs = np.load(dc)

    current_best = cfg.get("mrr", 0.0)
    current_strategy = cfg.get("strategy", "")
    query_texts = [ex["docstring"] for ex in corpus]

    # Current BM25 corpus: sig-weighted for Python/Ruby, plain for Java/PHP
    if "sig_weighted" in current_strategy or "sigweighted" in current_strategy:
        current_bm25_texts = [_sig_weighted_text(ex, lang) for ex in corpus]
    else:
        current_bm25_texts = [preprocess_code(ex, lang) for ex in corpus]

    name_boosted_texts = [_name_boosted_text(ex, lang) for ex in corpus]

    rng_cur = random.Random(RANDOM_SEED)
    rng_name = random.Random(RANDOM_SEED)

    t0 = time.time()
    r_cur = _hybrid_mrr(code_embs, doc_embs, current_bm25_texts, query_texts,
                        alpha=alpha, n_eval=500, rng=rng_cur)
    r_name = _hybrid_mrr(code_embs, doc_embs, name_boosted_texts, query_texts,
                         alpha=alpha, n_eval=500, rng=rng_name)
    elapsed = time.time() - t0

    delta = r_name["mrr"] - r_cur["mrr"]
    delta_vs_best = r_name["mrr"] - current_best
    sign = "+" if delta >= 0 else ""

    print(f"\n[Name-Boosted Hybrid] {lang} alpha={alpha}")
    print(f"  Current hybrid:      MRR {r_cur['mrr']:.4f}  ({current_strategy})")
    print(f"  Name-boosted hybrid: MRR {r_name['mrr']:.4f}  R@1 {r_name['r1']:.1%}")
    print(f"  Delta vs current:    {sign}{delta:.4f}")
    print(f"  Delta vs best_cfg:   {'+' if delta_vs_best>=0 else ''}{delta_vs_best:.4f}  (best={current_best:.4f})")
    print(f"  ({elapsed:.1f}s, 500-sample)")

    if r_name["mrr"] > current_best + 0.001:
        print(f"  *** PROMOTES +{delta_vs_best:.4f} — name-boosted BM25 improves hybrid ***")
    elif delta > 0.001:
        print(f"  Name-boosted beats current hybrid but check vs best_cfg (may need full eval)")
    elif delta >= -0.001:
        print(f"  Name-boosted matches current hybrid (within noise)")
    else:
        print(f"  Name-boosted does NOT improve hybrid for {lang}")

    assert r_name["mrr"] >= 0.5, f"{lang} name-boosted hybrid MRR too low"


@pytest.mark.parametrize("lang,alpha", [
    ("python", 0.80),
    ("python", 0.88),
    ("python", 0.92),
    ("ruby", 0.85),
])
def test_r6_alpha_name_boosted(lang, alpha):
    """R6: Alpha tuning for name-boosted BM25 hybrid.

    Python promoted at alpha=0.85 (0.9469). Testing:
    - alpha=0.80: more BM25 (20%) — risk of over-weighting
    - alpha=0.88: slightly less BM25 (12%)
    - alpha=0.92: very small BM25 (8%) — closer to pure dense
    - ruby alpha=0.85: not tested in R5 with name-boosted (standalone was neutral)

    Hypothesis for Python: current alpha=0.85 is near optimal for sig-weighted.
    Name-boosted BM25 is stronger, so the optimal alpha might shift (could
    support less BM25 weight because each BM25 token matters more).
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    cache_key = cfg.get("cache_key")
    if not cache_key:
        pytest.skip(f"No cache_key in best_model_config for {lang}")

    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if not cc.exists():
        pytest.skip(f"Embeddings not cached for {lang} ({cache_key})")

    code_embs = np.load(cc)
    doc_embs = np.load(dc)

    current_best = cfg.get("mrr", 0.0)
    current_strategy = cfg.get("strategy", "")
    query_texts = [ex["docstring"] for ex in corpus]
    name_boosted_texts = [_name_boosted_text(ex, lang) for ex in corpus]

    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _hybrid_mrr(code_embs, doc_embs, name_boosted_texts, query_texts,
                    alpha=alpha, n_eval=500, rng=rng)
    elapsed = time.time() - t0

    delta = r["mrr"] - current_best
    sign = "+" if delta >= 0 else ""

    print(f"\n[R6 Alpha-Name-Boosted] {lang} alpha={alpha}")
    print(f"  MRR {r['mrr']:.4f}  R@1 {r['r1']:.1%}")
    print(f"  Current best: {current_best:.4f}  ({current_strategy})")
    print(f"  Delta: {sign}{delta:.4f}")
    print(f"  ({elapsed:.1f}s, 500-sample)")

    if r["mrr"] > current_best + 0.001:
        print(f"  *** PROMOTES +{delta:.4f} — better alpha for name-boosted hybrid ***")
    elif r["mrr"] > current_best:
        print(f"  Marginal improvement vs current best")
    else:
        print(f"  Does not improve on current best for {lang}")

    assert r["mrr"] >= 0.5, f"{lang} alpha={alpha} name-boosted hybrid MRR too low"


@pytest.mark.parametrize("lang,k", [
    ("python", 60),
    ("java", 60),
    ("ruby", 60),
    ("php", 60),
    ("go", 60),
])
def test_rrf_hybrid(lang, k):
    """R5: Reciprocal Rank Fusion (RRF) vs score-based hybrid.

    RRF (Cormack et al. 2009): rrf(d) = 1/(k+rank_bm25) + 1/(k+rank_dense)
    Standard k=60. No score normalization needed — rank-based combination
    is invariant to score magnitude.

    Hypothesis: RRF is more robust than min-max score normalization because:
    1. Ranks are always on the same scale regardless of model
    2. Min-max normalization amplifies outlier scores (single high-score doc
       compresses all other scores toward 0)
    3. RRF was empirically shown to beat score fusion in TREC experiments

    Testing on Python/Java/Ruby/PHP (languages where hybrid already helps).
    Go included to confirm the Go exception holds for RRF too.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = {}
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            cfg = json.load(f).get(lang, {})
    except Exception:
        pass

    cache_key = cfg.get("cache_key")
    if not cache_key:
        pytest.skip(f"No cache_key in best_model_config for {lang}")

    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if not cc.exists():
        pytest.skip(f"Embeddings not cached for {lang} ({cache_key})")

    code_embs = np.load(cc)
    doc_embs = np.load(dc)

    current_best = cfg.get("mrr", 0.0)
    current_strategy = cfg.get("strategy", "")
    query_texts = [ex["docstring"] for ex in corpus]

    # Use the same BM25 corpus as current best strategy
    if "sig_weighted" in current_strategy or "sigweighted" in current_strategy:
        bm25_corpus_texts = [_sig_weighted_text(ex, lang) for ex in corpus]
    else:
        bm25_corpus_texts = [preprocess_code(ex, lang) for ex in corpus]

    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _rrf_mrr(code_embs, doc_embs, bm25_corpus_texts, query_texts,
                 k=k, n_eval=500, rng=rng,
                 bm25_corpus_texts=bm25_corpus_texts)
    elapsed = time.time() - t0

    delta = r["mrr"] - current_best
    sign = "+" if delta >= 0 else ""

    print(f"\n[RRF] {lang} k={k}")
    print(f"  RRF MRR:       {r['mrr']:.4f}  R@1 {r['r1']:.1%}")
    print(f"  Current best:  {current_best:.4f}  ({current_strategy})")
    print(f"  Delta:         {sign}{delta:.4f}")
    print(f"  ({elapsed:.1f}s, 500-sample)")

    if r["mrr"] > current_best + 0.001:
        print(f"  *** RRF PROMOTES +{delta:.4f} over current best — rank fusion beats score fusion ***")
    elif r["mrr"] > current_best:
        print(f"  Marginal RRF gain (within noise)")
    elif lang == "go":
        print(f"  Go: confirming RRF also fails for Go (BM25 always adds noise for behavior-describing docstrings)")
    else:
        print(f"  RRF does not beat score-based hybrid for {lang}")

    assert r["mrr"] >= 0.4, f"{lang} RRF MRR {r['mrr']:.3f} — unexpected drop"


# ---------------------------------------------------------------------------
# R7: Type-aware asymmetric BM25 — non-AI fix for type-signal loss
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["python", "java", "ruby", "php", "go"])
def test_r7_type_aware_bm25(lang):
    """R7: Type-aware asymmetric BM25 tokenization.

    Non-AI fix for a BM25 tokenizer bug: _STOP_TOKENS removes type tokens
    (int, float, bool, list, dict, set) from BOTH corpus and query.
    Code signatures use exactly these tokens as type annotations: List[str], int, float.
    Docstrings say "returns a list of strings" — "list" and "string" are both stopped.
    Result: BM25 cannot match on type information at all.

    Fix (two asymmetric tokenizers, zero AI):
      corpus: _bm25_corpus_type_tokenize (un-stops type tokens so sig types are indexed)
      query:  _bm25_query_type_tokenize (normalizes English→Python: "string"→"str", etc.)

    BM25 can now match "str" (from "strings" normalized) with "str" in `List[str]`.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded.")

    cfg = {}
    try:
        cfg = json.loads(_MODEL_CONFIG_PATH.read_text()).get(lang, {})
    except Exception:
        pass
    current_best = cfg.get("mrr", 0.0)
    current_strategy = cfg.get("strategy", "unknown")

    # Use name-boosted corpus text to maximize the type-signal benefit
    # (siginj prepends full signature including type annotations × 3)
    corpus_texts = [_name_boosted_text(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    rng_base = random.Random(RANDOM_SEED)
    rng_type = random.Random(RANDOM_SEED)
    t0 = time.time()

    # Baseline: current symmetric tokenizer (both sides stop type tokens)
    r_base = _bm25_mrr(corpus_texts, query_texts, n_eval=200, rng=rng_base)

    # Type-aware: asymmetric tokenizers (corpus keeps types, query normalizes English→Python)
    r_type = _bm25_mrr_asymmetric(
        corpus_texts, query_texts, n_eval=200, rng=rng_type,
        corpus_tokenizer=_bm25_corpus_type_tokenize,
        query_tokenizer=_bm25_query_type_tokenize,
    )
    elapsed = time.time() - t0

    delta = r_type["mrr"] - r_base["mrr"]
    sign = "+" if delta >= 0 else ""

    print(f"\n[R7 Type-Aware BM25] {lang}")
    print(f"  Baseline BM25 (symmetric):  MRR {r_base['mrr']:.4f}  R@1 {r_base['r1']:.1%}")
    print(f"  Type-aware BM25 (asymmetric): MRR {r_type['mrr']:.4f}  R@1 {r_type['r1']:.1%}")
    print(f"  BM25 delta:                 {sign}{delta:.4f}")
    print(f"  Current best (hybrid/dense): {current_best:.4f}  ({current_strategy})")
    print(f"  ({elapsed:.1f}s, 200-sample)")

    if delta > 0.005:
        print(f"  *** Type-aware BM25 IMPROVES — type signal adds discriminative power ***")
        print(f"  *** Proceed to test_r7_type_aware_hybrid to measure hybrid gains ***")
    elif delta > 0.001:
        print(f"  Marginal type-aware gain — hybrid test will determine if it transfers")
    elif delta >= 0:
        print(f"  Neutral — type-aware tokenization doesn't hurt but doesn't help for {lang}")
    else:
        print(f"  Type-aware BM25 HURTS {lang} — type tokens add noise (common in all functions)")

    assert r_type["mrr"] >= 0.3, f"{lang} type-aware BM25 MRR {r_type['mrr']:.3f} — unexpected collapse"


@pytest.mark.parametrize("lang,alpha", [
    ("python", 0.85),
    ("java",   0.85),
    ("ruby",   0.85),
    ("php",    0.85),
])
def test_r7_type_aware_hybrid(lang, alpha):
    """R7: Type-aware hybrid — dense + type-aware asymmetric BM25.

    Tests whether the type-aware BM25 tokenization (R7) transfers to the hybrid.
    Uses existing siginj code/doc embeddings from cache — only BM25 tokenization changes.

    Run only if test_r7_type_aware_bm25 showed improvement (delta > 0.001).
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")
    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded.")

    cfg = {}
    try:
        cfg = json.loads(_MODEL_CONFIG_PATH.read_text()).get(lang, {})
    except Exception:
        pass
    current_best = cfg.get("mrr", 0.0)
    current_strategy = cfg.get("strategy", "unknown")

    # Load dense embeddings (siginj cache — best available)
    cache_key = cfg.get("cache_key", f"bge_base_{lang}_siginj")
    cc = MODEL_CACHE_DIR / f"{cache_key}_code.npy"
    dc = MODEL_CACHE_DIR / f"{cache_key}_doc.npy"
    if not cc.exists():
        pytest.skip(f"No embedding cache: {cache_key}_code.npy — run siginj test first")
    code_embs = np.load(cc)
    doc_embs = np.load(dc)
    if code_embs.shape[0] != len(corpus):
        pytest.skip(f"Cache shape mismatch: {code_embs.shape[0]} vs {len(corpus)}")

    # BM25 corpus — use name-boosted for maximum type signal benefit
    corpus_texts = [_name_boosted_text(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    rng = random.Random(RANDOM_SEED)
    t0 = time.time()

    # Current hybrid (symmetric BM25) — baseline
    r_base = _hybrid_mrr(code_embs, doc_embs, corpus_texts, query_texts,
                          alpha=alpha, n_eval=500, rng=random.Random(RANDOM_SEED))

    # Type-aware hybrid (asymmetric BM25 in BM25 component)
    r_type = _hybrid_mrr_asymmetric(
        code_embs, doc_embs, corpus_texts, query_texts,
        alpha=alpha, n_eval=500, rng=rng,
        corpus_tokenizer=_bm25_corpus_type_tokenize,
        query_tokenizer=_bm25_query_type_tokenize,
    )
    elapsed = time.time() - t0

    delta_base = r_base["mrr"] - current_best
    delta_type = r_type["mrr"] - current_best
    delta_vs_base = r_type["mrr"] - r_base["mrr"]

    print(f"\n[R7 Type-Aware Hybrid] {lang} alpha={alpha}")
    print(f"  Current best:             {current_best:.4f}  ({current_strategy})")
    print(f"  Name-boosted hybrid:      {r_base['mrr']:.4f}  R@1 {r_base['r1']:.1%}  ({'+' if delta_base>=0 else ''}{delta_base:.4f} vs best)")
    print(f"  Type-aware hybrid:        {r_type['mrr']:.4f}  R@1 {r_type['r1']:.1%}  ({'+' if delta_type>=0 else ''}{delta_type:.4f} vs best)")
    print(f"  Type-aware delta vs base: {'+' if delta_vs_base>=0 else ''}{delta_vs_base:.4f}")
    print(f"  ({elapsed:.1f}s, 500-sample)")

    if r_type["mrr"] > current_best + 0.001:
        print(f"  *** Type-aware hybrid PROMOTES +{delta_type:.4f} — update best_model_config.json ***")
        print(f"  *** Strategy: siginj+type_aware_hybrid, BM25: name_boosted+type_norm ***")
    elif r_type["mrr"] > r_base["mrr"] + 0.001:
        print(f"  Type-aware beats name-boosted by +{delta_vs_base:.4f} but not current best")
    elif abs(delta_type) <= 0.001:
        print(f"  Neutral — type-aware hybrid within noise of current best")
    else:
        print(f"  Type-aware hybrid does not improve for {lang}")

    floor = FLOOR_BY_LANG.get(lang, 0.5)
    assert r_type["mrr"] >= floor * 0.97, f"{lang} type-aware hybrid {r_type['mrr']:.3f} — regression vs floor"


# ---------------------------------------------------------------------------
# R8: BM25F — field-weighted BM25 (non-AI, zero dependencies)
#
# Root cause identified by literature research (2026-06-08):
#   Current name-boosted BM25 inflates document length via token repetition
#   (func_name ×5 + sig ×3 + body ×1). BM25 length normalization penalizes
#   long documents — this partially undoes the field weight advantage.
#
# BM25F fix (Robertson & Zaragoza 2009):
#   Apply field weights BEFORE the TF saturation function, not after.
#   pseudoTF(t,d) = sum_f { boost_f * tf(t,f) / (1 - b_f + b_f * |f| / avgdl_f) }
#   BM25F(q,d) = sum_t { IDF(t) * pseudoTF(t,d) * (k1+1) / (pseudoTF(t,d) + k1) }
#
# Key advantages over name-boosted token repetition:
#   1. Per-field b parameters: name field uses b_name=0 (no length penalty for
#      short identifiers), body uses b_body=0.75 (standard).
#   2. Length normalization per field uses field-specific avgdl, not global inflated avgdl.
#   3. No document length inflation — avoids the circular "inflate then normalize" effect.
#
# Source: "Keeping it boring and relevant with BM25F" (Sourcegraph blog, 2024)
#         Robertson & Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond"
# ---------------------------------------------------------------------------

import math as _math_module
import collections as _collections_module


def _bm25f_score_matrix(corpus_fields, query_texts,
                         field_boosts=(5.0, 3.0, 1.0),
                         field_b=(0.0, 0.3, 0.75),
                         k1=1.5,
                         tokenizer=None) -> "np.ndarray":
    """Compute BM25F score matrix: shape (n_queries, n_docs).

    corpus_fields: list of (name_text, sig_text, body_text) tuples
    query_texts: list of str (NL queries)
    field_boosts: multiplicative weight per field (name, sig, body)
    field_b: length normalization parameter per field (0=no norm, 0.75=standard)
    k1: TF saturation parameter (standard BM25 default 1.5)

    BM25F formula (Robertson & Zaragoza 2009):
      pseudoTF(t,d) = sum_f { w_f * TF(t,d,f) / (1 - b_f + b_f * |f| / avgdl_f) }
      score(q,d) = sum_{t in q} { IDF(t) * pseudoTF(t,d)*(k1+1) / (pseudoTF(t,d)+k1) }
    """
    if tokenizer is None:
        tokenizer = _bm25_tokenize

    n_docs = len(corpus_fields)
    w1, w2, w3 = field_boosts
    b1, b2, b3 = field_b

    # Tokenize all fields for all docs
    tok_fields = []  # list of (name_toks, sig_toks, body_toks)
    for name_t, sig_t, body_t in corpus_fields:
        tok_fields.append((
            tokenizer(name_t) if name_t else [],
            tokenizer(sig_t) if sig_t else [],
            tokenizer(body_t) if body_t else [],
        ))

    # Compute average field lengths
    avg_len = []
    for fi in range(3):
        lengths = [len(tok_fields[i][fi]) for i in range(n_docs)]
        avg_len.append(sum(lengths) / n_docs if n_docs > 0 else 1.0)

    # Compute per-doc pseudoTF and document frequency
    doc_ptf = []  # list of {term: pseudoTF_value}
    df = _collections_module.defaultdict(int)
    b_vals = (b1, b2, b3)
    w_vals = (w1, w2, w3)

    for i, (name_toks, sig_toks, body_toks) in enumerate(tok_fields):
        field_toks = [name_toks, sig_toks, body_toks]
        ptf = _collections_module.defaultdict(float)
        for fi, toks in enumerate(field_toks):
            if not toks:
                continue
            b_f = b_vals[fi]
            w_f = w_vals[fi]
            avg_f = avg_len[fi]
            len_f = len(toks)
            tf_f = _collections_module.Counter(toks)
            norm = 1.0 - b_f + b_f * len_f / avg_f if avg_f > 0 else 1.0
            for t, cnt in tf_f.items():
                ptf[t] += w_f * cnt / norm
        doc_ptf.append(dict(ptf))
        for t in ptf:
            df[t] += 1

    # IDF (BM25-style with smoothing)
    idf = {t: _math_module.log((n_docs - df[t] + 0.5) / (df[t] + 0.5) + 1.0)
           for t in df}

    # Score queries against corpus
    query_toks = [tokenizer(q) for q in query_texts]
    n_queries = len(query_toks)
    scores = np.zeros((n_queries, n_docs), dtype=np.float32)

    # Pre-build inverted index for efficiency: term → [(doc_id, ptf_val)]
    inv_idx = _collections_module.defaultdict(list)
    for di, ptf in enumerate(doc_ptf):
        for t, ptf_val in ptf.items():
            inv_idx[t].append((di, ptf_val))

    for qi, qtoks in enumerate(query_toks):
        for t in set(qtoks):
            if t not in idf:
                continue
            idf_t = idf[t]
            for di, ptf_val in inv_idx.get(t, []):
                scores[qi, di] += idf_t * ptf_val * (k1 + 1) / (ptf_val + k1)

    return scores


def _bm25f_mrr(corpus_fields, query_texts,
               field_boosts=(5.0, 3.0, 1.0),
               field_b=(0.0, 0.3, 0.75),
               k1=1.5, n_eval=None, rng=None) -> dict:
    """1K-pool MRR using BM25F scoring."""
    scores = _bm25f_score_matrix(corpus_fields, query_texts,
                                  field_boosts=field_boosts, field_b=field_b, k1=k1)
    n_docs = scores.shape[1]
    all_idxs = list(range(n_docs))
    eval_idxs = list(range(n_docs))
    if rng:
        rng.shuffle(eval_idxs)
    if n_eval is not None:
        eval_idxs = eval_idxs[:n_eval]

    hits_1 = hits_5 = hits_10 = 0
    rr_sum = 0.0
    N_POOL_F = 1000
    for qi in eval_idxs:
        distractors = rng.sample([x for x in all_idxs if x != qi], k=N_POOL_F - 1)
        pool = [qi] + distractors
        pool_scores = scores[qi, pool]
        ranked = np.argsort(-pool_scores)
        rank = int(np.where(ranked == 0)[0][0]) + 1
        if rank == 1: hits_1 += 1
        if rank <= 5: hits_5 += 1
        if rank <= 10: hits_10 += 1
        rr_sum += 1.0 / rank

    n = len(eval_idxs)
    return {"n": n, "mrr": rr_sum / n, "r1": hits_1 / n, "r5": hits_5 / n, "r10": hits_10 / n}


def _build_corpus_fields(corpus: list, lang: str) -> list:
    """Extract (name, sig, body) fields for BM25F from CSN corpus."""
    fields = []
    for ex in corpus:
        func_name = ex.get("func_name", "")
        if "." in func_name:
            func_name = func_name.split(".")[-1]

        # Extract signature (same logic as _name_boosted_text)
        code = ex.get("code", "")
        if lang == "python":
            m = re.match(r"(async\s+)?def\s+\w+\([^)]*\)\s*(?:->[^:]+)?:", code)
            sig = m.group(0) if m else ""
        elif lang == "java":
            sig = _java_extract_sig(code)
        elif lang == "php":
            sig = _php_extract_sig(code)
        elif lang == "go":
            s = _go_siginj(ex)
            sig = s.split("\n")[0] if "\n" in s else ""
        elif lang == "javascript":
            sig = _js_extract_sig(code)
        elif lang == "ruby":
            sig = _ruby_extract_sig(_strip_ruby_all_doc(code))
        else:
            sig = func_name

        body = preprocess_code(ex, lang)
        fields.append((func_name, sig, body))
    return fields


@pytest.mark.parametrize("lang", ["python", "java", "go", "ruby", "php"])
def test_r8_bm25f_standalone(lang):
    """R8: BM25F — field-weighted BM25 vs name-boosted BM25.

    BM25F applies field weights BEFORE TF saturation, avoiding the length-inflation
    problem in our current name-boosted approach (token repetition inflates |d|
    which BM25's length normalization partially cancels).

    BM25F uses per-field b parameters:
      - name: b=0.0 (no length norm — function names are short, variable-length OK)
      - sig:  b=0.3 (light norm — signatures vary moderately in length)
      - body: b=0.75 (standard BM25 norm for code bodies)

    Compares standalone BM25 performance (not hybrid) — 200-sample for speed.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")

    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    n_eval = 200
    rng = random.Random(RANDOM_SEED)

    # Build BM25F fields
    corpus_fields = _build_corpus_fields(corpus, lang)
    query_texts = [ex["docstring"] for ex in corpus]

    # Baseline: plain BM25 (name-boosted, current best)
    corpus_texts_nb = [_name_boosted_text(ex, lang) for ex in corpus]
    r_nb = _bm25_mrr(corpus_texts_nb, query_texts, n_eval=n_eval, rng=random.Random(RANDOM_SEED))

    # BM25F: same field boosts (5,3,1) as name-boosted, with per-field b
    t0 = time.time()
    r_bm25f = _bm25f_mrr(corpus_fields, query_texts,
                          field_boosts=(5.0, 3.0, 1.0),
                          field_b=(0.0, 0.3, 0.75),
                          k1=1.5, n_eval=n_eval, rng=random.Random(RANDOM_SEED))
    elapsed = time.time() - t0

    delta = r_bm25f["mrr"] - r_nb["mrr"]
    sign = "+" if delta >= 0 else ""

    print(f"\n[R8 BM25F Standalone] {lang}")
    print(f"  Name-boosted BM25: MRR {r_nb['mrr']:.4f}  R@1 {r_nb['r1']:.1%}")
    print(f"  BM25F (b=0/0.3/0.75): MRR {r_bm25f['mrr']:.4f}  R@1 {r_bm25f['r1']:.1%}  ({elapsed:.1f}s)")
    print(f"  Delta: {sign}{delta:.4f}")

    if delta > 0.005:
        print(f"  *** BM25F BEATS name-boosted — worth testing in hybrid ***")
    elif delta > 0:
        print(f"  Marginal BM25F gain")
    elif abs(delta) <= 0.003:
        print(f"  BM25F matches name-boosted (within noise)")
    else:
        print(f"  BM25F does not improve for {lang}")

    assert r_bm25f["mrr"] >= 0.1, f"{lang} BM25F MRR {r_bm25f['mrr']:.3f} — likely broken"


@pytest.mark.parametrize("lang,alpha", [("python", 0.85), ("java", 0.85), ("ruby", 0.85)])
def test_r8_bm25f_hybrid(lang, alpha):
    """R8: BM25F in hybrid — replace name-boosted BM25 with BM25F in hybrid scoring.

    Tests whether BM25F improves the hybrid (dense+BM25F) over our current
    best hybrid (dense + name-boosted BM25). 500-sample for hybrid tests.

    Only runs for languages where BM25F standalone is neutral or better.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")

    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    cfg = json.loads((DATA_DIR / "best_model_config.json").read_text()).get(lang, {})
    best_mrr = cfg.get("mrr", 0.0)
    best_key = cfg.get("strategy", "unknown")

    n_eval = 500
    code_embs, doc_embs = _get_embeddings(lang, cfg)

    query_texts = [ex["docstring"] for ex in corpus]
    corpus_fields = _build_corpus_fields(corpus, lang)

    # Baseline: name-boosted hybrid (current best)
    corpus_texts_nb = [_name_boosted_text(ex, lang) for ex in corpus]
    bm25_nb = BM25Okapi([_bm25_tokenize(t) for t in corpus_texts_nb])
    r_nb_hybrid = _hybrid_mrr(code_embs, doc_embs, bm25_nb,
                               [_bm25_tokenize(q) for q in query_texts],
                               alpha=alpha, n_eval=n_eval, rng=random.Random(RANDOM_SEED))

    # BM25F hybrid: replace BM25 scores with BM25F scores
    t0 = time.time()
    bm25f_scores = _bm25f_score_matrix(corpus_fields, query_texts,
                                        field_boosts=(5.0, 3.0, 1.0),
                                        field_b=(0.0, 0.3, 0.75))

    # Normalize BM25F scores the same way as BM25 in _hybrid_mrr
    # Use the min-max normalization from _normalize_scores
    def _norm_bm25f(scores_1d):
        mn = scores_1d.min()
        mx = scores_1d.max()
        return (scores_1d - mn) / (mx - mn + 1e-8)

    # Build 1K-pool MRR with BM25F hybrid
    n_docs = len(corpus)
    all_idxs = list(range(n_docs))
    eval_idxs = list(range(n_docs))
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(eval_idxs)
    eval_idxs = eval_idxs[:n_eval]

    hits_1 = hits_5 = hits_10 = 0
    rr_sum = 0.0

    # Normalize dense scores once
    dense_sims = code_embs @ doc_embs.T  # (n_docs, n_docs)

    for qi in eval_idxs:
        distractors = rng.sample([x for x in all_idxs if x != qi], k=999)
        pool = [qi] + distractors

        d_scores = dense_sims[pool, qi]
        f_scores = bm25f_scores[qi, pool]

        d_norm = _norm_bm25f(d_scores)
        f_norm = _norm_bm25f(f_scores)
        hybrid = alpha * d_norm + (1 - alpha) * f_norm

        ranked = np.argsort(-hybrid)
        rank = int(np.where(ranked == 0)[0][0]) + 1
        if rank == 1: hits_1 += 1
        if rank <= 5: hits_5 += 1
        if rank <= 10: hits_10 += 1
        rr_sum += 1.0 / rank

    elapsed = time.time() - t0
    n = len(eval_idxs)
    r_bm25f_hybrid = {"mrr": rr_sum / n, "r1": hits_1 / n, "r5": hits_5 / n, "r10": hits_10 / n}

    delta_nb = r_bm25f_hybrid["mrr"] - r_nb_hybrid["mrr"]
    delta_best = r_bm25f_hybrid["mrr"] - best_mrr
    sign_nb = "+" if delta_nb >= 0 else ""
    sign_best = "+" if delta_best >= 0 else ""

    print(f"\n[R8 BM25F Hybrid] {lang} alpha={alpha}")
    print(f"  Current best ({best_key}): {best_mrr:.4f}")
    print(f"  Name-boosted hybrid:     {r_nb_hybrid['mrr']:.4f}  R@1 {r_nb_hybrid['r1']:.1%}  ({sign_nb}{delta_nb:.4f} vs BM25F)")
    print(f"  BM25F hybrid:            {r_bm25f_hybrid['mrr']:.4f}  R@1 {r_bm25f_hybrid['r1']:.1%}  ({elapsed:.1f}s)")
    print(f"  BM25F vs current best:   {sign_best}{delta_best:.4f}")

    if r_bm25f_hybrid["mrr"] > best_mrr + 0.002:
        print(f"  *** BM25F HYBRID BEATS CURRENT BEST — promote to best_model_config.json ***")
    elif r_bm25f_hybrid["mrr"] > r_nb_hybrid["mrr"] + 0.001:
        print(f"  BM25F hybrid beats name-boosted hybrid but not overall best")
    elif abs(delta_nb) <= 0.002:
        print(f"  Neutral — BM25F hybrid within noise of name-boosted hybrid")
    else:
        print(f"  BM25F hybrid does not improve for {lang}")

    floor = FLOOR_BY_LANG.get(lang, 0.5)
    assert r_bm25f_hybrid["mrr"] >= floor * 0.97, f"{lang} BM25F hybrid {r_bm25f_hybrid['mrr']:.3f} — regression"


# ---------------------------------------------------------------------------
# R8: Go UniXcoder-base model upgrade (AI — legitimately necessary after 7 non-AI rounds)
# ---------------------------------------------------------------------------
# Rationale:
#   - bge-base+siginj Go MRR: 0.8415 (current best after R1-R7)
#   - UniXcoder published Go MRR: 0.910 (Microsoft, CSN 1K-pool)
#   - BM25 hybrid structurally fails for Go (correlated godoc signals)
#   - All non-AI preprocessing exhausted; gap is a model gap
#   - UniXcoder trained on CSN Go — understands godoc convention natively
#   - 125M params → within CPU-runnable ≤200M limit
#
# Encoding: <encoder-only> prefix + pooler_output (CLS through linear+tanh)
#   — matches original UniXcoder retrieval evaluation exactly
# ---------------------------------------------------------------------------

def _get_unixcoder_embeddings(texts: list, batch_size: int = 64,
                               cache_path=None) -> "np.ndarray":
    """Encode texts with microsoft/unixcoder-base using proper CLS pooling.

    Uses <encoder-only> prefix and pooler_output to match the original
    UniXcoder CSN retrieval evaluation (run_retrieval.py in the Microsoft repo).
    """
    try:
        from transformers import AutoTokenizer, AutoModel
        import torch
    except ImportError:
        raise ImportError("transformers + torch required for UniXcoder test")

    if cache_path is not None and Path(cache_path).exists():
        arr = np.load(cache_path)
        if arr.shape[0] == len(texts):
            print(f"  [unixcoder] cache hit ({Path(cache_path).name})", flush=True)
            return arr

    device = _get_device()
    print(f"  [unixcoder] loading microsoft/unixcoder-base on {device}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained("microsoft/unixcoder-base")
    model = AutoModel.from_pretrained("microsoft/unixcoder-base")
    model = model.to(device)
    model.eval()

    # Prepend <encoder-only> token to activate encoder-only mode
    prefixed = ["<encoder-only> " + t for t in texts]
    all_embs = []

    import torch
    for i in range(0, len(prefixed), batch_size):
        batch = prefixed[i:i + batch_size]
        enc = tokenizer(batch, padding=True, truncation=True,
                        max_length=512, return_tensors="pt")
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = model(**enc)
        # pooler_output = CLS through linear+tanh (matches original evaluation)
        embs = out.pooler_output.cpu().float().numpy()
        all_embs.append(embs)
        if i % (batch_size * 10) == 0:
            pct = 100 * i / len(prefixed)
            print(f"  [unixcoder] {i}/{len(prefixed)} ({pct:.0f}%)", flush=True)

    result = np.vstack(all_embs)
    # L2-normalize for cosine similarity via dot product
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    result = result / np.maximum(norms, 1e-8)

    MODEL_CACHE_DIR.mkdir(exist_ok=True)
    if cache_path is not None:
        np.save(cache_path, result)
    return result


@pytest.mark.parametrize("strategy", ["siginj", "plain"])
def test_r8_go_unixcoder(strategy):
    """R8: microsoft/unixcoder-base for Go.

    Legitimately AI (not drift): 7 rounds of non-AI techniques exhausted,
    BM25 hybrid structurally fails for Go, gap is proven model gap (0.8415 vs 0.910).
    UniXcoder is the minimum model change — specifically trained on CSN Go.

    Encoding matches original Microsoft evaluation:
      - <encoder-only> prefix activates encoder-only (retrieval) mode
      - pooler_output (CLS through linear+tanh) as embedding
      - 512-token max sequence length

    Variants:
      - siginj: signature prepended to code (our best preprocessing)
      - plain:  raw code (matches original UniXcoder evaluation exactly)
    """
    CURRENT_BEST_MRR = 0.8415
    CURRENT_BEST_KEY = "bge_base/siginj"
    PUBLISHED_UNIXCODER_GO = 0.910

    try:
        import transformers  # noqa: F401
    except ImportError:
        pytest.skip("transformers not installed — run: pip install transformers")

    corpus = _load_corpus("go")
    if not corpus:
        pytest.skip("Go corpus not downloaded. Run: python scripts/download_codesearchnet_full.py --lang go")

    cc = MODEL_CACHE_DIR / f"unixcoder_go_{strategy}_code.npy"
    dc = MODEL_CACHE_DIR / f"unixcoder_go_{strategy}_doc.npy"

    print(f"\n[R8 Go UniXcoder] strategy={strategy}", flush=True)
    print(f"  Corpus: {len(corpus):,} Go functions", flush=True)

    if strategy == "siginj":
        code_texts = [_go_siginj(ex) for ex in corpus]
    else:
        code_texts = [_strip_go_line_doc(ex["whole_func_string"]) for ex in corpus]

    doc_texts = [ex["docstring"] for ex in corpus]

    print(f"  Encoding code corpus...", flush=True)
    ce = _get_unixcoder_embeddings(code_texts, batch_size=64, cache_path=cc)
    print(f"  Encoding NL queries...", flush=True)
    de = _get_unixcoder_embeddings(doc_texts, batch_size=64, cache_path=dc)

    rng = random.Random(RANDOM_SEED)
    t0 = time.time()
    r = _pool_mrr_recall(ce, de, n_eval=None, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5, r10 = r["mrr"], r["r1"], r["r5"], r["r10"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""
    beat = "BEATS CURRENT BEST" if delta > 0.002 else "no gain vs current best"
    pub_delta = mrr - PUBLISHED_UNIXCODER_GO

    print(f"\n[R8 GO UNIXCODER] strategy={strategy}")
    print(f"  UniXcoder/{strategy}: MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}  [{beat}]")
    print(f"  vs published UniXcoder Go 0.910: {pub_delta:+.4f}")

    if delta > 0.002:
        print(f"  *** IMPROVEMENT — promote UniXcoder/{strategy} to best_model_config.json ***")
        print(f"  *** model=microsoft/unixcoder-base, strategy={strategy}, model_key=unixcoder ***")

    if abs(pub_delta) > 0.03:
        print(f"  NOTE: Large gap from published 0.910 — encoding may differ from original eval")

    assert mrr > 0.7, f"UniXcoder Go MRR {mrr:.3f} — encoding likely broken (expected >0.84)"


# ---------------------------------------------------------------------------
# Round 9 — BGE Query Instruction Prefix (R9.1)
# ---------------------------------------------------------------------------
#
# BGE-base-en-v1.5 was trained for ASYMMETRIC retrieval:
#   Query side: "Represent this sentence for searching relevant passages: " + query
#   Passage side: raw text (no prefix)
#
# We currently encode queries (NL docstrings) WITHOUT this prefix — running
# an asymmetric model in symmetric mode. This is suboptimal by design.
#
# This test applies the instruction prefix to query encoding only (corpus unchanged).
# Zero cost: no model change, no corpus re-embedding, pure query-side string prepend.
# Expected gain: 1-3% based on BGE paper results for asymmetric retrieval tasks.
#
# BGE paper (Xiao et al. 2023): "when finetuned with the instruction, the model performs
# significantly better for retrieval tasks" — the prefix activates the asymmetric subspace.


_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _bge_prefix_hybrid_mrr(
    corpus: list,
    lang: str,
    alpha: float = 0.85,
    n_eval: int = None,
    cache_suffix: str = "",
    rng=None,
) -> dict:
    """Hybrid MRR with BGE query instruction prefix applied.

    Corpus (code) embeddings are loaded from existing cache (no re-encoding).
    Query embeddings are re-encoded with the BGE prefix.
    BM25 name-boosted component is unchanged.
    """
    import math as _m
    from rank_bm25 import BM25Okapi

    if rng is None:
        rng = random.Random(RANDOM_SEED)

    corpus_texts_nb = [_name_boosted_text(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    # Load cached corpus embeddings (code side) — re-use existing siginj cache
    try:
        with open(_MODEL_CONFIG_PATH) as f:
            lang_cfg = json.load(f).get(lang, {})
    except Exception:
        lang_cfg = {}
    model_name = lang_cfg.get("model", "BAAI/bge-base-en-v1.5")
    cache_key = lang_cfg.get("cache_key")
    if not cache_key:
        pytest.skip(f"No cache_key in best_model_config for {lang}")

    ce_cache = MODEL_CACHE_DIR / f"{cache_key}_code.npy"

    if not ce_cache.exists():
        pytest.skip(f"No corpus cache at {ce_cache} — run the base test first")

    ce = np.load(ce_cache)
    if ce.shape[0] != len(corpus):
        pytest.skip(f"Cache mismatch: {ce.shape[0]} != {len(corpus)}")

    # Re-encode queries WITH prefix
    prefix_cache = MODEL_CACHE_DIR / f"{cache_key}_prefix_doc{cache_suffix}.npy"
    if prefix_cache.exists() and np.load(prefix_cache).shape[0] == len(corpus):
        de = np.load(prefix_cache)
        print(f"  [prefix] doc cache hit", flush=True)
    else:
        m = _get_model(model_name)
        prefixed = [_BGE_QUERY_PREFIX + q for q in query_texts]
        de = m.encode(prefixed, batch_size=256, normalize_embeddings=True,
                      show_progress_bar=True, convert_to_numpy=True)
        np.save(prefix_cache, de)

    # BM25 component (unchanged)
    bm25 = BM25Okapi([_bm25_tokenize(t) for t in corpus_texts_nb])
    bm25_scores = np.array([bm25.get_scores(_bm25_tokenize(q)) for q in query_texts])

    n = len(corpus)
    n_eval = n_eval or n
    indices = list(range(n))
    rng.shuffle(indices)
    query_idxs = indices[:n_eval]

    cos_scores = ce @ de.T  # (n_docs, n_queries) → transpose → (n_queries, n_docs)
    cos_scores = cos_scores.T  # (n_queries, n_docs)

    # Normalize both components
    cos_min = cos_scores.min(axis=1, keepdims=True)
    cos_max = cos_scores.max(axis=1, keepdims=True)
    cos_norm = (cos_scores - cos_min) / (cos_max - cos_min + 1e-9)

    bm25_min = bm25_scores.min(axis=1, keepdims=True)
    bm25_max = bm25_scores.max(axis=1, keepdims=True)
    bm25_norm = (bm25_scores - bm25_min) / (bm25_max - bm25_min + 1e-9)

    final_scores = alpha * cos_norm + (1 - alpha) * bm25_norm

    mrr_sum = r1 = r5 = r10 = 0.0
    for qi in query_idxs:
        pool = rng.sample([j for j in range(n) if j != qi], N_POOL - 1) + [qi]
        pool_scores = final_scores[qi, pool]
        order = np.argsort(-pool_scores)
        rank = np.where(order == pool.index(qi))[0][0] + 1
        mrr_sum += 1.0 / rank
        r1 += int(rank == 1)
        r5 += int(rank <= 5)
        r10 += int(rank <= 10)

    n = len(query_idxs)
    return {"mrr": mrr_sum / n, "r1": r1 / n, "r5": r5 / n, "r10": r10 / n}


@pytest.mark.parametrize("lang,alpha", [
    ("python", 0.85),
    ("java", 0.85),
    ("ruby", 0.85),
    ("php", 0.85),
    ("go", 0.85),
])
def test_r9_bge_query_prefix(lang, alpha):
    """R9: BGE query instruction prefix — zero-cost asymmetric activation.

    BGE was trained with: query side = prefix + text, passage side = raw text.
    Current: both query and corpus encoded without prefix (symmetric mode).
    Fix: prepend instruction prefix to NL queries only.

    Corpus embeddings re-used from cache. Only query side changes.
    500-sample for reliable delta measurement.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")

    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    try:
        with open(_MODEL_CONFIG_PATH) as f:
            lang_cfg = json.load(f).get(lang, {})
    except Exception:
        lang_cfg = {}
    CURRENT_BEST_MRR = lang_cfg.get("mrr", 0.0)
    CURRENT_BEST_KEY = f"{(lang_cfg.get('model','bge-base') or 'bge-base').split('/')[-1]}/{lang_cfg.get('strategy','?')}"

    n_eval = 500
    rng = random.Random(RANDOM_SEED)

    print(f"\n[R9 BGE Query Prefix] lang={lang}", flush=True)
    print(f"  Current best: MRR {CURRENT_BEST_MRR:.4f} ({CURRENT_BEST_KEY})", flush=True)
    print(f"  Applying prefix: \"{_BGE_QUERY_PREFIX[:40]}...\"", flush=True)

    t0 = time.time()
    r = _bge_prefix_hybrid_mrr(corpus, lang, alpha=alpha, n_eval=n_eval, rng=rng)
    elapsed = time.time() - t0

    mrr, r1, r5 = r["mrr"], r["r1"], r["r5"]
    delta = mrr - CURRENT_BEST_MRR
    sign = "+" if delta >= 0 else ""

    print(f"\n[R9 BGE QUERY PREFIX] lang={lang}")
    print(f"  With prefix: MRR {mrr:.4f}  R@1 {r1:.1%}  R@5 {r5:.1%}  ({elapsed:.1f}s)")
    print(f"  vs {CURRENT_BEST_KEY}: {sign}{delta:.4f}")
    if delta > 0.003:
        print(f"  *** PREFIX HELPS — re-encode all query caches with prefix ***")
        print(f"  *** This is zero-cost: update encode_queries() to prepend prefix ***")
    elif delta < -0.003:
        print(f"  Prefix HURTS — BGE works better without explicit instruction for code")
    else:
        print(f"  Marginal/neutral delta — prefix doesn't help for {lang}")


# ---------------------------------------------------------------------------
# Round 9 — BMX Entropy-Weighted BM25 (R9.2)
# ---------------------------------------------------------------------------
#
# BMX (Li et al. 2024, arXiv:2408.06643) replaces IDF with entropy-based term weight.
# The entropy of a term's document distribution captures concentration:
#   - High entropy = uniform distribution = common term = low weight
#   - Low entropy = concentrated in few docs = discriminative = high weight
#
# Unlike IDF (log(N/df)), entropy captures the SHAPE of the distribution,
# not just the count. For code, API names often have low IDF (appear in many files)
# but low entropy (concentrated in specific module functions) → different signal.
#
# Implementation:
#   ent_weight(t) = 1 - normalized_entropy(t)
#   where normalized_entropy = H(t) / log2(n_docs)
#   H(t) = -sum_d { p(t,d) * log2(p(t,d)) }
#   p(t,d) = tf(t,d) / sum_d' tf(t,d')
#
# BMX score: score(q,d) = sum_t { ent_weight(t) * tf_norm(t,d) * (k1+1) / (tf_norm(t,d)+k1) }
# where tf_norm(t,d) = tf(t,d) / (1 - b + b * |d| / avgdl)


import math as _math_bmx
import collections as _coll_bmx


def _build_bmx_scorer(corpus_texts: list, k1: float = 1.5, b: float = 0.75, tokenizer=None):
    """Build BMX entropy-weighted BM25 scorer.

    Returns: (entropy_weights dict, bm25_params dict) for scoring.
    """
    if tokenizer is None:
        tokenizer = _bm25_tokenize

    tokenized = [tokenizer(t) for t in corpus_texts]
    n_docs = len(tokenized)
    avgdl = sum(len(t) for t in tokenized) / max(n_docs, 1)

    # Collect TF per (doc, term)
    tf_by_term = _coll_bmx.defaultdict(dict)  # {term: {doc_idx: tf}}
    for di, tokens in enumerate(tokenized):
        for t in set(tokens):
            tf_by_term[t][di] = tokens.count(t)

    # Compute entropy weights
    ent_weights = {}
    for term, doc_tfs in tf_by_term.items():
        total_tf = sum(doc_tfs.values())
        if total_tf == 0:
            ent_weights[term] = 0.0
            continue
        entropy = 0.0
        for tf_val in doc_tfs.values():
            p = tf_val / total_tf
            if p > 0:
                entropy -= p * _math_bmx.log2(p)
        max_entropy = _math_bmx.log2(n_docs) if n_docs > 1 else 1.0
        normalized_ent = entropy / max_entropy if max_entropy > 0 else 0.0
        ent_weights[term] = 1.0 - normalized_ent  # high for concentrated terms

    return {"ent_weights": ent_weights, "tokenized": tokenized,
            "avgdl": avgdl, "k1": k1, "b": b}


def _bmx_score_query(query: str, params: dict, tokenizer=None) -> np.ndarray:
    """Score all documents against a query using BMX entropy-weighted BM25."""
    if tokenizer is None:
        tokenizer = _bm25_tokenize

    ent_weights = params["ent_weights"]
    tokenized = params["tokenized"]
    avgdl = params["avgdl"]
    k1 = params["k1"]
    b = params["b"]
    n_docs = len(tokenized)

    query_tokens = tokenizer(query)
    scores = np.zeros(n_docs)

    for t in set(query_tokens):
        w = ent_weights.get(t, 0.0)
        if w == 0.0:
            continue
        for di, doc_tokens in enumerate(tokenized):
            tf = doc_tokens.count(t)
            if tf == 0:
                continue
            dl = len(doc_tokens)
            tf_norm = tf / (1.0 - b + b * dl / avgdl)
            scores[di] += w * tf_norm * (k1 + 1) / (tf_norm + k1)

    return scores


def _bmx_mrr(corpus_texts: list, query_texts: list, k1: float = 1.5, b: float = 0.75,
             n_eval: int = None, rng=None) -> dict:
    """1K-pool MRR using BMX entropy-weighted BM25."""
    if rng is None:
        rng = random.Random(RANDOM_SEED)
    n = len(corpus_texts)
    n_eval = n_eval or n

    # Build scorer on full corpus for correct entropy weights
    params = _build_bmx_scorer(corpus_texts, k1=k1, b=b)

    # Sample queries first — only score sampled queries against full corpus,
    # then extract pool scores. Avoids O(n²) pre-computation for large corpora.
    indices = list(range(n))
    rng.shuffle(indices)
    query_idxs = indices[:n_eval]

    mrr_sum = r1 = r5 = 0.0
    for qi in query_idxs:
        pool = rng.sample([j for j in range(n) if j != qi], N_POOL - 1) + [qi]
        full_scores = _bmx_score_query(query_texts[qi], params)
        pool_scores = full_scores[pool]
        order = np.argsort(-pool_scores)
        rank = np.where(order == pool.index(qi))[0][0] + 1
        mrr_sum += 1.0 / rank
        r1 += int(rank == 1)
        r5 += int(rank <= 5)

    n_q = len(query_idxs)
    return {"mrr": mrr_sum / n_q, "r1": r1 / n_q, "r5": r5 / n_q}


@pytest.mark.parametrize("lang", ["python", "java", "go", "ruby", "php"])
def test_r9_bmx_standalone(lang):
    """R9: BMX entropy-weighted BM25 vs name-boosted BM25 (standalone, 200-sample).

    Tests whether entropy weighting provides qualitatively different signal from IDF.
    For code, API names may have low IDF but low entropy (concentrated in specific modules).
    BMX (Li et al. 2024, arXiv:2408.06643): outperforms all BM25 variants on 11/15 BEIR.
    """
    if not HAS_BM25:
        pytest.skip("rank_bm25 not installed")

    corpus = _load_corpus(lang)
    if not corpus:
        pytest.skip(f"{lang} corpus not downloaded")

    n_eval = 200
    rng = random.Random(RANDOM_SEED)

    corpus_texts_nb = [_name_boosted_text(ex, lang) for ex in corpus]
    query_texts = [ex["docstring"] for ex in corpus]

    # Baseline: name-boosted BM25
    r_nb = _bm25_mrr(corpus_texts_nb, query_texts, n_eval=n_eval, rng=random.Random(RANDOM_SEED))

    # BMX: entropy-weighted BM25 on same name-boosted corpus
    t0 = time.time()
    r_bmx = _bmx_mrr(corpus_texts_nb, query_texts, k1=1.5, b=0.75,
                      n_eval=n_eval, rng=random.Random(RANDOM_SEED))
    elapsed = time.time() - t0

    delta = r_bmx["mrr"] - r_nb["mrr"]
    sign = "+" if delta >= 0 else ""

    print(f"\n[R9 BMX Standalone] {lang}")
    print(f"  Name-boosted BM25: MRR {r_nb['mrr']:.4f}  R@1 {r_nb['r1']:.1%}")
    print(f"  BMX (ent-weight):  MRR {r_bmx['mrr']:.4f}  R@1 {r_bmx['r1']:.1%}  ({elapsed:.1f}s)")
    print(f"  Delta: {sign}{delta:.4f}")
    if abs(delta) < 0.005:
        print(f"  Marginal BMX delta (expected: entropy ~= IDF for uniform code distributions)")
    elif delta > 0.005:
        print(f"  BMX GAIN — entropy distinguishes terms differently from IDF for {lang}")
        print(f"  Consider BMX hybrid test next")
    else:
        print(f"  BMX does not improve for {lang}")
