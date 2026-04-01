# Prompting Patterns & Quality Rules

<knowledge-base name="prompting-patterns" version="1.0">
<triggers>prompt, quality, better, improve, response, output, rules, patterns, chain of thought, reasoning</triggers>
<overview>Proven patterns and rules that improve AI response quality. Use for better outputs, clearer reasoning, more reliable results.</overview>

<core-quality-rules>
  <rule id="1" name="Be Specific, Not Vague">
    <bad>Make it better, Fix the bug</bad>
    <good>Reduce latency by optimizing getUserOrders(), Fix null pointer exception on line 45 when user.email is undefined</good>
  </rule>
  <rule id="2" name="Provide Context First">
    <bad>Write a function to calculate tax</bad>
    <good>We're building US e-commerce checkout. Sales tax 0-10% by state. Write function for cart total + state code.</good>
  </rule>
  <rule id="3" name="Specify Output Format">
    <bad>Analyze this code</bad>
    <good>Analyze and provide: 1. Security vulnerabilities (with severity), 2. Performance issues (with line numbers), 3. Suggested fixes (code snippets)</good>
  </rule>
  <rule id="4" name="Use Examples (Few-Shot)">
    <example>Convert to past tense: Example 1: 'I run' → 'I ran', Example 2: 'She eats' → 'She ate'. Now convert: 'They swim'</example>
  </rule>
  <rule id="5" name="Break Complex Tasks">
    <bad>Build me an authentication system</bad>
    <good>Step 1: Design user schema, Step 2: Implement password hashing, Step 3: Create login/logout endpoints, Step 4: Add JWT handling. Start with step 1.</good>
  </rule>
</core-quality-rules>

<reasoning-patterns>
  <pattern name="Chain of Thought">
    <trigger>Complex problems requiring step-by-step reasoning</trigger>
    <template>Think through step by step: 1. What is current behavior? 2. What is expected? 3. What could cause difference? 4. How can we fix it?</template>
  </pattern>
  <pattern name="Self-Critique">
    <trigger>Need for self-evaluation</trigger>
    <template>After solution: 1. What are potential weaknesses? 2. What edge cases might fail? 3. How confident (1-10)? 4. What would increase confidence?</template>
  </pattern>
  <pattern name="Adversarial Thinking">
    <trigger>Consider failure modes</trigger>
    <template>Before implementing: How could this fail? What would attacker try? What happens under load? What if input malformed?</template>
  </pattern>
  <pattern name="Rubber Duck Debugging">
    <trigger>Need to understand code</trigger>
    <template>Explain line by line as if teaching a junior developer. Then identify where the bug might be.</template>
  </pattern>
</reasoning-patterns>

<output-patterns>
  <pattern name="Structured Output">
    <format><![CDATA[
## Summary
[2-3 sentence overview]
## Findings
- Finding 1: [description]
## Recommendations
1. [Priority 1 action]
## Code Changes
[specific code with file:line references]
]]></format>
  </pattern>
  <pattern name="Confidence Scoring">
    <template>For each recommendation: Confidence: HIGH/MEDIUM/LOW, Reasoning: Why, Alternatives: If confidence is low</template>
  </pattern>
  <pattern name="Verification Steps">
    <template>After writing code: 1. Trace through with example, 2. Identify edge cases, 3. Check error handling, 4. Verify matches requirements</template>
  </pattern>
</output-patterns>

<task-specific-patterns>
  <pattern name="Code Review">
    <template>Review for: 1. Bugs (logic, off-by-one, null safety), 2. Security (injection, auth, exposure), 3. Performance (N+1, loops), 4. Maintainability. Each issue: Severity, Line, Problem, Fix</template>
  </pattern>
  <pattern name="Debugging">
    <template>1. Reproduce: What steps? 2. Isolate: Smallest failing case? 3. Identify: What line/function? 4. Fix: What change? 5. Verify: How do we know?</template>
  </pattern>
  <pattern name="Design">
    <template>1. Requirements: What must it do? 2. Constraints: What limits? 3. Trade-offs: What optimizing for? 4. Alternatives: What other approaches? 5. Decision: Which and why?</template>
  </pattern>
  <pattern name="Estimation">
    <template>1. Break into subtasks, 2. Identify unknowns/risks, 3. Compare to similar past work, 4. Provide range (best/likely/worst), 5. List assumptions</template>
  </pattern>
</task-specific-patterns>

<meta-prompting>
  <technique name="Role Assignment">"You are a senior security engineer conducting a penetration test. Review this code."</technique>
  <technique name="Constraint Setting">"Solution that: Uses only standard library, Works in O(n), Handles empty input, Is thread-safe"</technique>
  <technique name="Output Priming">"Response should be: Concise (&lt;200 words), Actionable (specific steps), Prioritized (most important first)"</technique>
  <technique name="Iterative Refinement">"First, give quick solution. Then, critique it. Finally, provide improved version addressing critique."</technique>
  <technique name="Think Tool Pattern" benefit="54% improvement on complex tasks">
    <when>After tool outputs, policy-heavy environments, sequential decision-making</when>
    <template>Before next step: 1. PAUSE review, 2. Check goal alignment, 3. Check policy violations, 4. Check information complete, 5. Then proceed</template>
  </technique>
</meta-prompting>

<anti-patterns>
  <anti-pattern name="Vague Instructions">"Make it good", "Improve this", "Fix the issues"</anti-pattern>
  <anti-pattern name="Missing Context">"Write a sort function" (what language? data? constraints?)</anti-pattern>
  <anti-pattern name="Overloading">"Write backend, frontend, tests, docs, and deploy" (break into separate requests)</anti-pattern>
  <anti-pattern name="Ambiguous Success">"Make it faster" vs "Reduce response from 2s to &lt;200ms"</anti-pattern>
</anti-patterns>

<quality-checklist>
  <item>Specific: No vague language</item>
  <item>Structured: Clear organization</item>
  <item>Complete: All parts addressed</item>
  <item>Accurate: Facts verified</item>
  <item>Actionable: Clear next steps</item>
  <item>Appropriate: Matches request complexity</item>
</quality-checklist>

</knowledge-base>
