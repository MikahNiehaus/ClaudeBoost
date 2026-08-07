---
description: "<true|false|verify>  true: always-on rules only  |  false: off  |  verify: health check + optional auto-fix"
allowed-tools: Bash, Read, Write, Glob
---

# ClaudeBoost

## Arguments: $ARGUMENTS

The whole activation and health-check flow is described below. One helper script
(`scripts/boost-run.py`) handles the heavy lifting. Do NOT use inline `python -c`,
bare `$VAR`, or bare `python`/`python3` — they are blocked by bash-guard.py. Always
use `"${CLAUDEBOOST_PYTHON}"` and `"${CLAUDEBOOST_HOME}"` (brace form).

---

## Quick toggle (`true` / `false`)

- `$ARGUMENTS` is `true`:
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/boost-run.py" true
  ```
- `$ARGUMENTS` is `false`:
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/boost-run.py" false
  ```

Relay the one-line message the script printed. Stop — no scan, no report.

---

## Health Check (`verify` / empty)

### Step 1 — Core scan

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/boost-run.py" verify
```

Read the `=== BOOST_SUMMARY ===` JSON line at the end of the output. Capture:
`rag_ready`, `healed_scopes`, `missing_hooks`, `rules_ok`, `mode`, `active_workspaces`, `project_cwd`.

### Step 2 — Additional checks

Run each of these after Step 1. They are fast (check only, no repair yet).

**State files:**
```bash
for f in claudeboost-mode.json session-approvals.json speak-state.json; do
  test -f "${CLAUDEBOOST_HOME}/state/${f}" && echo "OK ${f}" || echo "MISSING ${f}"
done
```

**edge-tts** — write then run (multiline python -c is blocked):
Write `"${CLAUDEBOOST_HOME}/state/cb_edgetts_check.py"`:
```python
try:
    import edge_tts
    print("ok")
except ImportError:
    print("missing")
```
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/state/cb_edgetts_check.py"
```

**ONNX model** — write then run:
Write `"${CLAUDEBOOST_HOME}/state/cb_onnx_check.py"`:
```python
import pathlib
cfg = pathlib.Path(__file__).parent.parent / "mcp-rag-server" / ".env"
device = "cpu"
try:
    for line in open(cfg):
        if line.startswith("DEVICE="):
            device = line.split("=", 1)[1].strip()
except FileNotFoundError:
    pass
if device != "onnx-dml":
    print(f"SKIP device={device}")
else:
    p = pathlib.Path.home() / ".cache" / "rag-onnx" / "BAAI--bge-base-en-v1.5" / "model.onnx"
    print("EXISTS" if p.exists() else "MISSING")
```
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/state/cb_onnx_check.py"
```

**netcoredbg:**
```bash
dotnet --version 2>/dev/null || echo "NO_DOTNET"
where netcoredbg 2>/dev/null && echo "OK" || echo "MISSING"
```

**statusLine** — read `~/.claude/settings.json` with the Read tool; check whether
`statusLine.command` contains `rag-statusline`. PRESENT or MISSING.

**Global commands:**
```bash
SRC=$(ls "${CLAUDEBOOST_HOME}/.claude/commands/"*.md 2>/dev/null | wc -l | tr -d ' ')
DST=$(ls ~/.claude/commands/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "src=${SRC} dst=${DST}"
comm -23 <(ls "${CLAUDEBOOST_HOME}/.claude/commands/" 2>/dev/null | sort) <(ls ~/.claude/commands/ 2>/dev/null | sort)
```
MISSING if `comm` outputs any filenames.

**Permissions** — write then run:
Write `"${CLAUDEBOOST_HOME}/state/cb_perm_check.py"`:
```python
import json, os, sys
try:
    with open(os.path.expanduser("~/.claude/settings.json"), encoding="utf-8") as f:
        s = json.load(f)
except FileNotFoundError:
    print("MISSING settings.json"); sys.exit(1)
allow = s.get("permissions", {}).get("allow", [])
ask   = s.get("permissions", {}).get("ask", [])
deny  = s.get("permissions", {}).get("deny", [])
issues = []
if "Bash" not in allow:
    issues.append('"Bash" missing from allow')
for e in ["Bash(git commit **)", "Bash(git push **)", "Bash(git revert **)",
          "Bash(git config --global **)", "Bash(git filter-branch **)"]:
    if e not in ask:
        issues.append(f"{e} missing from ask")
for e in ["Bash(git push --force origin main **)", "Bash(git branch -D **)"]:
    if e not in deny:
        issues.append(f"{e} missing from deny")
if issues:
    for i in issues: print("FAIL:", i)
    sys.exit(1)
print(f"OK allow={len(allow)} ask={len(ask)} deny={len(deny)}")
```
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/state/cb_perm_check.py"
```

**Playwright MCP:**
```bash
claude mcp list 2>/dev/null | grep -i playwright && echo "OK" || echo "MISSING"
```

**Ollama + qwen3:4b:**
```bash
ollama --version 2>/dev/null && echo "INSTALLED" || echo "NOT_INSTALLED"
```
If installed: `curl -s --max-time 3 http://localhost:11434/` (running or not).
If running: `ollama list 2>/dev/null | grep qwen3` (model present or missing).

### Step 3 — Status table

Print a compact table of all results:

```
=== ClaudeBoost Health ===

Check                     Status
──────────────────────────────────────────
RAG (port 8612)          : ready / NOT READY
Dimension heal           : none / rebuilt [scopes]
Hooks (6/6)              : all present / MISSING: [list]
CLAUDE.md (~/.claude/)   : loaded / MISSING
State files (3/3)        : OK / MISSING: [list]
edge-tts                 : OK / NOT INSTALLED
ONNX model               : OK / MISSING / SKIP (device=cpu)
netcoredbg               : OK / MISSING / SKIP (no dotnet)
statusLine               : OK / MISSING
Global commands (N/N)    : OK / MISSING: [list]
Permissions              : OK / FAIL: [issues]
Playwright MCP           : OK / MISSING / SKIP (no Node)
Ollama + qwen3:4b        : OK / WARN: [reason]

Collaborative mode       : CONSULT / AUTO
Active workspaces        : [list or "none"]
──────────────────────────────────────────
```

### Step 4 — If all pass

```
ClaudeBoost is live. Status line shows RAG ● when healthy.
```

- If `active_workspaces` has exactly one entry: read
  `<project_cwd>/workspace/<id>/context.md` and summarize where it left off.
- Remind the user of the current mode (CONSULT/AUTO).

### Step 5 — If issues found

Tell the user what failed (one line each). Then ask:

> "Found N issue(s). Fix them all now?"

Options: **Yes — fix everything** / **No — I'll handle it manually**

Use `AskUserQuestion`.

### Step 6 — Fix phase (if yes)

Run `setup.py` first — it idempotently repairs hooks, state files, statusLine,
global command sync, and permission gates without touching existing user settings:

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/setup.py"
```

Then handle any extras that `setup.py` does not cover:

**ONNX MISSING** — write and run the export script:
Write `"${CLAUDEBOOST_HOME}/state/cb_onnx_export.py"`:
```python
"""Export BAAI/bge-base-en-v1.5 to ONNX for OnnxDirectMLEmbedding."""
import sys, pathlib, warnings
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
MODEL_NAME = "BAAI/bge-base-en-v1.5"
ONNX_DIR = pathlib.Path.home() / ".cache" / "rag-onnx" / "BAAI--bge-base-en-v1.5"
ONNX_PATH = ONNX_DIR / "model.onnx"
ONNX_DIR.mkdir(parents=True, exist_ok=True)
print(f"Exporting {MODEL_NAME} -> {ONNX_PATH}")
import torch, torch.nn as nn
from transformers import AutoModel, AutoTokenizer
class _Wrap(nn.Module):
    def __init__(self, bert):
        super().__init__()
        self.bert = bert
    def forward(self, input_ids, attention_mask, token_type_ids):
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask,
                        token_type_ids=token_type_ids, return_dict=False)
        return out[0], out[1]
