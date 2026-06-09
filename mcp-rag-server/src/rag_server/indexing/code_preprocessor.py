"""Per-language code preprocessing for embedding quality.

Applies docstring stripping and optional signature injection (siginj) based on
the per-language strategy in best_model_config.json.

siginj: deterministically extract the method/function signature and prepend it
to the stripped code body before embedding. Works on asymmetric retrieval models
(BGE family) where query and document subspaces are geometrically separated —
document enrichment improves retrieval without corrupting query signals.

CPU-first: all preprocessing is deterministic and runs in microseconds.
No LLM, no GPU required.
"""

import ast
import json
import logging
import re
import warnings
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to best_model_config.json — written by the benchmark improvement loop.
# Two hops up from this file: src/rag_server/indexing/ → src/rag_server/ → src/ → mcp-rag-server/
_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "tests" / "data" / "best_model_config.json"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_TRIPLE_SLASH = re.compile(r"^\s*///.*$", re.MULTILINE)
_JAVA_ANNOTATION = re.compile(r"^\s*@\w+.*$", re.MULTILINE)


def _load_strategies() -> dict[str, str]:
    """Return {lang: strategy} from best_model_config.json, or {} if not found."""
    try:
        if _CONFIG_PATH.exists():
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            return {lang: info.get("strategy", "") for lang, info in raw.items()}
    except Exception as exc:
        logger.debug("code_preprocessor: could not load strategies: %s", exc)
    return {}


# Loaded once at import time; refresh by calling reload_strategies().
_STRATEGIES: dict[str, str] = _load_strategies()


def reload_strategies() -> None:
    """Re-read best_model_config.json. Call after updating the config at runtime."""
    global _STRATEGIES
    _STRATEGIES = _load_strategies()


# ---------------------------------------------------------------------------
# Python preprocessing
# ---------------------------------------------------------------------------

def _strip_docstring_python(code: str) -> str:
    """Remove leading docstring from the first function/class in the AST."""
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                if (node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    node.body.pop(0)
                    if not node.body:
                        node.body.append(ast.Pass())
        return ast.unparse(tree)
    except Exception:
        return code


def _python_extract_sig(node) -> str:
    """Reconstruct 'def name(params) -> return:' from an AST FunctionDef node."""
    args = node.args
    parts = []
    n_regular = len(args.posonlyargs) + len(args.args)
    for i, arg in enumerate(args.posonlyargs):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        defaults_start = n_regular - len(args.defaults)
        di = i - (defaults_start - len(args.posonlyargs))
        default = f"={ast.unparse(args.defaults[di])}" if 0 <= di < len(args.defaults) else ""
        parts.append(f"{arg.arg}{ann}{default}")
    if args.posonlyargs:
        parts.append("/")
    for i, arg in enumerate(args.args):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        global_i = len(args.posonlyargs) + i
        defaults_start = n_regular - len(args.defaults)
        di = global_i - defaults_start
        default = f"={ast.unparse(args.defaults[di])}" if 0 <= di < len(args.defaults) else ""
        parts.append(f"{arg.arg}{ann}{default}")
    if args.vararg:
        ann = f": {ast.unparse(args.vararg.annotation)}" if args.vararg.annotation else ""
        parts.append(f"*{args.vararg.arg}{ann}")
    elif args.kwonlyargs:
        parts.append("*")
    for i, arg in enumerate(args.kwonlyargs):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        kwd = args.kw_defaults[i]
        default = f"={ast.unparse(kwd)}" if kwd is not None else ""
        parts.append(f"{arg.arg}{ann}{default}")
    if args.kwarg:
        ann = f": {ast.unparse(args.kwarg.annotation)}" if args.kwarg.annotation else ""
        parts.append(f"**{args.kwarg.arg}{ann}")
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(parts)}){ret}:"


def _python_siginj(content: str) -> str:
    """Python siginj: prepend extracted def-line to docstring-stripped code."""
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = _python_extract_sig(node)
                stripped = _strip_docstring_python(content)
                return f"{sig}\n\n{stripped}"
    except Exception:
        pass
    return _strip_docstring_python(content)


# ---------------------------------------------------------------------------
# Java preprocessing
# ---------------------------------------------------------------------------

def _java_extract_sig(code: str) -> str:
    """Extract Java method declaration by skipping leading annotations/blanks."""
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


def _java_siginj(content: str) -> str:
    """Java siginj: strip Javadoc, prepend extracted declaration line."""
    stripped = _BLOCK_COMMENT.sub("", content, count=1).strip()
    sig = _java_extract_sig(stripped)
    if sig and len(sig) < 300:
        return f"{sig}\n\n{stripped}"
    return stripped


