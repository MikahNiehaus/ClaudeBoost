---
description: Generate a conventional commit message by analyzing staged or unstaged git changes
allowed-tools: Bash
---

# /commit-message

Analyze the current git diff and output a ready-to-copy commit message following the [Conventional Commits](https://www.conventionalcommits.org/) specification.

## Steps

1. Check staged changes:
   ```bash
   git diff --staged
   ```

2. If nothing staged, check unstaged:
   ```bash
   git diff
   ```

3. Analyze the diff and identify:
   - **Type**: feat, fix, docs, refactor, test, chore, perf, ci, style, build
   - **Scope**: Affected area or module (optional but recommended)
   - **Description**: What changed and why (imperative mood — "add" not "added")

4. Output the commit message in this format:
   ```
   type(scope): brief description

   Optional body — explain the "why" for non-obvious changes.
   - Bullet points for multiple related changes

   Optional footer for breaking changes or issue references.
   ```

## Commit Types

| Type | Use for |
|------|---------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `chore` | Maintenance, dependencies, configs |
| `perf` | Performance improvement |
| `ci` | CI/CD changes |
| `style` | Formatting, whitespace (no logic change) |
| `build` | Build system or external dependency changes |

## Guidelines

- First line: under 72 characters
- Use imperative mood: "add" not "added", "fix" not "fixed"
- Body: explain "why" for non-obvious changes
- Footer: reference issues, note breaking changes with `BREAKING CHANGE:` or `!` suffix on the type
- One logical change per commit

## Output

Output only the commit message — no preamble, no explanation. The message should be ready to paste directly into `git commit -m "..."` or a HEREDOC.
