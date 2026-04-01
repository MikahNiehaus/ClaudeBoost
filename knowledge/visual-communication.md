# Visual Communication Knowledge Base

<knowledge-base name="visual-communication" version="1.0">
<triggers>explain, diagram, visual, architecture, show me, how does, what does, structure, flow, why</triggers>
<overview>Templates and guidelines for visual ASCII diagram communication. Orchestrator's DEFAULT mode per RULE-021.</overview>

<frameworks>

<framework id="SOLID">
  <principle id="SRP" desc="One class, one reason to change" annotation="SRP: [responsibility]"/>
  <principle id="OCP" desc="Extend without modifying" annotation="OCP: [extension point]"/>
  <principle id="LSP" desc="Subtypes replace base types" annotation="LSP: [substitution]"/>
  <principle id="ISP" desc="Small, focused interfaces" annotation="ISP: [interface scope]"/>
  <principle id="DIP" desc="Depend on abstractions" annotation="DIP: [abstraction name]"/>
</framework>

<framework id="GoF" name="Gang of Four">
  <category name="Creational">
    <pattern name="Factory Method" when="Object creation varies" annotation="GoF: Factory Method"/>
    <pattern name="Abstract Factory" when="Families of related objects" annotation="GoF: Abstract Factory"/>
    <pattern name="Builder" when="Complex object construction" annotation="GoF: Builder"/>
    <pattern name="Prototype" when="Clone existing objects" annotation="GoF: Prototype"/>
    <pattern name="Singleton" when="Exactly one instance" annotation="GoF: Singleton"/>
  </category>
  <category name="Structural">
    <pattern name="Adapter" when="Interface incompatibility" annotation="GoF: Adapter"/>
    <pattern name="Bridge" when="Separate abstraction/impl" annotation="GoF: Bridge"/>
    <pattern name="Composite" when="Tree structures" annotation="GoF: Composite"/>
    <pattern name="Decorator" when="Add behavior dynamically" annotation="GoF: Decorator"/>
    <pattern name="Facade" when="Simplify subsystem" annotation="GoF: Facade"/>
    <pattern name="Flyweight" when="Share common state" annotation="GoF: Flyweight"/>
    <pattern name="Proxy" when="Control access" annotation="GoF: Proxy"/>
  </category>
  <category name="Behavioral">
    <pattern name="Chain of Responsibility" when="Pass request along chain" annotation="GoF: Chain of Resp"/>
    <pattern name="Command" when="Encapsulate request" annotation="GoF: Command"/>
    <pattern name="Iterator" when="Traverse collection" annotation="GoF: Iterator"/>
    <pattern name="Mediator" when="Centralize communication" annotation="GoF: Mediator"/>
    <pattern name="Memento" when="Capture/restore state" annotation="GoF: Memento"/>
    <pattern name="Observer" when="Notify subscribers" annotation="GoF: Observer"/>
    <pattern name="State" when="Behavior varies by state" annotation="GoF: State"/>
    <pattern name="Strategy" when="Swap algorithms" annotation="GoF: Strategy"/>
    <pattern name="Template Method" when="Define algorithm skeleton" annotation="GoF: Template Method"/>
    <pattern name="Visitor" when="Add operations externally" annotation="GoF: Visitor"/>
  </category>
</framework>

<framework id="OOP" name="Four Pillars">
  <pillar id="Encapsulation" desc="Bundle data + methods, hide internals" annotation="OOP: Encapsulated [what]"/>
  <pillar id="Abstraction" desc="Hide complexity, show essential features" annotation="OOP: Abstracted [what]"/>
  <pillar id="Inheritance" desc="Create subclass from parent (IS-A)" annotation="OOP: Inherits [parent]"/>
  <pillar id="Polymorphism" desc="Same interface, different behavior" annotation="OOP: Polymorphic [interface]"/>
</framework>

<framework id="TDD" name="Red-Green-Refactor">
  <phase id="Red" desc="Write failing test first" annotation="TDD: Test written for [behavior]"/>
  <phase id="Green" desc="Minimum code to pass" annotation="TDD: Passes [test name]"/>
  <phase id="Refactor" desc="Improve without breaking" annotation="TDD: Refactored [what]"/>
  <test-pyramid top="E2E (few, slow)" middle="Integration (some, medium)" base="Unit (many, fast)"/>
</framework>

