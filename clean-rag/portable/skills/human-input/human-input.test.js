// Run: node human-input.test.js. Needs playwright-core (NODE_PATH works) and a Chromium install.
const fs = require('fs');
const path = require('path');
const assert = require('assert');

// A broken scroll loop never returns, so fail instead of hanging.
setTimeout(() => { console.error('timed out'); process.exit(1); }, 90000).unref();

function loadPlaywright() {
  for (const name of ['playwright-core', 'playwright']) {
    try { return require(name); } catch {}
  }
  const base = process.env.LOCALAPPDATA
    ? path.join(process.env.LOCALAPPDATA, 'npm-cache', '_npx')
    : path.join(process.env.HOME || '', '.npm', '_npx');
  for (const d of fs.existsSync(base) ? fs.readdirSync(base) : []) {
    const p = path.join(base, d, 'node_modules', 'playwright-core');
    if (fs.existsSync(p)) return require(p);
  }
  throw new Error('playwright-core not found');
}

const { humanMove, humanClick, humanType, humanScroll } = require('./human-input.js');

// #b sits below the fold, so clicking it needs a scroll first.
const HTML = `<body style="margin:0"><input id=a style="margin:40px"><textarea id=t></textarea>
<div style="height:3000px"></div><button id=b style="margin:40px">go</button>
<div style="height:1000px"></div><script>
const ev = (t, e) => window.log.push({ t, trusted: e.isTrusted, ts: e.timeStamp, id: e.target.id,
  x: e.clientX, y: e.clientY, key: e.key, dy: e.deltaY });
window.log = [];
for (const t of ['click','keydown','keyup','mousedown','mouseup','mousemove','wheel','input'])
  document.addEventListener(t, (e) => ev(t, e), true);
</script></body>`;

(async () => {
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
  await page.setContent(HTML);
  const events = async (t) => (await page.evaluate(() => window.log.splice(0))).filter((e) => !t || e.t === t);
  const fast = { minMs: 5, maxMs: 15 };

  const text = 'Ab c.d@e-f_1';
  await events();
  await humanType(page, page.locator('#a'), text, fast);
  assert.strictEqual(await page.inputValue('#a'), text, 'typed text must equal input');
  const all = await events();
  assert(all.every((e) => e.trusted), 'all events must be trusted');
  const keys = all.filter((e) => e.t === 'keydown');
  assert.strictEqual(keys.map((e) => e.key).join(''), text, 'one real keydown per character');
  const gaps = { slow: [], other: [] };
  for (let i = 0; i < keys.length - 1; i++)
    gaps[/[\s.,;:@\-_]/.test(keys[i].key) ? 'slow' : 'other'].push(keys[i + 1].ts - keys[i].ts);
  const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
  assert(mean(gaps.slow) - mean(gaps.other) > 40, 'pause after spaces and punctuation');

  await humanType(page, page.locator('#t'), 'a\r\nb\rc\nd', fast);
  assert.strictEqual(await page.inputValue('#t'), 'a\nb\nc\nd', 'CR, LF and CRLF each type one newline');

  await humanType(page, page.locator('#a'), 'xé—y', { ...fast, clear: true });
  assert.strictEqual(await page.inputValue('#a'), 'xé—y', 'keys off a US keyboard still arrive');

  await humanType(page, page.locator('#a'), '', { ...fast, clear: true });
  assert.strictEqual(await page.inputValue('#a'), '', 'clear empties the field');

  await events();
  await humanMove(page, 600, 400);
  const moves = (await events('mousemove')).map((e) => [e.x, e.y]);
  assert.deepStrictEqual(moves.at(-1), [600, 400], 'pointer ends at the target');
  assert.deepStrictEqual(page.__mp, { x: 600, y: 400 }, 'last pointer position is remembered');
  const steps = moves.slice(1).map(([x, y], i) => Math.hypot(x - moves[i][0], y - moves[i][1]));
  const travel = Math.hypot(600 - moves[0][0], 400 - moves[0][1]);
  assert(Math.max(...steps) < travel / 2, 'pointer travels in many small steps');
  assert(steps.filter((s) => s > 0).at(-1) < 15, 'pointer eases into the target without a jump');

  assert.strictEqual(await page.evaluate(() => scrollY), 0);
  await humanClick(page, page.locator('#b'));
  const box = await page.locator('#b').boundingBox();
  const clickLog = await events();
  const click = clickLog.filter((e) => e.t === 'click').at(-1);
  assert(click && click.id === 'b', 'click lands on the element after scrolling it into view');
  assert(click.x >= box.x && click.x <= box.x + box.width && click.y >= box.y && click.y <= box.y + box.height, 'click inside box');
  const down = clickLog.find((e) => e.t === 'mousedown');
  const up = clickLog.find((e) => e.t === 'mouseup');
  const lastMove = clickLog.filter((e) => e.t === 'mousemove' && e.ts < down.ts).at(-1);
  assert(down.ts - lastMove.ts >= 45, 'hover before pressing');
  assert(up.ts - down.ts >= 30, 'button held before release');
  assert(clickLog.every((e) => e.trusted), 'click events must be trusted');

  await page.evaluate(() => scrollTo(0, 0));
  await page.waitForTimeout(100);
  await events();
  for (const [dy, expected] of [[777, 777], [-300, 477], [50, 527]]) {
    await humanScroll(page, dy);
    await page.waitForTimeout(200);
    assert.strictEqual(await page.evaluate(() => scrollY), expected, `scroll by ${dy} must sum to dy`);
    const wheelLog = await events('wheel');
    assert(wheelLog.every((e) => e.trusted), 'wheel events must be trusted');
    const wheels = wheelLog.map((e) => e.dy);
    assert.strictEqual(wheels.reduce((s, v) => s + v, 0), dy, 'wheel deltas sum to dy');
    assert(wheels.every((d) => Math.sign(d) === Math.sign(dy) && Math.abs(d) <= 168), 'chunks are small and one direction');
    if (Math.abs(dy) > 168) assert(wheels.length >= 2, 'large scrolls arrive in several wheels');
  }

  await browser.close();
  console.log('ok');
})().catch((e) => { console.error(e); process.exit(1); });
