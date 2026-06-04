---
description: Interactive Architecture Board — generate a visual project architecture map that opens in the browser
---

# Interactive Architecture Board

Generate a professional interactive architecture diagram as a self-contained HTML file and open it in the browser. Claude writes the HTML directly using **CSS flexbox layout** — no SVG pixel coordinates, no coordinate math, no overlaps.

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

Call `POST http://127.0.0.1:8612/context` with:
```json
{"agent":"workflow-agent","task_description":"architecture visualization of current project","project_path":"<cwd>"}
```

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

## Step 2a: Self-Map — Get Data from Extractor

Run the extractor — it reads all agents, knowledge files, hooks, and commands in one shot:

```bash
python -c "
import os,subprocess,sys,json
h=os.environ['CLAUDEBOOST_HOME']
t=os.environ.get('TEMP','/tmp')
r=subprocess.run([sys.executable,h+'/scripts/visualize-extract.py',h,t+'/cb-graph.json'])
if r.returncode==0:
    print(open(t+'/cb-graph.json').read())
sys.exit(r.returncode)
"
```

Read the JSON output. Use the `layers`, `side_rails`, and card fields (`title`, `subtitle`, `detail`, `responsibilities`, `icon`, `accent`) as your content. Do not run any other data-gathering commands — everything is already in the JSON.

---

## Step 2b: Project-Map — Gather Data

1. Read top-level structure and key config:
   ```bash
   ls -la && cat package.json 2>/dev/null || cat pyproject.toml 2>/dev/null || cat Cargo.toml 2>/dev/null
   ```
2. If RAG project index exists: `POST http://127.0.0.1:8612/search` with `{"scope":"codebase","mode":"graph","query":"services endpoints data models","project_path":"<cwd>","limit":8}`
3. Identify **8–15 key components**: entry points, services, data stores, external APIs, middleware. Cap at 15 — more components hurt clarity.

---

## Step 3: Write the HTML File

Write a fully self-contained HTML file. No external CDN, no fonts, no network requests. All CSS and JS inline. **Use CSS flexbox layout throughout — never use pixel-positioned SVG elements.**

### Design tokens

```css
--bg:      #020617
--surface: #0f172a
--card-bg: #1e293b
--border:  #334155
--text:    #f1f5f9
--muted:   #94a3b8
```

### Component accent colors (use as `border-left-color` on each card)

| Type | Color |
|------|-------|
| User / Input | `#0ea5e9` |
| Orchestrator / Core | `#f97316` |
| Agent / Worker | `#22c55e` |
| Knowledge / RAG | `#a855f7` |
| Storage / Database | `#f59e0b` |
| External / API | `#06b6d4` |
| Scripts / Hooks | `#10b981` |
| Config | `#64748b` |

