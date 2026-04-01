# Model Selection Knowledge Base

<knowledge-base name="model-selection" version="1.0">
<triggers>model, opus, sonnet, haiku, escalate, complexity, which model</triggers>
<overview>Two-tier model selection: Sonnet (default for 15 agents), Opus (critical checkpoints and complex reasoning). Priority: Quality > Accuracy > Token Cost.</overview>

<always-opus count="3">
  <agent name="architect-agent" rationale="Design decisions cascade everywhere - bad architecture propagates through entire codebase"/>
  <agent name="ticket-analyst-agent" rationale="Wrong understanding = building wrong thing entirely - first step errors cascade"/>
  <agent name="reviewer-agent" rationale="Final quality gate before shipping - catches architecture, security, subtle bugs"/>
</always-opus>

<default-sonnet count="15">
  <agent name="test-agent" notes="Escalate for complex mocking strategies"/>
  <agent name="debug-agent" notes="Escalate for architectural bugs"/>
  <agent name="workflow-agent" notes="Escalate for complex integrations"/>
  <agent name="docs-agent"/>
  <agent name="refactor-agent" notes="Escalate for large-scale refactors"/>
  <agent name="research-agent"/>
  <agent name="explore-agent"/>
  <agent name="estimator-agent"/>
  <agent name="ui-agent"/>
  <agent name="performance-agent" notes="Escalate for system-wide optimization"/>
  <agent name="security-agent" notes="Escalate for auth/payment logic"/>
  <agent name="browser-agent"/>
  <agent name="evaluator-agent"/>
  <agent name="teacher-agent"/>
  <agent name="compliance-agent"/>
</default-sonnet>

<decision-tree><![CDATA[
Task arrives
    │
    ▼
Is agent architect/ticket-analyst/reviewer?
    ├─ YES → Use Opus
    └─ NO → Check Opus Escalation Triggers
              ├─ ANY trigger matched? → Use Opus
              └─ No triggers → Use Sonnet (default)
]]></decision-tree>

<opus-escalation-triggers>
  <trigger category="Agent Type">architect-agent, ticket-analyst-agent, reviewer-agent</trigger>

  <trigger category="Complexity">
    <condition>4+ domains in Planning Checklist</condition>
    <condition>10+ subtasks decomposed</condition>
    <condition>Multi-file architectural changes</condition>
    <condition>Cross-cutting concerns (logging, auth, caching across modules)</condition>
  </trigger>

  <trigger category="Stakes">
    <condition>Production deployment or live system</condition>
    <condition>Payment processing logic</condition>
    <condition>Authentication/authorization code</condition>
    <condition>Sensitive data handling (PII, credentials, secrets)</condition>
    <condition>Security-critical paths</condition>
  </trigger>

  <trigger category="Ambiguity">
    <condition>Vague requirements ("make it better", "improve performance")</condition>
    <condition>Conflicting constraints requiring trade-offs</condition>
    <condition>Architectural decisions with long-term implications</condition>
  </trigger>

  <trigger category="Reasoning Depth">
    <condition>Multi-step autonomous decision chains</condition>
    <condition>Complex debugging requiring system-wide understanding</condition>
    <condition>Design pattern selection with trade-offs</condition>
  </trigger>

  <trigger category="Mid-Task Escalation">
    <condition>Agent reports Confidence: LOW on critical subtask</condition>
    <condition>Agent reports Status: BLOCKED with capability reason</condition>
    <condition>Multiple failed tool calls (>3) on same operation</condition>
    <condition>Agent explicitly requests deeper reasoning</condition>
  </trigger>
</opus-escalation-triggers>

<complexity-scoring purpose="Edge cases when escalation decision is unclear">
  <dimension name="Domains" sonnet="1-3 domains" opus="4+ domains"/>
  <dimension name="Subtasks" sonnet="1-9 subtasks" opus="10+ subtasks"/>
  <dimension name="Ambiguity" sonnet="Clear requirements" opus="Vague/interpretive"/>
  <dimension name="Stakes" sonnet="Dev/test environment" opus="Production/sensitive"/>
  <dimension name="Reasoning" sonnet="Linear/sequential" opus="Multi-step autonomous"/>
  <threshold opus="Total 8+" sonnet="Total 5-7"/>
  <override>Always-Opus agents use Opus regardless of score</override>
</complexity-scoring>

<mid-task-escalation>
  <scenario name="LOW Confidence on Critical Path">
    <condition>Agent self-reflection reports LOW confidence</condition>
    <condition>Subtask is on critical path (not exploratory)</condition>
    <action>Retry same subtask with Opus</action>
  </scenario>
  <scenario name="BLOCKED with Capability Issue">
    <condition>Status: BLOCKED</condition>
    <condition>Reason suggests reasoning limitation</condition>
    <action>Spawn Opus agent for same task</action>
  </scenario>
  <scenario name="Repeated Failures">
    <condition>Same tool call fails 3+ times</condition>
    <condition>Failures suggest reasoning issue</condition>
    <action>Escalate to Opus</action>
  </scenario>
  <scenario name="Explicit Request">
    <condition>Agent output includes: "This task may benefit from deeper reasoning"</condition>
    <action>Honor the request, spawn Opus</action>
  </scenario>
</mid-task-escalation>

<model-characteristics>
  <model name="Opus" strength="Deep reasoning, complex analysis, nuanced judgment">
    <best-for>Architecture, requirements, final review, high-stakes</best-for>
    <avoid-for>High-volume simple tasks</avoid-for>
  </model>
  <model name="Sonnet" strength="Balanced intelligence, strong coding, efficient">
    <best-for>Implementation, testing, debugging, documentation</best-for>
    <avoid-for>Tasks requiring deep architectural reasoning</avoid-for>
  </model>
  <context-note>Both support 200K context; Sonnet has 1M beta; for >100K tokens, prefer Opus for synthesis</context-note>
</model-characteristics>

<anti-patterns>
  <anti-pattern name="Use Opus to be safe" problem="Wastes usage" fix="Follow decision tree"/>
  <anti-pattern name="Sonnet for everything" problem="Misses quality benefits" fix="Always-Opus agents exist for a reason"/>
  <anti-pattern name="No visibility into usage" problem="Can't optimize" fix="Track in context.md"/>
  <anti-pattern name="Ignoring escalation signals" problem="Agent confidence exists for a reason" fix="Honor LOW/BLOCKED"/>
</anti-patterns>

<integration>
  <step phase="Planning">Identify agents, apply decision tree, document in context.md</step>
  <step phase="Spawning">Include model: "opus" or "sonnet" parameter in Task tool</step>
  <step phase="Monitoring">Watch for escalation triggers, update context.md if escalation</step>
</integration>

</knowledge-base>
