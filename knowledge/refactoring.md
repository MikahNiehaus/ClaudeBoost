# Code Refactoring Best Practices

<knowledge-base name="refactoring" version="1.0">
<triggers>refactor, code smell, technical debt, clean code, legacy code, extract method, duplication</triggers>
<overview>Changing code structure without changing behavior. Goal: easier to understand, maintain, and extend.</overview>

<why-refactor>
  <reason stat="13.5 hrs/week on tech debt">Reduce technical debt</reason>
  <reason>Enable feature development - clean code is easier to extend</reason>
  <reason>Improve understanding - refactored code documents intent</reason>
  <reason>Reduce bugs - simpler code has fewer hiding places</reason>
  <reason stat="208x deploy frequency">Faster development for elite teams</reason>
</why-refactor>

<trigger-thresholds>
  <threshold metric="Method length" value=">40 lines" action="Extract Method"/>
  <threshold metric="Cyclomatic complexity" value=">10" action="Simplify conditionals"/>
  <threshold metric="Parameter count" value=">4" action="Introduce Parameter Object"/>
  <threshold metric="Class size" value=">300 lines" action="Extract Class"/>
  <threshold metric="Duplication" value=">3 occurrences" action="Extract common code"/>
</trigger-thresholds>

<when-to-refactor>
  <do>Before adding features - clean foundation first</do>
  <do>When fixing bugs - "Boy Scout Rule" - leave code cleaner</do>
  <do>During code review - spot improvement opportunities</do>
  <do>When understanding code - refactor to clarify</do>
  <do>Scheduled tech debt sprints - dedicated improvement time</do>
  <do-not>No test coverage (write tests first)</do-not>
  <do-not>Close to deadline (risky timing)</do-not>
  <do-not>Code being replaced soon</do-not>
  <do-not>Working code that won't change</do-not>
</when-to-refactor>

<safe-refactoring-process>
  <step order="1">Ensure test coverage - can't refactor safely without tests</step>
  <step order="2">Commit current state - rollback point</step>
  <step order="3">Make one change - single refactoring at a time</step>
  <step order="4">Run tests - verify behavior preserved</step>
  <step order="5">Commit - save progress</step>
  <step order="6">Repeat - next refactoring</step>
</safe-refactoring-process>

<strangler-fig-pattern use="Legacy Systems">
  <step>Identify small piece to modernize</step>
  <step>Build new implementation alongside old</step>
  <step>Redirect traffic to new code</step>
  <step>Remove old code when no longer used</step>
  <step>Repeat for next piece</step>
</strangler-fig-pattern>

<code-smells>
  <category name="Bloaters">
    <smell name="Long Method" signs="Method >20-30 lines, needs comments" fix="Extract Method"/>
    <smell name="Large Class" signs="Class >300 lines, multiple responsibilities" fix="Extract Class"/>
    <smell name="Long Parameter List" signs=">3-4 parameters" fix="Introduce Parameter Object"/>
    <smell name="Primitive Obsession" signs="Using primitives for domain concepts" fix="Replace Primitive with Object"/>
  </category>
  <category name="Dispensables">
    <smell name="Duplicate Code" signs="Same code in multiple places" fix="Extract Method or Class"/>
    <smell name="Dead Code" signs="Unreachable code, unused variables" fix="Delete it"/>
    <smell name="Comments Explaining What" signs="Comments describing what code does" fix="Refactor to be self-documenting"/>
  </category>
  <category name="Couplers">
    <smell name="Feature Envy" signs="Method uses another class's data more than its own" fix="Move Method"/>
    <smell name="Message Chains" signs="a.getB().getC().getD()" fix="Hide Delegate"/>
  </category>
</code-smells>

<refactoring-techniques>
  <technique name="Extract Method">
    <when>Code fragment that can be grouped together</when>
    <how>Create new method with descriptive name, move code, replace with call</how>
  </technique>
  <technique name="Extract Class">
    <when>Class doing too many things</when>
    <how>Identify subset of fields/methods, create new class, move them, delegate</how>
  </technique>
  <technique name="Inline Method">
    <when>Method body is as clear as its name</when>
    <how>Replace all calls with method body, delete method</how>
  </technique>
  <technique name="Replace Temp with Query">
    <when>Temp variable holds result of expression</when>
    <how>Extract expression into method, replace temp with calls</how>
  </technique>
  <technique name="Introduce Parameter Object">
    <when>Group of parameters that travel together</when>
    <how>Create class for parameter group, update callers</how>
  </technique>
  <technique name="Replace Conditional with Polymorphism">
    <when>Conditional logic based on type</when>
    <how>Create class hierarchy, move branches to subclass methods</how>
  </technique>
</refactoring-techniques>

<success-metrics>
  <metric name="Cyclomatic Complexity" tool="SonarQube" target="&lt;10 per method"/>
  <metric name="Code Duplication" tool="SonarQube" target="&lt;3%"/>
  <metric name="Method Length" tool="Linter" target="&lt;40 lines"/>
  <metric name="Test Coverage" tool="Coverage tools" target="&gt;80%"/>
  <qualitative-signs>
    <sign>Easier to understand when reading</sign>
    <sign>Faster to make changes</sign>
    <sign>Fewer bugs in modified areas</sign>
    <sign>Less "fear" when touching code</sign>
  </qualitative-signs>
</success-metrics>

<tech-debt-prioritization>
  <priority level="P0" criteria="Blocks feature work" action="Refactor immediately"/>
  <priority level="P1" criteria="Causes bugs regularly" action="Schedule soon"/>
  <priority level="P2" criteria="Slows development" action="Plan for tech debt sprint"/>
  <priority level="P3" criteria="Code smell, no impact" action="Address opportunistically"/>
</tech-debt-prioritization>

<anti-patterns>
  <anti-pattern name="Big Bang Rewrite" problem="Replacing everything at once"/>
  <anti-pattern name="Refactoring Without Tests" problem="No safety net"/>
  <anti-pattern name="Gold Plating" problem="Perfecting working code unnecessarily"/>
  <anti-pattern name="Mixing with Feature Work" problem="Confuses code review"/>
  <anti-pattern name="Not Committing Often" problem="Loses rollback points"/>
  <anti-pattern name="Ignoring Test Code" problem="Tests need refactoring too"/>
  <anti-pattern name="Premature Refactoring" problem="Optimizing code you don't understand"/>
</anti-patterns>

<tools>
  <tool category="Static Analysis">SonarQube, ESLint/Pylint, CodeClimate, Semgrep</tool>
  <tool category="IDE Support">Extract Method/Variable/Class, Rename with references, Move/Copy, Inline, Change Signature</tool>
</tools>

<references>
  <ref name="Refactoring" author="Martin Fowler" url="https://martinfowler.com/books/refactoring.html"/>
  <ref name="Refactoring Guru" url="https://refactoring.guru/refactoring"/>
  <ref name="Working Effectively with Legacy Code" author="Michael Feathers"/>
</references>

</knowledge-base>
