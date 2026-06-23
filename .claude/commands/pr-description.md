---
argument-hint: [branch-name — defaults to current branch vs latest sprint release or master]
description: Generate a filled PR description and title for the current branch, following project conventions
allowed-tools: Read, Bash, Glob, Grep
---

# /pr-description — PR Description Generator

Generate a filled PR template and title for **$ARGUMENTS** (defaults to current branch vs master if blank).

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
`[pr-description] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.


---

## Phase 1: Resolve scope

**1a — Determine branches.**

First, read `<repo-root>/.claude/pr-config.md` and extract `sprint_branch_prefix` if present (default: `sprint-release-`).

Find the latest sprint release branch by listing all local branches that start with the prefix, sorting the numeric suffix, and taking the highest:

```bash
git rev-parse --show-toplevel
git branch --list "sprint-release-*" | sed 's/[* ]*//' | sort -t- -k3 -n | tail -1
```

Use the result as **SPRINT_BASE** if one is found.

Parse `$ARGUMENTS`:
- Empty or blank → FEATURE_BRANCH = current branch, BASE_BRANCH = SPRINT_BASE (or `master` if none found)
- Single branch name → FEATURE_BRANCH = that branch, BASE_BRANCH = SPRINT_BASE (or `master` if none found)
- `branch from base` or `branch vs base` → use both exactly as given

```bash
git rev-parse --abbrev-ref HEAD
```

Announce the resolved BASE_BRANCH so the user can see what it diffed against.

**1b — Get the diff stat and commits.**

```bash
git diff <BASE_BRANCH>...HEAD --stat
git log <BASE_BRANCH>..HEAD --oneline
```

If stat is empty: "No changes between <BASE_BRANCH> and this branch." Stop.

---

## Phase 2: Find ticket context

**2a — Extract ticket ID from branch name.**

Branch naming pattern: `[type]/TICKET-ID-description` (e.g. `fix/ASC-1201-filter-bugs`).

Extract the ticket ID (pattern: 2-6 uppercase letters, hyphen, digits — e.g. `ASC-1201`, `PROJ-42`).

**2b — Check for workspace ticket file.**

If a ticket ID was found, check for a workspace file:
```bash
ls workspace/*/ticket.md 2>/dev/null | head -5
```

Read the matching workspace ticket.md if it exists. This provides acceptance criteria and ticket context.

**2c — Look up Jira base URL from project config.**

Find the repo root:
```bash
git rev-parse --show-toplevel
```

Check for `<repo-root>/.claude/pr-config.md` (gitignored alongside `settings.local.json` — holds project-specific config that shouldn't be committed). Read it if it exists and look for a line of the form:
```
jira_base_url: https://your-company.atlassian.net/browse
```

If `jira_base_url` is found and a ticket ID was extracted from the branch name, construct the full URL as `{jira_base_url}/{TICKET-ID}`. Do NOT ask the user.

If `.claude/pr-config.md` does not exist or has no `jira_base_url` line:
- If a ticket ID was found: ask:
  ```
  What is the Jira base URL for this project? (e.g. https://company.atlassian.net/browse)
  Or say "none" to leave the ticket link blank.
  ```
  Construct the full URL as `{answer}/{TICKET-ID}`.
- If no ticket ID found anywhere (no branch pattern match, no workspace file, no commit message reference): ask:
  ```
  What is the Jira ticket URL? (e.g. https://company.atlassian.net/browse/PROJ-1234)
  Or say "none" to leave it blank.
  ```

The config file can also declare a `sprint_branch_prefix` for base branch auto-detection (used in Phase 1a).

---

## Phase 3: Read the full diff

```bash
git diff <BASE_BRANCH>...HEAD
```

Read the PR template from `.github/pull_request_template.md` if it exists.

Analyze the diff and identify:
- What changed (files, logic, UI)
- Why it changed (from ticket context or commit messages)
- Type of change: bug fix / new feature / breaking change / refactor / docs / performance
- How it was tested (look for test files in the diff, or `workspace/*/screenshots/` directory)

Check for test files added in the diff:
```bash
git diff <BASE_BRANCH>...HEAD --name-only | grep -i test
```

Check for screenshots in workspace:
```bash
ls workspace/*/screenshots/ 2>/dev/null | head -10
ls workspace/*/bug\ fix/ 2>/dev/null | head -10
```

---

## Phase 4: Generate title and description

### Title rules
- Format: `type(scope): description`
- Types: `feat`, `fix`, `refactor`, `test`, `chore`, `docs`, `perf`
- Scope: the affected area (e.g. `groups`, `auth`, `notifications`)
- Under 72 characters, lowercase first letter, no period at the end
- Imperative mood: "add" not "added", "fix" not "fixed"

### Description rules (CRITICAL — violations break GitHub rendering)
- **Description**, **How Has This Been Tested**, and **Additional Notes** must be plain prose paragraphs
- Zero markdown inside these sections: no bold, no bullets, no headers, no dashes of any kind
- Each paragraph is ONE continuous line — no manual line breaks inside it
- Text starts flush at column zero — not a single leading space or indent
- Non-formal, concise, polite, professional
- No dashes whatsoever — not em-dash (—), not en-dash (–), not spaced hyphen ( - )
- Use commas and periods instead of dashes
- Say "tested locally" for testing — never mention Playwright or automation tools

### Type of Change checkboxes
Check the appropriate box(es) based on the diff.

### Checklist
Check items that clearly apply based on the diff:
- `My code follows the style guidelines` — always check
- `I have performed a self-review` — always check
- `I have commented my code` — check if comments were added/changed in the diff
- `My changes generate no new warnings` — check if no warning-generating patterns visible
- `I have added tests` — check if test files appear in the diff
- `New and existing unit tests pass locally` — check if tests were run (look for test files in diff)
- Leave `documentation` and `dependent changes` unchecked unless clearly relevant

### Screenshots
If workspace screenshots exist, reference them: `See workspace/[ticket]/screenshots/ for screenshots.`
Otherwise omit the section or write "N/A."

---

## Phase 5: Output

Output the title on a line by itself, then the filled template as a raw markdown code block (triple backticks).

Format:
```
**Title**: type(scope): description

```markdown
[full filled template here]
```
```

The title is outside the code block so it can be read at a glance. The template body is inside triple backticks so it pastes into GitHub without rendering.

**Self-check before outputting:**
1. Does any prose paragraph contain a dash? Replace with a comma or colon.
2. Does any prose paragraph have a line break inside it? Join into one line.
3. Does any prose paragraph start with a space or indent? Remove it.
4. Is the title under 72 chars and lowercase? Fix if not.
5. Does the Jira URL section have a real URL? If not, ask before outputting.
