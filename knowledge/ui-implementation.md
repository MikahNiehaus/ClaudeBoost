# UI Implementation Guide

<knowledge-base name="ui-implementation" version="1.0">
<triggers>UI, mockup, frontend, design to code, Figma, pixel-perfect, component, responsive</triggers>
<overview>Context engineering, visual feedback loops, and Claude-specific techniques for UI implementation. Results: 50-70% time savings.</overview>

<prompt-engineering>
  <principle name="Use XML Tags">Claude trained with XML - improves accuracy ~20%</principle>
  <principle name="Images First">Place images at very start before any text</principle>
  <principle name="Force Analysis">Use chain-of-thought with thinking tags before code</principle>

  <xml-structure><![CDATA[
<mockup>[Base64 image or file reference]</mockup>

<specifications>
- Colors: #3B82F6 (primary), #10B981 (secondary)
- Typography: Inter font, 16px base, 1.5 line-height
- Spacing: 8px grid system (8, 16, 24, 32, 48, 64)
</specifications>

<requirements>
1. Extract ALL text exactly as shown in mockup
2. Match colors precisely using provided HEX codes
3. Implement responsive breakpoints at 640px, 768px, 1024px
4. No placeholders or abbreviated code
</requirements>

<tech_stack>Next.js 14, TypeScript, Tailwind CSS, shadcn/ui</tech_stack>
]]></xml-structure>
</prompt-engineering>

<specifications always-provide="true">
  <spec type="Colors">HEX codes, not color names (#3B82F6 not "blue")</spec>
  <spec type="Typography">Font family, sizes, weights, line-height</spec>
  <spec type="Spacing">8px grid system (8, 16, 24, 32, 48, 64)</spec>
  <spec type="Breakpoints">640px, 768px, 1024px, 1280px</spec>
  <spec type="Border radius">4px, 8px, 12px</spec>
  <spec type="Shadows">Full rgba values</spec>
</specifications>

<failure-modes>
  <failure name="Text Omissions">
    <problem>Claude skips or abbreviates text from mockups</problem>
    <solution>Explicit requirement: Extract ALL text exactly as shown, do NOT abbreviate</solution>
  </failure>
  <failure name="Generic Styling">
    <problem>Claude uses defaults instead of matching mockup</problem>
    <solution>Provide explicit design tokens JSON with exact values</solution>
  </failure>
  <failure name="Incomplete Code">
    <problem>Claude writes "// ... rest of component"</problem>
    <solution>Rule: No placeholders, no abbreviated sections, every function fully implemented</solution>
  </failure>
  <failure name="Wrong Component Library">
    <problem>Claude uses different library than specified (e.g., jQuery instead of native APIs)</problem>
    <solution>Explicit DO/DO NOT use lists. DO NOT use jQuery - use React refs, vanilla JS, or native DOM APIs instead. See forbidden-libraries section.</solution>
  </failure>
</failure-modes>

<forbidden-libraries>
  <library name="jQuery" severity="BLOCKER">
    <status>BANNED in ViveryAscend codebase</status>
    <reason>Incompatible with React/Next.js paradigm. jQuery directly manipulates the DOM, conflicting with React's virtual DOM.</reason>
    <if-user-asks-for-dom-manipulation>
      <use context="React component">useRef() + useEffect() for direct DOM access</use>
      <use context="Event handling">React synthetic events (onClick, onChange, etc.)</use>
      <use context="Class toggling">Conditional className or clsx/cn utility with Tailwind</use>
      <use context="AJAX calls">fetch(), Next.js server actions, or SWR/React Query</use>
      <use context="Animation">CSS transitions, Tailwind animate-*, or Framer Motion</use>
      <use context="Outside React">Vanilla JS: document.querySelector(), addEventListener()</use>
    </if-user-asks-for-dom-manipulation>
    <override>ONLY if user explicitly says "use jQuery"</override>
  </library>
</forbidden-libraries>

<visual-feedback-loop>
  <step order="1">Generate initial implementation</step>
  <step order="2">Screenshot the rendered result</step>
  <step order="3">Compare side-by-side with mockup</step>
  <step order="4">Provide screenshot back to Claude with specific corrections</step>
  <correction-format>
    <example>Header padding is 24px, should be 16px</example>
    <example>Button color is #3B82F6, should be #2563EB</example>
    <example>Missing hover state on navigation items</example>
  </correction-format>
</visual-feedback-loop>

<component-first-approach>
  <order>
    <step>Identify atomic components first</step>
    <step>Generate each component separately</step>
    <step>Compose into larger structures</step>
    <step>Generate page layout last</step>
  </order>
  <component-spec-template><![CDATA[
<component name="[Name]">
<description>[Purpose]</description>
<props>
- prop: type (required/optional)
</props>
<visual_specs>
- Dimensions, Padding, Border, Shadow
</visual_specs>
<states>Default, Hover, Focus, Active</states>
</component>
]]></component-spec-template>
</component-first-approach>

<reuse-first-protocol>
  <description>BEFORE creating any new component, widget, utility, or hook, follow this search-before-build workflow.</description>
  <step order="1">Search project for existing components (Glob/Grep for similar names, patterns)</step>
  <step order="2">Search project's component library / design system exports</step>
  <step order="3">Search shared hooks, utilities, helpers</step>
  <step order="4" condition="match-found">Reuse, extend, or compose existing code — do NOT rebuild</step>
  <step order="5" condition="no-match">Document why new code is necessary before proceeding</step>
</reuse-first-protocol>

<responsive-strategy>
  <approach>Mobile-first</approach>
  <breakpoints>
    <breakpoint name="mobile" width="&lt;640px" layout="Single column, stacked nav"/>
    <breakpoint name="sm" width="640px" layout="2-column grid"/>
    <breakpoint name="md" width="768px" layout="Sidebar appears"/>
    <breakpoint name="lg" width="1024px" layout="3-column grid"/>
    <breakpoint name="xl" width="1280px" layout="Max-width container"/>
  </breakpoints>
</responsive-strategy>

<accessibility>
  <requirement>Semantic HTML elements (nav, main, article, section)</requirement>
  <requirement>ARIA labels for interactive elements</requirement>
  <requirement>Keyboard navigation support</requirement>
  <requirement>Focus visible states</requirement>
  <requirement>Color contrast minimum 4.5:1</requirement>
  <requirement>Alt text for images</requirement>
  <requirement>Skip links for navigation</requirement>
</accessibility>

<quality-checklist>
  <category name="Visual Accuracy">
    <item>Colors match mockup exactly</item>
    <item>Typography matches (font, size, weight, line-height)</item>
    <item>All text content included (no omissions)</item>
  </category>
  <category name="Code Quality">
    <item>No placeholder comments</item>
    <item>All imports included</item>
    <item>TypeScript types defined</item>
  </category>
  <category name="Responsiveness">
    <item>Mobile layout works</item>
    <item>No horizontal scroll on any viewport</item>
  </category>
  <category name="Interactivity">
    <item>Hover states implemented</item>
    <item>Focus states visible</item>
    <item>Loading/error states if applicable</item>
  </category>
</quality-checklist>

</knowledge-base>
