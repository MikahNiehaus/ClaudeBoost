# Multi-Agent System Failure Patterns

<knowledge-base name="multi-agent-failures" version="1.0">
<triggers>multi-agent, failure, cascade, coordination, misalignment, handoff failure, agent conflict</triggers>
<overview>Multi-agent systems have 14 unique failure modes in 4 categories (MAST taxonomy from 1600+ traces). Understanding prevents cascading failures.</overview>

<mast-taxonomy>
  <category id="1" name="System Design Issues" percent="32%">
    <failure mode="Unclear Specification" description="Agent role/boundaries ambiguous" prevention="Explicit JSON schemas for inputs/outputs"/>
    <failure mode="Missing Context" description="Agent lacks info to decide" prevention="Require context.md reading before action"/>
    <failure mode="Wrong Agent Selection" description="Task routed to wrong expertise" prevention="Explicit routing table in _orchestrator.md"/>
    <failure mode="Scope Creep" description="Agent does more than assigned" prevention="Define explicit boundaries in agent definition"/>
    <failure mode="Overlapping Responsibilities" description="Multiple agents claim same work" prevention="Clear domain ownership in collaboration matrix"/>
  </category>

  <category id="2" name="Inter-Agent Misalignment" percent="28%" most-common="true">
    <failure mode="Communication Mismatch" description="Output format doesn't match expected input" prevention="Standardize format in _shared-output.md"/>
    <failure mode="Lost Handoff" description="Context dropped between agents" prevention="Mandatory context.md updates"/>
    <failure mode="Duplicate Effort" description="Agents redo each other's work" prevention="Parallel Findings table"/>
    <failure mode="Conflicting Actions" description="Agents make incompatible changes" prevention="Conflict resolution rules"/>
    <failure mode="Responsibility Amnesia" description="Agent forgets role mid-task" prevention="Constitutional principles in spawn prompt"/>
  </category>

  <category id="3" name="Task Verification Gaps" percent="24%">
    <failure mode="Premature Completion" description="Task marked done before criteria met" prevention="Evaluator-agent quality gate"/>
    <failure mode="Missing Validation" description="Output not verified" prevention="Pre-completion verification protocol"/>
    <failure mode="Acceptance Criteria Drift" description="Final doesn't match original" prevention="Re-read original task before completion"/>
    <failure mode="Silent Failures" description="Errors hidden or ignored" prevention="Mandatory error reporting in status"/>
  </category>

  <category id="4" name="Infrastructure Issues" percent="16%">
    <failure mode="Token Exhaustion" description="Context window overflow" prevention="Checkpoint protocol, scratchpad pattern"/>
    <failure mode="Rate Limiting" description="API throttling" prevention="Retry with exponential backoff"/>
    <failure mode="Timeout" description="Long operations exceed limits" prevention="Break into smaller operations"/>
    <failure mode="Tool Errors" description="Tool execution failures" prevention="Error recovery protocol"/>
  </category>
</mast-taxonomy>

<error-cascading>
  <pattern><![CDATA[
Agent A makes error
    ↓
Agent B receives bad output
    ↓
Agent B builds on bad output (compounds error)
    ↓
Agent C receives even worse output
    ↓
Final output is catastrophically wrong
]]></pattern>

  <prevention name="Validation at Boundaries">
    <check>Output format matches expected schema?</check>
    <check>All required fields present?</check>
    <check>Values within expected ranges?</check>
    <check>No obvious errors in reasoning?</check>
    <rule>If ANY check fails → Report BLOCKED, don't propagate error</rule>
  </prevention>

  <prevention name="Error Isolation">
    <step>STOP processing immediately</step>
    <step>Log error with full context</step>
    <step>DO NOT pass error downstream</step>
    <step>Report BLOCKED with specifics</step>
    <step>Wait for orchestrator to resolve</step>
  </prevention>

  <prevention name="Result Validation">
    <step>Re-read original requirements</step>
    <step>Compare output against requirements</step>
    <step>Run verification commands</step>
    <step>Check for inconsistencies</step>
    <step>Self-reflect on confidence</step>
  </prevention>
</error-cascading>

<conflict-resolution>
  <rule priority="1">Security vs Performance: Security wins</rule>
  <rule priority="2">Correctness vs Speed: Correctness wins</rule>
  <rule priority="3">Multiple Valid Approaches: Present options to user</rule>
  <rule priority="4">Unclear Priority: Ask user for guidance</rule>
</conflict-resolution>

<anti-patterns>
  <anti-pattern name="Over-Engineering">
    <bad>Building "self-reflecting autonomous super-duper agents" for simple problems</bad>
    <good>Start simple, add complexity only when needed. Single-threaded loop + good tools = reliable agents</good>
  </anti-pattern>
  <anti-pattern name="Prototype as Production">
    <bad>"The prototype works, let's ship it!" (optimized for speed, not resilience)</bad>
    <good>Redesign for production: Decomposition, Observability, Testing, Error handling</good>
  </anti-pattern>
  <anti-pattern name="Ignoring Hallucinations">
    <bad>Assuming 5% hallucination rate is acceptable (errors compound)</bad>
    <good>Validate all outputs, use evaluator-agent, require confidence scores</good>
  </anti-pattern>
  <anti-pattern name="Implicit Contracts">
    <bad>Agent A expects JSON, Agent B outputs markdown, no one documented interface</bad>
    <good>Explicit schema definitions, standardized output formats, validation at boundaries</good>
  </anti-pattern>
</anti-patterns>

<recovery-patterns>
  <pattern name="Checkpoint and Restart">
    <step>Stop all agents</step>
    <step>Identify cascade origin point</step>
    <step>Load last good checkpoint</step>
    <step>Fix root cause</step>
    <step>Resume from checkpoint</step>
  </pattern>
  <pattern name="Graceful Degradation">
    <step>Isolate failure (don't propagate)</step>
    <step>Try simpler fallback approach</step>
    <step>If fallback fails → Human escalation</step>
    <step>Never continue with broken state</step>
  </pattern>
  <pattern name="Human-in-the-Loop Gate">
    <step>Agent proposes action</step>
    <step>Present to user for approval</step>
    <step>Only execute if approved</step>
    <step>Log decision for audit</step>
  </pattern>
</recovery-patterns>

<health-metrics>
  <metric name="First-try success" healthy=">90%" alert="&lt;80%"/>
  <metric name="BLOCKED rate" healthy="&lt;10%" alert=">20%"/>
  <metric name="Cascade rate" healthy="&lt;2%" alert=">5%"/>
  <metric name="Human escalation" healthy="&lt;5%" alert=">15%"/>
</health-metrics>

</knowledge-base>
