# Interactive Architecture Board

Generate an interactive visual board of the project's architecture — boxes for components, lines showing connections, click to drill into details. Opens in a browser tab.

## Step 1: Detect Mode

Check if the current working directory has both `agents/` and `knowledge/` directories:

```bash
ls agents/ knowledge/ 2>/dev/null | head -5
```

- If both exist → **self-map mode** (ClaudeBoost itself). Use the automated extractor.
- If not → **project-map mode**. Claude analyzes the repo and builds the graph manually.

User can override with args: `--self` forces self-map, `--project` forces project-map.

## Step 2a: Self-Map (automated extractor)

Run the extractor to build graph.json from the repo's own structure:

```bash
python "$CLAUDEBOOST_HOME/scripts/visualize-extract.py" "." "graph.json"
```

Then skip to Step 3.

## Step 2b: Project-Map (Claude-driven)

For non-ClaudeBoost repos, analyze the project architecture manually:

1. Read the template: `$CLAUDEBOOST_HOME/scripts/visualize-template.json`
2. Explore the repo structure: entry points, modules, services, data stores, external deps
3. Use `rag_search` if RAG is available, or read top-level files directly
4. Build `graph.json` following the template structure

Node kinds for project-map: `service`, `module`, `datastore`, `external`, `middleware`, `config`.

Edge kinds: `calls`, `reads`, `writes`, `depends`, `triggers`, `composes`.

Write style: one clear sentence per node purpose. Responsibilities are optional — use for complex nodes only.

## Step 3: Save Outputs

Save to the workspace:
1. If `workspace/[task-id]/` exists, save to `workspace/[task-id]/visualize/`
2. Otherwise create `workspace/visualize-YYYY-MM-DD/visualize/`

Write:
- `graph.json` — the raw graph data
- `visualize.html` — rendered self-contained HTML

Render the HTML:
```bash
python "$CLAUDEBOOST_HOME/scripts/visualize-viewer/render.py" "graph.json" "visualize.html"
```

## Step 4: Launch

Open the board in the default browser using a Windows-format path:
```bash
WIN_PATH="$(cygpath -w "$(realpath workspace/[output-dir]/visualize/visualize.html)")" && cmd.exe /c start "" "$WIN_PATH"
```

Replace `[output-dir]` with the actual directory name (e.g., `visualize-2026-05-09`).

**NEVER pass `$(pwd)` or bash paths directly to `cmd.exe`, `start`, or `explorer.exe`** — bash returns Unix paths (`/c/Development/...`) that cmd.exe cannot parse. Always convert with `cygpath -w` first.

## Step 5: Report

Tell the user:
- How many nodes and edges were extracted/generated
- Where the files were saved
- That the board is open in their browser
- Keyboard shortcuts: `esc` close drawer, `/` search, `r` reset zoom, `1-4` switch layout, `dblclick` focus mode

