// Paste at the top of a browser_run_code body. Uses only `page`.
const rand = (a, b) => a + Math.random() * (b - a);
const pause = (page, a, b) => page.waitForTimeout(Math.round(rand(a, b)));

// Eased cubic Bezier from the last pointer position.
async function humanMove(page, x, y, { steps = 22 } = {}) {
  const from = page.__mp || { x: rand(20, 200), y: rand(20, 200) };
  const dx = x - from.x, dy = y - from.y;
  const bend = Math.min(80, Math.hypot(dx, dy) * 0.25);
  const c1 = { x: from.x + dx * 0.3 + rand(-bend, bend), y: from.y + dy * 0.3 + rand(-bend, bend) };
  const c2 = { x: from.x + dx * 0.7 + rand(-bend, bend), y: from.y + dy * 0.7 + rand(-bend, bend) };
  for (let i = 1; i <= steps; i++) {
    const lin = i / steps;
    const t = lin * lin * (3 - 2 * lin);
    const u = 1 - t;
    const px = u ** 3 * from.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t ** 3 * x;
    const py = u ** 3 * from.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t ** 3 * y;
    await page.mouse.move(px, py);
    await pause(page, 4, 14);
  }
  await page.mouse.move(x, y);
  page.__mp = { x, y };
}

async function humanClick(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error('humanClick: element has no bounding box');
  const x = box.x + box.width * rand(0.25, 0.75);
  const y = box.y + box.height * rand(0.25, 0.75);
  await humanMove(page, x, y);
  await pause(page, 60, 200);
  await page.mouse.down();
  await pause(page, 40, 110);
  await page.mouse.up();
}

// Keys a US keyboard cannot press fall back to insertText.
async function humanType(page, locator, text, { minMs = 40, maxMs = 160, clear = false } = {}) {
  await humanClick(page, locator);
  if (clear) {
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.press('Backspace');
  }
  // Playwright presses both \r and \n as Enter, so CRLF would type two newlines.
  for (const ch of text.replace(/\r\n?/g, '\n')) {
    if (ch === '\n') await page.keyboard.press('Enter');
    else {
      try { await page.keyboard.press(ch); }
      catch { await page.keyboard.insertText(ch); }
    }
    const slow = /[\s.,;:@\-_]/.test(ch) ? rand(60, 180) : 0;
    await pause(page, minMs + slow, maxMs + slow);
  }
}

// Chunks sum to exactly dy.
async function humanScroll(page, dy, { chunk = 120 } = {}) {
  let left = dy;
  const dir = Math.sign(dy) || 1;
  while (Math.abs(left) > 0) {
    const part = dir * Math.min(Math.abs(left), Math.round(rand(chunk * 0.6, chunk * 1.4)));
    await page.mouse.wheel(0, part);
    left -= part;
    await pause(page, 40, 160);
  }
}

if (typeof module !== 'undefined') module.exports = { humanMove, humanClick, humanType, humanScroll };
