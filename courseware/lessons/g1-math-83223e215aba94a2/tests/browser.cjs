// Regression of the lesson's real decisions, first-miss behavior, demonstration and replay.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(path.resolve(__dirname, '../../../../student-web/node_modules/playwright-core'));
const args = process.argv.slice(2);
const directory = args[args.indexOf('--dir') + 1];
const shots = args.includes('--screenshots') ? args[args.indexOf('--screenshots') + 1] : null;
if (!directory || directory.startsWith('--')) throw new Error('--dir is required');
if (shots) fs.mkdirSync(shots, {recursive: true});
const wait = page => page.waitForTimeout(700);
(async () => {
  const browser = await chromium.launch({executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--allow-file-access-from-files']});
  const page = await browser.newPage({viewport: {width: 1280, height: 720}});
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  const shot = async (key, state) => {
    if(shots) {
      await page.waitForTimeout(220); // Let the 150 ms position animation settle before judging its destination.
      await page.screenshot({path: path.join(shots, key + '-' + state + '.png')});
    }
  };
  const state = () => page.evaluate(() => K.lessonState());
  const phase = value => page.evaluate(phase => K.onState({phase}), value);
  const start = async key => {
    await page.goto(pathToFileURL(path.join(directory, key + '.html')).href);
    await page.locator('#start-btn').click();
    const escaped = await page.evaluate(() => {
      const play = document.querySelector('#play').getBoundingClientRect();
      return ['#count-stage','#stamp-stage','#score-stage','#route-board'].flatMap(selector => {
        const el = document.querySelector(selector); if(!el)return[];
        const rect=el.getBoundingClientRect();
        return rect.top<play.top||rect.bottom>play.bottom||rect.left<play.left||rect.right>play.right?[selector]:[];
      });
    });
    assert.deepEqual(escaped, [], 'learning board must remain above the narration bar');
    await shot(key, 'initial');
  };
  const clickAll = selector => page.locator(selector).evaluateAll(nodes => nodes.forEach(n => n.click()));
  await start('p02');
  await phase('demo'); await phase('marked'); await shot('p02', 'teacher'); await phase('play');
  await clickAll('.pot'); await page.getByRole('button', {name: '记录数字1', exact: true}).click();
  assert.equal((await state()).wrong, 1); assert.equal((await state()).marked, 3); await shot('p02', 'wrong');
  await page.getByRole('button', {name: '记录数字3', exact: true}).click(); await shot('p02', 'correct'); await wait(page);
  await clickAll('.pot'); await page.getByRole('button', {name: '记录数字5', exact: true}).click(); await wait(page);
  await page.locator('#btn-again').click(); assert.equal((await state()).marked, 0); assert.equal((await state()).level, 0);
  await start('p05');
  await phase('demo'); await phase('print');
  const targetBox = await page.locator('#stamp-target svg').boundingBox();
  const printBox = await page.locator('#stamp-result svg').boundingBox();
  assert.deepEqual(printBox, targetBox, 'impression and target must share exact geometry');
  await shot('p05', 'teacher'); await phase('play');
  await page.getByRole('button', {name: '积木面 circle', exact: true}).click();
  assert.equal((await state()).wrong, 1); assert.equal(await page.locator('#stamp-result svg').count(), 0); await shot('p05', 'wrong');
  for (const k of ['square', 'triangle', 'rectangle']) {await page.getByRole('button', {name: '积木面 ' + k, exact: true}).click(); if(k==='square')await shot('p05', 'correct');await wait(page);}
  await page.locator('#btn-again').click(); assert.equal((await state()).target, 'square'); assert.equal(await page.locator('#stamp-result svg').count(), 0);
  await start('p07');
  await phase('demo'); await phase('record'); await shot('p07', 'teacher'); await phase('play');
  await clickAll('.collect'); await page.getByRole('button', {name: '记录总分3', exact: true}).click();
  assert.equal((await state()).wrong, 1); assert.equal((await state()).total, 4); await shot('p07', 'wrong');
  await page.getByRole('button', {name: '记录总分4', exact: true}).click(); await shot('p07', 'correct'); await wait(page);
  await clickAll('.collect'); await page.getByRole('button', {name: '记录总分6', exact: true}).click(); await wait(page);
  await page.locator('#btn-again').click(); assert.equal((await state()).recorded, 0); assert.equal((await state()).total, 0);
  await start('p10');
  await phase('demo'); await phase('step'); await phase('step'); await phase('step'); await shot('p10', 'teacher'); await phase('play');
  await page.locator('[data-dir="left"]').click(); assert.deepEqual((await state()).pos, [3, 0]); assert.equal((await state()).wrong, 1); await shot('p10', 'wrong');
  for (const d of ['up', 'up', 'right']) await page.locator('[data-dir="' + d + '"]').click();
  assert.deepEqual((await state()).pos, [1, 1]); await shot('p10', 'correct'); await wait(page);
  for (const d of ['right', 'right', 'up', 'up']) await page.locator('[data-dir="' + d + '"]').click();
  await wait(page); await page.locator('#btn-again').click(); assert.deepEqual((await state()).pos, [3, 0]); assert.equal((await state()).index, 0);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log('4 interactive regressions passed: first miss, teacher example, correct path, finish and replay; no page errors.');
})().catch(e => {console.error(e); process.exitCode=1;});
