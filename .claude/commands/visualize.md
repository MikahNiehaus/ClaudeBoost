---
description: Interactive Architecture Board — generate a visual project architecture map that opens in the browser
---

# Interactive Architecture Board

Generate a professional dark-themed SVG architecture diagram as a self-contained HTML file and open it in the browser. Claude writes the HTML directly — no intermediate JSON, no render scripts.

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

Call `rag_context(agent="workflow-agent", task_description="architecture visualization of current project", max_tokens=3000)`.

If it fails: stop and tell the user "RAG is not connected. Run /rag before using this skill."

---

## Step 1: Detect Mode

```bash
ls agents/ knowledge/ 2>/dev/null | head -5
```

- Both `agents/` and `knowledge/` exist → **self-map mode** (ClaudeBoost itself)
- Otherwise → **project-map mode**

User can override: `--self` forces self-map, `--project` forces project-map.

---

## Step 2a: Self-Map — Gather Data

Read ClaudeBoost's structure to populate the diagram:

1. **Agents** — list names and expertise:
   ```bash
   grep -r "<name>\|<expertise>" agents/*.xml | head -80
   ```
   Group by tier:
   - **Opus agents**: architect-agent, reviewer-agent, ticket-analyst-agent
   - **Quality agents**: security-agent, test-agent, debug-agent, performance-agent, refactor-agent, evaluator-agent
   - **Support agents**: everything else

2. **Knowledge bases** — count by category:
   ```bash
   ls knowledge/lang-*.xml | wc -l
   ls knowledge/fw-*.xml | wc -l
   ls knowledge/*.xml | grep -v lang- | grep -v fw- | wc -l
   ```

3. **Scripts** — list the major ones:
   ```bash
   ls scripts/*.py | head -20
   ```

4. **Commands** — count slash commands:
   ```bash
   ls .claude/commands/*.md | wc -l
   ```

Build this mental model for the diagram:
- **Layer 1 INPUT**: User
- **Layer 2 ORCHESTRATOR**: Claude Code + ClaudeBoost hooks (session-primer, context-nudge, agent-spawn-gate, rag-server-guard)
- **Layer 3 AGENTS**: Three columns — Opus tier, Quality tier, Support tier
- **Layer 4 RAG / KNOWLEDGE**: RAG server (port 8612) + three knowledge categories (domain, language guides, framework guides)
- **Left rail**: Scripts and hooks infrastructure
- **Right rail**: External integrations (MCP servers, edge-tts, git)

---

## Step 2b: Project-Map — Gather Data

For non-ClaudeBoost repos:

1. List top-level structure and read key config files:
   ```bash
   ls -la && cat package.json 2>/dev/null || cat pyproject.toml 2>/dev/null || cat Cargo.toml 2>/dev/null
   ```
2. Use RAG if available: `rag_search(scope="codebase", query="services endpoints data models API", mode="graph", limit=8)`
3. Identify 6–18 key components: entry points, services/modules, data stores, external APIs, middleware, config
4. Map their relationships: which calls which, which reads/writes where

---

## Step 3: Write the HTML File

Write a **fully self-contained** HTML file. No external CDN, no Google Fonts, no network requests. All CSS and JS inline.

### Design system

```
Background:        #020617
Grid overlay:      #0f172a (40px grid lines, opacity 0.4)
Surface:           #0f172a
Card background:   #1e293b
Border:            #334155
Text primary:      #f1f5f9
Text muted:        #94a3b8
Font:              -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif
Monospace:         'Consolas', 'Courier New', monospace
```

### Component color palette

| Type | Fill | Border | Label |
|------|------|--------|-------|
| User / Input | `#0ea5e9` | `#38bdf8` | `#e0f2fe` |
| Orchestrator / Core | `#f97316` | `#fb923c` | `#fff7ed` |
| Agent / Worker | `#22c55e` | `#4ade80` | `#f0fdf4` |
| Knowledge / RAG | `#a855f7` | `#c084fc` | `#faf5ff` |
| Storage / Database | `#f59e0b` | `#fbbf24` | `#fffbeb` |
| External / API | `#06b6d4` | `#22d3ee` | `#ecfeff` |
| Scripts / Hooks | `#10b981` | `#34d399` | `#ecfdf5` |
| Config | `#64748b` | `#94a3b8` | `#f8fafc` |

### HTML structure

