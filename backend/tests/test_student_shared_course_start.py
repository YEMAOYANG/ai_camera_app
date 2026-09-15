from __future__ import annotations

import hashlib
import inspect
import json
import re
import sqlite3
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from core.errors import ApiError
from repositories.learning_repository import LearningRepository
from repositories.learning_curriculum_preparation_repository import LearningCurriculumPreparationRepository
from repositories.profile_repository import ProfileRepository
from repositories.student_learning_library_repository import StudentLearningLibraryRepository
from repositories.student_shared_course_repository import claim_published_shared_course, shared_course_rows
from services.learning_curriculum_preparation_contract import build_preparation_target, preparation_target_fingerprint
from services.learning_service import LearningService
from services.student_learning_service import StudentLearningService


class MemoryConnection:
    """Execute task/identity SQL in isolated SQLite, never the application's DB."""
    def __init__(self):
        self.raw = sqlite3.connect(':memory:')
        self.raw.row_factory = sqlite3.Row
        self.statements = []
        self.assets_available = True

    def execute(self, sql, params=()):
        self.statements.append((sql, tuple(params)))
        if sql.startswith('SELECT package.id FROM learning_lesson_packages'):
            return SimpleNamespace(fetchone=lambda: {'id': 'package-new'} if self.assets_available else None)
        sql = re.sub(r'\s+FOR UPDATE(?: SKIP LOCKED)?', '', sql)
        sql = sql.replace('ON DUPLICATE KEY UPDATE id = id', 'ON CONFLICT DO NOTHING')
        cursor = self.raw.execute(sql, params)
        return SimpleNamespace(
            rowcount=cursor.rowcount,
            fetchone=lambda: self._row(cursor.fetchone()),
            fetchall=lambda: [dict(row) for row in cursor.fetchall()],
        )

    @staticmethod
    def _row(row):
        return dict(row) if row is not None else None


class MemoryDatabase:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def transaction(self):
        try:
            yield self.conn
            self.conn.raw.commit()
        except Exception:
            self.conn.raw.rollback()
            raise


