# Shared Agent Output Format

<shared-standards version="1.0">
<overview>All agents reference this for consistent output structure. Saves ~200 tokens per agent definition.</overview>

<required-status><![CDATA[
---
## Agent Status

**Status**: [COMPLETE | BLOCKED | NEEDS_INPUT]
**Confidence**: [HIGH | MEDIUM | LOW]
**Confidence Reasoning**: [1-2 sentences why this confidence level]

**If BLOCKED**:
- Blocked by: [What's preventing progress]
- Need: [What would unblock]

**If NEEDS_INPUT**:
- Question: [What clarification is needed]
- Options: [If applicable, list choices]

**Handoff Notes**: [Key findings for next agent or orchestrator]
]]></required-status>

<status-definitions>
  <status name="COMPLETE" meaning="Task finished successfully" action="Continue to next agent or synthesize"/>
  <status name="BLOCKED" meaning="Cannot proceed" action="Route to unblocking agent or ask user"/>
  <status name="NEEDS_INPUT" meaning="Need clarification" action="Ask user, then resume or re-spawn"/>
</status-definitions>

<context-acknowledgment required="true" when="collaborative tasks"><![CDATA[
---
## Context Acknowledgment

- **Context Read**: YES / NO / N/A (no prior context)
- **Context Path**: `workspace/[task-id]/context.md`
- **Prior Agents**: [List agents who contributed before you, or "None"]
- **Key Context Used**: [1-2 sentences: What you learned from prior work]
]]></context-acknowledgment>

<behavioral-guidelines>
  <guideline order="1">Read context FIRST: For collaborative tasks, read workspace/[task-id]/context.md before anything</guideline>
  <guideline order="2">Read your definition: Load your agent file for role clarity</guideline>
  <guideline order="3">Read knowledge base: Load domain expertise before acting</guideline>
  <guideline order="4">Stay in scope: Only handle your domain, escalate others</guideline>
  <guideline order="5">Be explicit: State assumptions, don't guess silently</guideline>
  <guideline order="6">Document findings: Future agents may need your discoveries</guideline>
  <guideline order="7">Fail fast: Report BLOCKED early, don't spin on impossible tasks</guideline>
  <guideline order="8">Update parallel findings: If spawned in parallel, add findings immediately</guideline>
  <guideline order="9">Self-reflect: Run self-reflection checklist before finalizing (knowledge/self-reflection.md)</guideline>
  <guideline order="10">Report confidence: Include confidence level with reasoning in status</guideline>
  <guideline order="11">Self-critique code: Review each line/block, document assumptions/edge cases (knowledge/code-critique.md)</guideline>
  <guideline order="12">Teach with code: Explain WHY, alternatives rejected, concepts applied (knowledge/code-teaching.md)</guideline>
  <guideline order="13">Validate standards: Verify SOLID, code metrics, patterns, OOP best practices (knowledge/coding-standards.md)</guideline>
  <guideline order="14">Add appropriate logging: Code with side effects, error handling, or external calls must include structured logging at correct levels. Error/catch blocks MUST have logger.error. See knowledge/observability.md</guideline>
</behavioral-guidelines>

<code-critique-template required-for="code changes"><![CDATA[
## Self-Critique

| Line/Block | Purpose | Critique | Fix Applied |
|------------|---------|----------|-------------|
| `[code]` | [why it exists] | [issue or "Sound"] | [fix or "None"] |

**Assumptions Made**: [List assumptions the code relies on]
**Edge Cases Not Covered**: [What's not handled and why]
**Trade-offs Accepted**: [What you sacrificed for what gain]
]]></code-critique-template>

<teaching-template required-for="code changes"><![CDATA[
## Teaching

**Why This Approach**:
[Explain the design decision - not just WHAT but WHY]

**Alternatives Considered**:
| Alternative | Why Rejected |
|-------------|--------------|
| [Option A] | [Reason] |

**Key Concepts Applied**:
1. **[Concept]**: [Brief explanation of principle/pattern used]

**What You Should Learn**:
- [Key insight 1]

**Questions to Think About**:
- [Socratic question about the code]
]]></teaching-template>

<standards-compliance-template required-for="code changes"><![CDATA[
## Standards Compliance Check

### SOLID Principles
- [ ] **SRP**: Each class has single responsibility
- [ ] **OCP**: Design supports extension without modification
- [ ] **LSP**: Subtypes are substitutable for base types
- [ ] **ISP**: Interfaces are small and focused
- [ ] **DIP**: Dependencies point to abstractions

### Code Metrics
- [ ] Cyclomatic complexity ≤ 10 per method
- [ ] Method length ≤ 40 lines
- [ ] Class length ≤ 300 lines
- [ ] Parameter count ≤ 4
- [ ] Nesting depth ≤ 3

### Design Patterns (if applicable)
- [ ] Pattern choice is justified
- [ ] Pattern is correctly implemented
- [ ] No anti-patterns present

### OOP Best Practices
- [ ] Composition preferred over deep inheritance
- [ ] Encapsulation maintained
- [ ] High cohesion within classes
- [ ] Low coupling between classes

### Logging & Observability (if code has side effects)
- [ ] Error/catch blocks include logger.error with context (BLOCKER if missing)
- [ ] Service methods log entry and outcome
- [ ] External service calls are logged
- [ ] Log levels match severity (ERROR/WARN/INFO/DEBUG)
- [ ] No sensitive data in log output
- [ ] Structured format used (key-value context)

### Violations Found
| Principle | Location | Issue | Severity |
|-----------|----------|-------|----------|
| [SOLID/Metric/Pattern/OOP] | [file:line] | [description] | [H/M/L] |

### Standards Verdict
**Verdict**: [PASS / PASS_WITH_WARNINGS / FAIL]
]]></standards-compliance-template>

<verdict-definitions>
  <verdict name="PASS">All standards met → proceed to COMPLETE</verdict>
  <verdict name="PASS_WITH_WARNINGS">Minor issues, acceptable → proceed, note for future</verdict>
  <verdict name="FAIL">Significant violations → must fix before COMPLETE</verdict>
</verdict-definitions>

<model-selection>
  <model agent="architect-agent" type="opus" rationale="Design decisions cascade"/>
  <model agent="ticket-analyst-agent" type="opus" rationale="Requirements understanding critical"/>
  <model agent="reviewer-agent" type="opus" rationale="Final quality gate"/>
  <model agent="all others (15)" type="sonnet" rationale="Escalate on LOW confidence"/>
  <escalation-note>If you report LOW confidence or BLOCKED, orchestrator may retry with Opus</escalation-note>
</model-selection>

<rules-enforced>
  <rule id="RULE-016">Self-Critique and Teaching sections required for code changes</rule>
  <rule id="RULE-017">Standards Compliance Check required for code changes</rule>
  <rule id="RULE-025">Logging enforcement for code with side effects</rule>
</rules-enforced>

</shared-standards>
