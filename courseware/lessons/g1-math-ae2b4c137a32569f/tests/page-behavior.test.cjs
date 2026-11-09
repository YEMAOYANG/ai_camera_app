// Regression checks for evidence boundaries, first-error handling and replay.
// Run with a built draft/body and its media directory as the two arguments.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require(path.resolve(__dirname, '../../../../student-web/node_modules/playwright-core'));

async function run() {
  const loaded = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const body = loaded.body || loaded;
  const media = path.resolve(process.argv[3]);
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  async function open(key) {
    const scene = body.scenes.find(s => s.outlineId === key);
    const html = scene.content.html.replace(/\/api\/classroom-media\/[\w-]+\/media\/([\w.-]+)/g,
      (_, name) => pathToFileURL(path.join(media, name)).href);
    await page.setContent(html);
    await page.click('#start-btn');
  }
  async function finished() {
    await page.waitForSelector('#finish:not(.gone)');
    await page.click('#btn-again');
    assert.equal(await page.locator('#star-n').textContent(), '0');
    assert.equal(await page.locator('#finish:not(.gone)').count(), 0);
  }
  try {
    await open('p02');
    for (const [kind, slot] of [['building', 0], ['tree', 1], ['slide', 2]]) {
      await page.click('#stamp-' + kind);
      await page.click('#map-slot-' + slot);
    }
    await finished();
    assert.equal(await page.locator('.map-slot.placed').count(), 0);

    await open('p04');
    await page.click('#count-choice-5');
    assert.equal(await page.locator('#count-number').textContent(), '0');
    await page.click('#count-item-1');
    await page.click('#count-item-1');
    assert.equal(await page.locator('#count-number').textContent(), '1', 'the same tree cannot count twice');
    await page.click('#count-item-2'); await page.click('#count-item-3');
    await page.click('#count-choice-3');
    await page.waitForTimeout(750);
    for (const n of [4, 5]) {
      for (let i = 1; i <= n; i++) await page.click('#count-item-' + i);
      await page.click('#count-choice-' + n);
      await page.waitForTimeout(750);
    }
    await finished();
    assert.equal(await page.locator('.tree-item.counted').count(), 0);

    await open('p07');
    await page.locator('#shape-stamp-circle').dispatchEvent('pointerdown', { button: 0, clientX: 100, clientY: 450 });
    await page.locator('body').dispatchEvent('pointerup', { button: 0, clientX: 100, clientY: 450 });
    assert.equal(await page.locator('#shape-target [fill="none"]').count(), 1,
      'a first wrong stamp leaves the target unfilled');
    assert.equal(await page.locator('#shape-stamp-triangle.teach-hl').count(), 0,
      'a first wrong stamp does not reveal the answer');
    for (const k of ['triangle', 'rectangle', 'square', 'circle']) {
      const b = await page.locator('#shape-stamp-' + k).boundingBox();
      await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
      await page.waitForTimeout(750);
    }
    await finished();

    await open('p10');
    for (let i = 0; i < 3; i++) {
      const b = await page.locator('#score-token-' + i).boundingBox();
      await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
    }
    assert.equal(await page.locator('#score-record .score-pair i').count(), 4,
      'one green and two orange counters record four points');
    await page.click('#score-choice-6');
    assert.equal(await page.locator('#score-choice-4.teach-hl').count(), 0);
    await page.click('#score-choice-4'); await page.waitForTimeout(750);
    for (const [count, total] of [[3, 6], [5, 7]]) {
      for (let i = 0; i < count; i++) {
        const b = await page.locator('#score-token-' + i).boundingBox();
        await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
      }
      assert.equal(await page.locator('#score-record .score-pair i').count(), total);
      await page.click('#score-choice-' + total); await page.waitForTimeout(750);
    }
    await finished();
    assert.equal(await page.locator('#score-record .score-pair').count(), 0);

    await open('p12');
    const origin = await page.locator('.route-person').boundingBox();
    await page.click('#route-right');
    assert.deepEqual(await page.locator('.route-person').boundingBox(), origin,
      'an out-of-order direction leaves the position unchanged');
    await page.click('#route-up');
    assert.equal(await page.locator('#star-n').textContent(), '1', 'each correct step shows progress');
    await page.click('#route-reset');
    assert.equal(await page.locator('#star-n').textContent(), '0', 'retry rolls back current-route stars');
    for (const plan of [['up', 'up', 'right', 'right'], ['right', 'up', 'up', 'up'], ['up', 'right', 'right', 'right']]) {
      for (const direction of plan) await page.click('#route-' + direction);
      await page.waitForTimeout(750);
    }
    await finished();
    assert.equal(await page.locator('.route-segment i.done').count(), 0);
    assert.deepEqual(errors, []);
    console.log('PASS: 5 pages; first-error boundaries, unique counting, weighted points, ordered routes and replay');
  } finally {
    await browser.close();
  }
}
run().catch(e => { console.error(e); process.exitCode = 1; });
