# Error Recovery & Self-Healing Protocol

<knowledge-base name="error-recovery" version="1.0">
<triggers>error, failure, stuck, blocked, retry, recovery, debug, self-healing</triggers>
<overview>Structured error recovery with root cause analysis achieves 24% higher accuracy than ad-hoc debugging. AgentDebug pattern for systematic failure recovery.</overview>

<error-taxonomy>
  <level id="1" name="Memory Errors">
    <error type="Context Overflow" symptoms="Forgetting context, repeating work" recovery="Checkpoint + compact + resume"/>
    <error type="Stale Reference" symptoms="Acting on outdated info" recovery="Re-read source files"/>
    <error type="Lost Handoff" symptoms="Missing context from previous agent" recovery="Re-read workspace context.md"/>
    <error type="Assumption Drift" symptoms="Incorrect assumptions" recovery="Verify assumptions explicitly"/>
  </level>
  <level id="2" name="Reflection Errors">
    <error type="Premature Completion" symptoms="Done before criteria met" recovery="Run verification commands"/>
    <error type="Scope Creep" symptoms="Doing more than asked" recovery="Re-read original task"/>
    <error type="Confidence Miscalibration" symptoms="HIGH confidence on uncertain output" recovery="Force self-reflection"/>
    <error type="Missing Self-Check" symptoms="No verification performed" recovery="Run self-reflection protocol"/>
  </level>
  <level id="3" name="Planning Errors">
    <error type="Task Misunderstanding" symptoms="Wrong interpretation" recovery="Ask user for clarification"/>
    <error type="Bad Decomposition" symptoms="Subtasks don't cover full task" recovery="Re-decompose with completeness check"/>
    <error type="Wrong Agent Selection" symptoms="Agent lacks expertise" recovery="Re-route to correct agent"/>
    <error type="Missing Dependencies" symptoms="Steps in wrong order" recovery="Rebuild dependency graph"/>
  </level>
  <level id="4" name="Action Errors">
    <error type="Tool Failure" symptoms="Command returns error" recovery="Parse error, adjust, retry"/>
    <error type="File Not Found" symptoms="Expected file missing" recovery="Search alternate locations"/>
    <error type="Permission Denied" symptoms="Can't access resource" recovery="Ask user for permissions"/>
    <error type="Syntax Error" symptoms="Code doesn't compile" recovery="Review and fix syntax"/>
  </level>
  <level id="5" name="System Errors">
    <error type="Token Exhaustion" symptoms="Near context limit" recovery="Force checkpoint + compact"/>
    <error type="Rate Limiting" symptoms="API throttling" recovery="Wait + retry with backoff"/>
    <error type="External Service Down" symptoms="API unavailable" recovery="Log + continue other work"/>
    <error type="Environment Mismatch" symptoms="Different from expected" recovery="Verify environment state"/>
  </level>
</error-taxonomy>

<detect-decide-act>
  <step name="Detect">
    <check>Did the last action succeed? (check return code/output)</check>
    <check>Does output match expected format?</check>
    <check>Are there error messages in output?</check>
    <check>Is progress being made? (not stuck in loop)</check>
    <check>Is confidence level appropriate? (not guessing)</check>
  </step>
  <step name="Decide">
    <classification>What level is the error?</classification>
    <route level="1">Memory → Context recovery actions</route>
    <route level="2">Reflection → Self-check actions</route>
    <route level="3">Planning → Re-planning actions</route>
    <route level="4">Action → Retry/adjust actions</route>
    <route level="5">System → Infrastructure actions</route>
  </step>
  <step name="Act">
    <log>Error Detected: [description], Classification: [Level-Type], Recovery Action: [what], Result: [success/blocked]</log>
  </step>
</detect-decide-act>

<recovery-protocols>
  <protocol name="Context Recovery" level="1">
    <step>Checkpoint current state to workspace/[task-id]/context.md</step>
    <step>Re-read all Key Files mentioned in context.md</step>
    <step>Verify current understanding matches file contents</step>
    <step>Update Quick Resume with current accurate state</step>
    <step>Resume from verified state</step>
  </protocol>
  <protocol name="Self-Check Recovery" level="2">
    <step>STOP current action</step>
    <step>Run full self-reflection checklist</step>
    <step>Identify specific failure point</step>
    <step>If confidence &lt; MEDIUM → Report NEEDS_INPUT</step>
    <step>If confidence >= MEDIUM → Proceed with corrections</step>
  </protocol>
  <protocol name="Re-Planning Recovery" level="3">
    <step>Re-read original user request</step>
    <step>Compare current approach to request</step>
    <step>If misaligned → Create new plan</step>
    <step>If unclear → Ask user via AskUserQuestion</step>
    <step>Update context.md with corrected plan</step>
  </protocol>
  <protocol name="Action Recovery" level="4">
    <step>Parse error message for root cause</step>
    <step>Search for similar errors in codebase</step>
    <step>Adjust command/approach</step>
    <step>Retry with adjustment</step>
    <step>If fails 3x → Escalate to different approach</step>
  </protocol>
  <protocol name="System Recovery" level="5">
    <step>Log system error with timestamp</step>
    <step>Checkpoint all progress</step>
    <step>If token exhaustion → Allow compaction</step>
    <step>If external service → Queue for later or skip</step>
    <step>Continue with available resources</step>
  </protocol>
</recovery-protocols>

<escalation-matrix>
  <escalation attempts="1">Retry with same approach</escalation>
  <escalation attempts="2">Adjust approach slightly</escalation>
  <escalation attempts="3">Try different approach entirely</escalation>
  <escalation attempts="4">Ask user for guidance</escalation>
  <escalation attempts="5+">Mark BLOCKED, document fully</escalation>
</escalation-matrix>

<model-escalation>
  <escalate from="haiku" to="sonnet" trigger="Complex reasoning needed"/>
  <escalate from="sonnet" to="opus" trigger="Architectural decisions, critical analysis"/>
  <escalate from="opus" to="user" trigger="Still stuck after opus attempt"/>
</model-escalation>

<anti-patterns>
  <anti-pattern name="Retry Without Analysis">
    <bad>Command failed → run same command again</bad>
    <good>Command failed → analyze error → adjust → retry</good>
  </anti-pattern>
  <anti-pattern name="Ignore Warnings">
    <bad>Warnings in output → proceed anyway</bad>
    <good>Warnings → assess severity → address if significant</good>
  </anti-pattern>
  <anti-pattern name="Assume Transient">
    <bad>Error occurred → assume temporary → move on</bad>
    <good>Error occurred → verify root cause → fix root cause</good>
  </anti-pattern>
</anti-patterns>

<metrics>
  <metric name="Recovery Rate" target=">80%">Errors resolved without escalation</metric>
  <metric name="First-Try Success" target=">90%">Actions succeed on first attempt</metric>
  <metric name="BLOCKED Rate" target="&lt;10%">Tasks requiring user intervention</metric>
  <metric name="False COMPLETE" target="0%">COMPLETE reported but task incomplete</metric>
</metrics>

</knowledge-base>
