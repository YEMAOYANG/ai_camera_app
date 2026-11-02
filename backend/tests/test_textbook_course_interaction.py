import hashlib
import json
import unittest
from contextlib import contextmanager
from unittest.mock import Mock

from content.textbook_catalog import digest
from content import textbook_course_interaction as ci
from core.errors import ApiError
from services.textbook_classroom_service import TextbookClassroomService


def release():
    room = {'scenes': [{'id': 'intro', 'order': 1, 'type': 'slide'},
        {'id': 'scene-p2', 'order': 2, 'type': 'interactive', 'content': {'html': '<p>p2</p>'}},
        {'id': 'scene-p3', 'order': 3, 'type': 'interactive', 'content': {'html': '<p>p3</p>'}}]}
    binding = {'editionId': 'pep-chinese-g1-upper-2022-standard',
               'revisionId': '20260924-directory-3', 'nodeId': 'u5-l1'}
    room['scenes'].extend({'id': f'scene-p{i}', 'order': i, 'type': 'interactive',
                           'content': {'html': f'<p>p{i}</p>'}} for i in range(4, 13))
    specs = [{'sceneId': scene['id'], 'sceneIndex': index,
              'contentSha256': hashlib.sha256(scene['content']['html'].encode()).hexdigest(),
              'validator': ci._VALIDATORS[scene['id']]}
             for index, scene in enumerate(room['scenes']) if scene['type'] == 'interactive']
    body = {'schemaVersion': ci.SCHEMA, 'binding': binding, 'scenes': specs}
    return {'classroom': room, 'textbookBinding': binding,
            'interactionCompletionContract': {**body, 'sha256': digest(body)}}


