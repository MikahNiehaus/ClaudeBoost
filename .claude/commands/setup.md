---
description: Full ClaudeBoost setup and verification — works for fresh installs and git pull updates
allowed-tools: Bash, Read, Write, Glob
---

# /setup — ClaudeBoost Setup & Verification

Installs ClaudeBoost (if needed) then verifies every component in a loop with auto-repair.

**Two scenarios this covers:**
- **Fresh computer** — No previous ClaudeBoost install. setup.py creates everything from scratch: hooks, MCP config, RAG server, state files, Python deps.
- **After `git pull`** — Existing install. setup.py picks up new hooks and deps idempotently (never duplicates). New slash commands are already in the repo. Re-index refreshes the RAG so new agents/knowledge are searchable.

> Cross-platform: setup.py runs on Windows, macOS, and Linux. The old `setup.ps1` is now a one-line shim that delegates here, so any existing automation keeps working.

Safe to re-run anytime — all operations preserve existing user settings.

---

## Phase 0: Locate ClaudeBoost Home

```bash
echo "CLAUDEBOOST_HOME=$CLAUDEBOOST_HOME"
```

If `$CLAUDEBOOST_HOME` is set, proceed to Phase 1.

If `$CLAUDEBOOST_HOME` is empty:

1. Try extracting from `~/.claude/settings.json`: read it with the **Read tool** and look for the `env.CLAUDEBOOST_HOME` key. If the file does not exist or the key is absent → treat as `MISSING`. (Read never prompts; the old `python -c ... || echo` form is blocked by bash-guard.)
2. If a valid path is returned: run `export CLAUDEBOOST_HOME=<path>` so Phase 1 can use it.
3. If `MISSING` (settings.json absent, or exists but has no `CLAUDEBOOST_HOME` key): ask the user:
   > "This appears to be a fresh install. What is the full path to your ClaudeBoost repo?"
   Then run: `export CLAUDEBOOST_HOME=<user-provided-path>`

Announce: `ClaudeBoost home: <path>`

---

## Phase 1: Run Setup Script

Installs hooks, registers MCP server, seeds state files, installs Python deps. All steps are idempotent.

```bash
"${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/setup.py"
```

(On macOS/Linux where only `python3` is on PATH, use `python3` instead.)

Read the output. Summarize:
- `[OK]` items: newly installed or verified
- `[SKIP]` items: already present (existing settings preserved)
- `[WARN]` items: non-fatal issues that may need attention

---

## Phase 2: Verification Loop

**Loop protocol:** For each check, run it, check the result. On failure, run the repair, then retry immediately. Repeat up to **3 attempts** per check. Move on only after passing or exhausting retries.

**IMPORTANT: Re-index is Step 0 of every loop iteration.** Run it unconditionally — even if you think the index is current. After a git pull, new agents and knowledge files must be in the RAG before any other check runs.

---

### Step 0 — Re-index ClaudeBoost RAG (MANDATORY, runs every time)

Call `POST http://127.0.0.1:8612/index with force=true` to force a full re-index of all ClaudeBoost agents and knowledge bases.

Report: "Re-indexed: N files, M chunks."

This ensures every subsequent check and all future sessions see the latest agents, knowledge, and slash commands.

---

### Check 1 — RAG Server Health

```bash
"${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/check-rag-health.py"; echo "EXIT=$?"
```

| Exit | Meaning | Repair |
|------|---------|--------|
| 0 | **PASS** | — |
| 2 | Dependency drift (tokenizers/transformers mismatch) | `"${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/reinstall-rag.py"` then retry |
| 3 | Wrong install path | `"${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/reinstall-rag.py"` then retry |
| 1 | Unknown error | Mark FAIL, include output — manual fix needed |

---

### Check 1b — ONNX Model Export (onnx-dml device only)

Only runs when `DEVICE=onnx-dml` is set in the RAG server config. Skip this check if the device is anything else (`cpu`, `cuda`, `dml`).

**1b-i. Detect the configured device:**

