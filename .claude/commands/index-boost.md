---
description: Reindex ClaudeBoost knowledge bases and agent definitions
allowed-tools: Bash, Glob
---

# Index Boost RAG

Reindex ClaudeBoost's knowledge bases and agent definitions.

## Arguments

Flexible — any combination:
- Empty → reindex all (knowledge + agents), incremental
- `knowledge` → reindex knowledge bases only
- `agents` → reindex agent definitions only
- `force` → force full reindex even if files haven't changed
- `knowledge force` or `force knowledge` → full reindex of knowledge only
- `agents force` → full reindex of agents only

## Instructions

1. **Parse arguments** from the input:
   - If `force` is present → set `force=true`, otherwise `force=false`
   - If `knowledge` is present (and not `agents`) → `scope="knowledge"`
   - If `agents` is present (and not `knowledge`) → `scope="agents"`
   - If both or neither → `scope="all"`

2. **Health check** — call `GET http://127.0.0.1:8612/status` via Bash:
   ```bash
   python3 -c "
   import json, urllib.request
   with urllib.request.urlopen('http://127.0.0.1:8612/status', timeout=5) as r:
       data = json.loads(r.read())
       print(json.dumps(data, indent=2))
   "
   ```
   If it fails, stop and tell the user: "RAG not connected — run `/rag` to start the server, then retry."

   Report current counts before indexing so the user can see what changed:
   - knowledge: N chunks, N files
   - agents: N chunks, N files

3. **Index** — call `POST http://127.0.0.1:8612/index` via Bash:
   ```bash
   python3 -c "
   import json, urllib.request
   body = json.dumps({'scope': '<scope>', 'force': <force>}).encode()
   req = urllib.request.Request('http://127.0.0.1:8612/index', data=body, headers={'Content-Type': 'application/json'})
   with urllib.request.urlopen(req, timeout=120) as r:
       print(json.dumps(json.loads(r.read()), indent=2))
   "
   ```

4. **Report results**:
   - Call `GET http://127.0.0.1:8612/status` again to get updated counts
   - Show a before/after table:
     ```
     Collection   Before              After
     knowledge    1600 chunks / 96f   XXXX chunks / XXf
     agents        279 chunks / 25f    XXX chunks / XXf
     ```
   - Note if counts changed (new files picked up) or stayed the same (already current)
   - If `force=true`: confirm full reindex completed

5. **Post-index quality checks** — run both checks, auto-fix if possible.

   a. **Vector quality — knowledge** (1 search call):
      ```bash
      python3 -c "
      import json, urllib.request
      body = json.dumps({'query': 'security parameterized queries input validation', 'scope': 'knowledge', 'limit': 5}).encode()
      req = urllib.request.Request('http://127.0.0.1:8612/search', data=body, headers={'Content-Type': 'application/json'})
      with urllib.request.urlopen(req, timeout=10) as r:
          data = json.loads(r.read())
          for hit in data.get('results', []):
              print(f\"{hit['score']:.3f}  {hit['source']}\")
      "
      ```
      - PASS: top score ≥ 0.68 AND result from a `.xml` knowledge file
      - WARN: top score 0.55–0.68
      - FAIL: top score < 0.55 OR no results

      If WARN/FAIL: retry with query `"OWASP injection SQL authentication"`.
      - If retry score ≥ 0.68: PASS (original query vocabulary mismatch). Show both scores.
      - If still < 0.68: WARN — consider `/index-boost force` to rebuild embeddings.

   b. **Vector quality — agents** (1 search call):
      Same HTTP pattern, query `"agent spawning model routing task description"`, scope `"agents"`, limit 3.
      - PASS: top score ≥ 0.68 AND result from an agents file
      - WARN: top score 0.55–0.68
      - FAIL: top score < 0.55 OR no results

      If WARN/FAIL: retry with query `"context endpoint orchestrator spawn"`.

   c. **Coverage check** — verify indexed file counts match disk:
      - knowledge files on disk: `Glob("knowledge/*.xml")` → count
      - agents files on disk: `Glob("agents/*.xml")` → count
      - PASS: status counts match disk counts
      - WARN: mismatch — run `/index-boost force` to rebuild

   **Print summary table:**
   ```
   ────────────────────────────────────────────────────
   Post-Index Quality Checks
   ────────────────────────────────────────────────────
   a. Knowledge vectors   ✓ / ⚠  [top score, source file]
   b. Agent vectors       ✓ / ⚠  [top score, source file]
   c. Coverage            ✓ / ⚠  [knowledge: Xf disk vs Yf indexed, agents: Xf vs Yf]
   ────────────────────────────────────────────────────
   ```

6. **Done** — one line: "Boost RAG is current." or "Boost RAG updated — N new chunks indexed." Append any warnings.
