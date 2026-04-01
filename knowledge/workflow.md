# Development Workflow & Reliable Execution Guide

<knowledge-base name="workflow" version="1.0">
<triggers>implement, execute, development, multi-step, feature, workflow, execution</triggers>
<overview>Claude 4.x follows instructions precisely but won't go "above and beyond" unless told. Structure prompts like managing a brilliant but inexperienced developer who needs clear boundaries, systematic processes, and mandatory verification.</overview>

<failure-patterns>
  <pattern name="Premature stopping">
    <problem>Completes part of task, moves on</problem>
    <solution>Structured progress tracking with checkpoints</solution>
  </pattern>
  <pattern name="Test manipulation">
    <problem>Modifies tests to match buggy code</problem>
    <solution>TDD workflow with tests committed first</solution>
  </pattern>
  <pattern name="Context drift">
    <problem>Forgets earlier instructions</problem>
    <solution>Recursive self-display of rules</solution>
  </pattern>
  <pattern name="Scope creep">
    <problem>Makes "improvements" beyond request</problem>
    <solution>Explicit scope boundaries</solution>
  </pattern>
  <pattern name="Skipping verification">
    <problem>Assumes tests pass without running</problem>
    <solution>Mandatory test execution at each phase</solution>
  </pattern>
</failure-patterns>

<plan-before-execute>
  <phase name="Explore">
    <step>Read relevant files</step>
    <step>Understand current architecture patterns</step>
    <step>Identify relevant existing modules</step>
    <step>List integration points</step>
    <step>Identify potential risks</step>
  </phase>
  <phase name="Plan">
    <step>Create detailed step-by-step approach</step>
    <step>Document modules to create/modify with rationale</step>
    <step>Define testing strategy</step>
    <step>Create rollback plan</step>
    <step>Save to plan.md and wait for approval</step>
  </phase>
  <phase name="Implement">
    <step>Execute with verification at each stage</step>
    <step>Run tests and fix failures</step>
    <step>Check integration with existing code</step>
    <step>Update plan.md progress</step>
    <step>Ask for review before next phase</step>
  </phase>
  <phase name="Commit">
    <step>Document changes</step>
    <step>Create PR with updated documentation</step>
  </phase>
</plan-before-execute>

<tdd-workflow>
  <step order="1">Write tests FIRST based on expected input-output pairs</step>
  <step order="2">Run tests and confirm they FAIL</step>
  <step order="3">Commit tests when satisfied with coverage</step>
  <step order="4">Implement functionality to make tests pass</step>
  <step order="5">Run tests and confirm they PASS</step>
  <step order="6">Commit the working implementation</step>
  <critical-rule>It is UNACCEPTABLE to remove, comment out, or edit tests to make them pass. Tests define requirements. If a test fails, fix the CODE, never the test.</critical-rule>
</tdd-workflow>

<database-safety>
  <before-any-operation>
    <step>Identify environment by checking environment variables</step>
    <step>Analyze connection strings for production indicators</step>
    <step>Confirm database name matches expected patterns</step>
    <step>Verify appropriate permissions</step>
  </before-any-operation>
  <operation-matrix>
    <operation type="READ" dev="Proceed" staging="Proceed" prod="Proceed"/>
    <operation type="WRITE" dev="Proceed" staging="Warn" prod="Warn"/>
    <operation type="DESTRUCTIVE" dev="Warn" staging="Block" prod="REFUSE"/>
    <operation type="SCHEMA" dev="Migrations only" staging="Migrations only" prod="Migrations only"/>
  </operation-matrix>
  <production-indicators>prod, production, .rds.amazonaws.com, .database.windows.net</production-indicators>
  <safe-indicators>localhost, 127.0.0.1, dev, test, _dev_, _test_, .local</safe-indicators>
</database-safety>

<circuit-breakers><![CDATA[
If tests fail, iterate to fix them. Maximum 5 attempts.
If all 5 attempts fail without resolution:
- STOP
- Summarize what you tried
- Explain why it's failing
- Ask for human guidance
]]></circuit-breakers>

<state-tracking>
  <file name="progress.json"><![CDATA[
{
  "current_phase": "implementation",
  "completed_tasks": ["setup", "models", "api"],
  "current_task": "frontend components",
  "next_tasks": ["testing", "documentation"],
  "blockers": []
}
]]></file>
  <new-session-steps>
    <step>Verify directory (pwd)</step>
    <step>Read progress.json</step>
    <step>Review recent git history</step>
    <step>Run tests</step>
    <step>Continue from next task</step>
  </new-session-steps>
</state-tracking>

<scope-control><![CDATA[
Fix ONLY the code directly related to [specific issue].
Do NOT:
- Refactor unrelated code
- "Improve" things outside this scope
- Make architectural changes

After making changes:
- Run ONLY the tests for [affected module]
- Report what changed and what tests you ran
]]></scope-control>

<anti-patterns-to-forbid>
  <pattern name="God Objects">Classes over 200 lines doing multiple things</pattern>
  <pattern name="Anemic Domain Models">All logic in services, none in domain</pattern>
  <pattern name="Circular Dependencies">A imports B imports A</pattern>
  <pattern name="Missing Error Handling">Only happy path implemented</pattern>
  <pattern name="Hardcoded Configuration">Magic strings/numbers</pattern>
  <pattern name="Tight Coupling">Direct concrete dependencies</pattern>
  <pattern name="Layer Violations">Domain calling infrastructure</pattern>
</anti-patterns-to-forbid>

<verification-checklist>
  <item>Architecture violations?</item>
  <item>Missing error handling for edge cases?</item>
  <item>Security vulnerabilities?</item>
  <item>Performance bottlenecks?</item>
  <item>Test coverage gaps?</item>
  <item>Anti-patterns present?</item>
</verification-checklist>

<session-start-checklist>
  <item>Read CLAUDE.md for project rules</item>
  <item>Check progress.json for current state</item>
  <item>Review recent git commits</item>
  <item>Run existing tests to establish baseline</item>
  <item>Identify task scope and boundaries</item>
  <item>Create/update todo list for tracking</item>
</session-start-checklist>

</knowledge-base>
