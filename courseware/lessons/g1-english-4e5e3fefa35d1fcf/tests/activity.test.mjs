import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

// Real pointer interactions test the wrong branch, teacher state, object movement,
// complete passage, and replay. Curriculum answers are independently checked by G7.
const [bodyPath, mediaPath] = process.argv.slice(2);
const allowAudioPending = process.argv.includes('--allow-audio-pending');
const captureIndex = process.argv.indexOf('--capture-dir');
const captureDir = captureIndex < 0 ? undefined : process.argv[captureIndex + 1];
assert(bodyPath && mediaPath, 'Usage: node activity.test.mjs <body.json> <media-dir>');
assert(process.env.MIRA_TASK_TMPDIR, 'Run through tools/task_tmp.py');
const require = createRequire(path.resolve('student-web/package.json'));
const { chromium } = require('playwright-core');
const loaded = JSON.parse(await fs.readFile(bodyPath, 'utf8'));
const body = loaded.body || loaded;
if (captureDir) await fs.mkdir(captureDir, { recursive: true });
const browser = await chromium.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--allow-file-access-from-files', '--autoplay-policy=no-user-gesture-required'],
});
let completed = 0;
try {
  for (const scene of body.scenes.filter(s => s.type === 'interactive')) {
    const errors = [];
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    page.on('pageerror', error => errors.push(error.message));
    const content = scene.content.html.replace(
      /\/api\/classroom-media\/[A-Za-z0-9_-]+\/media\/([A-Za-z0-9_.-]+)/g,
      (_, name) => pathToFileURL(path.resolve(mediaPath, name)).href,
    );
    assert(allowAudioPending || !/__VOICE:[a-z0-9-]+__/.test(content), `${scene.outlineId}: unresolved recorded audio`);
    const file = path.join(process.env.MIRA_TASK_TMPDIR, `${scene.outlineId}.html`);
    await fs.writeFile(file, content);
    await page.goto(pathToFileURL(file).href);
    const cfg = await page.locator('#lesson-data').evaluate(e => JSON.parse(e.textContent));
    const capture = name => captureDir && page.screenshot({
      path: path.join(captureDir, `${scene.outlineId}-${name}.png`), animations: 'disabled',
    });
    await page.locator('#start-btn').click();
    await page.waitForTimeout(180);
    await capture('initial');
    const first = cfg.trials[0];
    const wrong = first.choices.find(key => key !== first.key);
    await page.locator(`#card-${wrong}`).click();
    assert(await page.locator('#result-photo').isHidden(), `${scene.outlineId}: first miss exposes result`);
    assert.equal(await page.locator('.answer-hint').count(), 0, `${scene.outlineId}: first miss exposes answer`);
    await capture('first-wrong');
    await page.reload();
    const demonstration = scene.actions.find(a => a.type === 'widget_setState' && a.state.demo).state.demo;
    await page.evaluate(key => window.postMessage({ type: 'SET_WIDGET_STATE', state: { demo: key } }, '*'), demonstration);
    await page.waitForTimeout(80);
    assert(await page.locator('#result-photo').isVisible(), `${scene.outlineId}: teacher did not operate picture`);
    assert.equal(await page.locator('#result-photo').getAttribute('alt'), demonstration, `${scene.outlineId}: teacher shows the wrong person`);
    if (scene.outlineId === 'p07') {
      assert.equal(await page.locator('#photo-target').getAttribute('data-job'), 'school', 'teacher demonstration must be in school');
    }
    await capture('teacher-demo');
    await page.evaluate(() => window.postMessage({ type: 'SET_WIDGET_STATE', state: { demo: null, handoff: true } }, '*'));
    await page.waitForTimeout(80);
    for (let pass = 0; pass < 2; pass++) {
      if (pass === 1) {
        await page.addStyleTag({ content: '#target-word, #say, #hud .chip { color: transparent !important; }' });
        await page.locator('#prompt-audio').click();
      }
      for (let i = 0; i < cfg.trials.length; i++) {
        const card = page.locator(`#card-${cfg.trials[i].key}`);
        if (i === 0) await card.dragTo(page.locator('#photo-target'));
        else await card.click();
        assert(await page.locator('#result-photo').isVisible(), `${scene.outlineId}: photo not moved`);
        assert(await card.evaluate(e => e.classList.contains('placed')), `${scene.outlineId}: source not moved`);
        if (pass === 0 && i === 0) await capture('correct');
        await page.waitForTimeout(1050);
      }
      assert(await page.locator('#finish').isVisible(), `${scene.outlineId}: cannot complete`);
      await page.locator('#btn-again').click();
      assert.equal(await page.locator('#photo-track img').count(), 0, `${scene.outlineId}: replay leaves old photos`);
      assert(await page.locator('#result-photo').isHidden(), `${scene.outlineId}: replay leaves result`);
      assert.equal(await page.locator('#star-n').textContent(), '0', `${scene.outlineId}: replay leaves stars`);
    }
    assert.deepEqual(errors, [], `${scene.outlineId}: browser errors`);
    console.log(`${scene.outlineId}: first wrong, teacher demonstration, drag, replay, and text-covered pass`);
    completed++;
    await page.close();
  }
  if (!allowAudioPending) {
    const voiceFiles = body.scenes.flatMap(scene => scene.actions)
      .filter(action => action.type === 'speech')
      .map(action => ({ id: action.id, url: pathToFileURL(path.resolve(mediaPath, action.audioUrl.split('/').at(-1))).href }));
    const page = await browser.newPage();
    await page.goto(pathToFileURL(path.join(process.env.MIRA_TASK_TMPDIR, 'p02.html')).href);
    const durationChecks = await page.evaluate(async files => {
      async function checkAudio(file, playThrough) {
        const audio = new Audio(file.url);
        await new Promise((resolve, reject) => {
          if (audio.readyState >= 1) return resolve();
          const timer = setTimeout(() => reject(new Error(`metadata timeout ${file.id}`)), 4000);
          audio.addEventListener('loadedmetadata', () => { clearTimeout(timer); resolve(); }, { once: true });
          audio.addEventListener('error', () => { clearTimeout(timer); reject(new Error(`audio error ${file.id}`)); }, { once: true });
        });
        const duration = audio.duration;
        if (playThrough) {
          await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error(`playback timeout ${file.id}`)), 12000);
            audio.addEventListener('ended', () => { clearTimeout(timer); resolve(); }, { once: true });
            audio.play().catch(error => { clearTimeout(timer); reject(error); });
          });
        }
        return { id: file.id, duration };
      }
      const checked = [];
      for (const file of files) checked.push(await checkAudio(file, false));
      for (const id of ['p01-2', 'p07-10', 'quiz_speech_6']) {
        await checkAudio(files.find(file => file.id === id), true);
      }
      return checked;
    }, voiceFiles);
    assert.equal(durationChecks.length, 100);
    assert(durationChecks.every(item => Number.isFinite(item.duration) && item.duration > 0.1 && item.duration < 15),
      `Unexpected Chrome audio duration: ${JSON.stringify(durationChecks.filter(item => !(item.duration > 0.1 && item.duration < 15)))}`);
    console.log('Chrome read 100 recorded speech durations and completed playback of three representative clips');
    await page.close();
  }
} finally {
  await browser.close();
}
assert.equal(completed, 4);
console.log('4 interactive regression checks passed');
