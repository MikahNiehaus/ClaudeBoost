"""Download CodeSearchNet test splits for one or more languages.

Saves to: mcp-rag-server/tests/data/codesearchnet_{lang}_full.jsonl
Required by: mcp-rag-server/tests/test_codesearchnet_1k_pool.py

Usage:
    python scripts/download_codesearchnet_full.py              # Python only (default)
    python scripts/download_codesearchnet_full.py --lang python javascript java
    python scripts/download_codesearchnet_full.py --lang all

Supported languages: python, javascript, java, go, ruby, php

Requirements:
    pip install datasets

Data source: huggingface.co/datasets/code_search_net (CC BY-4.0)
"""

import argparse
import json
import sys
from pathlib import Path

DATA_DIR = (
    Path(__file__).resolve().parent.parent
    / "mcp-rag-server" / "tests" / "data"
)

SUPPORTED = ["python", "javascript", "java", "go", "ruby", "php"]


def download_language(lang: str, force: bool = False) -> int:
    output = DATA_DIR / f"codesearchnet_{lang}_full.jsonl"

    if output.exists() and not force:
        count = sum(1 for _ in open(output, encoding="utf-8"))
        print(f"[{lang}] Already downloaded: {output.name} ({count:,} functions).")
        print(f"       Pass --force to re-download.")
        return count

    print(f"[{lang}] Downloading CodeSearchNet {lang} test split from HuggingFace ...")

    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' not installed.")
        print("       pip install datasets")
        sys.exit(1)

    ds = load_dataset(
        "code-search-net/code_search_net",
        lang,
        split="test",
        trust_remote_code=False,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    with open(output, "w", encoding="utf-8") as f:
        for ex in ds:
            code = ex.get("whole_func_string", "")
            doc = ex.get("func_documentation_string", "")
            if not code.strip() or not doc.strip():
                skipped += 1
                continue
            record = {
                "code": code,
                "docstring": doc,
                "func_name": ex.get("func_name", ""),
                "repo": ex.get("repository_name", ""),
                "language": lang,
            }
            f.write(json.dumps(record) + "\n")
            written += 1

    print(f"[{lang}] Saved {written:,} functions to: {output.name}")
    if skipped:
        print(f"[{lang}] Skipped {skipped} records with empty code or docstring.")
    return written


def main():
    parser = argparse.ArgumentParser(description="Download CodeSearchNet test splits.")
    parser.add_argument(
        "--lang",
        nargs="+",
        default=["python"],
        help=f"Languages to download. Use 'all' for all supported. Supported: {', '.join(SUPPORTED)}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the file already exists.",
    )
    args = parser.parse_args()

    langs = SUPPORTED if "all" in args.lang else args.lang
    invalid = [l for l in langs if l not in SUPPORTED]
    if invalid:
        print(f"ERROR: Unsupported language(s): {', '.join(invalid)}")
        print(f"Supported: {', '.join(SUPPORTED)}")
        sys.exit(1)

    print(f"Languages to download: {', '.join(langs)}")
    print()

    total = 0
    for lang in langs:
        total += download_language(lang, force=args.force)

    print()
    print(f"Done. {total:,} total functions across {len(langs)} language(s).")
    print()
    print("Run benchmarks:")
    print("  pytest mcp-rag-server/tests/test_codesearchnet_1k_pool.py -v -s")
    print()
    print("Run multi-language benchmark:")
    print("  pytest mcp-rag-server/tests/test_codesearchnet_multilang.py -v -s")


if __name__ == "__main__":
    main()
