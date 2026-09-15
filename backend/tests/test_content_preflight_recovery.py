"""No Provider/database calls: exact recovery provenance and prior-history gates."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from content.learning_budget_policy import canonical, digest
from services import learning_content_preflight_recovery as recovery
from services.learning_content_recovery import candidate_less_evidence, recovery_dispatches
from tests.test_playful_billed_reply_recovery import fixture as billed_fixture


def fixture():
    item, histories, build = billed_fixture()
    item.update(subject='english', skill_id='past_future', error_code='preparation_content_provider_unavailable')
    rows = histories[1]['dispatches'][:3]
    rows[2].update(status='failed_safe', safe_error_code='question_phase_preflight_rejected',
        checkpoint_json=None, output_sha256=None, provider_request_id_hash=None,
        input_tokens=None, output_tokens=None, billing_evidence='unknown')
    for index, row in enumerate(rows):
        row['dispatched_at'] = 10001 + index
    histories[1]['dispatches'] = rows
    identity = {'scope': {'approvalReference': 'grade-build:' + 'a' * 64}}
    state = {'build': build, 'item': item, 'owner': {'id': 'owner'}, 'dispatches': rows}
    audit = {'schemaVersion': 'mira.english-3d.preflight-failure-state.v1', 'dbState': state,
        'dbStateSha256': digest(state), 'identity': identity, 'runtimes': [],
        'reservationAtOrAfterFailedPhase': [], 'authorization': {'id': 'authorization'},
        'taskReservations': [{'id': str(i), 'state': 'settled', 'authorization_id': 'authorization',
            'dispatched_at': rows[i]['dispatched_at']} for i in range(2)]}
    audit['auditSha256'] = digest(audit)
    return item, histories, identity, state, audit


class ContentPreflightRecoveryTest(unittest.TestCase):
    def test_original_three_rows_and_two_billed_sources_remain_unchanged(self):
        item, histories, identity, state, audit = fixture()
        before = deepcopy((item, histories, state, audit))
        self.assertEqual(recovery.preflight_history(item, histories[1]['dispatches']), histories[1]['dispatches'])
        self.assertEqual(recovery.validate_failure_audit(audit, identity=identity, state=state), histories[1]['dispatches'])
        self.assertEqual((item, histories, state, audit), before)

    def test_ambiguous_returned_extra_changed_or_cross_subject_history_is_rejected(self):
        mutations = (
            lambda i, h: h[1]['dispatches'][2].update(status='ambiguous'),
            lambda i, h: h[1]['dispatches'][2].update(safe_error_code='provider_connection_interrupted'),
            lambda i, h: h[1]['dispatches'][2].update(input_tokens=10),
            lambda i, h: h[1]['dispatches'][2].update(provider_request_id_hash='b' * 64),
            lambda i, h: h[1]['dispatches'][0].update(billing_evidence='unknown'),
            lambda i, h: h[1]['dispatches'][0].update(output_sha256='c' * 64),
            lambda i, h: h[1]['dispatches'][1].update(input_tokens=True),
            lambda i, h: h[1]['dispatches'].append(deepcopy(h[1]['dispatches'][2])),
            lambda i, h: h[1]['dispatches'][2].update(attempt_hard_deadline_at=1810001),
            lambda i, h: i.update(subject='math'),
            lambda i, h: i.update(skill_id='grammar_in_context'),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                item, histories, *_ = fixture()
                mutate(item, histories)
                with self.assertRaises(ValueError):
                    recovery.preflight_history(item, histories[1]['dispatches'])

    def test_audit_rejects_changed_scope_runtime_or_unsettled_or_later_charge(self):
        mutations = (
            lambda a: a['identity'].update(other='scope'),
            lambda a: a['runtimes'].append({'id': 'runtime'}),
            lambda a: a['reservationAtOrAfterFailedPhase'].append({'id': 'charge'}),
            lambda a: a['taskReservations'][1].update(state='unknown'),
            lambda a: a['taskReservations'][1].update(dispatched_at=10003),
            lambda a: a['taskReservations'].append(deepcopy(a['taskReservations'][0])),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                _, _, identity, state, audit = fixture()
                original_identity = deepcopy(identity)
                mutate(audit)
                audit['auditSha256'] = digest({k: v for k, v in audit.items() if k != 'auditSha256'})
                with self.assertRaises(ValueError):
                    recovery.validate_failure_audit(audit, identity=original_identity, state=state)

    def test_existing_host_audit_path_recognizes_both_local_copies_without_rebilling(self):
        item, histories, identity, _, audit = fixture()
        receipt = recovery.preflight_receipt(item, histories[1]['dispatches'],
            approval_reference=identity['scope']['approvalReference'], source_audit_sha=audit['auditSha256'])
        histories[1]['recoveryReceipt'] = receipt
        item.update(attempt_count=2, active_generation_request_id='generation.attempt2')
        self.assertIsNotNone(candidate_less_evidence(item=item, histories=histories))
        for row in histories[1]['dispatches'][:2]:
            copied = deepcopy(row)
            copied.update(logical_attempt=2, generation_request_id='generation.attempt2',
                provider_request_id_hash=None, input_tokens=None, output_tokens=None, billing_evidence='unknown')
            histories[2]['dispatches'].append(copied)
            self.assertIsNotNone(candidate_less_evidence(item=item, histories=histories))
        self.assertEqual(recovery_dispatches(item=item, evidence={'attemptHistories': histories}), histories[1]['dispatches'])
        histories[2]['dispatches'][1]['output_tokens'] = 1
        self.assertIsNone(candidate_less_evidence(item=item, histories=histories))
        histories[2]['dispatches'][1]['output_tokens'] = None
        histories[2]['dispatches'][1]['output_sha256'] = 'd' * 64
        self.assertIsNone(candidate_less_evidence(item=item, histories=histories))

    def test_failed_phase_must_still_have_no_intent_response_or_temporary_file(self):
        _, histories, _, _, audit = fixture()
        with TemporaryDirectory() as folder, patch.object(recovery, 'ARCHIVE_ROOT', Path(folder)):
            entries = []
            for index, row in enumerate(histories[1]['dispatches']):
                files = {}
                for key, suffix in (('intent', '.intent.json'), ('response', '.json'), ('temporaryResponse', '.reply.tmp')):
                    path = Path(folder) / (row['phase'] + '.' + row['input_sha256'] + suffix)
                    exists = index < 2 and key != 'temporaryResponse'
                    if exists:
                        path.write_text(canonical({'phase': row['phase']}))
                    files[key] = {'path': str(path), 'exists': exists,
                        'sha256': recovery.hashlib.sha256(path.read_bytes()).hexdigest() if exists else None}
                entries.append({'dispatchId': row['id'], 'inputSha256': row['input_sha256'],
                    'phase': row['phase'], 'phaseOrdinal': row['phase_ordinal'], 'files': files})
            audit['sidecarArchives'] = entries
            recovery._check_source_archives(audit, histories[1]['dispatches'])
            intent = Path(entries[2]['files']['intent']['path'])
            intent.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'intent'):
                recovery._check_source_archives(audit, histories[1]['dispatches'])


if __name__ == '__main__':
    unittest.main()
