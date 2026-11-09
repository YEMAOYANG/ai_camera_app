import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from '../../../../student-web/node_modules/playwright-core/index.mjs';

const work = resolve(process.env.MIRA_SOLID_SHAPES_WORK || 'output/courseware-lessons/pep-math-g1-upper-solid-shapes');
const scratch = process.env.MIRA_TASK_TMPDIR;
const capture = process.env.MIRA_SOLID_SHAPES_SCREENSHOTS === '1';
const executablePath = process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const width = 640;
const height = 360;
let browser;
let body;

before(async () => {
  assert.ok(scratch, 'Run under tools/task_tmp.py');
  body = JSON.parse(await readFile(process.env.MIRA_SOLID_SHAPES_BODY || resolve(work, 'preview-body.json')));
  browser = await chromium.launch({ executablePath, headless: true, args: ['--allow-file-access-from-files'] });
});
after(async () => { await browser?.close(); });

async function openScene(key) {
  const scene = body.scenes.find(item => item.outlineId === key);
  assert.equal(scene.type, 'interactive');
  const media = /\/api\/classroom-media\/[\w-]+\/media\/([\w.-]+)/g;
  const html = scene.content.html.replace(media, (_, filename) => pathToFileURL(resolve(work, 'media', filename)).href);
  const filename = resolve(scratch, key + '.html');
  await writeFile(filename, html);
  const page = await browser.newPage({ viewport: { width, height } });
  await page.goto(pathToFileURL(filename).href);
  return page;
}

async function snapshot(page, key, state) {
  if (capture) await page.screenshot({ path: resolve(scratch, key + '-' + state + '.png') });
}

async function click(page, selector) {
  await page.locator(selector).click();
}
async function dots(page, count) {
  await page.waitForFunction(expected => document.querySelectorAll('#dots .done').length === expected, count);
}
async function caption(page, kind) {
  await page.locator('#say.' + kind).waitFor({ state: 'visible' });
}
async function ready(page) {
  await click(page, '#start-btn');
  await page.locator('#ready').waitFor({ state: 'hidden' });
}
async function state(page, mode) {
  await page.evaluate(value => window.postMessage({ type: 'SET_WIDGET_STATE', state: { mode: value } }, '*'), mode);
}
async function hideReading(page) {
  await page.addStyleTag({ content: '#play span, #hud .chip, #say { visibility: hidden !important; }' });
}

const cases = [
  { key: 'turn', miss: '#turn-flat', hit: '#turn-cube', finish: ['#turn-control', '#turn-cube'],
    demo: 'turned', demoVisible: '#turn-cube.turned[disabled]', firstMove: '#turn-control', afterCorrect: '#turn-cube.success' },
  { key: 'roll', miss: '#roll-stand', hit: '#roll-side', finish: ['#roll-stand', '#roll-ball'],
    demo: 'sphere', demoVisible: '#roll-track[data-mode="sphere"]', afterCorrect: '#roll-track[data-mode="side"].moving' },
  { key: 'sort', miss: '[data-family="cube"]', hit: '[data-family="box"]',
    finish: ['[data-family="tube"]', '[data-family="cube"]', '[data-family="ball"]'],
    demo: 'placed', demoVisible: '[data-family="box"].placed .stored:not([hidden])', afterCorrect: '[data-family="box"].placed' },
  { key: 'clues', miss: 'button[data-form="box"]', hit: 'button[data-form="tube"]',
    finish: ['button[data-form="cube"]', 'button[data-form="ball"]'],
    demo: 'revealed', demoVisible: '#clue-reveal.revealed #clue-object:not([hidden])', afterCorrect: '#clue-reveal.revealed' },
  { key: 'stack', miss: 'button[data-form="ball"]', hit: 'button[data-form="box"]', finish: ['button[data-form="cube"]'],
    demo: 'top', demoVisible: '#stack-top.placed img[data-form="tube"]:not([hidden])', afterCorrect: '#stack-base.placed' },
];

for (const scenario of cases) {
  test(scenario.key + ' preserves the picture task, gentle retry and teacher reset', async () => {
    const page = await openScene(scenario.key);
    try {
      await snapshot(page, scenario.key, 'ready');
      await ready(page);
      await snapshot(page, scenario.key, 'initial');
      if (scenario.firstMove) await click(page, scenario.firstMove);
      await click(page, scenario.miss);
      await caption(page, 'no');
      assert.equal(await page.locator('#star-n').textContent(), '0');
      assert.equal(await page.locator('#dots .done').count(), 0);
      assert.equal(await page.locator('.solid-card.success').count(), 0);
      await snapshot(page, scenario.key, 'wrong');
      await hideReading(page);
      await click(page, scenario.hit);
      await page.locator(scenario.afterCorrect).waitFor({ state: 'visible' });
      assert.equal(await page.locator('#star-n').textContent(), '1');
      await snapshot(page, scenario.key, 'correct');
      await dots(page, 1);
      for (const selector of scenario.finish) await click(page, selector);
      await page.locator('#finish:not(.gone)').waitFor({ state: 'visible' });
      await click(page, '#btn-again');
      assert.equal(await page.locator('#star-n').textContent(), '0');
      assert.equal(await page.locator('#dots .done').count(), 0);
      await page.reload();
      await state(page, scenario.demo);
      await page.locator(scenario.demoVisible).waitFor({ state: 'visible' });
      await snapshot(page, scenario.key, 'demo');
      await state(page, 'play');
      await page.waitForFunction(() => document.querySelectorAll('.solid-card:not(:disabled)').length >= 2);
      assert.equal(await page.locator('#star-n').textContent(), '0');
      assert.deepEqual(await page.evaluate(() => window.__errs), []);
      assert.equal(await page.evaluate(() => Array.from(document.images).some(
        image => !image.hidden && image.currentSrc && (!image.complete || image.naturalWidth === 0),
      )), false);
    } finally {
      await page.close();
    }
  });
}

test('a missing registered shape picture falls back to the same geometry', async () => {
  const page = await openScene('turn');
  try {
    await ready(page);
    const image = page.locator('#turn-target');
    await image.evaluate(element => { element.src = 'file:///missing-solid-shapes-test-image.png'; });
    await page.waitForFunction(() => {
      const element = document.querySelector('#turn-target');
      const svg = element.nextElementSibling;
      return svg?.classList.contains('geometry-fallback') && svg.querySelector('path')
        && svg.getBoundingClientRect().width > 0;
    });
    assert.equal(await image.getAttribute('data-form'), 'cube');
  } finally {
    await page.close();
  }
});
