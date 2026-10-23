"""Native classroom activities: persistence, honest evidence, and private answers."""
from copy import deepcopy
import json
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import Mock

from content import textbook_activity as activity
from content.textbook_catalog import canonical
from core.errors import ApiError
from services.textbook_classroom_service import TextbookClassroomService


def release_fixture():
    prefix = '/api/classroom-media/tbpub_test/audio/'
    ids = {a for s in activity.PLAN['skills'].values() for a in s['learnAudio']}
    ids.update('review_speaker-' + p for p in ('coral', 'teal'))
    ids.update('review_cue-' + p for p in ('me', 'you', 'he'))
    ids.add(activity.PLAN['roleSwitchAudio'])
    actions = [{'id': a, 'audioUrl': prefix + a + '.wav'} for a in ids]
    questions = [{'id': f'q{i}', 'type': 'single', 'question': '听题选字',
        'options': [{'value': 'A', 'label': activity.PLAN['skills'][skill]['word']},
                    {'value': 'B', 'label': '石头'}], 'answer': ['A'],
        'points': 1, 'analysis': '正确讲解', 'questionAudioUrl': prefix + f'q{i}.wav'}
        for i, skill in enumerate(activity.PLAN['quizSkills'])]
    return {'sha256': activity.PLAN['releaseSha256'], 'classroomId': 'test',
        'media': [{'path': a['audioUrl'], 'mimeType': 'audio/wav'} for a in actions]
            + [{'path': q['questionAudioUrl'], 'mimeType': 'audio/wav'} for q in questions]
            + [{'path': '/api/classroom-media/tbpub_test/media/garden.webp', 'mimeType': 'image/webp'}],
        'classroom': {'scenes': [
            {'id': activity.PLAN['sceneIds']['games'], 'type': 'interactive', 'order': 0, 'actions': actions,
             'content': {'type': 'interactive', 'html': '<p>legacy</p>'}},
            {'id': activity.PLAN['sceneIds']['challenge'], 'type': 'quiz', 'order': 1, 'actions': [],
             'content': {'questions': questions}}]}}


