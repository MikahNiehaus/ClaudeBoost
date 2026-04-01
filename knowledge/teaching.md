# Teaching & Pedagogical Methods

<knowledge-base name="teaching" version="1.0">
<triggers>teach, learn, explain, understand, why, how, tutor, pedagogy, Socratic, scaffold, hint</triggers>
<overview>Methodology for helping users learn and understand rather than just receiving answers. Building capability over quick solutions.</overview>

<core-principles>
  <principle name="Socratic Method" philosophy="Knowledge discovered through questioning">
    <instead-of>The answer is X because of Y</instead-of>
    <use>What do you think happens when Z? What does that tell us about X?</use>
    <question-types>
      <type name="Clarifying" purpose="Probe understanding">What do you mean by...?</type>
      <type name="Probing Assumptions" purpose="Challenge beliefs">What are we assuming here?</type>
      <type name="Probing Evidence" purpose="Ground in facts">How do we know this is true?</type>
      <type name="Exploring Implications" purpose="Extend thinking">If this is true, what follows?</type>
      <type name="Questioning the Question" purpose="Meta-level">Why is this question important?</type>
    </question-types>
  </principle>

  <principle name="Metacognitive Scaffolding" philosophy="Think about thinking">
    <phase name="Planning">What do I already know? What am I trying to learn? What strategies might help?</phase>
    <phase name="Monitoring">Am I understanding this? Where am I confused? What connections am I making?</phase>
    <phase name="Evaluation">Did I achieve my goal? What was the key insight? How can I apply this?</phase>
  </principle>

  <principle name="Zone of Proximal Development" philosophy="Edge of capability">
    <detection>
      <signal interpretation="at edge (good)">User asks clarifying questions</signal>
      <signal interpretation="too easy">User immediately answers</signal>
      <signal interpretation="too hard">User has no response</signal>
    </detection>
    <adjustment when="too easy">Skip ahead, add complexity</adjustment>
    <adjustment when="too hard">Step back, provide scaffolding</adjustment>
  </principle>

  <principle name="Progressive Disclosure" philosophy="Reveal in layers">
    <level id="1" type="Minimal hint">Think about what happens when...</level>
    <level id="2" type="Concept name">This relates to memoization...</level>
    <level id="3" type="Guided explanation">Memoization caches results. What would it cache here?</level>
    <level id="4" type="Full explanation">We use memoization because...</level>
    <rule>Only escalate when user shows engagement but remains stuck</rule>
  </principle>
</core-principles>

<teaching-protocols>
  <protocol name="Code Explanation">
    <bad>This function does X</bad>
    <good>
      <step>What's the input to this function?</step>
      <step>What do you think happens on line 3?</step>
      <step>What's the loop doing with each item?</step>
      <step>Predict: What's returned for input [example]?</step>
      <step>Now let's verify your prediction...</step>
    </good>
  </protocol>

  <protocol name="Design Decisions" pattern="Context → Options → Trade-offs → Decision">
    <section name="Context">What problem we were solving</section>
    <section name="Options">Brief description of each approach</section>
    <section name="Trade-offs">Performance vs Simplicity vs Maintainability matrix</section>
    <section name="Decision">Why we chose this option</section>
    <section name="Question">Given different context [X], which would you choose?</section>
  </protocol>

  <protocol name="Error Understanding">
    <bad>The error means X. Here's the fix.</bad>
    <good>
      <step>Quote and decode error message</step>
      <step>What might be undefined?</step>
      <step>Where does that variable come from?</step>
      <step>Under what conditions might it fail?</step>
      <step>What's your hypothesis? Let's verify...</step>
    </good>
  </protocol>
</teaching-protocols>

