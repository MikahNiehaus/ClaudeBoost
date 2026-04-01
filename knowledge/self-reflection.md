# Agent Self-Reflection Protocol

<knowledge-base name="self-reflection" version="1.0">
<triggers>reflection, confidence, verify, check output, hallucination, accuracy</triggers>
<overview>Self-reflection is critical before finalizing output. Research shows "all types of self-reflection improve LLM agent performance" and helps catch hallucinations.</overview>

<when-to-reflect>ALWAYS - before producing any final output</when-to-reflect>

<self-reflection-checklist>
  <check name="Task Alignment">
    <item>Does output address the ACTUAL task requested?</item>
    <item>Have I stayed within my domain scope?</item>
    <item>Did I answer what was asked, not assumed?</item>
  </check>
  <check name="Assumption Check">
    <item>What assumptions have I made?</item>
    <item>Are any assumptions unverified?</item>
    <item>Should I state assumptions explicitly?</item>
  </check>
  <check name="Error Analysis">
    <item>What could be wrong with my analysis?</item>
    <item>What edge cases might I have missed?</item>
    <item>Would a senior engineer spot issues?</item>
  </check>
  <check name="Completeness Check">
    <item>Have I addressed all parts of request?</item>
    <item>Are there gaps in my response?</item>
    <item>Did I forget required output sections?</item>
  </check>
</self-reflection-checklist>

<confidence-assessment>
  <level name="HIGH" criteria="All assertions verified, sources checked, no significant assumptions" action="Proceed with COMPLETE"/>
  <level name="MEDIUM" criteria="Some unverified assumptions, minor uncertainty" action="Note assumptions in handoff"/>
  <level name="LOW" criteria="Significant uncertainty, guessing required" action="Consider NEEDS_INPUT instead"/>
</confidence-assessment>

<required-output-format><![CDATA[
## Agent Status
**Status**: [COMPLETE | BLOCKED | NEEDS_INPUT]
**Confidence**: [HIGH | MEDIUM | LOW]
**Confidence Reasoning**: [1-2 sentences explaining why]
]]></required-output-format>

<rules>
  <rule>LOW confidence + critical task → Report NEEDS_INPUT, not COMPLETE</rule>
  <rule>If errors found during reflection → FIX before finalizing</rule>
  <rule>Confidence without reasoning = invalid output</rule>
  <rule>Never skip self-reflection for "simple" tasks</rule>
</rules>

<anti-hallucination-patterns>
  <pattern name="Source Verification">
    <check>Did I cite specific file paths and line numbers?</check>
    <check>Did I verify by reading actual source?</check>
    <check>Am I stating facts or making inferences?</check>
  </pattern>
  <pattern name="Uncertainty Expression">
    <rule>Use "likely", "possibly", "based on X" when uncertain</rule>
    <rule>Never state uncertain things as facts</rule>
    <rule>Clearly mark inferences vs observations</rule>
  </pattern>
  <pattern name="Knowledge Boundaries">
    <check>Am I operating within training knowledge?</check>
    <check>Should I recommend web research?</check>
    <check>Am I making up details I don't know?</check>
  </pattern>
</anti-hallucination-patterns>

<model-selection>
  <model name="Opus 4.5" strength="Deep reasoning, complex analysis" cost="$5/$25">
    <use-for>Architecture decisions, complex bug analysis, final code review</use-for>
  </model>
  <model name="Sonnet 4.5" strength="Balanced intelligence, coding" cost="$3/$15">
    <use-for>Standard development, frontend/UI, research synthesis</use-for>
  </model>
  <model name="Haiku 4.5" strength="Speed, high-volume tasks" cost="$1/$5">
    <use-for>Parallel subtasks, quick exploration, high-volume validation</use-for>
  </model>
  <orchestration-pattern>
    <step>Sonnet creates plan and decomposes</step>
    <step>Haiku instances execute subtasks in parallel</step>
    <step>Opus reviews critical/complex results</step>
  </orchestration-pattern>
</model-selection>

<context-length-guidance>
  <scenario tokens="&lt;10K">Any model suitable</scenario>
  <scenario tokens="10K-50K">Sonnet preferred</scenario>
  <scenario tokens=">50K">Sonnet or Opus (Haiku "loses track fast")</scenario>
  <scenario tokens=">200K">Sonnet with 1M context beta</scenario>
</context-length-guidance>

</knowledge-base>