# ---------------------------------------------------------------------------
# C# preprocessing
# ---------------------------------------------------------------------------

def _csharp_siginj(content: str) -> str:
    """C# siginj: strip XML doc comments, prepend first non-attribute declaration."""
    stripped = _TRIPLE_SLASH.sub("", content).strip()
    lines = stripped.split("\n")
    collecting = False
    sig_lines = []
    for line in lines:
        s = line.strip()
        if not s:
            if not collecting:
                continue
        if s.startswith("[") and not collecting:
            continue
        collecting = True
        sig_lines.append(s)
        if "{" in s or ";" in s:
            break
    sig = " ".join(sig_lines)
    for ch in ["{", ";"]:
        pos = sig.find(ch)
        if pos >= 0:
            sig = sig[:pos].strip()
    if sig and len(sig) < 300:
        return f"{sig}\n\n{stripped}"
    return stripped


# ---------------------------------------------------------------------------
# Go preprocessing
# ---------------------------------------------------------------------------

_GO_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


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


def _go_extract_sig(code: str) -> str:
    """Extract Go function signature: lines from 'func' keyword up to '{'.

    Handles simple and multi-line Go signatures including receiver methods:
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


def _go_siginj(content: str) -> str:
    """Go siginj: strip godoc comments, prepend extracted func signature.

    Go has explicit types for all params and return values:
        func FindUserByID(id int64, db *sql.DB) (*User, error)
    Works with asymmetric models (BGE family) — confirmed pattern from Python/Java.
    """
    stripped = _strip_go_line_doc(content)
    sig = _go_extract_sig(stripped)
    if sig and len(sig) < 400:
        return f"{sig}\n\n{stripped}"
    return stripped


# ---------------------------------------------------------------------------
# Ruby preprocessing
# ---------------------------------------------------------------------------

_RUBY_DOC = re.compile(r"^=begin.*?^=end", re.MULTILINE | re.DOTALL)


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


def _ruby_extract_sig(code: str) -> str:
    """Extract Ruby method signature: first 'def' line.

    Ruby has no type annotations — sig is method name + param names only.
    Less informative than Go/Java but still bridges vocabulary gap.
    """
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("def "):
            return stripped
    return ""


def _ruby_siginj(content: str) -> str:
    """Ruby siginj: strip # comments, prepend def line.

    Works with asymmetric models (BGE family).
    Gain is smaller than typed languages (no type annotations in sigs).
    """
    stripped = _strip_ruby_all_doc(content)
    sig = _ruby_extract_sig(stripped)
    if sig and len(sig) < 200:
        return f"{sig}\n\n{stripped}"
    return stripped


def _ruby_query_sig(content: str) -> str:
    """Ruby query-side preprocessing: extract def line, split snake_case to NL words.

    def calculate_discount_rate(price, base) → "calculate discount rate price base"

    The split words match docstring vocabulary ("calculate the discount rate for a
    given price") more directly than the raw snake_case identifier.
    Only processes the first def line; returns content unchanged if no def found.
    """
    for line in content.split('\n'):
        stripped_line = line.strip()
        if not stripped_line.startswith('def '):
            continue
        m = re.match(r'def\s+(?:self\.)?(\w+)\s*(?:\(([^)]*)\))?', stripped_line)
        if not m:
            continue
        method_name = m.group(1).rstrip('!?')
        params_str = m.group(2) or ''
        name_parts = [p.lower() for p in method_name.split('_') if p]
        param_parts = []
        for tok in re.findall(r'\b([a-zA-Z_]\w*)\b', params_str):
            param_parts.extend(p.lower() for p in tok.split('_') if p)
        all_words = name_parts + param_parts[:6]
        prefix = ' '.join(w for w in all_words if len(w) > 1)
        if prefix.strip():
            return f"{prefix}\n\n{content}"
        break
    return content


# ---------------------------------------------------------------------------
# PHP preprocessing
# ---------------------------------------------------------------------------

def _php_extract_sig(code: str) -> str:
    """Extract PHP function signature: lines from 'function' keyword up to '{'.

    Modern PHP has type hints:
        function calcTax(array $items, float $rate): Decimal
    Type annotations captured — similar benefit to Go/Java siginj.
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


def _php_siginj(content: str) -> str:
    """PHP siginj: strip Javadoc, prepend function signature.

    PHP modern type hints: function calcTax(array $items, float $rate): Decimal
    Works with asymmetric models (BGE family).
    """
    sig = _php_extract_sig(content)
    stripped = _BLOCK_COMMENT.sub("", content, count=1).strip()
    if sig and len(sig) < 400:
        return f"{sig}\n\n{stripped}"
    return stripped


# ---------------------------------------------------------------------------
# JavaScript preprocessing
# ---------------------------------------------------------------------------

_CAMEL_SPLIT_RE = re.compile(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])')


