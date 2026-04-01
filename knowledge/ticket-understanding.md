# Ticket Understanding Methodology

<knowledge-base name="ticket-understanding" version="1.0">
<triggers>analyze ticket, understand requirements, clarify request, decompose task, vague requirements</triggers>
<overview>37% of project failures stem from unclear requirements. Cost of requirement error increases 100x when discovered in production vs analysis. Uncover the TRUE need beneath the stated want.</overview>

<understanding-levels>
  <level order="1" name="Literal">What did user literally say? Exact words.</level>
  <level order="2" name="Intent">What do they actually want to accomplish? Goal behind request.</level>
  <level order="3" name="Context">Why do they need this? What problem? Who benefits?</level>
  <level order="4" name="Implicit">What did they NOT say but will expect? Standards, patterns, obvious features.</level>
  <level order="5" name="Constraint">What limitations? Time, budget, technology, dependencies.</level>
</understanding-levels>

<exact-wording-rule>
  <rationale>Paraphrasing causes interpretation drift across agents. When Agent A rewrites "filter by date range" as "date filtering functionality", Agent B loses the original precision. Across multiple agents, meaning degrades like a game of telephone.</rationale>

  <examples>
    <example>
      <ticket-says>Users must be able to filter results by date range</ticket-says>
      <wrong>The system should support date filtering functionality</wrong>
      <right>"Users must be able to filter results by date range" (ticket.md)</right>
    </example>
    <example>
      <ticket-says>Display error message when payment fails</ticket-says>
      <wrong>Show feedback for unsuccessful transactions</wrong>
      <right>"Display error message when payment fails" (ticket.md)</right>
    </example>
    <example>
      <ticket-says>Admin can bulk-delete inactive accounts older than 90 days</ticket-says>
      <wrong>Support batch removal of stale user records</wrong>
      <right>"Admin can bulk-delete inactive accounts older than 90 days" (ticket.md)</right>
    </example>
  </examples>

  <self-check-procedure>
    <step order="1">Open workspace/[task-id]/ticket.md</step>
    <step order="2">Find the EXACT sentence in ticket.md that matches the requirement you are referencing</step>
    <step order="3">If your wording differs from ticket.md, REPLACE your wording with the exact ticket text</step>
    <step order="4">If no matching sentence exists in ticket.md, FLAG it as an inferred requirement (not from ticket)</step>
  </self-check-procedure>
</exact-wording-rule>