class SharedCourseStartTest(unittest.TestCase):
    def setUp(self):
        self.conn = MemoryConnection()
        self.db = MemoryDatabase(self.conn)
        self.repo = LearningRepository(self.db)
        self.target = build_preparation_target('primary_6')
        self.fingerprint = preparation_target_fingerprint(self.target)
        digest = hashlib.sha256(f'grade-build:{self.fingerprint}'.encode()).hexdigest()[:24]
        self.build_id, self.release_id = f'catalog_build_{digest}', f'catalog_release_{digest}'
        self.child = dict(id='child-primary6', family_id='family-a', grade_code='primary_6',
                          grade_selection_revision=1, grade_school_year_start=2026)
        self.course = dict(id='course-new', version='playful-v1', title='校园文化节', objective='理解百分数',
                           grade_code='primary_6', subject='math', node_code='fraction_ratio_percentage',
                           curriculum_version=self.target['curriculumVersion'], content_json='{}',
                           status='published', quality_status='released', content_origin='openmaic_generated',
                           retired_at=None, published_at=1000)
        self.available = dict(course_id=self.course['id'], course_version=self.course['version'],
                              build_item_id='item-new', target_fingerprint=self.fingerprint)
        task_columns = re.search(r'INSERT INTO tasks\((.*?)\)\s*VALUES',
                                 inspect.getsource(LearningRepository._insert_learning_task), re.S).group(1)
        columns = [name.strip() for name in task_columns.split(',')]
        self.conn.raw.execute('CREATE TABLE tasks (' + ','.join(
            name + (' TEXT PRIMARY KEY' if name == 'id' else ' TEXT UNIQUE' if name == 'learning_assignment_key' else '')
            for name in columns) + ')')
        plan_columns = re.search(r'INSERT INTO learning_curriculum_preparation_plans\((.*?)\)\s*VALUES',
                                 inspect.getsource(LearningCurriculumPreparationRepository.reserve_plan), re.S).group(1)
        names = [name.strip() for name in plan_columns.split(',')]
        names += ['catalog_build_id', 'catalog_release_id']
        self.conn.raw.execute('CREATE TABLE learning_curriculum_preparation_plans (' + ','.join(
            name + (' TEXT PRIMARY KEY' if name == 'id' else '') for name in names) + ')')
        self.conn.raw.execute('CREATE TABLE children (id, family_id, grade_code, grade_selection_revision, grade_school_year_start)')
        self.conn.raw.execute('CREATE TABLE learning_catalog_build_jobs (id, release_id, target_spec_json)')
        self.conn.raw.execute('CREATE TABLE learning_catalog_build_items (id, build_job_id, release_id, grade_code)')
        self.conn.raw.execute('CREATE TABLE learning_courses (' + ','.join(self.course) + ')')
        self.conn.raw.execute('CREATE TABLE student_learning_course_favorites (family_id,child_id,course_id,course_version)')
        self.insert('children', self.child)
        self.insert('learning_courses', self.course)
        self.insert('learning_catalog_build_jobs', dict(id=self.build_id, release_id=self.release_id,
                    target_spec_json=json.dumps(self.target, ensure_ascii=False, sort_keys=True, separators=(',', ':'))))
        self.insert('learning_catalog_build_items', dict(id='item-new', build_job_id=self.build_id,
                    release_id=self.release_id, grade_code='primary_6'))
        prep = LearningCurriculumPreparationRepository(self.db)
        self.owner, _ = prep.reserve_plan(
            self.conn, family_id=None, child_id=None, grade_code='primary_6', school_year_start_year=0,
            grade_selection_revision=0, target=self.target, target_fingerprint=self.fingerprint,
            request_id=f'library:{self.fingerprint}', shared_build_request_id=f'grade-build:{self.fingerprint}',
            now=1000, library_owned=True,
        )
        self.conn.execute('UPDATE learning_curriculum_preparation_plans SET catalog_build_id=?,catalog_release_id=? WHERE id=?',
                          (self.build_id, self.release_id, self.owner['id']))
        self.conn.raw.commit()
        self.inventory_patch = patch('repositories.course_supply_inventory.published_supply',
                                     return_value={('math','fraction_ratio_percentage',1): self.available})
        self.published = self.inventory_patch.start()
        self.addCleanup(self.inventory_patch.stop)

    def insert(self, table, row):
        self.conn.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))

    def visible(self, **overrides):
        scope = dict(family_id=self.child['family_id'], child_id=self.child['id'], grade_code='primary_6',
                     grade_selection_revision=1, course_id=self.course['id'], course_version=self.course['version'])
        return shared_course_rows(self.conn, **{**scope, **overrides})

    def service(self):
        service = StudentLearningService.__new__(StudentLearningService)
        principal = dict(id='student-a', family_id='family-a', child_id='child-primary6')
        service.student_auth_service = SimpleNamespace(authenticate=lambda token: {'principal':principal})
        service.static_catalog_enabled = False
        service.repository = self.repo
        learning = LearningService.__new__(LearningService)
        learning.profile_repository = ProfileRepository(self.db)
        learning.formal_learning_access_checker = None
        service.learning_service = learning
        return service

    def start(self):
        def visible(conn, **scope):
            rows = shared_course_rows(conn, **scope)
            return rows[0] if rows else None
        with patch.object(self.repo, 'get_student_visible_course', side_effect=visible), \
             patch('repositories.lesson_package_repository.LessonPackageRepository.get_active_formal_package',
                   return_value={'id':'package-new','version':1}) as package, \
             patch.object(self.repo, 'add_task_event'), \
             patch('services.student_learning_service.now_ms', return_value=1_789_100_000_000):
            result = self.service().start_course('token', self.course['id'], self.course['version'])
            package.assert_called_once()
            return result

    def test_real_child_grade_and_revision_scope_fail_closed(self):
        self.assertEqual(self.visible()[0]['id'], self.course['id'])
        for overrides in ({'family_id':'other-family'}, {'child_id':'other-child'},
                          {'grade_code':'primary_1'}, {'grade_selection_revision':0},
                          {'grade_selection_revision':2}, {'course_version':'other-version'}):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.visible(**overrides), [])

    def test_published_membership_and_subject_favorite_filters(self):
        self.assertEqual(self.visible(subject='english'), [])
        self.assertEqual(self.visible(favorite_only=True), [])
        self.insert('student_learning_course_favorites', dict(family_id='family-a',child_id='child-primary6',
                    course_id=self.course['id'],course_version=self.course['version']))
        self.assertEqual(len(self.visible(favorite_only=True)), 1)
        self.published.return_value = {}
        self.assertEqual(self.visible(), [])
        with self.assertRaises(ApiError) as failure:
            self.start()
        self.assertEqual(failure.exception.code, 'learning_course_not_found')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) AS n FROM tasks').fetchone()['n'], 0)

    def test_start_claims_only_exact_child_follower_and_is_idempotent(self):
        owner_before = self.conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id=?', (self.owner['id'],)).fetchone()
        first, second = self.start(), self.start()
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(first['taskId'], second['taskId'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) AS n FROM tasks').fetchone()['n'], 1)
        follower = self.conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE child_id=?', (self.child['id'],)).fetchone()
        self.assertEqual(follower['catalog_build_id'], self.build_id)
        self.assertEqual(follower['catalog_release_id'], self.release_id)
        self.assertIsNone(follower['library_target_fingerprint'])
        self.assertIsNotNone(follower['next_run_at'])
        self.assertEqual(follower['status'], 'queued')
        self.assertEqual(follower['target_fingerprint'], self.fingerprint)
        self.assertEqual(owner_before, self.conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id=?', (self.owner['id'],)).fetchone())
        self.assertTrue(any('children' in sql and 'FOR UPDATE' in sql for sql, _ in self.conn.statements))

    def test_different_versions_keep_old_task_and_progress(self):
        old_course = {**self.course, 'version':'old-v1'}
        old, _ = self.repo.assign_today_task(self.conn, family_id='family-a', child_id='child-primary6',
                    learning_date='2026-09-11', slot='core', scheduled_start='19:30', course=old_course,
                    created_by='student:student-a', now=1000)
        self.conn.execute("UPDATE tasks SET status='in_progress' WHERE id=?", (old['id'],))
        self.conn.raw.execute('CREATE TABLE learning_sessions (id,task_id,status,current_question_index)')
        self.insert('learning_sessions', dict(id='old-session',task_id=old['id'],status='in_progress',current_question_index=4))
        before = self.conn.execute('SELECT * FROM tasks WHERE id=?', (old['id'],)).fetchone()
        new = self.start()
        self.assertNotEqual(new['taskId'], old['id'])
        self.assertEqual(before, self.conn.execute('SELECT * FROM tasks WHERE id=?', (old['id'],)).fetchone())
        self.assertEqual(self.conn.execute('SELECT current_question_index FROM learning_sessions').fetchone()['current_question_index'], 4)
        self.assertEqual(self.conn.execute('SELECT learning_slot FROM tasks WHERE id=?', (new['taskId'],)).fetchone()['learning_slot'], 'catalog')
        daily = self.repo.get_today_tasks(self.conn, family_id='family-a',child_id='child-primary6',learning_date='2026-09-11')
        self.assertEqual([task['id'] for task in daily], [old['id']])

    def test_same_existing_daily_course_reuses_task(self):
        old, _ = self.repo.assign_today_task(self.conn, family_id='family-a',child_id='child-primary6',
            learning_date='2026-09-11',slot='core',scheduled_start='19:30',course=self.course,created_by='student:a',now=1000)
        result = self.start()
        self.assertEqual(result['taskId'], old['id'])
        self.assertFalse(result['created'])

    def assert_stopped_task_cannot_restart(self, task_id):
        for status in ('cancelled', 'rejected', 'expired'):
            with self.subTest(status=status):
                self.conn.execute('UPDATE tasks SET status=? WHERE id=?', (status,task_id))
                self.conn.raw.commit()
                before = self.conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
                statements_before = len(self.conn.statements)
                with self.assertRaises(ApiError) as failure:
                    self.start()
                self.assertEqual(failure.exception.code, 'learning_course_start_unavailable')
                self.assertEqual(self.conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone(), before)
                self.assertEqual(self.conn.execute('SELECT COUNT(*) AS n FROM tasks').fetchone()['n'], 1)
                self.assertFalse(any('INSERT INTO tasks' in sql for sql, _ in self.conn.statements[statements_before:]))

    def test_cancelled_catalog_unique_key_and_other_stopped_states_are_not_reused(self):
        result = self.start()
        self.assert_stopped_task_cannot_restart(result['taskId'])

    def test_stopped_daily_assignment_is_not_revived_as_catalog_task(self):
        task, _ = self.repo.assign_today_task(self.conn, family_id='family-a',child_id='child-primary6',
            learning_date='2026-09-11',slot='core',scheduled_start='19:30',course=self.course,created_by='student:a',now=1000)
        self.assert_stopped_task_cannot_restart(task['id'])

    def test_asset_withdrawal_rolls_back_new_follower_and_task(self):
        self.conn.assets_available = False
        with self.assertRaises(ApiError) as failure:
            self.start()
        self.assertEqual(failure.exception.code, 'learning_course_not_found')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) AS n FROM tasks').fetchone()['n'], 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) AS n FROM learning_curriculum_preparation_plans').fetchone()['n'], 1)

    def test_frozen_source_mismatch_is_rejected_before_task_creation(self):
        self.conn.execute("UPDATE learning_catalog_build_jobs SET target_spec_json='{}'")
        self.conn.raw.commit()
        with self.assertRaises(ApiError) as failure:
            self.start()
        self.assertEqual(failure.exception.code, 'learning_classroom_release_changed')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) AS n FROM tasks').fetchone()['n'], 0)

    def test_worker_cannot_claim_follower_even_if_its_time_is_made_due(self):
        self.start()
        follower = self.conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE child_id=?', (self.child['id'],)).fetchone()
        # Exercise the actual queue predicate against both NULL and due times.
        source = inspect.getsource(LearningCurriculumPreparationRepository.claim_next)
        self.assertIn('AND next_run_at <= ?', source)
        self.assertIn('library_owner.library_target_fingerprint =', source)
        self.assertIn('learning_curriculum_preparation_plans.target_fingerprint', source)
        sql = '''SELECT id FROM learning_curriculum_preparation_plans
          WHERE id=? AND status IN ('queued','running') AND next_run_at <= ?
            AND (library_target_fingerprint IS NOT NULL OR NOT EXISTS (
              SELECT 1 FROM learning_curriculum_preparation_plans AS library_owner
              WHERE library_owner.library_target_fingerprint = learning_curriculum_preparation_plans.target_fingerprint))'''
        for due in (None, 1):
            self.conn.execute('UPDATE learning_curriculum_preparation_plans SET next_run_at=? WHERE id=?', (due,follower['id']))
            self.assertIsNone(self.conn.execute(sql,(follower['id'],9_999_999_999_999)).fetchone())

    def test_history_and_carryover_keep_manual_and_existing_sessions_separate(self):
        history = inspect.getsource(StudentLearningLibraryRepository.list_library)
        self.assertIn("((session.id IS NOT NULL AND session.status <> 'completed') OR NOT EXISTS (", history)
        self.assertIn("COALESCE(task.learning_slot, 'core') <> 'catalog'", history)
        carryover = inspect.getsource(LearningRepository.list_carryover_candidates)
        self.assertIn("COALESCE(task.learning_slot, 'core') <> 'catalog'", carryover)

    def test_old_in_progress_remains_in_library_and_daily_carryover_after_manual_start(self):
        old_course = {**self.course, 'version': 'old-v1'}
        self.insert('learning_courses', old_course)
        self.conn.raw.execute('CREATE TABLE learning_sessions (id,family_id,child_id,task_id,status,current_question_index,correct_count,attempted_count,started_at,completed_at,updated_at)')
        self.conn.raw.execute('CREATE TABLE learning_reports (id,family_id,task_id,session_id,score,mastery_level,summary,next_step,created_at)')
        self.conn.raw.execute('CREATE TABLE task_events (task_id,event_type)')
        self.conn.raw.execute('CREATE TABLE learning_task_carryovers (source_task_id,target_date)')
        old, _ = self.repo.assign_today_task(self.conn, family_id='family-a',child_id='child-primary6',
            learning_date='2026-09-11',slot='core',scheduled_start='19:30',course=old_course,created_by='student:a',now=1000)
        self.insert('learning_sessions', dict(id='old-session',family_id='family-a',child_id='child-primary6',
            task_id=old['id'],status='in_progress',current_question_index=4,correct_count=3,attempted_count=4,
            started_at=1000,updated_at=1100))
        new = self.start()
        library = StudentLearningLibraryRepository(self.db)
        with patch('repositories.student_learning_library_repository._PACKAGE_CLASSROOM_AVAILABILITY_SQL', '1'), \
             patch('repositories.student_learning_library_repository._FULL_CLASSROOM_AVAILABILITY_SQL', '1'), \
             patch('repositories.student_learning_library_repository.with_parsed_runtime_manifests', side_effect=lambda sql: sql):
            items, _ = library.list_library(self.conn,family_id='family-a',child_id='child-primary6',
                bucket='all',subject=None,before_date='2026-09-12',cursor=None,limit=20)
            self.assertEqual({item['taskId'] for item in items}, {old['id'],new['taskId']})
            continuation = library.get_continue_item(self.conn,family_id='family-a',child_id='child-primary6')
            self.assertEqual(continuation['taskId'], old['id'])
        candidates = self.repo.list_carryover_candidates(self.conn,family_id='family-a',child_id='child-primary6',
            earliest_date='2026-09-10',target_date='2026-09-13')
        self.assertEqual([item['id'] for item in candidates], [old['id']])
        self.assertEqual(self.repo.count_learning_backlog(self.conn,family_id='family-a',child_id='child-primary6',
            before_date='2026-09-13'), 1)

    def test_route_preserves_identity_response_and_safe_errors(self):
        from routes.api.v2.student_learning import student_learning_bp
        app = Flask(__name__)
        app.register_blueprint(student_learning_bp, url_prefix='/api/v2/student/learning')
        client = app.test_client()
        response = {'ok': True, 'taskId': 'task-new', 'created': False,
                    'courseId': 'course-new', 'courseVersion': 'playful-v1'}
        with patch('routes.api.v2.student_learning.student_learning_service') as factory:
            factory.return_value.start_course.return_value = response
            result = client.post('/api/v2/student/learning/courses/course-new/versions/playful-v1/start',
                                 json={}, headers={'Authorization': 'Bearer student-token'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json, response)
            factory.return_value.start_course.assert_called_once_with('student-token', 'course-new', 'playful-v1')
            factory.return_value.start_course.side_effect = ApiError('learning_course_not_found', '课程不存在', 404)
            rejected = client.post('/api/v2/student/learning/courses/course-new/versions/playful-v1/start',
                                   json={}, headers={'Authorization': 'Bearer student-token'})
            self.assertEqual(rejected.status_code, 404)


if __name__ == '__main__':
    unittest.main()
