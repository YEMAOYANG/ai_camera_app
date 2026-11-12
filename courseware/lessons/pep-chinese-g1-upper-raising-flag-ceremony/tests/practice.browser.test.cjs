// Set MIRA_PRACTICE_DIR to a directory with local frame-crane.html and stroke-route.html.
const assert = require('node:assert/strict');
const path = require('node:path');
const {test} = require('node:test');
const {pathToFileURL} = require('node:url');

const pages = process.env.MIRA_PRACTICE_DIR;
const studentWeb = path.resolve(__dirname, '../../../../student-web');
const chrome = process.env.MIRA_CHROME_BIN ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

async function play(name, action) {
  const {chromium} = require(path.join(process.env.MIRA_PLAYWRIGHT_DIR || studentWeb, 'node_modules/playwright-core'));
  const browser = await chromium.launch({executablePath: chrome, headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 640, height: 360}, hasTouch: true});
    await page.goto(pathToFileURL(path.join(pages, name + '.html')).href);
    await page.evaluate(() => window.postMessage({
      type: 'SET_WIDGET_STATE', state: {demo: false, level: 1}
    }, '*'));
    await action(page);
    assert.deepEqual(await page.evaluate(() => K.errs), []);
  } finally {
    await browser.close();
  }
}

test('a child can lower the crane with a 44px touch target and with Space',
     {skip: !pages, timeout: 15000}, async () => {
  await play('frame-crane', async (page) => {
    const button = page.locator('#crane-drop');
    await button.waitFor({state: 'visible'});
    const box = await button.boundingBox();
    assert.ok(box.width >= 44 && box.height >= 44);
    await button.tap();
    await page.waitForFunction(() => K.game.current.levelMisses === 1);
    await page.waitForFunction(() => Math.abs(K.game.current.data.world.x - 688) < 14);
    await page.keyboard.press('Space');
    await page.waitForFunction(() => K.game.current.data.world.landed.has(1));
    assert.equal(await page.locator('#crane-score').textContent(), '得分 100');
  });
});

test('arrows and held touchscreen controls advance the same authored stroke route',
     {skip: !pages, timeout: 15000}, async () => {
  await play('stroke-route', async (page) => {
    const right = page.locator('[data-trace-direction="right"]');
    await right.waitFor({state: 'visible'});
    const box = await right.boundingBox();
    assert.ok(box.width >= 44 && box.height >= 44);
    await page.keyboard.down('ArrowUp');
    await page.waitForFunction(() => K.game.current.levelMisses >= 1);
    await page.keyboard.up('ArrowUp');
    assert.equal(await page.evaluate(() => K.game.current.data.world.s), 0);
    await page.keyboard.down('ArrowDown');
    await page.waitForFunction(() => K.game.current.data.world.stroke === 1);
    await page.keyboard.up('ArrowDown');
    const session = await page.context().newCDPSession(page);
    try {
      await session.send('Input.dispatchTouchEvent', {
        type: 'touchStart', touchPoints: [{x: box.x + box.width / 2, y: box.y + box.height / 2}]
      });
      await page.waitForFunction(() => K.game.current.data.world.s > 120);
      await session.send('Input.dispatchTouchEvent', {type: 'touchEnd', touchPoints: []});
    } finally {
      await session.detach();
    }
    assert.equal(await page.evaluate(() => K.game.current.data.world.stroke), 1);
  });
});
