---
description: Generate project documentation in docs/ folder
allowed-tools: Read, Write, Glob, Bash, Grep
---

# Update Documentation

Generate polished documentation for the PROJECT (not the toolkit) in the `docs/` folder.

**Note**: docs/ is gitignored. Run this command to create/update documentation when work is complete.

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

Call `rag_context(agent="workflow-agent", task_description="generate project documentation", max_tokens=3000)`.

This loads relevant knowledge before any work begins. If `rag_context` fails: stop and tell the user "RAG is not connected. Run /boost before using this skill."

---

## When to Use

- After completing a feature or milestone
- When project documentation needs updating
- To create clean, organized docs from workspace notes

## Instructions

1. **Create docs/ folder** (if it doesn't exist):
   ```
   mkdir -p docs
   ```

2. **Review completed work** in workspace/:
   - Read context.md files from completed tasks
   - Identify what's been built/changed
   - Gather key findings and decisions

3. **Explore the project codebase**:
   - Identify main components and structure
   - Find API endpoints, key functions, architecture
   - Note important patterns and conventions

4. **Generate documentation**:
   - `docs/README.md` - Project overview, getting started
   - `docs/architecture.md` - System design, components (if applicable)
   - `docs/api.md` - API reference (if applicable)
   - Other docs as appropriate for the project

5. **Structure should reflect the PROJECT**, not the toolkit:
   - What does this project do?
   - How is it organized?
   - How do you use it?
   - Key concepts and patterns

## Documentation Style

- Clear and concise
- Code examples where helpful
- Organized by topic/component
- Written for someone new to the project

## After Update

Before reporting completion to the user, spawn a single `evaluator-agent` with this prompt:

"Read the generated documentation files listed above. Verify:
1. Every command, script, or API call described in the docs actually exists in the project (check package.json scripts, Makefile targets, or source files as needed).
2. If multiple sections were planned (e.g., README, architecture, API), verify each promised section is present and non-empty.
3. Flag any section that describes a command or endpoint not found in the codebase, or any planned section that is missing.

Output a simple table:
| Claim/Section | Evidence present? | Verdict (CONFIRMED/NEEDS_EVIDENCE) |

Flag any NEEDS_EVIDENCE items. Under 500 tokens."

Surface any NEEDS_EVIDENCE items to the user alongside the completion report.

Then report:
- What documentation was created/updated
- Key sections covered
- Any gaps that need manual attention