def _camel_split(name: str) -> str:
    """Split camelCase/PascalCase identifier into lowercase words.

    Examples:
        computeUniqueAsyncExpiration → compute unique async expiration
        StatisticLabel               → statistic label
        XMLParser                    → xml parser
        getUserById                  → get user by id
    """
    parts = _CAMEL_SPLIT_RE.sub(' ', name)
    parts = re.sub(r'[_\-]+', ' ', parts)
    return ' '.join(p.lower() for p in parts.split() if p)


def _js_extract_func_name(code: str) -> str:
    """Extract function name from JavaScript code.

    Handles named functions (67%), async functions, and const/let/var arrow forms.
    Searches only the first few lines to avoid matching variables inside the body.
    """
    # Search first 500 chars — covers the declaration line for all common forms
    head = code[:500]
    m = re.search(r'(?:async\s+)?function\s+(\w+)\s*\(', head)
    if m:
        return m.group(1)
    # const/let/var assignment — FIRST LINE ONLY to avoid body variable false positives
    first_line = code.split('\n')[0]
    m = re.search(
        r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\(|async\s+\()',
        first_line,
    )
    if m:
        return m.group(1)
    return ''


def _js_siginj(content: str) -> str:
    """JavaScript query siginj: split camelCase function name, prepend as NL words.

    CamelCase names are opaque compound tokens to BGE
    (computeUniqueAsyncExpiration → 1-4 subwords) but docstrings describe them
    with plain English words ("Creates a unique async expiration time").
    Splitting bridges the lexical gap deterministically.

    For anonymous/unextracted functions: extract param names as fallback.
    """
    name = _js_extract_func_name(content)
    if name:
        split_name = _camel_split(name)
        if split_name and split_name != name.lower():
            return f"{split_name}\n\n{content}"
    # Fallback: extract camelCase-split param names from first (...)
    m = re.search(r'\(([^)]{1,120})\)', content.split('\n')[0])
    if m:
        param_names = re.findall(r'\b([a-zA-Z_]\w*)\b', m.group(1))
        skip = {'async', 'function', 'const', 'let', 'var', 'return'}
        param_names = [p for p in param_names if p not in skip][:4]
        if param_names:
            split_params = ' '.join(_camel_split(p) for p in param_names if _camel_split(p))
            if split_params.strip():
                return f"{split_params}\n\n{content}"
    return content


# ---------------------------------------------------------------------------
# Default preprocessing (unrecognized languages)
# ---------------------------------------------------------------------------

_KNOWN_LANGUAGES = frozenset({
    "python", "java", "csharp", "go", "ruby", "php", "javascript",
})


def _default_normalize(content: str) -> str:
    """Generic preprocessing for unrecognized languages.

    Applies whitespace normalization and camelCase/snake_case splitting.
    Does NOT apply siginj signature extraction — cannot parse unknown syntax.
    """
    content = re.sub(r'\s+', ' ', content).strip()
    content = _CAMEL_SPLIT_RE.sub(' ', content)
    content = re.sub(r'(?<=[a-zA-Z0-9])_(?=[a-zA-Z])', ' ', content)
    return content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preprocess_chunk(content: str, lang: str) -> str:
    """Apply per-language preprocessing to a code chunk before embedding.

    Reads the strategy for `lang` from best_model_config.json:
      - "siginj": strip docstrings + prepend extracted function signature
      - "": no-op (return raw content)

    Unknown languages (not in _KNOWN_LANGUAGES) get default normalization:
    whitespace normalization + camelCase/snake_case splitting.

    Falls back gracefully on parse errors — always returns valid text.
    CPU-only, deterministic, microsecond latency per chunk.
    """
    strategy = _STRATEGIES.get(lang, "")
    if strategy != "siginj":
        if lang not in _KNOWN_LANGUAGES:
            logger.debug("code_preprocessor: unrecognized language %r — applying default normalization", lang)
            return _default_normalize(content)
        return content

    try:
        if lang == "python":
            return _python_siginj(content)
        if lang == "java":
            return _java_siginj(content)
        if lang == "csharp":
            return _csharp_siginj(content)
        if lang == "go":
            return _go_siginj(content)
        if lang == "ruby":
            return _ruby_siginj(content)
        if lang == "php":
            return _php_siginj(content)
        if lang == "javascript":
            return _js_siginj(content)
    except Exception as exc:
        logger.debug("siginj failed for %s: %s", lang, exc)

    return content