<framework id="DDD" name="Domain-Driven Design">
  <concept name="Entity" desc="Has unique identity" annotation="DDD: Entity"/>
  <concept name="Value Object" desc="Defined by attributes, immutable" annotation="DDD: Value Object"/>
  <concept name="Aggregate" desc="Consistency boundary" annotation="DDD: Aggregate"/>
  <concept name="Aggregate Root" desc="Entry point for aggregate" annotation="DDD: Aggregate Root"/>
  <concept name="Bounded Context" desc="Model boundary, ubiquitous language" annotation="DDD: Bounded Context"/>
  <concept name="Domain Event" desc="Something significant happened" annotation="DDD: Domain Event"/>
  <concept name="Repository" desc="Collection-like interface for aggregates" annotation="DDD: Repository"/>
  <concept name="Domain Service" desc="Stateless domain operation" annotation="DDD: Domain Service"/>
</framework>

<framework id="CIA" name="Security Triad">
  <aspect id="C" name="Confidentiality" questions="Who can see? Is it encrypted? Are access logs kept?"/>
  <aspect id="I" name="Integrity" questions="Can it be tampered with? Is it signed? Are changes tracked?"/>
  <aspect id="A" name="Availability" questions="What if this fails? Is there redundancy? What's recovery time?"/>
</framework>

<framework id="GRASP" name="General Responsibility Assignment">
  <pattern name="Information Expert" desc="Assign to class with needed info" annotation="GRASP: Expert [class]"/>
  <pattern name="Creator" desc="Who creates instances?" annotation="GRASP: Creator [class]"/>
  <pattern name="Controller" desc="First object receiving UI events" annotation="GRASP: Controller [class]"/>
  <pattern name="Low Coupling" desc="Minimize dependencies" annotation="GRASP: Low coupling via [how]"/>
  <pattern name="High Cohesion" desc="Focused, related responsibilities" annotation="GRASP: Cohesive [class]"/>
  <pattern name="Polymorphism" desc="Use polymorphism for varying behavior" annotation="GRASP: Polymorphic [interface]"/>
  <pattern name="Pure Fabrication" desc="Artificial class for cohesion/coupling" annotation="GRASP: Fabrication [class]"/>
  <pattern name="Indirection" desc="Intermediate object to decouple" annotation="GRASP: Indirection via [what]"/>
  <pattern name="Protected Variations" desc="Wrap instability points" annotation="GRASP: Protected [variation]"/>
</framework>

<framework id="CleanCode">
  <principle name="Meaningful Names" annotation="Clean: Named [intent]" rule="Classes=nouns, Methods=verbs"/>
  <principle name="Small Functions" annotation="Clean: Small [lines]" rule="< 20 lines ideal"/>
  <principle name="Single Purpose" annotation="Clean: Single purpose [what]" rule="One thing well"/>
  <principle name="No Side Effects" annotation="Clean: Pure function" rule="Input to output only"/>
</framework>

<framework id="KISS-DRY-YAGNI">
  <principle id="KISS" desc="Keep It Simple, Stupid" annotation="KISS: Simplified [how]" antipattern="Over-engineering"/>
  <principle id="DRY" desc="Don't Repeat Yourself" annotation="DRY: Extracted [what]" antipattern="Copy-paste code"/>
  <principle id="YAGNI" desc="You Aren't Gonna Need It" annotation="YAGNI: Removed [what]" antipattern="Speculative features"/>
</framework>

</frameworks>

<architectures>

<architecture id="CleanArchitecture"><![CDATA[
+-------------------------------------------+
|           Frameworks & Drivers             |  ← Outermost: DB, Web, UI
|  +-------------------------------------+  |
|  |         Interface Adapters          |  |  ← Controllers, Presenters, Gateways
|  |  +-------------------------------+  |  |
|  |  |          Use Cases            |  |  |  ← Application business rules
|  |  |  +-------------------------+  |  |  |
|  |  |  |       Entities          |  |  |  |  ← Enterprise business rules
|  |  |  +-------------------------+  |  |  |
|  |  +-------------------------------+  |  |
|  +-------------------------------------+  |
+-------------------------------------------+
CA RULE: Dependencies ONLY point inward
]]></architecture>

<architecture id="Hexagonal" name="Ports &amp; Adapters"><![CDATA[
     [Web UI]  [CLI]  [API Client]
          \     |     /
           v    v    v
    +─────────────────────────+
    |    PRIMARY ADAPTERS     |  ← Driving adapters
    +─────────────────────────+
               │
    +─────────────────────────+
    |     PRIMARY PORTS       |  ← Input interfaces
    +─────────────────────────+
               │
    +─────────────────────────+
    |    APPLICATION CORE     |  ← Business logic
    +─────────────────────────+
               │
    +─────────────────────────+
    |    SECONDARY PORTS      |  ← Output interfaces
    +─────────────────────────+
               │
    +─────────────────────────+
    |   SECONDARY ADAPTERS    |  ← Driven adapters
    +─────────────────────────+
               │
     [Database] [Email] [Gateway]

Key: Domain is ISOLATED from external concerns
]]></architecture>

