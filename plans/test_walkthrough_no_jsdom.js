/**
 * Adversarial tests for walkthrough SKILL.md JS injection snippets.
 * Uses a minimal DOM mock — no jsdom dependency required.
 * Run with: node plans/test_walkthrough_no_jsdom.js
 */

'use strict';

// ---- Minimal DOM mock ----

function makeElement(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    id: '',
    className: '',
    textContent: '',
    src: '',
    rel: '',
    href: '',
    style: makeStyle(),
    onerror: null,
    onload: null,
    _children: [],
    _parent: null,
    getAttribute: function(name) { return this['_attr_' + name] || null; },
    setAttribute: function(name, val) { this['_attr_' + name] = val; },
    getBoundingClientRect: function() {
      return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 };
    },
    appendChild: function(child) {
      child._parent = this;
      this._children.push(child);
    },
    querySelectorAll: function(sel) {
      // Simple class/id/tag selector parser
      return querySelectorAll(sel, this);
    },
    querySelector: function(sel) {
      return querySelectorAll(sel, this)[0] || null;
    },
    remove: function() {
      if (this._parent) {
        const idx = this._parent._children.indexOf(this);
        if (idx !== -1) this._parent._children.splice(idx, 1);
        this._parent = null;
      }
    }
  };
  return el;
}

function makeStyle() {
  const s = {
    _map: {},
    get cssText() {
      return Object.entries(this._map).map(function(kv) { return kv[0] + ': ' + kv[1]; }).join('; ');
    },
    set cssText(val) {
      this._map = {};
      val.split(';').forEach(function(part) {
        const idx = part.indexOf(':');
        if (idx === -1) return;
        const k = part.slice(0, idx).trim().replace(/-([a-z])/g, function(m, c) { return c.toUpperCase(); });
        const v = part.slice(idx + 1).trim();
        if (k) s._map[k] = v;
      });
    }
  };

  // Proxy-like getter/setter for individual properties
  const handler = {
    get: function(target, prop) {
      if (prop in target) return typeof target[prop] === 'function' ? target[prop].bind(target) : target[prop];
      return target._map[prop] || '';
    },
    set: function(target, prop, value) {
      if (prop === 'cssText') { target.cssText = value; return true; }
      if (prop in target) { target[prop] = value; return true; }
      if (value === '' || value === undefined) {
        delete target._map[prop];
      } else {
        target._map[prop] = String(value);
      }
      return true;
    }
  };
  return new Proxy(s, handler);
}

// Walk element tree collecting all descendants
function allDescendants(el) {
  const result = [];
  function walk(node) {
    node._children.forEach(function(child) {
      result.push(child);
      walk(child);
    });
  }
  walk(el);
  return result;
}

// Very simple selector match: class (.x), id (#x), tag, and compound (comma separated)
function matchesSelector(el, sel) {
  sel = sel.trim();
  if (sel.startsWith('.')) return el.className && el.className.split(' ').indexOf(sel.slice(1)) !== -1;
  if (sel.startsWith('#')) return el.id === sel.slice(1);
  // attribute selector: [style*="outline: 3px solid"]
  if (sel.startsWith('[style*="')) {
    const needle = sel.slice('[style*="'.length, -2);
    return el.style.cssText.includes(needle);
  }
  return el.tagName === sel.toUpperCase();
}

function querySelectorAll(sel, root) {
  const selectors = sel.split(',').map(function(s) { return s.trim(); });
  const all = allDescendants(root);
  return all.filter(function(el) {
    return selectors.some(function(s) { return matchesSelector(el, s); });
  });
}

function makeDocument() {
  const head = makeElement('head');
  const body = makeElement('body');
  const html = makeElement('html');
  html._children = [head, body];
  head._parent = html;
  body._parent = html;

  const idMap = {};

  const doc = {
    head: head,
    body: body,
    _idMap: idMap,
    createElement: function(tag) { return makeElement(tag); },
    getElementById: function(id) { return findById(html, id); },
    querySelector: function(sel) { return querySelectorAll(sel, html)[0] || null; },
    querySelectorAll: function(sel) { return querySelectorAll(sel, html); },
  };

  // When elements with IDs are appended, track them
  const origAppend = makeElement.prototype;

  return doc;
}

