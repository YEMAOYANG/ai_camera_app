import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const work = process.env.MIRA_LESSON_WORK || path.join(repo, 'output/courseware-lessons/g1-english-e818f015bc1fd476');
const require = createRequire(path.join(repo, 'student-web/package.json'));
const { chromium } = require('playwright-core');
const draft = JSON.parse(fs.readFileSync(path.join(work, 'draft.json'), 'utf8'));
const screenshots = process.env.MIRA_VISUAL_REVIEW || path.join(work, 'visual-review');
fs.mkdirSync(screenshots, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });

async function open(scene, failImageOnce = false) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let failed = false;
  await page.route('http://lesson.local/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.includes('/media/')) {
      const name = path.basename(pathname);
      if (failImageOnce && !failed && name.endsWith('.png')) {
        failed = true;
        await route.fulfill({ status: 404, body: '' });
      } else {
        const filename = path.join(work, 'media', name);
        assert.ok(fs.existsSync(filename), `Referenced media is missing: ${name}`);
        await route.fulfill({ path: filename, contentType: name.endsWith('.png') ? 'image/png' : 'audio/wav' });
      }
    } else await route.fulfill({ contentType: 'text/html', body: scene.content.html });
  });
  await page.goto('http://lesson.local/page');
  await page.waitForTimeout(120);
  return { page, errors };
}

const tap = selector => page => page.locator(selector).click();
const paint = color => async page => {
  await page.locator('#color-tray-' + color).click();
  await page.locator('#color-drop').click();
};
const dragPaint = color => async page => {
  const chip = await page.locator('#color-tray-' + color).boundingBox();
  const car = await page.locator('#color-drop').boundingBox();
  await page.mouse.move(chip.x + chip.width / 2, chip.y + chip.height / 2);
  await page.mouse.down();
  await page.mouse.move(car.x + car.width / 2, car.y + car.height / 2, { steps: 8 });
  await page.mouse.up();
};
const plan = (animal, color) => async page => {
  await page.locator('#phrase-choice-' + animal).click();
  await page.locator('#phrase-palette-' + color).click();
};
const paintState = page => page.locator('#color-drop').getAttribute('data-paint');
const moveState = stage => page => page.locator(stage + ' img').count();
const cases = [
  { key: 's03', round: '#animal-board', state: moveState('#animal-stage'), initial: 0,
    demo: { demo: 'dog' }, demonstration: 1, wrong: tap('#animal-right'),
    correct: [tap('#animal-left'), tap('#animal-right'), tap('#animal-left')], correctState: [1, 1, 1] },
  { key: 's08', round: '#color-board', state: paintState, initial: 'unpainted',
    demo: { demo: 'blue' }, demonstration: 'blue', wrong: paint('red'),
    correct: [paint('yellow'), dragPaint('blue')], correctState: ['yellow', 'blue'] },
  { key: 's11', round: '#phrase-board', state: moveState('#phrase-frame'), initial: 0,
    demo: { demo: 'dog' }, demonstration: 1, wrong: tap('#phrase-choice-cat'),
    correct: [plan('panda', 'blue'), plan('bird', 'red'), plan('cat', 'yellow'), plan('dog', 'green')],
    correctState: [1, 1, 1, 1], next: async page => {
      const next = page.locator('#phrase-next');
      await next.click();
      assert.ok(await next.isDisabled() || !await next.isVisible(), 'Next click is accepted even during recorded feedback');
    } },
  { key: 's13', round: '#pair-board', state: moveState('#pair-stage'), initial: 0,
    demo: { demo: ['black', 'white'] }, demonstration: 1, wrong: tap('#pair-tray-red'),
    correct: [['white', 'black'], ['yellow', 'blue'], ['green', 'red']].map(colors => async page => {
      for (const color of colors) await page.locator('#pair-tray-' + color).click();
    }), correctState: [1, 1, 1] },
];

async function progress(page, test, round) {
  if (test.next) await test.next(page);
  if (round === test.correct.length) {
    await page.locator('#finish:not(.gone)').waitFor();
  } else {
    await page.waitForFunction(({ selector, value }) => document.querySelector(selector).dataset.round === value,
      { selector: test.round, value: String(round) });
  }
}

async function capture(page, filename) {
  await page.locator('#play img:visible').evaluateAll(images =>
    Promise.all(images.map(image => image.decode())));
  await page.screenshot({ path: filename, animations: 'disabled' });
}

try {
  for (const test of cases) {
    const scene = draft.body.scenes.find(item => item.id === 'scene-' + test.key);
    assert.ok(scene);
    const { page, errors } = await open(scene);
    await page.locator('#ready button').click();
    await capture(page, path.join(screenshots, `${test.key}-initial.png`));

    await page.evaluate(state => window.postMessage({ type: 'SET_WIDGET_STATE', state }, '*'), test.demo);
    await page.waitForTimeout(50);
    assert.equal(await test.state(page), test.demonstration, 'Teacher demonstration changes the picture');
    assert.equal(await page.locator('#star-n').textContent(), '0', 'Teacher demonstration is not student evidence');
    await capture(page, path.join(screenshots, `${test.key}-teacher.png`));
    await page.evaluate(() => window.postMessage({ type: 'SET_WIDGET_STATE', state: { reset: true } }, '*'));
    await page.waitForTimeout(50);
    if (test.key === 's08') assert.equal(await page.locator('#color-tray .teach-hl').count(), 0);

    await test.wrong(page);
    assert.equal(await page.locator('#star-n').textContent(), '0');
    assert.equal(await page.locator(test.round).getAttribute('data-round'), '0');
    assert.equal(await test.state(page), test.initial, 'First wrong answer does not reveal the answer');
    assert.equal(await page.locator('#say').getAttribute('class'), 'no');
    await capture(page, path.join(screenshots, `${test.key}-wrong.png`));

    for (let round = 0; round < test.correct.length; round += 1) {
      await test.correct[round](page);
      assert.equal(await page.locator('#star-n').textContent(), String(round + 1));
      assert.equal(await test.state(page), test.correctState[round], 'Correct answer changes a real picture');
      if (round === 0) await capture(page, path.join(screenshots, `${test.key}-correct.png`));
      await progress(page, test, round + 1);
    }
    assert.ok(await page.locator('#finish:not(.gone)').isVisible());
    await page.locator('#btn-again').click();
    assert.equal(await page.locator('#star-n').textContent(), '0');
    assert.equal(await page.locator(test.round).getAttribute('data-round'), '0');

    // Non-target instructional text can be covered while picture operations still work.
    await page.addStyleTag({ content: '#play .scene-caption,#play .frame-label,#play .btn,#say{color:transparent!important}' });
    for (const [index, play] of test.correct.entries()) { await play(page); await progress(page, test, index + 1); }
    assert.ok(await page.locator('#finish:not(.gone)').isVisible());
    assert.deepEqual(errors, []);
    console.log(`${test.key}: teacher, first-wrong, picture movement, completion, replay and masked-text play passed`);
    await page.close();
  }

  const { page, errors } = await open(draft.body.scenes.find(scene => scene.id === 'scene-s03'), true);
  await page.locator('#asset-stop').waitFor();
  assert.ok(await page.locator('#asset-retry').isVisible());
  await page.locator('#asset-retry').click();
  await page.waitForTimeout(200);
  assert.equal(await page.locator('#asset-stop').count(), 0);
  await page.locator('#ready button').click();
  assert.equal(await page.locator('#star-n').textContent(), '0');
  assert.deepEqual(errors, []);
  await page.close();
  console.log('Image failure blocks guessing and reload recovers without awarding evidence');
} finally {
  await browser.close();
}
