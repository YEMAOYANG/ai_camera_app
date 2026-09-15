from contextlib import ExitStack, nullcontext
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import generate_one_library_course as operator


class DuplicateRuntimeOperatorTest(unittest.TestCase):
    def test_audit_cannot_authorize_the_normal_generation_command(self):
        args = SimpleNamespace(command='run-to-review', grade='primary_6', subject='math',
            skill='fraction_ratio_percentage', slot=1, duplicate_recovery_sha='a' * 64)
        with patch.object(operator, 'operator_app') as app, self.assertRaisesRegex(RuntimeError, 'only the saved-stage'):
            operator.run(args)
        app.assert_not_called()

    def test_normal_scope_still_counts_the_retired_duplicate(self):
        args = SimpleNamespace(subject='math', skill='fraction_ratio_percentage', slot=1, budget_policy=None)
        state = {'requests': [{'subject': 'math', 'skill_id': args.skill, 'variant_ordinal': 1}],
            'dispatches': 7, 'otherTouchedItems': 0,
            'runtimes': [{'status': 'ready'}, {'status': 'failed', 'retired_at': 1000}]}
        with self.assertRaisesRegex(RuntimeError, 'single-course production ceiling exceeded'):
            operator.assert_scope(state, args)
        self.assertFalse(operator.review_ready({**state, 'receipt': {'classroom_status': 'passed',
            'tts_status': 'passed', 'asr_roundtrip_status': 'passed'}}))

    def run_tail(self, *, publishing=False, lease_lost=False, expired_deadline=False, renewal_rejected=False):
        plan = {'id': 'owner', 'stage': 'generating_content', 'status': 'running',
            'lease_token': 'lease', 'lease_expires_at': 500 if expired_deadline else 5000,
            'hard_deadline_at': 500 if expired_deadline else 5000}
        runtime = {'id': 'selected', 'status': 'ready', 'course_id': 'course', 'course_version': '1',
                   'upstream_job_id': 'saved-native-job'}
        state = {'owner': dict(plan), 'runtimes': [runtime, {'id': 'duplicate', 'retired_at': 900}],
            'receipt': {'runtime_classroom_id': 'selected', 'classroom_status': 'passed',
                        'tts_status': 'passed' if publishing else 'pending',
                        'asr_roundtrip_status': 'passed' if publishing else 'pending', 'publication_status': 'pending'}}
        args = SimpleNamespace(runtime_id='selected', grade='primary_6', duplicate_recovery_sha='a' * 64,
            review_output='unused.json')
        conn = Mock()
        library = SimpleNamespace(database=SimpleNamespace(transaction=lambda: nullcontext(conn)))
        repository = Mock()
        repository.transaction.side_effect = lambda: nullcontext(conn)
        repository.claim_next.return_value = dict(plan)
        repository.get_plan.side_effect = lambda *_: deepcopy(state['owner'])
        def renew(_conn, **kwargs):
            if renewal_rejected:
                return None
            state['owner'].update(lease_expires_at=kwargs['now'] + kwargs['lease_ms'],
                                  hard_deadline_at=kwargs['now'] + kwargs['lease_ms'])
            return deepcopy(state['owner'])
        repository.renew_saved_classroom_publication_lease.side_effect = renew
        processor = Mock()
        adapter = SimpleNamespace(repository=repository, runtime_candidate_processor=processor,
            formal_auto_publication_enabled=False)
        observed = []
        def advance(_plan, *, stage):
            observed.append(stage)
            self.assertIsNone(adapter.runtime_candidate_processor)
            self.assertEqual(adapter.formal_auto_publication_enabled, publishing)
            state['owner']['stage'] = 'generating_speech'
            if lease_lost:
                state['owner']['lease_token'] = 'other-lease'
            else:
                state['receipt'].update(tts_status='passed', asr_roundtrip_status='passed')
                if publishing:
                    state['receipt']['publication_status'] = 'published'
        adapter._process_progressive_formal_tail = Mock(side_effect=advance)
        with ExitStack() as stack, TemporaryDirectory() as folder:
            if publishing:
                confirmation = Path(folder) / 'approved.json'
                confirmation.write_text(json.dumps({'frozen': 'identity', 'status': 'approved'}))
                args.visual_confirmation = str(confirmation)
            stack.enter_context(patch('services.service_factory.learning_curriculum_preparation_checkpoint_adapter', return_value=adapter))
            stack.enter_context(patch('services.learning_duplicate_runtime_recovery.authorized_selection', return_value=(runtime, {})))
            stack.enter_context(patch.object(operator, 'inventory', side_effect=lambda *_: deepcopy(state)))
            stack.enter_context(patch.object(operator, 'now_ms', return_value=1000))
            stack.enter_context(patch.object(operator, 'write_review_request', return_value='review.json'))
            stack.enter_context(patch.object(operator, 'review_identity', return_value={'frozen': 'identity'}))
            stack.enter_context(patch.object(operator, 'emit'))
            tick = stack.enter_context(patch.object(operator.learning_curriculum_preparation_runner, 'run_once'))
            if lease_lost or renewal_rejected:
                with self.assertRaisesRegex(RuntimeError, 'renewal was rejected' if renewal_rejected else 'lease changed'):
                    operator.run_selected_saved_stage_tail(args, library, {'targetFingerprint': 'target'}, publishing=publishing)
            else:
                self.assertEqual(operator.run_selected_saved_stage_tail(args, library,
                    {'targetFingerprint': 'target'}, publishing=publishing), 0)
            tick.assert_not_called()
        self.assertEqual(observed, [] if renewal_rejected else ['generating_content'])
        processor.assert_not_called()
        self.assertIs(adapter.runtime_candidate_processor, processor)
        self.assertFalse(adapter.formal_auto_publication_enabled)
        self.assertEqual(len(state['runtimes']), 2)
        if expired_deadline and publishing:
            repository.renew_saved_classroom_publication_lease.assert_called_once_with(conn,
                plan_id='owner', lease_token='lease', runtime_id='selected', upstream_job_id='saved-native-job',
                target_fingerprint='target', now=1000, lease_ms=600_000)
        else:
            repository.renew_saved_classroom_publication_lease.assert_not_called()
        if lease_lost or renewal_rejected:
            repository.release_lease.assert_not_called()
        else:
            repository.release_lease.assert_called_once_with(conn, plan_id='owner', lease_token='lease',
                expected_stage='generating_speech', now=1000)

    def test_audio_review_tail_never_runs_generation_and_releases_current_stage(self):
        self.run_tail()

    def test_publication_uses_the_same_tail_without_generation(self):
        self.run_tail(publishing=True)

    def test_lost_tail_lease_stops_and_does_not_release_another_owners_lease(self):
        self.run_tail(lease_lost=True)

    def test_saved_publication_resumes_expired_generation_deadline_through_existing_gate(self):
        self.run_tail(publishing=True, expired_deadline=True)

    def test_saved_publication_wrong_binding_stops_before_validation_or_generation(self):
        self.run_tail(publishing=True, expired_deadline=True, renewal_rejected=True)

    def test_audio_review_does_not_renew_generation_or_publication_authority(self):
        self.run_tail(expired_deadline=True)
