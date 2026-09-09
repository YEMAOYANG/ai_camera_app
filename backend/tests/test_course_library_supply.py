from __future__ import annotations

import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from core.database import Database
from services.course_library_service import CourseLibraryService, supply_targets, prioritize_demand
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_curriculum_preparation_runner import CheckpointSharedBuildAdapter
from tests.support import fresh_test_config


class CourseLibrarySupplyTest(unittest.TestCase):
    def setUp(self):
        self.config = fresh_test_config()
        self.library = CourseLibraryService(self.config['DATABASE_URL'], clock=lambda: 1000)

    def test_owner_is_idempotent_without_any_child_or_family(self):
        first = self.library.ensure_owner()
        second = self.library.ensure_owner()
        self.assertEqual(first['id'], second['id'])
        self.assertIsNone(first['child_id'])
        self.assertIsNone(first['family_id'])
        with self.library.database.transaction() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM children').fetchone()['n'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM learning_curriculum_preparation_plans').fetchone()['n'], 1)

    def test_replenishment_is_deduplicated_and_never_counts_candidates_as_ready(self):
        self.library.request_scope('canary')
        self.library.request_scope('canary')
        self.assertEqual(self.library.status()['requestedCount'], 3)
        self.assertEqual(self.library.status()['readyCount'], 0)
        self.library.request_scope('first_unit')
        self.library.request_scope('first_unit')
        status = self.library.status()
        self.assertEqual(status['requestedCount'], 12)
        self.assertEqual(status['missingCount'], 12)
        for subject in ('chinese', 'math', 'english'):
            self.assertEqual(sum(r['subject'] == subject for r in status['items']), 4)

    def _plan_library(self):
        self.library.request_scope('canary')
        repo = self.library.preparations
        with repo.transaction() as conn:
            plan = repo.claim_next(conn, now=1000, lease_ms=360000,
                                   grade_code='primary_1', target_fingerprint=self.library.fingerprint)
        self.assertIsNotNone(plan)
        adapter = CheckpointSharedBuildAdapter(
            LearningCatalogReleaseService(self.config['DATABASE_URL'], dynamic_generation_service=None, lesson_package_service=None, clock_ms=lambda: 1000),
            repository=repo, clock=lambda: 1000,
        )
        result = adapter.advance(plan, now_ms=1000, heartbeat=lambda: True)
        self.assertEqual(result.next_stage, 'generating_content')
        with repo.transaction() as conn:
            count = conn.execute('SELECT COUNT(*) AS n FROM learning_catalog_build_items').fetchone()['n']
            self.assertEqual(count, 30)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM learning_course_provider_dispatches').fetchone()['n'], 0)

    def test_library_owner_can_plan_a_real_build_without_a_child(self):
        self._plan_library()

    def test_concurrent_owner_reservations_share_one_production_identity(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: self.library.ensure_owner()['id'], range(24)))
        self.assertEqual(len(set(ids)), 1)

    def test_reconciliation_activity_does_not_move_actual_progress(self):
        self._plan_library()
        repo = self.library.preparations
        service = LearningCatalogReleaseService(self.config['DATABASE_URL'], dynamic_generation_service=None, lesson_package_service=None)
        repo.content_proof_auditor = service.audit_locked_content_proofs
        with repo.transaction() as conn:
            owner = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint = ?', (self.library.fingerprint,)).fetchone()
            before = owner['last_progress_at']
            repo.reconcile_shared_build(conn, build_id=owner['catalog_build_id'], target_fingerprint=self.library.fingerprint, now=99999)
            after = repo.get_plan(conn, owner['id'])
            self.assertEqual(after['updated_at'], 99999)
            self.assertEqual(after['last_progress_at'], before)

    def test_repeated_owner_lookup_does_not_postpone_scheduled_work(self):
        self._plan_library()
        repo = self.library.preparations
        service = LearningCatalogReleaseService(self.config['DATABASE_URL'], dynamic_generation_service=None, lesson_package_service=None)
        repo.content_proof_auditor = service.audit_locked_content_proofs
        before = self.library.ensure_owner()
        self.library.clock = lambda: 99999
        for _ in range(3):
            current = self.library.ensure_owner()
            self.assertEqual(current['next_run_at'], before['next_run_at'])
        with repo.transaction() as conn:
            claimed = repo.claim_next(conn, now=99999, lease_ms=360000,
                                      grade_code='primary_1', target_fingerprint=self.library.fingerprint)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed['id'], before['id'])

    def test_changed_runtime_failure_requires_fresh_review_after_an_authorized_retry(self):
        from repositories.course_supply_repository import record_supply_incident
        self._plan_library()
        with self.library.database.transaction() as conn:
            item = conn.execute('SELECT id FROM learning_catalog_build_items LIMIT 1').fetchone()
            record_supply_incident(conn, item_id=item['id'], stage='classroom', reason='failed', runtime_id='attempt-one', now=1000)
            conn.execute('UPDATE learning_course_supply_incidents SET resolved_at = 1100 WHERE build_item_id = ?', (item['id'],))
            record_supply_incident(conn, item_id=item['id'], stage='classroom', reason='failed', runtime_id='attempt-one', now=1200)
            self.assertEqual(conn.execute('SELECT resolved_at FROM learning_course_supply_incidents WHERE build_item_id = ?', (item['id'],)).fetchone()['resolved_at'], 1100)
            record_supply_incident(conn, item_id=item['id'], stage='classroom', reason='failed', runtime_id='attempt-two', now=1300)
            self.assertIsNone(conn.execute('SELECT resolved_at FROM learning_course_supply_incidents WHERE build_item_id = ?', (item['id'],)).fetchone()['resolved_at'])

    def test_narrower_scope_disables_old_requests_without_erasing_audit(self):
        self.library.request_scope('first_unit')
        self.library.request_scope('canary')
        self.assertEqual(self.library.status()['requestedCount'], 3)
        with self.library.database.transaction() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM learning_course_supply_requests').fetchone()['n'], 12)

    def test_fast_and_struggling_learners_keep_prerequisites_and_scope(self):
        desired = supply_targets(self.library.target, self.library.policy, 'first_unit')
        mastered = [dict(child_id='fast', subject='math', node_code='number_sense_20', mastery_level='mastered')]
        boosted = prioritize_demand(desired, mastered, forward_boundaries=1)
        next_core = next(r for r in boosted if r['subject'] == 'math' and r['boundaryOrdinal'] == 2 and r['variantOrdinal'] == 1)
        self.assertEqual(next_core['priority'], 1)
        struggling = prioritize_demand(desired, [dict(child_id='slow', subject='math', node_code='number_sense_20', mastery_level='needs_practice')], forward_boundaries=1)
        review = next(r for r in struggling if r['subject'] == 'math' and r['boundaryOrdinal'] == 1 and r['variantOrdinal'] == 2)
        self.assertEqual(review['priority'], 1)
        self.assertTrue(all(r['boundaryOrdinal'] <= 2 for r in boosted + struggling))

    def test_internal_status_requires_auth_and_etag_reads_never_dispatch(self):
        from flask import Flask
        from routes.internal.learning_curriculum_preparations import internal_learning_curriculum_preparations_bp
        app = Flask('course-library-read-test')
        app.config.update(self.config)
        app.config['INTERNAL_API_TOKEN'] = 'test-library-status-token'
        app.register_blueprint(internal_learning_curriculum_preparations_bp, url_prefix='/internal/learning/curriculum-preparations')
        client = app.test_client()
        path = '/internal/learning/curriculum-preparations/library/status'
        self.assertEqual(client.get(path).status_code, 401)
        headers = {'X-Mira-Internal-Token': 'test-library-status-token'}
        first = client.get(path, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json['library']['state'], 'not_started')
        second = client.get(path, headers={**headers, 'If-None-Match': first.headers['ETag']})
        self.assertEqual(second.status_code, 304)
        with self.library.database.transaction() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM learning_course_provider_dispatches').fetchone()['n'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM learning_curriculum_preparation_plans').fetchone()['n'], 0)

    def test_cached_summary_distinguishes_delay_from_known_stop(self):
        from services import course_library_service as module
        status = {'planId': 'shared-owner', 'version': 'v1', 'requestedCount': 3, 'readyCount': 0,
                  'blocked': False, 'stalled': True, 'lastProgressAt': 1000}
        module._status_cache.clear()
        with patch.object(module.CourseLibraryService, 'status', return_value=status) as query:
            first = module.cached_supply_summary(self.config['DATABASE_URL'], grade_code='primary_1')
            second = module.cached_supply_summary(self.config['DATABASE_URL'], grade_code='primary_1')
            self.assertEqual(first, second)
            self.assertFalse(first['paused'])
            self.assertTrue(first['delayed'])
            self.assertEqual(query.call_count, 1)
        module._status_cache.clear()

    def test_scope_rejects_unknown_modes_without_creating_production(self):
        with self.assertRaises(ValueError):
            self.library.request_scope('all_grades')
        self.assertEqual(self.library.status()['state'], 'not_started')

    def test_one_blocked_subject_does_not_pause_healthy_siblings(self):
        from services import course_library_service as module
        status = {'planId': 'shared-owner', 'version': 'v1', 'requestedCount': 3,
                  'readyCount': 0, 'blocked': True, 'stalled': False,
                  'lastProgressAt': 1000, 'waitReason': 'course_review_required',
                  'items': [{'reason_code': 'quality_rejected', 'runtime_status': 'failed'},
                            {'reason_code': 'search_limited', 'runtime_status': 'failed'},
                            {'runtime_status': 'generating'}]}
        with patch.object(module.CourseLibraryService, 'status', return_value=status):
            def summary():
                module._status_cache.clear()
                return module.cached_supply_summary(self.config['DATABASE_URL'], grade_code='primary_1')
            self.assertFalse(summary()['paused'])
            status['waitReason'] = 'provider_quota_exhausted'
            self.assertTrue(summary()['paused'])
            status['waitReason'] = 'course_review_required'
            status['items'][2] = {'reason_code': 'quality_rejected', 'runtime_status': 'failed'}
            self.assertTrue(summary()['paused'])
        module._status_cache.clear()


if __name__ == '__main__':
    unittest.main()