class NativeActivityTests(unittest.TestCase):
    def setUp(self):
        self.release = release_fixture()
        self.state = activity.initial({}, self.release)

    def act(self, action, choice=None, section='challenge'):
        data = {'section': section, 'version': self.state['version'], 'action': action}
        if choice is not None:
            data['choice'] = choice
        activity.advance(self.state, section, data, self.release)

    def finish(self, section):
        while self.state[section]['phase'] != 'done':
            current = activity.item(self.state[section], self.release)
            if not self.state[section].get('feedback', {}).get('canNext'):
                self.act('answer', current['targets'][0], section)
            self.act('next', section=section)

    def test_only_exact_release_gets_native_scenes_and_snapshot_is_unchanged(self):
        before = deepcopy(self.release)
        public = deepcopy(self.release['classroom'])
        activity.attach(public, self.release)
        self.assertEqual(public['scenes'][0]['miraActivity']['section'], 'games')
        self.assertEqual(public['scenes'][0]['actions'], [])
        self.assertNotIn('html', public['scenes'][0]['content'])
        self.assertEqual(self.release, before)
        other = deepcopy(self.release['classroom'])
        activity.attach(other, {**self.release, 'sha256': 'another'})
        self.assertNotIn('miraActivity', other['scenes'][0])

    def test_public_question_does_not_leak_key_skill_hint_or_other_question_answers(self):
        view = activity.public_view(self.state, self.release)['challenge']
        for private in ('answer', 'targets', 'skill', 'word', 'hint', 'explanation'):
            self.assertNotIn(private, view)
        self.assertEqual(view['hintAudio'], [])
        self.assertNotIn('正确讲解', json.dumps(view, ensure_ascii=False))

    def test_wrong_answer_and_hints_lead_to_targeted_repair_without_inflating_score(self):
        self.act('answer', 'B'); self.act('next')
        self.act('hint'); self.act('answer', 'A'); self.act('next')
        self.act('adult'); self.act('answer', 'A'); self.act('next')
        for _ in range(3):
            self.act('answer', 'A'); self.act('next')
        self.assertEqual(self.state['challenge']['phase'], 'repair')
        self.assertEqual(activity.repair_skills(self.state['challenge']), ['sky', 'earth', 'person'])
        before = activity.quiz_result(self.state, self.release)
        self.assertEqual((before['correctCount'], before['independentCorrectCount'], before['hintCount'], before['adultHelpCount']), (5, 3, 1, 1))
        self.finish('challenge')
        self.assertEqual(activity.quiz_result(self.state, self.release), before)
        view = activity.public_view(self.state, self.release)
        self.assertEqual(view['evidence']['transferIndependent'], 6)

    def test_three_people_are_valid_person_targets_but_ground_is_not(self):
        for person in ('coral', 'teal', 'yellow'):
            self.state = activity.initial({}, self.release)
            self.state['games']['index'] = 2
            self.act('answer', 'earth', 'games')
            self.assertFalse(self.state['games']['feedback']['canNext'])
            self.act('hint', section='games')
            self.act('answer', person, 'games')
            record = self.state['games']['records'][0]
            self.assertFalse(record['correct'])
            self.assertTrue(record['solved'])
            self.assertEqual(record['attempts'], 2)

    def test_roles_change_with_the_speaker(self):
        self.state['games'].update(phase='roles', index=0)
        self.assertEqual(activity.item(self.state['games'], self.release)['targets'], ['teal'])
        self.state['games']['index'] = 3
        self.assertEqual(activity.item(self.state['games'], self.release)['targets'], ['coral'])
        self.state['games']['index'] = 4
        self.assertEqual(activity.item(self.state['games'], self.release)['targets'], ['teal'])
        self.act('hint', section='games')
        cues = activity.public_view(self.state, self.release)['games']['hintAudio']
        self.assertTrue(cues[0].endswith(activity.PLAN['roleSwitchAudio'] + '.wav'))

    def test_reload_and_replay_preserve_quiz_and_first_game_evidence(self):
        self.finish('games'); self.finish('challenge')
        first = deepcopy(self.state['games']['records'])
        self.state = activity.initial({'textbookPlay': json.loads(json.dumps(self.state))}, self.release)
        evidence = activity.public_view(self.state, self.release)['evidence']
        self.act('replay', section='games')
        self.assertTrue(activity.complete({'textbookPlay': self.state}))
        self.finish('games')
        self.assertEqual(self.state['games']['firstRun'], first)
        self.assertEqual(activity.public_view(self.state, self.release)['evidence'], evidence)

    def test_rejects_skip_duplicate_stale_and_invalid_payloads(self):
        for invalid in [None, [], {}, {'section': 'challenge', 'version': True, 'action': 'hint'},
            {'section': 'challenge', 'version': 0, 'action': 'next'},
            {'section': 'challenge', 'version': 0, 'action': 'answer', 'choice': 'C'},
            {'section': 'challenge', 'version': 0, 'action': 'answer', 'choice': 'A', 'correct': True}]:
            with self.assertRaises(ApiError):
                activity.advance(self.state, 'challenge', invalid, self.release)
        self.act('answer', 'A')
        with self.assertRaises(ApiError):
            self.act('answer', 'B')
        with self.assertRaises(ApiError):
            activity.advance(self.state, 'challenge', {'section': 'challenge', 'version': 0, 'action': 'next'}, self.release)

    def test_old_scores_are_kept_and_only_followup_is_added(self):
        self.finish('challenge')
        score = activity.quiz_result(self.state, self.release)
        restored = activity.initial({'quiz': score}, self.release)
        self.assertEqual(restored['challenge']['phase'], 'transfer')
        self.assertEqual(activity.quiz_result(restored, self.release)['score'], score['score'])

    def test_classroom_cannot_complete_until_games_and_followup_are_done(self):
        scenes = self.release['classroom']['scenes']
        progress = {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 0,
            'visited': [s['id'] for s in scenes], 'actions': [], 'quiz': {'results': []}}
        session = {'id': 'session', 'status': 'in_progress', 'runtime_state_json': canonical(progress)}
        self.assertFalse(TextbookClassroomService._status(session, self.release)['completionReady'])
        self.finish('games'); self.finish('challenge')
        progress['textbookPlay'] = self.state
        session['runtime_state_json'] = canonical(progress)
        result = TextbookClassroomService._status(session, self.release)
        self.assertTrue(result['completionReady'])
        # Completing a native activity does not fabricate heard-audio evidence.
        self.assertNotIn(activity.PLAN['sceneIds']['games'], result['completedActionSceneIds'])

    def test_parent_report_distinguishes_independent_answers_and_help(self):
        self.act('hint'); self.act('answer', 'A'); self.act('next')
        self.act('adult'); self.act('answer', 'A'); self.act('next')
        self.finish('challenge')
        result = activity.quiz_result(self.state, self.release)
        service = object.__new__(TextbookClassroomService)
        service.learning = Mock()
        service._report(None, {'id': 'session', 'task_id': 'task'}, {'family_id': 'family', 'id': 'child'},
            {'id': 'course', 'version': '1', 'title': '天地人', 'grade_code': 'primary_1', 'subject': 'chinese'}, result)
        report = service.learning.create_or_get_report.call_args.kwargs
        self.assertEqual((report['correct_count'], report['independent_correct_count'], report['hint_count']), (6, 4, 1))
        self.assertIn('大人帮助 1 题', report['summary'])
        self.assertIn('课堂', report['next_step'])

    def test_resume_prefers_unfinished_activity_over_highest_visited_slide(self):
        scenes = self.release['classroom']['scenes']
        progress = {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 0,
            'visited': [s['id'] for s in scenes], 'actions': [], 'quiz': None, 'textbookPlay': self.state}
        session = {'id': 'session', 'status': 'in_progress', 'runtime_state_json': canonical(progress)}
        self.assertEqual(TextbookClassroomService._status(session, self.release)['resumeScene']['sceneId'],
                         activity.PLAN['sceneIds']['games'])
        self.finish('games')
        session['runtime_state_json'] = canonical(progress)
        self.assertEqual(TextbookClassroomService._status(session, self.release)['resumeScene']['sceneId'],
                         activity.PLAN['sceneIds']['challenge'])

    def test_authentication_and_existing_session_persistence(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE learning_sessions (id TEXT, runtime_state_json TEXT, updated_at INTEGER)')
        progress = {'schemaVersion': 'mira.textbook.progress.v1', 'visited': ['original'], 'actions': ['audio'], 'lastSequence': 9, 'quiz': None}
        conn.execute('INSERT INTO learning_sessions VALUES (?, ?, 0)', ('session', canonical(progress)))
        @contextmanager
        def transaction():
            with conn:
                yield conn
        service = object.__new__(TextbookClassroomService)
        service.repository = Mock(); service.repository.transaction = transaction
        service.learning = Mock()
        service.learning.get_session.side_effect = lambda *args, **kwargs: dict(conn.execute('SELECT * FROM learning_sessions').fetchone())
        service._authority = Mock(return_value=(None, {'family_id': 'family'}, {}, self.release, {}, {'id': 'session'}))
        service._playback_release = Mock(side_effect=deepcopy)
        service.play('authorized', {'section': 'games', 'version': 0, 'action': 'hint'})
        restored = service.play('authorized')
        self.assertTrue(restored['games']['hintUsed'])
        saved = json.loads(conn.execute('SELECT runtime_state_json FROM learning_sessions').fetchone()[0])
        self.assertEqual((saved['visited'], saved['actions'], saved['lastSequence']), (['original'], ['audio'], 9))
        self.assertTrue(service.learning.get_session.call_args.kwargs['for_update'])
        service._authority.side_effect = ApiError('textbook_session_invalid', 'revoked', 401)
        with self.assertRaises(ApiError):
            service.play('revoked')
        conn.close()


if __name__ == '__main__':
    unittest.main()
