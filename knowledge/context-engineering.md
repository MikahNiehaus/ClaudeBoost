# Context Engineering for Agents

<knowledge-base name="context-engineering" version="1.0">
<triggers>context, token, attention, memory, write, select, compress, isolate, scratchpad</triggers>
<overview>The art of filling the context window with just the right information. Goal: find the smallest set of high-signal tokens that maximize desired outcome.</overview>

<four-pillars>
  <pillar name="Write" focus="System Prompts">
    <principle>Find "right altitude" - specific enough to guide, flexible enough for heuristics</principle>
    <do>
      <item>Organize with XML tags or Markdown headers</item>
      <item>Start minimal, add instructions based on failure modes</item>
      <item>Use direct, imperative language</item>
      <item>Provide concrete examples instead of abstract rules</item>
    </do>
    <dont>
      <item>Hardcode brittle if-else logic</item>
      <item>Use overly vague guidance ("be helpful")</item>
      <item>Include every possible edge case</item>
      <item>Write essay-style prose</item>
    </dont>
  </pillar>

  <pillar name="Select" focus="Tool & Example Curation">
    <principle>Design minimal viable toolsets. Each unused tool wastes attention budget.</principle>
    <tool-design-rules>
      <rule>Self-contained (no implicit dependencies)</rule>
      <rule>Robust to errors (handle edge cases internally)</rule>
      <rule>Extremely clear documentation</rule>
      <rule>Single purpose (avoid multi-function tools)</rule>
    </tool-design-rules>
    <token-costs>
      <item type="Tool definition">100-300 tokens</item>
      <item type="Example (short)">50-100 tokens</item>
      <item type="Example (detailed)">200-500 tokens</item>
      <item type="Knowledge base (small)">500-1000 tokens</item>
      <item type="Knowledge base (large)">2000-5000 tokens</item>
    </token-costs>
  </pillar>

  <pillar name="Compress" focus="Long-Horizon Management">
    <strategy name="Compaction">
      <when>Context nears limit</when>
      <how>Distill critical details, discard redundant tool outputs</how>
      <preserve>Architectural decisions, unresolved bugs, implementation details</preserve>
    </strategy>
    <strategy name="Structured Note-Taking">
      <what>Agents write persistent notes outside context window</what>
      <where>workspace/[task-id]/scratchpad.md</where>
      <structure>Key Discoveries, Intermediate Results, Questions, Decisions</structure>
    </strategy>
    <strategy name="Sub-Agent Architecture">
      <what>Specialized agents return condensed summaries (1,000-2,000 tokens)</what>
      <benefit>Main agent receives summaries, not full context</benefit>
    </strategy>
  </pillar>

  <pillar name="Isolate" focus="Dynamic Retrieval">
    <principle>Use "just-in-time" context with lightweight identifiers</principle>
    <pattern name="Lightweight References">
      <instead-of>Pasting entire file content</instead-of>
      <use>"Read src/auth/login.ts for implementation details"</use>
    </pattern>
    <pattern name="Progressive Disclosure">
      <initial>File paths + descriptions</initial>
      <on-demand>Read specific files when needed</on-demand>
      <never>Load everything upfront</never>
    </pattern>
    <pattern name="Metadata-Guided">Use file structure, naming conventions, timestamps to guide reads</pattern>
  </pillar>
</four-pillars>

<per-agent-budgets>
  <budget type="Lightweight (explore)" init="3,000" output="1,000" rationale="Quick operations"/>
  <budget type="Standard (test, debug)" init="8,000" output="3,000" rationale="Normal tasks"/>
  <budget type="Heavy (architect, workflow)" init="15,000" output="5,000" rationale="Complex reasoning"/>
  <budget type="Orchestrator" init="25,000" output="5,000" rationale="Coordination overhead"/>
</per-agent-budgets>

<token-efficiency>
  <technique name="READ vs Paste">50 tokens instruction vs 2000 tokens content</technique>
  <technique name="Reference vs Inline">Link to files vs paste file content</technique>
  <technique name="Summary vs Full">Key findings vs complete output</technique>
  <technique name="Selective Loading">Load relevant sections vs entire knowledge base</technique>
</token-efficiency>

<anti-patterns>
  <anti-pattern name="Context Dumping">
    <bad>Paste entire file contents into chat history</bad>
    <good>Read file, extract relevant section, summarize</good>
  </anti-pattern>
  <anti-pattern name="Kitchen Sink Tools">
    <bad>One tool that does 20 different operations</bad>
    <good>20 focused tools that each do one thing well</good>
  </anti-pattern>
  <anti-pattern name="Example Overload">
    <bad>50 examples covering every edge case</bad>
    <good>5 diverse examples showing key patterns</good>
  </anti-pattern>
  <anti-pattern name="Outdated Context">
    <bad>Keep old file contents after editing</bad>
    <good>Re-read files after modifications</good>
  </anti-pattern>
</anti-patterns>

<attention-priority>
  <high keep="in focus">
    <item>Current task requirements</item>
    <item>Immediate next step</item>
    <item>Critical constraints</item>
    <item>Recent errors/blockers</item>
  </high>
  <medium reference="as needed">
    <item>Full task plan</item>
    <item>Agent contributions</item>
    <item>File contents</item>
    <item>Test results</item>
  </medium>
  <low action="archive/compress">
    <item>Superseded plans</item>
    <item>Old tool outputs</item>
    <item>Verbose logs</item>
    <item>Historical decisions (keep summary only)</item>
  </low>
</attention-priority>

<quality-checklist>
  <item>Relevant: Is all context necessary for this task?</item>
  <item>Fresh: Is information current (not outdated)?</item>
  <item>Structured: Is context organized for easy retrieval?</item>
  <item>Minimal: Could we accomplish this with less context?</item>
  <item>Referenced: Are we using pointers vs copies?</item>
</quality-checklist>

</knowledge-base>
