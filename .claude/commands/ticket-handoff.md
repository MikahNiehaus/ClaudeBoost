---
description: Generate a filled ticket handoff document using the team Confluence template and copy it to clipboard with rich formatting
argument-hint: [ticket-id] [handoff-to]
---

# Ticket Handoff — Generate Confluence Document

Generate a filled handoff document for the current ticket using the team template, then copy it to clipboard as rich HTML so it pastes correctly into Confluence.

Arguments: $ARGUMENTS

---

## Template Structure

The team Confluence handoff template (from https://upstreamimpact.atlassian.net/wiki/spaces/UI/pages/1268318209) has these sections:

```
Ticket Handoff: [Ticket ID]: [Ticket Title]
Handoff from: [your name]
Handoff to: [recipient name or "team"]
Date: [YYYY-MM-DD]
Reason: [Vacation: dates / QA bounce-back / Passing to colleague]
Branch: [branch name]
Ticket link: [Jira URL]

Status at a Glance
  Ticket status: [In Progress / Completed needs rework / Blocked / Ready for review]
  [One paragraph: where things stand right now, what works, and what doesn't.]

Acceptance Criteria
  [List from Jira ticket]

Work Completed
  [bullet list of completed items]
  Key files changed:
    [file path]: [what changed]

Work Remaining
  [ ] [specific next task]

How to Run and Test
  [env vars, seed data, feature flags needed]

Blockers and Risks
  [blocker or risk, and suggested workaround]

Decisions Made
  [key decisions and rationale]

[BOUNCE-BACK] What Failed   (only include if this is a QA bounce-back)
  Failure summary, steps to reproduce, expected vs actual, evidence, severity, what was tried
```

---

## Steps

### 1. Parse ticket ID and arguments

- Infer the ticket ID from the branch name (`git branch --show-current`) unless `$ARGUMENTS` contains a Jira-style ID (e.g. TFF-1038)
- If `$ARGUMENTS` contains a name after the ticket ID, use it as "Handoff to"; default is "team"
- If `$ARGUMENTS` contains pasted Jira ticket content (descriptions, acceptance criteria, comments), extract and use it — but the branch name is the authoritative source for which ticket this handoff covers

### 2. Gather git context

Run all of these in parallel:

```bash
git -C "$PROJECT_PATH" branch --show-current
```
```bash
git -C "$PROJECT_PATH" log --oneline -15
```
```bash
git -C "$PROJECT_PATH" diff --stat HEAD
```
```bash
git -C "$PROJECT_PATH" log --oneline --not origin/master | head -20
```

Then run these sequentially to understand branch-specific work:

```bash
# Find commits specific to this ticket on the branch
git -C "$PROJECT_PATH" log --format="%h %s" --not origin/master | grep -i "<TICKET-ID>"
```
```bash
# Show what files the key commits touched (run for the 2-3 most significant commits)
git -C "$PROJECT_PATH" show --stat <commit-sha>
```

Also read `$CLAUDEBOOST_HOME/state/handoff-latest.json` if it exists for workspace memo context.

### 3. Read the changed files

After identifying which files are specific to this ticket (not just accumulated branch noise), read the key ones:
- The main page/view/controller changed
- Any service or utility class added or significantly changed
- Do NOT list files from unrelated tickets that happened to land on the same branch

### 4. Extract ticket context from arguments

If `$ARGUMENTS` contains pasted Jira content:
- Pull the acceptance criteria scenarios verbatim and use them in the AC section
- Pull any comments that describe current state, blockers, or outstanding items (these belong in Status at a Glance, Work Remaining, or Blockers)
- Note the QA Rejection Count if visible — if > 0, mention it in Status at a Glance
- Note any Jira comments about accounts, env vars, flags, or known issues that need follow-up

### 5. Fill the template

Use everything gathered to fill out the template. Rules:
- Date is always today (use current date from context)
- "Handoff from" is always Mikah Niehaus
- "Branch" comes from `git branch --show-current`
- "Key files changed" lists only files specific to THIS ticket's work — never include .gitignore
- Status at a Glance: one honest paragraph — what works, what doesn't, what's still pending
- Work Remaining: use checkbox format `[ ] task` — include uncommitted changes, pending PRs, open blockers from comments
- Skip the [BOUNCE-BACK] section unless the reason is a QA bounce-back
- Do NOT include section headers that have no content
- Keep it concise — each bullet is one sentence max

**Voice and style rules (apply to every word in the document):**

Read `$CLAUDEBOOST_HOME/knowledge/human-voice.xml` and apply all rules. The short version:

- **Zero dashes of any kind.** No em dash (—), no en dash (–), no spaced hyphen ( - ), and no hyphenated compound words. "auto-dismiss" becomes "auto dismiss". "double-banner" becomes "double banner". "step-by-step" becomes "step by step". "client-side" becomes "client side". The only exception is when a dash is part of an actual identifier being named (a filename, branch name, or flag).
- No AI vocabulary: never use seamless, robust, leverage, utilize, facilitate, comprehensive, nuanced, pivotal, delve, empower, holistic, or any word from the banned list in the XML.
- Write like a person wrote it. Contractions are fine. Sentence fragments are fine. Opinions are fine.
- Vary sentence length. Three sentences the same shape in a row reads like a machine.
- Be specific and concrete. "The JWT secret was base64 decoded instead of read as UTF8" beats "there was an encoding issue".
- No filler openers. Start with the substance.

### 4. Audit the draft for accuracy

Before writing the final files, spawn an agent to verify every factual claim in the draft against the actual git history and code. The agent should:

- Confirm branch name(s), PR number(s), and merge commit stats match what the draft claims
- Confirm all file paths in "Key files changed" exist in the repo at the exact paths listed (do NOT trust shortened or inferred paths — grep or read to verify)
- Confirm feature flag names match what is in `FeatureFlagsEnum.cs`
- Confirm any filter logic, field names, or behavioral descriptions match the actual code
- For each claim: report PASS or FAIL with one line of evidence

The agent spawn prompt MUST include:
```
POST http://127.0.0.1:8613/search
{"query": "<the claim you are checking>", "sources": ["project:<PROJECT_PATH>"], "mode": "both", "limit": 8}
```

Fix any FAIL items in the draft before continuing to step 5.

### 5. Copy to clipboard as HTML + plain text

First, resolve the temp directory path by running:

```bash
powershell.exe -Command "[System.IO.Path]::GetTempPath()"
```

Use that resolved path (e.g. `C:/Users/username/AppData/Local/Temp`) for all file writes below. Never hardcode a user-specific path in this skill.

Write the filled HTML document to `<TEMP>/ticket-handoff.html` using the Write tool.

Also write a plain text version of the same content to `<TEMP>/ticket-handoff.txt` using the Write tool. The plain text version uses the same sections but with plain separators (no HTML tags), dashes replaced by colons or commas, and checkboxes as `[ ]`.

Then write a clipboard helper script to `<TEMP>/copy-handoff.ps1` using the Write tool with this content:

```powershell
$htmlContent = Get-Content -Raw '<TEMP>/ticket-handoff.html'
$plainContent = Get-Content -Raw '<TEMP>/ticket-handoff.txt'

# CF_HTML requires a header with byte offsets so apps like Confluence accept it as rich HTML
$header = "Version:0.9`r`nStartHTML:AAAAAAAA`r`nEndHTML:BBBBBBBB`r`nStartFragment:CCCCCCCC`r`nEndFragment:DDDDDDDD`r`n"
$startTag = "<html><body><!--StartFragment-->"
$endTag   = "<!--EndFragment--></body></html>"

$startHtml = $header.Length
$startFrag = $startHtml + $startTag.Length
$endFrag   = $startFrag + $htmlContent.Length
$endHtml   = $endFrag   + $endTag.Length

$cfHtml = ($header + $startTag + $htmlContent + $endTag) `
    -replace 'AAAAAAAA', $startHtml.ToString('D8') `
    -replace 'BBBBBBBB', $endHtml.ToString('D8') `
    -replace 'CCCCCCCC', $startFrag.ToString('D8') `
    -replace 'DDDDDDDD', $endFrag.ToString('D8')

Add-Type -AssemblyName System.Windows.Forms
$dataObj = [System.Windows.Forms.DataObject]::new()
$dataObj.SetData([System.Windows.Forms.DataFormats]::Html, $cfHtml)
$dataObj.SetData([System.Windows.Forms.DataFormats]::Text, $plainContent)
[System.Windows.Forms.Clipboard]::SetDataObject($dataObj, $true)
Write-Output "Copied to clipboard (HTML + plain text, $($cfHtml.Length) bytes CF_HTML format)."
```

Then run:

```bash
powershell.exe -ExecutionPolicy Bypass -File "<TEMP>/copy-handoff.ps1"
```

Note: Always use the Write tool for both files and the `-File` flag for execution. Inline `-Command` with PowerShell variables triggers bash-guard and the clipboard step will fail. The CF_HTML byte-offset header is required; plain HTML on the clipboard pastes as text in Confluence. The DataObject approach puts both formats on the clipboard simultaneously: Confluence picks up CF_HTML, Slack/email/text editors pick up plain text.

**HTML format rules:**
- `<h2>` for section headings (Status at a Glance, Work Completed, etc.)
- `<p>` for the header metadata block (Ticket Handoff, Handoff from, etc.)
- `<ul><li>` for bullet lists
- `<ul><li><input type="checkbox">` for work remaining checkboxes
- `<strong>` for labels (Handoff from:, Branch:, etc.)
- `<a href="...">` for URLs

### 6. Report to user

Tell the user:
- The handoff doc is ready and copied to clipboard
- Paste it directly into the Confluence page at https://upstreamimpact.atlassian.net/wiki/spaces/UI/pages/1268318209
- Note any sections they should manually fill in (e.g. Acceptance Criteria if not obvious from context)


---

## Phase 0: Workspace Detection

**Workspace detection (run before any other action):**

Run `get-active-workspace.py` to get the active workspace for this Claude
instance — matches the blue "WS XXXX" status bar (per-instance, not the
stale shared global file):
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"
```

Store `project_path` as `PROJECT_PATH` and `workspace_path` as `WORKSPACE_PATH`.
If `PROJECT_PATH` is empty: fall back to current working directory (`pwd`).

**Collision check:** if your context or memory references a different workspace
than what the script returned, print:
`[ticket-handoff] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.

