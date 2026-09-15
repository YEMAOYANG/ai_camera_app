import json
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask

from scripts.generate_one_library_course import write_policy, assert_search_budget_ready
from scripts import generate_one_library_course as operator
from content.single_course_budget import build_single_course_policy


class SingleCourseOperatorGuardsTest(unittest.TestCase):
    def test_new_policy_cannot_replace_a_paused_file_or_follow_an_existing_symlink(self):
        paused = SimpleNamespace(raw={'enabled': False, 'authorizationWindow': {'expiresAt': 123}})
        new = SimpleNamespace(raw={'enabled': True, 'authorizationWindow': {'expiresAt': 999}})
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'policy.json'
            write_policy(path, paused, create_only=True)
            original = path.read_bytes()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                write_policy(path, new, create_only=True)
            self.assertEqual(path.read_bytes(), original)
            link = Path(folder) / 'link.json'
            missing = Path(folder) / 'missing.json'
            link.symlink_to(missing)
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                write_policy(link, new, create_only=True)
            self.assertFalse(missing.exists())
            write_policy(path, new)  # Existing pause/close update path remains available.
            self.assertEqual(json.loads(path.read_text()), new.raw)

    def test_search_mismatch_stops_before_any_database_or_provider_work(self):
        policy, identity = build_single_course_policy(grade='primary_6', subject='math',
            skill='fraction_ratio_percentage', ordinal=1, now=1000)
        runtime = SimpleNamespace(client=SimpleNamespace(formal_generation_readiness=Mock(return_value={
            'ready': True, 'webSearch': {'providerId': 'baidu', 'productionMode': 'baidu_api',
                'formalProductionConfigured': True, 'verification': 'configuration_only'}})))
        library = SimpleNamespace(database=Mock())
        with TemporaryDirectory() as folder:
            path = write_policy(Path(folder) / 'policy.json', policy, create_only=True)
            with self.assertRaisesRegex(ValueError, 'differs from the selected production budget'):
                assert_search_budget_ready(SimpleNamespace(budget_policy=str(path)), library,
                    identity, runtime, {'dispatches': 0, 'runtimes': []})
        library.database.transaction.assert_not_called()
        runtime.client.formal_generation_readiness.assert_called_once_with()


class SingleCourseOperatorTickGuardsTest(unittest.TestCase):
    def setUp(self):
        self.state = {
            'requests': [{'subject': 'math', 'skill_id': 'fraction_ratio_percentage', 'variant_ordinal': 1}],
            'owner': {'status': 'running'},
            'item': {'status': 'course_ready', 'content_phase': 'course_ready', 'content_gate_status': 'passed'},
            'dispatches': 7,
            'runtimes': [{'status': 'generating', 'quality_status': 'pending_review',
                          'upstream_job_id': 'existing-job'}],
            'receipt': None, 'otherTouchedItems': 0,
        }
        self.args = SimpleNamespace(command='run-to-review', grade='primary_6', subject='math',
            skill='fraction_ratio_percentage', slot=1, budget_policy='original-policy.json',
            confirm_workers_stopped=True, timeout_seconds=30, once=True, review_output='unused-review.json')
        self.identity = {'buildItemId': 'existing-item', 'scope': {'existing': 'scope'}}
        self.app = Flask('single-course-operator-test')
        self.app.config.update(DATABASE_URL='unused', OPENMAIC_FULL_RUNTIME_INTERNAL_URL='http://native.invalid')
        self.runtime = Mock()
        self.runtime.formal_provider_circuit_status.return_value = {'dispatchAllowed': True}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        patches = {
            'single_slot_identity': Mock(return_value=self.identity),
            'operator_app': Mock(return_value=self.app),
            'learning_curriculum_preparation_service': Mock(),
            'CourseLibraryService': Mock(),
            'inventory': Mock(side_effect=lambda *_: deepcopy(self.state)),
            'openmaic_full_runtime_service': Mock(return_value=self.runtime),
            'assert_search_budget_ready': Mock(),
            'now_ms': Mock(return_value=1000),
            'emit': Mock(),
        }
        for name, replacement in patches.items():
            self.stack.enter_context(patch.object(operator, name, replacement))
        policy = SimpleNamespace(aggregate_limits_enabled=False,
            raw={'enabled': True, 'authorizationWindow': {'startsAt': 0, 'expiresAt': 2000,
                                                         'scopes': [self.identity['scope']]}})
        self.stack.enter_context(patch.object(operator.LearningBudgetPolicy, 'load', return_value=policy))
        self.stack.enter_context(patch('services.service_factory._checkpoint_question_phase_profile',
            return_value={'name': 'openmaic_runtime', 'model': 'courseware-v2', 'baseUrl': 'http://native.invalid'}))
        self.tick = self.stack.enter_context(patch.object(operator.learning_curriculum_preparation_runner, 'run_once'))
        self.sleep = self.stack.enter_context(patch.object(operator.time, 'sleep'))

    def test_status_failure_stops_before_tick_can_create_a_replacement(self):
        def fail_existing(_):
            self.state['runtimes'][0].update(status='failed', quality_status='rejected')
        self.runtime.generation_status.side_effect = fail_existing
        with self.assertRaisesRegex(RuntimeError, 'stopping without another instance'):
            operator.run(self.args)
        self.runtime.generation_status.assert_called_once_with('existing-job')
        self.tick.assert_not_called()
        self.sleep.assert_not_called()

    def test_status_poll_can_finish_normally_and_tick_can_process_ready_receipts(self):
        def ready_existing(_):
            self.state['runtimes'][0].update(status='ready', quality_status='passed')
        self.runtime.generation_status.side_effect = ready_existing
        self.assertEqual(operator.run(self.args), 0)
        self.tick.assert_called_once_with(self.app, now_ms=1000)

    def test_in_progress_status_keeps_the_normal_single_tick(self):
        self.assertEqual(operator.run(self.args), 0)
        self.runtime.generation_status.assert_called_once_with('existing-job')
        self.tick.assert_called_once_with(self.app, now_ms=1000)

    def test_inner_tick_failure_is_rejected_before_once_reports_completion(self):
        def fail_in_tick(*_args, **_kwargs):
            self.state['runtimes'][0].update(status='failed', quality_status='rejected')
        self.tick.side_effect = fail_in_tick
        with self.assertRaisesRegex(RuntimeError, 'stopping without another instance'):
            operator.run(self.args)
        self.tick.assert_called_once()
        self.assertNotIn('step_completed', [call.args[0] for call in operator.emit.call_args_list])
        self.sleep.assert_not_called()

    def test_inner_tick_extra_instance_is_rejected_without_a_second_tick(self):
        def create_extra(*_args, **_kwargs):
            self.state['runtimes'].append({'status': 'generating', 'upstream_job_id': 'unexpected-job'})
        self.tick.side_effect = create_extra
        with self.assertRaisesRegex(RuntimeError, 'single-course production ceiling exceeded'):
            operator.run(self.args)
        self.tick.assert_called_once()
        self.assertNotIn('step_completed', [call.args[0] for call in operator.emit.call_args_list])
        self.sleep.assert_not_called()
