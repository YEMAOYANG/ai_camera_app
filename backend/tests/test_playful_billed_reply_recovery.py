"""No database or Provider: exercise first-attempt replay admission and audited CAS."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

from content.learning_budget_policy import canonical, digest
from integrations.openmaic_formal_media import PLAYFUL_PROFESSIONAL_POLICY
from repositories.learning_catalog_repository import LearningCatalogRepository
from services import learning_content_recovery as recovery


def fixture():
    item = {'id': 'item', 'build_job_id': 'build', 'grade_code': 'primary_6',
        'subject': 'math', 'skill_id': 'fraction_ratio_percentage', 'variant_ordinal': 1,
        'attempt_count': 1, 'generation_request_id': 'generation',
        'active_generation_request_id': 'generation', 'status': 'failed',
        'content_phase': 'failed', 'content_claim_attempt_ordinal': 1,
        'content_gate_status': 'not_started', 'content_gate_attempt_count': 0,
        'content_attempt_started_at': 10000, 'content_provider_attempt_hard_deadline_at': None,
        'error_code': 'preparation_content_validation_failed', 'course_id': None,
        'course_version': None, 'content_lease_token': None}
    checkpoints = [{'phaseStatus': 'accepted', 'outline': {}}, {'phaseStatus': 'accepted', 'candidate': {}},
                   {'phaseStatus': 'rejected', 'rejectionCode': 'candidate_repair_schema_rejected'}, None]
    phases = ['outline', 'raw_candidate', 'candidate_repair', 'candidate_repair_retry']
    rows = [{'id': 'dispatch-' + str(i), 'build_item_id': 'item', 'logical_attempt': 1,
        'generation_request_id': 'generation', 'phase': phase, 'phase_ordinal': i + 1,
        'status': 'succeeded' if checkpoint is not None else 'failed_safe',
        'safe_error_code': None if checkpoint is not None else 'question_phase_output_rejected',
        'checkpoint_json': canonical(checkpoint) if checkpoint is not None else None,
        'output_sha256': digest(checkpoint) if checkpoint is not None else None,
        'input_sha256': str(i + 1) * 64, 'profile': 'a' * 64,
        'provider_request_id_hash': 'b' * 64, 'input_tokens': 100 + i, 'output_tokens': 40 + i,
        'billing_evidence': 'reported', 'completed_at': 11000 + i,
        'attempt_started_at': 10000, 'attempt_hard_deadline_at': 1810000}
        for i, (phase, checkpoint) in enumerate(zip(phases, checkpoints))]
    histories = {1: {'dispatches': rows, 'jobs': [], 'candidates': [], 'courses': []},
                 2: {'dispatches': [], 'jobs': [], 'candidates': [], 'courses': []}}
    target = {'formalRuntimePolicy': {'professionalCreationPolicy': deepcopy(PLAYFUL_PROFESSIONAL_POLICY)}}
    build = {'id': 'build', 'status': 'running', 'error_code': None, 'target_spec_json': canonical(target)}
    return item, histories, build


class ReadConnection:
    def __init__(self, rows):
        self.calls = []
        self.requested = [{'subject': 'math', 'skill_id': 'fraction_ratio_percentage', 'variant_ordinal': 1}]
        self.dispatch_ids = [{'id': row['id']} for row in rows]
        self.runtimes = []
        self.receipts = []
        self.events = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.startswith('UPDATE') or sql.lstrip().startswith('UPDATE'):
            return SimpleNamespace(rowcount=1)
        if 'learning_course_supply_requests' in sql:
            result = self.requested
        elif 'SELECT id FROM learning_course_provider_dispatches' in sql:
            result = self.dispatch_ids
        elif 'learning_openmaic_runtime_classrooms' in sql:
            result = self.runtimes
        elif 'learning_curriculum_classroom_item_receipts' in sql:
            result = self.receipts
        elif 'learning_curriculum_preparation_events' in sql:
            result = self.events
        else:
            raise AssertionError('Unexpected SQL: ' + sql)
        return SimpleNamespace(fetchall=lambda: deepcopy(result))


class PlayfulBilledReplyRecoveryTest(unittest.TestCase):
    def test_exact_returned_history_passes_without_mutating_original_evidence(self):
        item, histories, _ = fixture()
        original = deepcopy((item, histories))
        self.assertEqual(recovery.playful_billed_attempt_one_evidence(item=item, histories=histories), histories[1]['dispatches'])
        self.assertEqual((item, histories), original)

    def test_no_ambiguous_unbilled_extra_or_candidate_history_can_be_replayed(self):
        mutations = [
            lambda i, h: h[1]['dispatches'][-1].update(status='ambiguous'),
            lambda i, h: h[1]['dispatches'][0].update(billing_evidence='unknown'),
            lambda i, h: h[1]['dispatches'][2].update(provider_request_id_hash=None),
            lambda i, h: h[1]['dispatches'][2].update(input_tokens=True),
            lambda i, h: h[1]['dispatches'][1].update(output_sha256='f' * 64),
            lambda i, h: h[1]['dispatches'][1].update(attempt_hard_deadline_at=1810001),
            lambda i, h: h[1]['dispatches'][-1].update(safe_error_code='provider_connection_interrupted'),
            lambda i, h: h[2]['dispatches'].append({'id': 'extra'}),
            lambda i, h: h[1]['candidates'].append({'id': 'candidate'}),
            lambda i, h: i.update(course_id='course'),
            lambda i, h: i.update(content_lease_token='lease'),
            lambda i, h: i.update(content_gate_status='passed'),
            lambda i, h: i.update(active_generation_request_id='generation.attempt2'),
            lambda i, h: i.update(content_provider_attempt_hard_deadline_at=1810001),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                item, histories, _ = fixture()
                mutate(item, histories)
                with self.assertRaises(ValueError):
                    recovery.playful_billed_attempt_one_evidence(item=item, histories=histories)

    def test_exact_new_policy_and_original_single_slot_only(self):
        item, histories, build = fixture()
        connection = ReadConnection(histories[1]['dispatches'])
        before = deepcopy((item, histories, build))
        fingerprint = recovery.require_playful_billed_recovery_authority(connection, build=build,
            item=item, histories=histories, now=12000)
        self.assertEqual(fingerprint, digest(json.loads(build['target_spec_json'])))
        self.assertEqual((item, histories, build), before)
        self.assertTrue(all(sql.startswith('SELECT') for sql, _ in connection.calls))
        for mutation in ('legacy', 'extra-key', 'bool-as-number', 'expired', 'extra-slot', 'extra-call', 'runtime', 'receipt'):
            with self.subTest(mutation=mutation):
                item, histories, build = fixture()
                connection = ReadConnection(histories[1]['dispatches'])
                target = json.loads(build['target_spec_json'])
                policy = target['formalRuntimePolicy']['professionalCreationPolicy']
                if mutation == 'legacy': del policy['playfulLearningPolicy']
                if mutation == 'extra-key': policy['unreviewed'] = True
                if mutation == 'bool-as-number': policy['playfulLearningPolicy']['aiDesigned'] = 1
                if mutation == 'extra-slot': connection.requested.append({'subject': 'english'})
                if mutation == 'extra-call': connection.dispatch_ids.append({'id': 'unknown-call'})
                if mutation == 'runtime': connection.runtimes = [{'id': 'runtime'}]
                if mutation == 'receipt': connection.receipts = [{'build_item_id': 'item'}]
                build['target_spec_json'] = canonical(target)
                with self.assertRaises(ValueError):
                    recovery.require_playful_billed_recovery_authority(connection, build=build,
                        item=item, histories=histories, now=1810000 if mutation == 'expired' else 12000)
                self.assertTrue(all(sql.startswith('SELECT') for sql, _ in connection.calls))

    def test_replay_requires_original_fingerprint_snapshot_before_preflight(self):
        item, histories, _ = fixture()
        catalog = Mock()
        with self.assertRaisesRegex(ValueError, 'frozen historical'):
            recovery.replay_billed_reply(catalog=catalog, item=item, histories=histories, archive={})
        catalog._content_provider_preflight.assert_not_called()

    def test_replay_checks_exact_input_profile_and_preserves_snapshot_without_provider_execution(self):
        item, histories, _ = fixture()
        failed = histories[1]['dispatches'][-1]
        prepared = SimpleNamespace(input_sha256=failed['input_sha256'], profile_sha256=failed['profile'], request={})
        catalog = Mock()
        catalog._content_phase_command.return_value = ('command', {})
        catalog._content_provider_preflight.return_value = prepared
        catalog.staged_content_candidate_generator._adapter = SimpleNamespace(node_binary='node', sidecar_root=Path('/sidecar'))
        archive = {'schemaVersion': 'mira.openmaic.question-phase-reply-archive.v1', 'requestId': 'generation',
            'phase': 'candidate_repair_retry', 'phaseOrdinal': 4, 'gradeCode': 'primary_6', 'subject': 'math',
            'skillId': 'fraction_ratio_percentage', 'receipt': {'providerRequestIdHash': failed['provider_request_id_hash'],
                'inputTokens': failed['input_tokens'], 'outputTokens': failed['output_tokens'], 'billingEvidence': 'reported'},
            'content': '{}', 'contentSha256': recovery.hashlib.sha256(b'{}').hexdigest(),
            'inputSha256': failed['input_sha256'], 'providerProfileSha256': failed['profile']}
        accepted = {'phaseStatus': 'accepted', 'candidate': {'questions': []}}
        replay = {'checkpoint': accepted, 'inputSha256': failed['input_sha256'], 'providerProfileSha256': failed['profile']}
        before = deepcopy(histories)
        with patch.object(recovery.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(replay))) as subprocess_call, \
             patch('integrations.openmaic_question_adapter._normalize_phase_output_checkpoint', return_value=accepted), \
             patch('services.learning_formal_question_preflight.validate_formal_phase_question_checkpoint') as host_gate:
            checkpoint, _ = recovery.replay_billed_reply(catalog=catalog, item=item, histories=histories,
                archive=archive, historical_fingerprints=['c' * 64])
            self.assertEqual(checkpoint, accepted)
            self.assertEqual(catalog._content_phase_command.call_args_list[0].kwargs['plan']['historicalQuestionFingerprints'], ['c' * 64])
            host_gate.assert_called_once()
            self.assertEqual(subprocess_call.call_args.kwargs['env'].keys(), {'PATH', 'OPENMAIC_HOST_VALIDATOR_PYTHON', 'PYTHONDONTWRITEBYTECODE'})
            catalog.staged_content_candidate_generator.execute.assert_not_called()
            self.assertEqual(histories, before)
            archive['inputSha256'] = 'e' * 64
            with self.assertRaisesRegex(ValueError, 'exact billed Provider evidence'):
                recovery.replay_billed_reply(catalog=catalog, item=item, histories=histories,
                    archive=archive, historical_fingerprints=['c' * 64])
            self.assertEqual(subprocess_call.call_count, 1)

    def test_repository_requires_durable_audit_and_retains_billing_and_original_deadline(self):
        item, histories, build = fixture()
        connection = ReadConnection(histories[1]['dispatches'])
        checkpoint = {'phaseStatus': 'accepted', 'candidate': {'questions': []}}
        repository = LearningCatalogRepository(None)
        repository.lock_build_authority = Mock(return_value=({'id': 'release'}, build))
        repository.list_build_items = Mock(return_value=[item])
        repository._content_authority_is_exact = Mock(return_value=True)
        repository._load_content_attempt_histories_locked = Mock(return_value={'item': histories})
        repository.get_item = Mock(return_value=item)
        failed = histories[1]['dispatches'][-1]
        audit = {'schemaVersion': recovery.BILLED_PLAYFUL_KIND, 'buildId': 'build', 'buildItemId': 'item',
            'logicalAttempt': 1, 'originalItem': deepcopy(item), 'originalAttemptDispatches': deepcopy(histories[1]['dispatches']),
            'checkpoint': checkpoint, 'checkpointSha256': digest(checkpoint),
            'sourceArchive': {'saved': 'raw Provider reply'}, 'sourceArchiveSha256': digest({'saved': 'raw Provider reply'})}
        sha = digest(audit)
        args = dict(build_id='build', item_id='item', expected_subject='math', expected_skill_id='fraction_ratio_percentage',
            expected_grade='primary_6', failed_dispatch_id=failed['id'], expected_input_sha256=failed['input_sha256'],
            checkpoint=checkpoint, now=12000, recovery_audit_sha256=sha)
        with TemporaryDirectory() as folder, patch.object(recovery, 'ARCHIVE_ROOT', Path(folder)):
            with self.assertRaises(FileNotFoundError): repository.recover_billed_candidate_retry_host_checkpoint(connection, **args)
            self.assertFalse(any(sql.lstrip().startswith('UPDATE') for sql, _ in connection.calls))
            Path(folder, 'recovery-' + sha + '.json').write_text(canonical(audit))
            with self.assertRaisesRegex(ValueError, 'immutable preparation event'):
                repository.recover_billed_candidate_retry_host_checkpoint(connection, **args)
            connection.events = [{'payload_json': canonical({'recoveryKindId': recovery.BILLED_PLAYFUL_KIND,
                'buildItemId': 'item', 'auditShaId': sha, 'sourceDispatchId': failed['id'],
                'originalHistoryShaId': digest(histories[1]['dispatches']), 'sourceArchiveShaId': digest(audit['sourceArchive']),
                'checkpointShaId': digest(checkpoint)})}]
            repository.recover_billed_candidate_retry_host_checkpoint(connection, **args)
            updates = [(sql, params) for sql, params in connection.calls if sql.lstrip().startswith('UPDATE')]
            self.assertEqual(len(updates), 3)
            dispatch_set = updates[0][0].split('SET', 1)[1].split('WHERE', 1)[0]
            for field in ('input_tokens', 'output_tokens', 'billing_evidence', 'provider_request_id_hash', 'completed_at', 'input_sha256', 'attempt_started_at', 'attempt_hard_deadline_at'):
                self.assertNotIn(field, dispatch_set)
            self.assertEqual(updates[1][1][0], 1810000)
            self.assertLessEqual(updates[1][1][1], 1810000)
            self.assertNotIn('attempt_count =', updates[1][0].split('WHERE')[0])
            self.assertNotIn('content_attempt_started_at', updates[1][0].split('WHERE')[0])


if __name__ == '__main__':
    unittest.main()
