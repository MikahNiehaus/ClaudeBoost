---
argument-hint: <list|allow|ask|deny|remove|move> [pattern] [--local]
description: Manage project-level Claude Code permissions in .claude/settings.json (or settings.local.json with --local)
allowed-tools: Read, Edit, Write, Bash, Glob
---

# /set-permissions — Project Permission Manager

Arguments: **$ARGUMENTS**

---

## Phase 0: Parse Arguments

Split `$ARGUMENTS` on whitespace. Rules:

- If `--local` is present anywhere in arguments: `TARGET_FILE = .claude/settings.local.json`
- Otherwise: `TARGET_FILE = .claude/settings.json`
- Strip `--local` from remaining tokens before further parsing.

**Remaining tokens after stripping `--local`:**

| Position | Meaning |
|----------|---------|
| `$1` | Action: `list`, `allow`, `ask`, `deny`, `remove`, `move` |
| `$2` | Pattern (for add/remove) OR source-list (for `move`) |
| `$3` | Target-list (for `move` only) |
| `$4` | Pattern (for `move` only) |

If no arguments given → default to `list`.

---

## Phase 1: Read Settings File

Read `TARGET_FILE`.

If the file does not exist:
- If `TARGET_FILE` is `settings.local.json`: create it with `{"permissions":{"allow":[],"ask":[],"deny":[]}}` and notify the user.
- If `TARGET_FILE` is `settings.json`: print "No project settings.json found at .claude/settings.json. Create one first or use --local for a personal override." and stop.

Parse the `permissions` object. If missing `allow`, `ask`, or `deny` arrays, treat them as empty.

---

## Phase 2: Execute Action

### `list`

Read `~/.claude/settings.json` (global settings). Then print:

```
Project permissions — .claude/settings.json
(use --local to target settings.local.json)

ALLOW (N)
  [1] Bash(npm *)
  [2] Read                    ← also in global allow (redundant)
  ...

ASK (N)
  [1] Bash(git push:*)
  [2] Bash(curl:*)            ← overrides global allow (Bash is in global allow)
  ...

DENY (N)
  [1] Bash(rm -rf /)
  ...
```

Annotations to add per entry:
- `← also in global allow (redundant)` — appears in both global allow and project allow
- `← overrides global allow` — in project ask, but global allow has `"Bash"` or a matching pattern (project ask restricts further, which may be intentional)
- `← also in global ask (this allow has no effect)` — in project allow, but global ask has a matching pattern (global ask wins; this entry does nothing)
- `← also in global deny (shadowed)` — in project allow/ask but global deny blocks it

If a list is empty, print `  (empty)`.

---

### `allow <pattern>` / `ask <pattern>` / `deny <pattern>`

1. **Dedup check**: scan all three lists for the exact pattern.
   - If already in the requested list → print "Already in [list]: [pattern]" and stop.
   - If in a DIFFERENT list → print warning: "Pattern is currently in [other-list]. Use `/set-permissions move [other-list] [target-list] <pattern>` to move it." Do NOT add a duplicate; stop.

2. **Global conflict check**: Read `~/.claude/settings.json`.

   **If adding to `allow`**:
   - If the global ask list contains the exact pattern OR a pattern that would match the same commands (e.g. global has `Bash(npm **)` and you're adding `Bash(npm:*)`), warn:
     ```
     Warning: ~/.claude/settings.json has a matching pattern in global ask.
     Global ask beats project allow — this entry will have NO EFFECT.
     To actually allow this without prompting, remove the global ask rule:
       /set-global-permissions remove "[global-pattern]"
     Add anyway? (yes/no)
     ```
     **Pause and wait for user confirmation before writing.**
   - If the global deny list contains a matching pattern, warn: "A global deny rule blocks this command — adding it to project allow won't help. Remove the global deny rule first."

   **If adding to `ask`**:
   - If `"Bash"` is in global allow AND the pattern is `Bash(...)`, inform (not block):
     ```
     Note: ~/.claude/settings.json has "Bash" in global allow, meaning all Bash
     commands are already auto-approved globally. Adding this to project ask
     will make this specific command prompt in this project only.
     This is intentional if you want extra confirmation here. Proceed? (yes/no)
     ```
     **Pause and wait for user confirmation before writing.**

3. **Add the pattern** to the correct array in `TARGET_FILE`.

4. Print: "Added to [list]: [pattern]  →  [TARGET_FILE]"

---

### `remove <pattern>`

1. Search all three lists for the exact pattern.
2. If not found → print "Pattern not found in any list: [pattern]" and stop.
3. Remove it from whichever list(s) contain it.
4. Print: "Removed from [list]: [pattern]  →  [TARGET_FILE]"

---

### `move <from-list> <to-list> <pattern>`

Valid list names: `allow`, `ask`, `deny`.

1. Verify `from-list` and `to-list` are valid names. If not → print valid options and stop.
2. Check the pattern exists in `from-list`. If not → print "Pattern not found in [from-list]: [pattern]" and stop.
3. Remove from `from-list`, add to `to-list`.
4. Print: "Moved [pattern]: [from-list] → [to-list]  →  [TARGET_FILE]"

---

## Phase 3: Validate

After any write, read `TARGET_FILE` back and verify:
- Valid JSON (if not, print the JSON error and restore from the pre-edit content)
- The expected pattern appears in the expected list

Print a one-line confirmation of the final state.

---

## Glob Syntax Reference (shown when user adds a pattern)

After any successful add, print this reminder if the pattern contains `Bash(`:

```
Glob syntax: * matches any string within a token — it does NOT match spaces by default.
  Bash(curl * localhost:*)   matches: curl -s http://localhost:3000/api
  Bash(git -C * status*)     matches: git -C /path/to/repo status --short
  Bash(npm run *)            matches: npm run build, npm run test
  Bash(command:*)            matches any command starting with "command"
```

---

## Examples

```
/set-permissions list
/set-permissions allow "Bash(curl * localhost:*)"
/set-permissions ask "Bash(git push:*)"
/set-permissions deny "Bash(rm -rf *)"
/set-permissions remove "Bash(curl:*)"
/set-permissions move ask allow "Bash(npm run *)"
/set-permissions --local allow "Bash(docker compose *)"
```
