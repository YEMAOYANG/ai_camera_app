import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from courseware.kit import game, page
from courseware.tools import autoplay
from courseware.tools.check import check_classroom

# A tiny real-time game: a paddle catches falling balls. With the pointer idle the balls always land far away,
# so the child loses lives; with the autopilot every ball is caught.
GAME = r"""
K.ready({emoji:'🍎',title:'接一接',sub:'测试'});
function spawn(g){var d=g.data;d.by=-30;d.bx=g.auto?200+Math.random()*880:(d.px>640?150:1130)}
K.game({levels:2,lives:3,
 levelName:function(l){return l?'快一点':'接住小球'},
 reset:function(g,l){g.data={px:640,tx:640,bx:0,by:-30,need:2+l,got:0};spawn(g)},
 autopilot:function(g){g.data.tx=g.data.bx},
 update:function(g,dt){var d=g.data,tx=g.auto?d.tx:(g.pointer.active?g.pointer.x:d.px);d.px+=(tx-d.px)*Math.min(1,dt*12);d.by+=900*dt;
  if(d.by>=600){if(Math.abs(d.bx-d.px)<90){d.got++;K.sfx.pop();g.burst(d.bx,600);if(d.got>=d.need){g.win();return}}else if(g.hurt())return;spawn(g)}},
 draw:function(g,c){var d=g.data;c.fillStyle='#BFE7FB';c.fillRect(0,0,1280,720);c.fillStyle='#E53D2F';K.draw.circle(c,d.bx||0,d.by||0,20);
  c.fillStyle='#8B5631';K.draw.rr(c,(d.px||640)-80,610,160,30,12);c.fill()}
});
"""

