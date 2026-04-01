# System Rules Reference

<knowledge-base name="rules" version="1.0">
<triggers>rule, RULE-, violation, compliance, block, warn, enforcement</triggers>
<overview>15 system rules enforced by orchestrator and compliance-agent</overview>

<rule-format>
  <field name="ID">Unique identifier (RULE-XXX)</field>
  <field name="TRIGGER">When to check this rule</field>
  <field name="CONDITION">What must be true</field>
  <field name="ACTION">What to do if violated</field>
  <field name="SEVERITY">BLOCK (halt) or WARN (log and continue)</field>
</rule-format>

<rules severity="BLOCK">

<rule id="RULE-001" name="Agent Spawn Required for Code Changes">
  <trigger>Before any Write/Edit tool call on code files</trigger>
  <condition>An appropriate agent has been spawned for this task</condition>
  <action>HALT. Spawn appropriate agent before editing code.</action>
  <mappings>
    <map task="Testing code" agent="test-agent"/>
    <map task="Bug fixes" agent="debug-agent"/>
    <map task="Architecture decisions" agent="architect-agent"/>
    <map task="Security changes" agent="security-agent"/>
    <map task="Refactoring" agent="refactor-agent"/>
  </mappings>
</rule>

<rule id="RULE-002" name="TodoWrite for Multi-Step Tasks">
  <trigger>After identifying task has 2+ steps</trigger>
  <condition>TodoWrite has been called with task items</condition>
  <action>HALT. Create todo list before proceeding.</action>
</rule>

<rule id="RULE-003" name="Planning Phase Required">
  <trigger>Before spawning any agent</trigger>
  <condition>workspace/[task-id]/context.md exists with Plan section populated</condition>
  <action>HALT. Complete planning phase first.</action>
  <planning-checklist>
    <domain id="1">Testing - New code, behavior changes, bug fixes?</domain>
    <domain id="2">Documentation - API changes, config changes, user features?</domain>
    <domain id="3">Security - Auth, user input, sensitive data, DB queries?</domain>
    <domain id="4">Architecture - New component, design decisions, integrations?</domain>
    <domain id="5">Performance - Large loops, DB queries, caching, hot paths?</domain>
    <domain id="6">Review - Code changes ready for merge?</domain>
    <domain id="7">Clarity - Vague request, missing acceptance criteria?</domain>
  </planning-checklist>
</rule>

<rule id="RULE-004" name="Agent Status Validation">
  <trigger>After any agent completes</trigger>
  <condition>Agent output contains Status: COMPLETE | BLOCKED | NEEDS_INPUT</condition>
  <action>HALT. Request status if missing. Do not proceed without it.</action>
  <status-handling>
    <status value="COMPLETE">Continue to next step</status>
    <status value="BLOCKED">Resolve blocker before continuing</status>
    <status value="NEEDS_INPUT">Get user clarification</status>
  </status-handling>
</rule>

<rule id="RULE-005" name="Context Logging Required">
  <trigger>After any agent action or orchestrator decision</trigger>
  <condition>workspace/[task-id]/context.md updated with contribution</condition>
  <action>HALT. Update context.md before continuing.</action>
  <required-fields>
    <field>Agent name and timestamp</field>
    <field>Task assigned</field>
    <field>Status returned</field>
    <field>Key findings</field>
    <field>Handoff notes</field>
  </required-fields>
</rule>

<rule id="RULE-010" name="Playwright MCP Tool Usage Required">
  <trigger>When using Playwright for browser interaction</trigger>
  <condition>Using mcp__playwright_* tools directly (NOT writing code)</condition>
  <action>HALT. Use MCP tools instead of writing Playwright code.</action>
  <required-tools>
    <tool>mcp__playwright_browser_navigate</tool>
    <tool>mcp__playwright_browser_click</tool>
    <tool>mcp__playwright_browser_type</tool>
    <tool>mcp__playwright_browser_snapshot</tool>
  </required-tools>
</rule>

<rule id="RULE-012" name="Self-Reflection Required">
  <trigger>Before any agent reports COMPLETE status</trigger>
  <condition>Agent has performed self-reflection checklist</condition>
  <action>HALT. Run self-reflection, include confidence level.</action>
  <required-output>
    <field>Confidence: HIGH | MEDIUM | LOW</field>
    <field>Confidence Reasoning: 1-2 sentences</field>
  </required-output>
</rule>

<rule id="RULE-014" name="No Stopping in PERSISTENT Mode">
  <trigger>When task mode is PERSISTENT and considering asking user</trigger>
  <condition>All completion criteria are MET or tokens exhausted</condition>
  <action>HALT any question/stopping until criteria met. Auto-continue.</action>
  <blocked-phrases>
    <phrase>Shall I continue?</phrase>
    <phrase>Would you like...</phrase>
    <phrase>Let me know if...</phrase>
    <phrase>Should I proceed...</phrase>
  </blocked-phrases>
</rule>

