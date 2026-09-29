"""Adaptive routes, delayed recall and bounded support on isolated state."""
from copy import deepcopy
import json
import unittest
import wave
from unittest.mock import Mock
from content import textbook_journey as journey
from content import textbook_activity as legacy
from core.errors import ApiError
from services.textbook_journey_service import sync_journey
from test_textbook_activity import release_fixture


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.release = release_fixture()
        self.state = journey.initial({}, self.release)
        self.time = 1800000000000

    def act(self, name, action, choice=None):
        value = {'section': name, 'version': self.state['version'], 'action': action}
        if choice is not None:
            value['choice'] = choice
        journey.advance(self.state, name, value, self.release, timestamp=self.time)

    def correct(self, name):
        current = journey.item(self.state[name], self.release, self.state)
        self.act(name, 'answer', current['targets'][0])
        self.act(name, 'next')

    def finish(self, name):
        for _ in range(100):
            if self.state[name]['phase'] == 'done':
                return
            self.correct(name)
        self.fail('The learning flow did not terminate')

    def test_precheck_shortens_known_skills_but_still_requires_new_context(self):
        self.finish('games')
        self.assertEqual(self.state['skippedSkills'], journey.SKILLS)
        self.assertEqual(len(self.state['games']['records']), 6)
        self.assertEqual(self.state['challenge']['phase'], 'transfer')
        self.assertFalse(journey.complete({'textbookPlay': self.state}))
        self.finish('challenge')
        self.assertTrue(journey.complete({'textbookPlay': self.state}))
        self.assertEqual(self.state['status'], 'session_passed')
        self.assertEqual(self.state['reviewDueAt'], self.time + journey.DAY)

    def test_hint_layers_are_distinct_and_block_independent_credit(self):
        hints = []
        for _ in range(3):
            self.act('games', 'hint')
            hints.append(journey.public_view(self.state, self.release)['games']['hint'])
        self.assertEqual(len(set(hints)), 3)
        self.correct('games')
        self.finish('games')
        self.assertEqual(journey.quiz_result(self.state, self.release)['independentCorrectCount'], 5)
        self.assertNotIn('sky', self.state['skippedSkills'])
        self.assertTrue(any(r['phase'] == 'hunt' and r['skill'] == 'sky' for r in self.state['games']['records']))

    def test_wrong_check_triggers_probe_repair_and_unassisted_different_item(self):
        self.finish('games')
        first = journey.item(self.state['challenge'], self.release, self.state)
        self.act('challenge', 'answer', next(o['value'] for o in first['options'] if o['value'] not in first['targets']))
        self.act('challenge', 'next')
        for _ in range(5): self.correct('challenge')
        self.assertEqual(self.state['challenge']['phase'], 'probe')
        self.assertFalse(journey.complete({'textbookPlay': self.state}))
        self.correct('challenge')
        self.assertIn('字词对应', self.state['diagnoses']['sky']['observation'])
        self.assertEqual(self.state['challenge']['phase'], 'repair')
        self.correct('challenge')
        alternate = journey.item(self.state['challenge'], self.release, self.state)
        self.assertNotEqual(first['id'], alternate['id'])
        self.act('challenge', 'hint')
        self.correct('challenge')
        self.assertEqual(self.state['challenge']['phase'], 'probe')
        self.finish('challenge')
        self.assertEqual(len(self.state['verified']), 6)

    def test_persistent_difficulty_pauses_without_false_mastery_then_resumes(self):
        self.finish('games')
        for _ in range(100):
            phase = self.state['challenge']['phase']
            if phase == 'break': break
            if phase == 'transfer': self.act('challenge', 'adult')
            self.correct('challenge')
        self.assertEqual(self.state['challenge']['phase'], 'break')
        self.assertTrue(self.state['parentNeeded'])
        self.assertIsNone(self.state['reviewDueAt'])
        self.assertFalse(journey.complete({'textbookPlay': self.state}))
        seen = set(self.state['usedItems'])
        self.act('challenge', 'resume')
        self.assertTrue(self.state['parentNeeded'])
        self.finish('challenge')
        self.assertFalse(self.state['parentNeeded'])
        new_checks = {r['questionId'] for r in self.state['challenge']['records'] if r['phase'] == 'transfer'}
        self.assertFalse(seen & new_checks)

    def test_day_and_week_reviews_use_new_banks_and_cannot_be_done_early(self):
        self.finish('games'); self.finish('challenge')
        baseline = deepcopy(self.state['baseline'])
        first = {r['questionId'] for r in self.state['challenge']['records'] if r['phase'] == 'transfer'}
        due = self.state['reviewDueAt']
        with self.assertRaises(ApiError): self.act('challenge', 'review')
        self.assertEqual(self.state['reviewDueAt'], due)
        self.act('games', 'replay'); self.finish('games')
        self.assertEqual(self.state['reviewDueAt'], due)
        self.time = due
        self.act('challenge', 'review'); self.finish('challenge')
        second = {r['questionId'] for r in self.state['challenge']['records'] if r['phase'] == 'transfer'}
        self.assertFalse(first & second)
        self.assertEqual(self.state['reviewDueAt'], due + 7 * journey.DAY)
        self.assertEqual(self.state['reviewLevel'], 1)
        self.time = self.state['reviewDueAt']
        self.act('challenge', 'review'); self.finish('challenge')
        third = {r['questionId'] for r in self.state['challenge']['records'] if r['phase'] == 'transfer'}
        self.assertFalse((first | second) & third)
        self.assertEqual(self.state['status'], 'retained')
        self.assertIsNone(self.state['reviewDueAt'])
        self.assertEqual(self.state['baseline'], baseline)
        self.assertEqual(len(self.state['reviewHistory']), 2)

    def test_reload_stale_request_and_private_answers(self):
        public = journey.public_view(self.state, self.release)
        self.assertNotIn('targets', json.dumps(public))
        self.assertNotIn('独立追问', json.dumps(public, ensure_ascii=False))
        self.correct('games')
        restored = journey.initial({'textbookPlay': json.loads(json.dumps(self.state))}, self.release)
        self.assertEqual(restored, self.state)
        with self.assertRaises(ApiError):
            journey.advance(self.state, 'games', {'section': 'games', 'version': 0, 'action': 'hint'}, self.release)
        with self.assertRaises(ApiError): self.act('challenge', 'answer', 'A')

    def test_legacy_grades_are_retained_and_new_context_is_required(self):
        old = legacy.initial({}, self.release)
        for _ in range(6):
            for action in ('answer', 'next'):
                legacy.advance(old, 'challenge', {'section': 'challenge', 'version': old['version'], 'action': action,
                    **({'choice': 'A'} if action == 'answer' else {})}, self.release)
        result = legacy.quiz_result(old, self.release)
        upgraded = journey.initial({'textbookPlay': old, 'quiz': result}, self.release)
        self.assertEqual(upgraded['legacyEvidence'], old)
        self.assertEqual(journey.quiz_result(upgraded, self.release), result)
        self.assertEqual(upgraded['challenge']['phase'], 'transfer')

    def test_parent_report_updates_and_review_tasks_are_idempotent(self):
        self.finish('games'); self.finish('challenge')
        learning, conn = Mock(), Mock()
        learning.get_task.return_value = {'created_by': 'student'}
        learning._insert_learning_task.return_value = ({'id': 'review-1'}, True)
        args = (conn, learning, {'id': 'session', 'task_id': 'lesson'}, {'family_id': 'family', 'id': 'child'},
                {'id': 'course', 'version': '1', 'title': '天地人'})
        sync_journey(*args, self.state, {})
        self.assertEqual(learning._insert_learning_task.call_count, 1)
        self.assertTrue(learning._insert_learning_task.call_args.kwargs['slot'].startswith('tbr_'))
        sync_journey(*args, self.state, deepcopy(self.state))
        self.assertEqual(learning._insert_learning_task.call_count, 1)
        report_writes = [c for c in conn.execute.call_args_list if 'UPDATE learning_reports' in c.args[0]]
        self.assertIn('新情境独立通过 6/6', report_writes[-1].args[1][0])
        self.assertNotIn('score=', report_writes[-1].args[0])
        self.time = self.state['reviewDueAt']
        self.act('challenge', 'review')
        previous = deepcopy(self.state)
        self.finish('challenge')
        learning._insert_learning_task.return_value = ({'id': 'review-2'}, True)
        sync_journey(*args, self.state, previous)
        learning.mark_task_completed.assert_called_once()
        self.assertEqual(learning.mark_task_completed.call_args.kwargs['task_id'], 'review-1')
        self.assertEqual(self.state['reviewTaskId'], 'review-2')

    def test_all_authored_voice_assets_are_real_and_bound_to_manifest(self):
        from scripts.prepare_textbook_journey_audio import texts
        manifest = json.loads((journey.ROOT / 'audio-v2/manifest.json').read_text())
        for text in texts():
            asset = journey.audio_id(text) + '.wav'
            path = journey.audio_file(asset)
            self.assertEqual(manifest[asset]['text'], text)
            self.assertEqual(manifest[asset]['providerId'], 'qwen-tts')
            self.assertEqual(manifest[asset]['modelId'], 'qwen3-tts-flash')
            self.assertEqual(manifest[asset]['voice'], 'Serena')
            self.assertFalse(manifest[asset]['fallbackUsed'])
            self.assertEqual(path.read_bytes()[:4], b'RIFF')
            with wave.open(str(path)) as clip:
                self.assertGreater(clip.getnframes() / clip.getframerate(), .3)
        with self.assertRaises(ApiError): journey.audio_file('../anything')

if __name__ == '__main__': unittest.main()
