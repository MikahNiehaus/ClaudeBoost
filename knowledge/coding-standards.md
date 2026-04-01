# Coding Standards & Best Practices

<knowledge-base name="coding-standards" version="1.0">
<triggers>SOLID, OOP, design pattern, Gang of Four, GoF, abstraction, clean code, code quality, coding standard, best practice, principle</triggers>
<overview>Standards ALL code-producing agents MUST validate against before reporting COMPLETE. Referenced by RULE-017.</overview>

<priority-hierarchy>
  <priority rank="1">Security (never compromise)</priority>
  <priority rank="2">Correctness (code must work)</priority>
  <priority rank="3">Maintainability (others must understand)</priority>
  <priority rank="4">Performance (within requirements)</priority>
  <priority rank="5">Simplicity (less is more)</priority>
</priority-hierarchy>

<solid-principles>

<principle id="SRP" name="Single Responsibility">
  <definition>A class should have only one reason to change</definition>
  <checklist>
    <check>Can you describe what this class does in one sentence without "and"?</check>
    <check>Does this class have only one actor that would request changes?</check>
    <check>Are all methods related to the class's single purpose?</check>
    <check>Would changing one feature require changing unrelated methods?</check>
  </checklist>
  <violations>
    <sign>Class name contains "And" or "Manager" or "Handler"</sign>
    <sign>Class has methods for unrelated concerns (User with sendEmail)</sign>
    <sign>Change in one feature breaks unrelated tests</sign>
    <sign>Class imports from many unrelated modules</sign>
  </violations>
  <fix-patterns>Extract Class, Extract Interface</fix-patterns>
  <example type="violation"><![CDATA[
class User:
    def save(self): db.save(self)
    def send_welcome_email(self):  # Wrong responsibility!
        email_service.send(self.email, "Welcome!")
  ]]></example>
  <example type="fixed"><![CDATA[
class User:
    def save(self): db.save(self)

class UserNotificationService:
    def send_welcome_email(self, user):
        email_service.send(user.email, "Welcome!")
  ]]></example>
</principle>

<principle id="OCP" name="Open/Closed">
  <definition>Software entities should be open for extension but closed for modification</definition>
  <checklist>
    <check>Can new behavior be added without modifying existing code?</check>
    <check>Are there extension points (interfaces, abstract classes, hooks)?</check>
    <check>Does adding a new case require changing switch/if-else chains?</check>
    <check>Is the code parameterized for variation?</check>
  </checklist>
  <violations>
    <sign>Adding feature requires modifying existing switch statements</sign>
    <sign>Type-checking conditionals (if isinstance(x, TypeA))</sign>
    <sign>Hardcoded behaviors that could vary</sign>
    <sign>No abstraction layer for varying behaviors</sign>
  </violations>
  <fix-patterns>Strategy Pattern, Template Method, Plugin Architecture</fix-patterns>
  <example type="violation"><![CDATA[
def calculate_area(shape):
    if shape.type == "circle": return 3.14 * shape.radius ** 2
    elif shape.type == "rectangle": return shape.width * shape.height
    # Must add new elif for each shape!
  ]]></example>
  <example type="fixed"><![CDATA[
class Shape(ABC):
    @abstractmethod
    def area(self) -> float: pass

class Circle(Shape):
    def area(self): return 3.14 * self.radius ** 2

class Rectangle(Shape):
    def area(self): return self.width * self.height
# New shapes just implement Shape - no modification needed!
  ]]></example>
</principle>

<principle id="LSP" name="Liskov Substitution">
  <definition>Subtypes must be substitutable for their base types without altering program correctness</definition>
  <checklist>
    <check>Can any subclass replace the parent without breaking behavior?</check>
    <check>Do subclasses honor all parent contracts (pre/postconditions)?</check>
    <check>Does subclass throw unexpected exceptions?</check>
    <check>Are return types consistent (covariant)?</check>
    <check>Are parameter types consistent (contravariant)?</check>
  </checklist>
  <violations>
    <sign>Subclass throws NotImplementedError for parent methods</sign>
    <sign>Subclass narrows acceptable inputs</sign>
    <sign>Subclass returns unexpected types</sign>
    <sign>Code checks isinstance() to handle subclass differently</sign>
    <sign>"Square extends Rectangle" problems</sign>
  </violations>
  <fix-patterns>Extract Interface, Replace Inheritance with Composition</fix-patterns>
  <example type="violation"><![CDATA[
class Square(Rectangle):  # Violates LSP!
    def set_width(self, width):
        self._width = width
        self._height = width  # Unexpected side effect!
# rect.set_width(5); rect.set_height(10); assert rect.area() == 50  # Fails!
  ]]></example>
  <example type="fixed"><![CDATA[
class Shape(ABC):
    @abstractmethod
    def area(self) -> float: pass

class Rectangle(Shape): ...  # Independent implementations
class Square(Shape): ...     # No inheritance relationship
  ]]></example>
