import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {chromium} from '../../student-web/node_modules/playwright/index.mjs';

const fixture = process.env.MIRA_FIXED_GAME_TEST_PREVIEW;
const useDraftPatch = process.env.MIRA_FIXED_GAME_TEST_DRAFT === '1';
const patch = new URL('../patches/0308-mira-fixed-game-landscape-fullscreen.patch', import.meta.url);

function draftStyle() {
  const cssHunks = readFileSync(patch, 'utf8').split('diff --git a/app/mira-student-orbit.css b/app/mira-student-orbit.css')[1];
  assert.ok(cssHunks, 'Fullscreen patch must contain the authored CSS');
  return cssHunks.split('\n').filter(line => line.startsWith('+') && !line.startsWith('+++'))
    .map(line => line.slice(1)).join('\n');
}

test('short landscape fullscreen fits a fixed game with all classroom controls reachable', {
  skip: !fixture && 'Set MIRA_FIXED_GAME_TEST_PREVIEW to a staged local classroom with an interactive entry',
}, async () => {
  const url = new URL(fixture);
  assert.ok(['http://localhost:3100', 'http://localhost:3110'].includes(url.origin),
    'Test a managed or isolated local preview');
  assert.equal(url.searchParams.get('mira'), '1');
  assert.equal(url.searchParams.get('textbook'), '1');
  const browser = await chromium.launch({channel: 'chrome'});
  try {
    const context = await browser.newContext({viewport: {width: 640, height: 360}, hasTouch: true});
    let sequence = 0;
    await context.route(url.origin + '/mira/runtime-events', route => {
      if (route.request().method() !== 'GET') {
        sequence = route.request().postDataJSON().sequence;
        return route.fulfill({json: {ok: true, sequence}});
      }
      return route.fulfill({json: {ok: true, schemaVersion: 'mira.openmaic.student-runtime-event-receipt.v1',
        runtimeSessionId: 'fixed-game-layout-test', lastSequence: sequence, nextSequence: sequence + 1, completed: false,
        completionReady: false, answeredQuestionIds: []}});
    });
    const page = await context.newPage();
    await page.goto(url.href);
    const shell = page.locator('[data-mira-playback-shell="storybook"]');
    const start = page.getByRole('button', {name: '开始上课', exact: true});
    await start.tap({timeout: 15000});
    const game = page.locator('iframe[srcdoc*="K.game=function"]:visible');
    await game.waitFor({state: 'visible', timeout: 15000});
    const gameBody = game.contentFrame().locator('body');
    const token = await gameBody.evaluate(node => {
      node.dataset.layoutTestToken = String(Math.random());
      return node.dataset.layoutTestToken;
    });
    if (useDraftPatch) {
      await shell.evaluate(node => node.setAttribute('data-mira-fixed-game-landscape', ''));
      await page.addStyleTag({content: draftStyle()});
    }
    assert.equal(await shell.getAttribute('data-mira-fixed-game-landscape'), '');
    await page.getByRole('button', {name: '全屏', exact: true}).tap();
    await page.waitForFunction(() => document.fullscreenElement);
    const nav = page.locator('[data-mira-presentation-toolbar] [data-mira-chrome="playback-controls"]');
    await nav.waitFor();
    await page.waitForFunction(() => {
      const area = document.querySelector('iframe[srcdoc*="K.game=function"]')?.getBoundingClientRect();
      return area?.width >= 520 && area?.height >= 290;
    }, undefined, {timeout: 6000});
    assert.equal(await gameBody.getAttribute('data-layout-test-token'), token, 'Fullscreen reloaded the game');
    const board = await game.boundingBox();
    const toolbar = await nav.boundingBox();
    assert.ok(toolbar.height >= 48 && toolbar.height <= 52, JSON.stringify(toolbar));
    assert.ok(board.y + board.height <= toolbar.y, 'Toolbar covers the game');
    const controls = await nav.getByRole('button').evaluateAll(elements => elements.filter(element => {
      const rect = element.getBoundingClientRect();
      return rect.width && rect.height && getComputedStyle(element).visibility === 'visible';
    }).map(element => {
      const {x, y, width, height, right, bottom} = element.getBoundingClientRect();
      const hit = document.elementFromPoint(x + width / 2, y + height / 2);
      return {label: element.getAttribute('aria-label') || element.textContent,
        usable: width >= 48 && height >= 48 && x >= 0 && y >= 0 && right <= innerWidth && bottom <= innerHeight
          && element.contains(hit)};
    }));
    assert.ok(controls.length >= 8 && controls.every(item => item.usable), JSON.stringify(controls));
    const dock = page.locator('[data-mira-discussion-rail="dock"]');
    await dock.waitFor();
    const dockBox = await dock.boundingBox();
    assert.ok(dockBox.x >= board.x + board.width, 'Discussion dock covers the game');
    await page.getByRole('button', {name: '退出全屏', exact: true}).tap();
    await page.waitForFunction(() => !document.fullscreenElement);
    assert.equal(await gameBody.getAttribute('data-layout-test-token'), token);
  } finally {
    await browser.close();
  }
});
