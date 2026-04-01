# PR Review Guidelines

<knowledge-base name="pr-review" version="1.0">
<triggers>PR review, code review, pull request, feedback, LGTM, approve, request changes</triggers>
<overview>Code review serves knowledge transfer, maintaining code health, and creating historical records. Approve code that improves overall health, even if not perfect.</overview>

<core-principles>
  <principle>Approve code that definitely improves overall code health, even if not perfect</principle>
  <principle>Effectiveness drops beyond 400 lines of code</principle>
  <principle>Reviews should take 60-90 minutes maximum</principle>
  <principle>Optimal inspection rate: 300-500 LOC/hour</principle>
</core-principles>

<technical-criteria>
  <category name="Functionality">
    <check>Verify code solves the stated problem</check>
    <check>Check for logic errors: off-by-one, incorrect conditionals</check>
    <check>Examine edge cases: empty, null, boundary, min/max</check>
    <check>Verify error handling with meaningful messages</check>
    <check>Review test coverage for edge cases and error paths</check>
  </category>

  <category name="Code Quality">
    <check>Functions should be small and focused</check>
    <check>Flag code with >3-4 levels of nesting</check>
    <check>Flag excessive branching (long if/else chains)</check>
    <check>Variable/function/class names clear and descriptive</check>
    <check>Comments explain WHY, not WHAT</check>
    <check>Remove commented-out code</check>
    <check>Replace magic numbers with named constants</check>
  </category>

  <category name="SOLID Principles">
    <red-flag principle="SRP">Classes mixing business logic with persistence/presentation/logging</red-flag>
    <red-flag principle="OCP">Long if/else chains checking types, frequent instanceof</red-flag>
    <red-flag principle="LSP">Derived classes requiring explicit casting</red-flag>
    <red-flag principle="ISP">"Fat" interfaces where clients implement unused functionality</red-flag>
    <red-flag principle="DIP">Direct dependencies on concrete classes, liberal use of new</red-flag>
  </category>
</technical-criteria>

<security-review always-blocking="true">
  <category name="Input Validation (OWASP Top 10)">
    <check>SQL injection: Use parameterized queries</check>
    <check>Command injection: Handle safely</check>
    <check>Path traversal: Validate file paths</check>
    <check>All user inputs: Validate, sanitize, escape</check>
  </category>
  <category name="Auth">
    <check>Robust authentication mechanisms</check>
    <check>Proper session handling with timeouts</check>
    <check>Password storage: bcrypt or Argon2</check>
    <check>Authorization checks at all entry points</check>
    <check>CSRF protection</check>
  </category>
  <category name="Data Exposure">
    <check>No passwords/tokens/credentials in code or logs</check>
    <check>Error messages don't expose system details</check>
    <check>Sensitive data encrypted at rest and in transit</check>
  </category>
</security-review>

<performance-review>
  <check>Flag O(n²) or worse without justification</check>
  <check>Check for N+1 query problem (queries in loops)</check>
  <check>Verify appropriate indexes for WHERE and JOIN</check>
  <check>Large result sets: use pagination or streaming</check>
  <check>File handles/connections properly cleaned up</check>
</performance-review>

<api-changes>
  <breaking require-major-version="true">
    <change>Removing fields or endpoints</change>
    <change>Changing field types</change>
    <change>Renaming (equivalent to remove and add)</change>
    <change>Making optional parameters required</change>
    <change>Changing HTTP response code meanings</change>
  </breaking>
  <safe>
    <change>Adding optional fields</change>
    <change>New endpoints</change>
    <change>Optional parameters with sensible defaults</change>
    <change>Deprecation (maintains function)</change>
  </safe>
</api-changes>

<communication>
  <golden-rules>
    <rule>Comment on the code, never on the developer</rule>
    <rule>Use questions instead of commands</rule>
    <rule>Frame as personal observations (I-messages)</rule>
    <rule>Avoid condescending words: just, easy, only, obvious, simply</rule>
    <rule>Never use sarcasm</rule>
  </golden-rules>

  <actionable-feedback>
    <bad>This doesn't look right</bad>
    <bad>Improve this</bad>
    <bad>Fix this</bad>
    <good>The calculateTotal function lacks error handling for invalid input. Please add checks for negative numbers.</good>
    <elements>Specificity + Reasoning + Guidance</elements>
  </actionable-feedback>

  <conventional-comments>
    <label name="blocker">Critical issues preventing merge</label>
    <label name="issue">Problems needing fixes, usually blocking</label>
    <label name="suggestion (non-blocking)">Proposes improvements</label>
    <label name="question">Asks for clarification</label>
    <label name="nit">Trivial, preference-based (always non-blocking)</label>
    <label name="praise">Highlights something genuinely positive</label>
    <decoration name="(blocking)">Must be resolved before merge</decoration>
    <decoration name="(non-blocking)">Shouldn't prevent acceptance</decoration>
    <decoration name="(security)">Security-related concern</decoration>
  </conventional-comments>
