const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { createRequire } = require('node:module');

const root = path.resolve(__dirname, '../../../..');
const load = createRequire(path.join(root, 'student-web/package.json'));
const { chromium } = load('playwright-core');
const work = path.join(root, 'output/courseware-lessons/g1-math-1c9a598fd65c828e');
const temporary = process.env.MIRA_TASK_TMPDIR;

test('three sizes preserve demo isolation, wrong/retry, completion and replay', async () => {
  assert.ok(temporary, 'Run inside the repository task_tmp workspace');
  const body = JSON.parse(fs.readFileSync(process.env.MIRA_CAMPUS_BODY || path.join(work, 'body.json'), 'utf8'));
  const browser = await chromium.launch({
    executablePath: process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--allow-file-access-from-files']
  });
  try {
    for (const [width, height] of [[1280, 720], [1000, 563], [640, 360]]) {
      for (const scene of body.scenes.filter(scene => scene.type === 'interactive')) {
        const key = scene.content.widgetType;
        const filename = path.join(temporary, `${key}-${width}.html`);
        const html = scene.content.html.replace(/\/api\/classroom-media\/[A-Za-z0-9_-]+\/media\/([A-Za-z0-9_.-]+)/g,
          (_, name) => pathToFileURL(path.join(work, 'media', name)).href);
        fs.writeFileSync(filename, html);
        const page = await browser.newPage({ viewport: { width, height } });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(pathToFileURL(filename).href);
        await page.locator('#start-btn').click();
        await page.waitForFunction(() => [...document.images].every(img => img.complete && img.naturalWidth > 0));
        const shot = async state => page.screenshot({ path: path.join(temporary, `${key}-${width}-${state}.png`) });
        await shot('initial');
        if (key === 'campus-count-once' || key === 'campus-mark-count') {
          const bird = key === 'campus-count-once';
          const prefix = bird ? 'bird-item-' : 'butterfly-item-';
          const counter = bird ? '#bird-count' : '#mark-count';
          const marked = bird ? '.demo-birds .marked' : '.demo-marks .marked';
          await page.evaluate(state => window.postMessage({ type: 'SET_WIDGET_STATE', state }, '*'),
            bird ? { demoStep: 3 } : { demoMark: 3 });
          await page.waitForFunction(selector => document.querySelectorAll(selector).length === 3, marked);
          assert.equal(await page.locator(counter).textContent(), '0');
          assert.equal(await page.locator('#star-n').textContent(), '0');
          await shot('teacher');
          await page.locator('#' + prefix + '0').click();
          await page.waitForTimeout(500);
          await page.locator('#' + prefix + '0').click();
          assert.equal(await page.locator(counter).textContent(), '1');
          await shot('wrong');
          for (let index = 1; index < (bird ? 5 : 10); index++) await page.locator('#' + prefix + index).click();
          await page.waitForTimeout(850); await shot('correct');
          await page.locator('#finish:not(.gone)').waitFor();
          await page.locator('#btn-again').click();
          assert.equal(await page.locator(counter).textContent(), '0');
          assert.equal(await page.locator(marked).count(), 0);
          if (bird) {
            await page.evaluate(() => document.querySelector('#bird-item-0 img').dispatchEvent(new Event('error')));
            await page.locator('#bird-item-0').click();
            assert.equal(await page.locator(counter).textContent(), '0', 'image retry must not count');
            await page.waitForFunction(() => !document.querySelector('#bird-item-0').classList.contains('load-error'));
            await page.locator('#bird-item-0').click();
            assert.equal(await page.locator(counter).textContent(), '1');
          }
        } else {
          await page.evaluate(() => window.postMessage({ type: 'SET_WIDGET_STATE', state: { shapeDemo: 'round' } }, '*'));
          await page.locator('#shape-demo-sample').waitFor({ state: 'visible' });
          assert.equal(await page.locator('#star-n').textContent(), '0');
          await shot('teacher');
          await page.evaluate(() => window.postMessage({ type: 'SET_WIDGET_STATE', state: { shapeDemo: 'reset' } }, '*'));
          await page.locator('#shape-ball').click(); await page.locator('#shape-long').click();
          assert.equal(await page.locator('#star-n').textContent(), '0');
          assert.equal(await page.locator('#say').textContent(), '再看看外边的样子。');
          await shot('wrong');
          await page.locator('#shape-ball').click(); await page.locator('#shape-round').click();
          await page.locator('#shape-book').click(); await page.locator('#shape-long').click();
          await shot('correct');
          await page.locator('#finish:not(.gone)').waitFor();
          await page.locator('#btn-again').click();
          assert.equal(await page.locator('#shape-tray .shape-item').count(), 2);
          assert.equal(await page.locator('#star-n').textContent(), '0');
        }
        assert.deepEqual(errors, [], `${key} at ${width}: browser errors`);
        console.log(`verified ${key} ${width}x${height}; screenshots in ${temporary}`);
        await page.close();
      }
    }
  } finally { await browser.close(); }
});
