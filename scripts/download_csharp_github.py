"""Download C# code+docstring pairs from well-documented GitHub repos.

Uses GitHub zip archives — no API key, no large dataset download needed.
Parses /// <summary> XML doc comment + method body pairs.

Target repos (all MIT/Apache licensed, excellent documentation):
  - Newtonsoft.Json (Json.NET)
  - AutoMapper
  - Polly (resilience library)
  - FluentValidation
  - Dapper (micro-ORM)
  - MediatR
  - Serilog

Usage:
    python scripts/download_csharp_github.py
    python scripts/download_csharp_github.py --target 5000

Output:
    mcp-rag-server/tests/data/codesearchnet_csharp_full.jsonl
"""

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib import request as urllib_request
from urllib.error import URLError

DATA_DIR = (
    Path(__file__).resolve().parent.parent
    / "mcp-rag-server" / "tests" / "data"
)

REPOS = [
    ("JamesNK/Newtonsoft.Json",         "master"),
    ("AutoMapper/AutoMapper",            "master"),
    ("App-vNext/Polly",                  "main"),
    ("FluentValidation/FluentValidation","main"),
    ("DapperLib/Dapper",                 "main"),
    ("jbogard/MediatR",                  "main"),
    ("serilog/serilog",                  "dev"),
    ("dotnet/efcore",                    "main"),
    ("domaindrivendev/Swashbuckle.AspNetCore", "master"),
    ("StackExchange/StackExchange.Redis", "main"),
    ("reactiveui/ReactiveUI",            "main"),
    ("nunit/nunit",                      "main"),
    ("moq/moq",                          "main"),
    ("castleproject/Core",               "master"),
]

_XML_SUMMARY = re.compile(
    r"///\s*<summary>(.*?)</summary>",
    re.DOTALL | re.IGNORECASE,
)
_XML_TAG      = re.compile(r"<[^>]+>")
_TRIPLE_SLASH = re.compile(r"^\s*///.*$", re.MULTILINE)
_MULTI_WS     = re.compile(r"\s{2,}", re.MULTILINE)

_METHOD_RE = re.compile(
    r"""
    (?:(?:public|private|protected|internal|static|async|virtual|override
        |abstract|sealed|readonly|extern|new|partial)\s+)+
    (?:[\w<>\[\],?.]+\s+)+      # return type
    (\w+)                        # method name (group 1)
    \s*(?:<[^>]*>)?\s*           # optional generic
    \(                           # open paren
    [^)]*                        # params
    \)\s*
    (?:where\s+[^{]*)?           # optional constraint
    \{                           # open brace
    """,
    re.VERBOSE | re.DOTALL,
)

_PROP_RE = re.compile(
    r"""
    (?:(?:public|private|protected|internal|static|virtual|override
        |abstract|sealed|readonly|new)\s+)+
    [\w<>\[\],?.]+\s+            # type
    (\w+)\s*                     # name (group 1)
    \{                           # open brace
    """,
    re.VERBOSE,
)

SKIP_NAMES = {
    "get", "set", "add", "remove", "value", "if", "else", "while",
    "for", "foreach", "switch", "case", "return", "try", "catch",
    "finally", "throw", "using", "new", "this", "base", "var",
    "true", "false", "null", "string", "int", "bool", "void",
    "object", "class", "interface", "struct", "enum", "namespace",
}