</principle>

<principle id="ISP" name="Interface Segregation">
  <definition>Clients should not be forced to depend on interfaces they don't use</definition>
  <checklist>
    <check>Are interfaces small and focused?</check>
    <check>Do any implementations have empty/stub methods?</check>
    <check>Do clients use all methods of interfaces they depend on?</check>
    <check>Could the interface be split into smaller, cohesive parts?</check>
  </checklist>
  <violations>
    <sign>Interface with 10+ methods</sign>
    <sign>Implementations with pass or raise NotImplementedError</sign>
    <sign>Classes implementing interfaces they only partially need</sign>
    <sign>"Fat interfaces" that serve multiple client types</sign>
  </violations>
  <fix-patterns>Split Interface, Role Interface</fix-patterns>
  <example type="violation"><![CDATA[
class Worker(ABC):
    def work(self): pass
    def eat(self): pass
    def sleep(self): pass

class Robot(Worker):
    def work(self): print("Working...")
    def eat(self): pass   # Robots don't eat! Forced to implement.
    def sleep(self): pass # Robots don't sleep!
  ]]></example>
  <example type="fixed"><![CDATA[
class Workable(ABC):
    def work(self): pass

class Robot(Workable):  # Only implements what it needs
    def work(self): print("Working...")
  ]]></example>
</principle>

<principle id="DIP" name="Dependency Inversion">
  <definition>High-level modules should not depend on low-level modules. Both should depend on abstractions.</definition>
  <checklist>
    <check>Do classes depend on interfaces/abstractions, not concrete implementations?</check>
    <check>Are dependencies injected rather than instantiated internally?</check>
    <check>Can implementations be swapped without changing dependent code?</check>
    <check>Are imports from stable abstractions, not volatile concretions?</check>
  </checklist>
  <violations>
    <sign>new keyword inside business logic</sign>
    <sign>Direct imports of concrete implementations</sign>
    <sign>Hardcoded class instantiation</sign>
    <sign>Cannot mock dependencies for testing</sign>
  </violations>
  <fix-patterns>Dependency Injection, Abstract Factory, Service Locator</fix-patterns>
  <example type="violation"><![CDATA[
class OrderService:
    def __init__(self):
        self.db = MySQLDatabase()  # Hardcoded!
        self.mailer = SMTPMailer() # Hardcoded!
  ]]></example>
  <example type="fixed"><![CDATA[
class OrderService:
    def __init__(self, db: Database, mailer: Mailer):
        self.db = db       # Injected abstraction
        self.mailer = mailer
# Can inject any implementation: OrderService(PostgresDB(), SendGrid())
  ]]></example>
</principle>

</solid-principles>

<gof-patterns>
  <overview>Before using a pattern: Is it solving a real problem? Is complexity justified? Would simpler work?</overview>

  <pattern-group name="Creational">
    <pattern name="Factory Method" when="Object creation varies by context" avoid="Creation logic is trivial"/>
    <pattern name="Abstract Factory" when="Family of related objects needed" avoid="Only one product type"/>
    <pattern name="Builder" when="Complex object with many optional parts" avoid="Object is simple"/>
    <pattern name="Singleton" when="Exactly one instance needed globally" avoid="State causes testing issues"/>
  </pattern-group>

  <pattern-group name="Structural">
    <pattern name="Adapter" when="Interface incompatibility" avoid="Can modify the source"/>
    <pattern name="Decorator" when="Add behavior dynamically" avoid="Static composition works"/>
    <pattern name="Facade" when="Simplify complex subsystem" avoid="Already simple"/>
    <pattern name="Proxy" when="Control access to object" avoid="Direct access is fine"/>
  </pattern-group>

  <pattern-group name="Behavioral">
    <pattern name="Observer" when="One-to-many notification" avoid="Tight coupling acceptable"/>
    <pattern name="Strategy" when="Interchangeable algorithms" avoid="Algorithm never varies"/>
    <pattern name="Command" when="Encapsulate requests as objects" avoid="Simple direct calls work"/>
    <pattern name="Template Method" when="Algorithm with variant steps" avoid="No invariant structure"/>
    <pattern name="State" when="Behavior changes with state" avoid="Few states, simple logic"/>
  </pattern-group>

  <anti-patterns>
    <anti-pattern name="Singleton abuse" problem="Global state, testing issues" fix="Use dependency injection"/>
    <anti-pattern name="Factory for everything" problem="Unnecessary indirection" fix="Direct instantiation if simple"/>
    <anti-pattern name="Over-decorated" problem="Too many layers" fix="Flatten if not needed"/>
    <anti-pattern name="Observer spaghetti" problem="Can't track listeners" fix="Use explicit event handling"/>
    <anti-pattern name="Strategy overkill" problem="One algorithm that never changes" fix="Inline the logic"/>
  </anti-patterns>

  <selection-shortcuts>
    <shortcut need="One instance" pattern="Singleton (consider DI first)"/>
    <shortcut need="Creating objects varies" pattern="Factory Method"/>
    <shortcut need="Family of objects" pattern="Abstract Factory"/>
    <shortcut need="Complex construction" pattern="Builder"/>
    <shortcut need="Incompatible interface" pattern="Adapter"/>
    <shortcut need="Add behavior dynamically" pattern="Decorator"/>
    <shortcut need="Simplify subsystem" pattern="Facade"/>
    <shortcut need="Control access" pattern="Proxy"/>
    <shortcut need="Notify many objects" pattern="Observer"/>
    <shortcut need="Swap algorithms" pattern="Strategy"/>
    <shortcut need="Vary algorithm steps" pattern="Template Method"/>
    <shortcut need="Behavior depends on state" pattern="State"/>
  </selection-shortcuts>
