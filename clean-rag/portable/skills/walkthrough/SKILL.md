---
name: walkthrough
description: Generate an interactive step by step tutorial/walkthrough for any feature or workflow. Uses Playwright MCP in headed mode to navigate through the UI, inject visual annotations (highlights, numbered callouts, arrows, popovers) via JavaScript, capture annotated screenshots at each step, and assemble a polished markdown document with embedded images. USE when the user asks to document how something works, create a tutorial, write a walkthrough, or generate step by step instructions for a feature.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_click, mcp__playwright__browser_type, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_evaluate, mcp__playwright__browser_fill_form, mcp__playwright__browser_select_option, mcp__playwright__browser_wait_for, mcp__playwright__browser_press_key, mcp__playwright__browser_console_messages, mcp__playwright__browser_resize, mcp__playwright__browser_close, mcp__playwright__browser_hover, mcp__playwright__browser_find
---

# Walkthrough: Interactive Tutorial Generator

Generate step by step tutorials with annotated screenshots by driving a live
app through Playwright MCP. The output is a self contained markdown document
with numbered steps and embedded images showing exactly what to click, where
to look, and what happens.

## Phase 0: Understand the Task

Read `$ARGUMENTS`. Derive:

- **FEATURE** -- what feature or workflow to document (e.g. "login flow",
  "creating a new project", "configuring notifications")
- **URL** -- the starting URL. Must be localhost, 127.0.0.1, 0.0.0.0, or
  `*.local` / `*.test`. Refuse non local URLs.
- **OUTPUT_DIR** -- where to write the walkthrough. Default:
  `docs/walkthroughs/` relative to the project root. Create if missing.
- **SLUG** -- lowercase filename stem derived from FEATURE (e.g.
  `login-flow`, `create-project`)

If no URL is given, ask the user for one. The app must be running.

## Phase 1: Plan the Steps

Before touching the browser, write a step outline:

1. List the 5 to 15 steps that make up the workflow
2. For each step, note: what action the user takes, what element to
   highlight, what the expected result is
3. Save the outline to `{OUTPUT_DIR}/{SLUG}-plan.md`

Show the plan to the user and wait for approval before proceeding.

## Phase 2: Navigate and Annotate

For each step in the plan:

### 2a. Navigate or act

Use the appropriate Playwright MCP tool:
- `browser_navigate` for page loads
- `browser_click` for clicks
- `browser_fill_form` or `browser_type` for text input
- `browser_select_option` for dropdowns
- `browser_press_key` for keyboard actions

### 2b. Wait for stability

Use `browser_wait_for` to confirm the expected element or text is present
before annotating. Never annotate a page that has not settled.

### 2c. Inject annotations

Use `browser_evaluate` to inject visual callouts. The injection pattern
uses Driver.js when available, or falls back to pure DOM injection.

**Inject Driver.js (once per page navigation):**

```javascript
// Inject Driver.js CSS
(function() {
  if (document.getElementById('__walkthrough_driver_css')) return;
  var link = document.createElement('link');
  link.id = '__walkthrough_driver_css';
  link.rel = 'stylesheet';
  link.href = 'https://cdn.jsdelivr.net/npm/driver.js@1.4.0/dist/driver.css';
  document.head.appendChild(link);
})();
```

```javascript
// Inject Driver.js script
(function() {
  if (window.__walkthroughDriver) return Promise.resolve();
  return new Promise(function(resolve, reject) {
    var script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/driver.js@1.4.0/dist/driver.js.iife.js';
    script.onload = function() {
      window.__walkthroughDriver = true;
      resolve();
    };
    script.onerror = function() {
      reject(new Error('Driver.js CDN unreachable'));
    };
    document.head.appendChild(script);
    setTimeout(function() {
      if (!window.__walkthroughDriver) {
        reject(new Error('Driver.js load timed out'));
      }
    }, 3000);
  });
})();
```

**Highlight an element with a popover:**

```javascript
(function(selector, title, description, side) {
  var driverFn = window.driver.js.driver;
  var d = driverFn({
    animate: true,
    overlayOpacity: 0.5,
    stagePadding: 8,
    stageRadius: 5,
    allowClose: false,
    popoverClass: 'walkthrough-popover'
  });
  d.highlight({
    element: selector,
    popover: {
      title: title,
      description: description,
      side: side || 'bottom',
      align: 'center'
    }
  });
  window.__walkthroughCurrentDriver = d;
})('#target-selector', 'Step 1', 'Click this button to begin', 'bottom');
```

**Add a numbered callout badge (no library needed):**

```javascript
(function(selector, stepNum) {
  var el = document.querySelector(selector);
  if (!el) return;
  el.style.outline = '3px solid #e53e3e';
  el.style.outlineOffset = '2px';
  var badge = document.createElement('div');
  badge.className = '__walkthrough_badge';
  badge.textContent = stepNum;
  badge.style.cssText = [
    'position: fixed', 'z-index: 99999',
    'width: 28px', 'height: 28px', 'border-radius: 50%',
    'background: #e53e3e', 'color: white', 'font-weight: bold',
    'font-size: 14px', 'line-height: 28px', 'text-align: center',
    'font-family: sans-serif', 'pointer-events: none',
    'box-shadow: 0 2px 8px rgba(0,0,0,.4)'
  ].join(';');
  var rect = el.getBoundingClientRect();
  badge.style.top = (rect.top - 14) + 'px';
  badge.style.left = (rect.left - 14) + 'px';
  document.body.appendChild(badge);
})('#target-selector', '1');
```

**Add a directional arrow with label:**

