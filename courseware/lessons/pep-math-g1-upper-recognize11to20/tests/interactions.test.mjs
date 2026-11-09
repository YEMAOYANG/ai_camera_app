import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from '../../../../student-web/node_modules/playwright-core/index.mjs';

const work = resolve('output/courseware-lessons/pep-math-g1-upper-recognize11to20/release-work-v1');
const scratch = process.env.MIRA_TASK_TMPDIR;
const capture = process.env.MIRA_RECOGNIZE_SCREENSHOTS === '1';
const executablePath = process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
let browser;
let body;

before(async () => {
  assert.ok(scratch, 'Run through tools/task_tmp.py');
  body = JSON.parse(await readFile(process.env.MIRA_RECOGNIZE_BODY || resolve(work, 'pre-audio-body.json')));
  browser = await chromium.launch({ executablePath, headless: true, args: ['--allow-file-access-from-files'] });
});
after(async () => { await browser?.close(); });

async function pageFor(key) {
  const scene = body.scenes.find(item => item.outlineId === key);
  assert.equal(scene.type, 'interactive');
  const media = /\/api\/classroom-media\/[\w-]+\/media\/([\w.-]+)/g;
  const html = scene.content.html.replace(media, (_, name) => pathToFileURL(resolve(work, 'media', name)).href);
  const filename = resolve(scratch, key + '.html');
  await writeFile(filename, html);
  const page = await browser.newPage({ viewport: { width: 640, height: 360 } });
  await page.goto(pathToFileURL(filename).href);
  await page.locator('#start-btn').click();
  await page.locator('#' + key + '-view').waitFor({ state: 'visible' });
  return page;
}
function screenshot(page, key, phase) {
  return capture ? page.screenshot({ path: resolve(scratch, key + '-' + phase + '.png') }) : undefined;
}
function button(page, label) {
  return page.getByRole('button', { name: label, exact: true });
}
async function done(page, count) {
  await page.waitForFunction(n => document.querySelectorAll('#dots .done').length === n, count);
}
function textIs(page, selector, expected) {
  return page.waitForFunction(({ css, value }) => document.querySelector(css)?.textContent === value,
    { css: selector, value: expected });
}
async function teacher(page, mode) {
  await page.evaluate(state => window.postMessage({ type: 'SET_WIDGET_STATE', state: { mode: state } }, '*'), mode);
}

const scenarios = [
  {
    key: 'pack', wrong: '9根的一盘', right: '10根的一盘', next: ['14', '18'], demo: 'read-eight',
    initial: async page => assert.deepEqual(await page.locator('.pack-tray').evaluateAll(
      trays => trays.map(tray => tray.querySelectorAll('.stick-diagram').length)), [9, 11, 10]),
    changed: async page => page.locator('#pack-count').waitFor({ state: 'visible' }),
    demonstrated: async page => {
      await page.locator('#pack-loose .stick-diagram').first().waitFor({ state: 'visible' });
      assert.equal(await page.locator('#pack-loose .stick-diagram').count(), 8);
    },
  },
  {
    key: 'twenty', wrong: '扎成一捆', right: '添一根', next: ['扎成一捆'], demo: 'traded',
    initial: async page => assert.equal(await page.locator('#exchange-ones .stick-diagram').count(), 9),
    changed: async page => assert.equal(await page.locator('#exchange-ones .stick-diagram').count(), 10),
    demonstrated: async page => {
      await page.locator('#exchange-new-bundle').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#exchange-ones .stick-diagram').count(), 0);
    },
  },
  {
    key: 'beads', wrong: '2颗珠子', right: '1颗珠子', next: ['5颗珠子', '1颗珠子', '8颗珠子'], demo: 'both',
    initial: async page => assert.equal(await page.locator('#bead-tens .bead-stack i').count(), 0),
    changed: async page => assert.equal(await page.locator('#bead-tens .bead-stack i').count(), 1),
    demonstrated: async page => {
      await textIs(page, '#bead-target', '11');
      assert.equal(await page.locator('#bead-tens .bead-stack i').count(), 1);
      assert.equal(await page.locator('#bead-ones .bead-stack i').count(), 1);
    },
  },
  {
    key: 'route', wrong: '18', right: '16', next: ['19', '11'], demo: 'filled',
    initial: page => textIs(page, '#route-hole', ''),
    changed: page => textIs(page, '#route-hole', '16'),
    demonstrated: page => textIs(page, '#route-hole', '12'),
  },
  {
    key: 'near', wrong: '比较到二十的距离', right: '比较到十的距离',
    next: ['比较到二十的距离', '比较到二十的距离'], demo: 'paths',
    initial: async page => {
      assert.equal(await page.locator('#near-line .near-tick').count(), 11);
      assert.equal(await page.locator('#near-line .walk').count(), 0);
    },
    changed: async page => assert.equal(await page.locator('#near-line .walk').count(), 10),
    demonstrated: async page => {
      await textIs(page, '#near-line .near-count.left', '2');
      await textIs(page, '#near-line .near-count.right', '8');
    },
  },
];

