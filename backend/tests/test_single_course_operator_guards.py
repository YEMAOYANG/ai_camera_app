import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from scripts.generate_one_library_course import write_policy, assert_search_budget_ready
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
