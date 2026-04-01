# Code Exploration Knowledge Base

<knowledge-base name="code-exploration" version="1.0">
<triggers>explore, codebase, understand, find, where, how does, architecture, structure, dependencies, navigate, search code</triggers>
<overview>Systematic code exploration produces reliable understanding faster than ad-hoc browsing. Techniques for navigating codebases of any size.</overview>

<core-principles>
  <principle>Read-only first: Understand before modifying</principle>
  <principle>Structured exploration: Use systematic patterns, not random browsing</principle>
  <principle>Pattern recognition: Look for recurring structures across files</principle>
  <principle>Dependency awareness: Understand relationships, not just individual files</principle>
  <principle>Incremental depth: Start broad, drill down as needed</principle>
  <principle>Context preservation: Always note file paths and line numbers</principle>
</core-principles>

<exploration-workflows>
  <workflow name="Quick Overview" duration="&lt;5 min">
    <step>Check README and docs/</step>
    <step>List top-level directories</step>
    <step>Find entry points (main, index, app, server)</step>
    <step>Identify configuration (package.json, pyproject.toml)</step>
    <step>Count and categorize source files</step>
    <output>High-level structure map, tech stack, entry points</output>
  </workflow>
  <workflow name="Feature Understanding" duration="5-15 min">
    <step>Identify feature entry point (API route, UI component)</step>
    <step>Trace imports and dependencies</step>
    <step>Map call chain through execution path</step>
    <step>Find related tests</step>
    <step>Check for configuration/feature flags</step>
    <output>Execution flow diagram, key files list, test locations</output>
  </workflow>
  <workflow name="Dependency Analysis" duration="10-20 min">
    <step>Start from target file/module</step>
    <step>Map all direct imports</step>
    <step>Recursively map transitive dependencies</step>
    <step>Identify circular dependencies</step>
    <step>Find common utilities/shared code</step>
    <output>Dependency graph, coupling analysis</output>
  </workflow>
  <workflow name="Architecture Discovery" duration="20-30 min">
    <step>Identify layer boundaries (UI, API, business, data)</step>
    <step>Map module/package structure</step>
    <step>Find abstraction patterns (interfaces, base classes)</step>
    <step>Trace cross-cutting concerns (logging, auth, errors)</step>
    <step>Identify external integrations</step>
    <output>Layer diagram, pattern catalog, integration points</output>
  </workflow>
</exploration-workflows>

<glob-patterns>
  <pattern glob="**/*.ts" finds="All TypeScript files" use="Language-specific search"/>
  <pattern glob="src/**/*" finds="All source files" use="Source vs config separation"/>
  <pattern glob="**/test*/**" finds="Test directories" use="Finding test coverage"/>
  <pattern glob="**/*Controller*" finds="Controller files" use="MVC pattern discovery"/>
  <pattern glob="**/*.{ts,tsx}" finds="TS and TSX files" use="React project exploration"/>
  <pattern glob="!**/node_modules/**" finds="Exclude deps" use="Avoiding package bloat"/>
</glob-patterns>

<entry-point-patterns>
  <language name="JavaScript/TypeScript">**/index.{js,ts}, **/main.{js,ts}, **/app.{js,ts}, **/server.{js,ts}</language>
  <language name="Python">**/__main__.py, **/main.py, **/app.py, **/wsgi.py</language>
  <language name="Go">**/main.go, **/cmd/**</language>
  <language name="Rust">**/main.rs, **/lib.rs</language>
</entry-point-patterns>

<grep-patterns>
  <pattern goal="Class definition" regex="class\s+ClassName"/>
  <pattern goal="Function definition" regex="function\s+name or def\s+name"/>
  <pattern goal="Import statements" regex="import.*ModuleName"/>
  <pattern goal="TODO/FIXME comments" regex="TODO|FIXME|HACK"/>
  <pattern goal="API endpoints" regex="@(Get|Post|Put) or router\.(get|post)"/>
  <pattern goal="Error handling" regex="catch|except|rescue"/>
  <pattern goal="Configuration" regex="process\.env|os\.environ"/>
</grep-patterns>

<dependency-metrics>
  <metric name="Afferent coupling (Ca)" measures="Incoming dependencies" high-means="Many dependents (stable)"/>
  <metric name="Efferent coupling (Ce)" measures="Outgoing dependencies" high-means="Many dependencies (unstable)"/>
  <metric name="Instability" formula="Ce/(Ca+Ce)" range="0=stable, 1=unstable"/>
  <metric name="Abstractness" measures="Abstract vs concrete" range="High=abstract, Low=concrete"/>
