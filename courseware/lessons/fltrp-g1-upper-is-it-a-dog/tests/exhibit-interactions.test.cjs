const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { mkdirSync, readFileSync, writeFileSync } = require('node:fs');
const { basename, resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
const { after, before, test } = require('node:test');
const { chromium } = require('../../../../student-web/node_modules/playwright-core');

const repository = resolve(__dirname, '../../../..');
const chrome = process.env.MIRA_CHROME_BIN ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const formalWork = process.env.MIRA_FORMAL_WORK;
const captureDir = process.env.MIRA_G6_CAPTURE_DIR;
const taskScratch = process.env.MIRA_TASK_TMPDIR;
assert.equal(Boolean(formalWork), Boolean(captureDir));
if (formalWork) assert.ok(taskScratch, 'Run formal captures under tools/task_tmp.py');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const bodyBytes = formalWork && readFileSync(resolve(formalWork, 'body.json'));
const capture = { bodyFileSha256: bodyBytes && digest(bodyBytes), viewport: '640x360', states: [], imageSha256: {} };
let browser;

before(async () => {
  if (formalWork) mkdirSync(captureDir);
  browser = await chromium.launch({ executablePath: chrome, headless: true,
    args: ['--allow-file-access-from-files'] });
});

after(async () => {
  await browser?.close();
  if (formalWork) {
    assert.equal(capture.states.length, 3);
    capture.ranAt = new Date().toISOString();
    capture.network = 'HTTP and HTTPS blocked; exact local release media';
    writeFileSync(resolve(captureDir, 'capture-receipt.json'), JSON.stringify(capture, null, 2) + '\n', {flag:'wx'});
  }
});

function fixtureHtml(title) {
  const readPage = [
    'from pathlib import Path',
    'import sys',
    'from courseware.kit.page import page',
    'source = Path("courseware/lessons/fltrp-g1-upper-is-it-a-dog/pages")',
    'read = lambda ext: (source / ("exhibit." + ext)).read_text(encoding="utf-8")',
    'print(page(sys.argv[1], read("html"), read("css"), read("js")))',
  ].join('\n');
  return execFileSync('python3', ['-B', '-c', readPage, title], { cwd: repository, encoding: 'utf8' })
    .replace(/__IMG:([a-z0-9-]+)__/g, (_, key) => {
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><title>' +
        key + '</title><rect width="160" height="120" fill="#ddcfaa"/></svg>';
      return 'data:image/svg+xml;base64,' + Buffer.from(svg).toString('base64');
    })
    .replace(/__CLIP:([a-z0-9-]+)__/g, '/fixture-audio/$1.wav')
    .replace(/\/api\/classroom-media\/__STAGE__\/media\/tts-([a-z0-9-]+)-[a-f0-9]{64}\.wav/g,
      '/fixture-audio/$1.wav');
}

async function start(t, title) {
  const viewport = { width: 640, height: 360 };
  const context = await browser.newContext({ viewport, offline: true });
  t.after(() => context.close());
  const page = await context.newPage();
  if (formalWork) {
    const scene = JSON.parse(bodyBytes).scenes.find(item => item.title === title && item.type === 'interactive');
    assert.ok(scene);
    const sceneKey = scene.outlineId;
    page.sceneKey = sceneKey;
    const pageFile = resolve(taskScratch, sceneKey + '.html');
    const html = scene.content.html.replace(/\/api\/classroom-media\/[a-z0-9_-]+\/media\/([a-z0-9.-]+)/gi, (_, name) => {
      const path = resolve(formalWork, 'media', name);
      assert.equal(digest(readFileSync(path)), name.match(/([a-f0-9]{64})\.(?:png|wav)$/)?.[1]);
      return pathToFileURL(path).href;
    });
    await context.route(/^https?:/, route => route.abort());
    await page.addInitScript(() => {
      const RealAudio = window.Audio;
      window.fixtureAudioFailed = false;
      window.fixtureAudioSources = [];
      window.g6AudioEnded = [];
      window.Audio = function (src) {
        window.fixtureAudioSources.push(src);
        const audio = new RealAudio(window.fixtureAudioFailed ? 'missing-on-purpose.wav' : src);
        audio.addEventListener('ended', () => window.g6AudioEnded.push({ src, duration: audio.duration }));
        return audio;
      };
    });
    writeFileSync(pageFile, html, {flag:'wx'});
    await page.goto(pathToFileURL(pageFile).href);
    const startPicture = page.locator('#ready .pic');
    assert.equal(await startPicture.evaluate(element => getComputedStyle(element).objectFit), 'contain');
    await screen(page, 'initial');
    await page.locator('#start-btn').click();
    await page.evaluate(() => window.postMessage({type:'SET_WIDGET_STATE', state:{mode:'demo',round:0,step:'answer'}}, '*'));
    await page.locator('#exhibit-target img').waitFor();
    assert.equal(await page.locator('#star-n').textContent(), '0');
    assert.equal(await page.locator('#match-right').isDisabled(), true);
    await screen(page, 'teacher-demo');
    await page.evaluate(() => window.postMessage({type:'SET_WIDGET_STATE', state:{mode:'practice'}}, '*'));
    await page.locator('#listen-cue:enabled').waitFor();
    await page.addStyleTag({content: '#activity-heading,.exhibit-workspace h3,#say,#tip,#hud .chip{visibility:hidden!important}'});
    return page;
  }
  await page.setContent(fixtureHtml(title));
  await page.evaluate(() => {
    window.fixtureAudioFailed = false;
    window.fixtureAudioSources = [];
    window.Audio = class {
      constructor(src) { this.src = src; }
      play() {
        window.fixtureAudioSources.push(this.src);
        if (window.fixtureAudioFailed) return Promise.reject(new Error('fixture failure'));
        this.timer = setTimeout(() => this.onended?.(), 300);
        return Promise.resolve();
      }
      pause() { clearTimeout(this.timer); }
    };
  });
  await page.locator('#start-btn').click();
  return page;
}

async function screen(page, state) {
  if (!formalWork) return;
  const images = page.locator('img:visible');
  await Promise.all((await images.all()).map(image => image.evaluate(element => element.decode())));
  const name = `${page.sceneKey}-${state}.png`;
  const png = await page.screenshot({path:resolve(captureDir, name), animations:'disabled'});
  capture.imageSha256[name] = digest(png);
}

async function hear(page, next) {
  const cue = page.locator('#listen-cue');
  await cue.click();
  assert.equal(await cue.getAttribute('aria-busy'), 'true');
  assert.equal(await cue.isDisabled(), true);
  await page.locator(next + ':enabled').waitFor();
}

async function finishAndReset(page) {
  await page.locator('#finish:not(.gone)').waitFor();
  assert.equal(await page.locator('#star-n').textContent(), '2');
  assert.equal(await page.locator('#evidence-photos img').count(), 2);
  await page.locator('#btn-again').click();
  assert.equal(await page.locator('#star-n').textContent(), '0');
  assert.equal(await page.locator('#evidence-photos img').count(), 0);
  assert.equal(await page.locator('#exhibit-target').isDisabled(), true);
  assert.deepEqual(await page.evaluate(() => window.K.errs), []);
  if (formalWork) {
    const ended = await page.evaluate(() => window.g6AudioEnded);
    assert.equal(ended.length, 2);
    assert.ok(ended.every(item => Number.isFinite(item.duration) && item.duration >= 0.3));
    capture.states.push({scene:page.sceneKey, passed:true, maskedCopy:true, reset:true,
      realLocalMedia:ended.map(item => ({file:basename(item.src), duration:item.duration}))});
  }
}

test('a failed cue remains retryable and a guess must be revealed before the response', async t => {
  const page = await start(t, '听猜测，再揭图');
  const cue = page.locator('#listen-cue');
  const box = await cue.boundingBox();
  assert.ok(box.width >= 44 && box.height >= 44);
  await page.evaluate(() => { window.fixtureAudioFailed = true; });
  await cue.click();
  await page.locator('#say.no').waitFor({state:'attached'});
  assert.equal(await page.locator('#exhibit-target').isDisabled(), true);
  await page.evaluate(() => { window.fixtureAudioFailed = false; });
  await hear(page, '#exhibit-target');
  assert.equal(await page.locator('#match-right').isDisabled(), true);
  await page.locator('#exhibit-target').click();
  await page.locator('#match-left').click();
  assert.equal(await page.locator('#match-left.is-wrong').count(), 1);
  assert.equal(await page.locator('#evidence-photos img').count(), 0);
  await screen(page, 'masked-wrong');
  await page.locator('#match-right').click();
  await screen(page, 'masked-correct');
  await hear(page, '#exhibit-target');
  await page.locator('#exhibit-target').click();
  await page.locator('#match-left').click();
  await finishAndReset(page);
  const sources = (await page.evaluate(() => window.fixtureAudioSources)).map(item => basename(item));
  assert.equal(sources.length, 3);
  assert.equal(sources[0], sources[1]);
  assert.match(sources[0], formalWork ? /^tts-hear-and-reveal-11-[a-f0-9]{64}\.wav$/ : /^hear-and-reveal-11\.wav$/);
  assert.match(sources[2], formalWork ? /^tts-hear-and-reveal-12-[a-f0-9]{64}\.wav$/ : /^hear-and-reveal-12\.wav$/);
});

async function dragTo(page, target) {
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#exhibit-target')).transform === 'none');
  const source = await page.locator('#exhibit-target').boundingBox();
  const dest = await page.locator(target).boundingBox();
  await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
  await page.mouse.down();
  await page.mouse.move(dest.x + dest.width / 2, dest.y + dest.height / 2, { steps: 10 });
  await page.mouse.up();
}

test('a dog-shaped kite is sorted by real drag and the next photo can be sorted with a keyboard', async t => {
  const page = await start(t, '把真实照片放上展台');
  await hear(page, '#exhibit-target');
  await dragTo(page, '#match-right');
  assert.equal(await page.locator('#match-right.is-wrong').count(), 1);
  await screen(page, 'masked-wrong');
  await dragTo(page, '#match-left');
  await page.locator('#evidence-photos img').waitFor();
  await screen(page, 'masked-correct');
  await hear(page, '#exhibit-target');
  await page.locator('#exhibit-target').press('Enter');
  assert.equal(await page.locator('#exhibit-target').getAttribute('aria-pressed'), 'true');
  await page.locator('#match-right').press('Enter');
  await finishAndReset(page);
});

test('the role page moves a guessed object before opening the photo and responds in two turns', async t => {
  const page = await start(t, '轮流问，轮流答');
  await page.evaluate(() => window.postMessage({ type:'SET_WIDGET_STATE', state:{ mode:'demo', round:0, step:'answer' } }, '*'));
  await page.locator('#exhibit-target img').waitFor();
  assert.equal(await page.locator('#star-n').textContent(), '0');
  assert.equal(await page.locator('#match-right').isDisabled(), true);
  await page.evaluate(() => window.postMessage({ type:'SET_WIDGET_STATE', state:{ mode:'practice' } }, '*'));
  await hear(page, '#match-left');
  assert.equal(await page.locator('#exhibit-target').isDisabled(), true);
  await page.locator('#match-left').click();
  assert.equal(await page.locator('#match-left.is-wrong').count(), 1);
  await screen(page, 'masked-wrong');
  await page.locator('#match-right').click();
  await page.locator('#guess-photo img').waitFor();
  await page.locator('#exhibit-target').click();
  await page.locator('#match-right').click();
  await page.locator('#evidence-photos img').waitFor();
  await screen(page, 'masked-correct');
  await hear(page, '#match-left');
  await page.locator('#match-left').click();
  await page.locator('#exhibit-target').click();
  await page.locator('#match-left').click();
  await finishAndReset(page);
});
