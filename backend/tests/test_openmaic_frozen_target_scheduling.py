from __future__ import annotations
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
import unittest
from integrations.openmaic_formal_media import compatible_preparation_targets
from repositories.learning_curriculum_preparation_repository import LearningCurriculumPreparationRepository
from repositories.lesson_package_repository import LessonPackageRepository
from services.learning_curriculum_preparation_contract import (
    build_preparation_target, compatible_preparation_scope_sql, preparation_target_fingerprint,
)


def encoded(target):
    return json.dumps(target, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Selected(Exception):
    def __init__(self, row):
        self.row = row


class MemoryConnection:
    def __init__(self, *, stop_after_select=False):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.stop_after_select = stop_after_select
        self.db.execute('''CREATE TABLE learning_curriculum_preparation_plans (
            id TEXT, grade_code TEXT, target_spec_json TEXT, target_fingerprint TEXT,
            status TEXT, stage TEXT, resume_stage TEXT, next_run_at INT, created_at INT,
            lease_token TEXT, lease_expires_at INT, progress_percent INT, hard_deadline_at INT,
            work_unit_kind TEXT, superseded_at INT)''')

    def add(self, target, *, id="plan", fingerprint=None, **values):
        row = dict(id=id, grade_code=target["gradeCode"], target_spec_json=encoded(target),
                   target_fingerprint=fingerprint or preparation_target_fingerprint(target),
                   status="queued", stage="planning", next_run_at=1, created_at=1)
        row.update(values)
        self.db.execute("INSERT INTO learning_curriculum_preparation_plans (" + ",".join(row) + ") VALUES (" + ",".join("?" for _ in row) + ")", tuple(row.values()))

    def execute(self, sql, params=()):
        cursor = self.db.execute(sql.replace(" FOR UPDATE SKIP LOCKED", ""), params)
        if self.stop_after_select:
            raise Selected(cursor.fetchone())
        return cursor


class CaptureConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        return SimpleNamespace(fetchone=lambda: None)


class OpenMaicFrozenTargetSchedulingTest(unittest.TestCase):
    def setUp(self):
        self.current = build_preparation_target("primary_1")
        self.targets = compatible_preparation_targets(self.current)
        self.automatic_targets = (self.targets[0], self.targets[3], self.targets[4])
        self.fingerprint = preparation_target_fingerprint(self.current)
        self.repository = LearningCurriculumPreparationRepository(None)

    def test_five_exact_contracts_have_independent_copies_and_original_hashes(self):
        self.assertEqual(len(self.targets), 5)
        self.assertEqual(len({preparation_target_fingerprint(t) for t in self.targets}), 5)
        self.assertEqual([preparation_target_fingerprint(t) for t in self.targets[1:]], [
            "174a787e2ddbb8dd9c50e859a829bd2fe08fec71838448a8c5e5b0d2246766f1",
            "48cceefd0543abe9e3bfcf2f8d640ef21b8e03503cfa3dc6ef89a0428bcef2df",
            "7d4c0980789621cffb338e14b39c7dbc7b0d34c40013be0725c0076dad3b90a3",
            "c8fb538cb53fe365f86d0fd62bb9f270c9a2c17a39d5b0b8ce425cf7e0051f4a",
        ])
        self.targets[1]["formalRuntimePolicy"]["professionalCreationPolicy"]["mode"] = "changed"
        self.assertEqual(self.current["formalRuntimePolicy"]["professionalCreationPolicy"]["mode"], "professional_skill")
        self.assertEqual(len(compatible_preparation_targets(self.current)), 5)

    def claim_selection(self, conn, *, fingerprint=None):
        with self.assertRaises(Selected) as selected:
            self.repository.claim_next(conn, now=100, lease_ms=1000, supported_stages=("planning",),
                                       grade_code="primary_1", target_fingerprint=fingerprint or self.fingerprint)
        return selected.exception.row

    def test_actual_claim_selects_new_and_previous_production_without_rewriting_identity(self):
        for target in self.automatic_targets:
            with self.subTest(policy=target["formalRuntimePolicy"]["professionalCreationPolicy"]):
                conn = MemoryConnection(stop_after_select=True)
                conn.add(target)
                row = self.claim_selection(conn)
                self.assertEqual(row["target_spec_json"], encoded(target))
                self.assertEqual(row["target_fingerprint"], preparation_target_fingerprint(target))

    def test_dormant_contracts_require_explicit_recovery_scope(self):
        for target in self.targets[1:3]:
            conn = MemoryConnection(stop_after_select=True)
            conn.add(target)
            self.assertIsNone(self.claim_selection(conn))
            row = self.claim_selection(conn, fingerprint=preparation_target_fingerprint(target))
            self.assertEqual(row["target_spec_json"], encoded(target))

    def test_actual_claim_rejects_wrong_hash_unknown_contract_and_other_grade(self):
        changed = deepcopy(self.current); changed["curriculumVersion"] = "unknown"
        unknown = deepcopy(self.current); unknown["formalRuntimePolicy"]["professionalCreationPolicy"]["mode"] = "unknown"
        for target, fingerprint in ((self.targets[1], self.fingerprint), (changed, None), (unknown, None),
                                    (build_preparation_target("primary_2"), None)):
            with self.subTest(target=target["gradeCode"], fingerprint=fingerprint):
                conn = MemoryConnection(stop_after_select=True); conn.add(target, fingerprint=fingerprint)
                self.assertIsNone(self.claim_selection(conn))

    def test_actual_claim_preserves_oldest_priority_and_terminal_lease_gates(self):
        conn = MemoryConnection(stop_after_select=True)
        conn.add(self.current, id="new", created_at=2)
        conn.add(self.targets[3], id="old", created_at=1)
        conn.add(self.targets[2], id="failed", status="failed", created_at=0)
        conn.add(self.targets[3], id="leased", status="running", lease_expires_at=101, created_at=0)
        self.assertEqual(self.claim_selection(conn)["id"], "old")
        conn.db.execute("DELETE FROM learning_curriculum_preparation_plans WHERE id IN ('new','old')")
        self.assertIsNone(self.claim_selection(conn))

    def test_runner_status_counts_automatic_three_but_not_dormant_terminal_or_unknown_plans(self):
        conn = MemoryConnection()
        for i, target in enumerate(self.targets):
            conn.add(target, id=str(i), status="running")
        conn.add(self.targets[1], id="failed", status="failed")
        conn.add(self.targets[1], id="wrong-hash", fingerprint="9" * 64)
        counts = self.repository.count_runner_scope(conn, now=100, supported_stages=("planning",),
                                                    grade_code="primary_1", target_fingerprint=self.fingerprint)
        self.assertEqual(counts, dict(claimablePlanCount=3, runningPlanCount=3, expiredLeaseCount=0))

    def test_start_formal_pipeline_passes_the_selected_old_plan_fingerprint(self):
        conn = MemoryConnection()
        conn.add(self.targets[3], stage="building_classrooms", status="running", progress_percent=35,
                 next_run_at=None, hard_deadline_at=None)
        calls = []
        self.repository.start_formal_pipeline = lambda _conn, **kwargs: calls.append(kwargs) or True
        result = self.repository.start_next_formal_pipeline(conn, grade_code="primary_1",
                        target_fingerprint=self.fingerprint, now=100)
        self.assertEqual(result, "plan")
        self.assertEqual(calls[0]["target_fingerprint"], preparation_target_fingerprint(self.targets[3]))

    def test_explicit_old_scope_and_unscoped_api_are_unchanged(self):
        old_hash = preparation_target_fingerprint(self.targets[1])
        self.assertEqual(self.repository._runner_target_scope("primary_1", old_hash),
                         (" AND grade_code = ? AND target_fingerprint = ?", ("primary_1", old_hash)))
        self.assertEqual(self.repository._runner_target_scope(None, None), ("", ()))
        for grade, digest in ((None, self.fingerprint), ("primary_1", None), ("primary_1", "invalid")):
            with self.assertRaises(ValueError): self.repository._runner_target_scope(grade, digest)

    def test_scope_rejects_unsafe_column_names(self):
        for column in ("plan.id OR true", "a.b.c", "x;SELECT", "", None):
            with self.assertRaises(ValueError):
                compatible_preparation_scope_sql(self.current, target_column=column, fingerprint_column="plan.target_fingerprint")

    def test_candidate_selection_keeps_all_original_failure_and_ambiguity_gates(self):
        conn = CaptureConnection()
        self.assertIsNone(LessonPackageRepository(None).get_next_formal_candidate_authority(conn))
        sql, params = conn.calls[0]
        self.assertEqual(sql.count("?"), len(params))
        self.assertEqual(len(params), 6)
        self.assertEqual(tuple(params[::2]), tuple(encoded(t) for t in self.automatic_targets))
        self.assertEqual(tuple(params[1::2]), tuple(preparation_target_fingerprint(t) for t in self.automatic_targets))
        for gate in ("plan.status = 'running'", "plan.superseded_at IS NULL", "plan.completed_at IS NULL",
                     "blocked.quality_status = 'quarantined'", "blocked.error_code LIKE '%%ambiguous%%'",
                     "recovery.status IN ('reserving', 'running', 'succeeded')", "ORDER BY plan.created_at, plan.id"):
            self.assertIn(gate, sql)

    def reserve_to_lock(self, target, *, fingerprint=None):
        conn = CaptureConnection()
        authority = dict(build_item_id="item", preparation_plan_id="plan", course_id="course", course_version="1",
                         target_spec_json=encoded(target))
        with self.assertRaises(ValueError) as error:
            LessonPackageRepository(None).reserve_formal_runtime_package(conn, authority=authority,
                package_id="package", target_fingerprint=fingerprint or preparation_target_fingerprint(target),
                public_payload={}, private_payload={}, public_hash="a"*64, private_hash="b"*64,
                validation_report={}, now=100)
        return conn.calls, str(error.exception)

    def test_reservation_locks_each_exact_old_target_and_original_hash(self):
        for target in self.targets:
            calls, error = self.reserve_to_lock(target)
            self.assertEqual(error, "formal package authority is not content-ready")
            sql, params = calls[0]
            self.assertEqual(sql.count("?"), len(params))
            self.assertEqual(params[-2:], (preparation_target_fingerprint(target), encoded(target)))
            self.assertIn("plan.target_spec_json = build.target_spec_json", sql)

    def test_reservation_rejects_wrong_hash_or_changed_contract_before_lock(self):
        changed = deepcopy(self.targets[1]); changed["curriculumVersion"] = "unknown"
        for target, digest in ((self.targets[1], self.fingerprint), (changed, None)):
            calls, error = self.reserve_to_lock(target, fingerprint=digest)
            self.assertEqual(calls, [])
            self.assertEqual(error, "formal package target contract is stale")

    def test_undispatched_renewal_select_scope_preserves_provider_dependency_gates(self):
        conn = CaptureConnection()
        self.repository.content_provider_dependency_auditor = object()
        self.assertFalse(self.repository.renew_undispatched_content_budget(conn, grade_code="primary_1",
            target_fingerprint=self.fingerprint, now=100, required_budget_ms=1000))
        sql, params = conn.calls[0]
        self.assertEqual(sql.count("?"), len(params))
        self.assertEqual(len(params), 8)
        for gate in ("status = 'queued'", "stage = 'retry_wait'", "work_unit_kind = 'provider_phase'",
                     "lease_token IS NULL", "superseded_at IS NULL"):
            self.assertIn(gate, sql)


if __name__ == "__main__":
    unittest.main()