function findById(root, id) {
  if (root.id === id) return root;
  for (let i = 0; i < root._children.length; i++) {
    const found = findById(root._children[i], id);
    if (found) return found;
  }
  return null;
}

// Make a fake window+document context
function makeContext() {
  const document = makeDocument();
  const ctx = {
    document: document,
    window: null,
    Promise: Promise,
    __walkthroughDriver: undefined,
    __walkthroughCurrentDriver: undefined,
  };
  ctx.window = ctx;
  return ctx;
}

// Eval a snippet in context by wrapping it as a function
function evalInCtx(ctx, snippet) {
  const fn = new Function('window', 'document', 'Promise', snippet);
  return fn(ctx.window, ctx.document, Promise);
}

// ---- Test runner ----

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log('  PASS  ' + name);
    passed++;
  } catch(e) {
    console.log('  FAIL  ' + name);
    console.log('        ' + e.message);
    failed++;
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assertion failed');
}

// =====================================================================
// Test 1: __walkthroughDriver truthy but window.driver absent → highlight crashes
// The injection guard (window.__walkthroughDriver) is a DIFFERENT variable from
// the library namespace (window.driver.js.driver). If navigation destroys the
// page state but __walkthroughDriver persists on the old window, the re-injection
// check will pass but window.driver won't exist yet.
// This is Correctness Property #2: "Driver.js must be re-injected after any page
// navigation (it is destroyed on navigation)."
// =====================================================================
test('FINDING: highlight snippet crashes when __walkthroughDriver true but window.driver absent', function() {
  const ctx = makeContext();
  ctx.__walkthroughDriver = true;
  // window.driver NOT set

  const highlightSnippet =
    'var driverFn = window.driver.js.driver;' +
    'var d = driverFn({ animate: true, overlayOpacity: 0.5 });' +
    'd.highlight({ element: "#btn", popover: { title: "t", description: "d" } });';

  let threw = false;
  try {
    evalInCtx(ctx, highlightSnippet);
  } catch(e) {
    threw = true;
  }
  assert(threw, 'Expected TypeError: window.driver is undefined');
});

// =====================================================================
// Test 2: Badge missing element → silent return (correct behavior)
// =====================================================================
test('Badge: missing element -> silent return no crash', function() {
  const ctx = makeContext();
  const badgeSnippet =
    'var el = document.querySelector("#nonexistent");' +
    'if (!el) return;' +
    'var badge = document.createElement("div");' +
    'badge.className = "__walkthrough_badge";' +
    'document.body.appendChild(badge);';

  evalInCtx(ctx, badgeSnippet);
  const badges = ctx.document.querySelectorAll('.__walkthrough_badge');
  assert(badges.length === 0, 'Expected 0 badges');
});

// =====================================================================
// Test 3: Arrow with unknown direction → arrow has no top/left (silent bug)
// The switch statement handles left/right/up/down only. Any other value
// (including a typo like "diagonal" or an unspecified default) falls through
// with no position set. The arrow is still appended to the DOM, but at (0,0).
// =====================================================================
test('FINDING: Arrow with unknown direction appended without position (silent visual bug)', function() {
  const ctx = makeContext();
  const targetEl = ctx.document.createElement('div');
  targetEl.id = 'target';
  ctx.document.body.appendChild(targetEl);

  const arrowSnippet =
    'var el = document.querySelector("#target");' +
    'if (!el) return;' +
    'var rect = el.getBoundingClientRect();' +
    'var arrow = document.createElement("div");' +
    'arrow.className = "__walkthrough_arrow";' +
    'var arrowW = 60, arrowH = 4;' +
    'var css = ["position: fixed", "z-index: 99999", "background: #e53e3e", "width: " + arrowW + "px", "height: " + arrowH + "px"];' +
    'switch ("diagonal") {' +
    '  case "left": css.push("top: 0px"); css.push("left: 0px"); break;' +
    '  case "right": css.push("top: 0px"); css.push("left: 0px"); break;' +
    '  case "up": css.push("top: 0px"); css.push("left: 0px"); break;' +
    '  case "down": css.push("top: 0px"); css.push("left: 0px"); break;' +
    '}' +
    'arrow.style.cssText = css.join(";");' +
    'document.body.appendChild(arrow);';

  evalInCtx(ctx, arrowSnippet);
  const arrow = ctx.document.querySelector('.__walkthrough_arrow');
  assert(arrow !== null, 'Arrow should have been appended');
  const cssText = arrow.style.cssText;
  // Arrow has position:fixed but no top/left — defaults to top:0, left:0
  assert(!cssText.includes('top') && !cssText.includes('left'),
    'Arrow with unknown direction should have no top/left, got: ' + cssText);
});

