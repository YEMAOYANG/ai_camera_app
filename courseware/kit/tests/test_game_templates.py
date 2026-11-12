"""Exercise the shipped game templates in Chrome with the production engine."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.kit import game_templates, page
from courseware.tools import autoplay


ART = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2240%22 height=%2240%22%3E%3Ccircle cx=%2220%22 cy=%2220%22 r=%2218%22 fill=%22green%22/%3E%3C/svg%3E'
PICTURE = {'image': ART, 'fallback': {'count': 3}}
NUMBER_GROUPS = {'groups': [{'count': 3, 'color': '#E8934B'}, {'count': 4, 'color': '#378AD1'}]}


def round_spec(goal, **props):
    return {'goal': goal, 'hint': '先看看每一组。', 'hint2': '从左往右想一想。', **props}


def levels(*rounds):
    return [{'name': f'任务 {i}', 'rounds': [r]} for i, r in enumerate(rounds, 1)]


TEMPLATES = {
    'runner': levels(
        round_spec({'count': 3}, collect=3, track=[{'value': 3, 'airborne': True}, {'value': 2}, {'value': 4}]),
        round_spec({'count': 7}, collect=7, track=[{'value': 3}, {'value': 6}, {'value': 4, 'airborne': True}])),
    'lily': levels(
        round_spec(3, options=[4, 2], answer=0),
        round_spec(5, options=[3, 4, 6], answer=1, **{'from': 6})),
    'ring': levels(
        round_spec(2, targets=[PICTURE, PICTURE, PICTURE], rings=2),
        round_spec(3, targets=[PICTURE] * 10, rings=3, matches=[2, 5, 9])),
    'crane': levels(
        round_spec(1, cars=list(range(1, 11)), cargo=PICTURE, drop=[0]),
        round_spec(10, cars=list(range(1, 11)), cargo=PICTURE, drop=[0, 9], engine='right')),
    'parachute': levels(
        round_spec(PICTURE, options=[2, 3], answer=1),
        round_spec({'grid': {'filled': 6, 'total': 10, 'columns': 5}}, options=[4, 5, 6, 7], answer=0)),
    'trace': levels(
        round_spec(1, strokes=[[[615, 321], [615, 561]]], gridBox=[640, 459, 420]),
        round_spec(2, strokes=[[[640, 330], [640, 360]], [[560, 400], [700, 400], [700, 560], [670, 545]]],
                   background=PICTURE, imageBox=[640, 459, 600, 440], mirrorImage=True, showRoute=False,
                   strokeEnds=[PICTURE, 2], vehicle='lens')),
    'bumper': levels(
        round_spec(PICTURE, options=[4, 5, 6], answer=1),
        round_spec(NUMBER_GROUPS, options=[9, 8, 7, 6], answer=0, player={'count': 3})),
    'slingshot': levels(
        round_spec({'count': 2}, lamps=10, turnOff=2),
        round_spec({'count': 5, 'color': '#378AD1'},
                   lamps=[{'count': 1, 'color': '#378AD1' if i % 2 else '#E8934B'} for i in range(10)],
                   matches=[1, 3, 5, 7, 9]),
        round_spec({'count': 5, 'color': '#E8934B'}, lamps=[PICTURE] * 10, matches=[0, 2, 4, 6, 8])),
    'fishing': levels(
        round_spec(PICTURE, options=['3 + 4', '2 + 4', '4 + 3'], matches=[0, 2]),
        round_spec(NUMBER_GROUPS, options=['2 + 5', '3 + 4', '4 + 3', '7 − 3', '7 − 4'], matches=[1, 2, 3, 4])),
    'slice': levels(
        round_spec(7, options=['3 + 4', '2 + 4', '4 + 3'], matches=[0, 2]),
        round_spec(6, options=['2 + 5', '3 + 3', '4 + 2', '7 − 3', '7 − 1'], matches=[1, 2, 4])),
}
TEMPLATES['trace'][0]['demoRounds'] = [round_spec(9, strokes=[[[490, 320], [490, 440]]])]

ANCHORS = '<div id="game-goal"></div><div id="game-player"></div><div id="game-target"></div>'


def render(name, level_data):
    cover = 'data:image/png;base64,!' if name == 'ring' else ART
    source = f'K.ready({{title:"测试",sub:"测试用图",img:"{cover}"}});\n'
    config = {'levels': level_data, 'goalHeight': 128 if name == 'parachute' else 84}
    return page.page(name, ANCHORS, '', source + f'K.game(K.gameTemplates.{name}({json.dumps(config)}));')


BROWSER_TEST = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const [pw, executablePath] = process.argv.slice(1);
const { chromium } = require(pw + '/node_modules/playwright-core');
const inputs = JSON.parse(fs.readFileSync(0, 'utf8'));

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 640, height: 360 }, isMobile: true, hasTouch: true });
    const cdp = await page.context().newCDPSession(page);
    for (const [name, html] of Object.entries(inputs)) {
      await page.goto('about:blank');
      const errors = [];
      const onError = err => errors.push(err.message);
      page.on('pageerror', onError);
      await page.evaluate(() => {
        const frames = [];
        let now = 1;
        window.requestAnimationFrame = fn => frames.push(fn);
        window.step = (n, target) => {
          for (let i = 0; i < n; i++) {
            for (const frame of frames.splice(0)) frame(now);
            now += 1000 / 60;
            if (target && window.K.game.status().state === target) break;
          }
          return window.K.game.status();
        };
      });
      await page.setContent(html);
      await page.waitForFunction(() => window.K.game.status());
      if (name === 'ring') await page.locator('#ready canvas.pic').waitFor();
      const geometry = await page.evaluate(() => {
        const stage = document.querySelector('#gm').getBoundingClientRect();
        return [stage.x, stage.y, stage.width, stage.height, document.querySelector('#start-btn').getBoundingClientRect().height];
      });
      assert.deepEqual(geometry.slice(0, 4), [0, 0, 640, 360], name + ' mobile frame');
      assert(geometry[4] >= 44, name + ' start button too small');
      await page.locator('#start-btn').tap();
      await page.evaluate(() => window.step(2));
      assert.equal((await page.evaluate(() => window.K.game.status())).state, 'play');

      if (name === 'trace') {
        await page.evaluate(() => {
          window.K.onState({demo: true, level: 1});
          window.step(400);
        });
        const demo = await page.evaluate(() => ({
          levels: window.K.log.filter(x => x.startsWith('level:')),
          wins: window.K.log.filter(x => x.startsWith('win:')),
          goal: window.K.game.current.data.plan.rounds[0].goal
        }));
        assert(demo.wins.length >= 2);
        assert(demo.levels.every(x => x === 'level:1'));
        assert.equal(demo.goal, 9);
        await page.evaluate(() => {
          window.K.onState({demo: false, level: 1});
          window.step(1);
        });
        // The vertical course cannot be completed by holding its destination.
        await page.mouse.move(615 / 2, 561 / 2);
        await page.mouse.down();
        await page.evaluate(() => window.step(90));
        await page.mouse.up();
        assert.equal(await page.evaluate(() => window.K.game.current.data.world.s), 0);
        assert.equal(await page.evaluate(() => window.K.game.current.data.plan.rounds[0].goal), 1);

        // Native mobile touch starts over the #play layer and needs touch-action on the stage.
        await page.evaluate(() => {
          window.cancels = 0;
          window.addEventListener('pointercancel', () => window.cancels++);
        });
        const touch = (type, x, y) => cdp.send('Input.dispatchTouchEvent', {
          type, touchPoints: type === 'touchEnd' ? [] : [{x, y, id: 1}]
        });
        await touch('touchStart', 307.5, 160.5);
        await page.evaluate(() => window.step(3));
        for (let y = 168; y <= 275; y += 7) {
          await touch('touchMove', 307.5, y);
          await page.evaluate(() => window.step(4));
        }
        await touch('touchMove', 307.5, 276);
        await page.evaluate(() => window.step(8));
        await touch('touchEnd');
        assert.equal(await page.evaluate(() => window.cancels), 0);
        assert.equal(await page.evaluate(() => window.K.game.current.data.world.s), 240);
      } else if (name === 'slingshot') {
        // Real pointer pull on the bottom-right lamp; exact-count mode waits for confirmation.
        const [x, y, px, py] = await page.evaluate(() => {
          const p = window.K.game.current.data.world.positions[9];
          const t = 0.82;
          return [234, 490, 234 + (234 - p.x) / (12 * t), 490 + (490 - p.y + 455 * t * t / 2) / (12 * t)];
        });
        await page.mouse.move(x / 2, y / 2);
        await page.mouse.down();
        await page.evaluate(() => window.step(2));
        await page.mouse.move(px / 2, py / 2);
        await page.evaluate(() => window.step(2));
        await page.mouse.up();
        await page.evaluate(() => window.step(65));
        assert.equal(await page.evaluate(() => window.K.game.current.data.world.dark.has(9)), true);
        await page.mouse.click(820 / 2, 643 / 2);
        await page.evaluate(() => window.step(2));
        const incorrect = await page.evaluate(() => {
          const g = window.K.game.current;
          return {state:g.state, remaining:g.data.world.dark.size, bubble:g.bubbleObj?.text};
        });
        assert.deepEqual(incorrect, {state:'play', remaining:1, bubble:'先看看每一组。'});
      }

      await page.evaluate(() => {
        window.K.game.autoplay(true);
        window.K.onState({level: 1});
      });
      for (let i = 0; i < 2; i++) {
        const status = await page.evaluate(() => window.step(6000, 'done'));
        assert.equal(status.state, 'done', name + ' pass ' + (i + 1) + ' ' +
          JSON.stringify(await page.evaluate(() => window.K.log)));
        assert.deepEqual(status.stars, Array(status.levels).fill(3), name + ' reached every level');
        assert.equal(status.levelMisses, 0, name + ' autopilot missed');
        assert.equal(await page.locator('#finish .big').textContent(), '★★★');
        if (i === 0) {
          await page.locator('#btn-again').click();
          assert.equal((await page.evaluate(() => window.K.game.status())).level, 1);
        }
      }
      assert.deepEqual(await page.evaluate(() => window.K.errs), [], name);
      assert.deepEqual(errors, [], name);
      page.off('pageerror', onError);
    }
  } finally {
    await browser.close();
  }
})().catch(err => { console.error(err); process.exitCode = 1; });
"""


class GameTemplatesTest(unittest.TestCase):
    def test_page_bundles_only_the_used_mechanic(self):
        self.assertEqual(game_templates.javascript('K.game({levels: 2});'), '')
        built = render('parachute', TEMPLATES['parachute'])
        self.assertIn('K.game=', built)
        self.assertIn("T.register('parachute'", built)
        self.assertNotIn("T.register('runner'", built)
        self.assertNotIn('__IMG:', built)
        self.assertEqual(built.count('<script>'), 2)

    def test_unknown_mechanic_fails_build(self):
        with self.assertRaisesRegex(ValueError, 'unknown'):
            game_templates.javascript('K.game(K.gameTemplates.unknown({}));')

    def test_all_mechanics_win_every_level_twice_with_the_production_engine(self):
        node = shutil.which('node')
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not Path(chrome).exists():
            self.skipTest('node, playwright-core and Chrome are required')
        htmls = {name: render(name, config) for name, config in TEMPLATES.items()}
        run = subprocess.run([node, '-e', BROWSER_TEST, str(playwright), chrome],
                             input=json.dumps(htmls), capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 0, run.stderr)