Write `${CLAUDEBOOST_HOME}/state/cb_detect_device.py` (resolve `${CLAUDEBOOST_HOME}` by running `echo "${CLAUDEBOOST_HOME}"` first if needed):
```python
import os
cfg = os.path.join(os.environ.get('CLAUDEBOOST_HOME', ''), 'mcp-rag-server', '.env')
device = 'cpu'
try:
    for line in open(cfg):
        if line.startswith('DEVICE='):
            device = line.split('=', 1)[1].strip()
except FileNotFoundError:
    pass
print(device)
```

Then run:
```bash
"${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/state/cb_detect_device.py"
```

If the output is NOT `onnx-dml`: print `SKIP (device=<device>, onnx-dml not required)` and move to Check 2.

**1b-ii. Check if the ONNX model file exists:**

Write `${CLAUDEBOOST_HOME}/state/cb_onnx_check.py`:
```python
import pathlib
p = pathlib.Path.home() / '.cache' / 'rag-onnx' / 'BAAI--bge-base-en-v1.5' / 'model.onnx'
print('EXISTS' if p.exists() else 'MISSING')
print(str(p))
```

Then run:
```bash
"${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/state/cb_onnx_check.py"
```

| Result | Meaning | Action |
|--------|---------|--------|
| EXISTS | **PASS** | — |
| MISSING | ONNX model was never exported | Run auto-export below |

**Auto-export (if MISSING):**

Write the export script to a temp file and run it (avoids multiline python -c which is blocked by bash-guard):

Write `${CLAUDEBOOST_HOME}/state/cb_onnx_export.py`:
```python
"""Auto-export BAAI/bge-base-en-v1.5 to ONNX for OnnxDirectMLEmbedding."""
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

class _OnnxWrapper(nn.Module):
    def __init__(self, bert):
        super().__init__()
        self.bert = bert
    def forward(self, input_ids, attention_mask, token_type_ids):
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask,
                        token_type_ids=token_type_ids, return_dict=False)
        return out[0], out[1]

print("Loading model...")
bert = AutoModel.from_pretrained(MODEL_NAME)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
bert.eval()
wrapper = _OnnxWrapper(bert)
wrapper.eval()

enc = tokenizer(["export test"], return_tensors="pt", padding=True, truncation=True, max_length=64)
dummy = (enc["input_ids"], enc["attention_mask"],
         enc.get("token_type_ids", torch.zeros_like(enc["input_ids"])))
dynamic_axes = {
    "input_ids": {0:"batch",1:"seq"}, "attention_mask": {0:"batch",1:"seq"},
    "token_type_ids": {0:"batch",1:"seq"}, "last_hidden_state": {0:"batch",1:"seq"},
    "pooler_output": {0:"batch"},
}
print("Exporting (opset 14, TorchScript path)...")
with torch.no_grad(), warnings.catch_warnings():
    warnings.simplefilter("ignore")
    torch.onnx.export(wrapper, dummy, str(ONNX_PATH),
        input_names=["input_ids","attention_mask","token_type_ids"],
        output_names=["last_hidden_state","pooler_output"],
        dynamic_axes=dynamic_axes, opset_version=14,
        do_constant_folding=True, dynamo=False)

size_mb = ONNX_PATH.stat().st_size / 1024 / 1024
print(f"Exported: {ONNX_PATH} ({size_mb:.0f} MB)")

import onnxruntime as ort
sess = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
enc_np = tokenizer(["smoke test"], return_tensors="np", padding=True, truncation=True, max_length=32)
inp_names = {i.name for i in sess.get_inputs()}
out = sess.run(["last_hidden_state"], {k:v for k,v in enc_np.items() if k in inp_names})
print(f"Smoke test OK - shape: {out[0].shape}")
print("DONE")
```

Then run:
```bash
"${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/state/cb_onnx_export.py"
```

This takes **1-2 minutes** on first run (model download + ONNX tracing). The 418 MB output file is permanent — subsequent `/setup` runs skip this step.

