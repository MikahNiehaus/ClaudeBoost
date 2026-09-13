"""Stage 1 measurement: does headroom compression help clean-rag payloads?

Two questions, kept separate on purpose:
  1. Token delta -- how much smaller does the payload get?
  2. Field retention -- does every consumer field survive? (non-negotiable)

Tokenizer note: headroom's AnthropicProvider counts a bare string with
tiktoken cl100k_base x 1.1, NOT a real Anthropic tokenizer. Every number below
is therefore an APPROXIMATION. One tokenizer path is used for every payload so
the numbers are at least comparable to each other.
"""
from __future__ import annotations
import json, pathlib, statistics, sys

from headroom.providers.anthropic import AnthropicProvider
from headroom.transforms.smart_crusher import SmartCrusher, SmartCrusherConfig
from headroom import compress, CompressConfig

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from retention import check as retention_check, CONSUMER_FIELDS

HERE = pathlib.Path(__file__).parent
PAYLOADS = HERE / "payloads"
MODEL = "claude-sonnet-4-5-20250929"

# SmartCrusher / CompressConfig no-op gates, from the installed source.
MIN_ITEMS = 5
MIN_TOKENS_CRUSH = 200
MIN_TOKENS_COMPRESS = 250

tok = AnthropicProvider().get_token_counter(MODEL)   # tiktoken cl100k x1.1 -- approximate
crusher = SmartCrusher(config=SmartCrusherConfig())


def count(text: str) -> int:
    return tok.count_text(text)


def variant_smartcrusher(raw: str):
    """What headroom would do to this payload as a tool-output string."""
    r = crusher.crush(raw, query="", bias=1.0)
    return r.compressed, {"strategy": r.strategy, "was_modified": r.was_modified}


def variant_compress(raw: str):
    """Proxy-realistic: the payload as a tool message going over the wire."""
    msgs = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Analyse the search results and answer."},
        {"role": "tool", "tool_call_id": "call_0", "content": raw},
    ]
    res = compress(msgs, model=MODEL, config=CompressConfig())
    out = ""
    for m in res.messages:
        if m.get("role") == "tool" and isinstance(m.get("content"), str):
            out = m["content"]
    return out, {"transforms": sorted(set(res.transforms_applied)),
                 "lib_tokens_before": res.tokens_before,
                 "lib_tokens_after": res.tokens_after,
                 "lib_ratio": round(res.compression_ratio, 4)}


def metadata_only_floor(payload: dict) -> dict:
    """The ceiling on SAFE savings.

    If compression may not touch `content` (the source code an agent quotes
    verbatim), the most it can ever remove is the metadata envelope. This
    measures that envelope so the safe ceiling is a number, not an opinion.
    """
    res = payload.get("results", [])
    content_tok = sum(count(r.get("content") or "") for r in res)
    whole_tok = count(json.dumps(payload, indent=2))
    return {"content_tokens": content_tok, "total_tokens": whole_tok,
            "metadata_tokens": whole_tok - content_tok,
            "safe_ceiling_pct": round((whole_tok - content_tok) / whole_tok * 100, 1) if whole_tok else 0.0}


def eligible(raw: str, payload: dict) -> tuple[bool, str]:
    n = len(payload.get("results", []))
    t = count(raw)
    if n < MIN_ITEMS:
        return False, f"below min_items_to_analyze ({n}<{MIN_ITEMS})"
    if t < MIN_TOKENS_CRUSH:
        return False, f"below min_tokens_to_crush ({t}<{MIN_TOKENS_CRUSH})"
    if t < MIN_TOKENS_COMPRESS:
        return False, f"below min_tokens_to_compress ({t}<{MIN_TOKENS_COMPRESS})"
    return True, ""


def parse_after(s: str):
    try:
        return json.loads(s)
    except Exception:
        return s          # compressor emitted non-JSON text


