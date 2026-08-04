/**
 * Adversarial tests for walkthrough SKILL.md JS injection snippets.
 * Run with: node plans/test_walkthrough_js.js
 * Requires: npm install jsdom (in ClaudeBoost root or globally)
 */

'use strict';

const { JSDOM } = require('jsdom');

function makeDom() {
  const dom = new JSDOM('<!DOCTYPE html><html><head></head><body></body></html>', {
    url: 'http://localhost/',
    runScripts: 'dangerously',
  });
  return dom;
}

function evalInDom(dom, src) {
  return dom.window.eval(src);
}

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log('  PASS  ' + name);
    passed++;
  } catch (e) {
    console.log('  FAIL  ' + name);
    console.log('        ' + e.message);
    failed++;
  }
}

function assert(condition, msg) {
  if (!condition) throw new Error(msg || 'assertion failed');
}

// Test 1: __walkthroughDriver truthy but window.driver absent → highlight crashes
// This proves the injection guard flag (__walkthroughDriver) is decoupled from
// the actual library namespace (window.driver.js.driver). If the script loads
// but sets a different global, or if re-injection is skipped after navigation
// because __walkthroughDriver was already true, the highlight call will TypeError.
test('DriverJS guard: __walkthroughDriver truthy but window.driver absent -> highlight crashes', function() {
  const dom = makeDom();
  dom.window.__walkthroughDriver = true;
  // window.driver NOT set (CDN script not loaded)

  const highlightSnippet =
    '(function(selector, title, description, side) {' +
    '  var driverFn = window.driver.js.driver;' +
    '  var d = driverFn({ animate: true, overlayOpacity: 0.5, stagePadding: 8, stageRadius: 5, allowClose: false });' +
    '  d.highlight({ element: selector, popover: { title: title, description: description, side: side || "bottom", align: "center" } });' +
    '  window.__walkthroughCurrentDriver = d;' +
    '})(\'#some-selector\', \'Step 1\', \'Click here\', \'bottom\');';

  let threw = false;
  try {
    evalInDom(dom, highlightSnippet);
  } catch (e) {
    threw = true;
  }
  assert(threw, 'Expected TypeError when window.driver is absent but __walkthroughDriver is true');
});

// Test 2: Badge snippet silently returns when element missing
test('Badge snippet: missing element -> silent return no crash', function() {
  const dom = makeDom();
  const badgeSnippet =
    '(function(selector, stepNum) {' +
    '  var el = document.querySelector(selector);' +
    '  if (!el) return;' +
    '  el.style.outline = "3px solid #e53e3e";' +
    '  el.style.outlineOffset = "2px";' +
    '  var badge = document.createElement("div");' +
    '  badge.className = "__walkthrough_badge";' +
    '  badge.textContent = stepNum;' +
    '  var rect = el.getBoundingClientRect();' +
    '  badge.style.top = (rect.top - 14) + "px";' +
    '  badge.style.left = (rect.left - 14) + "px";' +
    '  document.body.appendChild(badge);' +
    '})("#nonexistent-element", "1");';
  evalInDom(dom, badgeSnippet);
  const badges = dom.window.document.querySelectorAll('.__walkthrough_badge');
  assert(badges.length === 0, 'Expected 0 badges, got ' + badges.length);
});

// Test 3: Arrow snippet with unknown direction — arrow appended without position
test('Arrow snippet: unknown direction -> arrow appended without top/left', function() {
  const dom = makeDom();
  dom.window.document.body.innerHTML = '<div id="target">target</div>';

  const arrowSnippet =
    '(function(selector, direction, label) {' +
    '  var el = document.querySelector(selector);' +
    '  if (!el) return;' +
    '  var rect = el.getBoundingClientRect();' +
    '  var arrow = document.createElement("div");' +
    '  arrow.className = "__walkthrough_arrow";' +
    '  var arrowW = 60, arrowH = 4;' +
    '  var css = ["position: fixed", "z-index: 99999", "background: #e53e3e", "width: " + arrowW + "px", "height: " + arrowH + "px"];' +
    '  switch (direction) {' +
    '    case "left": css.push("top: " + (rect.top + rect.height / 2 - arrowH / 2) + "px"); css.push("left: " + (rect.left - arrowW - 8) + "px"); break;' +
    '    case "right": css.push("top: " + (rect.top + rect.height / 2 - arrowH / 2) + "px"); css.push("left: " + (rect.right + 8) + "px"); break;' +
    '    case "up": css.push("top: " + (rect.top - arrowW - 8) + "px"); css.push("left: " + (rect.left + rect.width / 2 - arrowH / 2) + "px"); css.push("width: " + arrowH + "px"); css.push("height: " + arrowW + "px"); break;' +
    '    case "down": css.push("top: " + (rect.bottom + 8) + "px"); css.push("left: " + (rect.left + rect.width / 2 - arrowH / 2) + "px"); css.push("width: " + arrowH + "px"); css.push("height: " + arrowW + "px"); break;' +
    '  }' +
    '  arrow.style.cssText = css.join(";");' +
    '  document.body.appendChild(arrow);' +
    '})("#target", "diagonal", null);';

  evalInDom(dom, arrowSnippet);
  const arrow = dom.window.document.querySelector('.__walkthrough_arrow');
  assert(arrow !== null, 'Arrow should have been appended');
  // No top or left in the style — silent visual bug
  const cssText = arrow.style.cssText;
  assert(!cssText.includes('top:') && !cssText.includes('left:'),
    'Arrow with unknown direction should lack top/left, got: ' + cssText);
});