### HTML structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>[Project] · Architecture</title>
<style>
/* === RESET + BASE === */
*, *::before, *::after { box-sizing: border-box; }
body { background: #020617; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; margin: 0; }

/* === TOOLBAR === */
.toolbar { display: flex; justify-content: space-between; align-items: center;
           padding: 12px 20px; background: #0f172a; border-bottom: 1px solid #334155;
           position: sticky; top: 0; z-index: 10; }
.toolbar h1 { margin: 0; font-size: 15px; font-weight: 600; }
.toolbar button { background: #1e293b; color: #f1f5f9; border: 1px solid #334155;
                  padding: 6px 14px; border-radius: 6px; cursor: pointer; margin-left: 8px;
                  font-size: 12px; }
.toolbar button:hover { background: #334155; }

/* === BOARD GRID: left-rail | layers | right-rail === */
.board { display: grid; grid-template-columns: 130px 1fr 130px; gap: 20px;
         padding: 24px; align-items: start; }

/* === LAYERS (center column) === */
.layers { display: flex; flex-direction: column; gap: 0; }
.layer { display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; }
.layer-label { writing-mode: vertical-rl; text-orientation: mixed; font-size: 9px;
               letter-spacing: 3px; color: #475569; text-transform: uppercase;
               min-width: 20px; padding-top: 6px; flex-shrink: 0; }
.cards { display: flex; flex-wrap: wrap; gap: 10px; }
.layer-arrow { color: #475569; font-size: 11px; padding: 4px 0 4px 32px; }

/* === CARD === */
.card { background: #1e293b; border: 1px solid #334155; border-left: 4px solid #334155;
        border-radius: 8px; padding: 11px 13px; min-width: 130px; max-width: 190px;
        cursor: pointer; transition: background 0.12s; }
.card:hover { background: #253347; }
.card-icon { font-size: 17px; display: block; margin-bottom: 5px; }
.card-title { font-size: 12px; font-weight: 600; color: #f1f5f9; line-height: 1.3; }
.card-sub { font-size: 10px; color: #94a3b8; margin-top: 3px; line-height: 1.4; }
.card-badge { display: inline-block; font-size: 9px; padding: 1px 6px; border-radius: 10px;
              margin-top: 5px; font-weight: 500; }

/* Columns inside a layer (for sub-grouped tiers) */
.col-group { display: flex; flex-direction: column; gap: 6px; }
.col-label { font-size: 9px; color: #64748b; text-transform: uppercase; letter-spacing: 1px;
             padding-bottom: 2px; border-bottom: 1px solid #1e293b; }

/* === RAILS (flanking columns) === */
.rail { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; }
.rail-card { background: #1e293b; border: 1px solid #334155; border-left: 3px solid #64748b;
             border-radius: 6px; padding: 9px 10px; cursor: pointer; }
.rail-card:hover { background: #253347; }
.rc-title { font-size: 11px; font-weight: 600; color: #f1f5f9; }
.rc-sub { font-size: 9px; color: #94a3b8; margin-top: 2px; }

/* === DETAIL PANEL === */
.detail { position: fixed; right: 0; top: 0; height: 100vh; width: 300px;
          background: #0f172a; border-left: 1px solid #334155; padding: 20px;
          overflow-y: auto; z-index: 100; }
.detail.hidden { display: none; }
.detail-close { float: right; background: none; border: none; color: #64748b;
                font-size: 20px; cursor: pointer; line-height: 1; }
.detail-close:hover { color: #f1f5f9; }
.detail-type { display: inline-block; font-size: 10px; padding: 2px 8px; border-radius: 10px;
               background: #1e293b; color: #94a3b8; margin-bottom: 10px; margin-top: 4px; }
.detail h2 { margin: 6px 0 10px; font-size: 15px; clear: both; }
.detail p { color: #94a3b8; font-size: 12px; line-height: 1.6; margin-bottom: 12px; }
.detail ul { color: #cbd5e1; font-size: 12px; padding-left: 16px; line-height: 1.9; margin: 0; }

/* === PRINT === */
@media print {
  .toolbar button, .detail { display: none !important; }
  body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
</style>
</head>
<body>

<div class="toolbar">
  <h1>[Project Name] · Architecture</h1>
  <div>
    <button onclick="downloadSVG()">SVG</button>
    <button onclick="window.print()">PDF</button>
  </div>
</div>

<div class="board" id="board">

  <!-- Left rail (cross-cutting concerns) -->
  <aside class="rail rail-left">
    <div class="rail-card" style="border-left-color:#e74c3c" onclick="showDetail('global-rules')">
      <div class="rc-title">🔒 Global Rules</div>
      <div class="rc-sub">~/.claude/CLAUDE.md</div>
    </div>
    <!-- more rail cards... -->
  </aside>

  <!-- Main layers -->
  <main class="layers">

    <section class="layer">
      <div class="layer-label">INPUT</div>
      <div class="cards">
        <div class="card" style="border-left-color:#0ea5e9" onclick="showDetail('you')">
          <span class="card-icon">👤</span>
          <div class="card-title">You</div>
          <div class="card-sub">Chat · tickets · slash commands</div>
        </div>
      </div>
    </section>

    <div class="layer-arrow">classifies as ↓</div>

    <section class="layer">
      <div class="layer-label">CLASSIFICATION</div>
      <div class="cards">
        <!-- cards for this layer... -->
      </div>
    </section>

    <div class="layer-arrow">routes to ↓</div>

    <!-- For layers with sub-columns (e.g. agent tiers): -->
    <section class="layer">
      <div class="layer-label">AGENTS</div>
      <div class="cards" style="align-items:flex-start">
        <div class="col-group">
          <div class="col-label">Opus — Strategic</div>
          <div class="card" style="border-left-color:#22c55e" onclick="showDetail('architect')">
            <div class="card-title">architect-agent</div>
            <div class="card-sub">System design, SOLID review</div>
          </div>
          <!-- more cards in column -->
        </div>
        <div class="col-group">
          <div class="col-label">Sonnet — Quality</div>
          <!-- cards -->
        </div>
        <!-- more col-groups -->
      </div>
    </section>

    <div class="layer-arrow">searches ↓</div>

    <!-- more layers... -->

  </main>

  <!-- Right rail -->
  <aside class="rail rail-right">
    <!-- rail cards -->
  </aside>

</div>

<!-- Detail panel -->
<div id="detail" class="detail hidden">
  <button class="detail-close" onclick="closeDetail()">✕</button>
  <div id="detail-type" class="detail-type"></div>
  <h2 id="detail-title"></h2>
  <p id="detail-desc"></p>
  <ul id="detail-list"></ul>
</div>

<script>
// Component data — one entry per clickable card
const COMPONENTS = {
  'you': {
    title: 'You',
    type: 'Input',
    desc: 'You interact with Claude Code normally. ClaudeBoost changes how Claude thinks behind the scenes.',
    items: [
      'Type requests, paste tickets, or run slash commands',
      'Approve or adjust architectural proposals (CONSULT mode)',
    ]
  },
  'global-rules': {
    title: 'Global Rules',
    type: 'Config',
    desc: 'Hard rules loaded from ~/.claude/CLAUDE.md at every session. Not debatable.',
    items: [
      'jQuery ban — use React hooks / vanilla JS',
      'Parameterized queries only',
      'logger.error in every catch block',
      'No secrets in logs, URLs, or source code',
    ]
  },
  // add one entry per card id...
};

function showDetail(id) {
  const c = COMPONENTS[id];
  if (!c) return;
  document.getElementById('detail-title').textContent = c.title;
  document.getElementById('detail-type').textContent = c.type || '';
  document.getElementById('detail-desc').textContent = c.desc || '';
  document.getElementById('detail-list').innerHTML = (c.items || []).map(i => `<li>${i}</li>`).join('');
  document.getElementById('detail').classList.remove('hidden');
}

function closeDetail() {
  document.getElementById('detail').classList.add('hidden');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

function downloadSVG() {
  const board = document.getElementById('board');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${board.scrollWidth}" height="${board.scrollHeight}">
    <foreignObject width="100%" height="100%">
      <html xmlns="http://www.w3.org/1999/xhtml"><body style="margin:0;background:#020617">${board.outerHTML}</body></html>
    </foreignObject>
  </svg>`;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml'}));
  a.download = 'architecture.svg';
  a.click();
}
</script>

</body>
</html>
```

### Layout rules

- Every layer needs a `layer-label` and a `cards` div — no exceptions
- Between layers: `<div class="layer-arrow">flow description ↓</div>`
- Multi-column layers (e.g. agent tiers): wrap `card-group` divs side by side inside `.cards`
- `COMPONENTS` map must have an entry for every `onclick="showDetail('id')"` id on the page
- Colors: always set `border-left-color` on each card to match its component type
- Never use pixel positions, `position: absolute`, or SVG coordinate math

---

## Step 4: Save and Open

Pick an output directory:
- If `workspace/[task-id]/` exists → save to `workspace/[task-id]/visualize/architecture.html`
- Otherwise create `workspace/visualize-YYYY-MM-DD/` and save there

Open in browser (Windows):
```bash
powershell.exe -NoProfile -Command "Start-Process 'C:\path\to\architecture.html'"
```

Use the literal Windows path with backslashes. Do not use `cygpath` or `cmd.exe /c start`.

---

## Step 5: Report

Tell the user:
- How many components and layers are in the diagram
- Where the file was saved
- Click any card to see details. Export with the SVG / PDF buttons.
