import unittest
from unittest.mock import Mock, patch

from core.errors import ApiError
from services.textbook_classroom_service import TextbookClassroomService
from services.textbook_quiz_evidence import record_quiz_evidence


class TextbookQuizEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            {'id': 'q1', 'skill': 'counting', 'type': 'single', 'question': 'How many?',
             'options': [{'value': 'a'}, {'value': 'b'}], 'answer': ['a'], 'analysis': 'Count them.'},
            {'id': 'q2', 'type': 'single', 'question': 'Which?', 'options': [{'value': 'b'}],
             'answer': 'b', 'analysis': 'Look again.'},
        ]
        self.classroom = {'scenes': [{'type': 'quiz', 'content': {'questions': self.items}}]}
        self.results = [{'questionId': 'q1', 'response': 'b', 'correct': False},
                        {'questionId': 'q2', 'response': 'b', 'correct': True}]
        self.session = {'id': 'session', 'family_id': 'family', 'child_id': 'child'}
        self.course = {'id': 'course', 'version': '1', 'subject': 'math', 'grade_code': 'grade',
                       'title': 'Title'}

    @patch('services.textbook_quiz_evidence.record_course_answers')
    def test_maps_questions_and_results(self, record):
        self.assertEqual(record_quiz_evidence('conn', self.session, self.course, self.classroom, self.results, 123), 2)
        record.assert_called_once_with('conn', self.session, self.course, [
            {'id': 'q1', 'skill': 'counting', 'type': 'single', 'prompt': 'How many?',
             'options': self.items[0]['options'], 'answer': ['a'], 'explanation': 'Count them.'},
            {'id': 'q2', 'skill': None, 'type': 'single', 'prompt': 'Which?',
             'options': self.items[1]['options'], 'answer': 'b', 'explanation': 'Look again.'},
        ], [
            {'questionId': 'q1', 'answer': 'b', 'correct': False, 'attemptNumber': 1, 'hintUsed': False},
            {'questionId': 'q2', 'answer': 'b', 'correct': True, 'attemptNumber': 1, 'hintUsed': False},
        ], 123)

    @patch('services.textbook_quiz_evidence.record_course_answers')
    def test_empty_results_do_not_record(self, record):
        self.assertEqual(record_quiz_evidence(None, None, None, None, [], 123), 0)
        record.assert_not_called()

    def test_missing_skill_uses_question_id_for_knowledge_identity(self):
        with patch('services.learning_evidence_service.enabled', return_value=True), \
             patch('services.learning_evidence_service.record_answer') as record:
            record_quiz_evidence('conn', self.session, self.course, self.classroom, [self.results[1]], 123)
        question = record.call_args.kwargs['question']
        self.assertEqual(question['knowledgeId'], 'math:grade:course:q2')
        self.assertEqual(question['knowledgeLabel'], 'Title')
        self.assertFalse(record.call_args.kwargs['independent'])

    def test_quiz_records_only_new_results_after_guards(self):
        conn = Mock()
        repository = Mock()
        repository.transaction.return_value.__enter__ = Mock(return_value=conn)
        repository.transaction.return_value.__exit__ = Mock(return_value=False)
        service = TextbookClassroomService(repository, student_auth=Mock(), signing_key='test',
                                           public_url='https://example.invalid', course_file_store=Mock())
        release = {'classroom': self.classroom}
        service._authority = Mock(return_value=({}, {'family_id': 'family'}, {}, release, self.course, self.session))
        service.learning = Mock()
        service.learning.get_session.return_value = self.session
        state = {'quiz': None}
        service._state = Mock(return_value=state)
        service._report = Mock()

        def grade(_release, answers, **kwargs):
            results = [r for r in self.results if r['questionId'] in answers]
            return {'results': results, 'totalQuestions': len(results),
                    'correctCount': sum(r['correct'] for r in results)}

        with patch('services.textbook_classroom_service.grade_answers', side_effect=grade), \
             patch('services.textbook_classroom_service.textbook_activity.supported', return_value=False), \
             patch('services.textbook_classroom_service.now_ms', return_value=123), \
             patch('services.textbook_classroom_service.record_quiz_evidence') as record:
            service.quiz('token', {'q1': 'b'})
            record.assert_called_once_with(conn, self.session, self.course, self.classroom, [self.results[0]], 123)
            record.reset_mock()
            with self.assertRaises(ApiError) as caught:
                service.quiz('token', {'q1': 'a'})
            self.assertEqual(caught.exception.code, 'textbook_answers_already_submitted')
            record.assert_not_called()
            service.quiz('token', {'q1': 'b', 'q2': 'b'})
            record.assert_called_once_with(conn, self.session, self.course, self.classroom, [self.results[1]], 123)
            record.reset_mock()
            service.quiz('token', {'q1': 'b', 'q2': 'b'})
            record.assert_not_called()


if __name__ == '__main__':
    unittest.main()
