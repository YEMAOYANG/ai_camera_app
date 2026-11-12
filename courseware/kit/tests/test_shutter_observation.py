"""Exercise shutterScout's two camera views through the built player."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from urllib.parse import quote

from courseware.kit import page
from courseware.tools import autoplay


RUN = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.argv[1] + '/node_modules/playwright-core');
const {legacy, paired, config, expected} = JSON.parse(fs.readFileSync(0, 'utf8'));
const role = id => '#game-' + id;

async function run(browser, html, manual) {
  const p = await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  const errors = [];
  p.on('pageerror', e => errors.push(e.message));
  try {
    await p.evaluate(() => {
      const pending = [];
      let time = 1;
      window.requestAnimationFrame = callback => pending.push(callback);
      window.imagesDrawn = [];
      window.results = [];
      const drawImage = CanvasRenderingContext2D.prototype.drawImage;
      CanvasRenderingContext2D.prototype.drawImage = function(image, ...args) {
        if (image.src?.startsWith('data:image/svg+xml,') && this.canvas.id === 'gm') {
          const {e:x, f:y} = this.getTransform();
          imagesDrawn.push({src:image.src,x,y});
        }
        return drawImage.call(this,image,...args);
      };
      window.step = (frames, stop) => {
        for (let i = 0; i < frames; i++) {
          imagesDrawn.length = 0;
          for (const callback of pending.splice(0)) callback(time);
          time += 1000 / 60;
          if (stop && K.game.status().state === stop) return true;
        }
        return false;
      };
    });
    await p.setContent(html);
    await p.evaluate(() => {
      addEventListener('mira-game-observation-ready', () => results.push(K.game.observation()));
    });
    const step = n => p.evaluate(n => step(n), n);
    const until = state => p.evaluate(state => step(3600, state), state);
    const read = () => p.evaluate(() => ({
      snapshot: K.game.observation(), results, status: K.game.status(),
      photos: K.game.current.data.w.photos.map(p => p.view),
      live: imagesDrawn.find(im => im.y > 180 && im.y < 490)?.src,
      goal: imagesDrawn.find(im => im.y === 126)?.src,
      gallery: imagesDrawn.filter(im => im.y === 565).map(im => im.src),
      errors: K.errs,
    }));
    await p.locator('#start-btn').tap();
    if (manual) {
      await p.evaluate(async config => {
        const changes = [
          cfg => { delete cfg.levels[1].photoViews; },
          cfg => { cfg.levels[0].shots = [0,0]; },
          cfg => { delete cfg.art.icons[cfg.levels[0].photoViews.side]; },
          cfg => { cfg.observation.trials.paired.side = ['undeclared-view']; },
          cfg => { cfg.observation.trials.extra = cfg.observation.trials.paired; },
          cfg => {
            const {top,side} = cfg.levels[0].photoViews;
            cfg.art.icons[side] = cfg.art.icons[top];
          },
        ];
        for (const change of changes) {
          const invalid = structuredClone(config);
          change(invalid);
          try { K.gameTemplates.shutterScout(invalid); }
          catch (e) { if (e.message.startsWith('camera ')) continue; throw e; }
          throw new Error('accepted invalid shutter observation config');
        }
        await Promise.all(Object.values(config.art.icons).map(src => {
          const im = new Image();
          im.src = src;
          return im.decode();
        }));
      }, config);

      const first = config.levels[0].photoViews;
      const icon = id => config.art.icons[id];
      await step(2);
      const opening = await read();
      assert.equal(opening.live, icon(first.top));
      assert.equal(opening.goal, icon(first.side));
      const goalBox = await p.locator(role('goal')).boundingBox();
      assert.equal(goalBox.y + goalBox.height / 2, 63, 'teacher goal anchor follows the preview');
      await p.keyboard.press('Space');
      await step(1);
      const wrong = await read();
      assert.equal(wrong.status.misses, 1);
      assert.deepEqual(wrong.gallery, []);
      assert.equal(wrong.snapshot, null);

      await p.evaluate(() => K.onState({demo:true}));
      assert.ok(await until('between'));
      await step(30);
      const demo = await read();
      assert.deepEqual(demo.gallery, [icon(first.side)]);
      assert.deepEqual(demo.results, []);
      assert.equal(demo.snapshot, null);
      await p.evaluate(() => K.onState({demo:false,level:1}));
      await step(2);
      assert.deepEqual((await read()).gallery, []);

      async function aim() {
        // Follow the on-screen target with arrow controls and compare the
        // actual canvas images. No mechanic state is used to choose a shot.
        return p.evaluate(() => {
          const center = name => {
            const r = document.querySelector('#game-'+name).getBoundingClientRect();
            return [r.x+r.width/2,r.y+r.height/2];
          };
          const key = (type, direction) =>
            dispatchEvent(new KeyboardEvent(type,{key:direction}));
          for (let i = 0; i < 1200; i++) {
            const [x,y] = center('player'), [tx,ty] = center('target');
            const goal = imagesDrawn.find(im => im.y === 126);
            const live = imagesDrawn.find(im => im.y > 180 && im.y < 490);
            if (Math.abs(x-tx) < 17 && Math.abs(y-ty) < 12 && goal?.src === live?.src) return true;
            const directions = [];
            if (Math.abs(x-tx) > 5) directions.push(tx < x ? 'ArrowLeft' : 'ArrowRight');
            if (Math.abs(y-ty) > 5) directions.push(ty < y ? 'ArrowUp' : 'ArrowDown');
            for (const direction of directions) key('keydown',direction);
            step(1);
            for (const direction of directions) key('keyup',direction);
          }
          return false;
        });
      }

      for (const [index, level] of config.levels.entries()) {
        const captured = [];
        for (const state of level.shots) {
          assert.ok(await aim(), 'could not frame the requested view');
          if (captured.length === 0) await p.getByRole('button',{name:'按快门'}).tap();
          else await p.keyboard.press('Space');
          await step(1);
          captured.push(level.photoViews[state === 1 ? 'top' : 'side']);
          const result = await read();
          assert.deepEqual(result.photos, captured);
          assert.deepEqual(result.gallery, captured.map(icon));
          assert.deepEqual(result.results, []);
          assert.equal(result.snapshot, null);
          await step(28);
        }
        if (index < config.levels.length-1) {
          await step(80);
          await p.locator('#g-next').tap();
          await step(2);
          assert.deepEqual((await read()).gallery, []);
        }
      }
      assert.ok(await until('done'));
      const finished = await read();
      assert.deepEqual(finished.snapshot, expected);
      assert.deepEqual(finished.results, [expected]);
      await p.locator('#btn-again').tap();
      await step(2);
      const replay = await read();
      assert.equal(replay.snapshot, null);
      assert.deepEqual(replay.gallery, []);
      assert.deepEqual(replay.results, [expected]);
    }

    await p.evaluate(() => K.game.autoplay(true));
    const baseline = manual ? [expected] : [];
    for (let pass = 0; pass < 2; pass++) {
      const logStart = await p.evaluate(() => K.log.length);
      assert.ok(await until('done'));
      const result = await read();
      const wins = await p.evaluate(from =>
        K.log.slice(from).filter(line => line.startsWith('win:')).map(line => +line.split(':')[1]), logStart);
      assert.deepEqual(wins, [1,2,3]);
      assert.equal(result.status.stars.length, 3);
      assert.ok(result.status.stars.every(stars => stars >= 1 && stars <= 3));
      assert.equal(result.snapshot, null);
      assert.deepEqual(result.results, baseline);
      assert.deepEqual(result.errors, []);
      assert.deepEqual(errors, []);
      if (pass === 0) await p.locator('#btn-again').tap();
    }
    console.log(manual ? 'Paired views: manual captures and replay, demo, two autoplay runs.'
                       : 'Legacy shutterScout: two autoplay runs.');
  } finally { await p.close(); }
}

(async () => {
  const browser = await chromium.launch({executablePath:process.argv[2]});
  try {
    await run(browser, legacy, false);
    await run(browser, paired, true);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
"""


