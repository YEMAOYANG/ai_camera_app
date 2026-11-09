import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from courseware.tools.native_author import digest, native_job


class NativeAuthorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.work = Path(directory.name)
        self.standard = self.work / 'standard.md'
        self.standard.write_text('Current courseware standard')
        self.source = self.work / 'draft.json'
        self.draft = {
            'schemaVersion': 'mira.courseware.openmaic-generation-input.v1',
            'binding': {**dict(editionId='edition', revisionId='revision', nodeId='node', unitId='unit'),
                        'classHours': ['one', 'two']},
            'request': '为一年级编写一门计数课',
            'qualityRules': ['一屏一事'],
            'pagePlan': [{'goal': '逐物点数'}],
            'assessmentBlueprint': [{'skill': 'count'}],
            'assetPlan': [{'assetKey': 'cover'}],
            'scopeReview': {'status': 'current-standard-g0-reviewed', 'objectives': ['逐物点数'],
                            'coveredOfficialHours': ['one', 'two'], 'videoStatus': 'waived',
                            'excludedTopics': ['乘法'], 'officialNotes': 'private/path'},
            'sourceInput': {'standardSha256': digest(self.standard.read_bytes())},
            'generationControls': dict(serverRoutedDeepSeekRequired=True, automaticImageGeneration=False,
                                       automaticVideoGeneration=False, automaticTts=False, publication=False),
        }
        self.save_source()
        self.calls = []

    def save_source(self):
        self.source.write_text(json.dumps(self.draft), encoding='utf-8')

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == '/api/health':
            return {'runtimePolicy': {'modelPolicy': {'policyId': 'configured-policy',
                'coursewareCreator': {'providerId': 'deepseek', 'modelId': 'configured-model'},
                'structuredScene': {'modelId': 'configured-model'}}}}
        if method == 'POST':
            return {'jobId': 'test-job', 'status': 'queued'}
        if path.endswith('/test-job'):
            return {'jobId': 'test-job', 'status': 'succeeded', 'result': {'classroomId': 'test-room'}}
        return {'classroom': {'id': 'test-room', 'stage': {'id': 'test-room'}, 'scenes': [{'id': 'scene'}]}}

    def step(self, action, request=None):
        return native_job(self.work, action, self.source, self.standard, request=request or self.request)

    def test_only_one_native_dispatch_and_private_readback(self):
        self.step('prepare')
        self.assertEqual([], self.calls)
        self.assertEqual('test-job', self.step('start')['jobId'])
        self.step('start')
        posts = [body for method, _, body in self.calls if method == 'POST']
        self.assertEqual(1, len(posts))
        self.assertEqual({False}, {posts[0][key] for key in
                                   ('enableImageGeneration', 'enableVideoGeneration', 'enableTTS', 'enableWebSearch')})
        self.assertNotIn('private/path', posts[0]['requirement'])
        result = self.step('poll')
        self.assertFalse(result['publicationAllowed'])
        self.assertEqual('test-room', result['classroomId'])

    def test_ambiguous_post_retains_claim_and_is_never_repeated(self):
        def interrupted(method, path, body=None):
            if method == 'POST':
                self.calls.append((method, path, body))
                raise TimeoutError('Response was lost')
            return self.request(method, path, body)

        self.step('prepare')
        with self.assertRaises(TimeoutError):
            self.step('start', interrupted)
        with self.assertRaisesRegex(ValueError, 'outcome unknown'):
            self.step('start')
        self.assertEqual(1, sum(method == 'POST' for method, _, _ in self.calls))

    def test_incomplete_scope_and_changed_frozen_input_do_not_dispatch(self):
        self.draft['scopeReview']['coveredOfficialHours'] = ['one']
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'reviewed official hour'):
            self.step('prepare')
        self.draft['scopeReview']['coveredOfficialHours'] = ['one', 'two']
        self.save_source()
        self.step('prepare')
        self.draft['request'] += '。还需写小结。'
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'changed since preparation'):
            self.step('start')
        self.assertEqual([], self.calls)

    def test_balance_retry_preserves_first_job_and_polls_replacement(self):
        self.step('prepare')
        self.step('start')
        original = (self.work / 'dispatch-response.json').read_bytes()

        def recharged(method, path, body=None):
            if path.endswith('/test-job'):
                return {'jobId': 'test-job', 'status': 'failed', 'completedAt': 'time',
                        'error': 'AI_APICallError: Insufficient Balance (request_id: original-id)',
                        'scenesGenerated': 1}
            if method == 'POST':
                self.calls.append((method, path, body))
                return {'jobId': 'replacement-job', 'status': 'queued'}
            if path.endswith('/replacement-job'):
                return {'jobId': 'replacement-job', 'status': 'succeeded',
                        'result': {'classroomId': 'test-room'}}
            return self.request(method, path, body)

        for _ in range(2):
            result = native_job(self.work, 'retry-after-balance', self.source, self.standard,
                                request=recharged, failed_job='test-job')
            self.assertEqual('replacement-job', result['jobId'])
        self.assertEqual(original, (self.work / 'dispatch-response.json').read_bytes())
        claim = json.loads((self.work / 'balance-retry-claim.json').read_bytes())
        self.assertEqual(1, claim['originalTerminalResponse']['scenesGenerated'])
        posts = [body for method, _, body in self.calls if method == 'POST']
        self.assertEqual(2, len(posts))
        self.assertEqual(posts[0], posts[1])
        self.assertEqual('test-room', self.step('poll', recharged)['classroomId'])

    def test_retry_requires_a_confirmed_balance_failure_and_retains_ambiguous_claim(self):
        self.step('prepare')
        self.step('start')

        def retry(request):
            return native_job(self.work, 'retry-after-balance', self.source, self.standard,
                              request=request, failed_job='test-job')

        with self.assertRaisesRegex(ValueError, 'confirmed terminal balance failure'):
            retry(self.request)

        def interrupted(method, path, body=None):
            if path.endswith('/test-job'):
                return {'jobId': 'test-job', 'status': 'failed', 'completedAt': 'time',
                        'error': 'Insufficient Balance'}
            if method == 'POST':
                self.calls.append((method, path, body))
                raise TimeoutError('Retry response lost')
            return self.request(method, path, body)

        with self.assertRaises(TimeoutError):
            retry(interrupted)
        with self.assertRaisesRegex(ValueError, 'outcome unknown'):
            retry(interrupted)
        with self.assertRaisesRegex(ValueError, 'outcome unknown'):
            self.step('poll')
        self.assertEqual(2, sum(method == 'POST' for method, _, _ in self.calls))

    def test_no_official_hours_requires_bound_textbook_and_listing_evidence(self):
        self.draft['binding']['classHours'] = []
        self.draft['scopeReview']['coveredOfficialHours'] = []
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'requires the exact official notes'):
            self.step('prepare')
        notes = self.work / 'official-notes.json'
        review = {
            'binding': self.draft['binding'],
            'sourceCompleteness': {
                'status': 'complete_textbook_with_official_resource_absence', 'generationAllowed': True,
                'officialClassHours': [], 'textbookReviewed': True, 'absenceEvidence': 'Verified listing',
                'objectiveBasis': 'Reviewed textbook pages',
            },
            'officialListingSearch': dict(chapterIdQuery='node', exactLessonMatches=0, partCount=1,
                                          listingUrl='https://example.org/parts.json', listingSha256='a' * 64,
                                          normalizedTitleQuery='Example'),
            'textbookBoundary': {'start': {'printedPage': 2}, 'end': {'printedPage': 3}},
            'resources': {key: {'status': 'not_provided', 'evidence': 'Exact lesson missing from listing'}
                          for key in ('teachingDesign', 'courseware', 'learningTaskSheet', 'afterClassExercise')},
        }
        review['resources']['textbook'] = {'status': 'reviewed', 'pageRefs': [2, 3], 'findings': ['Count']}
        notes.write_text(json.dumps(review), encoding='utf-8')
        self.draft['sourceInput']['officialNotesSha256'] = digest(notes.read_bytes())
        self.save_source()
        self.assertEqual('prepared', native_job(self.work, 'prepare', self.source, self.standard,
                                               request=self.request, notes_path=notes)['status'])
        self.assertEqual([], self.calls)
        review['officialListingSearch']['exactLessonMatches'] = 1
        notes.write_text(json.dumps(review), encoding='utf-8')
        self.draft['sourceInput']['officialNotesSha256'] = digest(notes.read_bytes())
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'documented absence'):
            native_job(self.work, 'start', self.source, self.standard, request=self.request, notes_path=notes)
        self.assertEqual([], self.calls)

    def test_template_retry_uses_latest_failed_job_and_preserves_both_attempts(self):
        self.step('prepare')
        self.step('start')
        templates = self.work / 'templates'
        template = templates / 'slide-content' / 'system.md'
        template.parent.mkdir(parents=True)
        template.write_text('Readable prompt template', encoding='utf-8')
        template_error = "EPERM: operation not permitted, open '%s'" % (self.work / 'other.md')
        responses = iter(('balance-job', 'template-job'))

        def runtime(method, path, body=None):
            if method == 'POST':
                self.calls.append((method, path, body))
                return {'jobId': next(responses), 'status': 'queued'}
            if path.endswith('/test-job') or path.endswith('/balance-job'):
                job = path.rsplit('/', 1)[1]
                return {'jobId': job, 'status': 'failed', 'completedAt': 'time',
                        'error': 'Insufficient Balance' if job == 'test-job' else template_error}
            if path.endswith('/template-job'):
                return {'jobId': 'template-job', 'status': 'running'}
            return self.request(method, path, body)

        def retry(action, job):
            return native_job(self.work, action, self.source, self.standard, request=runtime, failed_job=job)

        retry('retry-after-balance', 'test-job')
        balance_receipt = (self.work / 'balance-retry-response.json').read_bytes()
        with patch('courseware.tools.native_author.TEMPLATE_ROOT', templates):
            with self.assertRaisesRegex(ValueError, 'preceding recorded dispatch'):
                retry('retry-after-template-error', 'test-job')
            with self.assertRaisesRegex(ValueError, 'readable template error'):
                retry('retry-after-template-error', 'balance-job')
            template_error = "EPERM: operation not permitted, open '%s'" % template
            self.assertEqual('template-job', retry('retry-after-template-error', 'balance-job')['jobId'])
            self.assertEqual('template-job', retry('retry-after-template-error', 'balance-job')['jobId'])
        self.assertEqual(balance_receipt, (self.work / 'balance-retry-response.json').read_bytes())
        self.assertEqual('template-job', self.step('poll', runtime)['jobId'])
        self.assertEqual(3, sum(method == 'POST' for method, _, _ in self.calls))

    def test_answer_retry_requires_revised_prompt_and_preserves_reviewed_lesson(self):
        self.step('prepare')
        self.step('start')
        original = (self.work / 'input.json').read_bytes()

        def runtime(method, path, body=None):
            if path.endswith('/test-job'):
                return {'jobId': 'test-job', 'status': 'failed', 'completedAt': 'time',
                        'error': 'LEARNING_SCENE_ANSWER_CARDINALITY_INVALID'}
            if method == 'POST':
                self.calls.append((method, path, body))
                return {'jobId': 'answer-repair-job', 'status': 'queued'}
            if path.endswith('/answer-repair-job'):
                return {'jobId': 'answer-repair-job', 'status': 'running'}
            return self.request(method, path, body)

        def retry():
            return native_job(self.work, 'retry-after-answer-error', self.source, self.standard,
                              request=runtime, failed_job='test-job')

        with self.assertRaisesRegex(ValueError, 'changed prompt for the same reviewed lesson'):
            retry()
        self.draft['request'] += '。单选题只能给出一个唯一的选项值。'
        self.draft['binding']['nodeId'] = 'different-node'
        self.save_source()
        with self.assertRaisesRegex(ValueError, 'changed prompt for the same reviewed lesson'):
            retry()
        self.draft['binding']['nodeId'] = 'node'
        self.save_source()
        self.assertEqual('answer-repair-job', retry()['jobId'])
        self.assertEqual('answer-repair-job', retry()['jobId'])
        self.assertEqual(original, (self.work / 'input.json').read_bytes())
        repaired = json.loads((self.work / 'answer-retry-input.json').read_bytes())
        claim = json.loads((self.work / 'answer-retry-claim.json').read_bytes())
        self.assertEqual(repaired['draftSha256'], claim['draftSha256'])
        self.assertIn('一个唯一的选项值', repaired['request']['requirement'])
        self.assertEqual('answer-repair-job', self.step('poll', runtime)['jobId'])
        self.assertEqual(2, sum(method == 'POST' for method, _, _ in self.calls))