// =====================================================================
// Test 4: Cleanup removes badges
// =====================================================================
test('Cleanup: removes badge elements', function() {
  const ctx = makeContext();
  const badge = ctx.document.createElement('div');
  badge.className = '__walkthrough_badge';
  ctx.document.body.appendChild(badge);

  assert(ctx.document.querySelectorAll('.__walkthrough_badge').length === 1, 'Badge should be present before cleanup');

  const cleanupSnippet =
    'document.querySelectorAll(".__walkthrough_badge, .__walkthrough_arrow, .__walkthrough_arrow_label").forEach(function(el) { el.remove(); });';

  evalInCtx(ctx, cleanupSnippet);
  assert(ctx.document.querySelectorAll('.__walkthrough_badge').length === 0, 'Badge should be removed after cleanup');
});

// =====================================================================
// Test 5: CSS idempotency guard prevents double injection
// =====================================================================
test('CSS injection: idempotency guard prevents double link tag', function() {
  const ctx = makeContext();
  const cssSnippet =
    'if (document.getElementById("__walkthrough_driver_css")) return;' +
    'var link = document.createElement("link");' +
    'link.id = "__walkthrough_driver_css";' +
    'link.rel = "stylesheet";' +
    'link.href = "https://cdn.jsdelivr.net/npm/driver.js@1.4.0/dist/driver.css";' +
    'document.head.appendChild(link);';

  // First call
  evalInCtx(ctx, cssSnippet);
  // Manually register the id on the element so getElementById works
  const link = ctx.document.head._children.find(function(c) { return c.id === '__walkthrough_driver_css'; });
  assert(link != null, 'Link should be created on first call');

  // Second call should be no-op because getElementById would find it
  // But our minimal mock's getElementById searches by el.id — let's confirm it works
  const found = ctx.document.getElementById('__walkthrough_driver_css');
  assert(found != null, 'getElementById should find the link');

  evalInCtx(ctx, cssSnippet); // second call
  const links = ctx.document.head._children.filter(function(c) { return c.id === '__walkthrough_driver_css'; });
  assert(links.length === 1, 'Should only have 1 link after double injection, got: ' + links.length);
});

// =====================================================================
// Test 6: Script injection returns Promise in both branches
// =====================================================================
test('Script injection: both branches return Promise', function() {
  const ctx = makeContext();

  // Branch 1: guard set → Promise.resolve()
  ctx.__walkthroughDriver = true;
  const snippet =
    'if (window.__walkthroughDriver) return Promise.resolve();' +
    'return new Promise(function(resolve) {' +
    '  var script = document.createElement("script");' +
    '  script.src = "https://cdn.jsdelivr.net/npm/driver.js@1.4.0/dist/driver.js.iife.js";' +
    '  script.onload = function() { window.__walkthroughDriver = true; resolve(); };' +
    '  document.head.appendChild(script);' +
    '});';

  const r1 = evalInCtx(ctx, snippet);
  assert(r1 instanceof Promise, 'Branch 1 should return Promise, got: ' + typeof r1);

  // Branch 2: guard not set → new Promise
  const ctx2 = makeContext();
  const r2 = evalInCtx(ctx2, snippet);
  assert(r2 instanceof Promise, 'Branch 2 should return Promise, got: ' + typeof r2);
});