<rule id="RULE-015" name="Ask Before Migrations and Deployments">
  <trigger>Before running migration, deployment, or database-altering command</trigger>
  <condition>User has explicitly approved this specific operation</condition>
  <action>HALT. Ask user for confirmation before proceeding.</action>
  <always-ask>
    <operation>Database migrations (migrate, db push, prisma migrate)</operation>
    <operation>Database seeding</operation>
    <operation>Deployments (deploy, publish, release)</operation>
    <operation>Production operations</operation>
    <operation>Schema changes</operation>
  </always-ask>
</rule>

<rule id="RULE-016" name="Code Critique and Teaching Required">
  <trigger>When any agent produces code changes in output</trigger>
  <condition>Output includes BOTH Self-Critique AND Teaching sections</condition>
  <action>Reject output, request agent re-do with both sections</action>
  <required-critique ref="knowledge/code-critique.md">
    <field>Line-by-line review table</field>
    <field>Assumptions documented</field>
    <field>Edge cases not covered</field>
    <field>Trade-offs accepted</field>
  </required-critique>
  <required-teaching ref="knowledge/code-teaching.md">
    <field>Why this approach (not just what)</field>
    <field>Alternatives considered and rejected</field>
    <field>Key concepts/patterns applied</field>
    <field>What user should learn</field>
    <field>Questions to deepen understanding</field>
  </required-teaching>
  <applies-to>
    <agent>debug-agent</agent>
    <agent>workflow-agent</agent>
    <agent>refactor-agent</agent>
    <agent>test-agent</agent>
    <agent>ui-agent</agent>
    <agent>architect-agent</agent>
  </applies-to>
</rule>

<rule id="RULE-017" name="Coding Standards Compliance Required">
  <trigger>When any agent produces code changes in output</trigger>
  <condition>Output includes Standards Compliance Check section</condition>
  <action>Verify SOLID, metrics, patterns; spawn standards-validator-agent if issues</action>
  <solid-checks ref="knowledge/coding-standards.md">
    <check id="SRP">Each class has one reason to change</check>
    <check id="OCP">Extend without modifying existing code</check>
    <check id="LSP">Subtypes substitutable for base types</check>
    <check id="ISP">Small, focused interfaces</check>
    <check id="DIP">Depend on abstractions</check>
  </solid-checks>
  <metrics>
    <metric name="Cyclomatic complexity" max="10" unit="per method"/>
    <metric name="Method length" max="40" unit="lines"/>
    <metric name="Class length" max="300" unit="lines"/>
    <metric name="Parameter count" max="4"/>
    <metric name="Nesting depth" max="3"/>
  </metrics>
  <verdicts>
    <verdict value="PASS">Proceed to COMPLETE</verdict>
    <verdict value="PASS_WITH_WARNINGS">Proceed, note for future</verdict>
    <verdict value="FAIL">Must fix before COMPLETE</verdict>
  </verdicts>
  <applies-to>
    <agent>debug-agent</agent>
    <agent>workflow-agent</agent>
    <agent>refactor-agent</agent>
    <agent>test-agent</agent>
    <agent>ui-agent</agent>
    <agent>architect-agent</agent>
    <agent>standards-validator-agent</agent>
  </applies-to>
</rule>

<rule id="RULE-022" name="Mandatory Best Practices Review">
  <trigger>When reviewer-agent or any agent performs code review</trigger>
  <condition>Review output includes Best Practices Assessment section</condition>
  <action>Reject review, require Best Practices Assessment with all subsections</action>
  <required-subsections>
    <subsection name="SOLID Compliance">
      <check id="SRP">Single responsibility verified</check>
      <check id="OCP">Open/closed verified</check>
      <check id="LSP">Liskov substitution verified</check>
      <check id="ISP">Interface segregation verified</check>
      <check id="DIP">Dependency inversion verified</check>
    </subsection>
    <subsection name="GoF Patterns">
      <check>Patterns identified and validated</check>
      <check>Anti-patterns flagged</check>
    </subsection>
    <subsection name="OOP Best Practices">
      <check>Composition over inheritance</check>
      <check>Encapsulation maintained</check>
      <check>Cohesion/coupling assessed</check>
    </subsection>
    <subsection name="Clean Code">
      <check>Naming conventions</check>
      <check>Function single responsibility</check>
      <check>No magic numbers</check>
      <check>DRY principle</check>
    </subsection>
    <subsection name="Metrics">
      <check>Complexity ≤ 10</check>
      <check>Method length ≤ 40</check>
      <check>Class length ≤ 300</check>
    </subsection>
  </required-subsections>
  <verdict-required>PASS | PASS_WITH_WARNINGS | FAIL</verdict-required>
  <applies-to>
    <agent>reviewer-agent</agent>
    <agent>architect-agent</agent>
    <agent>standards-validator-agent</agent>
  </applies-to>
</rule>

</rules>

<rules severity="WARN">

<rule id="RULE-006" name="Research Agent for Research Tasks">
  <trigger>Task involves web search, fact verification, external info</trigger>
  <condition>research-agent spawned (not direct WebSearch/WebFetch)</condition>
  <action>Log warning. Consider spawning research-agent.</action>
</rule>