<user-types>
  <type name="Beginner" asks="what questions">
    <strategy>Define terms before using</strategy>
    <strategy>Use analogies to familiar concepts</strategy>
    <strategy>Provide concrete examples</strategy>
    <strategy>Check understanding frequently</strategy>
  </type>
  <type name="Intermediate" asks="how questions">
    <strategy>Focus on patterns and principles</strategy>
    <strategy>Introduce trade-offs</strategy>
    <strategy>Challenge with edge cases</strategy>
    <strategy>Encourage experimentation</strategy>
  </type>
  <type name="Advanced" asks="why questions">
    <strategy>Discuss design philosophy</strategy>
    <strategy>Explore alternatives</strategy>
    <strategy>Debate trade-offs</strategy>
    <strategy>Engage as peers</strategy>
  </type>
</user-types>

<anti-patterns>
  <anti-pattern name="Information Dump" problem="Overwhelming" fix="Break into chunks with engagement between"/>
  <anti-pattern name="Answer Machine" problem="Always direct answers" fix="Default to questions; answers are last resort"/>
  <anti-pattern name="Condescender" problem="Explaining known things" fix="Ask what they know first"/>
  <anti-pattern name="Gatekeeper" problem="Making simple things complex" fix="Start simple, add complexity when needed"/>
  <anti-pattern name="Abandoner" problem="Questions without follow-up" fix="Respond to attempts, guide forward"/>
</anti-patterns>

<understanding-assessment>
  <quick-checks>
    <check>Can you explain that back to me?</check>
    <check>What would happen if we changed X?</check>
    <check>How would you apply this to [different scenario]?</check>
  </quick-checks>
  <signs-of-understanding>
    <sign>User asks follow-up questions</sign>
    <sign>User makes connections to other concepts</sign>
    <sign>User predicts correctly</sign>
    <sign>User catches their own mistakes</sign>
  </signs-of-understanding>
  <signs-of-confusion>
    <sign>Vague or non-committal responses</sign>
    <sign>Repeating without understanding</sign>
    <sign>Complete silence</sign>
    <sign>Unrelated tangents</sign>
  </signs-of-confusion>
</understanding-assessment>

<templates>
  <template name="Quick Explanation">
    <section name="In One Sentence">Core concept</section>
    <section name="Why It Matters">Practical relevance</section>
    <section name="Example">Concrete illustration</section>
    <section name="Test Yourself">One verification question</section>
  </template>
  <template name="Guided Discovery">
    <section name="Starting Point">What do you already know about [related]?</section>
    <section name="Exploration">Questions leading toward insight</section>
    <section name="The Insight">Reveal concept, connecting to answers</section>
    <section name="Application">How would you use this for [scenario]?</section>
  </template>
  <template name="Deep Dive">
    <section name="Historical Context">Why does this exist?</section>
    <section name="Core Concepts">Foundational ideas</section>
    <section name="How It Works">Detailed mechanism</section>
    <section name="Trade-offs">Benefits vs Costs</section>
    <section name="Common Misconceptions">Reality checks</section>
  </template>
</templates>

<integration>
  <when-to-teach>
    <trigger>Decision was non-obvious</trigger>
    <trigger>User would benefit from understanding</trigger>
    <trigger>User expressed interest in learning</trigger>
  </when-to-teach>
  <teaching-in-context>
    <item>Agent: which agent acted</item>
    <item>Action: what they did</item>
    <item>Why This Way: brief explanation</item>
    <item>The Concept: underlying principle</item>
    <item>Want to Learn More?: offer deep dive options</item>
  </teaching-in-context>
</integration>

<research-foundation>
  <source name="Socratic Method" author="Plato" year="400 BCE"/>
  <source name="Constructivism" author="Piaget, Vygotsky"/>
  <source name="Zone of Proximal Development" author="Vygotsky" year="1978"/>
  <source name="Metacognitive Theory" author="Flavell" year="1979"/>
  <finding year="2024-2025">Socratic AI tutors: 24% improvement in critical thinking</finding>
  <finding year="2024-2025">Students prefer guided hints: 4.0/5 satisfaction</finding>
  <finding year="2024-2025">Metacognitive scaffolding: 35% improved learning transfer</finding>
</research-foundation>

</knowledge-base>
