"""ClaudeBoost CoIR Evaluation

Wraps ClaudeBoost's per-language preprocessing pipeline into the CoIR model
interface. The "model" being evaluated is the preprocessing pipeline — the
underlying embedding models are off-the-shelf.

Innovation: AST-aware docstring stripping, function name prepending (S6),
C# PascalCase splitting (name_double_split), per-language model routing via
self-improving benchmark loop.

Run:
    python claudeboost_coir_eval.py
"""

import ast
import json
import re
import warnings
from pathlib import Path
from typing import List, Dict

import numpy as np
import torch

try:
    from sentence_transformers import SentenceTransformer
    HAS_ST = True
except ImportError:
    HAS_ST = False

# ---------------------------------------------------------------------------
# Preprocessing (mirrors test_codesearchnet_multilang.py exactly)
# ---------------------------------------------------------------------------

_BLOCK_COMMENT = re.compile(r"^\s*/\*\*?.*?\*/\s*", re.DOTALL)
_RUBY_DOC      = re.compile(r"^\s*=begin.*?=end\s*", re.DOTALL)
_TRIPLE_SLASH  = re.compile(r"^\s*///.*$", re.MULTILINE)
_CS_PASCAL     = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_CS_GENERICS   = re.compile(r"<[^>]{1,40}>")
_CS_USING      = re.compile(r"^\s*using\s+[\w.]+;\s*$", re.MULTILINE)
_CS_ATTR       = re.compile(r"^\s*\[.*?\]\s*$", re.MULTILINE)


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


def _strip_go_line_doc(code: str) -> str:
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
    code  = ex.get("code", ex.get("text", ""))
    name  = (ex.get("func_name") or ex.get("title", "")).strip()
    short = name.split(".")[-1] if "." in name else name
    base  = _cs_strip_doc(code)
    if strategy == "name_double_split":
        n = _cs_split_id(short)
        return f"{n} {n}\n\n{_cs_split_id(base)}" if n else _cs_split_id(base)
    # fallback S6
    return f"{short}\n\n{base}" if short else base


def strip_docstring(code: str, lang: str) -> str:
    if lang == "python":
        return _strip_docstring_python(code)
    if lang == "go":
        return _strip_go_line_doc(code)
    if lang == "ruby":
        return _strip_ruby_all_doc(code)
    if lang == "csharp":
        return _cs_strip_doc(code)
    return _BLOCK_COMMENT.sub("", code, count=1).strip()


def preprocess_code(ex: dict, lang: str) -> str:
    """Apply ClaudeBoost's strategy-aware preprocessing."""
    code = ex.get("code", ex.get("text", ""))
    if lang == "csharp":
        return _cs_preprocess(ex, "name_double_split")
    base = strip_docstring(code, lang)
    if lang == "python":
        return base
    name = ex.get("func_name", ex.get("title", ""))
    if name and "." in name:
        name = name.split(".")[-1]
    return f"{name}\n\n{base}" if name else base


# ---------------------------------------------------------------------------
# Language detection — each CoIR encode_corpus call is a single language
# ---------------------------------------------------------------------------

def _detect_language(texts: List[str]) -> str:
    """Heuristically detect language from a sample of code texts."""
    sample = "\n".join(texts[:30])
    # Go: package declaration + func keyword + := operator
    if re.search(r"\bpackage\s+\w+", sample) or (re.search(r"\bfunc\s+\w+", sample) and ":=" in sample):
        return "go"
    # PHP: dollar signs as variables, <?php or function $
    if "<?php" in sample or re.search(r"function\s+\w+\s*\([^)]*\$", sample) or sample.count("$") > 5:
        return "php"
    # Ruby: def + end (no colon after def line), or require, attr_
    if (re.search(r"\bdef\s+\w+", sample) and "end" in sample and
            not re.search(r"\bdef\s+\w+.*:$", sample, re.MULTILINE)):
        return "ruby"
    # Java: strong signals — import java, public class, @Override, throws
    if (re.search(r"\bimport\s+java\.", sample) or
            re.search(r"\bpublic\s+(class|interface|enum)\b", sample) or
            "@Override" in sample):
        return "java"
    # JavaScript: function keyword + common JS patterns, or arrow functions
    if (re.search(r"\bfunction\s+\w+\s*\(", sample) or
            re.search(r"(const|let|var)\s+\w+\s*=\s*(async\s+)?\(", sample) or
            "module.exports" in sample or "require(" in sample):
        return "javascript"
    # Python: def with colon, self, import style
    if re.search(r"\bdef\s+\w+\s*\([^)]*\)\s*:", sample):
        return "python"
    return "python"  # safe default