After export, verify (reuse the temp file from 1b-ii):
```bash
"${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/state/cb_onnx_check.py"
```

If still MISSING after export: mark FAIL, report the error output. Do not retry — this is a torch/transformers version issue requiring manual diagnosis.

---

### Check 2 — Required Hooks

All seven hook types must be registered in `~/.claude/settings.json`:

```bash
for hook in SessionStart SessionEnd PreToolUse PostToolUse PreCompact UserPromptSubmit Stop; do
  "${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/check-hooks.py" "${hook}"; echo "${hook} exit:$?"
done
```

`exit:0` = OK, anything else = MISSING. (Brace-form variables and no `|| echo` — both required by bash-guard.)

If any are MISSING: re-run `setup.py` (hooks are additive — re-running never duplicates), then retry.

---

### Check 3 — State Files

```bash
ls "${CLAUDEBOOST_HOME}/state/"
```

Required: `claudeboost-mode.json`, `session-approvals.json`, `speak-state.json`

If any are missing: re-run `setup.py` (it seeds missing files while preserving existing ones), then retry.

Also verify that `claudeboost-mode.json` contains `"mode": "CONSULT"`:

```bash
"${CLAUDEBOOST_PYTHON:-python3}" -c "import json,os; d=json.load(open(os.path.join(os.environ['CLAUDEBOOST_HOME'],'state','claudeboost-mode.json'))); print('mode =', d.get('mode','MISSING'))"
```

If mode is not `CONSULT`: re-run `setup.py` — it now resets any non-CONSULT value back to CONSULT automatically.

---

### Check 4 — edge-tts (for /speak)

```bash
"${CLAUDEBOOST_PYTHON:-python3}" -c "import edge_tts; print('ok')"
```

If FAIL: repair → `pip install edge-tts`, then retry.

---

### Check 4b — mcp-debugger: netcoredbg (.NET debugging)

`netcoredbg` is required for mcp-debugger to step through .NET/C# code. Without it the E2E skill skips all code verification for .NET projects and warns the user at runtime. Install it now so it's always ready.

**Step 1 — Confirm dotnet SDK is available:**
```bash
dotnet --version
```
If `dotnet` is not found: mark WARN (not FAIL), skip to Check 5. .NET is optional — skip this check only if dotnet itself isn't installed.

**Step 2 — Check whether netcoredbg is on PATH:**
```bash
where netcoredbg
```

| Result | Meaning | Action |
|--------|---------|--------|
| Path printed | **PASS** | Continue |
| Not found | Needs install | Run auto-repair below |

**Auto-repair (if not found):**
```bash
dotnet tool install -g Samsung.Netcoredbg
```

After install, re-check `where netcoredbg`. If still not found, `%USERPROFILE%\.dotnet\tools` may not be on PATH. Fix it permanently in the user's environment:
```bash
$toolsDir = "$env:USERPROFILE\.dotnet\tools"
$current = [System.Environment]::GetEnvironmentVariable('PATH','User')
if ($current -notlike "*$toolsDir*") {
    [System.Environment]::SetEnvironmentVariable('PATH', "$current;$toolsDir", 'User')
    echo "PATH updated — restart terminal for it to take effect"
}
```

Retry `where netcoredbg` after the PATH fix. Up to 3 attempts total before marking FAIL.

**This check is mandatory.** Never skip it — even for non-.NET projects. mcp-debugger is a project-agnostic tool; the user may run E2E tests against .NET projects at any time.

---

### Check 5 — Global CLAUDE.md

Read `~/.claude/CLAUDE.md` with the **Read tool** (limit 3 lines). If the Read errors, the file is MISSING.

If missing: **do not auto-copy** — the project CLAUDE.md documents ClaudeBoost internals and must not be used as the global user file. Instead, warn the user:

> "~/.claude/CLAUDE.md is missing. Create it with your personal global rules (shell conventions, security standards, coding preferences). See the ClaudeBoost docs for an example of what to include. Once created, re-run /setup to verify."

