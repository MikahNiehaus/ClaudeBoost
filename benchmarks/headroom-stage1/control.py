"""Control experiment: how much of headroom's saving is just JSON compaction?

clean-rag sends indent=2 pretty-printed JSON. Compacting it is lossless,
structure-preserving, needs no dependency, and is a one-line change. If that
alone matches headroom's median, headroom adds nothing on those payloads.

Two things this measures that an earlier version of the evaluation got wrong:

1. The statistic that answers "what does headroom add" is the median of the
   PER-PAYLOAD differences, not the difference of the two medians. Every payload
   is measured under both conditions, so the comparison is paired, and the median
   does not commute with subtraction. On this data the two disagree by 48%
   (0.27 vs 0.40 points). See metrics.paired_gains.
2. Whether tuning changes the answer has to be swept in the direction that makes
   headroom compress MORE. headroom's bias is "a multiplier: >1 keeps more items
   (conservative), <1 keeps fewer (aggressive)" (headroom/config.py), so raising
   it compresses less. The sweep below uses headroom's own named presets so it
   tracks whatever it ships, and records savings and retention together --
   either half alone answers the wrong question.
"""
import collections
import json
import pathlib
import statistics
import sys

from headroom.config import PROFILE_PRESETS
from headroom.providers.anthropic import AnthropicProvider
from headroom.transforms.smart_crusher import SmartCrusher, SmartCrusherConfig

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from metrics import paired_gains, saved_pct
from retention import check as retention_check

HERE = pathlib.Path(__file__).parent
PAYLOADS = HERE / "payloads_wire"
MODEL = "claude-sonnet-4-5-20250929"
BIAS = PROFILE_PRESETS["moderate"].bias      # headroom's default, 1.0

tok = AnthropicProvider().get_token_counter(MODEL)
crusher = SmartCrusher(config=SmartCrusherConfig())


def parse_after(compressed: str):
    """The compressed payload as a consumer would receive it."""
    try:
        return json.loads(compressed)
    except json.JSONDecodeError:
        return compressed


def by_preset(wire: str, payload: dict, t_wire: int) -> dict:
    """What each named preset saves on this payload, and what it costs.

    The savings and the retention verdict have to be read together: the only
    setting that compresses this payload shape meaningfully is the one that
    rewrites `results` into a CSV string, and that is the setting that fails the
    retention gate.
    """
    out = {}
    for name, profile in PROFILE_PRESETS.items():
        result = crusher.crush(wire, query="", bias=profile.bias)
        verdict = retention_check(payload, parse_after(result.compressed))
        out[name] = {
            "bias": profile.bias,
            "saved_pct": saved_pct(t_wire, tok.count_text(result.compressed)),
            "strategy": result.strategy.split("(")[0],
            "retention": verdict["verdict"],
            "structure_preserved": verdict["structure_preserved"],
            "ccr_placeholders": verdict["ccr_placeholders"],
        }
    return out


rows = []
for f in sorted(PAYLOADS.glob("search_*.json")):
    wire = f.read_text()
    payload = json.loads(wire)
    compact = json.dumps(payload, separators=(",", ":"))
    crushed = crusher.crush(wire, query="", bias=BIAS)
    crushed_compact = crusher.crush(compact, query="", bias=BIAS)

    t_wire = tok.count_text(wire)
    t_compact = tok.count_text(compact)
    compact_pct = saved_pct(t_wire, t_compact)
    crush_pct = saved_pct(t_wire, tok.count_text(crushed.compressed))
    rows.append({
        "file": f.name,
        "wire": t_wire,
        "compact_pct": compact_pct,
        "crush_pct": crush_pct,
        # What headroom adds over compaction, on THIS payload. The paired
        # difference; the reported statistic is the median of these.
        "headroom_gain_pts": crush_pct - compact_pct,
        "crush_on_compact_pct": saved_pct(t_compact, tok.count_text(crushed_compact.compressed)),
        "strategy": crushed.strategy.split("(")[0],
        "table": crushed.strategy.startswith("lossless:table"),
        "by_preset": by_preset(wire, payload, t_wire),
    })


def med(key, table=None):
    vals = [r[key] for r in rows if table is None or r["table"] == table]
    return statistics.median(vals) if vals else float("nan")


print(f"{len(rows)} payloads, all from real clean-rag /search wire bytes")
print(f"\n{'':34}{'median':>9}{'min':>9}{'max':>9}")
for key, label in (("compact_pct", "compact JSON only (no headroom)"),
                   ("crush_pct", "SmartCrusher on wire bytes"),
                   ("crush_on_compact_pct", "SmartCrusher AFTER compacting")):
    vals = [r[key] for r in rows]
    print(f"{label:<34}{statistics.median(vals):>8.1f}%{min(vals):>8.1f}%{max(vals):>8.1f}%")

print(f"\n--- at the default bias {BIAS}, split by what SmartCrusher actually did ---")
for table, label in ((True, "lossless:table"), (False, "no compression")):
    group = [r for r in rows if r["table"] == table]
    if not group:
        continue
    gains = paired_gains([r["crush_pct"] for r in group],
                         [r["compact_pct"] for r in group])
    print(f"{label:<15} ({len(group):>2} payloads): crush {med('crush_pct', table):>5.1f}%   "
          f"compact-only {med('compact_pct', table):>5.1f}%")
    print(f"{'':18}-> headroom adds {statistics.median(gains):>6.2f} pts "
          f"(median paired difference; min {min(gains):.2f}, max {max(gains):.2f}, "
          f"{sum(g == 0 for g in gains)}/{len(gains)} exactly zero)")

print("\n--- can tuning make headroom worth it? headroom's own named presets ---")
print(f"{'preset':<14}{'bias':>6}{'median saved':>14}{'lossless:table':>16}"
      f"{'retention PASS':>16}{'CCR pointers':>14}")
for name in sorted(PROFILE_PRESETS, key=lambda n: PROFILE_PRESETS[n].bias):
    cells = [r["by_preset"][name] for r in rows]
    n = len(cells)
    print(f"{name:<14}{PROFILE_PRESETS[name].bias:>6}"
          f"{statistics.median(c['saved_pct'] for c in cells):>13.1f}%"
          f"{sum(c['strategy'] == 'lossless:table' for c in cells):>11}/{n}"
          f"{sum(c['retention'] == 'PASS' for c in cells):>11}/{n}"
          f"{sum(c['ccr_placeholders'] > 0 for c in cells):>9}/{n}")
print(f"\nstrategies at bias {BIAS}: {dict(collections.Counter(r['strategy'] for r in rows))}")

out_path = HERE / "control_results.json"
out_path.write_text(json.dumps(rows, indent=2))
print(f"\nfull results -> {out_path}")