class CourseInteractionTest(unittest.TestCase):
    def setUp(self):
        self.release = release()
        self.progress = {}
        self.count = 0

    def op(self, page, name, **extra):
        self.count += 1
        return ci.apply_operation(self.progress, release=self.release, scene_index=page-1,
            scene_id='scene-p' + str(page), contract_sha256=self.release['interactionCompletionContract']['sha256'],
            operation_id='op-' + str(self.count), operation={'name': name, **extra})

    def test_wrong_then_revise_evidence_and_count_leafs(self):
        self.op(2, 'start')
        for slot, value in enumerate(('wrong_warm', 'leaves', 'animals')):
            self.op(2, 'select', value=value); self.op(2, 'place', slot=slot)
        self.assertFalse(self.op(2, 'submit')['completed'])
        self.op(2, 'retract', slot=0); self.op(2, 'hint')
        self.op(2, 'select', value='weather'); self.op(2, 'place', slot=0)
        result = self.op(2, 'submit')
        self.assertTrue(result['completed']); self.assertFalse(result['allActivitiesCompleted'])
        attempts = self.progress['courseInteraction']['scenes']['scene-p2']['attempts']
        self.assertEqual([x['passed'] for x in attempts], [False, True])
        self.assertEqual([x['helpCount'] for x in attempts], [0, 1])
        self.op(3, 'start'); self.op(3, 'add')
        self.assertFalse(self.op(3, 'submit')['completed'])
        self.op(3, 'add'); self.op(3, 'toggleWind')
        result = self.op(3, 'submit')
        self.assertFalse(result['allActivitiesCompleted'])
        self.assertEqual(result['evidenceBoundary'], 'client_reported_operations_not_mastery')
        self.assertFalse(ci.completion_ready(self.progress, self.release))
        self.op(3, 'remove')
        self.assertFalse(ci.completion_ready(self.progress, self.release))

    def test_checkpoint_or_forged_completion_cannot_be_submitted(self):
        self.op(3, 'start')
        for operation in ({'name': 'complete'}, {'name': 'submit', 'completed': True},
                          {'name': 'add', 'leafCount': 9}):
            with self.assertRaises(ApiError):
                ci.apply_operation(self.progress, release=self.release, scene_index=2, scene_id='scene-p3',
                    contract_sha256=self.release['interactionCompletionContract']['sha256'],
                    operation_id='forged', operation=operation)
        self.assertFalse(ci.completion_ready(self.progress, self.release))

    def test_duplicate_operation_id_is_idempotent_and_cannot_be_reused(self):
        sha = self.release['interactionCompletionContract']['sha256']
        def apply(opid, operation):
            return ci.apply_operation(self.progress, release=self.release, scene_index=2, scene_id='scene-p3',
                contract_sha256=sha, operation_id=opid, operation=operation)
        apply('start', {'name': 'start'}); apply('same', {'name': 'add'}); apply('same', {'name': 'add'})
        self.assertEqual(self.progress['courseInteraction']['scenes']['scene-p3']['leafCount'], 1)
        with self.assertRaises(ApiError): apply('same', {'name': 'remove'})

    def test_recovery_uses_server_operations_not_checkpoint_and_copies_state(self):
        self.op(3, 'start'); self.op(3, 'add')
        self.progress['activityCheckpoint'] = {'scene-p3': {'leafCount': 9, 'completed': True}}
        recovered = ci.recovery_state(self.progress, self.release)
        self.assertEqual(recovered['scenes']['scene-p3']['leafCount'], 1)
        self.assertFalse(recovered['scenes']['scene-p3']['completed'])
        recovered['scenes']['scene-p3']['leafCount'] = 7
        self.assertEqual(self.progress['courseInteraction']['scenes']['scene-p3']['leafCount'], 1)

    def test_page_content_or_binding_or_partial_contract_fails_closed(self):
        self.release['classroom']['scenes'][1]['content']['html'] += 'tamper'
        with self.assertRaises(ApiError): ci.validate_contract(self.release)
        self.release = release(); self.release['textbookBinding']['nodeId'] = 'other'
        with self.assertRaises(ApiError): ci.validate_contract(self.release)
        self.release = release(); self.release['classroom']['scenes'].pop()
        with self.assertRaises(ApiError): ci.validate_contract(self.release)

    def test_builder_binds_delivered_html_after_media_url_rewrite(self):
        delivered = release()
        delivered['classroom']['scenes'][1]['content']['html'] = (
            '<img src="/api/classroom-media/tbpub_example/media/delivered.png">')
        contract = ci.build_contract(delivered['classroom'], delivered['textbookBinding'])
        delivered['interactionCompletionContract'] = contract
        self.assertEqual(ci.validate_contract(delivered), contract)
        self.assertEqual(contract['scenes'][0]['contentSha256'], hashlib.sha256(
            delivered['classroom']['scenes'][1]['content']['html'].encode()).hexdigest())
        delivered['classroom']['scenes'][1]['content']['html'] += '<p>changed</p>'
        with self.assertRaises(ApiError): ci.validate_contract(delivered)

    def test_builder_rejects_missing_or_unsupported_pages_and_wrong_binding(self):
        candidate = release()
        candidate['classroom']['scenes'].pop()
        with self.assertRaises(ApiError): ci.build_contract(candidate['classroom'], candidate['textbookBinding'])
        candidate = release()
        candidate['classroom']['scenes'][4]['id'] = 'unreviewed-page'
        with self.assertRaises(ApiError): ci.build_contract(candidate['classroom'], candidate['textbookBinding'])
        candidate = release()
        candidate['textbookBinding']['nodeId'] = 'another-lesson'
        with self.assertRaises(ApiError): ci.build_contract(candidate['classroom'], candidate['textbookBinding'])

    def test_delivery_templates_bind_rewritten_paths_to_frozen_source_and_bytes(self):
        candidate = release()
        source = candidate['classroom']
        source['scenes'][1]['content']['html'] = '<img src="/api/classroom-media/old/media/leaf.png">'
        source_sha, delivery_sha = '1' * 64, '2' * 64
        templates = ci.html_templates(source, candidate['textbookBinding'], lambda _: source_sha)
        frozen = {'interactionCompletionTemplates': {
            'schemaVersion': 'mira.textbook.interaction-delivery-templates.v1', 'scenes': templates,
            'assets': [{'sourceSha256': source_sha, 'deliverySha256': delivery_sha,
                        'mimeType': 'image/png', 'byteSize': 9}]}}
        target = json.loads(json.dumps(candidate))
        target['classroom']['scenes'][1]['content']['html'] = '<img src="/api/classroom-media/new/media/copied.png">'
        target['interactionCompletionContract'] = ci.build_contract(target['classroom'], target['textbookBinding'])
        target['media'] = [{'path': '/api/classroom-media/new/media/copied.png', 'sha256': delivery_sha,
                            'sourceSha256': source_sha, 'mimeType': 'image/png', 'byteSize': 9}]
        self.assertTrue(ci.validate_delivery_templates(frozen, target))
        # Rehashing the modified page and release contract is not evidence of
        # the reviewed source: the frozen template remains authoritative.
        target['classroom']['scenes'][1]['content']['html'] += '<p>extra</p>'
        target['interactionCompletionContract'] = ci.build_contract(target['classroom'], target['textbookBinding'])
        with self.assertRaises(ApiError): ci.validate_delivery_templates(frozen, target)
        target['classroom']['scenes'][1]['content']['html'] = '<img src="/api/classroom-media/new/media/copied.png">'
        target['media'][0]['sha256'] = '3' * 64
        with self.assertRaises(ApiError): ci.validate_delivery_templates(frozen, target)

    def test_invalid_order_out_of_range_and_forged_target_fail(self):
        with self.assertRaises(ApiError): self.op(2, 'select', value='weather')
        self.op(2, 'start')
        with self.assertRaises(ApiError): self.op(2, 'place', slot=0)
        with self.assertRaises(ApiError): self.op(2, 'select', value=[])
        self.op(3, 'start')
        with self.assertRaises(ApiError): self.op(3, 'remove')
        for _ in range(9): self.op(3, 'add')
        with self.assertRaises(ApiError): self.op(3, 'add')


