# Memory & Context Management Knowledge Base

<knowledge-base name="memory-management" version="1.0">
<triggers>memory, context, compact, compaction, session, persist, remember, forget, context window</triggers>
<overview>Strategies for preserving critical context across compaction events and sessions. Claude auto-compacts at ~95% capacity.</overview>

<compaction>
  <trigger-points>
    <trigger type="auto">~95% context capacity</trigger>
    <trigger type="manual">/compact command</trigger>
    <trigger type="clear">/clear resets conversation</trigger>
  </trigger-points>

  <process>
    <step order="1">Analyze entire conversation history</step>
    <step order="2">Create summary: accomplished, in-progress, files, next steps, constraints</step>
    <step order="3">Summary replaces old messages</step>
    <step order="4">Session continues with preserved context</step>
  </process>

  <survives>
    <item>CLAUDE.md files (loaded fresh each session)</item>
    <item>workspace/[task-id]/context.md (task state)</item>
    <item>Git history</item>
    <item>All files on disk</item>
  </survives>

  <does-not-survive>
    <item>Detailed conversation history (summarized)</item>
    <item>Working memory of file contents</item>
    <item>Agent's "knowledge" of discussed topics</item>
    <item>Nuanced instructions from early conversation</item>
  </does-not-survive>

  <hints>
    <hint>/compact preserve the agent decisions and task status</hint>
    <hint>/compact keep the architectural decisions we made</hint>
    <hint>/compact focus on the current implementation plan</hint>
  </hints>
</compaction>

<memory-hierarchy>
  <level rank="1" name="Enterprise" location="Org-wide policy" scope="All teams" loaded="Always"/>
  <level rank="2" name="Project" location="./CLAUDE.md" scope="Team/shared" loaded="Always"/>
  <level rank="3" name="User" location="~/.claude/CLAUDE.md" scope="Your projects" loaded="Always"/>
  <level rank="4" name="Local" location="./CLAUDE.local.md" scope="Personal" loaded="Always"/>
  <level rank="5" name="Task" location="workspace/[task-id]/context.md" scope="Per-task" loaded="On access"/>
</memory-hierarchy>

<persistence-strategies>

  <strategy id="claude-md-optimization">
    <rule>Keep it minimal but reference-rich (&lt; 500 lines)</rule>
    <include>Critical non-negotiables only</include>
    <include>One-liner quick references</include>
    <include>File structure overview</include>
    <include>@imports to extended context</include>
    <antipattern>Entire documentation</antipattern>
    <antipattern>Code examples (put in knowledge/)</antipattern>
    <antipattern>Conversation history</antipattern>
  </strategy>

  <strategy id="task-context" critical="true">
    <location>workspace/[task-id]/context.md</location>
    <required-sections>
      <section name="Quick Resume">1-2 sentences: task and current status</section>
      <section name="Status">ACTIVE/BLOCKED/COMPLETE</section>
      <section name="Key Files">List for quick re-reading</section>
      <section name="Agent Contributions">What each agent discovered/produced</section>
      <section name="Next Steps">What to do when resuming</section>
    </required-sections>
  </strategy>

  <strategy id="milestone-updates">
    <action>Update task context.md after each significant milestone</action>
    <action>Ensure Next Steps are current</action>
    <recovery-flow>
      <step>Read CLAUDE.md (always loaded)</step>
      <step>List workspace/ folders for active tasks</step>
      <step>Read relevant task context.md</step>
      <step>Resume with full understanding</step>
    </recovery-flow>
  </strategy>

</persistence-strategies>

<session-recovery-protocol>
  <step order="1">Read CLAUDE.md (automatic)</step>
  <step order="2">List workspace/ folders to find active tasks</step>
  <step order="3">For each active task: Read context.md, re-read key files</step>
  <step order="4">Resume from recorded "Next Steps"</step>
</session-recovery-protocol>

<persistent-mode description="For tasks that auto-continue until criteria met">

  <examples>
    <example>Convert all files to TypeScript</example>
    <example>Test until 90% coverage</example>
    <example>Refactor entire module</example>
  </examples>

  <checkpoint-triggers>
    <trigger>Every N items (default: 10)</trigger>
    <trigger>Before large operations (&gt;5K tokens)</trigger>
    <trigger>At ~75% token capacity</trigger>
    <trigger>After completing logical phase</trigger>
  </checkpoint-triggers>

  <checkpoint-content><![CDATA[
## Execution Mode
- **Mode**: PERSISTENT
- **Set At**: [timestamp]

### Completion Criteria
| # | Criterion | Verification Command | Threshold | Status |
|---|-----------|---------------------|-----------|--------|

### Progress Tracker
- **Items Total**: [n]
- **Items Completed**: [n]
- **Completion %**: [n%]
- **Next Item**: [path]
]]></checkpoint-content>

  <quick-resume-format><![CDATA[
## Quick Resume
**MODE: PERSISTENT** | Progress: 23/45 files | Next: Convert src/utils/crypto.js
Criteria: [1] All .js -> .ts [NOT MET: 22 remaining] [2] tsc passes [NOT MET]
]]></quick-resume-format>

  <recovery-flow>
    <step order="1">DO NOT ask user whether to continue</step>
    <step order="2">Read Quick Resume for current state</step>
    <step order="3">Run verification commands to validate progress</step>
    <step order="4">Compare actual vs stored (investigate discrepancies)</step>
    <step order="5">Continue from Next Item automatically</step>
  </recovery-flow>

  <safeguards>
    <safeguard name="Infinite Loop Prevention">If same item processed 3+ times: BLOCKED, wait for user</safeguard>
    <safeguard name="Progress Stall Detection">If 10+ iterations with no progress: ask user</safeguard>
    <safeguard name="Max Iterations">Optional limit in context.md: Max Iterations: 100</safeguard>
  </safeguards>