<rule id="RULE-007" name="Security Agent for Security Tasks">
  <trigger>Task involves auth, user input, sensitive data, DB queries</trigger>
  <condition>security-agent spawned or explicitly consulted</condition>
  <action>Log warning. Add security-agent to plan.</action>
  <triggers-list>
    <item>Authentication/authorization</item>
    <item>User input handling</item>
    <item>Sensitive data processing</item>
    <item>Database queries</item>
    <item>HTTP requests to external services</item>
    <item>File system operations</item>
    <item>Payment processing</item>
  </triggers-list>
</rule>

<rule id="RULE-008" name="Token Efficient Agent Spawning">
  <trigger>When spawning any agent via Task tool</trigger>
  <condition>Agent prompt instructs to READ files, not paste content</condition>
  <action>Rewrite prompt to use READ pattern.</action>
  <correct-pattern><![CDATA[
## Your Role
You are [agent-name]. READ agents/[agent-name].md for your definition.

## Your Knowledge
READ knowledge/[topic].md for domain expertise.
  ]]></correct-pattern>
</rule>

<rule id="RULE-009" name="Browser URL Access Policy">
  <trigger>Before any browser navigation via Playwright MCP</trigger>
  <condition>URL matches access policy</condition>
  <action>Ask user before navigating to external URLs.</action>
  <auto-allowed>
    <pattern>localhost:*</pattern>
    <pattern>127.0.0.1:*</pattern>
    <pattern>b2clogin.com</pattern>
    <pattern>auth0.com</pattern>
  </auto-allowed>
  <requires-permission>
    <item>Production URLs</item>
    <item>External domains</item>
  </requires-permission>
</rule>

<rule id="RULE-011" name="Windows File Edit Resilience">
  <trigger>Edit/Write tool fails with "unexpectedly modified" error</trigger>
  <condition>On Windows platform</condition>
  <action>Retry with workarounds.</action>
  <workaround-priority>
    <step order="1">Use relative paths</step>
    <step order="2">Read immediately before edit</step>
    <step order="3">Fall back to Bash commands</step>
    <step order="4">Create new file + rename</step>
  </workaround-priority>
</rule>

<rule id="RULE-013" name="Model Selection for Agents">
  <trigger>When spawning any agent via Task tool</trigger>
  <condition>Model explicitly specified AND matches criteria</condition>
  <action>Apply decision tree, specify model in Task call.</action>
  <always-opus>
    <agent>architect-agent</agent>
    <agent>ticket-analyst-agent</agent>
    <agent>reviewer-agent</agent>
  </always-opus>
  <default>sonnet</default>
  <opus-escalation-triggers>
    <trigger>4+ domains in Planning Checklist</trigger>
    <trigger>10+ subtasks identified</trigger>
    <trigger>Production/payment/auth code</trigger>
    <trigger>Agent reports LOW confidence or BLOCKED</trigger>
  </opus-escalation-triggers>
</rule>

<rule id="RULE-018" name="Parallel Agent Limits">
  <trigger>Before spawning 2+ agents in parallel</trigger>
  <condition>Context usage allows parallel execution</condition>
  <action>Check context, batch if needed, compact between batches</action>
  <escalates-to>BLOCK if context exhaustion occurs</escalates-to>
  <context-thresholds>
    <threshold usage="< 50%" max-parallel="3">Proceed normally</threshold>
    <threshold usage="50-75%" max-parallel="2">Consider /compact first</threshold>
    <threshold usage="> 75%" max-parallel="1">Run sequentially, no parallel</threshold>
  </context-thresholds>
  <batching-protocol>
    <step order="1">Split into batches of 3 agents max</step>
    <step order="2">Run Batch 1 → Wait → Update context.md</step>
    <step order="3">Run /compact with progress preservation</step>
    <step order="4">Run Batch 2 → Wait → Update</step>
    <step order="5">Repeat until all batches complete</step>
    <step order="6">Synthesize final results</step>
  </batching-protocol>
  <token-estimation>
    <item tokens="500-1000">Agent spawn prompt</item>
    <item tokens="1000-2000">Agent output (simple)</item>
    <item tokens="2000-5000">Agent output (with code)</item>
    <item tokens="1000-3000">File read</item>
  </token-estimation>
  <ref>knowledge/memory-management.md</ref>
</rule>

</rules>

<quick-compliance-check>
  <check rule="RULE-001">Am I editing code without an agent?</check>
  <check rule="RULE-002">Multi-step task without TodoWrite?</check>
  <check rule="RULE-003">Spawning agent without planning?</check>
  <check rule="RULE-004">Agent missing status field?</check>
  <check rule="RULE-005">Did I update context.md?</check>
  <check rule="RULE-006">Research task without research-agent?</check>
  <check rule="RULE-007">Security task without security-agent?</check>
  <check rule="RULE-016">Code changes without critique/teaching?</check>
  <check rule="RULE-017">Code changes without standards compliance?</check>
  <check rule="RULE-018">Spawning 4+ agents without batching?</check>
</quick-compliance-check>

</knowledge-base>
