# Code Documentation Guide

<knowledge-base name="documentation" version="1.0">
<triggers>documentation, docstring, comment, README, API docs, technical writing</triggers>
<overview>Writing docstrings, comments, README files, API documentation. Documentation explains the WHY, not the WHAT or HOW.</overview>

<core-philosophy>
  <principle>Code shows what it does; documentation explains reasoning invisible to code readers</principle>
  <principle>Treat prompts like engineering specifications with explicit constraints</principle>
  <antipattern>Never paraphrase code line-by-line (verbatim copying trap)</antipattern>
</core-philosophy>

<content-balance>
  <focus percent="80%">WHY: Business purpose, design decisions, trade-offs</focus>
  <focus percent="15%">WHAT: High-level behavior, inputs/outputs, errors</focus>
  <focus percent="5%">HOW: Only when implementation is surprising/non-obvious</focus>
</content-balance>

<critical-rules>
  <do-not>Restate what the code does line-by-line</do-not>
  <do-not>Copy code patterns into prose ("multiplies X by Y")</do-not>
  <do-not>Describe implementation details visible in the code</do-not>
  <do-not>Write "this function does X" without explaining WHY</do-not>
  <do>Explain the business purpose and real-world use case</do>
  <do>Document the "why" behind design decisions and trade-offs</do>
  <do>Provide context a new team member would need</do>
  <do>Include practical usage examples with realistic scenarios</do>
  <do>Note edge cases, constraints, and error handling strategies</do>
</critical-rules>

<good-vs-bad-example><![CDATA[
BAD (restates code):
"""Calculates discount.
This function takes a price and discount_rate parameter. It multiplies
the price by 1 minus the discount_rate. Then it returns the result."""

GOOD (explains WHY):
"""Calculate final price after applying a percentage discount.

This function implements the core pricing logic for promotional codes
in e-commerce checkout flows. The discount is applied multiplicatively
to support stacking with other promotions.

Args:
    price (float): Original item price in dollars, must be positive
    discount_rate (float): Discount as decimal between 0 and 1
        (e.g., 0.2 represents 20% off)

Returns:
    float: Final price after discount

Example:
    >>> calculate_discount(100.0, 0.2)
    80.0

Note:
    Does not handle currency conversion. Ensure all prices are in
    the same currency before applying discounts.
"""
]]></good-vs-bad-example>

<audience-guidelines>
  <audience level="Junior (0-2 years)">
    <guideline>Start with clear prerequisites</guideline>
    <guideline>Explain non-obvious design patterns</guideline>
    <guideline>Include "why" for non-intuitive approaches</guideline>
    <guideline>Provide complete, runnable examples</guideline>
    <guideline>Anticipate common mistakes</guideline>
  </audience>
  <audience level="Senior (5+ years)">
    <guideline>Lead with architectural context</guideline>
    <guideline>Focus on design trade-offs</guideline>
    <guideline>Document performance characteristics</guideline>
    <guideline>Note subtle edge cases and threading implications</guideline>
    <guideline>Skip obvious error cases</guideline>
  </audience>
  <progressive-disclosure>
    <layer name="QUICK START">One paragraph with purpose, signature, basic example</layer>
    <layer name="DETAILED GUIDE">Full parameters, return values, 2-3 usage examples</layer>
    <layer name="DEEP DIVE">Implementation notes, design rationale, edge cases, performance</layer>
  </progressive-disclosure>
</audience-guidelines>

<language-conventions>
  <convention lang="Python (Google-style)">
    <rule>Use imperative mood ("Return X" not "Returns X")</rule>
    <rule>Type hints in signature, not docstring</rule>
    <rule>First line: summary under 79 characters</rule>
    <rule>Include: Args, Returns, Raises, Example, Note</rule>
  </convention>
  <convention lang="JavaScript/TypeScript (TSDoc/JSDoc)">
    <rule>Do NOT repeat type information from TypeScript signature</rule>
    <rule>Use @param, @returns, @throws tags</rule>
    <rule>Include @example with executable code blocks</rule>
    <rule>Use @remarks for design rationale</rule>
  </convention>
  <convention lang="Java (Javadoc)">
    <rule>First sentence becomes summary (ends at period + space)</rule>
    <rule>Tag order: @param, @return, @throws, @see, @since</rule>
    <rule>Document all checked exceptions</rule>
  </convention>
  <convention lang="C++ (Doxygen)">
    <rule>Use @brief for one-line summary</rule>
    <rule>Document template parameters with @tparam</rule>
    <rule>Use @pre and @post for contracts</rule>
  </convention>
</language-conventions>

<inline-comment-rules>
  <write-when>
    <condition>Explaining why a workaround exists (reference bug ticket)</condition>
    <condition>Noting performance optimizations that look suboptimal but are measured</condition>
    <condition>Documenting business rules not obvious from code</condition>
    <condition>Marking intentional deviations from best practices</condition>
  </write-when>
  <never-write>
    <condition>Restate what the code obviously does</condition>
    <condition>Duplicate information in docstrings</condition>
    <condition>Describe standard language features</condition>
  </never-write>
</inline-comment-rules>

<technical-writing>
  <rule name="Active Voice (80-90%)">
    <good>"The function validates input"</good>
    <bad>"Input is validated by the function"</bad>
  </rule>
  <rule name="Sentence Structure">
    <guideline>Keep most sentences under 25 words</guideline>
    <guideline>Front-load important information: conclusion first, then details</guideline>
    <guideline>Keep subject and verb close together (within 5-7 words)</guideline>
  </rule>
  <rule name="Terminology Consistency">
    <guideline>Choose one term per concept and use it everywhere</guideline>
    <guideline>Don't switch between "user", "customer", "account holder"</guideline>
    <guideline>Define technical terms on first use</guideline>
  </rule>
</technical-writing>

<code-examples-requirements>
  <requirement>Be complete and immediately runnable (include imports, setup)</requirement>
  <requirement>Use realistic variable names and data</requirement>
  <requirement>Show both success and error cases</requirement>
  <requirement>Include expected output as comments</requirement>
  <requirement>Stay under 20 lines when possible</requirement>
  <requirement>Follow language best practices</requirement>
</code-examples-requirements>

<maintenance>
  <rule>Live in same Git repository as code (docs-as-code)</rule>
  <rule>Update in same PR/commit as code changes</rule>
  <rule>Include "last updated" dates for time-sensitive content</rule>
  <rule>Delete dead documentation aggressively</rule>
  <rule>Test examples automatically in CI/CD</rule>
</maintenance>

<quality-checklist>
  <item>Can a new team member understand purpose in under 60 seconds?</item>
  <item>Can someone use the API correctly without reading implementation?</item>
  <item>Are code examples copy-pasteable and runnable?</item>
  <item>Does documentation answer "why" questions that code cannot?</item>
  <item>Is technical terminology consistent throughout?</item>
</quality-checklist>

</knowledge-base>
