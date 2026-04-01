# Software Architecture Best Practices

<knowledge-base name="architecture" version="1.0">
<triggers>architecture, SOLID, Clean Architecture, design pattern, DDD, hexagonal, coupling, cohesion</triggers>
<overview>System design, architectural decisions, SOLID principles, Clean Architecture, DDD, and best practices.</overview>

<solid-principles>
  <principle id="SRP" name="Single Responsibility">
    <rule>A class should have only one reason to change</rule>
    <bad>ReportGenerator that generates AND formats reports</bad>
    <good>Separate ReportGenerator and ReportFormatter</good>
  </principle>
  <principle id="OCP" name="Open/Closed">
    <rule>Open for extension, closed for modification</rule>
    <bad>Modifying Shape class for each new shape type</bad>
    <good>Shape interface with new implementations for each type</good>
  </principle>
  <principle id="LSP" name="Liskov Substitution">
    <rule>Subtypes must be substitutable for base types</rule>
    <bad>Square extending Rectangle but breaking setWidth/setHeight</bad>
    <good>Rethink hierarchy or use composition</good>
  </principle>
  <principle id="ISP" name="Interface Segregation">
    <rule>Many specific interfaces over one general-purpose interface</rule>
    <bad>Single Worker interface with developer, tester, manager methods</bad>
    <good>Separate Developer, Tester, Manager interfaces</good>
  </principle>
  <principle id="DIP" name="Dependency Inversion">
    <rule>Depend on abstractions, not concrete implementations</rule>
    <bad>NotificationService directly depends on EmailSender</bad>
    <good>Depend on IMessageSender interface</good>
  </principle>
</solid-principles>

<clean-architecture>
  <layers>
    <layer rank="1" name="Entities" position="innermost">Enterprise business rules</layer>
    <layer rank="2" name="Use Cases">Application business rules</layer>
    <layer rank="3" name="Interface Adapters">Controllers, presenters, gateways</layer>
    <layer rank="4" name="Frameworks &amp; Drivers" position="outermost">DB, Web, UI</layer>
  </layers>
  <dependency-rule>Source code dependencies must only point inward</dependency-rule>
  <rules>
    <rule>Inner circles contain policies</rule>
    <rule>Outer circles contain mechanisms</rule>
    <rule>Business logic never imports from frameworks</rule>
  </rules>
</clean-architecture>

<hexagonal-architecture name="Ports &amp; Adapters">
  <concept name="Ports">Interfaces defining interactions</concept>
  <concept name="Adapters">Implementations connecting to actual technologies</concept>
  <port type="Driving">External actors interact with app (REST APIs, CLI)</port>
  <port type="Driven">App interacts with external systems (databases, queues)</port>
</hexagonal-architecture>

<ddd-concepts>
  <concept name="Ubiquitous Language">Shared vocabulary between developers and domain experts</concept>
  <concept name="Entities">Objects with unique identity (Customer, Order)</concept>
  <concept name="Value Objects">Defined by attributes, no identity (Money, Address)</concept>
  <concept name="Aggregates">Cluster of domain objects with consistency boundary</concept>
  <concept name="Aggregate Root">Entry point to aggregate (Order contains OrderItems)</concept>
  <concept name="Bounded Context">Explicit boundary where domain model applies</concept>
</ddd-concepts>

<design-patterns>
  <category name="Creational">
    <pattern name="Factory Method">Encapsulates instantiation</pattern>
    <pattern name="Builder">Separates complex construction from representation</pattern>
    <pattern name="Singleton">Single instance (prefer DI over singletons)</pattern>
  </category>
  <category name="Structural">
    <pattern name="Adapter">Converts incompatible interfaces</pattern>
    <pattern name="Decorator">Dynamically adds responsibilities</pattern>
    <pattern name="Facade">Simplifies complex subsystems</pattern>
  </category>
  <category name="Behavioral">
    <pattern name="Strategy">Encapsulates interchangeable algorithms</pattern>
    <pattern name="Observer">One-to-many notification of state changes</pattern>
    <pattern name="Command">Encapsulates requests as objects (undo/redo)</pattern>
  </category>
</design-patterns>

<dependency-injection>
  <rule>Always prefer constructor injection - makes dependencies explicit and immutable</rule>
  <example type="bad"><![CDATA[
class OrderService:
    def __init__(self):
        self.repo = OrderRepository()  # tight coupling
]]></example>
  <example type="good"><![CDATA[
class OrderService:
    def __init__(self, repo: IOrderRepository):
        self.repo = repo  # loose coupling, testable
]]></example>
</dependency-injection>

<core-principles>
  <principle id="DRY" name="Don't Repeat Yourself">
    <rule>Every piece of knowledge has single representation</rule>
    <note>Focus on knowledge duplication, not just textual similarity</note>
  </principle>
  <principle id="KISS" name="Keep It Simple, Stupid">
    <rule>Simplest solution that works is often best</rule>
    <note>Avoid premature optimization</note>
  </principle>
  <principle id="YAGNI" name="You Aren't Gonna Need It">
    <rule>Don't implement functionality before it's needed</rule>
    <note>Balance with good design that makes adding features easy</note>
  </principle>
  <principle id="Coupling">
    <goal>Low coupling - modules can be understood in isolation</goal>
  </principle>
  <principle id="Cohesion">
    <goal>High cohesion - all elements contribute to single purpose</goal>
  </principle>
</core-principles>