</gof-patterns>

<code-metrics>
  <hard-limits description="MUST enforce">
    <metric name="Cyclomatic complexity" max="10" unit="per method" action="Extract methods"/>
    <metric name="Method length" max="40" unit="lines" action="Extract methods"/>
    <metric name="Class length" max="300" unit="lines" action="Extract classes"/>
    <metric name="Parameter count" max="4" action="Introduce Parameter Object"/>
    <metric name="Nesting depth" max="3" unit="levels" action="Extract, early return"/>
    <metric name="Inheritance depth" max="3" unit="levels" action="Favor composition"/>
  </hard-limits>

  <soft-limits description="SHOULD enforce">
    <metric name="Test coverage" target="≥80%" guidance="Focus on critical paths"/>
    <metric name="Duplication" target="≤3%" guidance="DRY, but don't over-abstract"/>
    <metric name="Dependencies per class" target="≤5" guidance="More suggests SRP violation"/>
    <metric name="Public methods per class" target="≤7" guidance="More suggests ISP violation"/>
  </soft-limits>

  <cyclomatic-complexity>
    <formula>1 + number of decision points</formula>
    <decision-points>if, elif, while, for, case, catch/except, AND/OR operators, ternary</decision-points>
  </cyclomatic-complexity>
</code-metrics>

<oop-practices>
  <composition-over-inheritance>
    <prefer-composition>
      <when>Relationship is "has-a" not "is-a"</when>
      <when>Behavior needs to change at runtime</when>
      <when>Multiple behaviors need to be combined</when>
      <when>Inheritance hierarchy would be deep</when>
    </prefer-composition>
    <use-inheritance>
      <when>True "is-a" relationship exists</when>
      <when>Behavior is truly shared and stable</when>
      <when>Framework requires it</when>
    </use-inheritance>
  </composition-over-inheritance>

  <encapsulation-rules>
    <rule>Make fields private by default</rule>
    <rule>Expose only what's necessary</rule>
    <rule>Use getters/setters for controlled access</rule>
    <rule>Never expose internal collections directly</rule>
    <rule>Immutable by default where possible</rule>
  </encapsulation-rules>

  <cohesion>
    <high-cohesion-indicators>
      <indicator>All methods use most instance variables</indicator>
      <indicator>Methods relate to single concept</indicator>
      <indicator>Class name clearly describes purpose</indicator>
      <indicator>Easy to test in isolation</indicator>
    </high-cohesion-indicators>
    <low-cohesion-indicators>
      <indicator>Methods fall into unrelated groups</indicator>
      <indicator>Some methods don't use instance state</indicator>
      <indicator>Class has multiple responsibilities</indicator>
      <indicator>Hard to name the class</indicator>
    </low-cohesion-indicators>
  </cohesion>
</oop-practices>

