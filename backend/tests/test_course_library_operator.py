import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from scripts.course_library import all_canaries_settled, check_research_dependency, run_canaries


class CourseLibraryOperatorTests(unittest.TestCase):
    def test_failed_preflight_prevents_paid_probe_and_retry_unblocking(self):
        app = Flask(__name__)
        app.config['DATABASE_URL'] = 'unused-preflight-test'
        library = Mock()
        library.ensure_owner.return_value = {}
        library.status.return_value = {'readyCount': 0}
        runtime = Mock()
        args = SimpleNamespace(confirm_paid_canaries=True, probe_provider=True,
                               retry_item='blocked-course', timeout_seconds=1)
        with TemporaryDirectory() as directory, \
                patch('scripts.generate_one_formal_course._operator_app', return_value=app), \
                patch('scripts.generate_one_formal_course.LOCK_PATH', Path(directory) / 'operator.lock'), \
                patch('scripts.course_library.CourseLibraryService', return_value=library), \
                patch('services.service_factory.learning_curriculum_preparation_checkpoint_adapter'), \
                patch('services.service_factory.openmaic_full_runtime_service', return_value=runtime), \
                patch('scripts.course_library.check_research_dependency', return_value={'ready': False}), \
                patch('scripts.course_library.unblock_known_retry') as unblock:
            with self.assertRaisesRegex(RuntimeError, 'research dependency is unavailable'):
                run_canaries(args)
            runtime.probe_formal_generation_provider.assert_not_called()
            runtime.formal_provider_circuit_status.assert_not_called()
            unblock.assert_not_called()

    def test_search_preflight_uses_a_short_query_without_model_rewrite_input(self):
        client = Mock()
        client._request_json.return_value = {'sources': [{'url': 'https://example.org/curriculum'}]}
        result = check_research_dependency(client, {'dependencyPreflight': {'searchQuery': '小学一年级 课程标准'}})
        self.assertTrue(result['ready'])
        client._request_json.assert_called_once_with('POST', '/api/web-search', body={'query': '小学一年级 课程标准'}, timeout_seconds=20)

    def test_search_errors_and_empty_results_do_not_authorize_generation(self):
        policy = {'dependencyPreflight': {'searchQuery': '小学一年级 课程标准'}}
        client = Mock()
        client._request_json.side_effect = RuntimeError('Brave Search error (429): private provider response')
        result = check_research_dependency(client, policy)
        self.assertFalse(result['ready'])
        self.assertEqual(result['reasonCode'], 'research_rate_limited')
        self.assertNotIn('private provider response', str(result))
        client._request_json.side_effect = None
        for response in ({'sources': []}, {'sources': [{'url': 'javascript:invalid'}]}, None):
            client._request_json.return_value = response
            self.assertFalse(check_research_dependency(client, policy)['ready'])

    def test_long_preflight_queries_are_rejected_before_any_request(self):
        client = Mock()
        with self.assertRaises(ValueError):
            check_research_dependency(client, {'dependencyPreflight': {'searchQuery': 'x' * 401}})
        client._request_json.assert_not_called()

    def test_stops_only_when_each_requested_course_is_published_or_blocked(self):
        status = {'items': [{'ready': True}, {'reason_code': 'quality_rejected'},
                            {'reason_code': 'search_rate_limited'}]}
        self.assertTrue(all_canaries_settled(status))
        status['items'][2] = {'runtime_status': 'generating'}
        self.assertFalse(all_canaries_settled(status))
        status['items'][2] = {'reason_code': 'old_failure', 'runtime_status': 'generating'}
        self.assertFalse(all_canaries_settled(status))

    def test_unstarted_or_incomplete_scope_cannot_be_mistaken_for_completion(self):
        self.assertFalse(all_canaries_settled({'items': []}))
        self.assertFalse(all_canaries_settled({'items': [{'ready': True}]}))
        self.assertFalse(all_canaries_settled({'items': [{}, {}, {}]}))