# ---------------------------------------------------------------------------
# Per-language model config (mirrors best_model_config.json routing)
# ---------------------------------------------------------------------------

CODESEARCH_MODEL = "flax-sentence-embeddings/st-codesearch-distilroberta-base"
BGE_BASE_MODEL   = "BAAI/bge-base-en-v1.5"

# csharp uses bge-base; all others use codesearch
MODEL_FOR_LANG = {
    "python":     CODESEARCH_MODEL,
    "javascript": CODESEARCH_MODEL,
    "java":       CODESEARCH_MODEL,
    "go":         CODESEARCH_MODEL,
    "ruby":       CODESEARCH_MODEL,
    "php":        CODESEARCH_MODEL,
    "csharp":     BGE_BASE_MODEL,
}


# ---------------------------------------------------------------------------
# ClaudeBoost CoIR encoder
# ---------------------------------------------------------------------------

class ClaudeBoostEncoder:
    """CoIR/MTEB model interface wrapping ClaudeBoost's preprocessing pipeline.

    The entity being benchmarked is the pipeline (docstring stripping,
    function name prepending, PascalCase splitting, model routing), not the
    underlying embedding models.
    """

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"\n[ClaudeBoost] Using device: {self.device}", flush=True)
        self._models: Dict[str, SentenceTransformer] = {}

    def _get_model(self, model_name: str) -> SentenceTransformer:
        if model_name not in self._models:
            print(f"[ClaudeBoost] Loading {model_name} on {self.device} ...", flush=True)
            self._models[model_name] = SentenceTransformer(
                model_name, device=self.device, trust_remote_code=True
            )
        return self._models[model_name]

    def encode_queries(
        self,
        queries: List[str],
        batch_size: int = 256,
        **kwargs,
    ) -> np.ndarray:
        """Natural-language docstring queries — encode with codesearch model."""
        model = self._get_model(CODESEARCH_MODEL)
        return model.encode(
            queries,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        )

    def encode_corpus(
        self,
        corpus: List[Dict[str, str]],
        batch_size: int = 256,
        **kwargs,
    ) -> np.ndarray:
        """Detect language, apply per-language preprocessing, encode with best model."""
        texts = [doc.get("text", "") for doc in corpus]
        titles = [doc.get("title", "") for doc in corpus]

        lang = _detect_language(texts)
        print(f"\n[ClaudeBoost] Detected language: {lang} ({len(corpus):,} docs)", flush=True)

        processed = []
        for text, title in zip(texts, titles):
            ex = {"text": text, "code": text, "func_name": title}
            processed.append(preprocess_code(ex, lang))

        model_name = MODEL_FOR_LANG.get(lang, CODESEARCH_MODEL)
        model = self._get_model(model_name)

        return model.encode(
            processed,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        )


# ---------------------------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import coir
    from coir.evaluation import COIR

    results_dir = Path("C:/Users/grayw/AppData/Local/Temp/coir_results_claudeboost")
    results_dir.mkdir(exist_ok=True)

    print("\n" + "="*60)
    print("ClaudeBoost CoIR Evaluation")
    print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none (CPU)'}")
    print("="*60 + "\n")

    model = ClaudeBoostEncoder()

    tasks = coir.get_tasks(tasks=["codesearchnet"])
    evaluation = COIR(tasks=tasks, batch_size=256)
    results = evaluation.run(model, output_folder=str(results_dir))

    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(json.dumps(results, indent=2))

    # Save results
    out = results_dir / "claudeboost_coir_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved to: {out}")