</persistent-mode>

<parallel-agent-limits critical="true">

  <problem>Too many parallel agents exhausts context, causing "Conversation too long" error</problem>

  <hard-limits>
    <limit scenario="Simple tasks" max-parallel="3" action="Batch into groups of 3"/>
    <limit scenario="Complex tasks" max-parallel="2" action="Run sequentially"/>
    <limit scenario="Low context (&gt;75% used)" max-parallel="1" action="Run sequentially"/>
  </hard-limits>

  <pre-spawn-check>
    <rule condition="context &gt; 50%">/compact FIRST</rule>
    <rule condition="context &gt; 75%">Run agents sequentially, not parallel</rule>
    <rule condition="spawning 4+ agents">Split into batches with /compact between</rule>
  </pre-spawn-check>

  <batch-pattern><![CDATA[
WRONG: Spawn all 6 agents parallel → Context explosion → /compact fails

RIGHT (batched):
  Batch 1: Spawn 3 agents → Wait → Collect → Update context.md
  /compact (preserving progress)
  Batch 2: Spawn 3 agents → Wait → Collect → Update context.md
  Synthesize
]]></batch-pattern>

  <background-agents advantages="Doesn't block context, can check incrementally, allows compaction">
    <pattern>
      <step>Spawn with run_in_background: true</step>
      <step>Continue with other work</step>
      <step>Periodically check with TaskOutput (block: false)</step>
      <step>When complete, fetch full results</step>
      <step>Update context.md</step>
    </pattern>
  </background-agents>

  <emergency-recovery>
    <step order="1">Press Esc twice to go back</step>
    <step order="2">Delete most recent large messages</step>
    <step order="3">Run /compact with context hints</step>
    <step order="4">Resume from context.md state</step>
    <step order="5">Use sequential agents instead</step>
  </emergency-recovery>

  <token-estimation>
    <item action="Agent spawn prompt" tokens="500-1000"/>
    <item action="Agent output (simple)" tokens="1000-2000"/>
    <item action="Agent output (code)" tokens="2000-5000"/>
    <item action="File read (medium)" tokens="1000-3000"/>
    <item action="Large code block" tokens="2000-4000"/>
  </token-estimation>

  <proactive-compact-triggers>
    <trigger>Spawning 3+ agents</trigger>
    <trigger>Starting multi-file refactor</trigger>
    <trigger>Beginning "test everything" task</trigger>
    <trigger>Any task with 5+ subtasks</trigger>
    <trigger>Todo list has 5+ pending items</trigger>
  </proactive-compact-triggers>

</parallel-agent-limits>

<warning-signs description="Take action when you notice:">
  <sign>Claude forgetting earlier decisions</sign>
  <sign>Need to repeat instructions</sign>
  <sign>Claude re-reading files it already read</sign>
  <sign>Confusion about project structure</sign>
  <response>Manually /compact with hints rather than waiting for auto-compact</response>
</warning-signs>

<best-practices>
  <do>Keep CLAUDE.md lean (&lt; 500 lines)</do>
  <do>Update task context.md after each milestone</do>
  <do>Structure context.md for quick resume</do>
  <do>Record Next Steps explicitly</do>
  <do>Include file paths in all notes</do>
  <do>Use workspace/ folders for task isolation</do>
  <dont>Store conversation history in files</dont>
  <dont>Include full code in CLAUDE.md</dont>
  <dont>Rely on conversation memory for critical info</dont>
  <dont>Forget to update task status</dont>
  <dont>Use vague descriptions ("the thing we discussed")</dont>
</best-practices>

<recovery-checklist>
  <item>CLAUDE.md loads automatically</item>
  <item>List workspace/ folders to find active tasks</item>
  <item>Read context.md for each active task</item>
  <item>Re-read files mentioned in Key Files</item>
  <item>Review Next Steps for each task</item>
  <item>Continue from documented state</item>
</recovery-checklist>

</knowledge-base>
