const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '../../../..');
const work = path.join(root, 'output/courseware-lessons/g1-science-d45fe43e63abbfe6');
const requirePlayer = createRequire(path.join(root, 'student-web/package.json'));
const { chromium } = requirePlayer('playwright-core');
const body = JSON.parse(fs.readFileSync(path.join(work, 'body.json'), 'utf8'));
const tmp = process.env.MIRA_TASK_TMPDIR;
if (!tmp) throw new Error('Run through tools/task_tmp.py so browser fixtures stay in this task workspace.');
let browser;
test.before(async () => { browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true }); });
test.after(async () => { if (browser) await browser.close(); });
async function scene(key) {
  const source = body.scenes.find(s => s.outlineId === key).content.html;
  const local = source.replace(/\/api\/classroom-media\/[^/\s"'<>]+\/media\/([^\s"'<>+]+)/g, (_, name) => pathToFileURL(path.join(work, 'media', decodeURIComponent(name))).href);
  const filename = path.join(tmp, key + '.html'); fs.writeFileSync(filename, local);
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.addInitScript(() => {
    window.__clipEvents = [];
    window.Audio = class {
      constructor(src) { this.src = src; this.listeners = {}; window.__clipEvents.push(['new', src]); }
      addEventListener(name, fn) { this.listeners[name] = fn; }
      play() { window.__clipEvents.push(['play', this.src]); return Promise.resolve(); }
      pause() { window.__clipEvents.push(['pause', this.src]); }
    };
  });
  await page.goto(pathToFileURL(filename).href);
  await page.locator('#ready button').click();
  await page.waitForFunction(() => Array.from(document.querySelectorAll('#play img')).every(i => i.complete && i.naturalWidth > 0));
  return page;
}
async function drag(page, from, to) {
  const a = await page.locator(from).boundingBox(), b = await page.locator(to).boundingBox();
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 10 });
  await page.mouse.up();
}
test('method matching preserves the first mistake, changes the investigation scene, and resets teacher demo', async () => {
  const page = await scene('p02');
  await page.locator('#method-choice-1').click();
  assert.equal(await page.evaluate(() => K.stars), 0);
  assert.equal(await page.locator('#say').textContent(), '先想想，你需要得到什么信息。');
  assert.equal(await page.locator('#method-next').isEnabled(), false);
  await drag(page, '#method-choice-0', '#method-goal');
  assert.equal(await page.evaluate(() => K.stars), 1);
  assert.equal(await page.locator('#method-found img').count(), 1);
  await page.locator('#method-next').click();
  assert.equal(await page.locator('#play').getAttribute('data-level'), '1');
  await page.evaluate(() => window.postMessage({ type: 'SET_WIDGET_STATE', state: { mode: 'demo', level: 3 } }, '*'));
  await page.waitForFunction(() => document.querySelector('#play').dataset.mode === 'demo');
  await page.locator('#method-listen').click();
  assert.equal(await page.locator('#method-record img').count(), 0);
  await page.evaluate(() => window.postMessage({ type: 'SET_WIDGET_STATE', state: { mode: 'play', level: 0 } }, '*'));
  await page.waitForFunction(() => document.querySelector('#play').dataset.level === '0');
  assert.equal(await page.evaluate(() => K.stars), 0);
  await page.locator('#method-listen').click();
  await page.locator('#method-listen').click();
  const clips = await page.evaluate(() => window.__clipEvents);
  assert.ok(clips.filter(e => e[0] === 'play').length >= 3, 'actual prerecorded prompt references must be available');
  assert.ok(clips.filter(e => e[0] === 'pause').length >= 2, 'replay stops the previous clip');
  assert.ok(clips.filter(e => e[0] === 'new').every(e => /\/media\/tts-.*-[a-f0-9]{64}\.wav$/.test(e[1])));
  await page.close();
});
test('process ordering rejects a premature test, moves all three actual action pictures, and play-again clears them', async () => {
  const page = await scene('p04');
  await page.locator('#process-test').click();
  assert.equal(await page.evaluate(() => K.stars), 0);
  assert.equal(await page.locator('.slot-image img').count(), 0);
  await page.locator('#process-plan').click();
  assert.equal(await page.locator('#process-slot-0 img').count(), 1);
  await page.locator('#process-make').click();
  assert.equal(await page.locator('#process-slot-1 img').count(), 1);
  await page.locator('#process-test').click();
  await page.locator('#finish:not(.gone)').waitFor();
  assert.equal(await page.locator('.slot-image img').count(), 3);
  await page.locator('#btn-again').click();
  assert.equal(await page.locator('.slot-image img').count(), 0);
  assert.equal(await page.evaluate(() => K.stars), 0);
  assert.equal(await page.locator('#play').getAttribute('data-step'), '0');
  assert.equal(await page.locator('.picture-choice.placed').count(), 0);
  await page.close();
});
test('safety choices update the work area, do not grant a star for an unsafe action, and finish/reset both rounds', async () => {
  const page = await scene('p06');
  const initial = await page.locator('#safety-scene').getAttribute('src');
  await page.locator('#safety-option-0').click();
  assert.equal(await page.evaluate(() => K.stars), 0);
  assert.equal(await page.locator('#say').textContent(), '先看清手和嘴正在做什么。');
  await drag(page, '#safety-option-1', '#safety-zone');
  assert.notEqual(await page.locator('#safety-scene').getAttribute('src'), initial);
  await page.locator('#safety-next').click();
  await page.locator('#safety-option-1').click();
  assert.equal(await page.evaluate(() => K.stars), 1);
  await page.locator('#safety-option-0').click();
  await page.locator('#safety-next').click();
  await page.locator('#finish:not(.gone)').waitFor();
  await page.locator('#btn-again').click();
  assert.equal(await page.evaluate(() => K.stars), 0);
  assert.equal(await page.locator('#play').getAttribute('data-level'), '0');
  assert.equal(await page.locator('#safety-stamps img').count(), 0);
  await page.close();
});

