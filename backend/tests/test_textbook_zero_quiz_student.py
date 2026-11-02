import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.errors import ApiError
from repositories.learning_repository import LearningRepository
from services.learning_service import LearningService
from services.textbook_classroom_service import TextbookClassroomService
from services.textbook_publication_service import require_textbook_completion_capability


POLICY = 'verified-frozen-no-native-quiz'


class ZeroQuizStudentTest(unittest.TestCase):
    def setUp(self):
        self.course = {'id': 'course', 'version': '1', 'status': 'published', 'quality_status': 'released',
            'content_origin': 'openmaic_generated', 'content_json': json.dumps({
                'schemaVersion': 'mira.learning.fixed-textbook-course.v1', 'questions': [],
                'assessmentPolicy': POLICY, 'outcomeMode': 'ungraded'})}
        self.learning = object.__new__(LearningService)
        self.learning.repository = SimpleNamespace(parse_json=LearningRepository.parse_json, database=object())

    def test_empty_course_requires_an_actual_valid_published_build(self):
        fake = Mock(); fake.transaction.return_value.__enter__ = Mock(return_value=object())
        fake.transaction.return_value.__exit__ = Mock(return_value=False)
        fake.course_build.return_value = None
        with patch('repositories.textbook_repository.TextbookRepository', return_value=fake):
            with self.assertRaises(ApiError): self.learning._questions(self.course)
            fake.course_build.return_value = {'edition_id': 'book', 'revision_id': 'rev'}
            fake.get_revision.return_value = {'manifest_json': '{}'}; fake.manifest.return_value = {}
            with patch('content.textbook_release.validate_release', return_value={'assessmentPolicy': POLICY}):
                self.assertEqual(self.learning._questions(self.course), [])
            with patch('content.textbook_release.validate_release', side_effect=ApiError('x', 'invalid', 409)):
                with self.assertRaises(ApiError): self.learning._questions(self.course)
        forged = dict(self.course, content_origin='manual')
        with self.assertRaises(ApiError): self.learning._questions(forged)

    def test_no_questions_do_not_count_as_authoritative_answer_completion(self):
        self.learning._questions = Mock(return_value=[])
        self.learning._verified_zero_quiz_textbook = Mock(return_value=True)
        self.learning._runtime_authority_session_course = Mock(return_value=({'answers_json': '[]'}, self.course))
        self.assertFalse(self.learning.authoritative_runtime_questions_complete(None, authority={}))

    def test_publication_stops_until_real_zero_quiz_completion_exists(self):
        require_textbook_completion_capability(zero_native_quiz=False)
        with self.assertRaises(ApiError) as error:
            require_textbook_completion_capability(zero_native_quiz=True)
        self.assertEqual(error.exception.code, 'textbook_interaction_completion_unavailable')

    def test_publication_requires_every_supported_activity_and_exact_binding(self):
        binding = {'editionId': 'pep-chinese-g1-upper-2022-standard',
                   'revisionId': '20260924-directory-3', 'nodeId': 'u5-l1'}
        room = {'scenes': [{'id': 'scene-p1', 'order': 0, 'type': 'slide'}] + [
            {'id': f'scene-p{i}', 'order': i-1, 'type': 'interactive',
             'content': {'html': f'<main>activity {i}</main>'}} for i in range(2, 13)]}
        contract = require_textbook_completion_capability(
            zero_native_quiz=True, classroom=room, binding=binding)
        self.assertEqual(len(contract['scenes']), 11)
        with self.assertRaises(ApiError):
            require_textbook_completion_capability(zero_native_quiz=True,
                classroom=room, binding={**binding, 'nodeId': 'another-lesson'})
        with self.assertRaises(ApiError):
            require_textbook_completion_capability(zero_native_quiz=True,
                classroom={'scenes': room['scenes'][:-1]}, binding=binding)

    @staticmethod
    def release(policy=POLICY):
        return {'classroomId': 'classroom', 'sha256': 'a' * 64, 'assessmentPolicy': policy,
                'classroom': {'scenes': [{'id': 's1', 'order': 0, 'actions': [{'id': 'optional-cue'}]},
                                         {'id': 's2', 'order': 1, 'actions': [{'id': 'optional-cue-2'}]}]}}

    def test_page_visits_record_viewing_without_unlocking_course_completion(self):
        state = {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 0,
                 'visited': ['s1'], 'actions': [], 'quiz': None}
        session = {'id': 'session', 'status': 'in_progress', 'runtime_state_json': json.dumps(state)}
        self.assertFalse(TextbookClassroomService._status(session, self.release())['completionReady'])
        state['visited'] = ['s1', 'fake']; session['runtime_state_json'] = json.dumps(state)
        self.assertFalse(TextbookClassroomService._status(session, self.release())['completionReady'])
        state['visited'] = ['s1', 's2']; session['runtime_state_json'] = json.dumps(state)
        self.assertTrue(TextbookClassroomService._status(session, self.release())['viewingComplete'])
        self.assertFalse(TextbookClassroomService._status(session, self.release())['completionReady'])
        # An iframe snapshot, including a forged done flag, is only UI state.
        state['activitySnapshots'] = {'state': {'phase': 'done', 'completed': True}}
        state['quiz'] = {'results': [{'questionId': 'forged', 'correct': True}]}
        session['runtime_state_json'] = json.dumps(state)
        self.assertFalse(TextbookClassroomService._status(session, self.release())['completionReady'])
        self.assertEqual(TextbookClassroomService._status(session, self.release())['answeredQuestionIds'], [])
        self.assertFalse(TextbookClassroomService._status(session, self.release('ordinary'))['completionReady'])

    def test_completion_records_browsing_without_grade_or_parent(self):
        service = object.__new__(TextbookClassroomService); service.learning = Mock()
        conn = Mock(); session = {'id': 'session', 'status': 'in_progress', 'task_id': 'task'}
        child = {'family_id': 'family'}
        service._complete(conn, session, child, self.course, None)
        summary = service.learning.mark_task_completed.call_args.kwargs['summary']
        self.assertIn('已浏览', summary); self.assertIn('未进行独立能力测评', summary)
        self.assertNotIn('家长', summary); service.learning.create_or_get_report.assert_not_called()

    def test_zero_quiz_submission_is_rejected_without_grade(self):
        service = object.__new__(TextbookClassroomService); service.learning = Mock(); service.repository = Mock()
        session = {'id': 'session', 'status': 'in_progress', 'runtime_state_json': None}
        service._authority = Mock(return_value=(None, {'family_id': 'family'}, None, self.release(), self.course, session))
        @contextmanager
        def transaction(): yield object()
        service.repository.transaction.side_effect = transaction
        service.learning.get_session.return_value = session
        self.assertEqual(service.quiz('token'), {'ok': True, 'result': None, 'partial': None})
        with self.assertRaises(ApiError) as error: service.quiz('token', {'any': 'A'})
        self.assertEqual(error.exception.code, 'textbook_activity_ungraded')
        service.learning.create_or_get_report.assert_not_called()

    def test_final_event_rejects_browsing_only_without_scores_or_task_completion(self):
        state = {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 0,
                 'visited': ['s1', 's2'], 'actions': [], 'quiz': None}
        session = {'id': 'session', 'status': 'in_progress', 'task_id': 'task',
                   'runtime_state_json': json.dumps(state)}
        class Cursor:
            def __init__(self, row=None): self.row = row
            def fetchone(self): return self.row
        class Connection:
            def __init__(self): self.record = None; self.sql = []
            def execute(self, sql, args=()):
                self.sql.append(sql)
                if sql.startswith('SELECT * FROM learning_session_runtime_records'):
                    return Cursor(self.record)
                if sql.startswith('INSERT INTO learning_session_runtime_records'):
                    self.record = {'payload_json': args[7], 'response_json': args[8]}
                return Cursor()
        conn = Connection(); service = object.__new__(TextbookClassroomService)
        service.learning = Mock(); service.repository = Mock()
        service._authority = Mock(return_value=(None, {'family_id': 'family'}, None, self.release(), self.course, session))
        @contextmanager
        def transaction(): yield conn
        service.repository.transaction.side_effect = transaction
        service.repository.parse.side_effect = lambda value: json.loads(value) if isinstance(value, str) else value
        service.learning.get_session.return_value = session
        event = {'schemaVersion': 'mira.openmaic.student-runtime-event.v1', 'sequence': 1,
                 'type': 'classroom_completed', 'payload': {'sceneIndex': 1, 'sceneId': 's2'}}
        with self.assertRaises(ApiError) as error: service.events('token', event)
        self.assertEqual(error.exception.code, 'textbook_learning_incomplete')
        self.assertEqual(sum(sql.startswith('INSERT INTO learning_session_runtime_records') for sql in conn.sql), 0)
        service.learning.mark_task_completed.assert_not_called()
        service.learning.create_or_get_report.assert_not_called()
        self.assertFalse(any('answers_json' in sql or 'correct_count' in sql for sql in conn.sql))


if __name__ == '__main__': unittest.main()
