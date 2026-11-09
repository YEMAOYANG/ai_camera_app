/* Verify ordinal position and range feedback with the browser and built lesson assets. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(path.resolve('student-web/node_modules/playwright-core'));

const [bodyFile, media, shots] = process.argv.slice(2);
const origin = 'http://ordinal-fixture.test';

const click = (page, selector) => page.locator(selector).click({ timeout: 5000 });
const count = (page, selector) => page.locator(selector).count();
const stars = (page) => page.locator('#star-n').textContent();

async function capture(page, id, moment) {
  if (shots) {
    await page.screenshot({ path: path.join(shots, id + '-' + moment + '.png'), animations: 'disabled' });
  }
}

async function demo(page, state, selector) {
  await page.evaluate(state => window.postMessage({ type: 'SET_WIDGET_STATE', state }, '*'), state);
  await page.locator(selector).waitFor({ timeout: 3000 });
}

async function wrong(page, id, button, success, hint) {
  await click(page, button);
  assert.equal(await stars(page), '0');
  assert.equal(await count(page, success), 0);
  assert.match(await page.locator('#say.no').textContent(), hint);
  await capture(page, id, 'first-wrong');
}

async function horizontal(page) {
  await click(page, '#start-btn');
  assert.equal(await count(page, '#row-task .rank-dot'), 4);
  await wrong(page, 'p02', '#row-piano', '#row-exhibits .success', /回到门边/);
  await click(page, '#row-harp');
  assert.equal(await count(page, '#row-harp.success'), 1);
  assert.equal(await stars(page), '1');
  await capture(page, 'p02', 'correct');
  await page.locator('#row-ranks [data-rank="2"]').waitFor({ timeout: 3000 });
  assert.equal(await count(page, '#row-trumpet.active'), 1);
  await click(page, '#row-ranks [data-rank="2"]');
  assert.equal(await stars(page), '2');
  await demo(page, { demo: false }, '#row-harp:enabled');
  await demo(page, { demo: true, rank: 3 }, '#row-piano.active');
  assert.equal(await count(page, '#row-task .rank-dot'), 3);
  assert.equal(await count(page, '#row-exhibits button:enabled'), 0);
  assert.equal(await stars(page), '0');
  await capture(page, 'p02', 'teacher-demo');
}

async function vertical(page) {
  await click(page, '#start-btn');
  assert.equal(await count(page, '#rack-task .rack-dot'), 3);
  await wrong(page, 'p04', '#rack-two', '#rack-shelves .success', /箭头从哪头/);
  await click(page, '#rack-three');
  assert.equal(await count(page, '#rack-three.success'), 1);
  assert.equal(await stars(page), '1');
  await capture(page, 'p04', 'correct');
  await page.locator('#rack-direction.up').waitFor({ timeout: 3000 });
  assert.equal(await count(page, '#rack-task .rack-dot'), 2);
  await click(page, '#rack-three');
  assert.equal(await stars(page), '2');
  await demo(page, { demo: false }, '#rack-one:enabled');
  await demo(page, { demo: true, up: true, rank: 1, mark: 3 }, '#rack-four.active');
  assert.equal(await count(page, '#rack-direction.up'), 1);
  assert.equal(await count(page, '#rack-shelves button:enabled'), 0);
  assert.equal(await stars(page), '0');
  await capture(page, 'p04', 'teacher-demo');
}

async function ranges(page) {
  await click(page, '#start-btn');
  assert.equal(await count(page, '#beam-piano.boundary'), 1);
  await wrong(page, 'p05', '#beam-choices button:nth-child(3)', '#beam-exhibits .on', /青色边框/);
  await click(page, '#beam-choices button:nth-child(2)');
  assert.equal(await count(page, '#beam-exhibits .on'), 2);
  assert.equal(await count(page, '#beam-drum.on,#beam-trumpet.on'), 2);
  assert.equal(await count(page, '#beam-piano.on'), 0);
  assert.equal(await stars(page), '1');
  await capture(page, 'p05', 'correct');
  await demo(page, { demo: false }, '#beam-choices button:first-child:enabled');
  await demo(page, { demo: true, round: 2, lit: [2, 3] }, '#beam-piano.on');
  assert.equal(await count(page, '#beam-trumpet.boundary,#beam-tambourine.boundary'), 2);
  assert.equal(await count(page, '#beam-piano.on,#beam-harp.on'), 2);
  assert.equal(await count(page, '#beam-exhibits .boundary.on'), 0);
  assert.equal(await stars(page), '0');
  await capture(page, 'p05', 'teacher-demo');
}

(async () => {
  const body = JSON.parse(await fs.readFile(bodyFile, 'utf8'));
  const browser = await chromium.launch({
    executablePath: process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--disable-background-networking']
  });
  try {
    for (const [id, test] of [['p02', horizontal], ['p04', vertical], ['p05', ranges]]) {
      const scene = body.scenes.find(item => item.outlineId === id);
      const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.origin !== origin) return route.abort();
        if (url.pathname === '/') {
          return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: scene.content.html });
        }
        const match = /^\/api\/classroom-media\/[^/]+\/media\/(pic-[a-f0-9]{64}\.png)$/.exec(url.pathname);
        return match ? route.fulfill({ status: 200, contentType: 'image/png', path: path.join(media, match[1]) }) : route.abort();
      });
      await page.goto(origin);
      await page.waitForFunction(() => [...document.images].every(img => img.complete && img.naturalWidth > 0));
      await capture(page, id, 'initial');
      await test(page);
      assert.deepEqual(errors, []);
      await page.close();
      console.log(id + ' initial, wrong without revealing the answer, correct, and teacher demo verified');
    }
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
