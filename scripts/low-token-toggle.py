"""
low-token-toggle.py — Low Token Mode state manager.

Usage:
  low-token-toggle.py                 -- print current status
  low-token-toggle.py on              -- enable
  low-token-toggle.py off             -- disable
  low-token-toggle.py on --threshold 65   -- enable with custom threshold %

State file: $CLAUDEBOOST_HOME/state/low-token-mode.json
  {"enabled": bool, "threshold_pct": int}

The state file is in state/ which is gitignored — each machine manages its own.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def main() -> int:
    home = Path(
        os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent
    )
    state_path = home / "state" / "low-token-mode.json"

    state = _read_json(state_path, {"enabled": False, "threshold_pct": 70})

    args = sys.argv[1:]

    # Parse --threshold N
    threshold = state.get("threshold_pct", 70)
    filtered = []
    i = 0
    while i < len(args):
        if args[i] == "--threshold" and i + 1 < len(args):
            try:
                threshold = int(args[i + 1])
                if not 10 <= threshold <= 95:
                    print(f"ERROR: threshold must be between 10 and 95, got {threshold}")
                    return 1
            except ValueError:
                print(f"ERROR: threshold must be an integer, got {args[i+1]!r}")
                return 1
            i += 2
        else:
            filtered.append(args[i])
            i += 1

    command = filtered[0].lower() if filtered else "status"

    if command == "on":
        state["enabled"] = True
        state["threshold_pct"] = threshold
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"Low Token Mode: ON (threshold {threshold}%)")
        print("Status bar shows LT indicator. At context capacity a new terminal opens and this session closes.")

    elif command == "off":
        state["enabled"] = False
        state["threshold_pct"] = threshold
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print("Low Token Mode: OFF")
        print("Normal compaction behavior restored.")

    elif command == "status":
        enabled = state.get("enabled", False)
        pct = state.get("threshold_pct", 70)
        status_str = "ON" if enabled else "OFF"
        print(f"Low Token Mode: {status_str} (threshold {pct}%)")
        if not state_path.exists():
            print(f"(no state file yet at {state_path})")

    else:
        print(f"ERROR: unknown command {command!r}. Use: on, off, or status")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
