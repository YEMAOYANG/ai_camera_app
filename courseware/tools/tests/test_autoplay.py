import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from courseware.tools import autoplay


def body():
    html = '<img src="/api/classroom-media/stage-x/media/pic-ab.png"><script>var u="/api/classroom-media/stage-x/media/tts-a-1.wav"</script>'
    return {'stage': {'id': 'stage-x'}, 'scenes': [
        {'type': 'slide', 'content': {'canvas': {}}},
        {'type': 'interactive', 'content': {'html': html}},
        {'type': 'quiz', 'content': {'questions': []}},
        {'type': 'interactive', 'content': {'html': '<p>second</p>'}}]}


class AutoplayTests(unittest.TestCase):
    def play(self, results, code=0, **kw):
        seen = {}

        def run(command, timeout):
            directory = Path(command[command.index('--dir') + 1])
            seen['files'] = {p.name: p.read_text(encoding='utf-8') for p in directory.iterdir()}
            seen['command'] = command
            seen['timeout'] = timeout
            return code, json.dumps(results), ''
        with tempfile.TemporaryDirectory() as media, patch.object(autoplay, '_playwright_dir', return_value=Path('/pw')):
            receipt = autoplay.play_body(body(), media, run=run, **kw)
            seen['media'] = media
        return receipt, seen

    def test_only_interactive_scenes_are_played_with_local_media_urls(self):
        receipt, seen = self.play([{'file': 'scene-02.html', 'finishes': [30, 80], 'errors': [], 'stuck': None},
                                   {'file': 'scene-04.html', 'finishes': [12], 'errors': [], 'stuck': None}])
        self.assertEqual(sorted(seen['files']), ['scene-02.html', 'scene-04.html'])
        self.assertNotIn('/api/classroom-media', seen['files']['scene-02.html'])
        self.assertIn('file://', seen['files']['scene-02.html'])
        self.assertIn('pic-ab.png', seen['files']['scene-02.html'])
        self.assertEqual(seen['files']['scene-04.html'], '<p>second</p>')
        self.assertTrue(receipt['ok'])
        self.assertEqual([(p['scene'], p['stepsToFinish'], p['finishedAgain']) for p in receipt['pages']], [(2, 30, True), (4, 12, False)])
        self.assertEqual(receipt['bodySha256'], autoplay.body_hash(body()))
        self.assertIn('--max-steps', seen['command'])

    def test_errors_and_a_broken_replay_are_errors_and_an_unfinished_page_is_a_warning(self):
        receipt, _ = self.play([{'file': 'scene-02.html', 'finishes': [5], 'errors': ['TypeError: x', 'TypeError: x'], 'stuck': None},
                                {'file': 'scene-04.html', 'finishes': [], 'errors': [], 'stuck': 'never finished in 400 steps'}])
        self.assertFalse(receipt['ok'])
        self.assertEqual(receipt['pages'][0]['errors'], ['TypeError: x'])
        found = autoplay.issues(receipt)
        self.assertEqual([(i['code'], i['scene'], i['gate'], i['severity']) for i in found],
                         [('page_error_in_play', 2, 'G6', 'error'), ('play_unfinished', 4, 'G6', 'warn')])
        replay, _ = self.play([{'file': 'scene-02.html', 'finishes': [5], 'errors': [], 'stuck': 'finish still showing after play again'},
                               {'file': 'scene-04.html', 'finishes': [3], 'errors': [], 'stuck': 'no play-again button'}])
        self.assertEqual([(i['code'], i['severity']) for i in autoplay.issues(replay)], [('play_again_broken', 'error')] * 2)

    def test_a_failed_bot_run_is_an_error_not_a_pass(self):
        with self.assertRaises(RuntimeError):
            self.play([], code=1)
        with self.assertRaises(RuntimeError):
            self.play([{'file': 'scene-02.html', 'finishes': [1], 'errors': [], 'stuck': None}])


if __name__ == '__main__':
    unittest.main()