for (const scenario of scenarios) {
  test(scenario.key + ' checks the picture action, retry, finish and teacher reset', async () => {
    const page = await pageFor(scenario.key);
    try {
      await scenario.initial(page);
      await screenshot(page, scenario.key, 'initial');
      await button(page, scenario.wrong).click();
      await page.locator('#say.no').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#star-n').textContent(), '0');
      assert.equal(await page.locator('#dots .done').count(), 0);
      await screenshot(page, scenario.key, 'wrong');
      await page.addStyleTag({ content: '#say, #hud .chip, .operation span, .bead-column>span {visibility:hidden!important;}' });
      await button(page, scenario.right).click();
      await scenario.changed(page);
      assert.equal(await page.locator('#star-n').textContent(), '1');
      await screenshot(page, scenario.key, 'correct');
      await done(page, 1);
      for (const option of scenario.next) await button(page, option).click();
      await page.locator('#finish:not(.gone)').waitFor({ state: 'visible' });
      await page.locator('#btn-again').click();
      await scenario.initial(page);
      assert.equal(await page.locator('#star-n').textContent(), '0');
      await page.reload();
      await teacher(page, scenario.demo);
      await scenario.demonstrated(page);
      await screenshot(page, scenario.key, 'demo');
      await teacher(page, 'play');
      await page.waitForFunction(() => document.querySelector('.station-board:not([hidden]) button:not(:disabled)'));
      await scenario.initial(page);
      assert.deepEqual(await page.evaluate(() => window.__errs), []);
    } finally {
      await page.close();
    }
  });
}

test('a missing optional rod image preserves the displayed count', async () => {
  const page = await pageFor('twenty');
  try {
    await page.locator('#exchange-add img').evaluate(image => { image.src = 'file:///missing-rod-test.png'; });
    await page.locator('#exchange-add .diagram-fallback .stick-diagram').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#exchange-add .diagram-fallback .stick-diagram').count(), 1);
    assert.equal(await page.locator('#exchange-ones .stick-diagram').count(), 9);
  } finally {
    await page.close();
  }
});

test('teacher numbers exactly four loose rods in order and models writing sixteen', async () => {
  const pack = await pageFor('pack');
  const beads = await pageFor('beads');
  try {
    await teacher(pack, 'counted');
    const rods = pack.locator('#pack-loose .counted-stick');
    await rods.last().waitFor({ state: 'visible' });
    assert.deepEqual(await rods.evaluateAll(items => items.map(item => item.dataset.count)), ['1', '2', '3', '4']);
    await rods.last().evaluate(rod => Promise.all(rod.getAnimations().map(animation => animation.finished)));
    await screenshot(pack, 'pack', 'counted');
    await teacher(beads, 'sixteen');
    await textIs(beads, '#bead-target', '16');
    assert.equal(await beads.locator('#bead-tens .bead-stack i').count(), 1);
    assert.equal(await beads.locator('#bead-ones .bead-stack i').count(), 6);
    await screenshot(beads, 'beads', 'sixteen');
    await teacher(beads, 'play');
    await textIs(beads, '#bead-target', '15');
  } finally {
    await pack.close();
    await beads.close();
  }
});
