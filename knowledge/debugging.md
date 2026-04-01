# Claude Code Debugging Configuration

<knowledge-base name="debugging" version="1.0">
<triggers>debug, error, bug, troubleshoot, stack trace, fix, crash, exception, investigate</triggers>
<overview>Debugging errors, fixing bugs, troubleshooting issues, analyzing stack traces, investigating unexpected behavior.</overview>

<core-philosophy>
  <stat>78% accuracy on complex multi-file debugging</stat>
  <stat>73% longer context retention (50 min vs 17 min)</stat>
  <limitation>81% failure rate on semantic-preserving changes (renames, comment changes)</limitation>
  <key>Success requires structured prompts, proper context, systematic workflows</key>
</core-philosophy>

<structured-prompt-format><![CDATA[
<error_report>
Exact error message with line numbers
Stack trace with preserved formatting
Error codes
</error_report>

<context>
Recent changes that preceded the error
Environment details (OS, runtime versions)
Whether bug appears consistently or intermittently
</context>

<relevant_code>
The failing function
Immediate dependencies
Type definitions
File paths and line numbers
</relevant_code>

<instructions>
Analyze systematically
Identify root cause
Then propose a fix
</instructions>
]]></structured-prompt-format>

<debugging-frameworks>
  <framework name="Chain-of-Thought">
    <instruction>Analyze systematically: examine error → trace execution → find root cause → suggest fixes with rationale</instruction>
  </framework>
  <framework name="ReAct (Reasoning + Action)">
    <pattern>Thought → Action → Observation → Thought → ...</pattern>
    <benefit>Reduces guessing, grounds conclusions in evidence</benefit>
  </framework>
  <framework name="Self-Ask Decomposition">
    <question>What is the expected behavior?</question>
    <question>What is the actual behavior?</question>
    <question>Where does execution diverge?</question>
    <question>What changed recently?</question>
  </framework>
  <framework name="Five Whys">
    <pattern>Problem → Why 1 → Why 2 → Why 3 → Why 4 → Why 5 (Root Cause)</pattern>
    <requirement>Provide evidence citations at each step</requirement>
  </framework>
</debugging-frameworks>

<context-management>
  <always-include tokens="500-1000">
    <item>Exact error messages</item>
    <item>Relevant code sections</item>
    <item>Stack traces</item>
    <item>Recent changes</item>
    <item>Expected vs actual behavior</item>
  </always-include>
  <selectively-include>
    <item>Full file contents (when directly relevant)</item>
    <item>Configuration files</item>
    <item>Test cases</item>
  </selectively-include>
  <omit-or-summarize>
    <item>Third-party library code</item>
    <item>Boilerplate</item>
    <item>Historical context beyond recent changes</item>
  </omit-or-summarize>
  <lost-in-middle-effect>
    <structure position="START">Task instructions + specific error</structure>
    <structure position="MIDDLE">Code and context</structure>
    <structure position="END">Reiterate key constraints</structure>
  </lost-in-middle-effect>
</context-management>

<systematic-workflow>
  <plan-then-execute>
    <step order="1">Explore: Read relevant files without coding</step>
    <step order="2">Plan: Create detailed step-by-step approach</step>
    <step order="3">Implement: Execute with verification at each step</step>
    <step order="4">Commit: Document changes</step>
  </plan-then-execute>
  <iterative-process when="initial fixes fail">
    <step>Replication: Reproduce consistently</step>
    <step>Problem Identification: Ask Claude to EXPLAIN incorrect output</step>
    <step>Iteration: Update prompts to handle edge cases</step>
    <step>Double Checking: Regenerate multiple times for consistency</step>
    <step>Benchmarking: Test against full test suite</step>
  </iterative-process>
</systematic-workflow>

<error-type-strategies>
  <strategy type="Runtime errors">Trace data flow to identify undefined value origins</strategy>
  <strategy type="Logic bugs">Step-by-step function walkthrough with sample data</strategy>
  <strategy type="Performance">Complexity analysis, Big O, bottleneck identification</strategy>
  <strategy type="Race conditions">Timing analysis, thread interleaving, lock gaps</strategy>
  <strategy type="Memory leaks">Lifecycle analysis, unclosed resources, circular references</strategy>
  <strategy type="Intermittent bugs">Multi-iteration testing, statistical pattern gathering</strategy>
</error-type-strategies>

<known-limitations>
  <struggles-with>
    <item>Complex multi-system issues (microservices, APIs, distributed databases)</item>
    <item>Security vulnerabilities (attack vectors, exploitation)</item>
    <item>Architectural decisions (long-term maintainability, scalability)</item>
    <item>Performance optimization (production environment specifics)</item>
    <item>Race conditions and timing-dependent bugs</item>
  </struggles-with>
  <location-bias>
    <stat>60% of correctly localized faults in first 25% of code</stat>
    <stat>Only 13% detected in last 25%</stat>
    <action>Place critical code sections EARLIER in context</action>
  </location-bias>
</known-limitations>

<failure-indicators description="Stop and escalate when:">
  <indicator>After 2-3 iterations without meaningful progress</indicator>
  <indicator>Suggestions become repetitive without new information</indicator>
  <indicator>Solutions becoming more complex instead of simpler</indicator>
  <indicator>Confident but incorrect statements about APIs/methods</indicator>
  <indicator>Surface fixes masking symptoms without addressing causes</indicator>
  <false-progress-patterns>
    <pattern name="Repetition loop">Same suggestions reformulated</pattern>
    <pattern name="Complexity spiral">Adding dependencies instead of fixing root cause</pattern>
    <pattern name="Hallucination">Confidently incorrect API/method info</pattern>
    <pattern name="Surface fix">Masks symptoms without addressing design flaws</pattern>
  </false-progress-patterns>
</failure-indicators>

<complexity-hierarchy>
  <level num="1" when="Clear errors, single-file, syntax/logic">Claude alone</level>
  <level num="2" when="Multi-file with clear boundaries">Claude + human guidance</level>
  <level num="3" when="System-wide, security, performance-critical">Human-led + Claude assistance</level>
  <level num="4" when="Distributed systems, production emergencies">Human only</level>
</complexity-hierarchy>

<quality-indicators>
  <strong-response>
    <indicator>Explains WHY fixes work</indicator>
    <indicator>References specific error messages</indicator>
    <indicator>Provides context about the problem</indicator>
    <indicator>Suggests prevention approaches</indicator>
    <indicator>Acknowledges limitations/uncertainties</indicator>
  </strong-response>
  <weak-response>
    <indicator>Generic "try this" without rationale</indicator>
    <indicator>Ignores provided context</indicator>
    <indicator>Multiple random changes without reasoning</indicator>
    <indicator>Fails to address actual error messages</indicator>
  </weak-response>
</quality-indicators>

<validation-checklist>
  <item>Tests written that would have caught the original bug</item>
  <item>Solution verified across multiple scenarios including edge cases</item>
  <item>No regressions in related functionality</item>
  <item>Root cause documented (why it occurred, how fix addresses it)</item>
</validation-checklist>

<time-boxing>
  <rule>Maximum 20-30 minutes before reassessing strategy</rule>
  <rule>If Claude repeatedly suggests same fixes → stop, switch approaches</rule>
  <rule>If more time explaining context than debugging → problem exceeds Claude's capabilities</rule>
</time-boxing>

</knowledge-base>
