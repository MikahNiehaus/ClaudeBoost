# Code Self-Critique Protocol

<knowledge-base name="code-critique" version="1.0">
<triggers>critique, self-review, code review, line-by-line, assumptions, edge cases, trade-offs</triggers>
<overview>Every agent that produces code changes MUST self-critique before finalizing. Ensures quality and surfaces issues before they become problems.</overview>

<when-to-critique>
  <trigger>After writing ANY code (new functions, bug fixes, refactors)</trigger>
  <trigger>Before reporting COMPLETE status</trigger>
  <trigger>Before handing off to another agent</trigger>
</when-to-critique>

<line-by-line-checklist>
  <category name="Purpose">
    <check>Does this line serve a clear, necessary purpose?</check>
    <check>Could this be removed without breaking functionality?</check>
    <check>Is the intent clear to someone reading it for the first time?</check>
  </category>
  <category name="Simplicity">
    <check>Is there a simpler way to achieve this?</check>
    <check>Am I over-engineering this?</check>
    <check>Would a built-in function/library handle this better?</check>
  </category>
  <category name="Correctness">
    <check>What assumptions does this line make?</check>
    <check>What inputs would break this?</check>
    <check>Are edge cases handled (null, empty, negative, overflow)?</check>
  </category>
  <category name="Abstraction">
    <check>Is this the right abstraction level?</check>
    <check>Should this be extracted into a separate function?</check>
    <check>Is this too generic or too specific?</check>
  </category>
  <category name="Safety">
    <check>Could this cause a security vulnerability?</check>
    <check>Is user input properly validated/sanitized?</check>
    <check>Are errors handled appropriately?</check>
  </category>
</line-by-line-checklist>

<required-output-sections>
  <section name="Line-by-Line Review Table">
    <column>Line/Block</column>
    <column>Purpose</column>
    <column>Critique</column>
    <column>Fix Applied</column>
  </section>

  <section name="Assumptions Made">
    <item>Data format assumptions</item>
    <item>Environment assumptions</item>
    <item>Caller behavior assumptions</item>
    <item>State assumptions</item>
  </section>

  <section name="Edge Cases Not Covered">
    <item>Why not handled (out of scope, rare, acceptable risk)</item>
    <item>What would happen if that edge case occurred</item>
  </section>

  <section name="Trade-offs Accepted">
    <item>Readability vs performance</item>
    <item>Simplicity vs flexibility</item>
    <item>Speed vs thoroughness</item>
    <item>Memory vs CPU</item>
  </section>
</required-output-sections>

<example type="good"><![CDATA[
## Self-Critique

| Code | Purpose | Critique | Fix Applied |
|------|---------|----------|-------------|
| `if (!user)` | Guard against null | Doesn't handle empty object `{}` | Changed to: `if (!user?.id)` |
| `users.filter(u => u.active)` | Get active users | Creates new array each call | Acceptable - called once per request |
| `return data.map(transform)` | Transform results | Assumes data is array | Added: `if (!Array.isArray(data)) return []` |
| `await Promise.all(tasks)` | Parallel execution | Fails fast on any rejection | Added: `Promise.allSettled` for resilience |

**Assumptions Made**:
- `user` object always has `id` property when valid
- `users` array fits in memory (no pagination needed)
- `transform` function is pure (no side effects)

**Edge Cases Not Covered**:
- Very large arrays (>10k items) - would need streaming
- Concurrent modifications to `users` - acceptable for read-only operation

**Trade-offs Accepted**:
- Chose `Promise.all` over sequential for speed, accepting fail-fast behavior
- Used in-memory filtering over database query for simplicity
]]></example>

<example type="bad"><![CDATA[
## Self-Critique

The code looks good. I checked everything and it should work.

**Assumptions**: None
**Edge Cases**: All handled
**Trade-offs**: None
]]></example>

<anti-patterns>
  <anti-pattern name="Vague">
    <bad>This might have issues</bad>
    <good>Line 15 assumes `data.items` exists - will throw if missing</good>
  </anti-pattern>
  <anti-pattern name="Over-Critique">
    <bad>Nitpicking every style choice</bad>
    <good>Focus on correctness, security, maintainability</good>
  </anti-pattern>
  <anti-pattern name="Skip It">
    <bad>This is simple code, no critique needed</bad>
    <good>Even simple code can have hidden assumptions</good>
  </anti-pattern>
  <anti-pattern name="Defensive">
    <bad>This is the best possible approach</bad>
    <good>I chose X over Y because Z, but Y would work if [conditions]</good>
  </anti-pattern>
</anti-patterns>

<confidence-guidelines>
  <impact finding="All assumptions verified" level="+HIGH"/>
  <impact finding="Unverified assumptions exist" level="MEDIUM max"/>
  <impact finding="Known unhandled edge cases" level="MEDIUM max"/>
  <impact finding="Significant trade-offs" level="Note in reasoning"/>
  <impact finding="Security concerns found" level="LOW until resolved"/>
  <impact finding="Blocking issues found" level="BLOCKED status"/>
</confidence-guidelines>

<completion-checklist>
  <item>Reviewed each significant line/block</item>
  <item>Documented all assumptions</item>
  <item>Listed unhandled edge cases</item>
  <item>Noted trade-offs made</item>
  <item>Applied fixes for issues found</item>
  <item>Updated confidence level based on findings</item>
</completion-checklist>

</knowledge-base>
