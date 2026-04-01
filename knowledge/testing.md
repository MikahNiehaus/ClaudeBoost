# Claude Code Testing Configuration

<knowledge-base name="testing" version="1.0">
<triggers>test, TDD, unit test, integration test, mock, assert, coverage, pytest, jest, spec</triggers>
<overview>Writing tests, implementing TDD, creating test suites. Tests verify BEHAVIOR, not implementation.</overview>

<core-philosophy>
  <principle>Tests must answer: "What should this code do?" NOT "What does this code currently do?"</principle>
  <principle>Tests generated FROM code mirror that code's bugs; tests generated FROM requirements validate correctness</principle>
  <principle>A test that passes when there's a bug is worse than no test at all</principle>
</core-philosophy>

<tdd-workflow name="Red-Green-Refactor">
  <step order="1" name="Red">Write failing tests FIRST based on requirements - do NOT look at implementation</step>
  <step order="2" name="Verify Failure">Run tests and confirm they FAIL for the right reason</step>
  <step order="3" name="Green">Write minimal code to make tests pass - do NOT modify tests</step>
  <step order="4" name="Verify Pass">Run tests and confirm they PASS</step>
  <step order="5" name="Refactor">Improve while keeping tests green</step>
  <step order="6" name="Complete">Never mark task complete until all tests pass</step>
</tdd-workflow>

<required-test-categories>
  <category>Happy path with valid inputs (normal operation)</category>
  <category>Edge cases: empty inputs, null/undefined, boundary values, maximum values</category>
  <category>Error conditions: invalid inputs, exceptions, permission errors</category>
  <category>State transitions and side effects</category>
  <category>Async behavior edge cases if applicable</category>
  <warning>If only writing happy-path tests, STOP and explicitly add edge case tests</warning>
</required-test-categories>

<aaa-pattern name="Arrange-Act-Assert">
  <section name="ARRANGE">Set up test data and dependencies</section>
  <section name="ACT">Execute the code being tested (ONE action)</section>
  <section name="ASSERT">Verify expected outcomes</section>
  <rule>Keep "Act" section to a single operation. Multiple actions = multiple tests.</rule>
</aaa-pattern>

<mocking-guidance>
  <do-mock>
    <item>External HTTP APIs and third-party services</item>
    <item>Database connections in unit tests</item>
    <item>File system operations</item>
    <item>Time/date functions for determinism</item>
  </do-mock>
  <do-not-mock>
    <item>The code being tested (never mock the subject)</item>
    <item>Framework features (don't test that React renders)</item>
    <item>Your own simple utility functions</item>
    <item>Data models and interfaces</item>
  </do-not-mock>
</mocking-guidance>

<superficial-test-prevention>
  <do-not-write>
    <anti-pattern>Tests that just assert function returns without error</anti-pattern>
    <anti-pattern>Copy implementation logic into expected values</anti-pattern>
    <anti-pattern>Test that mocks return what you configured them to return</anti-pattern>
    <anti-pattern>Only verify type correctness</anti-pattern>
    <anti-pattern>Assert implementation details like "called private method X"</anti-pattern>
  </do-not-write>
  <instead-write-tests-that-fail-if>
    <condition>The function returns the wrong value</condition>
    <condition>An edge case is mishandled</condition>
    <condition>An error condition isn't caught</condition>
    <condition>Business logic changes incorrectly</condition>
  </instead-write-tests-that-fail-if>
</superficial-test-prevention>

<test-execution-rules>
  <rule>ALWAYS run tests after writing them - never assume they pass</rule>
  <rule>Run the specific test file first, then the full suite</rule>
  <failure-loop>
    <step>READ: Parse complete error message (expected vs actual, stack trace)</step>
    <step>ANALYZE: Is the test correct? Is the implementation wrong?</step>
    <step>FIX: Make the SMALLEST change to fix</step>
    <step>RUN: Immediately re-execute test</step>
    <step>REPEAT: Until all pass</step>
  </failure-loop>
</test-execution-rules>

<framework-commands>
  <command lang="Python">pytest -xvs (stop on first failure, verbose)</command>
  <command lang="JavaScript/TypeScript">npm test -- --watch or jest --watch</command>
  <command lang=".NET">dotnet test --logger "console;verbosity=detailed"</command>
  <command lang="Java">mvn test -Dtest=ClassName#methodName</command>
  <command lang="Go">go test -v -run TestName</command>
</framework-commands>

<naming-conventions>
  <example>test_withdraw_with_insufficient_funds_raises_exception</example>
  <example>should throw error when input is null</example>
  <example>CalculateTotal_EmptyCart_ReturnsZero</example>
  <rule>Test names should explain what broke when they fail</rule>
</naming-conventions>

<first-principles>
  <principle id="F">Fast: Tests run in milliseconds; suites in seconds</principle>
  <principle id="I">Isolated: Tests don't depend on each other or external state</principle>
  <principle id="R">Repeatable: Same results every time in any environment</principle>
  <principle id="S">Self-Validating: Tests produce pass/fail without manual inspection</principle>
  <principle id="T">Thorough: Cover happy paths, error cases, and boundaries</principle>
</first-principles>

<production-safety critical="true">
  <rule>Tests MUST use dedicated test databases/services, NEVER production</rule>
  <rule>Add environment validation at test startup: assert APP_ENV != 'production'</rule>
  <rule>Use .env.test files separate from production configuration</rule>
  <database-isolation-strategies>
    <strategy>Transaction Rollback: Wrap each test, rollback after</strategy>
    <strategy>Testcontainers: Fresh database container per test class</strategy>
    <strategy>Schema Per Test: Create unique schema, drop after</strategy>
    <strategy>Truncate Pattern: Clear all data between tests</strategy>
  </database-isolation-strategies>
  <prohibited>
    <item>Production URLs, connection strings, or credentials</item>
    <item>Real API keys matching production patterns (sk_live_, pk_live_)</item>
    <item>DELETE/TRUNCATE without WHERE clauses</item>
    <item>DROP TABLE/DATABASE without environment checks</item>
  </prohibited>
</production-safety>

<determinism-requirements>
  <rule>Never use time.sleep() or setTimeout() with real delays</rule>
  <rule>Mock time/date for tests that depend on current time</rule>
  <rule>Use fixed seeds for random number generators</rule>
  <rule>Avoid tests that depend on execution order</rule>
</determinism-requirements>

<completion-criteria>
  <criterion>All new tests pass</criterion>
  <criterion>All existing tests pass (no regressions)</criterion>
  <criterion>Tests cover the primary functionality AND edge cases</criterion>
  <criterion>No skipped or pending tests</criterion>
  <criterion>Coverage meets project threshold (if defined)</criterion>
</completion-criteria>

<quality-checklist>
  <item>Tests would FAIL if the core functionality broke</item>
  <item>Edge cases (null, empty, max values) are covered</item>
  <item>Error handling paths are tested</item>
  <item>Test names describe WHAT should happen, not HOW</item>
  <item>No tests that just assert toBeTruthy() or != null</item>
  <item>Mocks verify they were called with correct arguments</item>
  <item>Tests are isolated (can run in any order)</item>
</quality-checklist>

</knowledge-base>
