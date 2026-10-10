"""Self-reported paper task completion must never manufacture a correct answer.

Exercises owned HTTP/domain contracts in isolated SQL with fake Tencent/TTS.
No provider network calls or existing child data are used.
"""
from copy import deepcopy
import json
from unittest import TestCase
from flask import Flask
from unittest.mock import patch

from services.homework_service import canonical
from services.homework_correction import correction_answer_state
from services.homework_answer_quality import reference_for_correction
from routes.api.v2.student_homework import student_homework_bp
from tests import test_homework_launch_loop as launch
from tests import test_report_homework_progress as report_fixtures


class HomeworkSelfReportedCompletionTest(TestCase):
    setUp = launch.HomeworkLaunchLoopTest.setUp
    create = launch.HomeworkLaunchLoopTest.create
    upload = launch.HomeworkLaunchLoopTest.upload
    queued = launch.HomeworkLaunchLoopTest.queued
    due = launch.HomeworkLaunchLoopTest.due
    events = launch.HomeworkLaunchLoopTest.events
    error = launch.HomeworkLaunchLoopTest.error
    paper = launch.HomeworkLaunchLoopTest.paper
    teach = launch.HomeworkLaunchLoopTest.teach

    def action(self, submission, action='self_complete', key='complete', *, token='student-a', revision=None):
        item = submission['items'][0]
        return self.service.student_action(token, submission['id'], item['id'], {
            'itemRevision': item['revision'] if revision is None else revision,
            'action': action, 'idempotencyKey': key})['submission']

    def state(self, submission):
        return self.db.execute('SELECT * FROM homework_items WHERE id=?',
            (submission['items'][0]['id'],)).fetchone()

    def test_completion_is_distinct_from_answer_and_preserves_wrong_review_source(self):
        submission = self.paper()
        original = self.state(submission)['result_json']
        original_events = self.events()
        calls = (self.transport.call_count, self.tencent.submit_question.call_count,
                 self.tencent.describe_question.call_count)
        child = self.db.execute('SELECT * FROM children WHERE id=?', ('child-a',)).fetchone()
        with self.db.transaction() as conn:
            original_pool = self.service.review_question_pool(conn, child)
        completed = self.action(submission)
        # The action replaces the student's detail snapshot. Preserve source
        # geometry so a successful mark cannot turn a question crop into a page.
        self.assertIn('paperStructure', submission)
        self.assertEqual(completed['paperStructure'], submission['paperStructure'])
        correction = completed['items'][0]['studentCorrection']
        self.assertEqual(correction['status'], 'self_reported')
        self.assertTrue(correction['selfReportedCompleted'])
        self.assertIsNone(correction['correct'])
        self.assertEqual(correction['attempts'], 0)
        self.assertFalse(correction['countsForAbility'])
        self.assertIsNone(correction['independent'])
        self.assertEqual(completed['summary']['corrected'], 0)
        self.assertEqual(completed['summary']['selfReportedCompleted'], 1)
        self.assertEqual(completed['studentSummary']['selfReportedCompleted'], 1)
        parent = self.service.get('parent-a', submission['id'])['submission']
        self.assertEqual(parent['items'][0]['studentAnswer'], '5')
        self.assertEqual(parent['items'][0]['studentCorrection'], correction)
        self.assertEqual(self.service.tutor.get('student-a', submission['id'], submission['items'][0]['id'])['tutor']['correction'], correction)
        self.assertEqual(self.state(submission)['result_json'], original)
        self.assertEqual(self.events(), original_events)
        with self.db.transaction() as conn:
            self.assertEqual(self.service.review_question_pool(conn, child), original_pool)
        self.assertEqual((self.transport.call_count, self.tencent.submit_question.call_count,
                         self.tencent.describe_question.call_count), calls)

    def test_idempotent_replay_never_reapplies_old_completion_or_reopen(self):
        submission = self.paper()
        completed = self.action(submission)
        first_at = completed['items'][0]['studentCorrection']['selfReportedCompletedAt']
        receipt = self.db.execute('SELECT * FROM homework_actions WHERE idempotency_key=?', ('complete',)).fetchone()
        self.tick[0] += 1234
        self.assertEqual(self.action(submission), completed)
        self.assertEqual(self.action(submission, key='another-complete')['items'][0]['studentCorrection']['selfReportedCompletedAt'], first_at)
        self.error('homework_idempotency_conflict', lambda: self.action(submission, 'reopen', 'complete'))
        opened = self.action(submission, 'reopen', 'reopen')
        self.assertEqual(opened['paperStructure'], submission['paperStructure'])
        self.assertFalse(opened['items'][0]['studentCorrection']['selfReportedCompleted'])
        self.assertEqual(self.action(submission), opened)
        self.assertEqual(self.db.execute('SELECT * FROM homework_actions WHERE id=?', (receipt['id'],)).fetchone(), receipt)
        self.tick[0] += 1000
        new = self.action(submission, key='new-complete')
        self.assertGreater(new['items'][0]['studentCorrection']['selfReportedCompletedAt'], first_at)
        self.assertEqual(self.action(submission, 'reopen', 'reopen'), new)

    def test_new_wrong_answer_revokes_self_report_and_correct_answer_is_highest_priority(self):
        submission = self.paper()
        item = submission['items'][0]
        self.action(submission)
        response = self.service.student_answer('student-a', submission['id'], item['id'], {
            'itemRevision': item['revision'], 'idempotencyKey': 'actual-wrong', 'answer': '2'})
        correction = response['submission']['items'][0]['studentCorrection']
        self.assertFalse(correction['selfReportedCompleted'])
        self.assertEqual((correction['status'], correction['correct'], correction['attempts']), ('needs_practice', False, 1))
        self.assertFalse(self.action(submission)['items'][0]['studentCorrection']['selfReportedCompleted'])
        marked = self.action(submission, key='mark-after-wrong')
        self.assertEqual(marked['items'][0]['studentCorrection']['correct'], False)
        self.assertEqual(marked['items'][0]['studentCorrection']['attempts'], 1)
        answered = self.teach(submission, mode='answer', message='三个', key='actual-correct')
        self.assertEqual(answered['tutor']['correction']['status'], 'corrected')
        self.assertFalse(answered['tutor']['correction']['selfReportedCompleted'])
        parent = self.service.get('parent-a', submission['id'])['submission']
        saved_answers = deepcopy(self.events())
        reopened = self.action(submission, 'reopen', 'after-correct')
        self.assertEqual(reopened['items'][0]['studentCorrection']['status'], 'corrected')
        self.assertEqual(self.events(), saved_answers)
        self.assertEqual(parent['summary']['corrected'], 1)
        self.assertEqual(parent['summary']['selfReportedCompleted'], 0)
        self.error('homework_already_corrected', lambda: self.action(submission, key='unnecessary-complete'))

    def test_revision_reference_readiness_deleted_and_foreign_scope_are_enforced(self):
        submission = self.paper()
        self.error('homework_not_found', lambda: self.action(submission, token='student-b'))
        self.error('homework_revision_conflict', lambda: self.action(submission, revision=99))
        self.error('homework_revision_conflict', lambda: self.action(submission, revision=True))
        marked = self.action(submission)
        raw = self.state(submission)
        result = json.loads(raw['result_json'])
        result['tencentRaw']['answer']['KnowledgePoints'] = ['参考已更新']
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?', (canonical(result), raw['id']))
        self.db.raw.commit()
        after = self.service.get('parent-a', submission['id'])['submission']['items'][0]['studentCorrection']
        self.assertFalse(after['selfReportedCompleted'])
        self.error('homework_reference_changed', lambda: self.action(submission))
        self.db.execute('UPDATE homework_items SET result_json=?,revision=revision+1 WHERE id=?', (raw['result_json'], raw['id']))
        self.db.raw.commit()
        self.assertFalse(self.service.get('parent-a', submission['id'])['submission']['items'][0]['studentCorrection']['selfReportedCompleted'])
        self.db.execute('UPDATE homework_items SET revision=?,media_json=? WHERE id=?', (raw['revision'], '{}', raw['id']))
        self.db.raw.commit()
        self.error('homework_media_preparing', lambda: self.action(submission, key='not-ready'))
        self.service.delete('parent-a', submission['id'], {'revision': submission['revision']})
        self.error('homework_not_found', lambda: self.action(submission))
        self.assertTrue(marked['items'][0]['studentCorrection']['selfReportedCompleted'])

    def test_unverified_reference_cannot_be_marked_complete(self):
        submission = self.paper(contradiction=True)
        before = self.db.execute('SELECT COUNT(*) n FROM homework_actions').fetchone()['n']
        self.error('homework_student_item_unsupported', lambda: self.action(submission))
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_actions').fetchone()['n'], before)
        self.assertEqual(self.events(), [])

    def test_hint_contract_remains_backward_compatible_without_a_new_key(self):
        submission = self.paper()
        item = submission['items'][0]
        result = self.service.student_action('student-a', submission['id'], item['id'], {'action': 'hint', 'itemRevision': item['revision']})
        self.assertTrue(result['submission']['items'][0]['studentCorrection']['hintViewed'])

    def test_http_contract_requires_key_and_child_scope_without_accepting_fake_correctness(self):
        submission = self.paper()
        item = submission['items'][0]
        app = Flask(__name__)
        app.register_blueprint(student_homework_bp, url_prefix='/api/v2/student/learning')
        client = app.test_client()
        path = f"/api/v2/student/learning/homework/{submission['id']}/items/{item['id']}/actions"
        data = {'action': 'self_complete', 'itemRevision': item['revision']}
        with patch('routes.api.v2.student_homework.service', return_value=self.service):
            self.assertEqual(client.post(path, json=data, headers={'Authorization': 'Bearer student-a'}).status_code, 400)
            self.assertEqual(client.post(path, json={**data, 'idempotencyKey': 'http'}, headers={'Authorization': 'Bearer student-b'}).status_code, 404)
            response = client.post(path, json={**data, 'idempotencyKey': 'http', 'correct': True}, headers={'Authorization': 'Bearer student-a'})
        self.assertEqual(response.status_code, 200)
        value = response.get_json()['submission']['items'][0]['studentCorrection']
        self.assertTrue(value['selfReportedCompleted'])
        self.assertIsNone(value['correct'])
        self.assertEqual(value['attempts'], 0)


