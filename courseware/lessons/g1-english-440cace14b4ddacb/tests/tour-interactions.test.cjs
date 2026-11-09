const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { resolve } = require('node:path');
const { after, before, test } = require('node:test');
const { chromium } = require('../../../../student-web/node_modules/playwright-core');

const repo = resolve(__dirname, '../../../..');
const chrome = process.env.MIRA_CHROME_BIN ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
function fixtureImage(key) {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64"><title>' + key +
    '</title><rect width="96" height="64" fill="#cad8b0"/></svg>';
  return 'data:image/svg+xml;base64,' + Buffer.from(svg).toString('base64');
}

let browser;
before(async () => {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
});
after(async () => {
  await browser?.close();
});

function sourceHtml(name) {
  const python = [
    'from pathlib import Path',
    'import sys',
    'from courseware.kit.page import page',
    'src = Path("courseware/lessons/g1-english-440cace14b4ddacb/pages")',
    'name = sys.argv[1]',
    'read = lambda ext: (src / (name + "." + ext)).read_text(encoding="utf-8")',
    'print(page(name, read("html"), read("css"), read("js")))',
  ].join('\n');
  return execFileSync('python3', ['-B', '-c', python, name], { cwd: repo, encoding: 'utf8' })
    .replace(/__IMG:([a-z0-9-]+)__/g, (_, key) => fixtureImage(key))
    .replace(/\/api\/classroom-media\/__STAGE__\/media\/tts-([a-z0-9-]+)-[a-f0-9]{64}\.wav/g,
      '/fixture-audio/$1.wav');
}

async function openGame(t, key, viewport = { width: 1280, height: 720 }) {
  const context = await browser.newContext({ viewport, offline: true });
  t.after(() => context.close());
  const page = await context.newPage();
  await page.setContent(sourceHtml(key), { waitUntil: 'load' });
  await page.evaluate(() => {
    window.fixtureAudioHistory = [];
    window.fixtureAudioFails = false;
    window.fixtureCueMs = 25;
    window.Audio = class {
      constructor(src) { this.src = src; }
      play() {
        window.fixtureAudioHistory.push(this.src);
        if (window.fixtureAudioFails) return Promise.reject(new Error('fixture audio failed'));
        this.timer = setTimeout(() => this.onended?.(), window.fixtureCueMs);
        return Promise.resolve();
      }
      pause() { clearTimeout(this.timer); }
    };
  });
  await page.locator('#start-btn').click();
  return page;
}

async function listen(page, option) {
  await page.locator('#tour-listen').click();
  await page.locator(option + ':enabled').waitFor();
}

async function waitForFinish(page) {
  await page.locator('#finish:not(.gone)').waitFor();
  assert.equal(await page.locator('#star-n').textContent(), '2');
}

async function assertReset(page, slots) {
  await page.locator('#btn-again').click();
  await page.locator('#finish.gone').waitFor({ state: 'attached' });
  assert.equal(await page.locator('#star-n').textContent(), '0');
  assert.equal(await page.locator(slots).count(), 0);
  assert.equal(await page.locator('#tour-listen').isEnabled(), true);
  assert.equal(await page.evaluate(() => window.K.errs.length), 0);
}

test('place matching requires sound, allows a retry, and resets both photos', async t => {
  const page = await openGame(t, 'find-places');
  assert.equal(await page.locator('#find-school').isDisabled(), true);
  await page.evaluate(() => { window.fixtureAudioFails = true; });
  await page.locator('#tour-listen').click();
  await page.locator('#say.no').waitFor();
  assert.equal(await page.locator('#find-school').isDisabled(), true);
  await page.evaluate(() => {
    window.fixtureAudioFails = false;
    window.fixtureCueMs = 500;
  });
  const replay = page.locator('#tour-listen');
  await replay.click();
  assert.equal(await replay.isDisabled(), true);
  assert.equal(await replay.getAttribute('aria-busy'), 'true');
  await page.locator('#find-school:enabled').waitFor();
  assert.equal(await replay.isEnabled(), true);
  await page.evaluate(() => { window.fixtureCueMs = 25; });
  await page.locator('#find-school').click();
  assert.equal(await page.locator('#star-n').textContent(), '0');
  assert.equal(await page.locator('.tour-gallery img').count(), 0);
  assert.equal(await page.locator('#find-classroom.correct').count(), 0);
  await page.locator('#find-classroom').click();
  await page.locator('.tour-gallery img').first().waitFor();
  await listen(page, '#find-school');
  await page.locator('#find-school').click();
  await waitForFinish(page);
  assert.equal(await page.locator('.tour-gallery img').count(), 2);
  assert.deepEqual(await page.evaluate(() => window.fixtureAudioHistory), [
    '/fixture-audio/find-places-11.wav',
    '/fixture-audio/find-places-11.wav',
    '/fixture-audio/find-places-12.wav',
  ]);
  await assertReset(page, '.tour-gallery img');
});