<code-organization>
  <structure name="Layered" use="by technical role">controllers/, models/, services/, repositories/</structure>
  <structure name="Feature-based" use="by domain" recommended="true">users/, products/, orders/, payments/</structure>
  <module-guidelines>
    <guideline>Single responsibility</guideline>
    <guideline>Loose coupling with other modules</guideline>
    <guideline>High internal cohesion</guideline>
    <guideline>Clear interfaces</guideline>
    <guideline>No circular dependencies</guideline>
  </module-guidelines>
</code-organization>

<naming-conventions>
  <convention type="Classes" style="PascalCase, nouns">UserManager, PaymentProcessor</convention>
  <convention type="Functions" style="camelCase, verbs">calculateTotal, validateInput</convention>
  <convention type="Booleans" style="Predicates">isActive, hasPermission, canEdit</convention>
  <convention type="Collections" style="Plurals">users, orderItems</convention>
  <convention type="Constants" style="SCREAMING_SNAKE">MAX_RETRY_COUNT, API_TIMEOUT</convention>
  <best-practices>
    <practice>Be descriptive (numberOfActiveUsers not count)</practice>
    <practice>Reveal intent (timeoutInMilliseconds not timeout)</practice>
    <practice>Avoid abbreviations (except id, url, etc.)</practice>
    <practice>Consistent vocabulary (pick fetch/retrieve/get and stick)</practice>
    <practice>Add business context (premiumCustomer not type1Customer)</practice>
  </best-practices>
</naming-conventions>

<testing-trophy>
  <level percent="10%" name="Static Analysis">TypeScript, ESLint</level>
  <level percent="20%" name="Unit Tests">Individual functions in isolation</level>
  <level percent="70%" name="Integration Tests" focus="main">Multiple units working together</level>
  <level percent="10%" name="E2E Tests">Complete user workflows</level>
  <structure>
    <rule>Mirror source structure in tests/ directory</rule>
    <rule>Name: component.test.js or user-flow.integration.test.js</rule>
    <rule>Use Arrange-Act-Assert pattern</rule>
    <rule>Keep tests independent</rule>
  </structure>
</testing-trophy>

<quality-metrics>
  <metric name="Cyclomatic Complexity">
    <range min="1" max="10">Simple, low risk</range>
    <range min="11" max="20">Moderate complexity</range>
    <range min="21" max="50">Complex, high risk</range>
    <range min="51" max="999">Untestable - refactor immediately</range>
  </metric>
  <size-guidelines>
    <guideline type="Functions" max="50 lines" ideal="20 lines"/>
    <guideline type="Classes" max="400 statements"/>
    <guideline type="Files" max="500-1000 lines"/>
  </size-guidelines>
</quality-metrics>

<anti-patterns>
  <anti-pattern name="God Object" problem="Class doing too much (&gt;200 lines)" solution="Split by responsibility"/>
  <anti-pattern name="Anemic Domain" problem="All logic in services" solution="Put behavior in domain objects"/>
  <anti-pattern name="Circular Dependencies" problem="A imports B imports A" solution="Dependency injection, events"/>
  <anti-pattern name="Missing Error Handling" problem="Only happy path" solution="Handle all edge cases"/>
  <anti-pattern name="Hardcoded Config" problem="Magic strings/numbers" solution="Environment variables, config files"/>
  <anti-pattern name="Tight Coupling" problem="Direct concrete dependencies" solution="Depend on abstractions"/>
  <anti-pattern name="Layer Violations" problem="Domain calling infrastructure" solution="Respect dependency direction"/>
</anti-patterns>

<security-architecture>
  <principles>
    <principle name="Defense in depth">Multiple security layers</principle>
    <principle name="Least privilege">Minimum permissions necessary</principle>
    <principle name="Security by design">Threat modeling during design</principle>
    <principle name="Zero trust">Never trust, always verify</principle>
  </principles>
  <checklist>
    <item>Strong authentication (MFA where possible)</item>
    <item>Authorization checks on every protected resource</item>
    <item>All inputs validated server-side</item>
    <item>Output encoding to prevent XSS</item>
    <item>Sensitive data encrypted at rest and in transit</item>
    <item>Security events logged</item>
    <item>No sensitive data in logs or error messages</item>
  </checklist>
</security-architecture>

<red-flags>
  <category name="Code">
    <flag>Hard-coded credentials</flag>
    <flag>SQL queries concatenated with user input</flag>
    <flag>No input validation on external data</flag>
    <flag>Exceptions caught and ignored</flag>
    <flag>Functions over 100 lines</flag>
  </category>
  <category name="Architecture">
    <flag>Circular dependencies between modules</flag>
    <flag>Business logic in presentation layer</flag>
    <flag>No abstraction for external services</flag>
    <flag>Single point of failure</flag>
  </category>
  <category name="Security">
    <flag>Authentication bypassable</flag>
    <flag>Sensitive data logged</flag>
    <flag>HTTPS not enforced</flag>
    <flag>Unpatched dependencies with known CVEs</flag>
  </category>
</red-flags>

<adr-template title="Architecture Decision Records"><![CDATA[
# ADR-XXX: [Title]

## Status
[Proposed | Accepted | Deprecated | Superseded]

## Context
[Problem and constraints]

## Options Considered
1. [Option A]
2. [Option B]
3. [Option C]

## Decision
[Chosen option]

## Consequences
+ [Positive outcomes]
- [Negative outcomes]
]]></adr-template>

<validation-rules>
  <rule>Functions should do one thing</rule>
  <rule>Keep abstractions at consistent levels</rule>
  <rule>Dependencies should point inward</rule>
  <rule>Fail fast on invalid state</rule>
  <rule>Prefer composition over inheritance</rule>
</validation-rules>

</knowledge-base>
