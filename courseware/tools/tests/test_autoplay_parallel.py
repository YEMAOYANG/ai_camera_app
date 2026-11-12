import json
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch

from courseware.tools import autoplay
from courseware.tools.tests.test_autoplay import body


class ParallelAutoplayTest(unittest.TestCase):
    def test_separate_simultaneous_bots_preserve_order_and_receipt_identity(self):
        def run(command, timeout):
            directory = Path(command[command.index('--dir') + 1])
            [page] = directory.glob('scene-*.html')
            started.wait(timeout=5)
            return 0, json.dumps([{'file': page.name, 'finishes': [2, 3],
                                   'errors': [], 'stuck': None, 'method': 'game-autopilot'}]), ''

        started = Barrier(2)
        lesson = body()
        with patch.object(autoplay, '_playwright_dir', return_value=Path('/pw')):
            receipt = autoplay.play_body(lesson, '/media', jobs=2, run=run)
        self.assertEqual(receipt['bodySha256'], autoplay.body_hash(lesson))
        self.assertEqual([page['scene'] for page in receipt['pages']], [2, 4])
        self.assertTrue(all(page['finishedAgain'] and page['method'] == 'game-autopilot' for page in receipt['pages']))
