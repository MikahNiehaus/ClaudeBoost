# Rule Enforcement Methodology

<knowledge-base name="rule-enforcement" version="1.0">
<triggers>rule, enforce, compliance, violation, check, validate, audit</triggers>
<overview>How rules are enforced in the multi-agent system via soft enforcement (compliance protocols) and periodic audits.</overview>

<rule-structure>
  <format><![CDATA[
### RULE-XXX: [Rule Name]
- **ID**: RULE-XXX
- **TRIGGER**: [When to check this rule]
- **CONDITION**: [What must be true]
- **ACTION**: [What to do if violated]
- **SEVERITY**: BLOCK | WARN
]]></format>
  <severity-levels>
    <level name="BLOCK" meaning="Critical - execution must stop" action="Halt, correct, then continue"/>
    <level name="WARN" meaning="Important guideline" action="Log in context.md, continue"/>
  </severity-levels>
</rule-structure>

<enforcement-mechanisms>
  <mechanism name="Soft Enforcement" primary="true">
    <trigger-points>
      <point>Before spawning any agent</point>
      <point>Before any Write/Edit tool call</point>
      <point>Every 10 actions on long-running tasks</point>
      <point>Before responding to user</point>
    </trigger-points>
    <compliance-checklist>
      <check rule="RULE-001">Am I writing code without an agent?</check>
      <check rule="RULE-002">Does task have 2+ steps without TodoWrite?</check>
      <check rule="RULE-003">Am I spawning agent without planning?</check>
      <check rule="RULE-004">Did last agent report status field?</check>
      <check rule="RULE-005">Did I update context.md after last agent?</check>
      <check rule="RULE-006">Is this research without research-agent?</check>
      <check rule="RULE-007">Does task involve security without security-agent?</check>
    </compliance-checklist>
  </mechanism>

  <mechanism name="Periodic Audits" secondary="true">
    <description>Spawn compliance-agent every ~10 actions for long tasks</description>
    <coverage>
      <item>Reviews all rules against task history</item>
      <item>Checks context.md for proper logging</item>
      <item>Verifies agent outputs have status fields</item>
      <item>Reports violations with evidence</item>
    </coverage>
  </mechanism>

  <mechanism name="Constitutional Principles" embedded="true">
    <principle>Complete ALL subtasks before reporting COMPLETE</principle>
    <principle>When blocked, explicitly report blockers</principle>
    <principle>When uncertain, report NEEDS_INPUT</principle>
    <principle>Verify outputs against acceptance criteria</principle>
    <principle>Document key decisions in handoff notes</principle>
  </mechanism>
</enforcement-mechanisms>

<pre-action-validation><![CDATA[
For this action: [description]

1. Which rules have TRIGGER conditions that match?
2. For each triggered rule:
   - Is the CONDITION met?
   - If NO: What ACTION is required?
   - What is the SEVERITY?

3. For BLOCK severity violations:
   - STOP immediately
   - Execute corrective ACTION
   - Log correction in context.md
   - Resume from compliant state

4. For WARN severity violations:
   - Log in context.md Notes section
   - Continue execution
]]></pre-action-validation>

<self-correction-protocol>
  <step order="1" name="Acknowledge">State which rule was violated</step>
  <step order="2" name="Correct">Take corrective action immediately</step>
  <step order="3" name="Log">Add to context.md with Rule, Violation, Correction</step>
  <step order="4" name="Continue">Resume from compliant state</step>
</self-correction-protocol>

<rule-specific-enforcement>
  <rule id="RULE-001" name="Agent Spawn Required for Code">
    <check-before>Write, Edit tool calls on code files</check-before>
    <verification>Is this code file? Has agent been spawned? Check context.md</verification>
    <if-violated>STOP Write/Edit → Identify agent → Spawn agent → Let agent produce change</if-violated>
  </rule>

  <rule id="RULE-002" name="TodoWrite for Multi-Step Tasks">
    <check-before>Starting execution on any task</check-before>
    <verification>Task has 2+ steps? TodoWrite called? Items being marked?</verification>
    <if-violated>STOP → Create TodoWrite list → Continue with first item</if-violated>
  </rule>

  <rule id="RULE-003" name="Planning Phase Required">
    <check-before>Spawning any agent</check-before>
    <verification>workspace/[task-id]/context.md exists? Plan section populated?</verification>
    <if-violated>STOP spawn → Create workspace → Run planning → Generate plan → Then spawn</if-violated>
  </rule>

  <rule id="RULE-004" name="Agent Status Validation">
    <check-after>Any agent completes</check-after>
    <verification>Output contains "Status:"? Is COMPLETE, BLOCKED, or NEEDS_INPUT?</verification>
    <if-violated>Request clarification → Do NOT proceed without status</if-violated>
  </rule>

  <rule id="RULE-005" name="Context Logging Required">
    <check-after>Any agent action or decision</check-after>
    <verification>context.md updated? Agent Contributions current? Handoff notes documented?</verification>
    <if-violated>STOP next action → Update context.md → Continue</if-violated>
  </rule>

  <rule id="RULE-006" name="Research Agent for Research" severity="WARN">
    <check-when>Task involves web search, fact verification</check-when>
    <if-violated>Log in Notes → Consider spawning research-agent → Continue</if-violated>
  </rule>

  <rule id="RULE-007" name="Security Agent for Security" severity="WARN">
    <check-when>Task involves auth, user input, sensitive data</check-when>
    <if-violated>Log in Notes → Add security-agent to plan → Continue</if-violated>
  </rule>

  <rule id="RULE-008" name="Token Efficient Spawning" severity="WARN">
    <check-when>Spawning any agent</check-when>
    <verification>Prompt says "READ" instead of pasting? Definitions not duplicated?</verification>
    <if-violated>Log inefficiency → Rewrite prompt → Continue</if-violated>
  </rule>
</rule-specific-enforcement>

<best-practices>
  <do>
    <item>Check rules BEFORE taking action, not after</item>
    <item>Log all violations, even corrected ones</item>
    <item>Use compliance-agent for long tasks</item>
    <item>Update context.md with compliance status</item>
    <item>Treat BLOCK rules as non-negotiable</item>
  </do>
  <dont>
    <item>Skip checks for "simple" tasks</item>
    <item>Batch compliance checks at end of task</item>
    <item>Ignore WARN violations entirely</item>
    <item>Proceed without status from agents</item>
    <item>Modify code without spawning agent</item>
  </dont>
</best-practices>

</knowledge-base>