PLAY = r"""
const { chromium } = require(process.env.PW_DIR + '/node_modules/playwright-core');
const [file, chrome] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const out = {};
  const status = () => page.evaluate(() => window.K.game.status());
  const visible = sel => page.evaluate(s => { const e = document.querySelector(s); if (!e) return false;
    const c = getComputedStyle(e); return c.display !== 'none' && c.visibility !== 'hidden' && !e.classList.contains('gone'); }, sel);
  const post = state => page.evaluate(s => window.postMessage({ type: 'SET_WIDGET_STATE', state: s }, '*'), state);
  const until = async (fn, ms) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await page.waitForTimeout(100); } return false; };
  await page.goto('file://' + file);
  await page.waitForTimeout(300);
  out.canvas = await page.evaluate(() => { const c = document.querySelector('#gm'); return c && [c.offsetWidth, c.offsetHeight]; });
  out.before = (await status()).state;
  await page.click('#start-btn');
  await post({ demo: true });
  out.demoLoop = await until(() => page.evaluate(() => window.K.log.filter(x => x.startsWith('win:1:')).length >= 2), 20000);
  out.demoLevels = await page.evaluate(() => window.K.log.filter(x => x.startsWith('level:')));
  await page.evaluate(() => window.K.game.autoplay(true));
  out.firstFinish = await until(() => visible('#finish'), 20000);
  out.log = await page.evaluate(() => window.K.log.filter(x => /^(win|level|auto|fail)/.test(x)));
  await page.click('#btn-again');
  await page.waitForTimeout(150);
  out.afterAgain = await status();
  out.secondFinish = await until(() => visible('#finish'), 20000);
  await page.click('#btn-again');
  await post({ demo: false, level: 2 });
  await page.waitForTimeout(150);
  out.teacherLevel = await status();
  out.retryShown = await until(() => visible('#g-retry'), 8000);
  out.afterFail = await status();
  await page.click('#g-retry');
  await page.waitForTimeout(150);
  out.afterRetry = await status();
  await page.evaluate(() => window.postMessage({ type: 'HIGHLIGHT_ELEMENT', target: '#gm' }, '*'));
  await page.waitForTimeout(150);
  out.errors = await page.evaluate(() => window.K.errs);
  await browser.close();
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def shipped(js, **kw):
    return page.page('接一接', '<div id="score"></div>', '', js, **kw)


class GameEngineShipping(unittest.TestCase):
    def test_only_pages_that_call_k_game_ship_the_engine(self):
        plain = shipped('K.ready({emoji:"🍎",title:"t",sub:"s"});')
        for marker in ('K.game=', '#gm{', '.g-anchor', 'K.sfx.jump='):
            self.assertNotIn(marker, plain)
        built = shipped(GAME)
        for marker in ('K.game=', '#gm{', 'K.game.status=', 'K.game.autoplay='):
            self.assertIn(marker, built)
        self.assertEqual(built.count('<script>'), 2)
        self.assertTrue(game.uses_game(GAME))
        self.assertFalse(game.uses_game('K.ready({});'))

    def test_page_styles_come_after_the_engine_styles(self):
        built = page.page('t', '', '#gm{opacity:.5}', GAME)
        self.assertLess(built.index(game.GAME_CSS), built.index('#gm{opacity:.5}'))

    def test_engine_ids_are_reserved(self):
        self.assertTrue({'gm', 'gcard', 'g-next', 'g-retry'} <= page.reserved_ids())
        self.assertNotIn('score', page.reserved_ids())

    def test_game_page_passes_the_release_external_media_rule(self):
        # backend/content/courseware_release.py rejects page text that looks like an external or inline media URL
        # (https?://, data:, file:, blob:) apart from the SVG/XHTML namespaces; an engine key written as `data:{}` tripped it.
        namespace = re.compile(r'https?://www\.w3\.org/(?:2000/svg|1999/xlink|1999/xhtml)')
        self.assertIsNone(re.search(r'(?:https?://|data:|file:|blob:)', namespace.sub('', shipped(GAME))))

    def test_game_page_passes_the_fixed_stage_gate(self):
        body = {'stage': {}, 'scenes': [{'type': 'interactive', 'actions': [], 'content': {'html': shipped(GAME)}}]}
        codes = {issue['code'] for issue in check_classroom(body)}
        self.assertNotIn('interactive_stage_missing', codes)


class GameEnginePlays(unittest.TestCase):
    def test_teacher_demo_replays_a_level_and_autoplay_finishes_every_level(self):
        node = shutil.which('node')
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not Path(chrome).exists():
            self.skipTest('node, playwright-core and Chrome are required for the engine play test')
        with tempfile.TemporaryDirectory() as folder:
            html = Path(folder, 'game.html')
            html.write_text(shipped(GAME), encoding='utf-8')
            script = Path(folder, 'play.cjs')
            script.write_text(PLAY, encoding='utf-8')
            result = subprocess.run([node, str(script), str(html), chrome], capture_output=True, text=True, timeout=120,
                                    env={**os.environ, 'PW_DIR': str(playwright)})
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(out['canvas'], [1280, 720])
        self.assertEqual(out['before'], 'ready')
        self.assertTrue(out['demoLoop'])
        self.assertEqual(set(out['demoLevels']), {'level:1'})
        self.assertIn('auto:1:loop', out['log'])
        self.assertTrue(out['firstFinish'])
        self.assertIn('auto:1', out['log'])
        self.assertTrue(any(x.startswith('win:1:') for x in out['log']))
        self.assertTrue(any(x.startswith('win:2:') for x in out['log']))
        self.assertEqual((out['afterAgain']['state'], out['afterAgain']['level']), ('play', 1))
        self.assertTrue(out['secondFinish'])
        self.assertEqual((out['teacherLevel']['level'], out['teacherLevel']['auto']), (2, False))
        self.assertTrue(out['retryShown'])
        self.assertEqual((out['afterFail']['state'], out['afterFail']['lives']), ('between', 0))
        self.assertEqual((out['afterRetry']['state'], out['afterRetry']['level'], out['afterRetry']['lives']), ('play', 2, 3))
        self.assertEqual(out['errors'], [])


if __name__ == '__main__':
    unittest.main()
