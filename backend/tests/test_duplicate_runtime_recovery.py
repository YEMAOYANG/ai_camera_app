"""Offline recovery evidence tests: no application context, database, or Provider."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from content.learning_budget_policy import canonical, digest
from integrations.openmaic_formal_quality import quality_canonical_json, quality_sha, quality_snapshot
from services import learning_duplicate_runtime_recovery as recovery
from repositories.learning_curriculum_preparation_repository import LearningCurriculumPreparationRepository


def session_identity(job):
    suffix = hashlib.sha256((job['runtimeRequestId'] + '\n' +
        quality_canonical_json(job['formalInput'])).encode()).hexdigest()
    return 'miraformal_' + suffix, 'mira-formal-professional:' + suffix


class DuplicateRuntimeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.native = self.root / 'native'
        self.evidence = self.root / 'cancel'
        self.archives = self.root / 'archives'
        self.addCleanup(patch.stopall)
        patch.object(recovery, 'ARCHIVES', self.archives).start()
        patch.object(recovery, 'NATIVE', self.native).start()
        # A forgotten mock must fail before any command or external connection.
        patch.object(recovery.subprocess, 'run', side_effect=AssertionError('no external process')).start()
        self.proof = self.make_proof()

    def file_record(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        path.write_text(raw)
        return {'path': str(path), 'raw': raw, 'sha256': hashlib.sha256(raw.encode()).hexdigest()}

    def replace_file(self, proof, key, edit):
        value = json.loads(proof['files'][key]['raw'])
        edit(value)
        proof['files'][key] = self.file_record(Path(proof['files'][key]['path']), value)

    def make_proof(self):
        identity = {'buildId': 'build-fixture', 'buildItemId': 'item-fixture',
            'targetFingerprint': 'target-fixture'}
        budget = {'schemaVersion': 'mira.learning.paid-budget-binding.v1',
            'required': True, 'authorizationId': 'authorization-fixture'}
        shared = {'course_id': 'course-fixture', 'course_version': 'v1',
            'package_id': 'package-fixture', 'package_version': 'v1',
            'candidate_build_item_id': identity['buildItemId'], 'candidate_release_id': 'release-fixture',
            'candidate_grade_code': 'primary_6', 'candidate_target_fingerprint': identity['targetFingerprint'],
            'candidate_binding_contract_version': 'mira.candidate-binding.v1', 'status': 'failed',
            'quality_status': 'rejected', 'error_code': 'openmaic_formal_generation_failed',
            'retired_at': None, 'ready_at': None, 'upstream_classroom_id': None,
            'feature_manifest_json': json.dumps({'paidBudget': budget})}
        rows, jobs = [], []
        for ordinal in (1, 2):
            request_id = f'request-fixture-{ordinal}'
            row = {**shared, 'id': f'runtime-{ordinal}', 'upstream_job_id': f'job-{ordinal}',
                'request_id': request_id, 'attempt_ordinal': ordinal, 'provider_attempt_ordinal': ordinal,
                'created_at': 1000 if ordinal == 1 else 2001,
                'updated_at': 2000 if ordinal == 1 else 3000,
                'retry_of_runtime_id': None if ordinal == 1 else 'runtime-1',
                'expected_previous_job_id': None if ordinal == 1 else 'job-1',
                'retry_reason': None if ordinal == 1 else 'formal_candidate_retry_2'}
            requirement = {'authority': 'mira_backend_formal_candidate', **identity,
                'runtimeRequestId': request_id, 'course': {'id': 'course-fixture', 'version': 'v1'}}
            formal_input = {'runtimeRequestId': request_id, 'requirement': json.dumps(requirement),
                'paidBudget': budget, 'agentMode': 'generate', 'enableTTS': False,
                'professionalCreationPolicy': {'mode': 'professional_skill', 'skillId': 'mira-primary-courseware'}}
            job = {'id': row['upstream_job_id'], 'status': 'failed', 'step': 'failed',
                'runtimeRequestId': request_id, 'formalInput': formal_input,
                'formalInputSha256': quality_sha(formal_input), 'completedAt': '2026-09-11T12:00:00.000Z',
                'error': 'FORMAL_PROFESSIONAL_SESSION_TIMEOUT' if ordinal == 1
                    else 'FORMAL_PROFESSIONAL_SESSION_CANCELLED:duplicate',
                'scenesGenerated': 8 if ordinal == 1 else 0, 'totalScenes': 8 if ordinal == 1 else 0}
            rows.append(row); jobs.append(job)
        questions = ['question-guided-a', 'question-guided-b', 'question-independent-a', 'question-independent-b']
        scenes = []
        for index in range(8):
            quiz = index in (5, 6)
            content = {'type': 'slide', 'canvas': {'elements': []}}
            if quiz:
                offset = 0 if index == 5 else 2
                content = {'type': 'quiz', 'questions': [{'id': q, 'type': 'single', 'answer': [],
                    'hasAnswer': False, 'points': 1} for q in questions[offset:offset + 2]]}
            scenes.append({'id': f'scene-{index + 1}', 'type': 'quiz' if quiz else 'slide',
                'title': f'Fixture scene {index + 1}', 'order': index, 'actions': [], 'content': content})
        source = {'stage': {'id': 'original-stage', 'name': 'Offline draft'}, 'scenes': scenes}
        files = {key: self.file_record(self.native / 'data/classroom-jobs' / f'job-{index + 1}.json', jobs[index])
            for index, key in enumerate(('selectedJob', 'duplicateJob'))}
        sid, owner_id = session_identity(jobs[1])
        before = {'schemaVersion': 1, 'identity': {'jobId': 'job-2', 'sessionId': sid,
            'ownerId': owner_id, 'runtimeInstanceId': 'runtime-2', 'buildItemId': 'item-fixture',
            'questionIds': questions}, 'stages': [], 'scenes': [],
            'originalFailedJobSha256': files['selectedJob']['sha256'],
            'eventRefs': [{'seq': 12, 'type': 'tool_execution_start'}, {'seq': 13, 'type': 'tool_execution_end'}]}
        files['cancelBefore'] = self.file_record(self.evidence / 'before.json', before)
        terminal = {'seq': 17, 'type': 'session_end', 'attempt': 1,
            'data': {'status': 'cancelled', 'toolCalls': 0}}
        after = {'session': {'id': sid, 'owner_id': owner_id, 'status': 'cancelled'},
            'terminalEvent': terminal, 'originalFailedJobSha256': files['selectedJob']['sha256']}
        files['cancelAfter'] = self.file_record(self.evidence / 'after.json', after)
        cancel = {'schemaVersion': 1, 'officialMethod': 'PgAgentSessionStore.requestCancel',
            'jobId': 'job-2', 'runtimeInstanceId': 'runtime-2', 'sessionId': sid, 'ownerId': owner_id,
            'buildItemId': 'item-fixture', 'beforeSha256': files['cancelBefore']['sha256'],
            'ownerEventId': '4', 'cancelRequestedAt': 4000}
        files['cancelReceipt'] = self.file_record(self.evidence / 'cancel-receipt.json', cancel)
        files['sourceSnapshot'] = self.file_record(self.root / 'source.json', source)
        native = []
        for index, job in enumerate(jobs):
            session_id, owner = session_identity(job)
            native.append({'session': {'id': session_id, 'owner_id': owner, 'status': 'cancelled',
                'deleted_at': None, 'lease_worker_id': None, 'lease_worker_pid': None,
                'lease_heartbeat_at': None, 'cancel_requested_at': None,
                'stage_id': 'original-stage' if index == 0 else 'stage-miraform',
                'active_stage_id': 'original-stage' if index == 0 else None},
                'stageCount': 1 if index == 0 else 0, 'sceneCount': 8 if index == 0 else 0,
                'snapshot': quality_snapshot(source) if index == 0 else None,
                'events': [{'seq': 12, 'type': 'tool_execution_start'},
                    {'seq': 13, 'type': 'tool_execution_end'}, deepcopy(terminal)],
                'ownerEvents': [{'id': '4', 'owner_id': owner, 'session_id': session_id,
                    'type': 'session_cancel_requested', 'ts': 4000}]})
        return {'schemaVersion': recovery.SCHEMA, 'identity': identity,
            'selectedRuntimeId': 'runtime-1', 'duplicateRuntimeId': 'runtime-2',
            'state': {'runtimes': rows, 'otherTouchedItems': [], 'receipt': None,
                'requests': [{'subject': 'math', 'skill_id': 'fraction_ratio_percentage', 'variant_ordinal': 1}],
                'item': {'id': 'item-fixture', 'course_id': 'course-fixture', 'course_version': 'v1',
                    'content_gate_status': 'passed', 'content_phase': 'course_ready'},
                'owner': {'id': 'plan-fixture', 'status': 'running', 'stage': 'generating_content',
                    'superseded_at': None, 'lease_token': None, 'catalog_build_id': 'build-fixture',
                    'library_target_fingerprint': 'target-fixture'}},
            'files': files, 'nativeSessions': native,
            'usage': {row['id']: {table: 0 for table in recovery.USAGE_TABLES} for row in rows},
            'paidLedger': [{'id': 'unknown-hold', 'status': 'unknown', 'reserved_units_json': '{"calls":1}'},
                {'id': 'charged-search', 'status': 'committed', 'charged_units_json': '{"calls":2}'}],
            'ownerEvents': [{'id': 'old-event', 'event_type': 'runtime_failed'}]}

    def archive(self, proof=None):
        proof = self.proof if proof is None else proof
        sha = digest(proof)
        self.archives.mkdir(exist_ok=True)
        (self.archives / f'duplicate-runtime-selection-{sha}.json').write_text(canonical(proof))
        return sha

    def reject(self, change):
        proof = deepcopy(self.proof)
        change(proof)
        with self.assertRaises(ValueError):
            recovery.validate_plan(proof)

    def test_real_cancel_shape_accepts_unused_placeholder_and_preserves_prior_tool_history(self):
        before = deepcopy(self.proof)
        selected, duplicate = recovery.validate_plan(self.proof)
        self.assertEqual((selected['id'], duplicate['id']), ('runtime-1', 'runtime-2'))
        self.assertTrue(any(e['type'] == 'tool_execution_start' for e in self.proof['nativeSessions'][1]['events']))
        self.assertEqual(self.proof, before)

    def test_third_runtime_or_wrong_selected_identity_cannot_use_exception(self):
        changes = [lambda p: p['state']['runtimes'].append(deepcopy(p['state']['runtimes'][1])),
            lambda p: p.update(selectedRuntimeId='runtime-2'),
            lambda p: p['identity'].update(targetFingerprint='other-target'),
            lambda p: p['identity'].update(buildItemId='other-item'),
            lambda p: p['state']['item'].update(course_id='other-course'),
            lambda p: p['state']['runtimes'][1].update(retry_of_runtime_id='unrelated-runtime')]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.reject(change)

    def test_duplicate_content_active_work_or_release_receipt_blocks_selection(self):
        changes = [lambda p: p['nativeSessions'][1].update(stageCount=1),
            lambda p: p['nativeSessions'][1].update(sceneCount=1),
            lambda p: p['nativeSessions'][1].update(snapshot={'stage': {'id': 'new-stage'}, 'scenes': []}),
            lambda p: p['nativeSessions'][1]['session'].update(active_stage_id='new-stage'),
            lambda p: p['nativeSessions'][1]['session'].update(lease_worker_id='worker:123'),
            lambda p: p['state'].update(receipt={'runtime_classroom_id': 'runtime-2'}),
            lambda p: p['state']['otherTouchedItems'].append('another-item')]
        for index, change in enumerate(changes):
            with self.subTest(case=index): self.reject(change)

    def test_every_student_media_and_probe_binding_is_a_hard_stop(self):
        for table in recovery.USAGE_TABLES:
            with self.subTest(table=table):
                self.reject(lambda p: p['usage']['runtime-2'].update({table: 1}))

    def test_missing_or_forged_official_cancel_evidence_is_rejected(self):
        for key, edit in [('cancelReceipt', lambda x: x.update(officialMethod='manual_status_patch')),
                ('cancelReceipt', lambda x: x.update(beforeSha256='0' * 64)),
                ('cancelReceipt', lambda x: x.update(sessionId='another-session')),
                ('cancelAfter', lambda x: x['terminalEvent']['data'].update(status='running')),
                ('cancelBefore', lambda x: x.update(stages=[{'id': 'authored-stage'}]))]:
            with self.subTest(key=key):
                proof = deepcopy(self.proof)
                self.replace_file(proof, key, edit)
                with self.assertRaises(ValueError): recovery.validate_plan(proof)
        self.reject(lambda p: p['nativeSessions'][1].update(events=[]))
        self.reject(lambda p: p['nativeSessions'][1].update(ownerEvents=[]))

    def test_archive_checks_own_digest_and_revalidates_evidence(self):
        sha = self.archive()
        self.assertEqual(recovery.load_archive(sha), self.proof)
        path = self.archives / f'duplicate-runtime-selection-{sha}.json'
        edited = deepcopy(self.proof); edited['selectedRuntimeId'] = 'runtime-2'
        path.write_text(canonical(edited))
        with self.assertRaises(ValueError): recovery.load_archive(sha)
        forged_sha = self.archive(edited)
        with self.assertRaises(ValueError): recovery.load_archive(forged_sha)
        for token in ('../outside', 'short', 'A' * 64):
            with self.subTest(token=token), self.assertRaises(ValueError): recovery.load_archive(token)

    def authorization_context(self):
        sha = self.archive()
        state = deepcopy(self.proof['state'])
        state['runtimes'][1]['retired_at'] = 5000
        event = {'recoveryReceiptId': sha, 'selectedRuntimeId': 'runtime-1', 'duplicateRuntimeId': 'runtime-2',
            'code': 'saved_stage_completion_and_publication_only', 'historicalRuntimeCount': 2,
            'newInstanceCount': 0}
        conn = self.connection(state, [{'payload_json': json.dumps(event), 'created_at': 5000}])
        patch.object(recovery, '_native_evidence', return_value=deepcopy(self.proof['nativeSessions'])).start()
        patch.object(recovery, '_usage', side_effect=lambda conn, rows:
            {r['id']: deepcopy(self.proof['usage'][r['id']]) for r in rows}).start()
        return sha, state, event, conn

    def connection(self, state, events=None):
        conn = Mock()
        conn.database_state = deepcopy(state)
        conn.event_rows = deepcopy(events or [])

        def execute(sql, parameters):
            self.assertTrue(sql.startswith('SELECT '), 'offline connection must not execute writes')
            result = Mock()
            if 'FROM learning_openmaic_runtime_classrooms ' in sql:
                result.fetchall.return_value = deepcopy(conn.database_state['runtimes'])
            elif 'FROM learning_curriculum_preparation_plans ' in sql:
                result.fetchone.return_value = deepcopy(conn.database_state['owner'])
            elif 'FROM learning_catalog_build_items ' in sql:
                result.fetchone.return_value = deepcopy(conn.database_state['item'])
            elif 'FROM learning_curriculum_classroom_item_receipts ' in sql:
                result.fetchone.return_value = deepcopy(conn.database_state['receipt'])
            elif 'FROM learning_course_supply_requests ' in sql:
                result.fetchall.return_value = deepcopy(conn.database_state['requests'])
            elif 'FROM learning_curriculum_preparation_events ' in sql:
                result.fetchall.return_value = deepcopy(conn.event_rows)
            else:
                self.fail('unexpected offline query: ' + sql)
            return result

        conn.execute.side_effect = execute
        return conn

    def test_archive_alone_cannot_authorize_selection_without_database_event(self):
        sha, state, event, conn = self.authorization_context()
        for events in ([], [{'payload_json': json.dumps(event)}] * 2):
            with self.subTest(events=len(events)):
                conn.event_rows = events
                with self.assertRaises(ValueError):
                    recovery.authorized_selection(conn, identity=self.proof['identity'], state=state,
                        runtime_id='runtime-1', audit_sha=sha)

    def test_authorized_tail_keeps_both_attempts_and_unknown_paid_reservations(self):
        sha, state, _, conn = self.authorization_context()
        before = deepcopy(state)
        selected, reopened = recovery.authorized_selection(conn, identity=self.proof['identity'], state=state,
            runtime_id='runtime-1', audit_sha=sha)
        self.assertEqual(selected['id'], 'runtime-1')
        self.assertEqual(state, before)
        self.assertEqual(len(state['runtimes']), 2)
        self.assertEqual(reopened['paidLedger'], self.proof['paidLedger'])
        self.assertEqual(reopened['paidLedger'][0]['status'], 'unknown')
        self.assertTrue(all(call.args[0].startswith('SELECT ') for call in conn.execute.call_args_list))

    def test_tail_rejects_new_duplicate_stage_after_authorization(self):
        sha, state, _, conn = self.authorization_context()
        changed = deepcopy(self.proof['nativeSessions']); changed[1]['stageCount'] = 1
        with patch.object(recovery, '_native_evidence', return_value=changed), self.assertRaises(ValueError):
            recovery.authorized_selection(conn, identity=self.proof['identity'], state=state,
                runtime_id='runtime-1', audit_sha=sha)

    def test_tail_rejects_wrong_target_changed_history_and_forged_event(self):
        sha, state, event, conn = self.authorization_context()
        cases = [('runtime-2', self.proof['identity'], deepcopy(state)),
            ('runtime-1', {**self.proof['identity'], 'targetFingerprint': 'other'}, deepcopy(state))]
        third = deepcopy(state); third['runtimes'].append({**third['runtimes'][1], 'id': 'runtime-3'})
        cases.append(('runtime-1', self.proof['identity'], third))
        for runtime_id, identity, current in cases:
            with self.subTest(runtime=runtime_id, count=len(current['runtimes'])), self.assertRaises(ValueError):
                recovery.authorized_selection(conn, identity=identity, state=current, runtime_id=runtime_id, audit_sha=sha)
        event['code'] = 'new_generation'
        conn.event_rows = [{'payload_json': json.dumps(event)}]
        with self.assertRaises(ValueError):
            recovery.authorized_selection(conn, identity=self.proof['identity'], state=state,
                runtime_id='runtime-1', audit_sha=sha)

    def test_tail_rechecks_database_history_instead_of_trusting_supplied_state(self):
        sha, state, _, conn = self.authorization_context()
        conn.database_state['runtimes'].append({**state['runtimes'][1], 'id': 'runtime-3'})
        with self.assertRaises(ValueError):
            recovery.authorized_selection(conn, identity=self.proof['identity'], state=state,
                runtime_id='runtime-1', audit_sha=sha)

    def plan_context(self):
        state = deepcopy(self.proof['state'])
        conn = self.connection(state)
        runtime_service, preparation = Mock(), Mock()

        @contextmanager
        def transaction():
            yield conn

        runtime_service.repository.transaction.side_effect = transaction

        def retire(connection, *, runtime_id, source_attempt_ordinal, now):
            self.assertIs(connection, conn)
            self.assertEqual((runtime_id, source_attempt_ordinal), ('runtime-2', 2))
            conn.database_state['runtimes'][1]['retired_at'] = now
            return True

        runtime_service.repository.retire_runtime_for_retry.side_effect = retire
        ledger = deepcopy(self.proof['paidLedger'])
        patch.object(recovery, '_usage', return_value=deepcopy(self.proof['usage'])).start()
        patch.object(recovery, '_ledger', side_effect=lambda *_: deepcopy(ledger)).start()
        patch.object(recovery, '_events', return_value=deepcopy(self.proof['ownerEvents'])).start()
        native = patch.object(recovery, '_native_evidence', return_value=deepcopy(self.proof['nativeSessions'])).start()
        options = {'runtime_service': runtime_service, 'preparation_repository': preparation,
            'identity': self.proof['identity'], 'state': state, 'runtime_id': 'runtime-1',
            'duplicate_runtime_id': 'runtime-2', 'evidence_dir': self.evidence,
            'source_snapshot': self.proof['files']['sourceSnapshot']['path'], 'now': 5000}
        return options, conn, native, ledger

    def test_offline_plan_apply_only_retires_successor_and_keeps_unknown_ledger(self):
        options, conn, _, ledger = self.plan_context()
        before = deepcopy(conn.database_state['runtimes'])
        plan = recovery.plan_or_apply(**options)
        options['runtime_service'].repository.retire_runtime_for_retry.assert_not_called()
        options['preparation_repository'].append_event.assert_not_called()
        applied = recovery.plan_or_apply(**options, apply=True, expected_sha=plan['expectedHistorySha256'])
        self.assertTrue(applied['applied'])
        self.assertEqual(applied['newInstances'], 0)
        self.assertFalse(applied['paidLedgerChanged'])
        self.assertEqual(conn.database_state['runtimes'], [before[0], {**before[1], 'retired_at': 5000}])
        self.assertEqual(ledger, self.proof['paidLedger'])
        self.assertEqual(recovery.load_archive(plan['expectedHistorySha256'])['paidLedger'], ledger)
        event = options['preparation_repository'].append_event.call_args.kwargs
        self.assertEqual(event['event_type'], recovery.EVENT)
        self.assertEqual(event['payload']['code'], 'saved_stage_completion_and_publication_only')
        self.assertEqual(event['payload']['historicalRuntimeCount'], 2)

    def test_apply_uses_real_repository_event_validation_and_sql_persistence(self):
        options, conn, _, _ = self.plan_context()
        database = sqlite3.connect(':memory:')
        database.row_factory = lambda cursor, row: dict(zip([c[0] for c in cursor.description], row))
        self.addCleanup(database.close)
        database.execute('CREATE TABLE learning_curriculum_preparation_events '
            '(id TEXT PRIMARY KEY,plan_id TEXT,event_type TEXT,stage TEXT,payload_json TEXT,created_at INTEGER)')
        original_execute = conn.execute.side_effect
        def execute(sql, parameters):
            if ('INSERT INTO learning_curriculum_preparation_events' in sql
                    or 'WHERE id = ? LIMIT 1' in sql):
                return database.execute(sql.replace('ON DUPLICATE KEY UPDATE id = id',
                    'ON CONFLICT(id) DO NOTHING'), parameters)
            return original_execute(sql, parameters)
        conn.execute.side_effect = execute
        options['preparation_repository'] = LearningCurriculumPreparationRepository(database)
        plan = recovery.plan_or_apply(**options)
        result = recovery.plan_or_apply(**options, apply=True, expected_sha=plan['expectedHistorySha256'])
        self.assertTrue(result['applied'])
        row = database.execute('SELECT * FROM learning_curriculum_preparation_events').fetchone()
        self.assertEqual(row['created_at'], conn.database_state['runtimes'][1]['retired_at'])
        payload = json.loads(row['payload_json'])
        self.assertEqual(payload['code'], 'saved_stage_completion_and_publication_only')
        self.assertEqual(payload['newInstanceCount'], 0)
        self.assertNotIn('retiredAt', payload)
        state = deepcopy(conn.database_state)
        conn.event_rows = [row]
        selected, _ = recovery.authorized_selection(conn, identity=options['identity'], state=state,
            runtime_id='runtime-1', audit_sha=plan['expectedHistorySha256'])
        self.assertEqual(selected['id'], 'runtime-1')
        # The global public-payload contract remains strict.
        for bad in ({'retiredAt': 5000}, {'newInstances': 0}, {'purpose': 'anything'}):
            with self.assertRaisesRegex(ValueError, 'non-public field'):
                options['preparation_repository'].append_event(conn, plan_id='plan-fixture',
                    event_type=recovery.EVENT, stage='generating_content', payload=bad, now=5001)

    def test_apply_rejects_changed_live_cancel_evidence_before_retirement(self):
        options, _, native, _ = self.plan_context()
        plan = recovery.plan_or_apply(**options)
        changed = deepcopy(self.proof['nativeSessions'])
        changed[1]['session']['status'] = 'running'
        native.side_effect = [deepcopy(self.proof['nativeSessions']), changed]
        with self.assertRaises(ValueError):
            recovery.plan_or_apply(**options, apply=True, expected_sha=plan['expectedHistorySha256'])
        options['runtime_service'].repository.retire_runtime_for_retry.assert_not_called()
        options['preparation_repository'].append_event.assert_not_called()


if __name__ == '__main__':
    unittest.main()
