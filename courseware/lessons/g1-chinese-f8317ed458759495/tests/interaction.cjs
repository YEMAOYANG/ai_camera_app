// Run with a compiled lesson body and local content-addressed media; no runtime or provider is used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test } = require('node:test');
const { chromium } = require('../../../../student-web/node_modules/playwright-core');

const [bodyFile, mediaDir] = process.argv.slice(2);
const work = process.env.MIRA_TASK_TMPDIR;
const capture = process.env.MIRA_CAPTURE_COURSEWARE_STATES === '1';
if (!bodyFile || !mediaDir || !work) throw new Error('Provide body.json, media directory and MIRA_TASK_TMPDIR.');
const body = JSON.parse(fs.readFileSync(bodyFile, 'utf8'));
const chrome = process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

async function show(page, sceneKey) {
  const scene = body.scenes.find(item => item.outlineId === sceneKey && item.type === 'interactive');
  assert.ok(scene, 'Missing interactive scene ' + sceneKey);
  const html = scene.content.html.replace(/\/api\/classroom-media\/[^/]+\/media\/([A-Za-z0-9_.-]+)/g,
    (_, file) => pathToFileURL(path.resolve(mediaDir, file)).href);
  const file = path.resolve(work, 'test-' + sceneKey + '.html');
  fs.writeFileSync(file, html);
  await page.goto(pathToFileURL(file).href);
}
async function start(page, key) {
  await show(page, key);
  await snapshot(page, key, 'start');
  await page.locator('#ready button').click();
  await page.locator('#ready.gone').waitFor({ state: 'hidden' });
  await snapshot(page, key, 'initial');
}
async function snapshot(page, key, state) {
  if (capture) await page.screenshot({ path: path.resolve(work, key + '-' + state + '.png') });
}
async function state(page, value) {
  await page.evaluate(state => window.postMessage({ type: 'SET_WIDGET_STATE', state }, '*'), value);
}
async function assertNoScore(page) {
  assert.equal(await page.locator('#star-n').textContent(), '0');
  assert.equal(await page.locator('#dots .done').count(), 0);
}
async function drag(page, from, to) {
  const a = await page.locator(from).boundingBox();
  const b = await page.locator(to).boundingBox();
  assert.ok(a && b);
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 10 });
  await page.mouse.up();
}
test('weather card distinguishes wrong, correct, and unscored teacher moves', async () => {
  await withPage(async page => {
    await start(page, 'p04');
    await page.locator('#weather-token').click();
    await page.locator('#weather-a').click();
    assert.equal(await page.locator('#weather-a').getAttribute('data-miss'), 'true');
    assert.equal(await page.locator('.weather-stamp:not(:empty)').count(), 0);
    assert.equal(await page.locator('#weather-b.teach-hl').count(), 0);
    await assertNoScore(page);
    await snapshot(page, 'p04', 'wrong');
    await drag(page, '#weather-token', '#weather-b');
    assert.equal(await page.locator('#weather-b .weather-stamp').textContent(), '风');
    await snapshot(page, 'p04', 'right');
    await show(page, 'p04');
    await state(page, { weatherDemo: 'prepare' });
    await page.waitForFunction(() => document.querySelector('#weather-token').textContent === '雨');
    await state(page, { weatherDemo: true });
    await page.locator('#weather-a[data-ok=true]').waitFor();
    assert.equal(await page.locator('#weather-a .weather-stamp').textContent(), '雨');
    await assertNoScore(page);
    await snapshot(page, 'p04', 'teacher');
  });
});
test('connecting two pictures draws a line only after a related pair is chosen', async () => {
  await withPage(async page => {
    await start(page, 'p06');
    await page.locator('#pair-left').click();
    await page.locator('#pair-option-tree').click();
    assert.equal(await page.locator('#pair-connection').getAttribute('d'), '');
    assert.equal(await page.locator('#pair-option-other.teach-hl').count(), 0);
    await snapshot(page, 'p06', 'wrong');
    await page.locator('#pair-option-other').click();
    assert.notEqual(await page.locator('#pair-connection').getAttribute('d'), '');
    await snapshot(page, 'p06', 'right');
    await show(page, 'p06');
    await state(page, { pairDemo: 'prepare' });
    await page.waitForFunction(() => document.querySelector('#pair-left img').alt === '花');
    await state(page, { pairDemo: true });
    await page.waitForFunction(() => Boolean(document.querySelector('#pair-connection').getAttribute('d')));
    await assertNoScore(page);
    await snapshot(page, 'p06', 'teacher');
  });
});
test('spring lens keeps the wrong choice separate from a successful crop and a demo', async () => {
  await withPage(async page => {
    await start(page, 'p10');
    await page.locator('#spring-mountain').click();
    assert.equal(await page.locator('#spring-mountain').getAttribute('data-state'), 'no');
    assert.equal(await page.locator('#spring-close').getAttribute('data-show'), null);
    await snapshot(page, 'p10', 'wrong');
    await page.locator('#spring-water').click();
    assert.equal(await page.locator('#spring-water').getAttribute('data-state'), 'ok');
    assert.equal(await page.locator('#spring-close').getAttribute('data-show'), 'true');
    await snapshot(page, 'p10', 'right');
    await show(page, 'p10');
    await state(page, { springDemo: true });
    await page.locator('#spring-mountain[data-state=ok]').waitFor();
    assert.equal(await page.locator('#spring-word').textContent(), '山清');
    await assertNoScore(page);
    await snapshot(page, 'p10', 'teacher');
  });
});
for (const [key, demo, expected] of [['p14', 'rain', '雨'], ['p16', 'water', '水']]) {
  test(key + ' shows ink on a real trace and keeps the teacher demo unscored', async () => {
    await withPage(async page => {
      await start(page, key);
      const grid = page.locator('#ink-grid');
      const r = await grid.boundingBox();
      await page.mouse.click(r.x + 18, r.y + 18);
      assert.equal(await page.locator('#say').getAttribute('class'), 'no');
      assert.equal(await page.locator('.ink-overlay[visibility=visible]').count(), 0);
      await snapshot(page, key, 'wrong');
      const points = await page.locator('.ink-guide.current').evaluate(guide => {
        const size = guide.getTotalLength();
        return Array.from({ length: 18 }, (_, i) => {
          const p = guide.getPointAtLength(size * i / 17);
          return { x: p.x, y: p.y };
        });
      });
      const move = ({ x, y }) => page.mouse.move(r.x + x * r.width / 100, r.y + y * r.height / 100);
      await move(points[0]);
      await page.mouse.down();
      for (const point of points.slice(1)) await move(point);
      await page.mouse.up();
      assert.equal(await page.locator('.ink-overlay[visibility=visible]').count(), 1);
      assert.equal(await page.locator('#say').getAttribute('class'), 'ok');
      await assertNoScore(page);
      await snapshot(page, key, 'right');
      await show(page, key);
      await state(page, { inkDemo: demo });
      await page.waitForFunction(expected => document.querySelector('#ink-word').textContent === expected &&
        document.querySelector('.ink-overlay[visibility=visible]'), expected);
      assert.equal(await page.locator('#ink-show').isDisabled(), true);
      await assertNoScore(page);
      await snapshot(page, key, 'teacher');
    });
  });
}
async function withPage(run) {
  const browser = await chromium.launch({ executablePath: chrome, headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await run(page);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
}