class SelfReportedCompletionReportTest(TestCase):
    setUp = report_fixtures.ReportHomeworkProgressTest.setUp
    submission = report_fixtures.ReportHomeworkProgressTest.submission
    item = report_fixtures.ReportHomeworkProgressTest.item
    report = report_fixtures.ReportHomeworkProgressTest.report

    def mark(self, identity, when):
        item = self.db.execute('SELECT * FROM homework_items WHERE id=?', (identity,)).fetchone()
        row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (item['submission_id'],)).fetchone()
        from services.homework_answer_quality import attach_reference_answer_layout, reviewed_result
        page = self.db.execute('SELECT * FROM homework_pages WHERE id=?', (item['page_id'],)).fetchone()
        reference = reference_for_correction(attach_reference_answer_layout(self.db, row, item, reviewed_result(row, item, page)))
        correction = json.loads(item['correction_json'])
        correction['selfReportedCompletion'] = {'schemaVersion': 'mira.homework-self-reported-completion.v1',
            'completed': True, 'completedAt': when, 'itemRevision': item['revision'],
            'referenceDigest': reference['digest'], 'answerStateSha256': correction_answer_state(correction)}
        self.db.execute('UPDATE homework_items SET correction_json=? WHERE id=?', (json.dumps(correction), identity))

    def test_self_report_is_exclusive_from_corrected_and_counted_without_assistance(self):
        self.submission()
        self.item('manual')
        self.item('retry', correction={'correct': False, 'attempts': 1, 'updatedAt': report_fixtures.at('2026-09-29')})
        self.item('corrected', correction={'correct': True, 'attempts': 1, 'updatedAt': report_fixtures.at('2026-09-29')})
        self.item('not-started')
        self.mark('manual', report_fixtures.at('2026-09-29'))
        self.mark('corrected', report_fixtures.at('2026-09-29'))
        before = self.db.raw.total_changes
        report = self.report()
        self.assertEqual({key: report[key] for key in ('total', 'corrected', 'selfReportedCompleted', 'inProgress', 'notStarted', 'assisted')},
            {'total': 4, 'corrected': 1, 'selfReportedCompleted': 1, 'inProgress': 1, 'notStarted': 1, 'assisted': 0})
        self.assertEqual(report['total'], sum(report[key] for key in ('corrected', 'selfReportedCompleted', 'inProgress', 'notStarted')))
        self.assertFalse(report['countsForAbility'])
        self.assertIsNone(report['independent'])
        self.assertEqual(self.db.raw.total_changes, before)

    def test_current_self_report_selects_old_homework_for_today_and_stale_binding_does_not(self):
        self.submission('old', day='2026-09-28')
        self.item('manual', paper='old')
        when = report_fixtures.at('2026-09-30')
        self.mark('manual', when)
        self.assertEqual(self.report()['submissionCount'], 0)
        report = self.report('2026-09-30')
        self.assertEqual((report['submissionCount'], report['selfReportedCompleted']), (1, 1))
        self.assertEqual(report['entries'][0]['lastActivityAt'], when)
        self.db.execute('UPDATE homework_items SET revision=2 WHERE id=?', ('manual',))
        self.assertEqual(self.report('2026-09-30')['submissionCount'], 0)
