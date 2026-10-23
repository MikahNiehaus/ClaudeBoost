---
name: human-input
description: WHEN driving a browser with Playwright MCP and the page reacts to how input arrives (silently ignored clicks, desynced fields, bot challenges, rate limits); type, move, click and scroll with real, human-paced events instead of fill() or script-dispatched clicks. USE before falling back to evaluate-based clicks.
---
# Human-paced browser input

Real input goes through CDP `Input.dispatch*`, so the page sees `isTrusted: true`.
`fill()` sends one text insert with no key events. `evaluate(el.click())` and
`dispatchEvent` read `isTrusted: false`, and a page cannot change that.

## Order of preference

1. `browser_click` and `browser_type` (with `slowly: true`) for ordinary fields.
2. The helpers in `human-input.js` through `browser_run_code` when the page
   wants pointer travel, key timing or scrolling.
3. Script-dispatched events or native setters only for a widget that rejects
   real input, and never for the final commit action of a form.

## Use the helpers

Paste the whole of `human-input.js` at the top of the `browser_run_code` body,
then call:

- `humanType(page, locator, text, { clear })` clicks the field, then one real
  key press per character, 40 to 160 ms apart, slower after spaces and
  punctuation. No typos are injected.
- `humanClick(page, locator)` scrolls into view, curves to a random point inside
  the element, hovers briefly, then presses and releases.
- `humanMove(page, x, y)` moves the pointer along an eased Bezier curve.
- `humanScroll(page, dy)` wheel-scrolls in chunks that sum to exactly `dy`.

```js
async (page) => {
  /* paste human-input.js here */
  await humanType(page, page.getByLabel('Email'), 'name@example.com');
  await humanClick(page, page.getByRole('button', { name: 'Continue' }));
}
```

## Rules

- Spend real time on a page before committing: read, scroll, then fill.
- Use `browser_fill_form` for passwords, not the typing helpers.
- A newline types Enter. In a single-line field that can submit the form, so
  send newlines only to a textarea.
- Do not retry a refused commit click with a synthetic one. Hand the tab to the
  human instead.
- No stealth patches.

## Verify

Log `isTrusted` once to confirm a setup produces trusted events:
`document.addEventListener('click', e => console.log('isTrusted', e.isTrusted), true)`,
then read it with `browser_console_messages`.

`node human-input.test.js` drives the helpers in headless Chromium and checks
typed text, click position, trusted events and scroll distance.