def _clean_summary(raw: str) -> str:
    text = _XML_TAG.sub("", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _find_balanced_block(src: str, start: int) -> str:
    depth = 0
    i = start
    in_string = False
    str_char = None
    while i < len(src):
        c = src[i]
        if in_string:
            if c == str_char and (i == 0 or src[i-1] != "\\"):
                in_string = False
        elif c in ('"', "'") and depth > 0:
            in_string = True
            str_char = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    return src[start:min(start + 2000, len(src))]


def extract_pairs_from_file(source: str) -> list[dict]:
    pairs = []
    lines = source.split("\n")
    i = 0
    while i < len(lines):
        if "///" not in lines[i]:
            i += 1
            continue

        # Collect consecutive /// lines
        comment_lines = []
        while i < len(lines) and "///" in lines[i]:
            comment_lines.append(lines[i])
            i += 1
        comment_block = "\n".join(comment_lines)

        m = _XML_SUMMARY.search(comment_block)
        if not m:
            continue
        summary = _clean_summary(m.group(1))
        if len(summary) < 20 or len(summary) > 500:
            continue

        # Look for method/property in next 6 lines
        lookahead = "\n".join(lines[i: i + 6])
        mm = _METHOD_RE.search(lookahead) or _PROP_RE.search(lookahead)
        if not mm:
            continue
        func_name = mm.group(1)
        if func_name.lower() in SKIP_NAMES or func_name.startswith("_"):
            continue

        # Find brace position in full source from current line
        line_offset = sum(len(l) + 1 for l in lines[:i])
        brace_search = source[line_offset: line_offset + 500]
        brace_pos = brace_search.find("{")
        if brace_pos == -1:
            continue
        abs_brace = line_offset + brace_pos
        block = _find_balanced_block(source, abs_brace)
        if len(block) < 15 or len(block) > 5000:
            continue

        # Build clean code: remove /// lines, keep method signature + body
        decl_start = line_offset
        code_section = source[decl_start: decl_start + 200 + len(block)]
        code_section = _TRIPLE_SLASH.sub("", code_section).strip()

        pairs.append({
            "code":      code_section[:4000],
            "docstring": summary,
            "func_name": func_name,
            "language":  "csharp",
        })

    return pairs


def fetch_repo_zip(owner_repo: str, branch: str) -> bytes | None:
    url = f"https://github.com/{owner_repo}/archive/refs/heads/{branch}.zip"
    print(f"  Downloading {owner_repo} ({branch}) ...", flush=True)
    try:
        req = urllib_request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib_request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        print(f"  {len(data) / 1024 / 1024:.1f} MB", flush=True)
        return data
    except URLError as e:
        print(f"  FAILED: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=5000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output = DATA_DIR / "codesearchnet_csharp_full.jsonl"
    if output.exists() and not args.force:
        count = sum(1 for _ in open(output, encoding="utf-8", errors="replace"))
        print(f"[csharp] Already exists: {output.name} ({count:,} pairs). Pass --force to redo.")
        return

    all_pairs = []
    seen_summaries = set()

    for owner_repo, branch in REPOS:
        if len(all_pairs) >= args.target:
            break
        raw = fetch_repo_zip(owner_repo, branch)
        if raw is None:
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                cs_files = [n for n in zf.namelist() if n.endswith(".cs")
                            and not any(skip in n.lower() for skip in
                                       ("test", "spec", "migration", "designer",
                                        "generated", "obj/", "bin/", ".g.cs",
                                        "assemblyinfo", "scaffolded"))]
                repo_pairs = 0
                for name in cs_files:
                    try:
                        source = zf.read(name).decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    if "///" not in source:
                        continue
                    pairs = extract_pairs_from_file(source)
                    for p in pairs:
                        key = p["docstring"][:80]
                        if key not in seen_summaries:
                            seen_summaries.add(key)
                            all_pairs.append(p)
                            repo_pairs += 1
                print(f"  Found {repo_pairs} pairs from {owner_repo}")
        except zipfile.BadZipFile:
            print(f"  Bad zip from {owner_repo}")

    if len(all_pairs) < 200:
        print(f"[csharp] Only found {len(all_pairs)} pairs — too few. Check network.")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for p in all_pairs:
            f.write(json.dumps(p) + "\n")

    print(f"\n[csharp] Saved {len(all_pairs):,} pairs to: {output.name}")
    print("Run: pytest mcp-rag-server/tests/test_codesearchnet_multilang.py -v -s -k csharp")


if __name__ == "__main__":
    main()
