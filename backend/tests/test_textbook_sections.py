"""The two directory entries share real progress, with an independent check gate."""
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from content import textbook_sections as sections
from content.textbook_catalog import canonical
from core.errors import ApiError
from core.security import now_ms
from repositories.textbook_repository import TextbookRepository
from services.textbook_classroom_service import TextbookClassroomService
from tests.test_textbook_learning import IsolatedDatabase


class TextbookSectionTests(unittest.TestCase):
    def setUp(self):
        self.key, self.plan = next(iter(sections._REGISTRY.items()))
        self.first, self.second = (item['nodeId'] for item in self.plan['sections'])
        scene_ids = ['opening'] + [
            scene_id for item in self.plan['sections'] for scene_id in
            [item['firstSceneId'], *[f'page-{n}' for n in range(item['firstPage'] + 1, item['lastPage'])],
             item['lastSceneId']]
        ] + self.plan['checkSceneIds']
        self.classroom = 'tbpub_' + self.key[:24]
        scenes = []
        for index, scene_id in enumerate(scene_ids):
            kind = 'quiz' if scene_id == self.plan['checkSceneIds'][0] else 'slide'
            scenes.append({'id': scene_id, 'order': index, 'type': kind,
                'content': {'type': kind, **({'questions': []} if kind == 'quiz' else {})},
                'actions': [] if kind == 'quiz' else [
                    {'id': f'first-speech-{index}', 'type': 'speech'},
                    {'id': f'focus-{index}', 'type': 'spotlight'},
                    {'id': f'last-speech-{index}', 'type': 'speech'},
                ]})
        self.release = {'sha256': self.plan['releaseSha256'], 'classroomId': self.classroom,
            'media': [], 'classroom': {'id': self.classroom, 'stage': {'id': self.classroom}, 'scenes': scenes}}
        self.groups = sections.scene_groups(self.release, self.plan)
        self.course = {'id': 'course-a', 'version': '1', 'title': '两部分共用课件'}
        self.build = {'edition_id': 'book-a', 'revision_id': 'rev-a', 'node_id': self.first,
            'input_json': '{"subject":"chinese"}'}
        self.db = IsolatedDatabase()
        self.addCleanup(self.db.raw.close)
        self.db.execute("ALTER TABLE learning_sessions ADD COLUMN runtime_state_json TEXT")
        self.db.execute("ALTER TABLE learning_sessions ADD COLUMN updated_at INT")
        self.db.execute("ALTER TABLE children ADD COLUMN name TEXT")
        self.db.execute("""CREATE TABLE learning_session_runtime_records (id TEXT, session_id TEXT, seq INT,
            idempotency_key TEXT, scene_id TEXT, action_id TEXT, record_type TEXT, payload_json TEXT,
            response_json TEXT, created_at INT, UNIQUE(session_id, seq))""")
        self.db.execute("INSERT INTO children VALUES ('child-a','family-a','primary_1',1,'学生')")
        self.db.execute("INSERT INTO learning_sessions VALUES ('session','family-a','child-a','course-a','1','in_progress',NULL,0)")
        self.db.raw.commit()
        repo = TextbookRepository(self.db)
        repo.get_revision = Mock(return_value={})
        repo.manifest = Mock(return_value={'units': [{'unitId': 'unit-a',
            'lessons': [{'nodeId': self.first}, {'nodeId': self.second}]}]})
        auth = Mock()
        principal = {'id': 'principal', 'family_id': 'family-a', 'child_id': 'child-a'}
        auth.authenticate.return_value = {'principal': principal, 'session': {'id': 'student-session'}}
        auth.repository.get_session.return_value = {'revoked_at': None, 'refresh_expires_at': now_ms() + 60_000}
        auth._active_principal_and_device.return_value = (principal, {})
        self.service = TextbookClassroomService(repo, student_auth=auth, signing_key='section-test-only',
            public_url='http://runtime.invalid')
        self.service._release = Mock(return_value=(self.build, self.release, self.course))
        self.service._playback_release = Mock(return_value=self.release)
        self.service.learning.assign_catalog_task = Mock(return_value=({'id': 'task-a'}, False))
        self.service.learning.create_or_get_session = Mock(side_effect=lambda conn, **_: (
            self.service.learning.get_session(conn, family_id='family-a', session_id='session'), False))
        self.service.learning.mark_task_in_progress = Mock()
        self.service._complete = Mock()

    def launch(self, entry=None):
        launch = self.service.launch('student', self.key, entry=entry)
        ticket = parse_qs(urlparse(launch['launchUrl']).query)['ticket'][0]
        exchange = self.service.exchange(ticket)
        self.assertEqual(exchange['entry'], launch['entry'])
        self.assertEqual(exchange['learningSessionId'], 'session')
        self.assertEqual(exchange['classroomId'], self.classroom)
        return launch, exchange['runtimeToken']

    def record(self, token, kind, scene, index, *, sequence=None, action=None):
        payload = {'sceneId': scene['id'], 'sceneIndex': index}
        if kind in ('action_completed', 'section_speech_completed'):
            payload['actionId'] = action if action is not None else scene['actions'][-1]['id']
        return self.service.events(token, {'schemaVersion': 'mira.openmaic.student-runtime-event.v1',
            'type': kind, 'sequence': sequence or self.service.events(token)['nextSequence'], 'payload': payload})

    def test_exact_section_order_and_wrong_scope(self):
        first, first_token = self.launch()
        second, second_token = self.launch(self.second)
        self.assertEqual(first['entry'], self.first)
        self.assertFalse(first['sectionProgress']['checkReady'])
        self.assertEqual(self.service.validate(second_token)['entry'], self.second)
        self.assertNotEqual(first_token, second_token)
        for entry, token in [(first['entry'], first_token), (second['entry'], second_token)]:
            room = self.service.classroom(token)['classroom']
            expected = self.groups[entry]
            self.assertEqual(room['id'], self.classroom)
            self.assertEqual(room['scenes'], [{**scene, 'stageId': self.classroom} for scene in expected])
            self.assertIsNone(self.service.events(token)['resumeScene'])
            self.assertFalse(self.service.events(token)['completionReady'])
        with self.assertRaisesRegex(ApiError, '课堂入口无效'):
            self.launch('other-node')
        with self.assertRaisesRegex(ApiError, '页面身份无效'):
            self.record(first_token, 'scene_entered', self.groups[self.second][0], 0)
        with self.assertRaisesRegex(ApiError, '先进入当前讲解页面'):
            self.record(first_token, 'section_speech_completed', self.groups[self.first][0], 0)
        self.assertEqual(self.service.events(first_token)['lastSequence'], 0)
        with self.assertRaisesRegex(ApiError, '听完两部分'):
            self.launch(sections.CHECK_ENTRY)
        with self.assertRaisesRegex(ApiError, '共用小检查入口'):
            self.service.quiz(second_token, {'fake-question': 'answer'})

    def test_both_orders_unlock_only_after_playing_all_pages(self):
        for order in ((self.first, self.second), (self.second, self.first)):
            with self.subTest(order=order):
                self.db.execute('DELETE FROM learning_session_runtime_records')
                self.db.execute('UPDATE learning_sessions SET runtime_state_json=NULL')
                self.db.raw.commit()
                for entry in order:
                    _, token = self.launch(entry)
                    scenes = self.groups[entry]
                    for i, scene in enumerate(scenes):
                        self.record(token, 'scene_entered', scene, i)
                    self.assertFalse(self.service.section_progress('student', self.key, 'session')['checkReady'])
                    for i, scene in enumerate(scenes):
                        # The old exhausted-cursor marker does not prove sound played.
                        self.record(token, 'action_completed', scene, i)
                        self.record(token, 'section_speech_completed', scene, i)
                    self.assertEqual(self.service.events(token)['completedActionSceneIds'], [])
                    self.assertFalse(self.service.section_progress('student', self.key, 'session')['checkReady'])
                    with self.assertRaisesRegex(ApiError, '讲解配音不存在'):
                        self.record(token, 'section_speech_completed', scenes[0], 0,
                            action=scenes[0]['actions'][1]['id'])
                    for i, scene in enumerate(scenes):
                        self.record(token, 'section_speech_completed', scene, i, action=scene['actions'][0]['id'])
                    self.assertFalse(self.service.events(token)['completionReady'])
                    self.assertIsNone(self.service.events(token)['resumeScene'])
                    self.assertEqual(self.service.events(token)['completedActionSceneIds'], [s['id'] for s in scenes])
                    with self.assertRaisesRegex(ApiError, '完成学习和练习'):
                        self.record(token, 'classroom_completed', scenes[-1], len(scenes)-1)
                ready = self.service.section_progress('student', self.key, 'session')
                self.assertTrue(ready['checkReady'])
                check, check_token = self.launch(sections.CHECK_ENTRY)
                self.assertTrue(check['sectionProgress']['checkReady'])
                self.assertEqual([s['id'] for s in self.service.classroom(check_token)['classroom']['scenes']],
                    self.plan['checkSceneIds'])
                self.assertFalse(self.service.events(check_token)['completionReady'])
                quiz, recap = self.groups[sections.CHECK_ENTRY]
                self.record(check_token, 'scene_entered', quiz, 0)
                self.record(check_token, 'scene_entered', recap, 1)
                for action in recap['actions']:
                    if action['type'] == 'speech':
                        self.record(check_token, 'section_speech_completed', recap, 1, action=action['id'])
                self.assertEqual(self.service.events(check_token)['completedActionSceneIds'], [recap['id']])
                self.assertFalse(self.service.events(check_token)['completionReady'])
                self.service._complete.assert_not_called()
        with self.assertRaises(ApiError):
            self.service.section_progress('student', self.key, 'a-different-session')

    def test_historical_visits_or_total_completion_do_not_unlock_check(self):
        all_scenes = self.release['classroom']['scenes']
        state = {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 0, 'quiz': None,
            'visited': [s['id'] for s in all_scenes], 'actions': [s['actions'][-1]['id'] for s in all_scenes if s['actions']]}
        self.db.execute("UPDATE learning_sessions SET status='completed', runtime_state_json=?", (canonical(state),))
        self.db.raw.commit()
        _, token = self.launch(self.second)
        self.assertEqual(self.service.events(token)['completedActionSceneIds'], [])
        self.assertFalse(self.service.events(token)['completed'])
        self.assertFalse(self.record(token, 'action_completed', self.groups[self.second][0], 0)['completed'])
        self.assertFalse(self.service.section_progress('student', self.key, 'session')['checkReady'])
        with self.assertRaisesRegex(ApiError, '听完两部分'):
            self.launch(sections.CHECK_ENTRY)

    def test_repeated_or_wrong_page_audio_cannot_fill_an_unheard_line(self):
        _, token = self.launch(self.first)
        scene, other = self.groups[self.first][:2]
        self.record(token, 'scene_entered', scene, 0)
        with self.assertRaisesRegex(ApiError, '讲解配音不存在'):
            self.record(token, 'section_speech_completed', scene, 0, action=other['actions'][0]['id'])
        first = self.record(token, 'section_speech_completed', scene, 0)
        self.assertEqual(self.record(token, 'section_speech_completed', scene, 0, sequence=first['sequence']), first)
        self.record(token, 'section_speech_completed', scene, 0)
        self.assertEqual(self.service.events(token)['completedActionSceneIds'], [])
        self.record(token, 'section_speech_completed', scene, 0, action=scene['actions'][0]['id'])
        self.assertEqual(self.service.events(token)['completedActionSceneIds'], [scene['id']])


if __name__ == '__main__':
    unittest.main()
