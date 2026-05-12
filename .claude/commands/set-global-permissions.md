---
argument-hint: <list|allow|ask|deny|remove|move> [pattern]
description: Manage global Claude Code permissions in ~/.claude/settings.json — applies to all projects
allowed-tools: Read, Edit, Write, Bash, Glob
---

# /set-global-permissions — Global Permission Manager

Arguments: **$ARGUMENTS**

Global permissions live in `~/.claude/settings.json` and apply to **every project**.
Use `/set-permissions` instead for project-scoped rules.

---

## Phase 0: Parse Arguments

Split `$ARGUMENTS` on whitespace.

`TARGET_FILE = ~/.claude/settings.json` (always — no `--local` flag here).

| Position | Meaning |
|----------|---------|
| `$1` | Action: `list`, `allow`, `ask`, `deny`, `remove`, `move` |
| `$2` | Pattern (for add/remove) OR source-list (for `move`) |
| `$3` | Target-list (for `move` only) |
| `$4` | Pattern (for `move` only) |

If no arguments given → default to `list`.

---

## Phase 1: Read Global Settings File

Read `~/.claude/settings.json`.

If the file does not exist → print "~/.claude/settings.json not found. This is unusual — Claude Code should have created it. Check your Claude Code installation." and stop.

Parse the `permissions` object. If missing `allow`, `ask`, or `deny` arrays, treat them as empty.

---

## Phase 2: Execute Action

### `list`

Print a formatted table of all three lists:

```
Global permissions — ~/.claude/settings.json
(affects ALL projects — use /set-permissions for project-scoped rules)

ALLOW (N)
  [1] Read
  [2] Write
  [3] Bash(npm *)
  ...

ASK (N)
  [1] Bash(curl:*)
  [2] Bash(git push:*)
  ...

DENY (N)
  [1] Bash(rm -rf /)
  ...
```

If a list is empty, print `  (empty)`.

Also print at the bottom:
```
Tip: project rules in .claude/settings.json merge with these.
     Project-level allow/ask/deny adds to global, not replaces it.
```

---

### `allow <pattern>` / `ask <pattern>` / `deny <pattern>`

1. **Safety check for global scope**: if the pattern is very broad (e.g., `Bash(*)`, `Bash(rm *)`, `Bash(curl *)` without a host restriction), print a warning:
   ```
   ⚠️  Broad pattern in global allow: [pattern]
   This will apply to ALL projects. Is this intentional?
   For localhost-only tools, prefer: Bash(curl * localhost:*) or Bash(curl * http://localhost:*)
   Type 'confirmed' to proceed, or refine the pattern.
   ```
   **PAUSE and wait for user response before writing.**

2. **Dedup check**: scan all three lists for the exact pattern.
   - If already in the requested list → print "Already in [list]: [pattern]" and stop.
   - If in a DIFFERENT list → print warning: "Pattern is currently in [other-list]. Use `/set-global-permissions move [other-list] [target-list] <pattern>` to move it." Stop.

3. **Add the pattern** to the correct array in `TARGET_FILE`.

4. Print: "Added to global [list]: [pattern]  →  ~/.claude/settings.json"

**Broad pattern detection rules** (trigger warning if ANY match):
- `Bash(*)` — matches everything
- `Bash(rm *)` or `Bash(rm:*)` — deletion without path restriction
- `Bash(curl *)` or `Bash(curl:*)` — curl without host restriction
- `Bash(wget *)` or `Bash(wget:*)` — wget without host restriction
- `Bash(sudo *)` or `Bash(sudo:*)` — unrestricted sudo
- Any pattern that is just a tool name with no qualifier: `Bash(python)`, `Bash(node)`

---

### `remove <pattern>`

1. Search all three lists for the exact pattern.
2. If not found → print "Pattern not found in any global list: [pattern]" and stop.
3. Remove it from whichever list(s) contain it.
4. Print: "Removed from global [list]: [pattern]  →  ~/.claude/settings.json"

---

### `move <from-list> <to-list> <pattern>`

Valid list names: `allow`, `ask`, `deny`.

1. Verify `from-list` and `to-list` are valid names. If not → print valid options and stop.
2. Check the pattern exists in `from-list`. If not → print "Pattern not found in global [from-list]: [pattern]" and stop.
3. **If moving TO `allow` from `ask`/`deny`**: run the broad-pattern safety check above.
4. Remove from `from-list`, add to `to-list`.
5. Print: "Moved [pattern]: [from-list] → [to-list]  →  ~/.claude/settings.json"

---

## Phase 3: Validate

After any write, read `TARGET_FILE` back and verify:
- Valid JSON (if not, print the JSON error and restore pre-edit content)
- The expected pattern appears in the expected list

Print a one-line confirmation of the final state.

---

## Glob Syntax Reference (shown when user adds a Bash pattern)

```
Glob syntax: * matches any string within a token.
  Bash(curl * http://localhost:*)  matches: curl -s http://localhost:3000/api
  Bash(git -C * status*)           matches: git -C /path status --short
  Bash(npm run *)                  matches: npm run build, npm run test
  Bash(command:*)                  matches any command starting with "command"
```

---

## Scope Reminder

| Skill | File | Scope |
|-------|------|-------|
| `/set-global-permissions` | `~/.claude/settings.json` | All projects |
| `/set-permissions` | `.claude/settings.json` | This project (committed) |
| `/set-permissions --local` | `.claude/settings.local.json` | This project (personal, gitignored) |

---

## Examples

```
/set-global-permissions list
/set-global-permissions allow "Bash(curl * http://localhost:*)"
/set-global-permissions ask "Bash(wget:*)"
/set-global-permissions deny "Bash(curl *)"
/set-global-permissions remove "Bash(curl:*)"
/set-global-permissions move ask allow "Bash(npm run *)"
```