// Test 4: Cleanup clears outlines set by badge snippet
test('Cleanup snippet: clears outline set by badge snippet', function() {
  const dom = makeDom();
  dom.window.document.body.innerHTML = '<button id="btn">Button</button>';
  evalInDom(dom, 'document.querySelector("#btn").style.outline = "3px solid #e53e3e";');
  evalInDom(dom, 'document.querySelector("#btn").style.outlineOffset = "2px";');

  const cleanupSnippet =
    '(function() {' +
    '  if (window.__walkthroughCurrentDriver) { window.__walkthroughCurrentDriver.destroy(); delete window.__walkthroughCurrentDriver; }' +
    '  document.querySelectorAll(".__walkthrough_badge, .__walkthrough_arrow, .__walkthrough_arrow_label").forEach(function(el) { el.remove(); });' +
    '  document.querySelectorAll(\'[style*="outline: 3px solid"]\').forEach(function(el) { el.style.outline = ""; el.style.outlineOffset = ""; });' +
    '})();';

  evalInDom(dom, cleanupSnippet);
  const btn = dom.window.document.querySelector('#btn');
  const outlineVal = btn.style.outline;
  assert(outlineVal === '' || outlineVal === 'none',
    'Outline should be cleared, got: "' + outlineVal + '"');
});

// Test 5: Script injection — both branches return a Promise
test('DriverJS script injection: both branches return Promise', function() {
  const dom = makeDom();
  const injectionSnippet =
    '(function() {' +
    '  if (window.__walkthroughDriver) return Promise.resolve();' +
    '  return new Promise(function(resolve) {' +
    '    var script = document.createElement("script");' +
    '    script.src = "https://cdn.jsdelivr.net/npm/driver.js@1.4.0/dist/driver.js.iife.js";' +
    '    script.onload = function() { window.__walkthroughDriver = true; resolve(); };' +
    '    document.head.appendChild(script);' +
    '  });' +
    '})();';

  dom.window.__walkthroughDriver = true;
  const r1 = evalInDom(dom, injectionSnippet);
  assert(r1 instanceof dom.window.Promise, 'Branch 1 (guard set) should return Promise');

  const dom2 = makeDom();
  const r2 = evalInDom(dom2, injectionSnippet);
  assert(r2 instanceof dom2.window.Promise, 'Branch 2 (guard not set) should return Promise');
});

// Test 6: onerror is absent on injected script tag
test('DriverJS script injection: onerror absent -> hung Promise on CDN failure', function() {
  const dom = makeDom();
  const injectionSnippet =
    '(function() {' +
    '  if (window.__walkthroughDriver) return Promise.resolve();' +
    '  return new Promise(function(resolve) {' +
    '    var script = document.createElement("script");' +
    '    script.src = "https://cdn.jsdelivr.net/npm/driver.js@1.4.0/dist/driver.js.iife.js";' +
    '    script.onload = function() { window.__walkthroughDriver = true; resolve(); };' +
    '    document.head.appendChild(script);' +
    '  });' +
    '})();';

  evalInDom(dom, injectionSnippet);
  const scripts = dom.window.document.head.querySelectorAll('script');
  const ds = Array.from(scripts).find(function(s) { return s.src && s.src.includes('driver.js'); });
  assert(ds != null, 'Driver.js script tag should be injected');
  assert(ds.onerror === null, 'onerror should be null (absent), got: ' + ds.onerror);
});

// Test 7: CSS idempotency guard works
test('CSS injection: idempotency guard prevents double injection', function() {
  const dom = makeDom();
  const cssSnippet =
    '(function() {' +
    '  if (document.getElementById("__walkthrough_driver_css")) return;' +
    '  var link = document.createElement("link");' +
    '  link.id = "__walkthrough_driver_css";' +
    '  link.rel = "stylesheet";' +
    '  link.href = "https://cdn.jsdelivr.net/npm/driver.js@1.4.0/dist/driver.css";' +
    '  document.head.appendChild(link);' +
    '})();';
  evalInDom(dom, cssSnippet);
  evalInDom(dom, cssSnippet);
  const links = dom.window.document.head.querySelectorAll('link#__walkthrough_driver_css');
  assert(links.length === 1, 'Should only have 1 driver CSS link after double injection, got: ' + links.length);
});

// Test 8: Highlight snippet crashes if window.driver is undefined (no guard)
test('Highlight snippet: no guard for window.driver -> TypeError if driver not loaded', function() {
  const dom = makeDom();
  // window.driver is undefined
  const highlightSnippet =
    '(function(selector, title, description, side) {' +
    '  var driverFn = window.driver.js.driver;' +
    '  var d = driverFn({ animate: true });' +
    '  d.highlight({ element: selector, popover: { title: title, description: description } });' +
    '  window.__walkthroughCurrentDriver = d;' +
    '})("#btn", "Step", "desc", "bottom");';

  let threw = false;
  let msg = '';
  try {
    evalInDom(dom, highlightSnippet);
  } catch(e) {
    threw = true;
    msg = e.message;
  }
  assert(threw, 'Expected TypeError when window.driver is undefined');
  assert(msg.toLowerCase().includes('undefined') || msg.toLowerCase().includes('cannot') || msg.toLowerCase().includes('null'),
    'Expected undefined/null property error, got: ' + msg);
});

console.log('');
console.log('Results: ' + passed + ' passed, ' + failed + ' failed');
if (failed > 0) {
  process.exit(1);
}
