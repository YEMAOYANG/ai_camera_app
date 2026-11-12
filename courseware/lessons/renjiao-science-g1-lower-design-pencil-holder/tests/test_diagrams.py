import json
from pathlib import Path
import sys
import unittest


LESSON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LESSON / 'diagrams'))
import render


class PencilHolderDiagramsTest(unittest.TestCase):
    def test_two_views_keep_each_load_and_change_only_view(self):
        trials = render.TRIALS
        self.assertEqual([(p.kind, p.bin) for p in trials[0]],
                         [('ruler', 'tall'), ('pencil-red', 'low'), ('eraser', 'tray')])
        self.assertEqual([(p.kind, p.bin) for p in trials[1]],
                         [('ruler', 'tall'), ('pencil-red', 'tall'), ('eraser', 'tray')])
        self.assertEqual(render.visible_from_side(trials[0]), ('ruler', 'pencil-red'))
        self.assertEqual(render.visible_from_side(trials[1]), ('ruler',))
        self.assertEqual(render.visible_from_side(trials[2]),
                         ('ruler', 'marker-blue', 'pencil-red', 'pencil-ochre'))

    def test_second_load_really_hides_pencil_in_side_raster(self):
        rgb = (222, 102, 79)
        trial = render.TRIALS[1]
        self.assertIn(rgb, {color for _, color in render.from_top(trial).getcolors(1000)})
        self.assertNotIn(rgb, {color for _, color in render.from_side(trial).getcolors(1000)})

    def test_observation_allowlist_uses_rendered_pairs(self):
        lesson = json.loads((LESSON / 'lesson.json').read_text(encoding='utf-8'))
        photo = next(s for s in lesson['scenes'] if s['key'] == 'take-two-views')
        exact = render.images()
        for i, level in enumerate(photo['observationCard']['levels'], 1):
            trial, = level['trials']
            self.assertEqual(trial['id'], 'same-load-views')
            top, = trial['top']
            side, = trial['side']
            self.assertEqual(top, f'trial-{i}-top')
            self.assertEqual(side, f'trial-{i}-side')
            self.assertNotEqual(exact[top].tobytes(), exact[side].tobytes())
        self.assertEqual(set(lesson['images']) - set(exact),
                         {'desk-scene', 'material-bench', 'sort-workbench', 'photo-workbench'})


if __name__ == '__main__':
    unittest.main()
