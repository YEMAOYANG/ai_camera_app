const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { createRequire } = require('node:module');

const root = path.resolve(__dirname, '../../../..');
const { chromium } = createRequire(path.join(root, 'student-web/package.json'))('playwright-core');
const build = path.resolve(process.env.COUNT_COMPARE_BUILD ||
  path.join(root, 'output/courseware-lessons/jsedu-math-g1-upper-count-compare/work-v1'));
const temporary = process.env.MIRA_TASK_TMPDIR;
const sceneKeys = ['p02', 'p03', 'p04', 'p07', 'p09'];
let browser;
let body;

before(async () => {
  assert.ok(temporary, 'use tools/task_tmp.py to keep screenshots private');
  const built = path.join(build, 'body.json');
  body = fs.existsSync(built)
    ? JSON.parse(fs.readFileSync(built, 'utf8'))
    : JSON.parse(fs.readFileSync(path.join(build, 'draft.json'), 'utf8')).body;
  browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--allow-file-access-from-files'],
  });
});

after(async () => { if (browser) await browser.close(); });

async function open(key, viewport = { width: 1280, height: 720 }) {
  const scene = body.scenes.find(item => item.outlineId === key);
  const html = scene.content.html.replace(/\/api\/classroom-media\/[^/\s"'<>]+\/media\/[^\s"'<>+]+/g, url => {
    return pathToFileURL(path.join(build, 'media', url.split('/media/')[1])).href;
  });
  const file = path.join(temporary, key + '.html');
  fs.writeFileSync(file, html);
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(pathToFileURL(file).href);
  await page.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth));
  return { page, errors };
}

async function shot(page, key, state) {
  if (process.env.COUNT_COMPARE_CAPTURE !== '1') return;
  await page.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth));
  await page.screenshot({ path: path.join(temporary, key + '-' + state + '.png') });
}

async function start(page, key) {
  await page.locator('#start-btn').click();
  await page.locator('#ready.gone').waitFor({ state: 'attached' });
  await shot(page, key, 'initial');
}

async function next(page, level) {
  await page.getByText('第 ' + level + ' 轮', { exact: true }).waitFor();
}

async function wrong(page, key) {
  await page.locator('#count-check').click();
  assert.equal(await page.locator('#star-n').textContent(), '0');
  await page.locator('#say.no').waitFor();
  await page.waitForTimeout(500);
  await shot(page, key, 'wrong');
}

async function correct(page, key) {
  await page.locator('#count-check').click();
  await page.locator('#say.ok').waitFor();
  assert.equal(await page.locator('#star-n').textContent(), '1');
  await shot(page, key, 'correct');
}

async function finished(page) {
  await page.locator('#finish:not(.gone)').waitFor();
  await page.locator('#btn-again').click();
  await next(page, 1);
  assert.equal(await page.locator('#star-n').textContent(), '0');
}

async function drag(page, source, target) {
  const from = await page.locator(source).boundingBox();
  const to = await page.locator(target).boundingBox();
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 12 });
  await page.mouse.up();
}

