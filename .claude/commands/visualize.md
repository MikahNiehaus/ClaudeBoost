---
description: Interactive Visual Board — generate a visual diagram of any concept, system, flow, or architecture and open it in the browser
---

# Interactive Visual Board

Generate a professional interactive diagram as a self-contained HTML file and open it in the browser. This skill visualizes anything — system architecture, data flows, auth sequences, pipelines, how a feature works, and more. Claude writes the HTML directly using **CSS flexbox layout** — no SVG pixel coordinates, no coordinate math, no overlaps.

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

Call `POST http://127.0.0.1:8612/context` with:
```json
{"agent":"workflow-agent","task_description":"visual diagram: $ARGUMENTS — current project","project_path":"<cwd>"}
```

If it fails: stop and tell the user "RAG is not connected. Run /rag before using this skill."

**0b — Verify project is indexed** (required for codebase search to work):

Detect the project path:
1. Read `$CLAUDEBOOST_HOME/state/project-workspaces.json` — use the entry keyed by the current working directory to get the active workspace ID, then look up `project_path` in `workspaces.json`. Fall back to current working directory if the file doesn't exist or has no entry for this directory.

Call `GET http://127.0.0.1:8612/status` and check `indexed_projects` for the detected path.

- **Indexed**: note file/chunk counts and continue.
- **Not indexed**: run `Skill(skill="index-project", args="<project_path>")` immediately. Do not continue until indexing completes.
- **RAG offline**: stop and tell the user to run `/rag` first.

---

## Phase 0c: Determine What to Visualize

Read `$ARGUMENTS` (the text the user typed after `/visualize`).

Derive three things you'll use throughout:
- **TOPIC** — a human-readable title for what's being visualized (e.g. "Auth Flow", "RAG Pipeline", "CI/CD Pipeline", "Architecture")
- **SLUG** — a lowercase, hyphenated filename stem (e.g. `auth-flow`, `rag-pipeline`, `ci-cd-pipeline`, `architecture`)
- **MODE** — one of: `concept`, `self-map`, `project-map`

Rules:
- `$ARGUMENTS` is empty or `--project` → **project-map** mode, TOPIC = "Architecture", SLUG = `architecture`
- `$ARGUMENTS` is `--self` → **self-map** mode, TOPIC = "How ClaudeBoost Works", SLUG = `claudeboost`
- `$ARGUMENTS` describes a concept, flow, or question (e.g. "auth flow", "how the RAG system works", "data pipeline") → **concept** mode; derive TOPIC and SLUG from the argument text