async function movePhoto(page, target) {
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#photo-card')).transform === 'none');
  const origin = await page.locator('#photo-card').boundingBox();
  const dest = await page.locator(target).boundingBox();
  await page.mouse.move(origin.x + origin.width / 2, origin.y + origin.height / 2);
  await page.mouse.down();
  await page.mouse.move(dest.x + dest.width / 2, dest.y + dest.height / 2, { steps: 10 });
  await page.mouse.up();
}

test('my and our classify the same photo through drag and keyboard selection', async t => {
  const page = await openGame(t, 'place-photos', { width: 640, height: 360 });
  const listenBox = await page.locator('#tour-listen').boundingBox();
  assert.ok(listenBox.width >= 44 && listenBox.height >= 44);
  await listen(page, '#photo-card');
  const firstPhoto = await page.locator('#photo-card img').getAttribute('src');
  await movePhoto(page, '#photo-group');
  assert.equal(await page.locator('#photo-group.wrong').count(), 1);
  assert.equal(await page.locator('.photo-slot img').count(), 0);
  assert.equal(await page.locator('#star-n').textContent(), '0');
  await movePhoto(page, '#photo-one');
  await page.locator('#photo-one .photo-slot img').waitFor();
  await listen(page, '#photo-card');
  assert.equal(await page.locator('#photo-card img').getAttribute('src'), firstPhoto);
  await page.locator('#photo-card').press('Enter');
  await page.locator('#photo-group').click();
  await waitForFinish(page);
  assert.equal(await page.locator('#photo-group .photo-slot img').count(), 1);
  await assertReset(page, '.photo-slot img');
});

test('seat pieces move into the result area and a demo leaves no stars', async t => {
  const page = await openGame(t, 'build-seat', { width: 1000, height: 563 });
  await page.evaluate(() => window.postMessage({
    type: 'SET_WIDGET_STATE', state: { mode: 'demo', choice: 'desk' },
  }, '*'));
  await page.locator('.tour-gallery img').waitFor();
  assert.equal(await page.locator('#star-n').textContent(), '0');
  assert.equal(await page.locator('#seat-desk').isDisabled(), true);
  await page.evaluate(() => window.postMessage({
    type: 'SET_WIDGET_STATE', state: { mode: 'practice' },
  }, '*'));
  await listen(page, '#seat-chair');
  await page.locator('#seat-chair').click();
  await page.locator('.tour-gallery img[alt="学生椅子"]').waitFor();
  await listen(page, '#seat-desk');
  await page.locator('#seat-desk').click();
  await waitForFinish(page);
  assert.equal(await page.locator('.tour-gallery img[alt="学生课桌"]').count(), 1);
  await assertReset(page, '.tour-gallery img');
});

test('guest route changes from meeting the teacher to greeting and can be replayed', async t => {
  const page = await openGame(t, 'welcome-guest');
  await listen(page, '#guest-person');
  await page.locator('#guest-action').click();
  assert.equal(await page.locator('#star-n').textContent(), '0');
  await page.locator('#guest-person').click();
  await page.locator('.tour-gallery img[alt="给学生上课的老师"]').waitFor();
  await listen(page, '#guest-action');
  await page.locator('#guest-action').click();
  await waitForFinish(page);
  await page.locator('.tour-gallery img[alt="客人与老师面对面问候"]').waitFor();
  await page.locator('#btn-again').click();
  assert.equal(await page.locator('#star-n').textContent(), '0');
  assert.equal(await page.locator('.tour-gallery img').count(), 1);
  assert.equal(await page.evaluate(() => window.K.errs.length), 0);
});
