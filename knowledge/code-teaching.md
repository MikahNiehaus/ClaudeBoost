# Teaching Code Changes

<knowledge-base name="code-teaching" version="1.0">
<triggers>teach, explain, why, learn, understand, decision, approach, alternative, concept, pattern</triggers>
<overview>Every code change is a teaching opportunity. Explain WHY, not just WHAT. Users should understand: why this approach, what alternatives existed, what concepts applied, what to learn.</overview>

<core-principle>Every code change MUST include a Teaching section</core-principle>

<required-sections>
  <section name="Why This Approach">
    <template>[Context] We needed to [solve X] because [reason]. [Decision] I chose [approach] because [justification]. [Trade-off] This means [what we get] at the cost of [what we give up].</template>
  </section>

  <section name="Alternatives Considered">
    <format>Table with Alternative and Why Rejected columns</format>
    <purpose>Show you evaluated options - teaches decision-making</purpose>
  </section>

  <section name="Key Concepts Applied">
    <format>Numbered list: [Concept Name]: [What it means and why it applies here]</format>
  </section>

  <section name="What You Should Learn">
    <format>Bullet list of generalizable insights and when to apply this pattern</format>
  </section>

  <section name="Questions to Deepen Understanding">
    <examples>
      <question>What would happen if [edge case]?</question>
      <question>Why might you NOT want to [alternative approach]?</question>
      <question>How would this change if [different requirement]?</question>
    </examples>
  </section>
</required-sections>

<by-code-type>
  <type name="Bug Fixes" focus="Root cause understanding, prevention">
    <sections>
      <section>Why This Fix: root cause, original assumption that failed, why this addresses root cause vs symptom</section>
      <section>What Caused This Bug: contributing factors</section>
      <section>How to Prevent Similar Bugs: prevention strategies</section>
      <section>Key Concept: defensive programming, fail-fast, etc.</section>
    </sections>
  </type>

  <type name="Refactoring" focus="Code quality principles, when to apply">
    <sections>
      <section>Why This Refactoring: code smell identified, problem it causes, technique applied, benefit</section>
      <section>Refactoring Technique: explanation from Martin Fowler, etc.</section>
      <section>When to Apply This: trigger conditions</section>
      <section>When NOT to Apply This: counter-indications</section>
    </sections>
  </type>

  <type name="New Features" focus="Design decisions, architecture patterns">
    <sections>
      <section>Why This Design: requirements, pattern chosen, benefits, flexibility</section>
      <section>Design Pattern: what it is, when to use it</section>
      <section>Architecture Decision: approach vs alternative, reasoning</section>
      <section>SOLID Principles Applied: how each applies</section>
    </sections>
  </type>

  <type name="Tests" focus="Testing strategy, coverage philosophy">
    <sections>
      <section>Why These Tests: test types chosen, reasoning, priority focus</section>
      <section>Testing Concepts Applied: AAA pattern, mocking strategy, etc.</section>
      <section>What's NOT Tested and Why: untested scenarios with reasoning</section>
    </sections>
  </type>
</by-code-type>

<teaching-techniques>
  <technique name="Progressive Disclosure">
    <level name="Key Insight">One sentence summary</level>
    <level name="Going Deeper">More detailed explanation</level>
    <level name="For the Curious">Advanced details or edge cases</level>
  </technique>

  <technique name="Concrete Before Abstract">
    <step order="1">Show the specific example first</step>
    <step order="2">Then explain the general principle</step>
    <example><![CDATA[
**What We Did**:
constructor(private db: Database) {}

**The Pattern**:
Dependency Injection means passing dependencies in rather than creating them.
This makes the code testable (mock) and flexible (swap implementations).
]]></example>
  </technique>

  <technique name="Connect to Familiar Concepts">
    <example context="React">This is like lifting state up - we moved logic to a parent so children can share it.</example>
    <example context="SQL">This is similar to a JOIN - we're combining data from two sources based on a common key.</example>
  </technique>
</teaching-techniques>

<socratic-questions>
  <category name="Design Decisions">
    <question>What would happen if we had 1000x more users?</question>
    <question>How would this change if requirement X was added?</question>
    <question>Why did we put this logic here instead of [alternative location]?</question>
  </category>
  <category name="Bug Fixes">
    <question>What assumption did the original code make?</question>
    <question>How could we have caught this earlier?</question>
    <question>What test would have prevented this?</question>
  </category>
  <category name="Refactoring">
    <question>What was the code smell that triggered this refactoring?</question>
    <question>When would you NOT apply this refactoring?</question>
    <question>How do you know when to stop refactoring?</question>
  </category>
  <category name="Performance">
    <question>What's the time/space complexity of this approach?</question>
    <question>When would the simpler approach be good enough?</question>
    <question>How would you measure if this optimization helped?</question>
  </category>
</socratic-questions>

<anti-patterns>
  <anti-pattern name="Just State Facts">
    <bad>We used a factory pattern.</bad>
    <good>We used a factory pattern because object creation involves conditional logic that would clutter the calling code.</good>
  </anti-pattern>
  <anti-pattern name="Assume Knowledge">
    <bad>This follows SOLID principles.</bad>
    <good>This follows Single Responsibility - each class has one job. UserValidator only validates, it doesn't also save.</good>
  </anti-pattern>
  <anti-pattern name="Condescending">
    <bad>As any developer knows...</bad>
    <good>A common pattern here is...</good>
  </anti-pattern>
  <anti-pattern name="Over-Teach">
    <bad>Explaining every basic operation</bad>
    <good>Focus on decisions, trade-offs, non-obvious choices</good>
  </anti-pattern>
</anti-patterns>

<quick-template><![CDATA[
## Teaching

**Why This Approach**:
[1-2 sentences on the reasoning]

**Alternatives Considered**:
| Alternative | Why Rejected |
|-------------|--------------|
| [A] | [Reason] |

**Key Concepts**:
1. **[Concept]**: [Brief explanation]

**What You Should Learn**:
- [Key insight]

**Questions**:
- [Thought-provoking question]
]]></quick-template>

</knowledge-base>
