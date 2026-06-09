"""Update best_model_config.json with the winning BEIR docs model.

Usage:
    python update_beir_best.py --model 'BAAI/bge-large-en-v1.5' --key 'bge_large'
    python update_beir_best.py --model 'intfloat/e5-large-v2' --key 'e5_large' \
        --query-prefix 'query: ' --doc-prefix 'passage: '
    python update_beir_best.py --model 'BAAI/bge-large-en-v1.5' --key 'bge_large' \
        --ndcg-fiqa 0.469 --ndcg-scifact 0.710 --ndcg-nfcorpus 0.355 --ndcg-arguana 0.541
"""

import argparse
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "tests" / "data" / "best_model_config.json"


def main():
    p = argparse.ArgumentParser(description="Update BEIR docs entry in best_model_config.json")
    p.add_argument("--model",  required=True, help="HuggingFace model name")
    p.add_argument("--key",    required=True, help="Short model key (e.g. bge_large)")
    p.add_argument("--query-prefix", default="", help="Query prefix (e.g. 'query: ' for e5)")
    p.add_argument("--doc-prefix",   default="", help="Doc prefix (e.g. 'passage: ' for e5)")
    p.add_argument("--ndcg-fiqa",     type=float, default=None)
    p.add_argument("--ndcg-scifact",  type=float, default=None)
    p.add_argument("--ndcg-nfcorpus", type=float, default=None)
    p.add_argument("--ndcg-arguana",  type=float, default=None)
    p.add_argument("--avg-ndcg",      type=float, default=None, help="Pre-computed average NDCG@10")
    args = p.parse_args()

    cfg = {}
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text("utf-8"))

    docs_entry = {
        "model":     args.model,
        "model_key": args.key,
    }
    if args.query_prefix:
        docs_entry["query_prefix"] = args.query_prefix
    if args.doc_prefix:
        docs_entry["doc_prefix"] = args.doc_prefix

    # Store per-dataset NDCG scores if provided
    scores = {}
    for ds, val in [("fiqa", args.ndcg_fiqa), ("scifact", args.ndcg_scifact),
                    ("nfcorpus", args.ndcg_nfcorpus), ("arguana", args.ndcg_arguana)]:
        if val is not None:
            scores[ds] = round(val, 4)
    if scores:
        docs_entry["ndcg"] = scores

    if args.avg_ndcg is not None:
        docs_entry["avg_ndcg"] = round(args.avg_ndcg, 4)
    elif scores:
        docs_entry["avg_ndcg"] = round(sum(scores.values()) / len(scores), 4)

    # Compute floor = avg_ndcg - 0.025 (regression tolerance)
    if "avg_ndcg" in docs_entry:
        docs_entry["floor"] = round(docs_entry["avg_ndcg"] - 0.025, 4)

    cfg["docs"] = docs_entry
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), "utf-8")
    print(f"Updated best_model_config.json['docs']:")
    print(json.dumps(docs_entry, indent=2))


if __name__ == "__main__":
    main()