class FixedClassroomEventTest(unittest.TestCase):
    def setUp(self):
        self.release = release()
        self.release.update(classroomId='room', sha256='a' * 64,
                            assessmentPolicy='verified-frozen-no-native-quiz')
        self.session = {'id': 'session', 'status': 'in_progress', 'task_id': 'task', 'runtime_state_json': None}
        self.service = object.__new__(TextbookClassroomService)
        self.service.learning = Mock(); self.service.repository = Mock()
        self.service.repository.parse.side_effect = lambda value: json.loads(value) if isinstance(value, str) else value
        self.service._authority = Mock(return_value=(None, {'family_id': 'family'}, None,
                                                     self.release, {}, self.session))
        self.service.learning.get_session.side_effect = lambda *args, **kwargs: self.session
        test = self
        class Cursor:
            def __init__(self, row=None): self.row = row
            def fetchone(self): return self.row
        class Conn:
            def __init__(self): self.records = {}
            def execute(self, sql, args=()):
                if sql.startswith('SELECT * FROM learning_session_runtime_records'):
                    return Cursor(self.records.get(args[1]))
                if sql.startswith('UPDATE learning_sessions SET runtime_state_json='):
                    test.session['runtime_state_json'] = args[0]
                elif sql.startswith('INSERT INTO learning_session_runtime_records'):
                    self.records[args[2]] = {'payload_json': args[7], 'response_json': args[8]}
                return Cursor()
        self.conn = Conn()
        @contextmanager
        def transaction(): yield self.conn
        self.service.repository.transaction.side_effect = transaction

    def event(self, sequence, kind, payload):
        return {'schemaVersion': 'mira.openmaic.student-runtime-event.v1', 'sequence': sequence,
                'type': kind, 'payload': payload}

    def op(self, sequence, opid, operation):
        return self.event(sequence, 'interaction_operation', {'sceneIndex': 1, 'sceneId': 'scene-p2',
            'contractSha256': self.release['interactionCompletionContract']['sha256'],
            'operationId': opid, 'operation': operation})

    def test_operation_requires_page_entry_and_exact_release(self):
        with self.assertRaises(ApiError): self.service.events('token', self.op(1, 'start', {'name': 'start'}))
        self.service.events('token', self.event(1, 'scene_entered', {'sceneIndex': 1, 'sceneId': 'scene-p2'}))
        forged = self.op(2, 'start', {'name': 'start'}); forged['payload']['contractSha256'] = 'b' * 64
        with self.assertRaises(ApiError): self.service.events('token', forged)
        result = self.service.events('token', self.op(2, 'start', {'name': 'start'}))
        self.assertEqual(result['interaction']['phase'], 'playing')
        self.assertFalse(result['interaction']['completed'])
        self.assertFalse(self.service.events('token')['completionReady'])

    def test_event_replay_is_idempotent_and_spoofed_complete_fails(self):
        self.service.events('token', self.event(1, 'scene_entered', {'sceneIndex': 1, 'sceneId': 'scene-p2'}))
        start = self.op(2, 'start', {'name': 'start'})
        self.assertEqual(self.service.events('token', start), self.service.events('token', start))
        with self.assertRaises(ApiError): self.service.events('token', self.op(3, 'forged', {'name': 'complete'}))
        with self.assertRaises(ApiError):
            self.service.events('token', self.event(3, 'classroom_completed', {'sceneIndex': 1, 'sceneId': 'scene-p2'}))
        self.service.learning.mark_task_completed.assert_not_called()
        self.service.learning.create_or_get_report.assert_not_called()


if __name__ == '__main__':
    unittest.main()