</dependency-metrics>

<layer-identification>
  <layer name="Presentation">
    <contains>Components, Views, Templates, Route handlers, Controllers</contains>
    <search>**/components/**, **/views/**, **/*Controller*</search>
  </layer>
  <layer name="Application">
    <contains>Services, Use Cases, Orchestration logic</contains>
    <search>**/services/**, **/usecases/**</search>
  </layer>
  <layer name="Domain">
    <contains>Entities, Value Objects, Business rules</contains>
    <search>**/domain/**, **/entities/**, **/models/**</search>
  </layer>
  <layer name="Infrastructure">
    <contains>Repositories, Adapters, External integrations</contains>
    <search>**/infrastructure/**, **/adapters/**, **/repositories/**</search>
  </layer>
</layer-identification>

<pattern-recognition>
  <pattern name="Factory" search="Factory, create, make" example="UserFactory.create()"/>
  <pattern name="Singleton" search="instance, getInstance" example="Logger.getInstance()"/>
  <pattern name="Observer" search="subscribe, on, emit" example="eventEmitter.on('event')"/>
  <pattern name="Repository" search="Repository, find, save" example="userRepository.find()"/>
  <pattern name="Service" search="Service, suffixed classes" example="AuthService.validate()"/>
  <pattern name="Controller" search="Controller, route handlers" example="UserController.list()"/>
  <pattern name="Middleware" search="use, next" example="app.use(authMiddleware)"/>
</pattern-recognition>

<large-codebase-strategies>
  <strategy>Never read all files: Use targeted search</strategy>
  <strategy>Start at boundaries: Entry points, APIs, tests</strategy>
  <strategy>Follow data flow: Input → processing → output</strategy>
  <strategy>Trust package boundaries: Don't drill into every module</strategy>
  <strategy>Sample patterns: Find 2-3 examples, assume pattern holds</strategy>
  <strategy>Set explicit scope boundaries before starting</strategy>
  <strategy>Time-box exploration phases</strategy>
  <strategy>Write findings as you go (don't hold in memory)</strategy>
  <strategy>Stop when you have enough to answer the question</strategy>
</large-codebase-strategies>

<output-standards>
  <always-include>
    <item>File paths: Absolute or repo-relative paths</item>
    <item>Line numbers: Specific line references</item>
    <item>Code context: Relevant snippets (not full files)</item>
    <item>Relationships: How files/functions connect</item>
    <item>Next steps: What to explore next</item>
  </always-include>
</output-standards>

<anti-patterns>
  <exploration>
    <bad>Reading files linearly: Code isn't a novel; jump around</bad>
    <bad>Ignoring tests: Tests show intended usage</bad>
    <bad>Missing configuration: Config often explains behavior</bad>
    <bad>Skipping README: Often contains crucial context</bad>
    <bad>Over-exploring: Stop when you have enough</bad>
  </exploration>
  <search>
    <bad>Too broad: *.* returns too much noise</bad>
    <bad>Too literal: Missing variations in naming</bad>
    <bad>Wrong language: Searching Python patterns in JS</bad>
    <bad>Ignoring case: User vs user both matter</bad>
  </search>
</anti-patterns>

<handoff-templates>
  <handoff to="debug-agent"><![CDATA[
"Exploration found the bug likely in these files:
- src/auth/validate.ts:42 - Token parsing
- src/middleware/auth.ts:15 - Middleware invocation
Call chain: request → middleware → validate → [error]"
]]></handoff>
  <handoff to="architect-agent"><![CDATA[
"Codebase uses layered architecture:
- Presentation: React components in /src/components
- Application: Services in /src/services
- Domain: Models in /src/domain
- Infrastructure: Repositories in /src/data
Current coupling issues found in /src/services/user.ts"
]]></handoff>
  <handoff to="test-agent"><![CDATA[
"Test coverage analysis:
- Unit tests in __tests__/ directories (co-located)
- Integration tests in /tests/integration/
- Missing coverage: /src/services/payment.ts has no tests
- Test patterns: Jest, describe/it structure, mock factories"
]]></handoff>
</handoff-templates>

</knowledge-base>
