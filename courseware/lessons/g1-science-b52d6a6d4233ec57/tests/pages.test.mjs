import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const repo = fileURLToPath(new URL('../../../../', import.meta.url));
const work = process.env.MIRA_LESSON_WORK || path.join(repo, 'output/courseware-lessons/g1-science-b52d6a6d4233ec57');
const temporary = process.env.MIRA_TASK_TMPDIR;
assert.ok(temporary, 'Run through tools/task_tmp.py so browser fixtures share one private task directory.');
const require = createRequire(path.join(repo, 'student-web/package.json'));
const { chromium } = require('playwright-core');
const bodyPath = fs.existsSync(path.join(work, 'body.json')) ? 'body.json' : 'draft.json';
const loaded = JSON.parse(fs.readFileSync(path.join(work, bodyPath), 'utf8'));
const body = loaded.body || loaded;
const source = JSON.parse(fs.readFileSync(path.join(repo, 'courseware/lessons/g1-science-b52d6a6d4233ec57/lesson.json'), 'utf8'));
const browser = await chromium.launch({ executablePath: process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--allow-file-access-from-files'] });
test.after(() => browser.close());

async function open(key) {
  const scene = body.scenes.find(s => s.outlineId === key);
  assert.ok(scene, key);
  const html = scene.content.html.replace(/\/api\/classroom-media\/[^/\s"'<>]+\/media\/[^\s"'<>+]+/g, url => pathToFileURL(path.join(work, 'media', url.split('/media/')[1])).href);
  const filename = path.join(temporary, key + '.html');
  fs.writeFileSync(filename, html);
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(pathToFileURL(filename).href);
  await page.locator('#start-btn').click();
  for (const beat of source.scenes.find(s => s.key === key).script) {
    for (const op of ['highlight', 'reveal', 'annotate']) if (beat[op]) assert.equal(await page.locator(beat[op]).count(), 1, key + ' teacher target');
  }
  return { page, errors };
}
const snapshot = page => page.evaluate(() => K.lessonSnapshot());
async function replay(page) {
  await page.locator('#btn-again').click();
  assert.equal(await page.locator('#finish.gone').count(), 1);
  assert.equal(await page.locator('#star-n').textContent(), '0');
}

test('plan: first miss preserves empty rail; each step is recorded; unknown object skips smell/taste; replay resets', async () => {
  const { page, errors } = await open('p02');
  const choices = await page.locator('#plan-choices button').evaluateAll(buttons => buttons.map(b => b.dataset.key));
  assert.notDeepEqual(choices.filter(key => key !== 'ear'), ['eye', 'hand', 'nose', 'adult', 'tongue']);
  await page.locator('#plan-tongue').click();
  assert.equal((await snapshot(page)).step, 0);
  assert.equal((await snapshot(page)).tries, 1);
  assert.equal(await page.locator('#plan-track img').count(), 0);
  assert.equal(await page.locator('#plan-eye.teach-hl').count(), 0, 'first miss must not reveal answer');
  for (const key of ['eye', 'hand', 'nose', 'adult', 'tongue']) await page.locator('#plan-' + key).click();
  await page.waitForTimeout(950);
  assert.equal((await snapshot(page)).level, 1);
  await page.locator('#plan-nose').click();
  assert.equal((await snapshot(page)).step, 0);
  for (const key of ['eye', 'adult']) await page.locator('#plan-' + key).click();
  await page.locator('#btn-again').waitFor();
  await replay(page);
  assert.equal((await snapshot(page)).step, 0);
  assert.equal((await snapshot(page)).level, 0);
  assert.deepEqual(errors, []);
  await page.close();
});

test('matching: wrong pairing adds no evidence; all five organs can be dragged; replay clears connections', async () => {
  const { page, errors } = await open('p06');
  const targets = await page.locator('#match-board button').evaluateAll(buttons => buttons.map(b => b.dataset.key));
  const choices = await page.locator('#sense-sources button').evaluateAll(buttons => buttons.map(b => b.dataset.key));
  assert.ok(choices.every((key, index) => key !== targets[index]), 'Position alone cannot solve a pairing');
  await page.locator('#sense-eye').click();
  await page.locator('#match-scene-2').click();
  assert.equal((await snapshot(page)).placed.length, 0);
  assert.equal((await snapshot(page)).tries, 1);
  assert.equal(await page.locator('.match-result img').count(), 0);
  for (const [index, key] of ['eye', 'ear', 'nose', 'tongue', 'hand'].entries()) await page.locator('#sense-' + key).dragTo(page.locator('#match-scene-' + (index + 1)));
  await page.locator('#btn-again').waitFor();
  assert.equal(await page.locator('.match-result img').count(), 5);
  await replay(page);
  assert.equal((await snapshot(page)).placed.length, 0);
  assert.equal(await page.locator('.match-result img').count(), 0);
  assert.deepEqual(errors, []);
  await page.close();
});

test('record: wrong or repeated choices cannot add evidence; two goals use different methods; replay empties bag', async () => {
  const { page, errors } = await open('p09');
  await page.locator('#record-tongue').click();
  assert.equal((await snapshot(page)).found.length, 0);
  assert.equal((await snapshot(page)).tries, 1);
  assert.equal(await page.locator('.record-card.filled').count(), 0);
  for (const key of ['eye', 'hand', 'nose']) await page.locator('#record-' + key).click();
  await page.waitForTimeout(950);
  assert.equal((await snapshot(page)).level, 1);
  for (const key of ['eye', 'hand', 'ear']) await page.locator('#record-' + key).click();
  await page.locator('#btn-again').waitFor();
  assert.equal(await page.locator('.record-card.filled').count(), 3);
  await replay(page);
  assert.equal((await snapshot(page)).found.length, 0);
  assert.equal(await page.locator('.record-card.filled').count(), 0);
  assert.deepEqual(errors, []);
  await page.close();
});

test('care: first miss keeps unsafe scene; correct action actually changes image; replay and teacher demo restore play', async () => {
  const { page, errors } = await open('p12');
  const initial = await page.locator('#care-picture').getAttribute('src');
  await page.locator('#care-screen-break').click();
  assert.equal(await page.locator('#care-picture').getAttribute('src'), initial);
  assert.equal((await snapshot(page)).tries, 1);
  assert.equal((await snapshot(page)).fixed, false);
  await page.locator('#care-hands-down').dragTo(page.locator('#care-scene'));
  assert.notEqual(await page.locator('#care-picture').getAttribute('src'), initial);
  await page.waitForTimeout(1000);
  await page.locator('#care-stick-away').click();
  await page.waitForTimeout(1000);
  await page.locator('#care-hands-down').click();
  await page.locator('#btn-again').waitFor();
  await replay(page);
  assert.equal((await snapshot(page)).level, 0);
  await page.evaluate(() => K.onState({ demo: 'reading' }));
  assert.equal((await snapshot(page)).phase, 'demo');
  await page.evaluate(() => K.onState({ phase: 'play' }));
  assert.equal((await snapshot(page)).phase, 'play');
  assert.equal((await snapshot(page)).fixed, false);
  assert.deepEqual(errors, []);
  await page.close();
});

test('teacher demonstration disables covered game controls and restores them for the child', async () => {
  for (const [key, demo, selector] of [
    ['p06', 'eye', '#match-board button, #sense-sources button'],
    ['p09', 'sponge', '#record-senses button'],
    ['p12', 'reading', '#care-options button'],
  ]) {
    const { page, errors } = await open(key);
    await page.evaluate(demo => K.onState({ demo }), demo);
    assert.equal(await page.locator(selector).evaluateAll(buttons => buttons.every(b => b.disabled)), true, key);
    if (key === 'p09') assert.equal(await page.locator('#record-demo-methods .rail-slot img:visible').count(), 2);
    await page.evaluate(() => K.onState({ phase: 'play' }));
    assert.equal(await page.locator(selector).evaluateAll(buttons => buttons.every(b => !b.disabled)), true, key);
    assert.deepEqual(errors, []);
    await page.close();
  }
});

test('ear scene accepts lowering the hand as a valid alternative that stops the unsafe action', async () => {
  const { page, errors } = await open('p12');
  await page.locator('#care-hands-down').click();
  await page.waitForTimeout(1000);
  assert.equal((await snapshot(page)).level, 1);
  await page.locator('#care-hands-down').click();
  assert.equal((await snapshot(page)).fixed, true);
  assert.equal((await snapshot(page)).tries, 0);
  assert.deepEqual(errors, []);
  await page.close();
});
