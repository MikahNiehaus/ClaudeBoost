#!/usr/bin/env python3
"""Zero-shot query classifier bridge. Runs inside .venv-router (isolated
venv, transformers + torch CPU), not the shared Python environment other
hooks use, for the same reason as .venv-coref (torch/transformers pull in
dependency versions that can conflict with other projects sharing the
global Python install).

Model: MoritzLaurer/deberta-v3-large-zeroshot-v2.0, chosen after testing
two other options this session: the original bart-large-mnli produced
near-tied, unusable scores on short conversational text (confirmed:
"thanks" scored 0.40 vs 0.35 vs 0.25, no real signal). This DeBERTa model
gave confident, well-separated scores on the same test cases. Not perfect
(one hard case still misclassified in testing), but a real, measured
improvement, not a guess.

Reads {"text": "..."} JSON from stdin, classifies into one of three
categories, prints result JSON to stdout.

Usage (from the main hook, via subprocess):
  echo '{"text": "..."}' | .venv-router/Scripts/python.exe _query_classifier.py
"""

import json
import sys

LABELS = ["programming or coding", "small talk", "explaining how a tool works"]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception as e:
        print(json.dumps({"label": "", "score": 0.0, "error": f"bad input: {e}"}))
        return 0

    text = payload.get("text", "")
    if not text:
        print(json.dumps({"label": "", "score": 0.0, "error": "empty text"}))
        return 0

    try:
        from transformers import pipeline

        classifier = pipeline(
            "zero-shot-classification",
            model="MoritzLaurer/deberta-v3-large-zeroshot-v2.0",
            device=-1,  # CPU only, confirmed per requirement
        )
        result = classifier(text, LABELS)
        print(json.dumps({
            "label": result["labels"][0],
            "score": result["scores"][0],
            "all_scores": dict(zip(result["labels"], result["scores"])),
            "error": None,
        }))
        return 0
    except Exception as e:
        print(json.dumps({"label": "", "score": 0.0, "error": f"{type(e).__name__}: {e}"}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
