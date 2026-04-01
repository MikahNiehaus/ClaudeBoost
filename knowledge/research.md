# Web Research Best Practices

<knowledge-base name="research" version="1.0">
<triggers>research, search, investigate, find out, look up, verify, citation, source</triggers>
<overview>Systematic methodology for reliable web research that minimizes hallucinations, maximizes accuracy, and produces verifiable, well-cited findings.</overview>

<core-principles>
  <principle name="Verify Before Claiming">Never present unverified information as fact. Every claim must have a source.</principle>
  <principle name="Multi-Source Verification">Cross-reference important claims across multiple authoritative sources.</principle>
  <principle name="Track Confidence">Rate confidence (High/Medium/Low) based on evidence quality and source agreement.</principle>
  <principle name="Admit Uncertainty">"I couldn't verify this" is better than guessing.</principle>
  <principle name="Structured Methodology">Plan → Execute → Verify → Synthesize. Don't jump to conclusions.</principle>
</core-principles>

<methodology>
  <phase name="Planning">
    <step name="Decompose">Break complex questions into sub-questions</step>
    <step name="Identify Sources">Official docs, research papers, blogs, community</step>
    <step name="Form Hypotheses">Develop competing explanations, stay open</step>
  </phase>

  <phase name="Execution">
    <step name="Targeted Search">Use specific queries with context (not "caching" but "Redis caching patterns Node.js 2024")</step>
    <step name="Source Evaluation">Note domain authority, publication date, author expertise, bias</step>
    <step name="Information Extraction">Record exact claims with context, note contradictions</step>
  </phase>

  <phase name="Verification">
    <step name="Multi-Source">Key claims need 2+ sources, check for circular references</step>
    <step name="Consensus">Do sources agree? What do authoritative sources say?</step>
    <step name="Numbers">Statistics must cite original source, check definition context</step>
    <step name="Recency">Is information current? When was source last updated?</step>
  </phase>

  <phase name="Synthesis">
    <step name="Resolve Contradictions">Weight by source quality, acknowledge unclear consensus</step>
    <step name="Rate Confidence">High: 3+ sources agree. Medium: 1-2 reputable. Low: limited/conflicting</step>
    <step name="Identify Gaps">What couldn't be found? What assumptions remain?</step>
  </phase>
</methodology>

<source-credibility>
  <tier level="1" name="High Authority" trust="High">
    <source>Official documentation (vendor, government)</source>
    <source>Peer-reviewed research</source>
    <source>Well-established industry publications</source>
    <source>Recognized domain experts with track record</source>
  </tier>
  <tier level="2" name="Medium Authority" trust="Medium">
    <source>Technical blogs from practitioners</source>
    <source>Conference presentations with citations</source>
    <source>Community wikis with sources</source>
    <source>Industry analyst reports</source>
  </tier>
  <tier level="3" name="Requires Verification" trust="Low">
    <source>Anonymous forum posts</source>
    <source>Uncited blog articles</source>
    <source>Social media claims</source>
    <source>AI-generated content (including other LLM outputs)</source>
    <source>Outdated sources (>2 years for fast-moving tech)</source>
  </tier>
  <red-flags>
    <flag>No author attribution</flag>
    <flag>No publication date</flag>
    <flag>No citations or references</flag>
    <flag>Promotional content masquerading as information</flag>
    <flag>Extraordinary claims without evidence</flag>
  </red-flags>
</source-credibility>

<anti-hallucination>
  <permission-for-uncertainty>
    <say>I couldn't verify this</say>
    <say>Sources conflict on this point</say>
    <say>This information may be outdated</say>
    <say>I found limited information about this</say>
  </permission-for-uncertainty>
  <grounding>
    <rule>Only claim what sources explicitly state</rule>
    <rule>Don't extrapolate beyond the evidence</rule>
    <rule>Don't assume source A's claim applies to context B</rule>
    <rule>Quote exactly when precision matters</rule>
  </grounding>
  <confidence-language>
    <level confidence="High" criteria="3+ quality sources agree" language="X is..."/>
    <level confidence="Medium" criteria="1-2 reputable sources" language="According to [source], X..."/>
    <level confidence="Low" criteria="Limited/conflicting" language="Some sources suggest X, but..."/>
    <level confidence="Uncertain" criteria="No clear evidence" language="I couldn't find reliable information on..."/>
  </confidence-language>
</anti-hallucination>

<report-structure>
  <section name="Executive Summary">Key findings, overall confidence, major caveats</section>
  <section name="Methodology">How research was conducted, sources consulted</section>
  <section name="Findings">Statement, confidence level, supporting sources, verification</section>
  <section name="Source Analysis Table">Source, Type, Authority, Date, Agrees/Conflicts</section>
  <section name="Uncertainties and Gaps">What couldn't be determined, assumptions</section>
  <section name="Full Citations">Complete list with URLs</section>
</report-structure>

<common-failures>
  <category name="Search">
    <failure problem="Overly broad results" cause="Generic query" fix="Use specific terms + context"/>
    <failure problem="Missing key sources" cause="Only one query" fix="Try multiple query variations"/>
    <failure problem="First-result bias" cause="Stopped too early" fix="Check multiple sources"/>
  </category>
  <category name="Verification">
    <failure problem="Wrong numbers" cause="Different definition" fix="Check measurement context"/>
    <failure problem="Outdated info" cause="Didn't check date" fix="Always note publication date"/>
    <failure problem="Circular reference" cause="Sources cite each other" fix="Trace to original source"/>
  </category>
  <category name="Synthesis">
    <failure problem="Cherry-picking" cause="Confirmation bias" fix="Represent all viewpoints"/>
    <failure problem="Over-confidence" cause="Single strong source" fix="Require multi-source"/>
  </category>
</common-failures>

<checklist>
  <phase name="Before Starting">
    <item>Research question clearly defined</item>
    <item>Sub-questions identified</item>
    <item>Source types to consult listed</item>
  </phase>
  <phase name="During Research">
    <item>Multiple search queries used</item>
    <item>Source authority evaluated</item>
    <item>Contradictions noted</item>
    <item>URLs saved for citation</item>
  </phase>
  <phase name="Verification">
    <item>Key claims cross-referenced (2+ sources)</item>
    <item>Numbers verified against original</item>
    <item>Publication dates checked</item>
  </phase>
  <phase name="Final Report">
    <item>All claims have citations</item>
    <item>Confidence levels assigned</item>
    <item>Uncertainties acknowledged</item>
  </phase>
</checklist>

</knowledge-base>
