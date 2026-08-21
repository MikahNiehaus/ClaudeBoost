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

2. **Health check** — call `GET http://127.0.0.1:8613/status` via Bash:
   ```bash
   curl -s --max-time 5 http://127.0.0.1:8613/status
   ```
   If it fails, stop and tell the user: "RAG not connected — run `/rag` to start the server, then retry."

   Report current counts before indexing so the user can see what changed:
   - knowledge: N chunks, N files
   - agents: N chunks, N files

3. **Index** — call `POST http://127.0.0.1:8613/index-project` via Bash (substitute the
   parsed `<scope>` string and `<force>` boolean into the JSON):
   ```bash
   curl -s --max-time 120 -X POST http://127.0.0.1:8613/index-project -H "Content-Type: application/json" -d '{"scope":"<scope>","force":<force>}'
   ```

4. **Report results**:
   - Call `GET http://127.0.0.1:8613/status` again to get updated counts
   - Show a before/after table:
     ```
     Collection   Before              After
     knowledge    1600 chunks / 96f   XXXX chunks / XXf
     agents        279 chunks / 25f    XXX chunks / XXf
     ```
   - Note if counts changed (new files picked up) or stayed the same (already current)
   - If `force=true`: confirm full reindex completed

5. **Post-index quality check** — run `/rag-health` with the appropriate scope:
   - If `scope="knowledge"` → run `/rag-health knowledge`
   - If `scope="agents"` → run `/rag-health agents`
   - If `scope="all"` → run `/rag-health all`

   Follow any actions listed in the health check output.

6. **Done** — one line: "Boost RAG is current." or "Boost RAG updated — N new chunks indexed." Append any warnings from `/rag-health`.
