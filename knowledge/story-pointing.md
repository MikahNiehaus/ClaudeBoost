# Story Pointing Guide

<knowledge-base name="story-pointing" version="1.0">
<triggers>estimate, story points, sprint planning, Fibonacci, ticket complexity, pointing</triggers>
<overview>Story points measure relative effort combining complexity, effort, and risk. NOT time estimates. Team-specific measures that improve through calibration.</overview>

<fibonacci-scale>
  <points value="1" complexity="Minimal" effort="Very low" risk="None">
    Simple text changes, config updates, typo fixes
  </points>
  <points value="2" complexity="Low" effort="Low" risk="Minor">
    Single form field, basic CRUD, simple UI component
  </points>
  <points value="3" complexity="Moderate" effort="Moderate" risk="Some">
    Multi-field forms, standard API endpoints, auth additions
  </points>
  <points value="5" complexity="Medium" effort="Medium-High" risk="Moderate">
    Frontend + backend + DB work, integrations, search with filtering
  </points>
  <points value="8" complexity="High" effort="High" risk="High">
    Multi-provider systems, complex reporting, significant refactoring
  </points>
  <points value="13" complexity="Very High" effort="Very High" risk="Very High" must-split="true">
    Major integrations, framework migrations
  </points>
</fibonacci-scale>

<pre-estimation-questions>
  <question order="1">Who and why? - User persona and pain point</question>
  <question order="2">What problem? - Specific business outcome</question>
  <question order="3">Success metrics? - Testable acceptance criteria</question>
  <question order="4">Dependencies? - Internal and external</question>
  <question order="5">Scope boundaries? - What's explicitly OUT of scope</question>
  <rule>If can't answer confidently → ticket needs clarification</rule>
</pre-estimation-questions>

<complexity-multipliers elevate="1-2 Fibonacci levels">
  <factor>First time working in codebase area</factor>
  <factor>No existing tests (need to create coverage)</factor>
  <factor>Third-party API integration</factor>
  <factor>Multiple team dependencies</factor>
  <factor>Unclear or changing requirements</factor>
  <factor>Legacy code refactoring</factor>
  <factor>Performance optimization needed</factor>
  <factor>Security-critical changes</factor>
  <factor>Data migration required</factor>
</complexity-multipliers>

<spike-creation when="technical uncertainty high">
  <trigger>Estimates diverge widely (range 3 to 21)</trigger>
  <trigger>Adopting new technology</trigger>
  <trigger>Implementation approach unclear</trigger>
  <duration>Time-boxed 1-3 days</duration>
  <output>Information and recommendations, not working code</output>
</spike-creation>

<decomposition-strategies when="exceeds 8 points">
  <strategy name="Separate by Concern">
    <example>Backend API (3) + Frontend UI (3) + Database/Integration (2)</example>
  </strategy>
  <strategy name="Extract Non-Functional">
    <example>Core feature (5) + Performance optimization (3) + Security hardening (2)</example>
  </strategy>
  <strategy name="Vertical Slices">
    <example>Add item to cart (3) + Display cart with updates (3) + Checkout integration (5)</example>
  </strategy>
</decomposition-strategies>

<justification-template>
  <format>"[X] points because: [Volume], [Complexity], [Risk]. Similar to [reference story]."</format>
  <include>
    <item>Specific complexity drivers (new integration, unfamiliar area)</item>
    <item>Identified risks (dependencies, brittle code)</item>
    <item>Scope indicators (affects 5 components vs 2)</item>
    <item>Comparisons to known reference stories</item>
  </include>
  <omit>
    <item>Implementation details (emerge during sprint)</item>
    <item>Hour/day time conversions</item>
  </omit>
</justification-template>

<planning-poker>
  <when-divergent>
    <step>Highest and lowest estimators explain reasoning first</step>
    <step>Focus on factors seen differently, not defending numbers</step>
    <step>Time-box to 2-3 minutes per story</step>
    <step>If no consensus after 2 rounds → create spike or defer</step>
  </when-divergent>
  <good-patterns>
    <pattern>"I see authentication risk because we'll touch the SSO module"</pattern>
    <pattern>"This is twice the size of Story X we did last week"</pattern>
  </good-patterns>
  <avoid>
    <pattern>"This should take me 2 days" (individual capacity)</pattern>
    <pattern>"I always give login features 5 points" (not relative)</pattern>
  </avoid>
</planning-poker>

<reference-stories>
  <story points="1" name="Update footer copyright">Single file, no logic</story>
  <story points="2" name="Add email validation to signup">One component, standard pattern</story>
  <story points="3" name="User profile edit form">Multiple fields, validation, API call</story>
  <story points="5" name="Payment method selection">Frontend + backend + external API</story>
  <story points="8" name="Multi-currency support">Multiple services, exchange rates, testing</story>
  <note>Update references quarterly based on retrospectives</note>
</reference-stories>

<risk-assessment>
  <level name="High" proceed="NO">
    External dependencies unclear, acceptance criteria undefined, technical feasibility unknown
  </level>
  <level name="Medium" proceed="Yes with assumptions">
    Minor edge cases, optimization targets, nice-to-have features
  </level>
  <level name="Low" proceed="Yes">
    Refactoring approach, code organization, test strategy
  </level>
  <key-question>If this assumption is wrong, does it invalidate our estimate or just change our approach?</key-question>
</risk-assessment>

<output-format><![CDATA[
Summary: [One sentence description]
Estimate: [X] story points (Confidence: [High/Medium/Low])

Breakdown:
- Complexity: [Low/Medium/High] - [reason]
- Effort: [Low/Medium/High] - [reason]
- Risk: [Low/Medium/High] - [reason]

Similar Stories: [Reference 2-3 comparable tickets]
Assumptions: [List any assumptions made]
Recommendation: [Clear next action]
]]></output-format>

<red-flags ticket-not-ready="true">
  <flag>Describes solution without explaining problem</flag>
  <flag>Vague success criteria ("improve", "enhance", "optimize")</flag>
  <flag>Missing user persona or business context</flag>
  <flag>Unknown external dependencies</flag>
  <flag>Estimate exceeds 13 points</flag>
  <flag>Team estimates diverge by more than 2 Fibonacci levels</flag>
</red-flags>

</knowledge-base>
