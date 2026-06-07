"""Download C# code+docstring pairs for benchmarking.

C# is not in CodeSearchNet. This script builds an equivalent benchmark
by extracting /// XML doc comment pairs from real C# code on GitHub
(codeparrot/github-code dataset, streaming — no full download required).

Extracts:
  - <summary> tag content as the natural-language query
  - Method/property body as the code to retrieve

Target: 5,000+ function+docstring pairs with at least 20 chars of summary.

Usage:
    pip install datasets
    python scripts/download_csharp_benchmark.py
    python scripts/download_csharp_benchmark.py --limit 10000
    python scripts/download_csharp_benchmark.py --force

Output:
    mcp-rag-server/tests/data/codesearchnet_csharp_full.jsonl

Note: streams C# files from HuggingFace — no full dataset download needed.
Depending on network speed, takes 3-15 minutes to find 5000 good pairs.
"""

import argparse
import json
import re
import sys
from pathlib import Path

DATA_DIR = (
    Path(__file__).resolve().parent.parent
    / "mcp-rag-server" / "tests" / "data"
)

TARGET_COUNT = 5000

_XML_SUMMARY = re.compile(
    r"///\s*<summary>(.*?)</summary>",
    re.DOTALL | re.IGNORECASE,
)
_XML_TAG = re.compile(r"<[^>]+>")
_INLINE_COMMENT = re.compile(r"^\s*///.*$", re.MULTILINE)
_SLASH_COMMENT = re.compile(r"//.*$", re.MULTILINE)

_METHOD_PAT = re.compile(
    r"""
    (?:public|private|protected|internal|static|async|virtual|override|abstract|sealed)
    [\s\w<>\[\],?*]+    # return type + optional generics
    \s+
    (\w+)               # method name (group 1)
    \s*
    (?:<[^>]*>)?        # optional generic params
    \s*
    \(                  # open paren
    [^)]*               # parameters
    \)
    (?:\s*:\s*base\([^)]*\))?
    (?:\s*where\s+\w+[^{;]*)?
    \s*
    \{                  # open brace
    """,
    re.VERBOSE,
)

_PROP_PAT = re.compile(
    r"""
    (?:public|private|protected|internal|static|virtual|override|abstract|sealed)\s+
    [\w<>\[\],?]+\s+    # type
    (\w+)               # name (group 1)
    \s*
    \{                  # open brace — property
    """,
    re.VERBOSE,
)


def _extract_block(code: str, brace_pos: int) -> str:
    """Extract balanced { } block starting at brace_pos."""
    depth = 0
    i = brace_pos
    while i < len(code):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[brace_pos : i + 1]
        i += 1
    return code[brace_pos:]


def _clean_summary(raw: str) -> str:
    text = _XML_TAG.sub("", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_pairs(source_code: str) -> list[dict]:
    """Extract (summary, method_code, name) triples from a C# file."""
    pairs = []
    lines = source_code.split("\n")
    i = 0
    while i < len(lines):
        # Collect consecutive /// lines
        if lines[i].strip().startswith("///"):
            block_start = i
            comment_lines = []
            while i < len(lines) and lines[i].strip().startswith("///"):
                comment_lines.append(lines[i])
                i += 1
            comment_block = "\n".join(comment_lines)
            m = _XML_SUMMARY.search(comment_block)
            if not m:
                continue
            summary = _clean_summary(m.group(1))
            if len(summary) < 20:
                continue

            # Look for method/property declaration within the next 5 lines
            remaining = "\n".join(lines[i : i + 5])
            mm = _METHOD_PAT.search(remaining) or _PROP_PAT.search(remaining)
            if not mm:
                continue
            func_name = mm.group(1)

            # Find the opening brace and extract the body
            brace_search = "\n".join(lines[i : i + 30])
            brace_pos = brace_search.find("{")
            if brace_pos == -1:
                continue
            decl_abs = source_code.find(remaining[:50].strip())
            if decl_abs == -1:
                continue
            block = _extract_block(source_code, decl_abs + brace_pos)
            if len(block) < 10 or len(block) > 4000:
                continue

            # Build the code snippet: comment stripped, just the method
            method_line = lines[i].strip() if i < len(lines) else ""
            snippet = brace_search[: brace_search.find("{") + len(block)]
            snippet = _INLINE_COMMENT.sub("", snippet).strip()

            pairs.append({
                "code": snippet,
                "docstring": summary,
                "func_name": func_name,
                "language": "csharp",
            })
        else:
            i += 1

    return pairs


def main():
    parser = argparse.ArgumentParser(description="Download C# benchmark pairs.")
    parser.add_argument("--limit", type=int, default=TARGET_COUNT,
                        help=f"Target number of pairs (default: {TARGET_COUNT})")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if file already exists.")
    args = parser.parse_args()

    output = DATA_DIR / "codesearchnet_csharp_full.jsonl"
    if output.exists() and not args.force:
        count = sum(1 for _ in open(output, encoding="utf-8", errors="replace"))
        print(f"[csharp] Already downloaded: {output.name} ({count:,} pairs).")
        print("         Pass --force to re-download.")
        return

    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: pip install datasets")
        sys.exit(1)

    print("[csharp] Streaming C# files from codeparrot/github-code ...")
    print(f"         Target: {args.limit:,} function+docstring pairs.")
    print("         This streams files — no full dataset download needed.\n")

    try:
        ds = load_dataset(
            "codeparrot/github-code",
            streaming=True,
            split="train",
            trust_remote_code=False,
        )
        ds = ds.filter(lambda x: x.get("language", "").lower() == "c#")
    except Exception as e:
        print(f"ERROR loading dataset: {e}")
        print("Try: pip install --upgrade datasets")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    collected = []
    files_scanned = 0

    try:
        for ex in ds:
            files_scanned += 1
            code = ex.get("code", "")
            if len(code) < 100 or "///" not in code:
                continue
            try:
                pairs = extract_pairs(code)
            except Exception:
                continue
            collected.extend(pairs)

            if files_scanned % 500 == 0:
                print(f"  Scanned {files_scanned:,} files — found {len(collected):,} pairs ...",
                      end="\r", flush=True)

            if len(collected) >= args.limit:
                break

    except KeyboardInterrupt:
        print("\n[csharp] Interrupted — saving what we have ...")

    print(f"\n[csharp] Scanned {files_scanned:,} files. Found {len(collected):,} pairs.")

    if len(collected) < 200:
        print("[csharp] Too few pairs. The streaming source may have changed.")
        print("         Try again or use a different source.")
        sys.exit(1)

    with open(output, "w", encoding="utf-8") as f:
        for pair in collected:
            f.write(json.dumps(pair) + "\n")

    print(f"[csharp] Saved {len(collected):,} pairs to: {output.name}")
    print()
    print("Run C# benchmark:")
    print("  pytest mcp-rag-server/tests/test_codesearchnet_multilang.py -v -s -k csharp")


if __name__ == "__main__":
    main()