```javascript
(function(selector, direction, label) {
  var el = document.querySelector(selector);
  if (!el) return;
  var rect = el.getBoundingClientRect();
  var arrow = document.createElement('div');
  arrow.className = '__walkthrough_arrow';
  var arrowW = 60, arrowH = 4;

  var css = [
    'position: fixed', 'z-index: 99999',
    'background: #e53e3e',
    'width: ' + arrowW + 'px', 'height: ' + arrowH + 'px'
  ];

  // Position based on direction
  switch (direction) {
    case 'left':
      css.push('top: ' + (rect.top + rect.height / 2 - arrowH / 2) + 'px');
      css.push('left: ' + (rect.left - arrowW - 8) + 'px');
      break;
    case 'right':
      css.push('top: ' + (rect.top + rect.height / 2 - arrowH / 2) + 'px');
      css.push('left: ' + (rect.right + 8) + 'px');
      break;
    case 'up':
      css.push('top: ' + (rect.top - arrowW - 8) + 'px');
      css.push('left: ' + (rect.left + rect.width / 2 - arrowH / 2) + 'px');
      css.push('width: ' + arrowH + 'px');
      css.push('height: ' + arrowW + 'px');
      break;
    case 'down':
      css.push('top: ' + (rect.bottom + 8) + 'px');
      css.push('left: ' + (rect.left + rect.width / 2 - arrowH / 2) + 'px');
      css.push('width: ' + arrowH + 'px');
      css.push('height: ' + arrowW + 'px');
      break;
  }
  arrow.style.cssText = css.join(';');
  document.body.appendChild(arrow);

  // Add label text
  if (label) {
    var text = document.createElement('div');
    text.className = '__walkthrough_arrow_label';
    text.textContent = label;
    text.style.cssText = [
      'position: fixed', 'z-index: 99999',
      'color: #e53e3e', 'font-weight: bold',
      'font-size: 13px', 'font-family: sans-serif',
      'background: rgba(255,255,255,0.9)',
      'padding: 2px 6px', 'border-radius: 3px',
      'white-space: nowrap', 'pointer-events: none'
    ].join(';');
    var arrowRect = arrow.getBoundingClientRect();
    text.style.top = (arrowRect.top - 20) + 'px';
    text.style.left = arrowRect.left + 'px';
    document.body.appendChild(text);
  }
})('#target-selector', 'right', 'Click here');
```

### 2d. Capture the screenshot

Use `browser_take_screenshot` to capture the annotated state.

Save each screenshot to `{OUTPUT_DIR}/{SLUG}/step-{N}.png`.

### 2e. Clean up annotations before the next step

```javascript
(function() {
  // Remove Driver.js overlay
  if (window.__walkthroughCurrentDriver) {
    window.__walkthroughCurrentDriver.destroy();
    delete window.__walkthroughCurrentDriver;
  }
  // Remove badges and arrows
  document.querySelectorAll(
    '.__walkthrough_badge, .__walkthrough_arrow, .__walkthrough_arrow_label'
  ).forEach(function(el) { el.remove(); });
  // Remove outlines
  document.querySelectorAll('[style*="outline: 3px solid"]').forEach(function(el) {
    el.style.outline = '';
    el.style.outlineOffset = '';
  });
})();
```

### 2f. Perform the step action

After capturing the "before action" screenshot with annotations showing
what to do, perform the actual action (click, type, etc.) so the app
advances to the next state.

**Re injection rule:** Driver.js and any injected CSS/JS is destroyed on
page navigation. After any `browser_navigate` or any click that causes a
full page load, re inject the Driver.js CSS and script before the next
annotation step.

## Phase 3: Assemble the Markdown

Write `{OUTPUT_DIR}/{SLUG}.md` with this structure:

```markdown
# {FEATURE} -- Step by Step

> Generated walkthrough with annotated screenshots.

---

## Step 1: {Step Title}

{One to three sentences explaining what to do and why.}

![Step 1](./{SLUG}/step-1.png)

---

## Step 2: {Step Title}

{Explanation.}

![Step 2](./{SLUG}/step-2.png)

---

(repeat for all steps)

---

## Summary

{Brief recap of the full workflow, 2 to 4 sentences.}
```

## Phase 4: Review

After generating the walkthrough:

1. Read the generated markdown file
2. Verify every screenshot path exists and points to a real file
3. Verify step numbering is sequential with no gaps
4. Present the walkthrough path to the user

## Annotation Selection Guide

Choose the right annotation for each step:

| Situation | Annotation |
|-----------|-----------|
| "Click this button" | Numbered badge + highlight box on the element |
| "Look at this section" | Driver.js popover with explanation text |
| "This connects to that" | Arrow pointing from source to target |
| "Fill in this field" | Highlight box around input + popover with instructions |
| "Notice this result" | Driver.js popover with side=top, descriptive text |

Combine annotations when useful. A step might have both a numbered badge
and a popover, or a highlight box and an arrow.

## Fallback: No CDN Access

If the target app cannot reach the CDN (air gapped, CORS issues), skip
Driver.js entirely and use only the pure DOM injection patterns (badges,
outlines, arrows). These require no external resources.

Test CDN availability after injecting the script tag. If
`window.driver` is undefined after 3 seconds, fall back.

## Safety

- **Localhost only.** Refuse any URL that is not localhost, 127.0.0.1,
  0.0.0.0, or `*.local` / `*.test`.
- **Headed browser.** Always use headed mode so the user can watch.
- **Read only intent.** The walkthrough documents existing behavior. Do
  not modify the application's code or data beyond what the walkthrough
  steps require (filling forms, clicking buttons).
- **Clean up.** Remove all injected DOM elements before closing the
  browser.
