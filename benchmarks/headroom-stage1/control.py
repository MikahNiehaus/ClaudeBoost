"""Control experiment: how much of headroom's saving is just JSON compaction?

clean-rag sends indent=2 pretty-printed JSON. Compacting it is lossless,
structure-preserving, needs no dependency, and is a one-line change. If that
alone matches headroom's median, headroom adds nothing on those payloads.
"""
import json, pathlib, statistics
from headroom.providers.anthropic import AnthropicProvider
from headroom.transforms.smart_crusher import SmartCrusher, SmartCrusherConfig

MODEL = "claude-sonnet-4-5-20250929"
tok = AnthropicProvider().get_token_counter(MODEL)
crusher = SmartCrusher(config=SmartCrusherConfig())

rows = []
for f in sorted(pathlib.Path("payloads_wire").glob("search_*.json")):
    wire = f.read_text()
    payload = json.loads(wire)
    compact = json.dumps(payload, separators=(",", ":"))
    crushed = crusher.crush(wire, query="", bias=1.0)
    crushed_compact = crusher.crush(compact, query="", bias=1.0)

    t_wire = tok.count_text(wire)
    t_compact = tok.count_text(compact)
    t_crush = tok.count_text(crushed.compressed)
    t_crush_c = tok.count_text(crushed_compact.compressed)
    rows.append({
        "file": f.name,
        "wire": t_wire,
        "compact_pct": (t_wire - t_compact) / t_wire * 100,
        "crush_pct": (t_wire - t_crush) / t_wire * 100,
        "crush_on_compact_pct": (t_compact - t_crush_c) / t_compact * 100,
        "strategy": crushed.strategy.split("(")[0],
        "table": crushed.strategy.startswith("lossless:table"),
    })

def med(k, sub=None):
    v = [r[k] for r in rows if sub is None or r["table"] == sub]
    return statistics.median(v) if v else float("nan")

print(f"{len(rows)} payloads, all from real clean-rag /search wire bytes")
print(f"\n{'':34}{'median':>9}{'min':>9}{'max':>9}")
for k, label in (("compact_pct", "compact JSON only (no headroom)"),
                 ("crush_pct", "SmartCrusher on wire bytes"),
                 ("crush_on_compact_pct", "SmartCrusher AFTER compacting")):
    v = [r[k] for r in rows]
    print(f"{label:<34}{statistics.median(v):>8.1f}%{min(v):>8.1f}%{max(v):>8.1f}%")

tbl = [r for r in rows if r["table"]]
non = [r for r in rows if not r["table"]]
print(f"\n--- split by what SmartCrusher actually did ---")
print(f"lossless:table  ({len(tbl):>2} payloads): crush {med('crush_pct', True):>5.1f}%   "
      f"compact-only {med('compact_pct', True):>5.1f}%   -> headroom adds "
      f"{med('crush_pct', True) - med('compact_pct', True):>5.1f} pts")
print(f"no compression  ({len(non):>2} payloads): crush {med('crush_pct', False):>5.1f}%   "
      f"compact-only {med('compact_pct', False):>5.1f}%   -> headroom adds "
      f"{med('crush_pct', False) - med('compact_pct', False):>5.1f} pts")
print(f"\nstrategies: {ptr if (ptr:=None) else dict((s, sum(1 for r in rows if r['strategy']==s)) for s in {r['strategy'] for r in rows})}")
pathlib.Path("control_results.json").write_text(json.dumps(rows, indent=2))
