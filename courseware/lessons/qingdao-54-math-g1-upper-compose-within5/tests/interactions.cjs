/* Exercise this course's authored pages with real pointer and choice events. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(path.resolve('student-web/node_modules/playwright-core'));

const [bodyFile, media, shots] = process.argv.slice(2);
const browserPath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const origin = 'http://lesson-fixture.test';

async function capture(page, scene, moment) {
  if (shots) await page.screenshot({ path: path.join(shots, `${scene}-${moment}.png`), animations: 'disabled' });
}

async function click(page, selector) {
  await page.locator(selector).click({ timeout: 5000 });
}

async function drag(page, from, to) {
  const source = await page.locator(from).boundingBox();
  const destination = await page.locator(to).boundingBox();
  assert.ok(source && destination);
  await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
  await page.mouse.down();
  await page.mouse.move(destination.x + destination.width / 2, destination.y + destination.height / 2, { steps: 12 });
  await page.mouse.up();
}

const count = (page, selector) => page.locator(selector).count();
const stars = (page) => page.locator('#star-n').textContent();
const demo = (page, state) => page.evaluate(state => {
  window.postMessage({ type: 'SET_WIDGET_STATE', state }, '*');
}, state);

async function seedTransfer(page) {
  await click(page, '#start-btn');
  assert.equal(await count(page, '#seed-left i'), 1);
  assert.equal(await count(page, '#seed-right i'), 4);
  await click(page, '#seed-choices [data-count="2"]');
  assert.equal(await stars(page), '0');
  assert.equal(await count(page, '#seed-right i'), 4);
  assert.match(await page.locator('#say').textContent(), /数一数卡片/);
  await capture(page, 'p02', 'first-wrong');
  await click(page, '#seed-choices [data-count="1"]');
  assert.equal(await count(page, '#seed-left i'), 2);
  assert.equal(await count(page, '#seed-right i'), 3);
  assert.equal(await stars(page), '1');
  await capture(page, 'p02', 'correct');
  await demo(page, { demo: false });
  await page.waitForFunction(() => document.querySelectorAll('#seed-left i').length === 1);
  await demo(page, { demo: true, left: 3 });
  await page.waitForFunction(() => document.querySelectorAll('#seed-left i').length === 3);
  assert.equal(await count(page, '#seed-right i'), 2);
  assert.equal(await stars(page), '0');
  await capture(page, 'p02', 'teacher-demo');
}

async function discTrays(page) {
  await click(page, '#start-btn');
  await drag(page, '.loose-disc:nth-child(1)', '#disc-left');
  assert.equal(await count(page, '#disc-left i'), 1);
  await drag(page, '.loose-disc:nth-child(2)', '#disc-left');
  assert.equal(await count(page, '#disc-left i'), 1);
  assert.equal(await count(page, '.loose-disc:not(.placed)'), 3);
  assert.equal(await stars(page), '0');
  assert.match(await page.locator('#say').textContent(), /跟图上一样多/);
  await capture(page, 'p04', 'first-wrong');
  await click(page, '.loose-disc:nth-child(2)');
  await click(page, '#disc-right');
  await drag(page, '.loose-disc:nth-child(3)', '#disc-right');
  await drag(page, '.loose-disc:nth-child(4)', '#disc-right');
  assert.equal(await count(page, '#disc-left i'), 1);
  assert.equal(await count(page, '#disc-right i'), 3);
  await capture(page, 'p04', 'correct');
  await click(page, '#disc-check');
  assert.equal(await stars(page), '1');
  assert.equal(await count(page, '#disc-target span:first-child i'), 2);
  await demo(page, { demo: false });
  await page.waitForFunction(() => document.querySelectorAll('#disc-left i').length === 0);
  await demo(page, { demo: true, round: 1, locations: [0,0,1,1] });
  await page.waitForFunction(() => document.querySelectorAll('#disc-left i').length === 2);
  assert.equal(await count(page, '#disc-right i'), 2);
  assert.equal(await stars(page), '0');
  await capture(page, 'p04', 'teacher-demo');
}

async function hiddenGroup(page) {
  await click(page, '#start-btn');
  await click(page, '#cover-choices button:first-child');
  assert.equal(await count(page, '#cover-lid i'), 0);
  assert.equal(await count(page, '#cover-lid.revealed'), 0);
  assert.equal(await stars(page), '0');
  assert.match(await page.locator('#say').textContent(), /位置已经对上/);
  await capture(page, 'p06', 'first-wrong');
  await click(page, '#cover-choices button:nth-child(2)');
  assert.equal(await count(page, '#cover-lid.revealed i'), 1);
  assert.equal(await page.locator('#cover-open-art').isVisible(), true);
  assert.equal(await page.locator('#cover-closed-art').isVisible(), false);
  assert.equal(await count(page, '#cover-total .cover-slot i'), 2);
  assert.equal(await stars(page), '1');
  await capture(page, 'p06', 'correct');
  await demo(page, { demo: false });
  await page.waitForFunction(() => document.querySelectorAll('#cover-lid i').length === 0);
  await demo(page, { demo: true, round: 2, reveal: true });
  await page.waitForFunction(() => document.querySelectorAll('#cover-lid .alternate').length === 1);
  assert.equal(await count(page, '#cover-open i'), 3);
  assert.equal(await count(page, '#cover-total .cover-slot i'), 4);
  assert.equal(await stars(page), '0');
  await capture(page, 'p06', 'teacher-demo');
}

(async () => {
  const body = JSON.parse(await fs.readFile(bodyFile, 'utf8'));
  const cases = new Map([['p02', seedTransfer], ['p04', discTrays], ['p06', hiddenGroup]]);
  const browser = await chromium.launch({ headless: true, executablePath: browserPath });
  try {
    for (const [id, check] of cases) {
      const scene = body.scenes.find(item => item.outlineId === id);
      const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route(`${origin}/**`, async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: scene.content.html });
        const match = /^\/api\/classroom-media\/[^/]+\/media\/(pic-[a-f0-9]{64}\.png)$/.exec(url.pathname);
        return match ? route.fulfill({ status: 200, contentType: 'image/png', path: path.join(media, match[1]) }) : route.abort();
      });
      await page.goto(origin);
      await page.waitForFunction(() => [...document.images].every(img => img.complete && img.naturalWidth > 0));
      await capture(page, id, 'initial');
      await check(page);
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`${id} initial, first wrong, correct, and teacher demo verified`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
