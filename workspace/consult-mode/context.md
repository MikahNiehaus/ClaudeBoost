# Task: CONSULT Mode for ClaudeBoost

## Goal
Add a structurally-enforced collaborative mode (`CONSULT`) that makes Claude announce architectural proposals before writing code, so the user can add constraints on top. Bypass mode `AUTO` available via slash command. Default is CONSULT.

## Status
- **Phase:** Planning complete, awaiting implementation approval
- **Branch:** `feature/consult-mode`
- **Mode:** NORMAL (stop after each step for user review)
- **Set By:** Orchestrator
- **Set At:** 2026-04-10

## Artifacts
- `ticket.md` — original user request verbatim + planning clarifications
- `plan.md` — full implementation plan (design decisions, hook architecture, draft prompt strings, verification plan)

## Key Design Decisions
1. Mode names: `CONSULT` (default) / `AUTO` (bypass) — matches existing NORMAL/PERSISTENT register
2. Approval memory: session-scoped via `state/session-approvals.json`
3. Consultation is additive, not gatekeeping — RAG standards always apply, user adds constraints
4. Research-first enforced via `architect-agent` PROPOSAL_ONLY refusal contract (≥2 file:line citations required)
5. Three layered hooks: SessionStart + PreToolUse(Edit|Write|MultiEdit) + PreToolUse(Task) + PreCompact
6. Meta-dir exemption: `workspace/`, `.claude/`, `knowledge/`, `plans/`, `docs/` bypass CONSULT

## Files to Modify (from plan.md)
### Create
- `.claude/commands/consult.md`
- `.claude/commands/auto.md`
- `knowledge/consult-mode.xml`
- `state/claudeboost-mode.json`
- `state/session-approvals.json`

### Modify
- `scripts/setup.ps1` (idempotency fix + 4 hook appends + state dir seeding)
- `agents/architect-agent.xml` (add `<consultation-mode>` refusal block)
- `knowledge/scope-governance.xml` (cross-ref consult-mode.xml)
- `.claude/commands/boost.md` (print current mode on boot)
- `CLAUDE.md` (document CONSULT/AUTO alongside existing modes)

## Biggest Implementation Gotcha
`scripts/setup.ps1:115-120` uses `if (-not $settings.hooks.PSObject.Properties["PreToolUse"])` which SKIPS entirely on upgrade (property already exists). Must change to sentinel-string scan + append to the existing array so new matchers install for existing users.

## Next Steps
1. User reviews plan.md
2. Orchestrator spawns implementation agents per plan
3. Each hook prompt is drafted already — execution agent just wires them

## Agent Contributions
_None yet — planning phase only._

## Completion Criteria
| # | Criterion | Verification | Status |
|---|-----------|--------------|--------|
| 1 | state files seeded on fresh install | re-run setup.ps1 on clean machine | pending |
| 2 | CONSULT triggers architect-agent spawn on new endpoint | manual test: "add /health endpoint" | pending |
| 3 | CONSULT does not trigger on typo fix | manual test: fix README typo | pending |
| 4 | /auto bypass works, /consult restores | toggle both, verify state file updates | pending |
| 5 | Research refusal: architect-agent blocks spawn without citations | craft malformed spawn | pending |
| 6 | Approval memory: second endpoint reuses first's validation choice | sequential endpoint requests | pending |
| 7 | Idempotent upgrade: re-running setup.ps1 does not duplicate hooks | run twice, diff settings.json | pending |