</communication>

<review-process>
  <clear-framework>
    <step name="Context">Review requirements, understand integration points</step>
    <step name="Layered">Structure → architecture → logic → security → performance</step>
    <step name="Explicit">Mentally execute with sample data, test boundaries</step>
    <step name="Alternative">Evaluate patterns, analyze trade-offs</step>
    <step name="Refactoring">Prioritize feedback high/medium/low</step>
  </clear-framework>
  <two-pass>
    <pass order="1">Architecture, overall approach, design patterns</pass>
    <pass order="2">Detailed line-by-line, edge cases, error handling</pass>
  </two-pass>
  <timing>
    <rule>Respond within one business day maximum</rule>
    <rule>Keep sessions to 60-90 minutes maximum</rule>
    <rule>Review at 300-500 LOC/hour</rule>
  </timing>
</review-process>

<self-review-checklist>
  <description>Before submitting a PR, the author should complete these 11 passes. Reviewers verify these were done.</description>
  <pass order="1" name="Simplicity pass">Can this be deleted, inlined, or simplified?</pass>
  <pass order="2" name="Already-exists pass">Does the codebase or a dependency already provide this? But verify the existing thing actually meets the requirement — reusing a single-select widget for a multi-select requirement is worse than creating a new one.</pass>
  <pass order="3" name="Dead code pass">Is every variable/param/function actually referenced?</pass>
  <pass order="4" name="Debug cleanup pass">Any temporary logs, flags, commented blocks left?</pass>
  <pass order="5" name="Project patterns pass">How does this repo usually solve this problem?</pass>
  <pass order="6" name="Common-pattern breaker pass">Am I breaking a shared convention?</pass>
  <pass order="7" name="Fresh eyes pass">Read every line like you didn't write it</pass>
  <pass order="8" name="Ticket alignment pass">Exactly what the ticket asks, no more, no less</pass>
  <pass order="9" name="Spec precision pass">Word-for-word match on UI copy, field names, behaviors</pass>
  <pass order="10" name="Manual smoke test pass">Did I actually use this feature in a browser? For each AC scenario, physically perform the described action. Don't trust code reading alone — JS widgets can behave differently than the HTML suggests. If you can't run it locally, flag it in the PR.</pass>
  <pass order="11" name="Migration/Schema pass">Every model property add/remove MUST have a matching migration. Verify the generated migration does what you expect.</pass>
</self-review-checklist>

<approval-criteria>
  <approve-when>
    <criterion>Code definitely improves overall code health</criterion>
    <criterion>Functionality correct and edge cases handled</criterion>
    <criterion>Security issues properly addressed</criterion>
    <criterion>Tests provide adequate coverage</criterion>
    <criterion>Remaining issues are truly minor</criterion>
  </approve-when>
  <request-changes-when>
    <criterion>Security vulnerabilities exist</criterion>
    <criterion>Functionality incorrect or missing critical edge cases</criterion>
    <criterion>Approach has fundamental flaws</criterion>
    <criterion>Tests missing or inadequate</criterion>
    <criterion>Performance issues will impact users</criterion>
  </request-changes-when>
</approval-criteria>

<review-depth>
  <context type="Small bug fixes" lines="&lt;50" focus="Correctness, edge cases, regression test"/>
  <context type="New features" lines="50-400" focus="Full review: architecture, security, performance, testing"/>
  <context type="Refactoring" focus="Maintains behavior, improves quality, adequate tests"/>
  <context type="Large architectural" lines=">400" focus="Request split, or walkthrough, multiple sessions"/>
  <context type="Critical/security" focus="Maximum scrutiny, domain expert review"/>
</review-depth>

<anti-patterns>
  <process>
    <bad name="Marathon reviews">Effectiveness drops after 60-90 minutes</bad>
    <bad name="Ping-pong reviews">Provide all feedback in one pass</bad>
    <bad name="Rubber stamping">Quick LGTM without examination</bad>
    <bad name="Moving goalposts">Objecting to previously accepted patterns</bad>
  </process>
  <communication>
    <bad>Harsh, hostile, or dismissive tone</bad>
    <bad>Vague feedback without actionable direction</bad>
    <bad>Excessive nitpicking on trivial style issues</bad>
  </communication>
</anti-patterns>

</knowledge-base>