```
<html>
  <head>
    <style>  ← all CSS inline </style>
  </head>
  <body style="background:#020617; margin:0; font-family:system-ui">
    <!-- Header bar: title left, export buttons right -->
    <div id="toolbar">
      <h1>Project Name · Architecture</h1>
      <div>
        <button onclick="copyPNG()">Copy</button>
        <button onclick="downloadPNG()">PNG</button>
        <button onclick="window.print()">PDF</button>
      </div>
    </div>

    <!-- Main SVG diagram -->
    <svg id="diagram" viewBox="0 0 1100 [height]" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <!-- arrowhead marker -->
        <marker id="arrow" markerWidth="10" markerHeight="7"
                refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#475569"/>
        </marker>
        <!-- grid pattern -->
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#0f172a" stroke-width="1"/>
        </pattern>
      </defs>

      <!-- Grid background -->
      <rect width="100%" height="100%" fill="url(#grid)"/>

      <!-- DRAW ARROWS FIRST (so they render behind boxes) -->
      <!-- connection lines with marker-end="url(#arrow)" -->
      <!-- use <path> for curved connections, <line> for straight -->

      <!-- THEN DRAW COMPONENT BOXES on top -->
      <!-- each component: <g id="comp-id" class="node" onclick="showDetail(...)">
             <rect rx="8" fill="[surface]" stroke="[type-border]" stroke-width="2"/>
             <rect width="4" height="[h]" rx="2" fill="[type-fill]"/>  ← left accent bar
             <text fill="[text-primary]" font-weight="600">Title</text>
             <text fill="[text-muted]" font-size="12">Subtitle</text>
           </g> -->

      <!-- Layer labels (left margin text) -->
      <!-- <text x="20" y="[mid-y]" fill="#475569" font-size="11"
             writing-mode="tb" letter-spacing="2">LAYER NAME</text> -->
    </svg>

    <!-- Detail panel (shown on node click) -->
    <div id="detail-panel" style="display:none; position:fixed; right:20px; top:80px;
         width:280px; background:#1e293b; border:1px solid #334155; border-radius:12px;
         padding:20px; color:#f1f5f9">
      <button onclick="closeDetail()" style="float:right">✕</button>
      <div id="detail-type-badge"></div>
      <h3 id="detail-title"></h3>
      <p id="detail-desc" style="color:#94a3b8; font-size:14px"></p>
      <ul id="detail-list" style="color:#cbd5e1; font-size:13px; padding-left:16px"></ul>
    </div>

    <script>
      // Component data for detail panel
      const COMPONENTS = { /* id: {title, type, desc, items:[]} */ };

      function showDetail(id) {
        const c = COMPONENTS[id]; if (!c) return;
        document.getElementById('detail-title').textContent = c.title;
        document.getElementById('detail-desc').textContent = c.desc;
        // populate list...
        document.getElementById('detail-panel').style.display = 'block';
      }

      function closeDetail() {
        document.getElementById('detail-panel').style.display = 'none';
      }

      document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

      // PNG export — draw SVG to canvas then download / copy
      async function svgToCanvas() {
        const svg = document.getElementById('diagram');
        const data = new XMLSerializer().serializeToString(svg);
        const blob = new Blob([data], {type:'image/svg+xml'});
        const url = URL.createObjectURL(blob);
        const img = new Image();
        await new Promise(r => { img.onload = r; img.src = url; });
        const canvas = document.createElement('canvas');
        canvas.width = svg.viewBox.baseVal.width * 2;   // 2x for retina
        canvas.height = svg.viewBox.baseVal.height * 2;
        const ctx = canvas.getContext('2d');
        ctx.scale(2, 2);
        ctx.fillStyle = '#020617';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        URL.revokeObjectURL(url);
        return canvas;
      }

      async function downloadPNG() {
        const canvas = await svgToCanvas();
        const a = document.createElement('a');
        a.download = 'architecture.png';
        a.href = canvas.toDataURL('image/png');
        a.click();
      }

      async function copyPNG() {
        const canvas = await svgToCanvas();
        canvas.toBlob(blob => {
          navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
        }, 'image/png');
      }
    </script>

    <style>
      @media print {
        #toolbar button { display: none; }
        body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      }
    </style>
  </body>
</html>
```

### SVG layout rules

**Layered (self-map and most projects):**
- Layers stack top-to-bottom with ~80px vertical gap between layers
- Components in a layer spread horizontally, centered, with ~20px gap between boxes
- Box size: 160×70px minimum; expand width for long titles
- Layer label: rotated text in left margin at x=14
- Connection arrows: straight `<line>` for same-column, `<path>` with a mid-point curve for cross-column; always drawn *before* boxes so they sit behind them
- Connection label: small `<text>` on the midpoint of the line, background rect for readability

**Side rails (cross-cutting concerns):**
- Left rail x=0–110, right rail x=990–1100
- Rail boxes are narrower (100px wide), stacked vertically
- Dashed `<line>` connections from rail boxes to the layers they affect

### Quality bar — check before writing the file

- Every component box has a colored left-accent bar (4px wide rect at x=box_x, same height as box)
- Every connection has a descriptive label (not just an arrow)
- No components overlap
- SVG `viewBox` height is computed from actual content, not hardcoded
- Detail panel `COMPONENTS` map has an entry for every clickable node

---

## Step 4: Save and Open

Save the file:
- If `workspace/[task-id]/` exists → save to `workspace/[task-id]/visualize/architecture.html`
- Otherwise create `workspace/visualize-YYYY-MM-DD/` and save there

Open in browser (Windows — always use cygpath):
```bash
WIN_PATH="$(cygpath -w "$(realpath [path-to-architecture.html])")" && cmd.exe /c start "" "$WIN_PATH"
```

**Never pass a bash/Unix path directly to `cmd.exe`** — it only understands Windows paths.

---

## Step 5: Report

Tell the user:
- How many components were diagrammed and how many connections
- Where the file was saved
- That it's open in their browser
- Click any box to see details. Export with the Copy / PNG / PDF buttons.
