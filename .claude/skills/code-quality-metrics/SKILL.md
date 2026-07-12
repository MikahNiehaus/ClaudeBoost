---
name: code-quality-metrics
description: Consider code quality metrics (complexity, maintainability, LOC) injected in context when making changes. Lower maintainability (<50) or high complexity (>15) warrant refactoring.
---

## Code Quality Metrics in Context

When you see a "Code Quality Metrics" section in your context, use it to guide refactoring decisions:

- **Maintainability Index < 50**: File is difficult to maintain. Consider breaking into smaller functions.
- **Cyclomatic Complexity > 15**: Too many branches. Simplify with early returns, extract methods, or split responsibilities.
- **Lines of Code > 500**: Long files should be modularized. Extract cohesive groups into separate modules.

## When to Refactor

- If user asks to modify a file with low maintainability, suggest refactoring first
- If complexity is high and the change adds more branches, simplify first
- If LOC is very high (>1000), split into smaller files before making large changes

## When NOT to Refactor

- User explicitly says "don't refactor, just fix the bug"
- File is a thin wrapper or data class (high LOC but low complexity = acceptable)
- Metrics are improving with current change (don't over-optimize)
