"""Check the finish card against the observations from the same playthrough."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.kit import page
from courseware.kit.tests.test_shutter_observation import fixture_image
from courseware.tools import autoplay


RUN = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.argv[1] + '/node_modules/playwright-core');
const {html, finalImages, hasSticker, screenshot} = JSON.parse(fs.readFileSync(0,'utf8'));

(async () => {
  const browser = await chromium.launch({executablePath:process.argv[2]});
  try {
    const p = await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
    const errors = [];
    p.on('pageerror', e => errors.push(e.message));
    await p.evaluate(() => {
      let now = 1;
      const queue = [];
      requestAnimationFrame = fn => queue.push(fn);
      window.step = (count,state) => {
        for (let i = 0; i < count; i++) {
          for (const fn of queue.splice(0)) fn(now);
          now += 1000/60;
          if (state && K.game.status().state === state) return true;
        }
        return false;
      };
    });
    await p.setContent(html);
    await p.locator('#start-btn').tap();
    const card = p.locator('#finish .shutter-observation');
    const again = p.locator('#btn-again');
    const photos = card.locator('figure');
    const absent = async () => assert.equal(await card.count(),0);
    const step = (count,state) => p.evaluate(([n, stop]) => window.step(n,stop),[count,state]);
    const shot = p.getByRole('button',{name:'按快门'});

    await p.evaluate(() => K.onState({demo:true}));
    assert.ok(await step(800,'between'));
    await absent();
    await p.evaluate(() => K.onState({demo:false,level:1}));
    for (let level = 1; level <= 3; level++) {
      await step(2);
      await shot.tap();
      await step(40);
      await absent();
      assert.equal(await p.evaluate(() => K.game.current.data.progress),1);
      await p.keyboard.press('Space');
      if (level < 3) {
        await step(110);
        await absent();
        await p.locator('#g-next').tap();
      }
    }
    assert.ok(await step(140,'done'));
    assert.equal(await card.count(),1);
    const snapshot = await p.evaluate(() => K.game.observation());
    assert.deepEqual(snapshot.levels.at(-1).trials,[{trialId:'pair',top:'top-3',side:'side-3'}]);
    const proof = await photos.evaluateAll(async figures => Promise.all(figures.map(async figure => {
      const image = figure.querySelector('img');
      await image.decode();
      return {src:image.getAttribute('src'), label:figure.querySelector('figcaption').textContent};
    })));
    assert.deepEqual(proof, finalImages.map((src,i) => ({src,label:['从上看','从侧面看'][i]})));
    const [top,side] = await Promise.all([photos.nth(0).boundingBox(),photos.nth(1).boundingBox()]);
    assert.ok(top.x+top.width < side.x && Math.abs(top.y-side.y) < 1);
    assert.ok(top.width >= 130 && top.height >= 120 && side.width >= 130 && side.height >= 120);
    const button = await again.boundingBox();
    assert.ok(button.width >= 44 && button.height >= 44 && button.y+button.height < 360);
    assert.match(await p.locator('#finish .card p').textContent(),/得分 675/);
    if (hasSticker) assert.equal(await p.locator('#finish .big img[alt="过关贴纸"]').count(),1);
    else assert.equal(await p.locator('#finish .big').textContent(),'★');
    assert.deepEqual(await p.evaluate(() => K.audit('shutter finish 640')),[]);
    if (screenshot) await p.screenshot({path:screenshot,animations:'disabled'});

    await again.tap();
    await absent();
    assert.equal(await p.evaluate(() => K.game.observation()),null);
    await p.evaluate(() => K.game.autoplay(true));
    assert.ok(await step(1800,'done'));
    await absent();
    assert.equal(await p.evaluate(() => K.game.observation()),null);
    assert.deepEqual(await p.evaluate(() => K.errs),[]);
    assert.deepEqual(errors,[]);
    console.log('Finish card: correct photos, score, sticker and replay at 640×360; hidden in demo, partial and auto runs.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def camera_fixture(views, *, sticker=None, screenshot=None):
    config = {
        'doneText': '把你拍到的两张照片放在一起，看看有什么不同。',
        'art': {'icons': {}},
        'levels': [],
        'observation': {'sceneId': 'scene-camera', 'trials': {'pair': {'top': [], 'side': []}}},
    }
    if sticker:
        config['art']['sticker'] = sticker
    for number, images in enumerate(views, 1):
        ids = {direction: f'{direction}-{number}' for direction in ('top', 'side')}
        for direction, image in zip(ids, images):
            config['art']['icons'][ids[direction]] = image
            config['observation']['trials']['pair'][direction].append(ids[direction])
        config['levels'].append(dict(rate=.55, range=88, aperture=155, shots=[1, 0], photoViews=ids))
    js = 'K.ready({title:"快门侦探"});K.game(K.gameTemplates.shutterScout(' + json.dumps(config) + '));'
    return dict(html=page.page('快门侦探', '', '', js, tests=True), finalImages=list(views[-1]),
                hasSticker=bool(sticker), screenshot=screenshot)


class ShutterFinishCardTest(unittest.TestCase):
    def test_completed_manual_run_shows_its_last_photo_pair(self):
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        node = shutil.which('node')
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')
        views = [(fixture_image(90, 60, color), fixture_image(12, 60, color))
                 for color in ('seagreen', 'orange', 'royalblue')]
        fixture = camera_fixture(views, sticker=fixture_image(80, 80, 'goldenrod'))
        result = subprocess.run(
            [node, '-e', RUN, str(playwright), str(chrome)], input=json.dumps(fixture),
            text=True, capture_output=True, timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout, end='')
