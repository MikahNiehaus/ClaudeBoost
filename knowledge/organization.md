# Workspace Organization

<knowledge-base name="organization" version="1.0">
<triggers>organize, workspace, task folder, artifact, snapshot, context</triggers>
<overview>All task-related artifacts organized in workspace/ folder using task-specific subfolders. Each task has isolated context for agent collaboration.</overview>

<critical-rule name="XML Format Required">
  <instruction>ALL workspace context.md files MUST use XML structured tags for AI-efficient parsing</instruction>
  <rationale>XML provides semantic structure, reduces ambiguity, enables attribute lookup</rationale>
  <format>Use knowledge-base wrapper with triggers and structured content sections</format>
</critical-rule>

<folder-structure><![CDATA[
workspace/
└── [task-id]/
    ├── ticket.md      # Verbatim original ticket/requirement (IMMUTABLE after creation)
    ├── mockups/       # Design references, input images, specifications
    ├── outputs/       # Generated artifacts, final deliverables
    ├── snapshots/     # Screenshots, progress captures, debugging images
    └── context.md     # Task context, notes, agent contributions, handoffs
]]></folder-structure>

<task-id-naming>
  <priority-order>
    <priority rank="1" name="Ticket Number (PRIMARY DEFAULT)">
      <rule>ALWAYS use ticket number when available - this is the DEFAULT</rule>
      <formats>ASC-914, JIRA-123, GH-456, BUG-789, TICKET-001</formats>
      <ask-user>If task seems related to a ticket, ASK user for ticket number first</ask-user>
    </priority>
    <priority rank="2" name="Date-Based (FALLBACK ONLY)">
      <rule>ONLY use when NO ticket number exists</rule>
      <format>YYYY-MM-DD-short-description (2-4 words, lowercase, hyphen-separated)</format>
      <examples>2026-01-08-auth-refactor, 2026-01-08-fix-login-bug</examples>
    </priority>
  </priority-order>
  <decision-flow><![CDATA[
  [New Task] → Has ticket number in request?
                │
           YES  │  NO
            ▼   │   ▼
  Use ticket    │  Ask: "Is this related to a ticket?"
  (ASC-123)     │       │
                │  YES  │  NO
                │   ▼   │   ▼
                │  Get  │  Use date-based
                │  #    │  (YYYY-MM-DD-desc)
  ]]></decision-flow>
</task-id-naming>

<folder-contents>
  <folder name="mockups">Design mockups, wireframes, UI specs, reference images, input files</folder>
  <folder name="outputs">Generated code, final deliverables, exported reports, completed artifacts</folder>
  <folder name="snapshots">Screenshots during testing, progress captures, debugging images, before/after comparisons</folder>
  <folder name="ticket.md">Verbatim copy of original ticket/requirement pasted by user. NEVER modified after creation. Single source of truth for all agents. All references to requirements MUST use exact wording from this file.</folder>
  <folder name="context.md">Task status, notes, findings, agent contributions, handoffs, open questions, session history</folder>
</folder-contents>

