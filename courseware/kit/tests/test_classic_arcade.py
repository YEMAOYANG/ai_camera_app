import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from courseware.kit.game_templates import javascript, stylesheet
from courseware.kit.page import page
from courseware.tools import autoplay
from courseware.tools.game_preview import build_examples


def _alternate_content(folder):
    # Simulated semantic IDs: numeric defaults cannot solve these levels.
    cases = {'tiles': ('fallingTiles', {'bottom': [None, 'boat-card', None, 'shell-card', None, 'kite-card'],
                                       'pieces': ['boat', 'shell', 'kite'], 'interval': 1.1}),
             'marbles': ('magnetMarbles', {'targets': [{'x': x, 'value': v} for x, v in
                                                       zip((450, 640, 830), ('boat-card', 'shell-card', 'kite-card'))],
                                          'queue': ['boat', 'shell', 'kite'], 'speed': 410, 'drift': 7})}
    directory = Path(folder, 'pairing')
    directory.mkdir()
    for filename, (template, opts) in cases.items():
        level = {**opts, 'pairs': [[v, v + '-card'] for v in ('boat', 'shell', 'kite')]}
        config = json.dumps({'levels': [level] * 3})
        script = ('K.ready({title:"Pairing",sub:"Regression fixture"});' +
                  f'K.game(K.gameTemplates.{template}({config}));')
        directory.joinpath(filename + '.html').write_text(page('Pairing fixture', '', '', script), encoding='utf-8')


class ClassicArcadeTest(unittest.TestCase):
    def test_inline_loader_is_opt_in_and_composable(self):
        platform = 'K.game(K.gameTemplates.platformHop({}));'
        self.assertNotIn('const Classic', javascript('K.game(K.gameTemplates.runner({}));'))
        self.assertNotIn('const Classic', javascript('K.game({});'))
        self.assertIn('const Classic', javascript(platform))
        self.assertNotIn('K.gameTemplates.fallingTiles =', javascript(platform))
        self.assertIn('.arc-key', stylesheet(platform))
        self.assertEqual(stylesheet('K.game({});'), '')
        combo = platform + 'K.game(K.gameTemplates.runner({}));'
        self.assertEqual(javascript(combo).count('const Classic'), 1)
        self.assertIn('platformHop =', javascript(combo))
        self.assertIn('register(\'runner\'', javascript(combo))

    def test_browser_demo_controls_difficulty_and_two_completions(self):
        node = shutil.which('node')
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not Path(chrome).exists():
            self.skipTest('node, playwright-core and Chrome are needed to verify gameplay')
        with tempfile.TemporaryDirectory() as temp:
            build_examples(temp, assets=None, tests=True)
            _alternate_content(temp)
            result = subprocess.run(
                [node, str(Path(__file__).with_name('classic_arcade.browser.cjs')), temp, chrome],
                text=True, capture_output=True, timeout=320, env={**os.environ, 'PW_DIR': str(playwright)},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout, end='')