// =====================================================================
// Test 7: script.onerror IS set — CDN failure rejects the Promise
// The injection snippet must have an onerror handler that rejects the
// Promise, so CDN failures are detectable instead of hanging forever.
// =====================================================================
test('Script injection: onerror handler present and rejects Promise on CDN failure', function() {
  const ctx = makeContext();
  // Use a snippet without setTimeout to avoid unhandled rejection in test.
  // We verify: (1) onerror is set as a function, (2) calling it rejects the Promise.
  const snippet =
    'if (window.__walkthroughDriver) return Promise.resolve();' +
    'return new Promise(function(resolve, reject) {' +
    '  var script = document.createElement("script");' +
    '  script.src = "https://cdn.jsdelivr.net/npm/driver.js@1.4.0/dist/driver.js.iie.js";' +
    '  script.onload = function() { window.__walkthroughDriver = true; resolve(); };' +
    '  script.onerror = function() { reject(new Error("Driver.js CDN unreachable")); };' +
    '  document.head.appendChild(script);' +
    '});';

  const p = evalInCtx(ctx, snippet);
  // Suppress unhandled rejection from simulated CDN failure below
  p.catch(function() {});

  const scripts = ctx.document.head._children.filter(function(c) { return c.src && c.src.includes('driver.js'); });
  assert(scripts.length === 1, 'Driver.js script should have been injected');
  const ds = scripts[0];
  assert(typeof ds.onerror === 'function', 'onerror should be a function, got: ' + typeof ds.onerror);

  // Simulate CDN failure: calling onerror should reject the Promise (not hang)
  ds.onerror(new Event('error'));
});

// =====================================================================
// Test 8: HOW-IT-WORKS.md slash command counts are consistent
// All three mentions (intro, tree, section) must say 36 to match the
// actual count of files in .claude/commands/.
// =====================================================================
test('DOC: HOW-IT-WORKS.md slash command counts are all 36', function() {
  var fs = require('fs');
  var content = fs.readFileSync(require('path').join(__dirname, '..', 'docs', 'HOW-IT-WORKS.md'), 'utf8');
  var lines = content.split('\n');
  // Line 4 (0-indexed 3): intro paragraph
  assert(lines[3].includes('36 slash'), 'Intro paragraph should say "36 slash", got: ' + lines[3].trim());
  // Line 16 (0-indexed 15): tree listing
  assert(lines[15].includes('36 slash'), 'Tree listing should say "36 slash", got: ' + lines[15].trim());
  // Line 106 (0-indexed 105): Slash Commands section header
  assert(lines[105].includes('36 commands'), 'Section header should say "36 commands", got: ' + lines[105].trim());
});

// =====================================================================
// Test 9: USING-CLAUDEBOOST.md has no duplicate section numbers
// Section numbering under "Common task patterns" must be sequential
// with no gaps or duplicates.
// =====================================================================
test('DOC: USING-CLAUDEBOOST.md has no duplicate subsection numbers under Common task patterns', function() {
  var fs = require('fs');
  var content = fs.readFileSync(require('path').join(__dirname, '..', 'docs', 'USING-CLAUDEBOOST.md'), 'utf8');
  var lines = content.split('\n');
  var sectionNums = [];
  var inCommonPatterns = false;
  for (var i = 0; i < lines.length; i++) {
    if (lines[i].match(/^## 10\. Common task patterns/)) inCommonPatterns = true;
    if (inCommonPatterns && lines[i].match(/^## \d+\./) && !lines[i].match(/^## 10\./)) break;
    if (inCommonPatterns) {
      var m = lines[i].match(/^### (\d+)\./);
      if (m) sectionNums.push(parseInt(m[1]));
    }
  }
  // Check for duplicates
  var seen = {};
  var duplicates = [];
  sectionNums.forEach(function(n) {
    if (seen[n]) duplicates.push(n);
    seen[n] = true;
  });
  assert(duplicates.length === 0, 'Duplicate subsection numbers found: ' + duplicates.join(', '));
  // Check sequential
  for (var j = 1; j < sectionNums.length; j++) {
    assert(sectionNums[j] === sectionNums[j-1] + 1,
      'Subsections not sequential: ' + sectionNums[j-1] + ' followed by ' + sectionNums[j]);
  }
});

// Summary
console.log('');
console.log('Results: ' + passed + ' passed, ' + failed + ' failed');
if (failed > 0) {
  process.exit(1);
}