<context-template format="XML"><![CDATA[
# Task: [Task ID]

<task-context task-id="[ID]" created="[YYYY-MM-DD]" updated="[YYYY-MM-DD]">

<quick-resume>
[1-2 sentences: Current state for session recovery after compaction]
NORMAL: "Implementing auth refactor. debug-agent found root cause in token.ts:45, waiting for test-agent."
PERSISTENT: "**MODE: PERSISTENT** | Progress: 23/45 files | Next: Convert src/services/auth.js | Criteria: [1] All .js -> .ts [NOT MET: 22 remaining]"
</quick-resume>

<status>
  <state>[PLANNING/ACTIVE/BLOCKED/COMPLETE]</state>
  <phase>[Planning | Execution | Review]</phase>
  <last-agent>[Most recent agent]</last-agent>
</status>

<execution-mode>
  <mode>[NORMAL/PERSISTENT]</mode>
  <set-by>[User request / Auto-detected from patterns: "all", "until", "entire", "every", "complete"]</set-by>

  <!-- PERSISTENT mode only -->
  <completion-criteria>
    <criterion id="1" verification="[command]" threshold="[value]" status="[pending/met/failed]">[description]</criterion>
  </completion-criteria>

  <progress-tracker>
    <total>[N or "counting..."]</total>
    <completed>[M]</completed>
    <percentage>[M/N * 100]%</percentage>
    <last-checkpoint>[Timestamp]</last-checkpoint>
    <last-item>[e.g., src/utils/auth.js]</last-item>
    <next-item>[e.g., src/utils/crypto.js]</next-item>
  </progress-tracker>
</execution-mode>

<plan>
  <planning-checklist>
    <domain name="Testing" needed="[Yes/No]" criteria="[specific]" agent="test-agent"/>
    <domain name="Documentation" needed="[Yes/No]" criteria="[specific]" agent="docs-agent"/>
    <domain name="Security" needed="[Yes/No]" criteria="[specific]" agent="security-agent"/>
    <domain name="Architecture" needed="[Yes/No]" criteria="[specific]" agent="architect-agent"/>
    <domain name="Performance" needed="[Yes/No]" criteria="[specific]" agent="performance-agent"/>
    <domain name="Review" needed="[Yes/No]" criteria="[specific]" agent="reviewer-agent"/>
    <domain name="Clarity" needed="[Yes/No]" criteria="[specific]" agent="ticket-analyst-agent"/>
  </planning-checklist>

  <subtasks>
    <subtask id="1" agent="[agent]" dependencies="None" status="[pending/in_progress/complete]">[Name]</subtask>
  </subtasks>

  <execution-strategy pattern="[Sequential | Parallel | Hybrid]">[Rationale]</execution-strategy>

  <model-usage>
    <agent name="[name]" model="[opus/sonnet]" rationale="[why]"/>
    <summary opus="[N agents]" sonnet="[N agents]" escalations="[count and reasons]"/>
  </model-usage>
</plan>

<blocked-resolution if="BLOCKED">
  <blocked-by>[Specific blocker]</blocked-by>
  <to-unblock>[Required action]</to-unblock>
  <owner>[user/specific-agent/external]</owner>
  <attempted>[What has been tried]</attempted>
</blocked-resolution>

<key-files>
  <file path="[path]" reason="[why important]"/>
</key-files>

<ticket-source>
  <has-ticket>[YES/NO]</has-ticket>
  <ticket-file>workspace/[task-id]/ticket.md</ticket-file>
  <reminder>ALL requirement references MUST use EXACT wording from ticket.md</reminder>
</ticket-source>

<task-description>[What this task is about, requirements, goals]</task-description>

<orchestrator-decisions timestamp="[ISO]">
  <user-request>[Original request]</user-request>
  <domains-identified>[testing, debugging, architecture, etc.]</domains-identified>
  <agents-considered>[List all applicable]</agents-considered>
  <agents-spawned>[List spawned and WHY]</agents-spawned>
</orchestrator-decisions>

<notes-findings>[Human notes, discoveries, key decisions]</notes-findings>

<agent-contributions>
  <contribution agent="[Name]" timestamp="[ISO]">
    <task>[What agent was asked to do]</task>
    <status>[COMPLETE/BLOCKED/NEEDS_INPUT]</status>
    <findings>[Main discoveries]</findings>
    <output>[What was produced or path]</output>
    <handoff>[What next agent needs to know]</handoff>
  </contribution>
</agent-contributions>

<parallel-findings>
  <!-- Parallel agents add findings here for real-time visibility -->
  <finding agent="[agent]" impact="[impact]" timestamp="[ISO]">[description]</finding>
</parallel-findings>

<handoff-queue>
  <handoff agent="[agent]" reason="[why]" priority="[P0-P2]"/>
</handoff-queue>

<open-questions>
  <question resolved="false">[Question]</question>
</open-questions>

<next-steps>
  <step order="1">[First thing when resuming]</step>
</next-steps>

<session-history>
  <entry time="[ISO]" agent="[agent]" action="[action]" result="[result]"/>
</session-history>

</task-context>
]]></context-template>

<status-definitions>
  <task-status>
    <status name="PLANNING" meaning="Planning phase in progress" action="Complete checklist, generate plan"/>
    <status name="ACTIVE" meaning="Execution in progress" action="Continue with next steps"/>
    <status name="BLOCKED" meaning="Cannot proceed" action="Check Blocked Resolution section"/>
    <status name="COMPLETE" meaning="Task finished" action="Archive or clean up"/>
  </task-status>
  <agent-status>
    <status name="COMPLETE" meaning="Agent finished successfully" action="Continue to next agent or synthesize"/>
    <status name="BLOCKED" meaning="Cannot proceed" action="Route to unblocking agent or ask user"/>
    <status name="NEEDS_INPUT" meaning="Requires user clarification" action="Present question to user"/>
  </agent-status>
</status-definitions>

<context-lifecycle>
  <create-when>
    <condition>Involves multiple steps</condition>
    <condition>Multiple agents collaborate</condition>
    <condition>Spans multiple sessions</condition>
    <condition>Needs progress tracking</condition>
    <condition>ANY agent is being spawned</condition>
    <condition>ANY code changes</condition>
  </create-when>
  <skip-only-when>
    <condition>Single read-only question</condition>
    <condition>Simple explanation fitting one response</condition>
    <condition>Codebase navigation question</condition>
  </skip-only-when>
  <update-after>
    <trigger>Each agent completes work</trigger>
    <trigger>Key decisions made</trigger>
    <trigger>Status changes</trigger>
    <trigger>Questions arise</trigger>
  </update-after>
</context-lifecycle>

<size-management>
  <limits>
    <limit metric="File size" target="< 30 KB" warning="> 30 KB" action="Archive old contributions"/>
    <limit metric="Agent contributions" target="< 10 active" warning="> 10" action="Move resolved to archive"/>
    <limit metric="Parallel findings" target="< 20 rows" warning="> 20" action="Consolidate into summary"/>
  </limits>
  <keep-active>Current status, unresolved questions, recent contributions (3-5), next steps, key files</keep-active>
  <archive-to>outputs/archive/context-history.md</archive-to>
</size-management>

<quick-resume-protocol mandatory="true">
  <rule>After EVERY agent completes, orchestrator MUST update Quick Resume</rule>
  <format>[agent-name] completed [task] at [HH:MM]. Next: [immediate next action].</format>
  <validation>Quick Resume should NEVER be more than 1 agent behind</validation>
  <triggers>
    <trigger>Immediately after receiving agent status</trigger>
    <trigger>Before spawning next agent</trigger>
    <trigger>Before any user-facing response</trigger>
    <trigger>When status changes to BLOCKED</trigger>
  </triggers>
</quick-resume-protocol>

</knowledge-base>