Mark as WARN (not FAIL) and continue. Do not retry — this requires manual user action.

---

### Check 6 — statusLine

**Read** `~/.claude/settings.json` with the Read tool and check the
`statusLine.command` value: PRESENT if it contains `rag-statusline`, MISSING
otherwise. (Match on the script name, not on 'ClaudeBoost', which never appears
in that mixed case. The full command is `"$CLAUDEBOOST_PYTHON" "$CLAUDEBOOST_HOME/scripts/rag-statusline.py"`.)

If MISSING: re-run `setup.py` — it now creates the statusLine on fresh installs. Then run `/rag` to start the server.

---

### Check 7 — Global slash commands synced

Project `.claude/commands/` only load when Claude Code's cwd is inside the ClaudeBoost repo. `setup.py` mirrors every command to `~/.claude/commands/` so all skills (`/workspace`, `/explore`, `/audit`, etc.) are available in **every** Claude instance regardless of directory. Verify the global dir has the full set:

```bash
SRC=$(ls "${CLAUDEBOOST_HOME}/.claude/commands/"*.md 2>/dev/null | wc -l)
DST=$(ls ~/.claude/commands/*.md 2>/dev/null | wc -l)
echo "project=${SRC} global=${DST}"
comm -23 <(ls "${CLAUDEBOOST_HOME}/.claude/commands/" 2>/dev/null | sort) <(ls ~/.claude/commands/ 2>/dev/null | sort)
```

If the `comm` output lists any files (commands present in the repo but missing globally), re-run `setup.py` — section 2b syncs them. Then **restart any other Claude instances** for them to pick up the new commands (the command list is read at startup).

---

### Check 8 — Ollama (community summaries LLM)

Ollama is required for community summaries (qwen3:4b). Without it, `/index-boost` will still work but summaries won't be generated.

**8a. Is Ollama installed?**

```bash
ollama --version
```

If the command is not found: tell the user to install Ollama from https://ollama.com/download and re-run `/setup`. Mark as WARN and skip 8b/8c — cannot auto-repair a missing binary.

**8b. Is Ollama running?**

```bash
curl -s --max-time 3 http://localhost:11434/
```

Non-empty output (Ollama answers `Ollama is running`) means RUNNING; an error or
empty output means NOT_RUNNING.

If `NOT_RUNNING`: start it in the background, then re-check:

```bash
nohup ollama serve > /tmp/ollama.log 2>&1 &
sleep 3
curl -s --max-time 3 http://localhost:11434/
```

If still not running after repair: mark as WARN — community summaries unavailable until Ollama starts. Continue.

**8c. Is qwen3:4b pulled?**

```bash
ollama list | grep qwen3
```

If `qwen3:4b` is **not** in the list:

```bash
ollama pull qwen3:4b
```

This may take several minutes (~2.5 GB). Wait for it to complete, then re-verify with `ollama list | grep qwen3`.

If pull succeeds: mark PASS.
If pull fails: mark WARN — community summaries will fall back to path-based names until model is available.

---

### Check 9 — Permission Gates

Verify that `~/.claude/settings.json` has the correct ClaudeBoost permission policy:
- `"Bash"` is in allow (catch-all; bash-guard.py enforces safety at hook level)
- All git/gh write operations are in ask (reads auto-approve, writes always prompt)
- Force-push to main/master is in deny

Run a quick audit:

```bash
"${CLAUDEBOOST_PYTHON:-python3}" /tmp/cb_perm_check.py
```

Where `cb_perm_check.py` contains:

