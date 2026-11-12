"""Check lesson picture counts and the provenance of the exact PNGs."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import unittest
from unittest.mock import patch

LESSON = Path(__file__).resolve().parent.parent
spec = spec_from_file_location('nursery_quantity_diagrams', LESSON / 'diagrams' / 'render.py')
art = module_from_spec(spec)
spec.loader.exec_module(art)


class DiagramsTest(unittest.TestCase):
    def test_original_stage_and_later_counts(self):
        with patch.object(art, 'stamp') as stamp:
            art.story_three()
        seedling_calls = [call for call in stamp.call_args_list if call.args[1] == 'seedling']
        self.assertEqual(len(seedling_calls), 13)
        first = [call for call in seedling_calls if call.args[2][0] < 245]
        middle = [call for call in seedling_calls if 245 < call.args[2][0] < 500]
        last = [call for call in seedling_calls if call.args[2][0] > 500]
        self.assertEqual((len(first),len(middle),len(last)),(5,5,3))
        self.assertEqual(sum(call.args[2][1] < 180 for call in middle),2)

    def test_whole_reconstruction_and_return_models_include_both_parts(self):
        for a,b in (*art.RETURN_PAIRS,*art.TILE_PAIRS):
            with patch.object(art, 'stamp') as stamp:
                art.returned_model(a,b)
            self.assertEqual(len(stamp.call_args_list),a+b)
            centers=[call.args[2] for call in stamp.call_args_list]
            self.assertEqual(len(set(centers)),a+b)
            self.assertEqual(sum(y<135 for x,y in centers),a)

    def test_replay_crosses_seven_of_thirteen(self):
        with patch.object(art,'stamp') as stamp:
            image=art.whole(7,6,crossed=7)
        self.assertEqual(len(stamp.call_args_list),13)
        center_pixels=[image.getpixel(call.args[2])[:3] for call in stamp.call_args_list]
        self.assertEqual(sum(pixel==(162,74,39) for pixel in center_pixels),7)

    def test_actions_before_and_after_have_different_time_directions(self):
        with patch.object(art,'arrow') as arrow:
            art.card_icon('past',13)
            art.card_icon('after',13)
        before,after=arrow.call_args_list
        self.assertGreater(before.args[1][0],before.args[2][0])
        self.assertLess(after.args[1][0],after.args[2][0])

    def test_provenance_and_quiz_answers_are_complete(self):
        lesson=json.loads((LESSON/'lesson.json').read_text())
        manifest=json.loads((LESSON/'asset-sources.json').read_text())['assets']
        for key,source in manifest.items():
            self.assertEqual(sha256((LESSON/source['file']).read_bytes()).hexdigest(),source['sha256'],key)
        self.assertTrue(set(lesson['images'])<=set(manifest))
        quiz=next(scene for scene in lesson['scenes'] if scene['type']=='quiz')
        self.assertEqual([question['answer'][0] for question in quiz['questions']],list('BCABAC'))
