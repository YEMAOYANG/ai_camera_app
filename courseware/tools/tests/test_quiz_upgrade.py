from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from courseware.tools.quiz_upgrade import upgrade_quiz


FIXTURE = Path(__file__).parent / 'fixtures' / 'sample_body.json'


def make_spec(body):
    scene_index = next(i for i, scene in enumerate(body['scenes'], 1) if scene['type'] == 'quiz')
    questions = body['scenes'][scene_index - 1]['content']['questions']
    picture = {'kind': 'picture', 'alt': '五只鸭子', 'picture': {
        'groups': [{'cells': [{'glyph': '🦆'} for _ in range(5)]}], 'separator': 'none'}}
    return {'scenes': [{'sceneIndex': scene_index, 'questions': [
        {'id': q['id'], 'skill': '数一数', 'question': '①【数一数】请数一数？🦆' if i == 0 else '②【数序】接下来是几？',
         'visual': picture if i == 0 else None,
         'options': {o['value']: {'label': o['label'], 'visual': picture if j == 0 else {'kind': 'quantity', 'count': j}}
                     for j, o in enumerate(q['options'])}}
        for i, q in enumerate(questions)]}]}


class QuizUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.body = json.loads(FIXTURE.read_text())
        self.spec = make_spec(self.body)
        self.index = self.spec['scenes'][0]['sceneIndex'] - 1

    def test_upgrade_preserves_answers_and_adds_picture_and_speech(self):
        original = deepcopy(self.body)
        with tempfile.TemporaryDirectory() as directory:
            result, needed = upgrade_quiz(self.body, self.spec, stage_id='stage-test', media_dir=directory,
                                          audio_urls={'q1': '/audio/q1.wav'})
            scene = result['scenes'][self.index]
            questions = scene['content']['questions']
            self.assertEqual(self.body, original)
            for before, question in zip(original['scenes'][self.index]['content']['questions'], questions):
                self.assertEqual(question['answer'], before['answer'])
                self.assertEqual(question['analysis'], before['analysis'])
                self.assertTrue(question['skill'])
                self.assertNotIn('🦆', question['question'])
                self.assertNotIn('【', question['question'])
                self.assertEqual(set(question['optionVisuals']), {o['value'] for o in question['options']})
                self.assertEqual(sum(a.get('text') == question['question'] for a in scene['actions'] if a['type'] == 'speech'), 1)
            self.assertEqual([a['text'] for a in needed], [q['question'] for q in questions])
            self.assertEqual([a['questionId'] for a in needed], [q['id'] for q in questions])
            self.assertEqual(len({a['id'] for a in scene['actions']}), len(scene['actions']))
            self.assertNotIn('自己读题', ''.join(a.get('text', '') for a in scene['actions']))
            self.assertEqual(questions[0]['questionAudioUrl'], '/audio/q1.wav')
            for path in Path(directory).iterdir():
                self.assertEqual(path.name, hashlib.sha256(path.read_bytes()).hexdigest() + '.png')
            self.assertTrue(list(Path(directory).iterdir()))
            self.assertTrue(questions[0]['visual']['src'].endswith(next(Path(directory).iterdir()).name))

    def test_absent_or_null_visual_removes_existing_visual(self):
        for absent in (False, True):
            with self.subTest(absent=absent), tempfile.TemporaryDirectory() as directory:
                body = deepcopy(self.body)
                spec = deepcopy(self.spec)
                body['scenes'][self.index]['content']['questions'][1]['visual'] = {'kind': 'quantity', 'count': 3}
                if absent:
                    del spec['scenes'][0]['questions'][1]['visual']
                result, _ = upgrade_quiz(body, spec, stage_id='stage-test', media_dir=directory)
                self.assertNotIn('visual', result['scenes'][self.index]['content']['questions'][1])

    def test_intro_replaces_speech_and_preserves_other_actions(self):
        scene = self.body['scenes'][self.index]
        old_speech = deepcopy(scene['actions'])
        first = {'id': 'quiz_speech_1', 'type': 'spotlight', 'elementId': 'first'}
        second = {'id': 'other_action', 'type': 'reveal', 'elementId': 'second'}
        scene['actions'] = [old_speech[0], first, old_speech[1], second, *old_speech[2:]]
        self.spec['scenes'][0]['intro'] = ['我们开始吧。', '一起看看。']
        with tempfile.TemporaryDirectory() as directory:
            result, needed = upgrade_quiz(self.body, self.spec, stage_id='stage-test', media_dir=directory)
        actions = result['scenes'][self.index]['actions']
        questions = result['scenes'][self.index]['content']['questions']
        self.assertEqual(actions[:2], [first, second])
        self.assertEqual([a['text'] for a in actions[2:]], ['我们开始吧。', '一起看看。'] + [q['question'] for q in questions])
        self.assertTrue(all(a['type'] == 'speech' for a in actions[2:]))
        self.assertEqual(needed, [{'id': a['id'], 'text': a['text'], 'questionId': question_id}
                                  for a, question_id in zip(actions[2:], [None, None] + [q['id'] for q in questions])])
        self.assertTrue({a['id'] for a in old_speech}.isdisjoint(a['id'] for a in actions[2:]))
        self.assertEqual(len({a['id'] for a in actions}), len(actions))

    def test_intro_reading_instruction_is_rejected(self):
        self.spec['scenes'][0]['intro'] = ['请你先自己读题']
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'intro line'):
                upgrade_quiz(self.body, self.spec, stage_id='stage-test', media_dir=directory)

    def test_missing_visual_and_empty_alt_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            del self.spec['scenes'][0]['questions'][0]['options']['A']['visual']
            with self.assertRaisesRegex(ValueError, 'missing option visual'):
                upgrade_quiz(self.body, self.spec, stage_id='stage-test', media_dir=directory)
            self.spec = make_spec(self.body)
            self.spec['scenes'][0]['questions'][0]['visual']['alt'] = ' '
            with self.assertRaisesRegex(ValueError, 'alt'):
                upgrade_quiz(self.body, self.spec, stage_id='stage-test', media_dir=directory)


if __name__ == '__main__':
    unittest.main()