def main():
    files = sorted(PAYLOADS.glob("search_*.json"))
    rows, skipped = [], []
    for f in files:
        raw = f.read_text()
        payload = json.loads(raw)
        ok, why = eligible(raw, payload)
        if not ok:
            skipped.append({"file": f.name, "reason": why})
            continue
        before = count(raw)
        floor = metadata_only_floor(payload)
        row = {"file": f.name, "tokens_before": before, **floor}
        for name, fn in (("smartcrusher", variant_smartcrusher),
                         ("compress", variant_compress)):
            try:
                out, meta = fn(raw)
            except Exception as e:
                row[name] = {"error": f"{type(e).__name__}: {e}"}
                continue
            after = count(out)
            ret = retention_check(payload, parse_after(out))
            row[name] = {
                "tokens_after": after,
                "saved_pct": round((before - after) / before * 100, 1) if before else 0.0,
                "verdict": ret["verdict"],
                "structure_preserved": ret["structure_preserved"],
                "lost_critical_n": len(ret["lost_critical"]),
                "lost_critical_fields": sorted({d["field"] for d in ret["lost_critical"]}),
                "content_altered": ret["content_altered_count"],
                "ccr_placeholders": ret["ccr_placeholders"],
                "distinctive_survival_pct": ret["distinctive_survival_pct"],
                "results_before": ret["results_before"],
                "results_after": ret["results_after"],
                **meta,
            }
        rows.append(row)

    out_path = HERE / "stage1_results.json"
    out_path.write_text(json.dumps({"model": MODEL,
                                    "tokenizer": "tiktoken cl100k_base x1.1 (APPROXIMATE)",
                                    "thresholds": {"min_items_to_analyze": MIN_ITEMS,
                                                   "min_tokens_to_crush": MIN_TOKENS_CRUSH,
                                                   "min_tokens_to_compress": MIN_TOKENS_COMPRESS},
                                    "eligible": rows, "not_eligible": skipped}, indent=2))

    print(f"payloads: {len(files)}   eligible: {len(rows)}   not eligible: {len(skipped)}")
    for s in skipped:
        print(f"  SKIP {s['file']}: {s['reason']}")
    print(f"\nsafe ceiling (metadata envelope as % of payload), median: "
          f"{statistics.median([r['safe_ceiling_pct'] for r in rows]):.1f}%")

    for variant in ("smartcrusher", "compress"):
        vals = [r[variant] for r in rows if "error" not in r[variant]]
        errs = [r for r in rows if "error" in r[variant]]
        print(f"\n=== {variant} ===")
        if errs:
            print(f"  errors: {len(errs)}  e.g. {errs[0][variant]['error']}")
        if not vals:
            continue
        saved = [v["saved_pct"] for v in vals]
        print(f"  token delta   median {statistics.median(saved):+.1f}%   "
              f"min {min(saved):+.1f}%   max {max(saved):+.1f}%")
        print(f"  structure preserved : {sum(v['structure_preserved'] for v in vals)}/{len(vals)}")
        print(f"  retention PASS      : {sum(v['verdict']=='PASS' for v in vals)}/{len(vals)}")
        print(f"  content altered     : {sum(v['content_altered']>0 for v in vals)}/{len(vals)} payloads")
        lost = sorted({f for v in vals for f in v["lost_critical_fields"]})
        print(f"  critical fields lost: {lost or 'none'}")
        ccr = [v["ccr_placeholders"] for v in vals]
        print(f"  CCR placeholders    : median {statistics.median(ccr):.0f} per payload "
              f"(content replaced by a retrieval pointer)")
        surv = [v["distinctive_survival_pct"] for v in vals
                if v["distinctive_survival_pct"] is not None]
        if surv:
            print(f"  distinctive metadata surviving as text: median "
                  f"{statistics.median(surv):.1f}%  min {min(surv):.1f}%")
        strat = {}
        for v in vals:
            k = v.get("strategy") or ",".join(v.get("transforms", [])) or "-"
            strat[k] = strat.get(k, 0) + 1
        print(f"  strategies/transforms: {strat}")
    print(f"\nfull results -> {out_path}")


if __name__ == "__main__":
    main()
