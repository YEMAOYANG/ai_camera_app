"""Game pages in the random-play check (G6).

Pages that call K.game (courseware/kit/game.py) cannot be finished by blind tapping, so the bot presses and drags at
random first and then lets the engine's own autopilot finish every level twice. The receipt must say which method
finished the page. The browser tests are opt-in with MIRA_BROWSER_TESTS=1 and never call a provider.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from courseware.kit import page
from courseware.tools import autoplay

# A paddle catches falling balls. Idle or random input loses lives; the autopilot catches every ball.
GAME = r"""
K.ready({emoji:'🍎',title:'接一接',sub:'测试'});
function spawn(g){var d=g.data;d.by=-30;d.bx=g.auto?200+Math.random()*880:(d.px>640?150:1130)}
K.game({levels:2,lives:3,
 reset:function(g,l){g.data={px:640,tx:640,bx:0,by:-30,need:2+l,got:0};spawn(g)},
 autopilot:function(g){g.data.tx=g.data.bx},
 update:function(g,dt){var d=g.data,tx=g.auto?d.tx:(g.pointer.active?g.pointer.x:d.px);d.px+=(tx-d.px)*Math.min(1,dt*12);d.by+=900*dt;
  if(d.by>=600){if(Math.abs(d.bx-d.px)<90){d.got++;if(d.got>=d.need){g.win();return}}else if(g.hurt())return;spawn(g)}},
 draw:function(g,c){var d=g.data;c.fillStyle='#BFE7FB';c.fillRect(0,0,1280,720);c.fillStyle='#E53D2F';K.draw.circle(c,d.bx||0,d.by||0,20);
  c.fillStyle='#8B5631';K.draw.rr(c,(d.px||640)-80,610,160,30,12);c.fill()}
});
"""

# A level that can never be won, even by its autopilot.
ENDLESS = r"""
K.ready({emoji:'🍎',title:'玩不完',sub:'测试'});
K.game({levels:2,reset:function(g){g.data={}},update:function(){},autopilot:function(){},
 draw:function(g,c){c.fillStyle='#BFE7FB';c.fillRect(0,0,1280,720)}});
"""


def body():
    return {'stage': {'id': 'stage-x'}, 'scenes': [
        {'type': 'interactive', 'content': {'html': '<p>game</p>'}},
        {'type': 'interactive', 'content': {'html': '<p>taps</p>'}}]}


class GameReceiptTests(unittest.TestCase):
    def test_the_receipt_names_the_method_that_finished_each_page(self):
        results = [{'file': 'scene-01.html', 'finishes': [41, 42], 'errors': [], 'stuck': None,
                    'method': 'game-autopilot', 'seconds': [31, 29]},
                   {'file': 'scene-02.html', 'finishes': [12, 30], 'errors': [], 'stuck': None}]
        with tempfile.TemporaryDirectory() as media, patch.object(autoplay, '_playwright_dir', return_value=Path('/pw')):
            receipt = autoplay.play_body(body(), media, run=lambda command, timeout: (0, json.dumps(results), ''))
        game, taps = receipt['pages']
        self.assertTrue(receipt['ok'])
        self.assertEqual((game['method'], game['secondsToFinish'], game['finishedAgain']), ('game-autopilot', [31, 29], True))
        self.assertEqual(taps['method'], 'random')
        self.assertNotIn('secondsToFinish', taps)

    def test_an_unfinished_game_is_a_blocking_issue(self):
        results = [{'file': 'scene-01.html', 'finishes': [], 'errors': [], 'method': 'game-autopilot', 'seconds': [],
                    'stuck': 'game autopilot did not finish round 1'},
                   {'file': 'scene-02.html', 'finishes': [12, 30], 'errors': [], 'stuck': None}]
        with tempfile.TemporaryDirectory() as media, patch.object(autoplay, '_playwright_dir', return_value=Path('/pw')):
            receipt = autoplay.play_body(body(), media, run=lambda command, timeout: (0, json.dumps(results), ''))
        self.assertFalse(receipt['ok'])
        self.assertEqual([(i['code'], i['scene']) for i in autoplay.issues(receipt)], [('play_unfinished', 1)])


@unittest.skipUnless(os.environ.get('MIRA_BROWSER_TESTS') == '1', 'opt-in real Chrome regression')
class GameBrowserTests(unittest.TestCase):
    def run_bot(self, js, seconds_per_level):
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        if not Path(chrome).exists() or not shutil.which('node'):
            self.skipTest('Chrome and node are required')
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, 'scene-01.html').write_text(page.page('接一接', '<div id="score"></div>', '', js), encoding='utf-8')
            played = subprocess.run([
                shutil.which('node'), str(autoplay.BOT), '--playwright', str(autoplay._playwright_dir()),
                '--chrome', chrome, '--dir', temporary, '--max-steps', '50', '--seed', '7',
                '--game-seconds-per-level', str(seconds_per_level),
            ], capture_output=True, text=True, timeout=300, check=True)
        report = json.loads(played.stdout.strip().splitlines()[-1])
        self.assertEqual(len(report), 1)
        return report[0]

    def test_random_input_then_autopilot_finishes_every_level_twice(self):
        result = self.run_bot(GAME, 60)
        self.assertEqual(result['method'], 'game-autopilot')
        self.assertEqual(result['errors'], [])
        self.assertIsNone(result['stuck'])
        self.assertEqual(len(result['finishes']), 2)
        self.assertEqual(len(result['seconds']), 2)

    def test_a_game_its_autopilot_cannot_win_is_reported_stuck(self):
        result = self.run_bot(ENDLESS, 2)
        self.assertEqual(result['method'], 'game-autopilot')
        self.assertEqual(result['finishes'], [])
        self.assertTrue(result['stuck'].startswith('game autopilot did not finish round 1'), result['stuck'])


if __name__ == '__main__':
    unittest.main()
