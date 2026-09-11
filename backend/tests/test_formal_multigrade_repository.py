"""Exact local test DB integration; creates no Provider or runtime calls."""
from __future__ import annotations

import json
import unittest

from core.database import Database
from repositories.learning_catalog_repository import LearningCatalogRepository
from repositories.lesson_package_repository import LessonPackageRepository
from services.course_library_service import CourseLibraryService
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_curriculum_preparation_runner import CheckpointSharedBuildAdapter
from tests.support import fresh_test_config, validated_test_database_url


class FormalMultigradeRepositoryTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.url = validated_test_database_url(config['DATABASE_URL'])
        self.catalog = LearningCatalogRepository(Database(self.url))
        self.release = LearningCatalogReleaseService(
            self.url, dynamic_generation_service=None, lesson_package_service=None,
            clock_ms=lambda: 1000,
        )

    def plan(self, grade):
        library = CourseLibraryService(self.url, grade_code=grade, clock=lambda: 1000)
        library.request_scope('canary')
        with library.preparations.transaction() as conn:
            plan = library.preparations.claim_next(
                conn, now=1000, lease_ms=360000, grade_code=grade,
                target_fingerprint=library.fingerprint,
            )
        self.assertIsNotNone(plan)
        result = CheckpointSharedBuildAdapter(
            self.release, repository=library.preparations, clock=lambda: 1000,
        ).advance(plan, now_ms=1000, heartbeat=lambda: True)
        self.assertEqual(result.next_stage, 'generating_content')
        return library

    def test_all_six_grades_plan_exact_separate_manifest_without_paid_dispatch(self):
        owners = set(); builds = set(); fingerprints = set(); item_ids = set()
        for number in range(1, 7):
            grade = f'primary_{number}'
            with self.subTest(grade=grade):
                library = self.plan(grade)
                owner = library.ensure_owner()
                owners.add(owner['id']); builds.add(owner['catalog_build_id'])
                fingerprints.add(owner['target_fingerprint'])
                with self.catalog.transaction() as conn:
                    build = self.catalog.get_build(conn, build_id=owner['catalog_build_id'])
                    release = self.catalog.get_release(conn, release_id=build['release_id'])
                    rows = conn.execute('SELECT * FROM learning_catalog_build_items WHERE build_job_id = ?', (build['id'],)).fetchall()
                    self.assertEqual(build['total_item_count'], 30 if number == 1 else 27)
                    self.assertEqual(release['required_boundary_count'], 10 if number == 1 else 9)
                    self.assertEqual(len(rows), build['total_item_count'])
                    self.assertEqual({r['grade_code'] for r in rows}, {grade})
                    self.assertTrue(item_ids.isdisjoint({r['id'] for r in rows}))
                    item_ids.update(r['id'] for r in rows)
                    self.assertEqual(json.loads(build['target_spec_json']), library.target)
                    claim = self.catalog.claim_next_content_item(conn, build_id=build['id'], now=2000, lease_ms=60000)
                    self.assertEqual(claim['grade_code'], grade)
                    self.assertEqual(claim['skill_id'], library.target['canaryManifest']['targets'][0]['skillId'])
                status = library.status()
                self.assertEqual(status['requestedCount'], 3)
                self.assertEqual(status['readyCount'], 0)
                self.assertEqual(status['gradeCode'], grade)
        self.assertEqual(len(owners), 6); self.assertEqual(len(builds), 6)
        self.assertEqual(len(fingerprints), 6)
        with self.catalog.transaction() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM learning_course_provider_dispatches').fetchone()['n'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM learning_openmaic_runtime_classrooms').fetchone()['n'], 0)

    def test_narrowed_scope_and_candidate_query_remain_grade_lease_bound(self):
        libraries = [self.plan(grade) for grade in ('primary_2', 'primary_6')]
        second, sixth = libraries
        second.request_scope('first_unit'); second.request_scope('canary')
        second.request_scope('catalog', preserve_existing_scope=True)
        self.assertEqual(second.status()['requestedCount'], 3)
        self.assertEqual(sixth.status()['requestedCount'], 3)
        packages = LessonPackageRepository(Database(self.url))
        for library in libraries:
            with library.preparations.transaction() as conn:
                plan = library.preparations.claim_next(
                    conn, now=2000, lease_ms=360000,
                    grade_code=library.target['gradeCode'],
                    target_fingerprint=library.fingerprint,
                )
            self.assertIsNotNone(plan)
            # No Host receipt/media exists, so neither grade may invent a
            # candidate or accidentally return the other grade's pending row.
            with packages.transaction() as conn:
                self.assertIsNone(packages.get_next_formal_candidate_authority(conn, preparation_plan=plan))
            corrupted = {**plan, 'grade_code': 'primary_1'}
            with packages.transaction() as conn, self.assertRaises(ValueError):
                packages.get_next_formal_candidate_authority(conn, preparation_plan=corrupted)
        with self.catalog.transaction() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM learning_course_provider_dispatches').fetchone()['n'], 0)

    def test_multigrade_migration_keeps_explicit_grade_and_sealed_counts(self):
        import pymysql
        library = self.plan('primary_6')
        plan = library.ensure_owner()
        for assignments, params in (
            ('grade_code = ?', ('primary_2',)),
            ('total_course_count = ?', (30,)),
            ('target_spec_json = JSON_REMOVE(target_spec_json, ?)', ('$.gradeCode',)),
            ('target_spec_json = JSON_SET(target_spec_json, ?, ?)', ('$.courseTargets', 'missing')),
        ):
            with self.subTest(assignments=assignments):
                with self.assertRaises(pymysql.err.OperationalError):
                    with self.catalog.transaction() as conn:
                        conn.execute('UPDATE learning_curriculum_preparation_plans SET '+assignments+' WHERE id = ?', (*params, plan['id']))

    def test_current_owner_does_not_reopen_older_compatible_production_scope(self):
        from services.learning_curriculum_preparation_contract import preparation_target_fingerprint
        from integrations.openmaic_formal_media import compatible_preparation_targets, PROFESSIONAL_POLICY
        old = CourseLibraryService(self.url, grade_code='primary_1', clock=lambda: 1000)
        old.target = next(target for target in compatible_preparation_targets(old.target)
                          if target['formalRuntimePolicy']['professionalCreationPolicy'] == PROFESSIONAL_POLICY)
        old.fingerprint = preparation_target_fingerprint(old.target)
        old.request_scope('first_unit')
        old_owner_id = old.ensure_owner()['id']
        current = CourseLibraryService(self.url, grade_code='primary_1', clock=lambda: 1001)
        current.request_scope('canary')
        with current.preparations.transaction() as conn:
            claimed = current.preparations.claim_next(conn, now=2000, lease_ms=360000,
                grade_code='primary_1', target_fingerprint=current.fingerprint)
            self.assertEqual(claimed['target_fingerprint'], current.fingerprint)
            self.assertIsNone(current.preparations.claim_next(conn, now=2001, lease_ms=360000,
                grade_code='primary_1', target_fingerprint=current.fingerprint))
            self.assertEqual(current.preparations.get_plan(conn, old_owner_id)['status'], 'queued')


if __name__ == '__main__':
    unittest.main()