bert = AutoModel.from_pretrained(MODEL_NAME)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
bert.eval()
wrapper = _Wrap(bert)
wrapper.eval()
enc = tokenizer(["export test"], return_tensors="pt", padding=True, truncation=True, max_length=64)
dummy = (enc["input_ids"], enc["attention_mask"],
         enc.get("token_type_ids", torch.zeros_like(enc["input_ids"])))
axes = {"input_ids":{0:"batch",1:"seq"},"attention_mask":{0:"batch",1:"seq"},
        "token_type_ids":{0:"batch",1:"seq"},"last_hidden_state":{0:"batch",1:"seq"},"pooler_output":{0:"batch"}}
with torch.no_grad(), warnings.catch_warnings():
    warnings.simplefilter("ignore")
    torch.onnx.export(wrapper, dummy, str(ONNX_PATH),
        input_names=["input_ids","attention_mask","token_type_ids"],
        output_names=["last_hidden_state","pooler_output"],
        dynamic_axes=axes, opset_version=14, do_constant_folding=True, dynamo=False)
print(f"Exported: {ONNX_PATH} ({ONNX_PATH.stat().st_size/1024/1024:.0f} MB)")
import onnxruntime as ort
sess = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
enc_np = tokenizer(["smoke test"], return_tensors="np", padding=True, truncation=True, max_length=32)
inp_names = {i.name for i in sess.get_inputs()}
out = sess.run(["last_hidden_state"], {k:v for k,v in enc_np.items() if k in inp_names})
print(f"Smoke test OK shape={out[0].shape}")
print("DONE")
```
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/state/cb_onnx_export.py"
```
This takes 1-2 minutes on first run (model download + ONNX tracing).

**netcoredbg MISSING** (only if dotnet is installed):
```bash
dotnet tool install -g Samsung.Netcoredbg
```

**Playwright MCP MISSING:**
```bash
claude mcp add playwright --scope user -- npx -y @playwright/mcp@latest
```

**Ollama NOT INSTALLED:** Tell the user to install from https://ollama.com/download and
re-run `/boost` — cannot auto-install a binary.

**qwen3:4b model missing** (Ollama is installed and running):
```bash
ollama pull qwen3:4b
```

**Force re-index after any fix** (ensures RAG sees the latest agents and knowledge):
```bash
curl -s -X POST http://127.0.0.1:8613/index-project -H "Content-Type: application/json" -d "{\"force\": true}"
```

### Step 7 — Post-fix summary

Report what was fixed, what still needs manual action (Ollama install, CLAUDE.md
creation). Re-run the scan once to confirm all auto-repaired items now pass.

```
ClaudeBoost setup complete. N/N checks passing.
```

If anything still fails after repair: list it and tell the user what to do manually.
