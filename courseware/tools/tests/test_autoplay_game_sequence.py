"""Game G6 needs two complete, ordered runs with no duplicate wins."""
import os
import unittest

from courseware.tools.tests import test_autoplay_game


@unittest.skipUnless(os.environ.get('MIRA_BROWSER_TESTS') == '1', 'opt-in real Chrome regression')
class GameSequenceTests(unittest.TestCase):
    def test_finished_game_with_duplicate_win_is_rejected(self):
        result = test_autoplay_game.GameBrowserTests().run_bot('''
K.ready({title:'重复过关测试',sub:'操作按钮'});
K.game({levels:2,winPause:.15,reset(){},draw(){},autopilot(){},
 update(g){if(g.auto){if(g.level===0)K.log.push('win:1:3');g.win();}}});
''', 3)
        self.assertEqual(result['method'], 'game-autopilot')
        self.assertEqual(result['finishes'], [])
        self.assertIn('one win per level in order (1, 1, 2; expected 1, 2)', result['stuck'])