def fixture_image(width, height, color):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
           f'<rect width="{width}" height="{height}" fill="{color}"/></svg>')
    return 'data:image/svg+xml,' + quote(svg, safe='')


class ShutterObservationTest(unittest.TestCase):
    def test_camera_uses_the_same_two_views_for_play_and_observations(self):
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        node = shutil.which('node')
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')

        sample = Path(__file__).resolve().parents[1] / 'examples/classic-arcade/shutter-scout.json'
        legacy = json.loads(sample.read_text(encoding='utf-8'))
        legacy.pop('art')  # The original offline example still supports absent art.
        config = json.loads(json.dumps(legacy))
        config['art'] = {'icons': {}}
        config['observation'] = {'sceneId': 'scene-camera', 'trials': {'paired': {'top': [], 'side': []}}}
        expected = dict(schemaVersion='mira.game.observation.v1', sceneId='scene-camera', kind='simulation', levels=[])
        for index, (level, color) in enumerate(zip(config['levels'], ('seagreen', 'orange', 'royalblue')), 1):
            top, side = f'top-{index}', f'side-{index}'
            level['photoViews'] = {'top': top, 'side': side}
            config['art']['icons'][top] = fixture_image(90, 60, color)
            config['art']['icons'][side] = fixture_image(90, 12, color)
            config['observation']['trials']['paired']['top'].append(top)
            config['observation']['trials']['paired']['side'].append(side)
            expected['levels'].append(dict(level=index, trials=[dict(trialId='paired', top=top, side=side)]))
        config['levels'][0]['shots'] = [0, 1, 0]

        def html(options):
            anchors = ''.join(f'<div id="game-{role}"></div>' for role in ('goal', 'player', 'target'))
            js = 'K.ready({title:"快门侦探"});K.game(K.gameTemplates.shutterScout(' + json.dumps(options) + '));'
            return page.page('快门侦探', anchors, '', js)

        result = subprocess.run(
            [node, '-e', RUN, str(playwright), str(chrome)],
            input=json.dumps(dict(legacy=html(legacy), paired=html(config), config=config, expected=expected)),
            text=True, capture_output=True, timeout=75,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout, end='')