<architecture id="CQRS"><![CDATA[
   [Client Request]
          │
          ├──────────────────────┐
          ▼                      ▼
   +-------------+        +-------------+
   |   COMMAND   |        |    QUERY    |
   |   (Write)   |        |   (Read)    |
   +-------------+        +-------------+
          │                      │
   +-------------+        +-------------+
   | Write Model |        | Read Model  |
   | (Normalized)|        |(Denormalized|
   +-------------+        +-------------+
          │      [Event]       │
          └────────►◄──────────┘

Commands: Change state, return void/ID
Queries: Return data, no side effects
]]></architecture>

<architecture id="EventSourcing"><![CDATA[
Traditional:              Event Sourced:
+-----------+             +-----------+
| Current   |             | Event 1   | → OrderCreated
| State     |             | Event 2   | → ItemAdded
| (Latest)  |             | Event 3   | → OrderPaid
+-----------+             +-----------+
                                │ Replay
                          +-----------+
                          | Current   |
                          +-----------+

Benefits: Audit trail, time travel, event replay
Challenges: Eventual consistency, schema evolution
]]></architecture>

</architectures>

<diagram-templates>

<template id="layered-architecture" use="Component relationships, system structure"><![CDATA[
+================================================================+
|                         LAYER NAME                              |
|                    (Layer Type: Domain/App/Infra)               |
+================================================================+
|  +---------------------------+  +---------------------------+   |
|  |      Component A          |  |      Component B          |   |
|  |  SRP: [responsibility]    |  |  SRP: [responsibility]    |   |
|  +---------------------------+  +---------------------------+   |
|             |                              |                    |
|             +------------+  +--------------+                    |
|                          v  v                                   |
|                   +-------------+                               |
|                   | Interface   |  ← DIP: Abstraction           |
|                   +-------------+                               |
+================================================================+
| CA: [Clean Architecture layer rule]                             |
| GoF: [Patterns used]                                            |
+================================================================+
]]></template>

<template id="request-flow" use="Logic explanation, conditional behavior, process flows"><![CDATA[
[Input/Request]
       │
+------------------+
|   ENTRY POINT    |  ← CA: Interface Adapter
+------------------+
       │
+------------------+
|   DECISION       |
+------------------+
       │
       ├── YES ─────────► [Action A]  ← OCP: Extended via [X]
       │
       └── NO ──────────► [Action B]  ← GoF: [Pattern]
]]></template>

<template id="component-interaction" use="Communication, data flow, API interactions"><![CDATA[
+------------+     +------------+     +------------+
|  Client    | --> | Interface  | --> |   Impl     |
|            |     | (Port)     |     | (Adapter)  |
+------------+     +------------+     +------------+
                         ^
                   DIP: Depends on abstraction
                   CA: Port separates domain from infrastructure
]]></template>

<template id="security-box" use="Security-relevant explanations" required="always-for-security"><![CDATA[
+================================================================+
|                      SECURITY DECISION                          |
+================================================================+
| CIA Impact:                                                     |
|   - Confidentiality: [How this protects/exposes data]           |
|   - Integrity: [How this ensures data accuracy]                 |
|   - Availability: [How this affects system access]              |
+================================================================+
| OWASP Relevance: [A01-A10 if applicable]                        |
| Threat Model: [What threats does this address?]                 |
+================================================================+
]]></template>

<template id="comparison-matrix" use="Evaluating alternatives, showing trade-offs"><![CDATA[
+==================+============+============+============+
|     Criterion    |  Option A  |  Option B  |  Option C  |
+==================+============+============+============+
| SOLID Compliance |    HIGH    |   MEDIUM   |    LOW     |
| Maintainability  |    HIGH    |    HIGH    |   MEDIUM   |
| Performance      |   MEDIUM   |    HIGH    |    HIGH    |
+==================+============+============+============+
| Selected: Option [X]                                     |
| Rationale: [principle-based reason]                      |
+==========================================================+
]]></template>

<template id="before-after" use="Showing violations and fixes, code evolution"><![CDATA[
BEFORE (Violations)                AFTER (Compliant)
+-------------------+             +-------------------+
| GodClass          |             | ClassA            |
| - method1()       |    SRP      | - responsibility1 |
| - method2()       |   ====>     +-------------------+
| [SRP VIOLATION]   |             | ClassB            |
+-------------------+             | - responsibility2 |
                                  +-------------------+
OCP: Now each can extend independently
DIP: Classes depend on interfaces, not each other
]]></template>

<template id="di-flow" use="Explaining dependency injection wiring"><![CDATA[
+-------------------------------------------+
|           DI Container (Startup)           |
+-------------------------------------------+
|  Register:                                |
|  │ IService → ConcreteService             |
|  │ IRepository → SqlRepository            |
+-------------------------------------------+
              │ At Runtime
+-------------------------------------------+
|           Consumer Created                 |
|  new Controller(container.Resolve<IService>())  |
|  DIP: Depends on abstraction, not impl    |
+-------------------------------------------+
]]></template>

</diagram-templates>

<response-guidelines>
  <guideline complexity="simple" diagram="1 small box" annotations="1-2" example="What does X do?"/>
  <guideline complexity="medium" diagram="2-3 connected boxes" annotations="3-4" example="How does X work?"/>
  <guideline complexity="complex" diagram="Full layered diagram" annotations="5+" example="Design for X"/>
  <guideline complexity="security" diagram="Include CIA box" annotations="CIA + OWASP ref" example="Is this secure?"/>
</response-guidelines>

<annotation-formats>
  <annotation type="SRP" format="SRP: [reason]" example="SRP: Handles only user validation"/>
  <annotation type="OCP" format="OCP: [extension point]" example="OCP: New validators via interface"/>
  <annotation type="LSP" format="LSP: [substitution note]" example="LSP: All handlers interchangeable"/>
  <annotation type="ISP" format="ISP: [interface focus]" example="ISP: Read-only vs read-write split"/>
  <annotation type="DIP" format="DIP: [abstraction]" example="DIP: Depends on IRepository"/>
  <annotation type="GoF" format="GoF: [Pattern]" example="GoF: Strategy for algorithms"/>
  <annotation type="DDD" format="DDD: [concept]" example="DDD: Aggregate root boundary"/>
  <annotation type="CA" format="CA: [layer rule]" example="CA: Domain knows no frameworks"/>
  <annotation type="CIA" format="CIA: [aspect]" example="CIA: C - encrypted at rest"/>
</annotation-formats>

<complete-example title="Order Processing System"><![CDATA[
+================================================================+
|                   ORDER PROCESSING SYSTEM                       |
|                    (Clean Architecture)                         |
+================================================================+
|   [Customer Request]                                            |
|          │                                                      |
|   +---------------------------+                                 |
|   |    OrderController        |  ← CA: Interface Adapter        |
|   |    (HTTP concerns only)   |    SRP: HTTP request handling   |
|   +---------------------------+                                 |
|          │                                                      |
|   +---------------------------+                                 |
|   |    PlaceOrderUseCase      |  ← CA: Application Layer        |
|   |    (orchestrates flow)    |    SRP: Order placement logic   |
|   +---------------------------+                                 |
|          │                                                      |
|          ├───────────────┬───────────────┐                     |
|          ▼               ▼               ▼                      |
|   +-------------+  +-------------+  +-------------+            |
|   | IOrderRepo  |  | IPaymentSvc |  | IInventory  |  ← Ports   |
|   +-------------+  +-------------+  +-------------+            |
|          │               │               │                      |
|   DIP: Use case depends on abstractions only                   |
|          ▼               ▼               ▼                      |
|   +-------------+  +-------------+  +-------------+            |
|   | SqlOrderRepo|  | StripeGateway|  | WarehouseAPI| ← Adapters|
|   +-------------+  +-------------+  +-------------+            |
+================================================================+
|  DDD: Order=Aggregate Root, OrderLine=Entity, Money=ValueObject |
|  GoF: Strategy (payment), Repository, Observer (events)         |
|  CIA: C=tokenized payments, I=server-side totals, A=retry logic |
+================================================================+
]]></complete-example>

<integration-rule ref="RULE-021">
  <step order="1">Identify question category (simple/medium/complex/security)</step>
  <step order="2">Select appropriate diagram template</step>
  <step order="3">Add principle annotations</step>
  <step order="4">Include CIA box if security-relevant</step>
  <step order="5">Conclude with key insight summary</step>
  <mandatory>Every explanation includes at least ONE framework annotation</mandatory>
</integration-rule>

</knowledge-base>
