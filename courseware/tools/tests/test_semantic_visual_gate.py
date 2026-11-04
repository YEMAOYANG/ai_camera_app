import json
from pathlib import Path
import shutil
import tempfile
import unittest

from courseware.tools import build


FIXTURE = Path(__file__).parent / 'fixtures' / 'build_lesson'


class SemanticVisualGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lesson = Path(self.tmp.name) / 'lesson'
        shutil.copytree(FIXTURE, self.lesson)
        self.out = Path(self.tmp.name) / 'out'

    def prepare(self):
        return build.prepare(self.lesson, self.out, stage_id='visual-gate-test', now_ms=1)

    def test_early_grade_interactive_requires_registered_picture_or_semantic_diagram(self):
        page = self.lesson / 'pages' / 'play.html'
        page.write_text('<button id="go">选</button>', encoding='utf-8')
        with self.assertRaises(build.BuildError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.args[0], 'semantic_visual_missing')

        page.write_text('<div data-semantic-diagram="数量点阵"><button id="go">选</button></div>', encoding='utf-8')
        self.assertEqual(self.prepare()['grade'], 1)

    def test_later_grade_page_is_not_forced_to_use_picture_play(self):
        lesson_file = self.lesson / 'lesson.json'
        lesson = json.loads(lesson_file.read_text(encoding='utf-8'))
        lesson['grade'] = 3
        lesson_file.write_text(json.dumps(lesson), encoding='utf-8')
        (self.lesson / 'pages' / 'play.html').write_text('<button id="go">选</button>', encoding='utf-8')
        self.assertEqual(self.prepare()['grade'], 3)


if __name__ == '__main__':
    unittest.main()
