# Completion Verification Methodology

<knowledge-base name="completion-verification" version="1.0">
<triggers>completion, verify, done, criteria, persistent mode, finish, complete task</triggers>
<overview>How to verify task completion, especially for PERSISTENT mode tasks that must continue until explicit criteria are met.</overview>

<verification-types>
  <type name="Count-Based" goal="all X type goals where completion = zero remaining">
    <pattern>Count before → Process → Count after → Complete when count = 0</pattern>
    <example task="Convert all .js to .ts">
      <before>find . -name "*.js" | wc -l (e.g., 45)</before>
      <complete-when>.js count = 0</complete-when>
    </example>
    <example task="Fix all lint errors">
      <before>npm run lint | grep -c "error" (e.g., 23)</before>
      <complete-when>error count = 0</complete-when>
    </example>
  </type>

  <type name="Threshold-Based" goal="until X% type goals">
    <pattern>Measure baseline → Process → Re-measure → Complete when metric >= threshold</pattern>
    <example task="Test coverage >= 90%">
      <measure>npm run coverage -- --json | jq '.total.lines.pct'</measure>
      <complete-when>coverage >= 90</complete-when>
    </example>
  </type>

  <type name="State-Based" goal="make X true type goals">
    <pattern>Define success command → Process → Run command → Complete when exit code = 0</pattern>
    <example task="No TypeScript errors">npx tsc --noEmit (exit 0 = complete)</example>
    <example task="All tests pass">npm test (exit 0 = complete)</example>
    <example task="Build succeeds">npm run build (exit 0 = complete)</example>
  </type>

  <type name="Composite" goal="multiple criteria required">
    <pattern>Define all criteria → All must pass → Complete when ALL met</pattern>
    <table><![CDATA[
| # | Criterion | Command | Threshold | Status |
|---|-----------|---------|-----------|--------|
| 1 | Files converted | find . -name "*.js" | = 0 | pending |
| 2 | TS compiles | npx tsc --noEmit | exit 0 | pending |
| 3 | Tests pass | npm test | exit 0 | pending |
]]></table>
  </type>
</verification-types>

<verification-protocol>
  <phase name="Before Starting (PERSISTENT Mode)">
    <step>Parse completion criteria from user request (explicit + implicit)</step>
    <step>Define verification command for each criterion (deterministic, measurable)</step>
    <step>Run baseline verification and establish starting point</step>
    <step>Store in context.md Completion Criteria table</step>
  </phase>

  <phase name="After Each Iteration">
    <step>Run all verification commands</step>
    <step>Compare against thresholds</step>
    <step>Update status: pending | met | failed | error</step>
    <step>Decision: ALL met → COMPLETE, ANY error → BLOCKED, else → continue</step>
  </phase>

  <phase name="On Resume (After Compaction)">
    <step>Read completion criteria from context.md</step>
    <step>Run ALL verification commands (don't trust stored status)</step>
    <step>Compare actual vs stored progress</step>
    <step>Continue from documented "Next Item"</step>
  </phase>
</verification-protocol>

<verification-commands>
  <category name="File Operations">
    <command purpose="Count by extension">find . -name "*.ext" -not -path "./node_modules/*" | wc -l</command>
    <command purpose="Check file exists">test -f "path/to/file" &amp;&amp; echo "exists" || echo "missing"</command>
    <command purpose="Check dir exists">test -d "path/to/dir" &amp;&amp; echo "exists" || echo "missing"</command>
  </category>
  <category name="Code Quality">
    <command purpose="TypeScript check">npx tsc --noEmit; echo "Exit: $?"</command>
    <command purpose="ESLint count">npm run lint 2>&amp;1 | grep -c "error" || echo "0"</command>
    <command purpose="Test suite">npm test; echo "Exit: $?"</command>
    <command purpose="Coverage">npm run coverage -- --json | jq '.total.lines.pct'</command>
  </category>
  <category name="Git Operations">
    <command purpose="No uncommitted">git status --porcelain | wc -l (0 = clean)</command>
    <command purpose="Current branch">git branch --show-current</command>
    <command purpose="Nothing staged">git diff --cached --stat | wc -l (0 = nothing)</command>
  </category>
</verification-commands>

<implicit-criteria always-check="true">
  <criterion name="Code compiles" why="Broken code is useless" verify="Build exits 0"/>
  <criterion name="Tests pass" why="No regressions" verify="Test command exits 0"/>
  <criterion name="No new lint errors" why="Code quality" verify="Lint exits 0"/>
  <criterion name="No secrets exposed" why="Security" verify="grep for API keys"/>
</implicit-criteria>

<checkpoint-protocol>
  <when-to-checkpoint>
    <trigger>Every N items (default: 10)</trigger>
    <trigger>Before operation consuming >10K tokens</trigger>
    <trigger>When token usage approaches ~75% capacity</trigger>
    <trigger>After completing a logical phase</trigger>
  </when-to-checkpoint>
  <what-to-save>
    <item>Progress: Items completed / total</item>
    <item>Last processed item, Next item</item>
    <item>Current count for each criterion</item>
    <item>Quick Resume updated</item>
  </what-to-save>
</checkpoint-protocol>

<anti-premature-completion>
  <before-saying-done>
    <check>Run ALL verification commands - ALL must return "met"</check>
    <check>Check implicit criteria (build, test, lint)</check>
    <check>Check task mode (PERSISTENT = ALL criteria met?)</check>
    <check>Check TodoWrite items all marked complete</check>
  </before-saying-done>
  <if-verification-fails>
    <action>DO NOT tell user "done"</action>
    <action>Report what IS complete</action>
    <action>Report what is NOT complete</action>
    <action>PERSISTENT mode: Continue automatically</action>
    <action>NORMAL mode: Ask user if continue</action>
  </if-verification-fails>
</anti-premature-completion>

<error-handling>
  <scenario name="Verification Command Fails">
    <action>Mark criterion as "error"</action>
    <action>Log error in context.md</action>
    <action>DO NOT mark task complete</action>
    <action>Report: "Cannot verify criterion - command failed"</action>
  </scenario>
  <scenario name="Infinite Loop Detection" trigger="Same item processed 3+ times">
    <action>Mark as BLOCKED</action>
    <action>Log pattern in context.md</action>
    <action>Ask user for guidance</action>
  </scenario>
  <scenario name="Threshold Never Met" trigger="10+ iterations, no progress">
    <action>Report current state</action>
    <action>Ask: "Progress stalled at X%. Continue or adjust?"</action>
  </scenario>
</error-handling>

<execution-modes>
  <mode name="NORMAL" default="true">
    <behavior>Verify only implicit criteria (build, test, lint)</behavior>
    <behavior>Single verification at end of step</behavior>
    <behavior>Report and stop</behavior>
  </mode>
  <mode name="PERSISTENT">
    <behavior>Verify ALL criteria (explicit + implicit)</behavior>
    <behavior>Continuous verification after each iteration</behavior>
    <behavior>Auto-continue until all criteria met</behavior>
    <behavior>Checkpoint every N items</behavior>
    <behavior>Resume automatically after compaction</behavior>
  </mode>
</execution-modes>

</knowledge-base>