<chain-of-thought><![CDATA[
## Thinking Through Request: "[Original Request]"

### Step 1: Parse the Request
- Key nouns (objects/entities): [list]
- Key verbs (actions): [list]
- Qualifiers/modifiers: [list]
- Ambiguous terms: [list]

### Step 2: Identify the Goal
- Immediate goal: [what they asked for]
- Underlying goal: [why they need it]
- Business value: [what problem it solves]

### Step 3: Map Stakeholders
- Direct users: [who will use this]
- Indirect beneficiaries: [who else affected]
- Decision makers: [who approves completion]

### Step 4: Define Success
- Observable outcome: [what will be different]
- Measurable criteria: [how to verify]
- Edge cases: [what could go wrong]

### Step 5: Identify Gaps
- Missing information: [what we don't know]
- Assumptions made: [what we're guessing]
- Clarifications needed: [questions to ask]
]]></chain-of-thought>

<five-whys>
  <purpose>Dig deeper to find root needs</purpose>
  <example>
    <request>Add a button to export data</request>
    <why order="1">Need to share data with finance team</why>
    <why order="2">Finance needs to reconcile with their system</why>
    <why order="3">Currently manually copy data (error-prone)</why>
    <why order="4">No automated integration exists</why>
    <why order="5">Systems were built separately</why>
    <root-need>Finance needs reliable data transfer (button is just ONE solution)</root-need>
    <insight>Maybe API integration or scheduled export would serve better</insight>
  </example>
</five-whys>

<essential-seven>
  <question name="WHAT">What specific behavior/outcome do you expect?</question>
  <question name="WHY">What problem does this solve? What happens if we don't do this?</question>
  <question name="WHO">Who will use this? Who else is affected?</question>
  <question name="WHEN">How urgent? When is it needed by?</question>
  <question name="WHERE">Where in the system/workflow does this fit?</question>
  <question name="HOW">How will we know it's working correctly?</question>
  <question name="HOW MUCH">What volume/scale do we need to support?</question>
</essential-seven>

<invest-criteria>
  <criterion id="I" name="Independent" question="Can be done without other tasks completing first?" warning="'After we do X...'"/>
  <criterion id="N" name="Negotiable" question="Flexibility in how implemented?" warning="Overly prescriptive vs outcome-focused"/>
  <criterion id="V" name="Valuable" question="Delivers user/business value?" warning="Tech debt with no user benefit"/>
  <criterion id="E" name="Estimable" question="Can roughly estimate effort?" warning="'Build AI' - too vague"/>
  <criterion id="S" name="Small" question="Can be done in reasonable timeframe?" warning="Multi-week epics bundled"/>
  <criterion id="T" name="Testable" question="Can verify when done?" warning="'Make it better' (unmeasurable)"/>
</invest-criteria>

<acceptance-criteria format="Given-When-Then">
  <template><![CDATA[
Scenario: [Specific scenario]
  Given [precondition/context]
  And [additional context if needed]
  When [action/trigger]
  Then [expected outcome]
  And [additional outcomes]
]]></template>
</acceptance-criteria>

<scope-boundary-template><![CDATA[
## Scope for: [Task Name]

### Explicitly In Scope
- [ ] [Specific deliverable 1]
- [ ] [Specific deliverable 2]

### Explicitly Out of Scope
- [ ] [Related item NOT included]
- [ ] [Future enhancement NOT included]

### Boundary Rules
1. This task covers [X] but NOT [Y]
2. We will modify [Component A] but NOT [Component B]
]]></scope-boundary-template>

<scope-creep-prevention>
  <warning-signs>
    <sign>"While we're at it, can we also..."</sign>
    <sign>"That reminds me, we should..."</sign>
    <sign>"It would be nice if..."</sign>
    <sign>"Users will probably want..."</sign>
    <sign>"Let's just quickly add..."</sign>
  </warning-signs>
  <response-strategy>
    <step order="1">Acknowledge: "That's a good idea."</step>
    <step order="2">Document: "Let me note that for future work."</step>
    <step order="3">Redirect: "For this task, we're focused on [original scope]."</step>
    <step order="4">Defer: "We can evaluate that as a separate ticket."</step>
  </response-strategy>
  <distinction>
    <scope-creep>Nice to have, adds new functionality, can be deferred</scope-creep>
    <missing-requirement>Must have, completes existing functionality, cannot defer</missing-requirement>
    <test>Can the original goal be achieved without this?</test>
  </distinction>
</scope-creep-prevention>

<decomposition-principles>
  <principle>Single Responsibility: Each subtask does one thing</principle>
  <principle>Independence: Minimize dependencies between tasks</principle>
  <principle>Testability: Each subtask has clear completion criteria</principle>
  <principle>Assignability: Each subtask can be given to one agent/person</principle>
  <principle>Parallelizability: Identify what can be done simultaneously</principle>
</decomposition-principles>

<red-flags>
  <category name="Ambiguous Language">
    <flag>"Better", "improved", "enhanced" (compared to what?)</flag>
    <flag>"Fast", "quick", "responsive" (how fast?)</flag>
    <flag>"User-friendly", "intuitive" (for whom?)</flag>
    <flag>"Support for X" (what kind of support?)</flag>
  </category>
  <category name="Missing Information">
    <flag>No acceptance criteria</flag>
    <flag>No error handling specified</flag>
    <flag>No edge cases considered</flag>
    <flag>No user identification</flag>
  </category>
  <category name="Scope Bombs">
    <flag>"Should be simple"</flag>
    <flag>"Just like [complex system]"</flag>
    <flag>"All the usual features"</flag>
    <flag>"Obviously it should..."</flag>
  </category>
</red-flags>

<anti-patterns>
  <pattern name="Assumption Cascade">Making one assumption that leads to more assumptions</pattern>
  <pattern name="Gold Plating">Adding requirements the user didn't ask for</pattern>
  <pattern name="Analysis Paralysis">Asking infinite questions instead of reasonable clarity</pattern>
  <pattern name="Literal Interpretation">Taking requests at face value without probing</pattern>
  <pattern name="Scope Blindness">Not defining boundaries until scope creep occurs</pattern>
  <pattern name="Happy Path Only">Ignoring error cases and edge conditions</pattern>
  <pattern name="Premature Decomposition">Breaking down before understanding the whole</pattern>
</anti-patterns>

<quality-checklist>
  <item>Original request captured verbatim</item>
  <item>User intent understood (not just words)</item>
  <item>Business value identified</item>
  <item>All ambiguous terms clarified</item>
  <item>Acceptance criteria defined (Given-When-Then)</item>
  <item>Scope boundaries explicit</item>
  <item>Out of scope documented</item>
  <item>Task decomposed into subtasks</item>
  <item>Dependencies mapped</item>
  <item>Risks identified</item>
  <item>Definition of done specified</item>
  <item>All requirement references use EXACT ticket wording - no paraphrasing (compare against ticket.md)</item>
</quality-checklist>

</knowledge-base>
