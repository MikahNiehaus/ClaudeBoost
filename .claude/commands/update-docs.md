---
description: Generate project documentation in docs/ folder
allowed-tools: Read, Write, Glob, Bash, Grep
---

# Update Documentation

Generate polished documentation for the PROJECT (not the toolkit) in the `docs/` folder.

**Note**: docs/ is gitignored. Run this command to create/update documentation when work is complete.

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

Report:
- What documentation was created/updated
- Key sections covered
- Any gaps that need manual attention
