// Runs the catalog's JSON presets through the actual engine and replay button.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { join } = require('node:path');
const [pw, executablePath] = process.argv.slice(2);
const { chromium } = require(join(pw, 'node_modules/playwright-core'));

async function run(browser, {name, html, levels, demoOnce, observation, voice}) {
  const page = await browser.newPage({ viewport: { width: 640, height: 360 }, hasTouch: true });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.evaluate(() => {
      const queue = [];
      let now = 1;
      window.requestAnimationFrame = fn => queue.push(fn);
      window.stepGame = (frames, stop) => {
        for (let i = 0; i < frames; i++) {
          for (const frame of queue.splice(0)) frame(now);
          now += 1000 / 60;
          if (stop && K.game.status().state === stop) return i + 1;
        }
        return null;
      };
    });
    await page.setContent(html);
    assert.deepEqual(errors, [], name + ': build error');
    assert.equal(await page.evaluate(() => K.game.status()?.state), 'ready', name);
    await page.locator('#start-btn').tap();
    if (observation) {
      await checkObservation(page);
      return;
    }
    if (voice) {
      await checkVoiceLead(page);
      return;
    }
    if (name.endsWith('.sortingDepot')) await checkSortingInput(page);
    if (demoOnce) {
      await page.evaluate(() => K.onState({ level: 2 }));
      const demo = await page.evaluate(() => {
        const from = K.log.length;
        K.onState({ demo: true });
        const frames = window.stepGame(1800, 'between');
        window.stepGame(1800); // A successful first action must stay frozen indefinitely.
        const { level, state } = K.game.status();
        return { frames, level, state, progress: K.game.current.data.progress,
          wins: K.log.slice(from).filter(x => x.startsWith('win:')).map(x => +x.split(':')[1]) };
      });
      assert.ok(demo.frames && demo.frames < 1800, name + ': no success within the first 30 s');
      assert.deepEqual({ ...demo, frames: undefined },
        { frames: undefined, level: 1, state: 'between', progress: 1, wins: [1] }, name + ': demo replayed');
      const handoff = await page.evaluate(() => {
        K.onState({ demo: false, level: 1 });
        window.stepGame(1);
        const { auto, level, state, stars } = K.game.status();
        const { total, progress } = K.game.current.data;
        const anchors = [...document.querySelectorAll('.g-anchor')].filter(a => a.getBoundingClientRect().width > 0).length;
        return { auto, level, state, stars, total, progress, anchors };
      });
      assert.deepEqual(handoff, { auto: false, level: 1, state: 'play', stars: [], total: 0, progress: 0, anchors: 3 }, name);
    }
    let from = await page.evaluate(() => {
      K.game.autoplay(true);
      K.onState({ level: 1 });
      return K.log.length;
    });
    for (let pass = 1; pass <= 2; pass++) {
      const result = await page.evaluate(from => {
        window.stepGame(7200, 'done');
        return { status: K.game.status(), wins: K.log.slice(from).filter(s => s.startsWith('win:')),
          errs: K.errs };
      }, from);
      assert.equal(result.status.state, 'done', name + ': pass ' + pass + ' ' + JSON.stringify(result));
      assert.deepEqual(result.wins.map(x => +x.split(':')[1]), Array.from({length: levels}, (_, i) => i + 1), name);
      assert.ok(result.status.stars.every(n => n >= 1 && n <= 3), name);
      assert.deepEqual(result.errs, [], name);
      if (pass === 1) {
        from = await page.evaluate(() => K.log.length);
        await page.locator('#btn-again').tap();
      }
    }
    assert.deepEqual(errors, [], name);
    console.log(name + ': ' + levels + ' levels × 2');
  } finally {
    await page.close();
  }
}

