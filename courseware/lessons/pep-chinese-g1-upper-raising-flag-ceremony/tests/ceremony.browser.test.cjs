// Set MIRA_CEREMONY_PAGE to the local HTML emitted by autoplay.page_html.
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const {fileURLToPath, pathToFileURL} = require('node:url');

const pageFile = process.env.MIRA_CEREMONY_PAGE;
const studentWeb = path.resolve(__dirname, '../../../../student-web');
const chrome = process.env.MIRA_CHROME_BIN ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const activity = '#ceremony-activity';
const audio = '#ceremony-anthem';
const flag = '#ceremony-flag';
const start = '#ceremony-start';

async function scene(viewport, fn) {
  const {chromium} = require(path.join(process.env.MIRA_PLAYWRIGHT_DIR || studentWeb, 'node_modules/playwright-core'));
  const browser = await chromium.launch({executablePath: chrome, headless: true});
  try {
    const page = await browser.newPage({viewport, hasTouch: true});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(pageFile).href);
    await page.waitForFunction(selector => document.querySelector(selector).naturalWidth > 0, flag);
    await fn(page);
    assert.deepEqual(errors, []);
    assert.deepEqual(await page.evaluate(() => window.K.errs), []);
  } finally {
    await browser.close();
  }
}

async function teacherReady(page) {
  await page.evaluate(() => window.postMessage({
    type: 'SET_WIDGET_STATE', state: {ceremonyReady: true}
  }, '*'));
  await page.waitForFunction(selector => document.querySelector(selector).dataset.phase === 'ready', activity);
}

function flagLift(page) {
  return page.locator(flag).evaluate(element =>
    Number.parseFloat(getComputedStyle(element).getPropertyValue('--flag-lift')));
}

async function touchRope(page) {
  const box = await page.locator('#ceremony-rope').boundingBox();
  assert.ok(box.width >= 44 && box.height >= 44);
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  const session = await page.context().newCDPSession(page);
  await session.send('Input.dispatchTouchEvent', {type: 'touchStart', touchPoints: [{x, y}]});
  for (const dy of [12, 24, 38, 52]) {
    await session.send('Input.dispatchTouchEvent', {type: 'touchMove', touchPoints: [{x, y: y + dy}]});
  }
  await session.send('Input.dispatchTouchEvent', {type: 'touchEnd', touchPoints: []});
  await session.detach();
}

test('a real touch pull starts the exact recording and lifts the flag with the full audio clock',
     {skip: !pageFile, timeout: 120000}, async () => {
  await scene({width: 640, height: 360}, async (page) => {
    const expected = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'lesson.json'), 'utf8'))
      .audio['ceremony-anthem'].sha256;
    const source = await page.locator(audio).evaluate(element => element.src);
    const bytes = fs.readFileSync(fileURLToPath(source));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), expected);
    await page.locator(audio).evaluate(element => {
      element.testMedia = {playing: 0, ended: 0, altered: 0};
      for (const event of ['playing', 'ended']) {
        element.addEventListener(event, () => ++element.testMedia[event]);
      }
      for (const event of ['seeking', 'ratechange']) {
        element.addEventListener(event, () => ++element.testMedia.altered);
      }
    });
    assert.equal(await page.locator(start).isDisabled(), true);
    await page.keyboard.press('Space');
    assert.equal(await page.locator(audio).evaluate(element => element.currentTime), 0);
    assert.equal(await flagLift(page), 324);
    await teacherReady(page);
    assert.ok((await page.locator(start).boundingBox()).height >= 44);
    await touchRope(page);
    await page.waitForFunction(selector => document.querySelector(selector).currentTime >= 0.8, audio);
    const clock = await page.locator(audio).evaluate(element => ({
      progress: element.currentTime / element.duration,
      duration: element.duration,
      muted: element.muted,
      rate: element.playbackRate
    }));
    assert.ok(Math.abs(clock.duration - 49.454896) < 0.05);
    assert.equal(clock.muted, false);
    assert.equal(clock.rate, 1);
    const lift = await flagLift(page);
    assert.ok(lift < 324 && lift > 0);
    assert.ok(Math.abs(lift - 324 * (1 - clock.progress)) < 3);
    assert.equal(await page.locator(start).isVisible(), false);
    await page.keyboard.press('Space');
    await page.waitForFunction(selector => document.querySelector(selector).dataset.phase === 'done',
      activity, {timeout: 100000});
    assert.equal(await flagLift(page), 0);
    assert.equal(await page.locator('[data-media-completion]').isVisible(), true);
    assert.equal(await page.locator('#gcard,#finish,#stars,.cf').count(), 0);
    assert.deepEqual(await page.locator(audio).evaluate(element => element.testMedia),
      {playing: 1, ended: 1, altered: 0});
  });
});

test('a failed recording stays at the bottom and a hidden iframe stops active playback',
     {skip: !pageFile, timeout: 20000}, async () => {
  await scene({width: 1000, height: 563}, async (page) => {
    const source = await page.locator(audio).evaluate(element => {
      const original = element.src;
      element.src = './unavailable-test-recording.wav';
      return original;
    });
    await page.evaluate(() => window.postMessage({
      type: 'SET_WIDGET_STATE', state: {activityReady: true}
    }, '*'));
    await page.waitForFunction(selector => document.querySelector(selector).dataset.phase === 'error', activity);
    assert.equal(await flagLift(page), 324);
    assert.equal(await page.locator('[data-media-completion]').isVisible(), false);
    await page.locator(audio).evaluate((element, src) => { element.src = src; }, source);
    await page.locator(start).click();
    await page.waitForFunction(selector => document.querySelector(selector).currentTime > 0.3, audio);
    await page.evaluate(() => window.postMessage({type: 'mira:checkpoint-visibility', active: false}, '*'));
    await page.waitForFunction(selector => document.querySelector(selector).dataset.phase === 'interrupted', activity);
    assert.equal(await page.locator(audio).evaluate(element => element.paused), true);
    assert.equal(await page.locator(start).isDisabled(), true);
    assert.equal(await page.locator('[data-media-completion]').isVisible(), false);
  });
});