<abstraction-guidelines>
  <naming-spectrum>
    <level type="too-abstract">DataProcessor, Manager, Handler</level>
    <level type="just-right">InvoiceValidator, OrderService, PaymentGateway</level>
    <level type="too-concrete">InvoiceFieldLengthChecker, OrderDatabaseSaverAndEmailer</level>
  </naming-spectrum>

  <when-to-abstract>
    <do-abstract>Multiple implementations exist or likely</do-abstract>
    <do-abstract>Implementation details should be hidden</do-abstract>
    <do-abstract>Code needs to be testable in isolation</do-abstract>
    <do-abstract>Feature will have variations</do-abstract>
    <dont-abstract>Only one implementation ever</dont-abstract>
    <dont-abstract>Abstraction adds complexity without benefit</dont-abstract>
    <dont-abstract>YAGNI applies</dont-abstract>
    <dont-abstract>Abstraction leaks implementation details anyway</dont-abstract>
  </when-to-abstract>

  <leaky-abstraction-signs>
    <sign>Clients need implementation knowledge to use correctly</sign>
    <sign>Exception types reveal implementation (SQLException from repository)</sign>
    <sign>Configuration requires implementation-specific settings</sign>
    <sign>Performance characteristics vary unexpectedly</sign>
  </leaky-abstraction-signs>
</abstraction-guidelines>

<code-smells>
  <smell name="Long Method" fix="Extract Method"/>
  <smell name="Large Class" fix="Extract Class"/>
  <smell name="Long Parameter List" fix="Introduce Parameter Object"/>
  <smell name="Switch Statements" fix="Replace with Polymorphism"/>
  <smell name="Duplicate Code" fix="Extract Method/Class"/>
  <smell name="Feature Envy" fix="Move Method"/>
  <smell name="Data Clumps" fix="Extract Class"/>
  <smell name="Primitive Obsession" fix="Replace with Value Object"/>
  <smell name="Inappropriate Intimacy" fix="Move Method, Extract Class"/>
  <smell name="Message Chains" fix="Hide Delegate"/>
</code-smells>

<forbidden-libraries>
  <overview>Libraries that MUST NOT be used unless the user explicitly requests them. Agents MUST check imports against this list.</overview>
  <library name="jQuery" packages="jquery, jquery-slim, jquery-ui, jquery-migrate">
    <status>BANNED</status>
    <reason>Deprecated in ViveryAscend codebase. Modern frameworks and native APIs provide equivalent functionality.</reason>
    <detection>
      <import-pattern>import $ from 'jquery'</import-pattern>
      <import-pattern>import jQuery from 'jquery'</import-pattern>
      <import-pattern>require('jquery')</import-pattern>
      <import-pattern>$.ajax, $.get, $.post, $(selector)</import-pattern>
      <script-pattern>&lt;script src=".*jquery.*"&gt;</script-pattern>
    </detection>
    <alternatives>
      <alternative context="DOM manipulation">Vanilla JS: document.querySelector(), element.classList, element.style</alternative>
      <alternative context="React/Next.js">React refs (useRef), state (useState/useReducer), effects (useEffect)</alternative>
      <alternative context="AJAX/HTTP">Native fetch() API or Next.js server actions, SWR, React Query</alternative>
      <alternative context="Animation">CSS transitions/animations or Framer Motion</alternative>
      <alternative context="Event handling">Native addEventListener() or React synthetic events</alternative>
    </alternatives>
    <override>ONLY permitted if user explicitly requests jQuery</override>
    <severity>HIGH - blocker in code review</severity>
  </library>
</forbidden-libraries>

<validation-template><![CDATA[
## Standards Compliance Check

### SOLID Principles
- [ ] **SRP**: Each class has single responsibility
- [ ] **OCP**: Design supports extension without modification
- [ ] **LSP**: Subtypes are substitutable for base types
- [ ] **ISP**: Interfaces are small and focused
- [ ] **DIP**: Dependencies point to abstractions

### Code Metrics
- [ ] Cyclomatic complexity ≤ 10 per method
- [ ] Method length ≤ 40 lines
- [ ] Class length ≤ 300 lines
- [ ] Parameter count ≤ 4
- [ ] Nesting depth ≤ 3

### Forbidden Libraries
- [ ] No jQuery imports or usage detected
- [ ] No other banned library imports detected

### Logging & Observability
- [ ] Error handlers log with context (entity IDs, error details) — BLOCKER if missing
- [ ] Code with side effects includes appropriate logging
- [ ] Log levels match severity (ERROR/WARN/INFO/DEBUG)
- [ ] No sensitive data in log statements

### Violations Found
| Principle | Location | Issue | Severity |
|-----------|----------|-------|----------|

### Fixes Applied
[Describe how violations were addressed]
]]></validation-template>

<quick-reference>
  <solid-one-liner id="S">One class, one reason to change</solid-one-liner>
  <solid-one-liner id="O">Extend behavior without modifying code</solid-one-liner>
  <solid-one-liner id="L">Subclasses work where parents work</solid-one-liner>
  <solid-one-liner id="I">Small, focused interfaces</solid-one-liner>
  <solid-one-liner id="D">Depend on abstractions, not concretions</solid-one-liner>
</quick-reference>

</knowledge-base>
