import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = path.resolve(import.meta.dirname, '../../../..');
const require = createRequire(path.join(root, 'student-web/package.json'));
const { chromium } = require('playwright');

test('mixed order validates the first event and really removes the outgoing books', async () => {
  const slug = path.basename(path.dirname(import.meta.dirname));
  const work = path.join(root, 'output/courseware-lessons', slug, 'build');
  const draft = JSON.parse(await fs.readFile(path.join(work, 'draft.json'), 'utf8'));
  const scene = draft.body.scenes.find(item => item.outlineId === 'p09');
  const file = path.join(process.env.MIRA_TASK_TMPDIR, 'shelf-order.html');
  const html = scene.content.html.replace(/\/api\/classroom-media\/[^/]+\/media\/([a-z0-9._-]+)/g,
    (_, name) => pathToFileURL(path.join(work, 'media', name)).href);
  await fs.writeFile(file, html, { flag: 'wx' });
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.goto(pathToFileURL(file).href);
    await page.locator('#start-btn').click();
    const select = async change => {
      await page.locator(`.event-choice[data-change="${change}"]`).click();
      await page.locator('#apply-event').click();
    };
    const count = async expected => {
      assert.equal(await page.locator('#shelf-now [data-book-id]').count(), expected);
      assert.equal(await page.locator('#shelf-count').textContent(), String(expected));
    };
    await select(5);
    await count(7);
    await select(-3);
    await count(4);
    await page.locator('#next-round').click();
    await select(2);
    await count(8);
    assert.equal(await page.locator('#event-traces .trace').count(), 0);
    await select(-3);
    await count(5);
    await select(2);
    await count(7);
  } finally {
    await browser.close();
  }
});
