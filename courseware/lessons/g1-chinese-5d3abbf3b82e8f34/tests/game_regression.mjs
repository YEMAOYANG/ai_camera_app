// Run with the repository's local Playwright dependency. All HTML and failure
// screenshots go to the caller's MIRA_TASK_TMPDIR; no service is contacted.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [bodyPath, mediaDir] = process.argv.slice(2);
assert(bodyPath && mediaDir && process.env.MIRA_TASK_TMPDIR,
  'usage: MIRA_TASK_TMPDIR=<private task dir> node game_regression.mjs body.json media/');
const require = createRequire(path.resolve('student-web/package.json'));
const { chromium } = require('playwright-core');
const body = JSON.parse(fs.readFileSync(bodyPath, 'utf8'));
const browser = await chromium.launch({
  executablePath: process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
});
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));

async function open(key) {
  const scene = body.scenes.find(item => item.outlineId === key);
  assert(scene, key + ' exists');
  const html = scene.content.html.replace(/\/api\/classroom-media\/[^/\s"'<>]+\/media\/[^\s"'<>+]+/g,
    url => pathToFileURL(path.resolve(mediaDir, url.split('/media/')[1])).href);
  const file = path.join(process.env.MIRA_TASK_TMPDIR, 'regression-' + key + '.html');
  fs.writeFileSync(file, html);
  await page.goto(pathToFileURL(file).href);
  assert.equal(await page.locator('#start-btn').count(), 1);
  await page.locator('#start-btn').click();
}

async function replay() {
  assert.equal(await page.locator('#finish').isVisible(), true);
  await page.locator('#btn-again').click();
  assert.match(await page.locator('#finish').getAttribute('class'), /gone/);
  assert.equal(await page.locator('#star-n').innerText(), '0');
}

try {
  await open('p02');
  const front = await page.locator('#book-object').getAttribute('src');
  await page.locator('#confirm-face').click();
  assert.equal(await page.locator('#finish:not(.gone)').count(), 0);
  assert.equal(await page.locator('#star-n').innerText(), '0');
  assert.doesNotMatch(await page.locator('#say').innerText(), /太阳|封面|背面/);
  for (let step = 0; step < 3; step++) {
    await page.locator('#change-btn').click();
    if (step === 0) assert.notEqual(await page.locator('#book-object').getAttribute('src'), front);
    await page.locator('#confirm-face').click();
    await page.waitForFunction(() => !document.querySelector('#confirm-face').disabled || document.querySelector('#finish:not(.gone)'));
  }
  await replay();
  assert.equal(await page.locator('#book-object').getAttribute('src'), front);
  await page.locator('#book-object').evaluate(el => { el.src = './missing-regression-image.png'; });
  await page.locator('#page-media-failure').waitFor({ state: 'visible' });
  assert.equal(await page.locator('#page-media-failure button').count(), 1);
  await page.locator('#page-media-failure button').click();
  await page.locator('#start-btn').waitFor({ state: 'visible' });
  assert.equal(await page.locator('#page-media-failure').count(), 0);
  console.log('p02: first miss, object flip, finish, replay and image-failure recovery passed');

  await open('p09');
  await page.locator('#order-leave').dragTo(page.locator('#slot-first'));
  assert.doesNotMatch(await page.locator('#say').innerText(), /备好后|准备书包.*出门/);
  await page.locator('#order-prepare').dragTo(page.locator('#slot-second'));
  await page.locator('#check-order').click();
  assert.equal(await page.locator('#finish:not(.gone)').count(), 0);
  assert.equal(await page.locator('#star-n').innerText(), '0');
  for (let round = 0; round < 2; round++) {
    if (round === 0) {
      await page.locator('#order-prepare').dragTo(page.locator('#slot-first'));
      await page.locator('#order-leave').dragTo(page.locator('#slot-second'));
    } else {
      await page.locator('#order-prepare').click();
      await page.locator('#slot-first').click({ position: { x: 20, y: 20 } });
      await page.locator('#order-leave').click();
      await page.locator('#slot-second').click({ position: { x: 20, y: 20 } });
    }
    await page.locator('#check-order').click();
    assert.equal(await page.locator('#finish').isVisible(), true);
    if (round === 0) {
      await replay();
      assert.equal(await page.locator('.order-slot .order-card').count(), 0);
      assert.equal(await page.locator('#order-bank .order-card').count(), 2);
    }
  }
  console.log('p09: wrong order, drag and tap routes, two finishes and reset passed');

  await open('p16');
  const dog = page.locator('.helper-card[data-key=dog]');
  const grandma = page.locator('.helper-card[data-key=grandma]');
  const girl = page.locator('.helper-card[data-key=girl]');
  const hint = page.locator('#say');
  await dog.click();
  assert.equal(await hint.innerText(), '想想前一位帮手请了谁。');
  assert.equal(await page.locator('#star-n').innerText(), '0');
  await dog.click();
  assert.match(await hint.innerText(), /老婆婆、小姑娘、最后|老婆婆，再接小姑娘，最后接小狗/);
  await grandma.dragTo(page.locator('#helper-tail'));
  assert.equal(await page.locator('#star-n').innerText(), '1');
  await dog.click();
  assert.equal(await hint.innerText(), '想想前一位帮手请了谁。');
  await girl.click();
  await dog.click();
  await replay();
  assert.equal(await page.locator('#helper-bank .helper-card').count(), 3);
  console.log('p16: first mistake counted once, drag order and hints reset, finish and replay passed');

  await open('p18');
  await page.locator('#ending-out').click();
  assert.equal(await page.locator('#finish:not(.gone)').count(), 0);
  await page.locator('#new-cat').click();
  assert.equal(await page.locator('#story-tail img').getAttribute('alt'), '续编加入的小猫');
  await page.locator('#story-tail').click();
  assert.equal(await page.locator('#star-n').innerText(), '1');
  await page.locator('#story-tail').click();
  assert.equal(await page.locator('#star-n').innerText(), '1', 'repeated pull cannot farm stars');
  await page.locator('#ending-out').click();
  assert.match(await page.locator('#story-root').getAttribute('style'), /translateY/);
  await page.locator('#story-done').click();
  await replay();
  assert.equal(await page.locator('#story-tail img').count(), 0);
  assert.equal(await page.locator('#story-root').evaluate(el => el.style.transform), '');
  await page.locator('#new-mouse').dragTo(page.locator('#story-tail'));
  await page.locator('#story-tail').dragTo(page.locator('#story-team'));
  await page.locator('#ending-more').click();
  await page.locator('#story-done').click();
  assert.equal(await page.locator('#finish').isVisible(), true);
  assert.equal(errors.length, 0, errors.join('\n'));
  console.log('p18: prerequisite, real movement, no repeat reward, both endings and reset passed');
} catch (error) {
  await page.screenshot({ path: path.join(process.env.MIRA_TASK_TMPDIR, 'game-regression-failed.png') });
  throw error;
} finally {
  await browser.close();
}