test('postage items move one at a time, can be returned, and reset', async () => {
  const { page, errors } = await open('p02');
  try {
    await start(page, 'p02');
    await wrong(page, 'p02');
    await drag(page, '#count-take', '#count-board');
    assert.equal(await page.locator('#count-board img').count(), 1);
    for (let i = 0; i < 3; i++) await page.locator('#count-take').click();
    await page.locator('#count-check').click();
    await page.locator('#say.no').waitFor();
    await page.locator('#count-return').click();
    assert.equal(await page.locator('#count-board img').count(), 3);
    await correct(page, 'p02');
    for (const [round, count] of [[2, 6], [3, 9]]) {
      await next(page, round);
      for (let i = 0; i < count; i++) await page.locator('#count-take').click();
      await page.locator('#count-check').click();
    }
    await finished(page);
    assert.equal(await page.locator('#count-board img').count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('printing verifies both the chosen symbol and the number of marks', async () => {
  const { page, errors } = await open('p03');
  try {
    await start(page, 'p03');
    await page.locator('[data-ink="leaf"]').click();
    assert.equal(await page.locator('[data-slot="0"]').isDisabled(), true);
    assert.equal(await page.locator('#count-board img').count(), 0);
    await wrong(page, 'p03');
    for (const [round, ink, count] of [[1, 'sun', 3], [2, 'leaf', 5], [3, 'sun', 8]]) {
      await next(page, round);
      await page.locator('[data-ink="' + ink + '"]').click();
      for (let i = 0; i < count; i++) await page.locator('[data-slot="' + (9 - i) + '"]').click();
      if (round === 1) {
        await page.locator('[data-slot="6"]').click();
        await page.locator('#count-check').click();
        await page.locator('#say.no').waitFor();
        await page.locator('#count-return').click();
        assert.equal(await page.locator('#count-board img').count(), count);
        await correct(page, 'p03');
      } else await page.locator('#count-check').click();
    }
    await finished(page);
    assert.equal(await page.locator('#count-board img').count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('rearranging moves the same ten objects and each can be counted once', async () => {
  const { page, errors } = await open('p04');
  try {
    await start(page, 'p04');
    await wrong(page, 'p04');
    const token = await page.locator('[data-token="0"]').elementHandle();
    const original = await token.evaluate(element => element.style.left);
    for (const round of [1, 2]) {
      await next(page, round);
      await page.locator('#count-shift').click();
      assert.equal(await page.locator('[data-token]').count(), 10);
      assert.notEqual(await token.evaluate(element => element.style.left), original);
      assert.equal(await page.locator('[data-token="0"]').evaluate((element, previous) => element === previous, token), true);
      for (let i = 0; i < 10; i++) await page.locator('[data-token="' + i + '"]').click();
      assert.equal(await page.locator('[data-token].counted').count(), 10);
      assert.equal(await page.locator('[data-token="0"]').isDisabled(), true);
      if (round === 1) await correct(page, 'p04');
      else await page.locator('#count-check').click();
    }
    await finished(page);
    assert.equal(await page.locator('[data-token].counted').count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('comparison shows the unpaired side and accepts any count meeting the rule', async () => {
  const { page, errors } = await open('p07');
  try {
    await start(page, 'p07');
    await wrong(page, 'p07');
    await page.locator('#count-plus').click();
    await page.locator('#count-plus').click();
    assert.equal(await page.locator('#count-bottom img.unpaired').count(), 2);
    await correct(page, 'p07');
    await next(page, 2);
    await page.locator('#count-plus').click();
    await page.locator('#count-check').click();
    await page.locator('#say.no').waitFor();
    assert.equal(await page.locator('#count-plus').isDisabled(), true);
    await page.locator('#count-minus').click();
    await page.locator('#count-minus').click();
    assert.equal(await page.locator('#count-top img.unpaired').count(), 1);
    await page.locator('#count-check').click();
    await next(page, 3);
    await page.locator('#count-plus').click();
    assert.equal(await page.locator('#count-board img.unpaired').count(), 0);
    await page.locator('#count-check').click();
    await finished(page);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('every envelope receives its own pair and rejects a third item', async () => {
  const { page, errors } = await open('p09');
  try {
    await start(page, 'p09');
    await wrong(page, 'p09');
    await drag(page, '#count-supply button', '[data-envelope="0"]');
    const first = page.locator('[data-envelope="0"]');
    assert.equal(await first.locator('.count-token-art').count(), 1);
    await first.click();
    await first.click();
    assert.equal(await first.locator('.count-token-art').count(), 2);
    assert.equal(await page.locator('[data-envelope="1"] .count-token-art').count(), 0);
    for (const [round, envelopes] of [[1, 2], [2, 3], [3, 5]]) {
      await next(page, round);
      for (let i = round === 1 ? 1 : 0; i < envelopes; i++) {
        const button = page.locator('[data-envelope="' + i + '"]');
        await button.click(); await button.click();
      }
      if (round === 1) await correct(page, 'p09');
      else await page.locator('#count-check').click();
    }
    await finished(page);
    assert.equal(await page.locator('.count-token-art').count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('teacher demos change the real objects without changing student rewards', async () => {
  const demos = {
    p02: [{ demo: true }, { showFour: true }],
    p03: [{ demo: true }, { showPrint: true }],
    p04: [{ demo: true }, { demoSpread: true }, { demoRows: true }],
    p07: [{ demo: true }, { demoEqual: true }],
    p09: [{ demo: true }, { demoFilled: true }],
  };
  for (const key of sceneKeys) {
    const { page, errors } = await open(key);
    try {
      await page.evaluate(states => { K.begin(); states.forEach(state => K.onState(state)); }, demos[key]);
      await page.locator('#count-board img').first().waitFor();
      assert.equal(await page.locator('#count-check').isDisabled(), true);
      assert.equal(await page.locator('#star-n').textContent(), '0');
      if (key === 'p04') {
        const rowSizes = await page.locator('[data-token]').evaluateAll(elements => {
          const counts = new Map();
          for (const element of elements) {
            const y = Math.round(element.getBoundingClientRect().top);
            counts.set(y, (counts.get(y) || 0) + 1);
          }
          return [...counts.values()];
        });
        assert.deepEqual(rowSizes, [5, 5]);
      }
      await shot(page, key, 'teacher');
      await page.evaluate(() => K.onState({ play: true }));
      await next(page, 1);
      assert.equal(await page.locator('#count-check').isDisabled(), false);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  }
});

test('icon controls and object pictures remain playable at the smallest size with captions covered', async () => {
  const cases = {
    p02: async page => {
      for (let i = 0; i < 3; i++) await page.locator('#count-take').click();
    },
    p03: async page => {
      await page.locator('[data-ink="sun"] img').waitFor();
      await page.locator('[data-ink="sun"]').click();
      for (let i = 0; i < 3; i++) await page.locator('[data-slot="' + i + '"]').click();
    },
    p04: async page => {
      await page.locator('#count-shift svg').waitFor();
      await page.locator('#count-shift').click();
      for (let i = 0; i < 10; i++) await page.locator('[data-token="' + i + '"]').click();
    },
    p07: async page => {
      await page.locator('#count-plus').click();
      assert.equal(await page.locator('#count-bottom img.unpaired').count(), 1);
    },
    p09: async page => {
      for (const index of [0, 1]) {
        const envelope = page.locator('[data-envelope="' + index + '"]');
        await envelope.click();
        await envelope.click();
      }
    },
  };
  for (const [key, interact] of Object.entries(cases)) {
    const { page, errors } = await open(key, { width: 640, height: 360 });
    try {
      await page.locator('#start-btn').click();
      await page.addStyleTag({ content:
        '.count-head,#say {visibility:hidden} .count-controls button,#count-shift,#count-return {font-size:0}',
      });
      await page.locator('#count-listen svg').waitFor();
      await page.locator('#count-check svg').waitFor();
      await interact(page);
      await page.locator('#count-check').click();
      assert.equal(await page.locator('#star-n').textContent(), '1');
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  }
});
