import importlib.util
import json
from pathlib import Path
import re
import unittest

from courseware.tools import check


SOURCE = Path(__file__).resolve().parents[1]


def load_source(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CourseSourceTests(unittest.TestCase):
    def test_source_manifest(self):
        lesson = json.loads((SOURCE / 'lesson.json').read_text())
        assets = {entry['file'] for entry in lesson['images'].values()}
        self.assertEqual(assets, {p.relative_to(SOURCE).as_posix() for p in (SOURCE / 'assets').glob('*.png')})
        notes = json.loads((SOURCE / 'official-notes.json').read_text())
        self.assertEqual(len(notes['objectives']), 6)
        self.assertEqual([x['pageCount'] for x in notes['resources'].values() if x['status'] == 'reviewed'], [5, 20, 2, 1])

    def test_every_activity_has_one_visible_answer_and_a_changed_board(self):
        renderer = load_source('render_widgets')
        lesson = json.loads((SOURCE / 'lesson.json').read_text())
        self.assertEqual(set(renderer.WIDGETS), {scene['page'] for scene in lesson['scenes'] if scene['type'] == 'interactive'})
        for key, widget in renderer.WIDGETS.items():
            text = (SOURCE / 'pages' / f'{key}.js').read_text()
            for round_spec in widget['rounds']:
                choices = [choice['url'] for choice in round_spec['choices']]
                self.assertEqual(len(set(choices)), 3)
                self.assertIn(round_spec['answer'], (0, 1, 2))
                self.assertNotEqual(round_spec['target']['url'], round_spec['result']['url'])
                self.assertTrue(all(art in text for art in [*choices, round_spec['target']['url'], round_spec['result']['url']]))

    def test_quiz_uses_registered_diagrams_for_prompts_and_options(self):
        lesson = json.loads((SOURCE / 'lesson.json').read_text())
        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        self.assertEqual(len(quiz['questions']), 8)
        self.assertIn('同时比较缺口的数量与轮廓', [q['skill'] for q in quiz['questions']])
        answers = [q['answer'][0] for q in quiz['questions']]
        self.assertLessEqual(max(answers.count(answer) for answer in set(answers)), len(answers) // 2)
        for q in quiz['questions']:
            options = [item['visual'] for item in q['options'].values()]
            self.assertEqual(len({item['image'] for item in options}), 3)
            self.assertTrue(all(item['image'] in lesson['images'] for item in [*options, *([q['visual']] if 'visual' in q else [])]))

    def test_narration_length_and_widget_targets(self):
        lesson = json.loads((SOURCE / 'lesson.json').read_text())
        for scene in lesson['scenes']:
            if scene['type'] == 'quiz':
                lines = [*scene['intro'], *[q['question'] for q in scene['questions']]]
            else:
                lines = [beat['say'] for beat in scene['script'] if 'say' in beat]
                interactive = scene['type'] == 'interactive'
                self.assertGreaterEqual(len(lines), 5 if interactive else 6)
                self.assertGreaterEqual(sum(map(len, lines)), 90 if interactive else 100)
                if interactive:
                    html = (SOURCE / 'pages' / f"{scene['page']}.html").read_text()
                    ids = set(re.findall(r'id="([^"]+)"', html))
                    self.assertTrue(all(beat['highlight'][1:] in ids for beat in scene['script'] if 'highlight' in beat))
            self.assertTrue(all(len(line) <= 40 and not check.traditional(line) for line in lines))


if __name__ == '__main__':
    unittest.main()