For concept mode: TOPIC = title-cased version of the argument, SLUG = lowercase hyphenated (strip "how", "the", "a" if they'd make the slug awkward). Example: `how the RAG system works` → TOPIC `RAG System`, SLUG `rag-system`.

Carry TOPIC, SLUG, and MODE forward. Use TOPIC in the HTML title and toolbar. Use SLUG for the output filename.

---

## Phase 0d: Audience Calibration (concept mode only)

**Only run when MODE = concept.**

Before designing layers, decide who this diagram is for. Look at the TOPIC and any phrasing in `$ARGUMENTS` for signals:

| Signal | Audience tier |
|--------|--------------|
| "how does X work", "explain X", "what is X" | **Novice** — explain from scratch |
| "X flow", "X pipeline", "X architecture" (no "how") | **Technical** — assume familiarity, skip basics |
| "X deep dive", "X internals", "X implementation" | **Expert** — full detail, jargon fine |

**Default for concept mode: Novice-first.**

Novice-first rules (apply unless TOPIC signals technical/expert audience):
- Open each layer label and card subtitle with plain language, not jargon. Add the technical term after: `"Stores results (vector database)"`
- Use one real-world analogy per card detail panel before any technical explanation. Example: "Think of this as a card catalog — it lets the system find relevant documents by meaning, not just keywords."
- Define acronyms on first use in the audio tour: "RAG — short for Retrieval-Augmented Generation — works like..."
- Put dense technical detail (config values, code paths, API contracts) in the collapsible `<details>` section of each detail panel, not in the main body
- The board should answer "what does this do for me?" before "how does it work?"

---

## Step 1: Detect Mode

```bash
ls agents/ knowledge/ 2>/dev/null | head -5
```

- `MODE` is already set from Phase 0c — skip detection only if the user passed an explicit flag (`--self`, `--project`) or a concept argument.
- If no argument was given, use the directory check: both `agents/` and `knowledge/` exist → set MODE to **self-map**; otherwise **project-map**.

User can always override: `--self` forces self-map, `--project` forces project-map.

---

## Step 2a: Self-Map — Get Data from Extractor

Run the extractor — it reads all agents, knowledge files, hooks, and commands in one shot:

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/visualize-extract.py" "${CLAUDEBOOST_HOME}" /tmp/cb-graph.json
```

Then **Read** `/tmp/cb-graph.json` with the Read tool. Use the `layers`, `side_rails`, and card fields (`title`, `subtitle`, `detail`, `responsibilities`, `icon`, `accent`) as your content. Do not run any other data-gathering commands — everything is already in the JSON.

---

## Step 2b: Project-Map — Gather Data

1. Read top-level structure and key config:
   ```bash
   ls -la && cat package.json 2>/dev/null || cat pyproject.toml 2>/dev/null || cat Cargo.toml 2>/dev/null
   ```
2. If RAG project index exists: `POST http://127.0.0.1:8612/search` with `{"scope":"codebase","mode":"graph","query":"services endpoints data models","project_path":"<cwd>","limit":8}`
3. Identify **8–15 key components**: entry points, services, data stores, external APIs, middleware. Cap at 15 — more components hurt clarity.

---

## Step 2c: Ticket Context Enrichment (runs whenever a workspace ticket is available)

After gathering project/self-map data, check for active ticket context. This step turns a plain architecture map into a *why are we here* diagram.

**Check for workspace files:**

From the workspace detected in Phase 0b, look for (in order):
- `<workspace>/ticket.md` — full ticket text with acceptance criteria
- `<workspace>/context.md` — app map and key flows built during E2E testing
- `<workspace>/plan.md` — test/implementation plan with per-scenario pass/fail/blocked status

**If ticket files are found, extract:**
- `TICKET_ID` — e.g., "TFF-1038"
- `TICKET_SUMMARY` — one sentence: what does this ticket do?
- `PROBLEM_STATEMENT` — what was broken or missing *before* this ticket? What triggered it?
- `SOLUTION_DESCRIPTION` — what does the ticket deliver? What can users do now that they couldn't before?
- `ACCEPTANCE_CRITERIA` — list of AC items, each with status: ✅ PASS / ❌ FAIL / ⏳ BLOCKED / 🔲 NOT TESTED
  Pull statuses from `plan.md` TC rows: `[x]` = PASS, `[ ]` = open (check if BLOCKED in the note).

**Add to the HTML diagram:**

1. **TICKET layer** — place at the very top of the board, before all other layers. Contains two cards side by side:
   - `ticket-problem` card (red accent `#ef4444`): titled "Before: [problem]" — what was missing/broken
   - `ticket-solution` card (green accent `#22c55e`): titled "After: [what it delivers]" — the high-level outcome

2. **Acceptance Criteria rail card** — add to left rail with red accent. Its detail panel shows a full AC table:
   ```javascript
   // AC table pattern:
   `<table style="width:100%;border-collapse:collapse;font-size:10px;margin-top:4px">
   <tr style="border-bottom:1px solid #334155">
     <th style="text-align:left;padding:4px 6px;color:#64748b;font-weight:600">Scenario</th>
     <th style="padding:4px 6px;color:#64748b;font-weight:600">TC</th>
     <th style="padding:4px 6px;color:#64748b;font-weight:600">Status</th>
   </tr>
   <tr><td style="padding:3px 6px;color:#f1f5f9">Flag OFF → 404</td>
       <td style="padding:3px 6px;color:#64748b">TC-002</td>
       <td style="padding:3px 6px;color:#22c55e">✅ PASS</td></tr>
   <!-- one row per scenario -->
   </table>`
   ```
   Status colors: `#22c55e` = PASS, `#ef4444` = FAIL, `#f59e0b` = BLOCKED, `#475569` = NOT TESTED

3. **Enhance ticket-relevant component detail panels** — for every card whose component directly implements or is changed by the ticket, add to its `html:` detail panel:
   - A **Before/After** section using `FLOW_ROW` showing state before and after the ticket
   - A **Scenario coverage** block listing which AC items this component is responsible for
   - A **Code path** reference (file:line) for the key logic

If no workspace ticket is found: skip this step silently and proceed to Step 3.

---

## Step 2d: Concept Mode — Gather Data

**Only run this step when MODE = concept.**

The goal is to understand the topic well enough to explain it visually as a layered flow. Gather from whichever sources apply:

1. **RAG knowledge search**: `POST http://127.0.0.1:8612/search` with `{"scope":"all","query":"<TOPIC>","limit":6}` — pull relevant knowledge files.
2. **Codebase search (both modes)**: `POST http://127.0.0.1:8612/search` with `{"scope":"codebase","mode":"both","query":"<TOPIC>","project_path":"<cwd>","limit":8}` — find the files that implement or relate to the concept.
3. **Read key files** identified above (no more than 5) to understand the actual implementation.

From those sources, identify:
- **4–8 key concepts, steps, or components** that make up this topic
- A **natural ordering** — left-to-right flow, top-to-bottom pipeline, or layered hierarchy
- **What happens at each step**: inputs, outputs, decisions, side effects

Use this to design the layers.

**Layer naming rules:**
- Use verb phrases, not nouns. Name layers after what they DO, not what they ARE. This tells the viewer what the stage accomplishes at a glance.
  - Good: "RECEIVES QUERY", "FINDS RELEVANT DOCS", "BUILDS CONTEXT", "GENERATES ANSWER"
  - Bad: "INPUT", "RETRIEVAL", "CONTEXT", "OUTPUT"
- Examples by topic:
  - Auth flow → "RECEIVES REQUEST", "VERIFIES IDENTITY", "ISSUES TOKEN", "GRANTS ACCESS"
  - RAG pipeline → "RECEIVES QUERY", "FINDS RELEVANT DOCS", "ASSEMBLES CONTEXT", "GENERATES ANSWER"
  - CI/CD → "PUSHES CODE", "BUILDS ARTIFACT", "RUNS TESTS", "DEPLOYS", "MONITORS"

**One message per layer:**
Each layer communicates a single concept. Ask: "What is the one thing a viewer should understand about this stage?" Write a layer subtitle (used in the audio tour intro for that segment) that completes the sentence: "This stage exists because..."

If a stage has more than one distinct purpose, split it into two layers.

**Max 5 cards per layer:**
Never put more than 5 cards in a single layer. If a concept has more than 5 components at one stage, group them into sub-themes using `col-group` columns inside the layer, or move detail into the panel rather than adding more cards. More than 5 cards per row overwhelms working memory (cognitive load research finding).

Cap at 8 layers total. The diagram is a teaching tool — clarity beats completeness.

---

### Enhanced detail panel patterns (use in COMPONENTS `html:`)

**Before/After state diagram** — use this for any component that changes behaviour:
```javascript
html: `<div style="font-size:11px;color:#94a3b8;margin-bottom:10px">Description of what this component does.</div>
${SECTION('Before', '')}
${FLOW_ROW('#ef4444','❌ Old behaviour or missing state','What happened before this ticket')}
${SECTION('After (this ticket)', '')}
${FLOW_ROW('#22c55e','✅ New behaviour','What this ticket delivers at this component')}
${SECTION('Code path', '')}
${FLOW_ROW('#64748b','File.cs:line — key method or check','')}`
```

**Scenario / AC coverage table** — for components that implement multiple AC scenarios:
```javascript
html: `...
${SECTION('Scenarios this covers', '')}
<table style="width:100%;border-collapse:collapse;font-size:10px;margin-top:4px">
<tr style="border-bottom:1px solid #334155">
  <th style="text-align:left;padding:3px 5px;color:#64748b">Scenario</th>
  <th style="padding:3px 5px;color:#64748b">Status</th>
</tr>
<tr><td style="padding:3px 5px;color:#f1f5f9">Flag OFF → 404</td><td style="padding:3px 5px;color:#22c55e">✅ TC-002</td></tr>
</table>`
```

**Dependency / blocked state diagram** — for components waiting on another ticket:
```javascript
html: `...
${SECTION('Current state', '')}
${FLOW_ROW('#f59e0b','⏳ BLOCKED','Reason: waiting on TFF-1033')}
${SECTION('Unblocked when', '')}
${FLOW_ROW('#22c55e','TFF-1033 deploys JWT endpoint','Then: configure Tableau:JwtEndpointUrl')}
${ARROW()}
${FLOW_ROW('#22c55e','TC-008, TC-TICKET-01, TC-009, TC-010 become testable','')}`
```

**Step-by-step flow diagram** — for integration flows with multiple hops:
```javascript
html: `...
${SECTION('Integration flow', '')}
${FLOW_ROW('#0ea5e9','Step 1: Admin navigates to /Reports/TableauValidation','')}
${ARROW()}
${FLOW_ROW('#a855f7','Step 2: Flag gate + role check','')}
${ARROW()}
${FLOW_ROW('#f97316','Step 3: Server fetches JWT from endpoint','')}
${ARROW()}
${FLOW_ROW('#06b6d4','Step 4: JWT injected into <tableau-viz> component','')}
${ARROW()}
${FLOW_ROW('#22c55e','Step 5: Dashboard renders in iframe','')} `
```

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
<title>[Project] · [TOPIC]</title>
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
  <h1>[Project Name] · [TOPIC]</h1>
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
  a.download = '[SLUG].svg';
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

## Step 3b: Add Audio Tour (MANDATORY — DO NOT SIMPLIFY)

Every visualization MUST include the **full audio bar system** using the Web Speech API. This is non-negotiable — users expect it in every diagram.

**BANNED — do NOT use these simpler patterns:**
- A small floating overlay div with prev/next/stop buttons
- A toolbar button that toggles a tour mode
- Any approach that does not include the full two-row audio bar at the bottom

**REQUIRED — always use the exact system below.** The canonical reference implementation is at:
`C:\Development\Food and Function\FoodAccessProject\workspace\TFF-1038\visualize\architecture.html`

The full system includes:
- Fixed two-row audio bar at the bottom with play/pause ▶⏸, stop ■, chapters ☰, transcript T
- Voice selector (auto-populated from browser speech synthesis, scored to prefer Microsoft Andrew)
- Speed selector (0.85× / 0.95× / 1.05× / 1.15×)
- Scrub track with chapter tick marks and draggable thumb
- Card pulse animation (blue glow) on highlighted cards during narration
- Chapters panel (click ☰ to jump to any segment)
- Transcript panel (click T to slide in full text, clickable to jump)
- `body { padding-bottom: 110px; }` to leave room for the bar

### Detail panel structure — progressive reveal (concept mode)

Every detail panel should reveal information in three layers, from simple to dense. Never open with technical jargon or a wall of prose.

```javascript
html: `
<!-- Layer 1: Plain English summary (always visible) -->
<div style="font-size:12px;color:#e2e8f0;line-height:1.6;margin-bottom:12px">
  One sentence that a non-technical person could read. What does this do in plain terms?
  Optional: one-sentence analogy. "Think of it like a card catalog — finds documents by meaning, not keywords."
</div>

<!-- Layer 2: Key facts (always visible) -->
${SECTION('How it works', '')}
${FLOW_ROW('#0ea5e9','Fact 1 — what goes in','')}
${ARROW()}
${FLOW_ROW('#a855f7','Fact 2 — what happens inside','')}
${ARROW()}
${FLOW_ROW('#22c55e','Fact 3 — what comes out','')}

<!-- Layer 3: Technical detail (collapsed, opt-in) -->
<details style="margin-top:12px">
  <summary style="font-size:10px;color:#475569;cursor:pointer;user-select:none;letter-spacing:0.5px">TECHNICAL DETAIL</summary>
  <div style="margin-top:8px;font-size:10px;color:#64748b;line-height:1.7">
    Config values, code paths, API contracts, edge cases. Dense is fine here — this is opt-in.
  </div>
</details>`
```

Rules:
- Layer 1 and Layer 2 must always be understandable without Layer 3
- Layer 3 is for people who want to go deeper — keep it collapsed by default
- Never move content from Layer 1/2 into Layer 3 to "save space" — the summary must stand alone
- For ticket-context panels: Before/After blocks go in Layer 2, code paths in Layer 3

---

### COMPONENTS pattern — ALWAYS use `html:` not `desc:`/`items:`

```javascript
// Define these helper functions at the top of the COMPONENTS block:
const FLOW_ROW = (color, text, sub) => `<div style="background:#0f172a;border-left:3px solid ${color};border-radius:4px;padding:6px 9px;font-size:10px;color:#f1f5f9;margin-bottom:3px">${text}${sub ? `<br><span style="font-size:9px;color:#475569">${sub}</span>` : ''}</div>`;
const ARROW = () => `<div style="color:#334155;font-size:10px;padding:0 0 3px 10px">↓</div>`;

// Every COMPONENTS entry uses html: (a template literal with flow diagrams, before/after code, truth tables):
const COMPONENTS = {
  'my-component': {
    title: 'Component Name',
    badge: '🔴 Modify',
    file: 'path/to/file.cs',
    html: `<div style="font-size:11px;color:#94a3b8;margin-bottom:10px">Brief description of what changes.</div>
${FLOW_ROW('#f97316','🚩 Trigger')}${ARROW()}${FLOW_ROW('#06b6d4','💉 Effect')}`,
  },
};
```

**Detail panel must render html: with innerHTML, not textContent:**
```javascript
function showDetail(id) {
  const c = COMPONENTS[id];
  if (!c) return;
  document.getElementById('detail-title').textContent = c.title;
  document.getElementById('detail-badge').textContent = c.badge || '';
  document.getElementById('detail-file').textContent = c.file || '';
  // Use innerHTML for rich diagrams:
  document.getElementById('detail-body').innerHTML = c.html || '';
  document.getElementById('detail').classList.remove('hidden');
}
```
Detail panel HTML must have `<div id="detail-body"></div>` instead of separate `<p>` and `<ul>`.

### TOUR_SEGMENTS — one per layer/major component

```javascript
const TOUR_SEGMENTS = [
  { label: 'Introduction', text: 'Narration text here...', highlights: [], scrollTo: null },
  { label: 'Component Name', text: 'Detail about this component...', highlights: ['component-id'], scrollTo: 'component-id' },
  // ... one segment per major area
];
```

### Image lightbox pattern (use whenever images appear in detail panels or cards)

When any card or detail panel includes an image (screenshot, diagram, chart), render it with the `viz-img` class so clicking it opens a fullscreen lightbox overlay.

**Image in a detail panel** (`html:` field):
```javascript
html: `<img class="viz-img" src="data:image/png;base64,..." alt="Description" style="width:100%;border-radius:6px;margin-top:8px;cursor:zoom-in;">`
// or for a relative path when the HTML and image are in the same folder:
html: `<img class="viz-img" src="screenshot.png" alt="Description" style="width:100%;border-radius:6px;margin-top:8px;cursor:zoom-in;">`
```

**Image embedded in a card** (inside the board layout):
```html
<div class="card" ...>
  <img class="viz-img" src="..." alt="..." style="width:100%;border-radius:4px;margin-top:6px;cursor:zoom-in;">
  <div class="card-title">Card Title</div>
</div>
```

The lightbox CSS, HTML, and JS are included in the sections below — they are always emitted, even if no images are present on first load, because images may be added to detail panels dynamically.

---

### CSS additions (add to `<style>` block)

```css
body { padding-bottom: 110px; } /* room for audio bar */

/* === IMAGE LIGHTBOX (native <dialog>) ===
   showModal() gives us focus trap, Escape key, and ::backdrop for free — no custom JS needed for those. */
dialog.viz-lightbox { border: none; padding: 0; background: transparent; width: 100dvw; height: 100dvh; max-width: 100dvw; max-height: 100dvh; margin: 0; display: flex; align-items: center; justify-content: center; cursor: zoom-out; overflow: hidden; }
dialog.viz-lightbox::backdrop { background: rgba(2,6,23,0.92); cursor: zoom-out; }
dialog.viz-lightbox img { max-width: 92vw; max-height: 90vh; object-fit: contain; border-radius: 8px; box-shadow: 0 24px 80px rgba(0,0,0,0.8); pointer-events: none; cursor: default; }
.viz-lightbox-close { position: fixed; top: 16px; right: 20px; z-index: 1; background: rgba(15,23,42,0.8); border: 1px solid #334155; color: #f1f5f9; font-size: 22px; line-height: 1; width: 38px; height: 38px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.viz-lightbox-close:hover { background: #1e293b; }

/* === AUDIO TOUR BAR (two-row) === */
.audio-bar { position: fixed; bottom: 0; left: 0; right: 0; background: #0f172a; border-top: 1px solid #334155; padding: 10px 20px 8px; z-index: 200; display: flex; flex-direction: column; gap: 8px; }
.audio-row-top { display: flex; align-items: center; gap: 12px; }
.audio-btn { background: #1e293b; color: #f1f5f9; border: 1px solid #334155; border-radius: 50%; width: 34px; height: 34px; font-size: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background 0.1s, border-color 0.1s; }
.audio-btn:hover { background: #334155; }
.audio-btn.active { background: #1d4ed8; border-color: #3b82f6; }
.audio-btn.stop-btn:hover { background: #7f1d1d; border-color: #ef4444; }
.audio-info { flex: 1; min-width: 0; }
.audio-section-label { font-size: 9px; color: #64748b; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 2px; }
.audio-section-text { font-size: 12px; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
.audio-section-text.idle { color: #475569; font-style: italic; font-weight: 400; }
.audio-counter { font-size: 11px; color: #64748b; flex-shrink: 0; white-space: nowrap; font-variant-numeric: tabular-nums; }
.audio-select-group { display: flex; flex-direction: column; gap: 2px; flex-shrink: 0; }
.audio-select-label { font-size: 9px; color: #475569; letter-spacing: 1px; text-transform: uppercase; }
.audio-select { background: #1e293b; color: #f1f5f9; border: 1px solid #334155; border-radius: 5px; padding: 3px 6px; font-size: 10px; cursor: pointer; }
/* Scrub track */
.audio-row-track { position: relative; height: 22px; display: flex; align-items: center; }
.audio-track-outer { width: 100%; height: 22px; display: flex; align-items: center; cursor: pointer; position: relative; user-select: none; }
.audio-track-bg { width: 100%; height: 6px; background: #1e293b; border-radius: 3px; position: relative; overflow: visible; border: 1px solid #334155; }
.audio-track-fill { height: 100%; background: linear-gradient(90deg, #2563eb, #3b82f6); border-radius: 3px 0 0 3px; transition: width 0.35s linear; width: 0%; position: relative; z-index: 1; }
.audio-thumb { position: absolute; width: 14px; height: 14px; background: #60a5fa; border-radius: 50%; border: 2px solid #1d4ed8; top: 50%; transform: translate(-50%, -50%); pointer-events: none; opacity: 0; transition: opacity 0.15s; z-index: 4; left: 0%; }
.audio-track-outer:hover .audio-thumb { opacity: 1; }
.audio-tick { position: absolute; top: -4px; width: 1px; height: 14px; background: #334155; z-index: 3; transform: translateX(-50%); transition: background 0.25s; pointer-events: none; }
.audio-tick.passed { background: #60a5fa; }
/* Card highlight during narration */
@keyframes narrate-pulse { 0% { box-shadow: 0 0 0 0 rgba(59,130,246,0); } 50% { box-shadow: 0 0 28px 6px rgba(59,130,246,0.55); } 100% { box-shadow: 0 0 0 0 rgba(59,130,246,0); } }
.card.narrating, .rail-card.narrating { outline: 2.5px solid #3b82f6; outline-offset: 3px; background: #172554 !important; animation: narrate-pulse 1.6s ease-in-out infinite; }
/* Chapters panel */
.chapters-panel { position: fixed; bottom: 105px; left: 20px; right: 20px; max-width: 640px; margin: 0 auto; background: #0f172a; border: 1px solid #334155; border-radius: 10px; z-index: 210; display: none; padding: 12px 14px 8px; box-shadow: 0 -8px 32px rgba(0,0,0,0.6); }
.chapters-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #1e293b; }
.chapters-header span { font-size: 11px; font-weight: 600; color: #f1f5f9; letter-spacing: 0.5px; }
.chapters-close { background: none; border: none; color: #64748b; cursor: pointer; font-size: 16px; line-height: 1; }
.chapter-row { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 6px; cursor: pointer; border: 1px solid transparent; margin-bottom: 3px; transition: background 0.1s; }
.chapter-row:hover { background: #1e293b; }
.chapter-row.active { background: #172554 !important; border-color: #3b82f6; }
.chapter-num { font-size: 10px; color: #475569; min-width: 18px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.chapter-label { font-size: 12px; color: #f1f5f9; flex: 1; }
.chapter-cards { font-size: 10px; color: #475569; flex-shrink: 0; }
/* Transcript panel */
.transcript-panel { position: fixed; right: 0; top: 0; height: calc(100vh - 100px); width: 320px; background: #0b1220; border-left: 1px solid #334155; z-index: 115; display: flex; flex-direction: column; transform: translateX(100%); transition: transform 0.2s ease; }
.transcript-panel.open { transform: translateX(0); }
.transcript-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 14px 10px; background: #0f172a; border-bottom: 1px solid #1e293b; flex-shrink: 0; }
.transcript-header-title { font-size: 11px; font-weight: 600; color: #f1f5f9; }
.transcript-close { background: none; border: none; color: #64748b; cursor: pointer; font-size: 16px; line-height: 1; padding: 0; }
.transcript-body { overflow-y: auto; flex: 1; padding: 8px 0 12px; }
.transcript-seg { padding: 10px 14px; cursor: pointer; border-left: 3px solid transparent; transition: background 0.1s; }
.transcript-seg:hover { background: #1e293b; }
.transcript-seg.active { background: #0f2040; border-left-color: #3b82f6; }
.tseg-num { font-size: 9px; color: #475569; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 3px; }
.transcript-seg.active .tseg-num { color: #60a5fa; }
.tseg-label { font-size: 11px; font-weight: 600; color: #94a3b8; margin-bottom: 4px; }
.transcript-seg.active .tseg-label { color: #f1f5f9; }
.tseg-text { font-size: 10.5px; color: #475569; line-height: 1.65; }
.transcript-seg.active .tseg-text { color: #94a3b8; }
.tseg-divider { height: 1px; background: #1e293b; margin: 0 14px; }
.board.transcript-open { padding-right: 340px; }
```

### HTML additions (add just before `</body>`)

```html
<!-- AUDIO TOUR BAR -->
<div class="audio-bar" id="audioBar">
  <div class="audio-row-top">
    <button class="audio-btn" id="playPauseBtn" title="Play / Pause" onclick="togglePlayPause()">▶</button>
    <button class="audio-btn stop-btn" id="stopBtn" title="Stop" onclick="stopTour()" style="font-size:12px;">■</button>
    <button class="audio-btn" id="chaptersBtn" title="Jump to segment" onclick="toggleChapters()" style="font-size:13px;">☰</button>
    <button class="audio-btn" id="transcriptBtn" title="Show transcript" onclick="toggleTranscript()" style="font-size:11px;font-weight:700;">T</button>
    <div class="audio-info">
      <div class="audio-section-label">Now playing</div>
      <div class="audio-section-text idle" id="audioSectionText">Press ▶ for the audio walkthrough</div>
    </div>
    <div class="audio-counter" id="audioProgressLabel">0 / N</div>
    <div class="audio-select-group">
      <div class="audio-select-label">Speed</div>
      <select class="audio-select" id="speedSelect">
        <option value="0.85">0.85×</option>
        <option value="0.95" selected>0.95×</option>
        <option value="1.05">1.05×</option>
        <option value="1.15">1.15×</option>
      </select>
    </div>
    <div class="audio-select-group">
      <div class="audio-select-label">Voice</div>
      <select class="audio-select" id="voiceSelect" style="max-width:160px;" onchange="primeVoice()"><option>Loading…</option></select>
    </div>
  </div>
  <div class="audio-row-track">
    <div class="audio-track-outer" id="audioTrackOuter" onclick="scrubTrack(event)">
      <div class="audio-track-bg" id="audioTrackBg">
        <div class="audio-track-fill" id="audioProgressFill"></div>
      </div>
      <div class="audio-thumb" id="audioThumb"></div>
    </div>
  </div>
</div>

<!-- TRANSCRIPT PANEL -->
<div class="transcript-panel" id="transcriptPanel">
  <div class="transcript-header">
    <span class="transcript-header-title">📄 &nbsp;Transcript</span>
    <button class="transcript-close" onclick="closeTranscript()">✕</button>
  </div>
  <div class="transcript-body" id="transcriptBody"></div>
</div>

<!-- CHAPTERS PANEL -->
<div class="chapters-panel" id="chaptersPanel">
  <div class="chapters-header">
    <span>☰ &nbsp;Jump to segment</span>
    <button class="chapters-close" onclick="closeChapters()">✕</button>
  </div>
  <div id="chaptersList"></div>
</div>

<!-- IMAGE LIGHTBOX (native <dialog> — focus trap + Escape + ::backdrop built-in) -->
<dialog class="viz-lightbox" id="vizLightbox" aria-label="Image viewer" onclick="handleLightboxClick(event)">
  <button class="viz-lightbox-close" onclick="closeLightbox()" aria-label="Close image viewer" autofocus>✕</button>
  <img id="vizLightboxImg" src="" alt="">
</dialog>
```

### JS additions (full audio engine — paste into `<script>`)

```javascript
// === AUDIO ENGINE ===
let voices = [], tourIndex = 0, isPlaying = false, isPaused = false, currentUtterance = null;

function loadVoices() {
  voices = speechSynthesis.getVoices();
  const sel = document.getElementById('voiceSelect');
  if (!voices.length) return;
  sel.innerHTML = '';
  // Score voices: Microsoft Online/Natural voices win; any Microsoft voice beats Google/generic.
  const scored = voices.filter(v => v.lang.startsWith('en')).map(v => {
    let s=0, n=v.name.toLowerCase();
    if(n.includes('microsoft')&&n.includes('andrew')&&n.includes('natural'))s+=200;
    if(n.includes('microsoft')&&n.includes('andrew')&&n.includes('online'))s+=198;
    if(n.includes('microsoft')&&n.includes('andrew'))s+=180;
    if(n.includes('microsoft')&&n.includes('mark')&&n.includes('natural'))s+=160;
    if(n.includes('microsoft')&&n.includes('guy')&&n.includes('natural'))s+=155;
    if(n.includes('microsoft')&&n.includes('mark')&&n.includes('online'))s+=150;
    if(n.includes('microsoft')&&n.includes('david')&&n.includes('desktop'))s+=140;
    if(n.includes('microsoft')&&n.includes('natural'))s+=120;  // any MS Natural voice
    if(n.includes('microsoft')&&n.includes('online'))s+=110;   // any MS Online voice
    if(n.includes('microsoft'))s+=80;                          // any MS voice beats Google/generic
    if(n.includes('google')&&n.includes('us')&&n.includes('male'))s+=30;
    if(v.lang==='en-US')s+=10; return {v,s};
  }).sort((a,b)=>b.s-a.s);
  scored.forEach(({v},i) => {
    const o=document.createElement('option'); o.value=v.name;
    o.textContent=v.name.replace('Microsoft ','').replace(' Online (Natural)',' ✦').replace(' Desktop','');
    if(i===0)o.selected=true; sel.appendChild(o);
  });
  // Pre-warm the top-scored voice so the first play click is instant with no processing lag.
  setTimeout(primeVoice, 400);
}
if(typeof speechSynthesis!=='undefined'){speechSynthesis.onvoiceschanged=loadVoices;loadVoices();}

function primeVoice() {
  // Speak a silent zero-width space to establish the Microsoft Online TTS connection before the user clicks play.
  // Without this, the first utterance has a noticeable delay while the backend initializes.
  const voice = getSelectedVoice();
  if (!voice) return;
  const utt = new SpeechSynthesisUtterance('\u200B');
  utt.voice = voice; utt.volume = 0; utt.rate = 1.0; utt.lang = 'en-US';
  speechSynthesis.speak(utt);
}

function getSelectedVoice() {
  const n = document.getElementById('voiceSelect').value;
  // Prefer the user's selection, then fall back to any Microsoft English voice, then any English voice.
  return voices.find(v => v.name === n)
    || voices.find(v => v.name.includes('Microsoft') && v.lang.startsWith('en'))
    || voices.find(v => v.lang.startsWith('en'))
    || null;
}
function getSelectedRate(){return parseFloat(document.getElementById('speedSelect').value);}

function setNarratingCards(ids){
  document.querySelectorAll('.card.narrating,.rail-card.narrating').forEach(el=>el.classList.remove('narrating'));
  let first=null;
  ids.forEach(id=>{
    const el=document.querySelector(`[onclick*="'${id}'"]`)||document.querySelector(`[onclick*="${id}"]`);
    if(el){el.classList.add('narrating');if(!first)first=el;}
  });
  if(first)first.scrollIntoView({behavior:'smooth',block:'center'});
}

function updateUI(i){
  const seg=TOUR_SEGMENTS[i],total=TOUR_SEGMENTS.length,pct=((i+1)/total)*100;
  document.getElementById('audioProgressFill').style.width=pct+'%';
  document.getElementById('audioThumb').style.left=pct+'%';
  document.getElementById('audioProgressLabel').textContent=`${i+1} / ${total}`;
  document.querySelectorAll('.audio-tick').forEach((t,j)=>t.classList.toggle('passed',j<i));
  const txt=document.getElementById('audioSectionText');txt.textContent=seg.label;txt.classList.remove('idle');
  document.getElementById('playPauseBtn').textContent='⏸';document.getElementById('playPauseBtn').classList.add('active');
  syncChapterHighlight(i);syncTranscriptHighlight(i);
}

// Chrome silently stops SpeechSynthesis on utterances longer than ~15 seconds (Chromium bug #679437).
// Fix: split each segment at sentence boundaries into ~140-char chunks and speak them sequentially.
function chunkText(text) {
  const sentences = text.match(/[^.!?]+[.!?]+\s*/g) || [text];
  const chunks = []; let buf = '';
  for (const s of sentences) {
    if (buf && (buf + s).length > 140) { chunks.push(buf.trim()); buf = s; }
    else buf += s;
  }
  if (buf.trim()) chunks.push(buf.trim());
  return chunks.length ? chunks : [text];
}

function speakSegment(index) {
  if (index >= TOUR_SEGMENTS.length) { finishTour(); return; }
  tourIndex = index; const seg = TOUR_SEGMENTS[index];
  updateUI(index); setNarratingCards(seg.highlights || []);
  if (seg.highlights && seg.highlights.length > 0) showDetail(seg.highlights[0]); else closeDetail();
  speakChunks(chunkText(seg.text), index, 0);
}

function speakChunks(chunks, segIndex, ci) {
  if (!isPlaying) return;
  if (ci >= chunks.length) { speakSegment(segIndex + 1); return; }
  const utt = new SpeechSynthesisUtterance(chunks[ci]);
  utt.voice = getSelectedVoice(); utt.rate = getSelectedRate(); utt.pitch = 1.0; utt.volume = 1.0;
  utt.lang = 'en-US';  // explicit lang prevents browser locale defaulting; reduces acronym mispronunciation
  utt.onend = () => { if (isPlaying) speakChunks(chunks, segIndex, ci + 1); };
  utt.onerror = (e) => { if (e.error !== 'interrupted' && e.error !== 'canceled') speakChunks(chunks, segIndex, ci + 1); };
  currentUtterance = utt; speechSynthesis.speak(utt);
}

function finishTour(){
  isPlaying=false;isPaused=false;currentUtterance=null;setNarratingCards([]);
  document.getElementById('audioProgressFill').style.width='100%';
  document.getElementById('audioThumb').style.left='100%';
  document.getElementById('audioProgressLabel').textContent=`${TOUR_SEGMENTS.length} / ${TOUR_SEGMENTS.length}`;
  document.querySelectorAll('.audio-tick').forEach(t=>t.classList.add('passed'));
  document.getElementById('audioSectionText').textContent='Tour complete — click any card to explore';
  document.getElementById('audioSectionText').classList.remove('idle');
  document.getElementById('playPauseBtn').textContent='↺';document.getElementById('playPauseBtn').classList.remove('active');
}

function togglePlayPause(){
  if(!isPlaying&&!isPaused){isPlaying=true;isPaused=false;speechSynthesis.cancel();speakSegment(0);return;}
  if(isPlaying&&!isPaused){speechSynthesis.pause();isPaused=true;isPlaying=false;document.getElementById('playPauseBtn').textContent='▶';document.getElementById('playPauseBtn').classList.remove('active');return;}
  if(isPaused){speechSynthesis.resume();isPaused=false;isPlaying=true;document.getElementById('playPauseBtn').textContent='⏸';document.getElementById('playPauseBtn').classList.add('active');return;}
  isPlaying=true;isPaused=false;speechSynthesis.cancel();speakSegment(0);
}

function stopTour(){
  isPlaying=false;isPaused=false;speechSynthesis.cancel();currentUtterance=null;setNarratingCards([]);
  document.getElementById('playPauseBtn').textContent='▶';document.getElementById('playPauseBtn').classList.remove('active');
  document.getElementById('audioProgressFill').style.width='0%';document.getElementById('audioThumb').style.left='0%';
  document.getElementById('audioProgressLabel').textContent=`0 / ${TOUR_SEGMENTS.length}`;
  document.querySelectorAll('.audio-tick').forEach(t=>t.classList.remove('passed'));
  document.getElementById('audioSectionText').textContent='Press ▶ for the audio walkthrough';
  document.getElementById('audioSectionText').classList.add('idle');
}

function buildTicks(){
  const bg=document.getElementById('audioTrackBg'),total=TOUR_SEGMENTS.length;
  TOUR_SEGMENTS.forEach((seg,i)=>{if(i===0)return;const t=document.createElement('div');t.className='audio-tick';t.style.left=(i/total*100)+'%';t.title=seg.label;bg.appendChild(t);});
}

function scrubTrack(event){
  const outer=document.getElementById('audioTrackOuter'),rect=outer.getBoundingClientRect();
  const pct=Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width));
  const idx=Math.min(Math.floor(pct*TOUR_SEGMENTS.length),TOUR_SEGMENTS.length-1);
  speechSynthesis.cancel();isPlaying=true;isPaused=false;speakSegment(idx);
}

// Drag scrubbing
(function(){
  let dragging=false;
  function doScrub(cx){
    const o=document.getElementById('audioTrackOuter');if(!o)return 0;
    const r=o.getBoundingClientRect(),pct=Math.max(0,Math.min(1,(cx-r.left)/r.width));
    const idx=Math.min(Math.floor(pct*TOUR_SEGMENTS.length),TOUR_SEGMENTS.length-1);
    document.getElementById('audioProgressFill').style.width=(pct*100)+'%';
    document.getElementById('audioThumb').style.left=(pct*100)+'%';
    return idx;
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const o=document.getElementById('audioTrackOuter');if(!o)return;
    o.addEventListener('mousedown',e=>{dragging=true;doScrub(e.clientX);e.preventDefault();});
    document.addEventListener('mousemove',e=>{if(dragging)doScrub(e.clientX);});
    document.addEventListener('mouseup',e=>{if(!dragging)return;dragging=false;const idx=doScrub(e.clientX);speechSynthesis.cancel();isPlaying=true;isPaused=false;speakSegment(idx);});
  });
})();

// Chapters panel
function buildChaptersList(){
  const list=document.getElementById('chaptersList');list.innerHTML='';
  TOUR_SEGMENTS.forEach((seg,i)=>{
    const row=document.createElement('div');row.id=`chapter-${i}`;
    row.className='chapter-row'+(i===tourIndex&&isPlaying?' active':'');
    const cc=seg.highlights.length;
    row.innerHTML=`<span class="chapter-num">${i+1}</span><span class="chapter-label">${seg.label}</span><span class="chapter-cards">${cc?cc+' card'+(cc>1?'s':''):''}</span>`;
    row.onclick=()=>{speechSynthesis.cancel();isPlaying=true;isPaused=false;closeChapters();speakSegment(i);};
    list.appendChild(row);
  });
}
function toggleChapters(){const p=document.getElementById('chaptersPanel');if(p.style.display==='block'){closeChapters();}else{buildChaptersList();p.style.display='block';document.getElementById('chaptersBtn').classList.add('active');}}
function closeChapters(){document.getElementById('chaptersPanel').style.display='none';document.getElementById('chaptersBtn').classList.remove('active');}
function syncChapterHighlight(i){document.querySelectorAll('.chapter-row').forEach((r,j)=>r.classList.toggle('active',j===i));}

// Transcript panel
function buildTranscript(){
  const body=document.getElementById('transcriptBody');body.innerHTML='';
  TOUR_SEGMENTS.forEach((seg,i)=>{
    if(i>0){const d=document.createElement('div');d.className='tseg-divider';body.appendChild(d);}
    const div=document.createElement('div');
    div.className='transcript-seg'+(i===tourIndex&&isPlaying?' active':'');div.id=`tseg-${i}`;
    div.innerHTML=`<div class="tseg-num">${i+1} / ${TOUR_SEGMENTS.length}</div><div class="tseg-label">${seg.label}</div><div class="tseg-text">${seg.text}</div>`;
    div.onclick=()=>{speechSynthesis.cancel();isPlaying=true;isPaused=false;speakSegment(i);};
    body.appendChild(div);
  });
}
function toggleTranscript(){
  const p=document.getElementById('transcriptPanel');
  if(p.classList.contains('open')){closeTranscript();}
  else{buildTranscript();p.classList.add('open');document.getElementById('transcriptBtn').classList.add('active');document.getElementById('board').classList.add('transcript-open');syncTranscriptHighlight(tourIndex);}
}
function closeTranscript(){document.getElementById('transcriptPanel').classList.remove('open');document.getElementById('transcriptBtn').classList.remove('active');document.getElementById('board').classList.remove('transcript-open');}
function syncTranscriptHighlight(i){
  const p=document.getElementById('transcriptPanel');if(!p.classList.contains('open'))return;
  document.querySelectorAll('.transcript-seg').forEach((el,j)=>el.classList.toggle('active',j===i));
  const a=document.getElementById(`tseg-${i}`);if(a)a.scrollIntoView({behavior:'smooth',block:'nearest'});
}

buildTicks();

// === IMAGE LIGHTBOX (native <dialog>) ===
// showModal() handles focus trap, Escape key, and backdrop automatically — no custom code needed for those.
function openLightbox(src, alt, triggerEl) {
  const lb = document.getElementById('vizLightbox');
  const img = document.getElementById('vizLightboxImg');
  img.src = src; img.alt = alt || '';
  lb._trigger = triggerEl || null;
  lb.showModal();
}
function closeLightbox() {
  const lb = document.getElementById('vizLightbox');
  if (lb.open) lb.close();
  if (lb._trigger) { lb._trigger.focus(); lb._trigger = null; }
}
function handleLightboxClick(e) {
  // Close when clicking the backdrop (the <dialog> element itself, not the img or close button inside it)
  if (e.target === e.currentTarget) closeLightbox();
}
// Restore focus when the browser closes the dialog natively via Escape
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('vizLightbox').addEventListener('cancel', () => {
    const lb = document.getElementById('vizLightbox');
    if (lb._trigger) { setTimeout(() => { if (lb._trigger) { lb._trigger.focus(); lb._trigger = null; } }, 0); }
  });
});
// Wire up all .viz-img elements — runs once on load and again after detail panel opens
function bindLightboxImages(root) {
  (root || document).querySelectorAll('img.viz-img').forEach(img => {
    if (img.dataset.lbBound) return;
    img.dataset.lbBound = '1';
    img.style.cursor = 'zoom-in';
    img.addEventListener('click', e => { e.stopPropagation(); openLightbox(img.src, img.alt, img); });
  });
}
document.addEventListener('DOMContentLoaded', () => bindLightboxImages());
// Re-bind after detail panel updates (called from showDetail)
const _origShowDetail = showDetail;
showDetail = function(id) { _origShowDetail(id); setTimeout(() => bindLightboxImages(document.getElementById('detail')), 0); };
```

### TOUR_SEGMENTS writing guide

- **Segment count is dynamic** — write one segment per meaningful layer or section, plus an intro and a summary. Let the diagram drive the count; don't cap at a fixed number.
- For concept-mode diagrams: match segments to layers. Four diagram layers → four content segments plus intro and summary (six total). Don't pad thin layers; don't merge distinct stages just to hit a target number.
- Merge only when two layers are so closely related that splitting them adds no new insight for the listener.
- Write 1 segment per major layer/section, plus 1 intro and 1 summary
- **When a ticket is present**: add 2 dedicated segments right after the intro — one for the problem statement ("what was broken/missing before this ticket"), one for the solution.
- Keep each segment 2–4 sentences. Chrome cuts off utterances after ~15 seconds; the audio engine chunks text automatically, but shorter writing still sounds better aloud.
- `highlights` should list the card IDs that get the blue pulse outline during narration
- Spell out abbreviations phonetically (e.g., "T F F dash 1040" not "TFF-1040"); `utt.lang = 'en-US'` is already in the engine to reduce mispronunciation of tech acronyms
- For ticket-related cards in highlights: open their detail panel so the user sees the before/after diagram while listening

**Lead with WHY, not WHAT (most important writing rule):**

Every segment must answer "why does this stage exist?" before explaining how it works. Users connect with purpose before mechanism.

Structure each segment text as:
1. **One sentence stating the problem this stage solves** — what goes wrong without it, or what need it fills. (The "why it exists")
2. **One or two sentences on how it works** — the mechanism. Keep it plain. Use an analogy if the audience tier is Novice.
3. **Optional: one sentence on what comes next** — bridges to the next segment.

Good example (RAG embedding stage):
> "The system needs to find documents that are *about* the same thing as your question — not just documents that share the same words. This stage turns both your question and every stored document into a list of numbers that captures meaning. Documents with similar meanings end up with similar numbers, so the next step can find them by distance."

Bad example (same stage):
> "The embedding layer uses a transformer model to convert text into dense vector representations stored in the vector database index."

The bad version describes what it is. The good version explains why you'd want it.

---

## Step 4: Save and Open

Pick an output directory:
- If `workspace/[task-id]/` exists → save to `workspace/[task-id]/visualize/[SLUG].html`
- Otherwise create `workspace/visualize-YYYY-MM-DD/` and save there as `[SLUG].html`

Open in browser (Windows):
```bash
powershell.exe -NoProfile -Command "Start-Process 'C:\path\to\[SLUG].html'"
```

Use the literal Windows path with backslashes. Do not use `cygpath` or `cmd.exe /c start`.

---

## Step 5: Report

Tell the user:
- What was visualized (TOPIC) and which mode was used (self-map / project-map / concept)
- How many components and layers are in the diagram
- Where the file was saved (`[SLUG].html`)

---

## What's Next After /visualize

| If the diagram revealed... | Run |
|---------------------------|-----|
| Something complex enough to plan out | `/workspace` — creates a structured implementation plan for the work |
| A dependency you want to trace deeply | `/graph [workspace-id]` — maps callers, importers, and structural neighbours |
| A security-relevant flow (auth, data, tokens) | `/security-review` — OWASP-aware review of pending changes |
| A performance bottleneck | Spawn `performance-agent` to profile and recommend fixes |
| Something you want to build | Describe it to Claude — if it's a big feature, use `/workspace` first |
