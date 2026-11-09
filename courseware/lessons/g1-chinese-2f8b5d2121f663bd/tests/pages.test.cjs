const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium } = require(path.join(process.cwd(), 'student-web/node_modules/playwright-core'));

const lesson = path.resolve(__dirname, '..');
const taskDirectory = process.env.MIRA_TASK_TMPDIR;
if (!taskDirectory) throw new Error('Run through tools/task_tmp.py so browser fixtures use a private task directory.');

function render(name) {
  const result = spawnSync('python3', ['-B', '-c', [
    'import sys', 'from pathlib import Path', 'from courseware.kit.page import page',
    'p=Path(sys.argv[1]); n=sys.argv[2]',
    "print(page(n,(p/(n+'.html')).read_text(),(p/(n+'.css')).read_text(),(p/(n+'.js')).read_text()))"
  ].join('\n'), path.join(lesson, 'pages'), name], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  // Synthetic pictures exercise behavior only. They are never lesson assets or release evidence.
  const image = 'data:image/svg+xml;base64,' + Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="#ddd"/></svg>').toString('base64');
  const html = result.stdout.replace(/__IMG:[^_]+__/g, image).replace('K.ready({', `K.ready({img:'${image}',`);
  const file = path.join(taskDirectory, `${name}.html`);
  fs.writeFileSync(file, html);
  return 'file://' + file;
}

for (const [width, height] of [[1280,720],[1000,563],[640,360]]) {
  test(`gallery corrects mistakes and fully resets at ${width}x${height}`, async () => {
    const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
    try {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.goto(render('gallery')); await page.locator('#start-btn').click();
      await page.locator('.gallery-photo[aria-label="风筝照片"]').click();
      assert.equal(await page.locator('#star-n').textContent(), '0');
      assert.equal(await page.locator('#gallery-chosen').isVisible(), false);
      assert.equal(await page.locator('.gallery-photo.selected').count(), 0);
      await page.locator('.gallery-photo[aria-label="五星红旗"]').click();
      assert.equal(await page.locator('#gallery-chosen').isVisible(), true);
      await page.waitForTimeout(950);
      await page.locator('.gallery-photo[aria-label="北京天安门"]').click();
      await page.locator('#finish').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#star-n').textContent(), '2');
      await page.locator('#btn-again').click();
      assert.equal(await page.locator('#star-n').textContent(), '0');
      assert.equal(await page.locator('#gallery-name').textContent(), '五星红旗');
      assert.equal(await page.locator('#gallery-chosen').isVisible(), false);
      assert.equal(await page.locator('.gallery-photo.selected').count(), 0);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });

  test(`river exploration separates teacher demonstration and child progress at ${width}x${height}`, async () => {
    const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
    try {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.goto(render('rivers')); await page.locator('#start-btn').click();
      await page.evaluate(() => window.K.onState({demo:true}));
      assert.equal(await page.locator('.river-window.opened').count(), 1);
      assert.equal(await page.locator('#star-n').textContent(), '0');
      await page.evaluate(() => window.K.onState({demo:false}));
      assert.equal(await page.locator('.river-window.opened').count(), 0);
      for (let phase=0;phase<2;phase++) {
        for (let number=1;number<=6;number++) await page.locator(`#river-window-${number}`).click();
        if (phase===0) await page.waitForTimeout(1100);
      }
      await page.locator('#finish').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#star-n').textContent(), '2');
      await page.locator('#btn-again').click();
      assert.equal(await page.locator('#star-n').textContent(), '0');
      assert.equal(await page.locator('#river-name').textContent(), '长江');
      assert.equal(await page.locator('.river-window.opened').count(), 0);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });
}