async function checkSortingInput(page) {
  // Move the metal spoon out of the way, then push the wooden spoon toward
  // the metal tray, via a route a child can actually enter with the arrows.
  const press = async direction => {
    await page.keyboard.press(direction);
    await page.evaluate(() => window.stepGame(22));
  };
  const arrows = {U:'ArrowUp',D:'ArrowDown',L:'ArrowLeft',R:'ArrowRight'};
  for (const key of 'URRDDLRUULLDRURDLDRR') await press(arrows[key]);
  const state = await page.evaluate(() => {
    const { w, progress, total } = K.game.current.data;
    return { p:w.state.p, positions:w.state.items, progress, total, help:w.help, misses:K.game.status().misses };
  });
  assert.deepEqual(state, {p:27, positions:[28,26], progress:0, total:0, help:true, misses:2},
    'same shape but wrong material must not score or occupy the tray');
  await page.locator('[data-arc-input="action"]').tap();
  await page.evaluate(() => window.stepGame(22));
  assert.equal(await page.evaluate(() => K.game.current.data.w.state.p), 19, 'touch undo restores the prior square');
}

async function checkObservation(page) {
  const read = () => page.evaluate(() => K.game.observation());
  assert.equal(await read(), null);
  const tap = async () => {
    await page.keyboard.press('Space');
    await page.evaluate(() => window.stepGame(96));
  };
  // In the fixture the first press is a partial trial; the second resolves it.
  for (let i = 1; i <= 3; i++) {
    await tap();
    assert.equal(await read(), null);
    await tap();
    if (i < 3) await page.locator('#g-next').tap();
  }
  const expected = {schemaVersion:'mira.game.observation.v1',sceneId:'trial-fixture-42',kind:'simulation',
    levels:Array.from({length:3},(_,i)=>({level:i+1,trials:[
      {trialId:'before',top:'overhang',side:'raised'}, {trialId:'after',top:'covered',side:'flat'}]}))};
  assert.deepEqual(await read(), expected);
  const log = await page.evaluate(() => {
    K.game.observation().levels[0].trials[0].top = 'tampered';
    return {signals: window.observationSignals, accepted: window.accepted};
  });
  assert.deepEqual(log, {signals:1, accepted:Array(3).fill([false,true,false,true]).flat()});
  assert.deepEqual(await read(), expected, 'read returns a detached copy');
  await page.locator('#btn-again').tap();
  assert.equal(await read(), null);
  await page.evaluate(() => {
    K.onState({ demo: true });
    window.stepGame(200);
  });
  assert.equal(await read(), null, 'demo never exports');
  await page.evaluate(() => {
    K.game.autoplay(true);
    K.onState({ level: 1 });
    window.stepGame(1600, 'done');
  });
  assert.equal(await page.evaluate(() => K.game.status().state), 'done');
  assert.equal(await read(), null, 'autopilot never exports');
  assert.equal(await page.evaluate(() => window.observationSignals), 1);
  assert.deepEqual(await page.evaluate(() => K.errs), []);
  console.log('Typed observations: normal input, isolation, replay, demo and autopilot pass');
}

async function checkVoiceLead(page) {
  const press = async () => {
    await page.keyboard.press('Space');
    await page.evaluate(() => window.stepGame(80));
  };
  const progress = () => page.evaluate(() => K.game.current.data.progress);
  await press();
  assert.equal(await progress(), 0, 'goal narration holds the timer and inputs');
  await page.evaluate(() => window.cueState('goal1', 'ready'));
  await press();
  assert.equal(await progress(), 1);
  await press();
  assert.equal(await progress(), 2);
  assert.equal(await page.evaluate(() => K.game.status().state), 'play', 'do not cut off praise to advance');
  await page.evaluate(() => { window.cueState('praise', 'ready'); window.stepGame(100); });
  await page.locator('#g-next').tap();
  await page.evaluate(() => window.stepGame(660));
  await press();
  assert.equal(await progress(), 1, 'a missing audio event cannot block play indefinitely');
  assert.deepEqual(await page.evaluate(() => K.errs), []);
  console.log('Voice lead: goal, praise and missing audio recovery pass');
}

(async () => {
  const fixtures = JSON.parse(fs.readFileSync(0, 'utf8'));
  const browser = await chromium.launch({ executablePath });
  try {
    for (const fixture of fixtures) await run(browser, fixture);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
