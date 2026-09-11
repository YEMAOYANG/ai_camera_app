from __future__ import annotations

import copy
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from repositories.course_supply_inventory import inherited_scope_requests, published_supply
from repositories.course_supply_repository import requested_supply
from services import course_library_service as supply
from services.learning_curriculum_preparation_contract import build_preparation_target


DATABASE = 'mysql+pymysql://unused:unused@127.0.0.1/ai_camera_app_test'


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class RecordedConnection:
    def __init__(self, *results):
        self.results = iter(results)
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        return Rows(next(self.results))


class ConnectionDatabase:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def transaction(self):
        yield self.conn


def pending_slot(subject='chinese', skill='pinyin_syllables', variant=1):
    return {'subject': subject, 'skill_id': skill, 'variant_ordinal': variant,
            'priority': 0, 'purpose': 'canary', 'ready': False,
            'reason_code': None, 'runtime_status': None, 'publication_status': None}


def available_slot(fingerprint='historical', course='shared-course'):
    return {'course_id': course, 'course_version': '1', 'published_at': 1000,
            'build_item_id': 'published-item', 'target_fingerprint': fingerprint}


class CourseSupplyAvailabilityTest(unittest.TestCase):
    def setUp(self):
        supply._status_cache.clear()

    def tearDown(self):
        supply._status_cache.clear()

    def test_unregistered_grade_is_not_advertised_as_primary_one(self):
        with self.assertRaises(supply.CourseLibraryNotOpen):
            supply.CourseLibraryService(DATABASE, grade_code='primary_7')
        with patch.object(supply.CourseLibraryService, 'status') as status:
            result = supply.cached_supply_summary(DATABASE, grade_code='primary_7')
        self.assertEqual(result['availabilityStatus'], 'not_open')
        self.assertEqual(result['gradeCode'], 'primary_7')
        self.assertIsNone(result['targetFingerprint'])
        status.assert_not_called()

    def test_a_target_for_another_grade_is_rejected_before_database_access(self):
        with patch.object(supply, 'build_preparation_target', return_value=build_preparation_target('primary_1')):
            with self.assertRaises(supply.CourseLibraryNotOpen):
                supply.CourseLibraryService(DATABASE, grade_code='primary_2')

    def test_grade_and_policy_fingerprint_both_partition_cached_status(self):
        base = build_preparation_target('primary_1')
        revision = [1]

        def target(grade):
            result = copy.deepcopy(base)
            result['gradeCode'] = grade
            result['testPolicyRevision'] = revision[0]
            return result

        def status(library):
            ready = 1 if library.target['gradeCode'] == 'primary_2' else 3
            return {'planId': 'owner', 'version': library.fingerprint, 'requestedCount': 3,
                    'readyCount': ready, 'blocked': False, 'stalled': False,
                    'lastProgressAt': 1000}

        with patch.object(supply, 'build_preparation_target', side_effect=target), \
                patch.object(supply.CourseLibraryService, 'status', autospec=True, side_effect=status) as query:
            two = supply.cached_supply_summary(DATABASE, grade_code='primary_2')
            six = supply.cached_supply_summary(DATABASE, grade_code='primary_6')
            self.assertEqual(two['readyCount'], 1)
            self.assertEqual(six['readyCount'], 3)
            self.assertNotEqual(two['targetFingerprint'], six['targetFingerprint'])
            self.assertEqual(two, supply.cached_supply_summary(DATABASE, grade_code='primary_2'))
            self.assertEqual(query.call_count, 2)
            revision[0] = 2
            upgraded = supply.cached_supply_summary(DATABASE, grade_code='primary_2')
            self.assertNotEqual(upgraded['targetFingerprint'], two['targetFingerprint'])
            self.assertEqual(query.call_count, 3)

    def test_compatible_published_course_satisfies_new_target_without_editing_input(self):
        source = pending_slot()
        inventory = {('chinese', 'pinyin_syllables', 1): available_slot()}
        result = supply.apply_published_inventory([source], inventory, 'new-policy')[0]
        self.assertTrue(result['ready'])
        self.assertTrue(result['reused'])
        self.assertEqual(result['source_target_fingerprint'], 'historical')
        self.assertEqual(result['course_id'], 'shared-course')
        self.assertFalse(source['ready'])

    def test_withdrawal_removes_readiness_and_preserves_published_audit(self):
        slot = {**pending_slot(), 'ready': True, 'publication_status': 'published'}
        result = supply.apply_published_inventory([slot], {}, 'current')[0]
        self.assertFalse(result['ready'])
        self.assertEqual(result['reason_code'], 'published_course_unavailable')
        self.assertEqual(result['publication_status'], 'published')

    def test_inventory_of_another_skill_never_satisfies_requested_slot(self):
        rows = supply.apply_published_inventory([pending_slot()],
            {('math', 'pinyin_syllables', 1): available_slot()}, 'current')
        self.assertFalse(rows[0]['ready'])

    def test_complete_scope_is_ready_while_underlying_long_build_remains_running(self):
        library = supply.CourseLibraryService(DATABASE, clock=lambda: 50000)
        row = pending_slot()
        library.database = ConnectionDatabase(RecordedConnection(
            [{'id': 'owner', 'status': 'running', 'stage': 'generating_content', 'updated_at': 40000}],
            [row], [{'status': 'open', 'reason_code': 'quota_exhausted'}],
        ))
        with patch.object(supply, 'published_supply', return_value={
                ('chinese', 'pinyin_syllables', 1): available_slot()}):
            status = library.status()
        self.assertEqual((status['state'], status['stage']), ('ready', 'completed'))
        self.assertEqual(status['productionState'], 'running')
        self.assertTrue(status['scopeReady'])
        self.assertFalse(status['blocked'])
        self.assertIsNone(status['waitReason'])
        self.assertEqual(status['availabilityStatus'], 'ready')

    def test_completed_scope_does_not_claim_that_child_finished_it(self):
        status = {'planId': 'owner', 'version': 'v', 'requestedCount': 3, 'readyCount': 3,
                  'blocked': True, 'stalled': True, 'waitReason': 'quota_exhausted',
                  'lastProgressAt': 1000}
        with patch.object(supply.CourseLibraryService, 'status', return_value=status):
            result = supply.cached_supply_summary(DATABASE, grade_code='primary_1')
        self.assertEqual(result['availabilityStatus'], 'ready')
        self.assertTrue(result['scopeReady'])
        self.assertFalse(result['paused'])
        self.assertFalse(result['delayed'])
        self.assertEqual(result['missingCount'], 0)
        self.assertNotIn('准备中', result['message'])

    def test_policy_upgrade_reads_existing_scope_without_creating_new_owner(self):
        library = supply.CourseLibraryService(DATABASE, clock=lambda: 50000)
        connection = RecordedConnection([], [], [])
        library.database = ConnectionDatabase(connection)
        inherited = {**pending_slot(), 'source_plan_id': 'old-owner'}
        with patch.object(supply, 'inherited_scope_requests', return_value=[inherited]), \
                patch.object(supply, 'published_supply', return_value={
                    ('chinese', 'pinyin_syllables', 1): available_slot()}):
            status = library.status()
        self.assertTrue(status['inheritedScope'])
        self.assertTrue(status['scopeReady'])
        self.assertIsNone(status['planId'])
        self.assertTrue(all(sql.lstrip().startswith('SELECT') for sql, _ in connection.calls))
        with patch.object(supply.CourseLibraryService, 'status', return_value=status):
            self.assertEqual(supply.cached_supply_summary(DATABASE, grade_code='primary_1')['readyCount'], 1)

    def test_existing_owner_with_empty_scope_does_not_reenable_old_requests(self):
        library = supply.CourseLibraryService(DATABASE)
        library.database = ConnectionDatabase(RecordedConnection([{'id': 'owner'}], [], []))
        with patch.object(supply, 'inherited_scope_requests') as inherit, \
                patch.object(supply, 'published_supply', return_value={}):
            status = library.status()
        inherit.assert_not_called()
        self.assertEqual(status['availabilityStatus'], 'empty')
        self.assertFalse(status['scopeReady'])

    def test_ready_legacy_slot_is_excluded_from_new_paid_content_claim(self):
        target = build_preparation_target('primary_1')
        row = pending_slot()
        conn = RecordedConnection([{'id': 'owner'}], [row])
        with patch('repositories.course_supply_repository.published_supply', return_value={
                ('chinese', 'pinyin_syllables', 1): available_slot()}):
            self.assertEqual(requested_supply(conn, {'target_spec_json': target}), {})
        self.assertIn('grade_code = ?', conn.calls[0][0])
        self.assertEqual(conn.calls[0][1][-1], 'primary_1')

    def test_pending_gap_reappears_after_media_is_withdrawn(self):
        row = pending_slot()
        with patch('repositories.course_supply_repository.published_supply', return_value={}):
            requested = requested_supply(RecordedConnection([{'id': 'owner'}], [row]),
                                         {'target_spec_json': build_preparation_target('primary_1')})
        self.assertEqual(requested, {('chinese', 'pinyin_syllables', 1): 0})

    def test_inherited_scope_uses_one_latest_owner_not_union_of_old_wider_scopes(self):
        conn = RecordedConnection([
            {**pending_slot(), 'source_plan_id': 'latest-canary'},
            {**pending_slot(variant=2), 'source_plan_id': 'old-catalog'},
        ])
        result = inherited_scope_requests(conn, build_preparation_target('primary_1'))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source_plan_id'], 'latest-canary')

    def test_latest_disabled_scope_does_not_reveal_an_older_enabled_scope(self):
        conn = RecordedConnection([
            {**pending_slot(), 'source_plan_id': 'latest-disabled', 'enabled': False},
            {**pending_slot(variant=2), 'source_plan_id': 'older-wide', 'enabled': True},
        ])
        self.assertEqual(inherited_scope_requests(conn, build_preparation_target('primary_1')), [])
        self.assertIn('LEFT JOIN learning_course_supply_requests', conn.calls[0][0])
        self.assertNotIn('request.enabled = TRUE', conn.calls[0][0])

    def test_automatic_policy_upgrade_inherits_narrow_or_disabled_scope(self):
        for enabled, expected in ((True, 1), (False, 0)):
            with self.subTest(enabled=enabled):
                conn = RecordedConnection(
                    [{'id': 'current-owner'}], [],
                    [{**pending_slot(), 'source_plan_id': 'latest-scope', 'enabled': enabled},
                     {**pending_slot(variant=2), 'source_plan_id': 'older-wide', 'enabled': True}],
                    [], [], [],
                )
                library = supply.CourseLibraryService(DATABASE, clock=lambda: 1000)
                library.database = ConnectionDatabase(conn)
                library.database.database_url = DATABASE
                with patch.object(library, 'ensure_owner', return_value={'id': 'current-owner'}):
                    result = library.request_scope('catalog', preserve_existing_scope=True)
                self.assertEqual(result['requestedCount'], expected)
                self.assertEqual(sum('INSERT INTO learning_course_supply_requests' in sql for sql, _ in conn.calls), expected)

    def test_inventory_query_requires_live_media_and_exact_grade_target_pairs(self):
        conn = RecordedConnection([])
        target = build_preparation_target('primary_1')
        self.assertEqual(published_supply(conn, target), {})
        sql, params = conn.calls[0]
        self.assertEqual(params[0], target['gradeCode'])
        self.assertIn('build.target_spec_json = ?', sql)
        self.assertIn('receipt.target_fingerprint = ?', sql)
        for gate in ("course.retired_at IS NULL", "package.retired_at IS NULL",
                     "runtime.retired_at IS NULL", "audio.state = 'auto_validated'",
                     "asset.status <> 'ready'", "asset.scan_status <> 'passed'",
                     "asset_review.status <> 'approved'", "asset_variant.status = 'ready'"):
            self.assertIn(gate, sql)


if __name__ == '__main__':
    unittest.main()