```python
import json, os, sys
with open(os.path.expanduser("~/.claude/settings.json"), encoding="utf-8") as f:
    s = json.load(f)
allow = s["permissions"]["allow"]
ask = s["permissions"]["ask"]
deny = s["permissions"]["deny"]

issues = []
if "Bash" not in allow:
    issues.append('MISSING: "Bash" in allow (catch-all needed for smooth dev workflow)')
for entry in ["Bash(git commit **)", "Bash(git push **)", "Bash(git revert **)",
              "Bash(git config --global **)", "Bash(git filter-branch **)"]:
    if entry not in ask:
        issues.append(f"MISSING from ask: {entry}")
for entry in ["Bash(git push --force origin main **)", "Bash(git branch -D **)"]:
    if entry not in deny:
        issues.append(f"MISSING from deny: {entry}")

if issues:
    for i in issues: print("FAIL:", i)
    sys.exit(1)
else:
    print(f"OK: allow={len(allow)} ask={len(ask)} deny={len(deny)}")
    sys.exit(0)
```

| Result | Meaning | Repair |
|--------|---------|--------|
| `OK: allow=N ask=N deny=N` | **PASS** | — |
| Any `FAIL:` line | Missing entries | Re-run `setup.py` — `_update_permissions()` adds missing entries idempotently |

If repair is needed, re-run Phase 1 (`setup.py`), then retry this check. `setup.py` calls `_update_permissions()` which adds all required entries without removing any user-added entries.

---

### Check 10 — Playwright MCP (browser tools)

Playwright MCP provides `mcp__playwright_*` tools used by `browser-agent` and `/end-to-end-test`. Without it, no browser automation is available in any session or agent.

**10a. Is Node/npx available?**

```bash
"${CLAUDEBOOST_PYTHON:-python3}" -c "import shutil; print('OK' if shutil.which('npx') else 'MISSING')"
```

If MISSING: mark WARN, skip 10b. Tell the user:
> "Node.js is not installed. Playwright MCP requires it. Install from https://nodejs.org/ then re-run /setup."

**10b. Is Playwright MCP registered?**

```bash
claude mcp list 2>/dev/null | grep -i playwright
```

| Result | Meaning | Repair |
|--------|---------|--------|
| Shows `playwright` | **PASS** | — |
| No output / grep exits 1 | Needs registration | Run repair below |
| Command fails | Claude CLI not on PATH | Mark WARN, manual fix needed |

**Repair (cross-platform — works on Windows, macOS, Linux):**

```bash
claude mcp add playwright --scope user -- npx -y @playwright/mcp@latest
```

After repair, verify with `claude mcp list | grep playwright`. Up to 3 attempts before marking FAIL.

**Note:** Changes take effect after restarting Claude Code — Playwright tools (`mcp__playwright_*`) will then be available directly in every session without spawning an agent.

---

## Phase 3: Report

Print a final status table:

```
=== ClaudeBoost Setup Status ===
Scenario : Fresh install / Update after git pull
Home     : <path>

Step/Check               Result
─────────────────────────────────────────
Re-index ClaudeBoost RAG : OK (N files, M chunks)
RAG server health        : OK / FAIL (<reason>)
ONNX model (onnx-dml)    : OK / SKIP (device=cpu) / EXPORTED (N MB) / FAIL
Required hooks           : OK (7/7) / MISSING: <list>
State files              : OK (3/3) / MISSING: <list>
edge-tts                 : OK / FAIL
netcoredbg (mcp-debugger): OK vX.Y.Z / INSTALLED / WARN (no dotnet SDK) / FAIL
CLAUDE.md                : OK / MISSING
statusLine               : OK / MISSING (run `/mcp` after setup.py)
Global commands synced   : OK (N/N) / MISSING: <list> (restart other instances)
Ollama (qwen3:4b)        : OK / WARN (<reason>)
Permission gates         : OK (allow=N ask=N deny=N) / FAIL (<missing entries>)
Playwright MCP           : OK / WARN (no Node.js) / FAIL

─────────────────────────────────────────
```

**If ALL checks pass:**
> "Setup complete. All systems operational."
> - **Fresh install:** "Run `/rag` to start the server, then run `/boost`."
> - **After git pull:** "Run `/boost` to activate the updated ClaudeBoost for this session."

**If any checks fail after all retries:**
> "N check(s) could not be auto-repaired. See above for manual steps. Run `/setup` again after fixing."
