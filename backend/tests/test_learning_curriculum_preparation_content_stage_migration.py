from __future__ import annotations

import json
from pathlib import Path
import unittest

import pymysql

from core.database import Database
from repositories.learning_catalog_repository import (
    LearningCatalogBuildConflict,
    LearningCatalogRepository,
)
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from scripts.migrate import run_migrations
from services.learning_curriculum_preparation_contract import (
    TARGET_SCHEMA_V1,
    TARGET_SCHEMA_V2,
    build_preparation_target,
    preparation_target_fingerprint,
)
from tests.support import fresh_test_config


MIGRATION_VERSION = "056_learning_curriculum_preparation_content_stage.sql"
LEGACY_STATE_MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / (
    "055_learning_curriculum_preparation_runner_evidence.sql"
)

PLAN_COLUMNS = (
    "content_target_count",
    "content_candidate_count",
    "content_failed_count",
    "content_canary_target_count",
    "content_canary_candidate_count",
    "content_canary_failed_count",
    "content_canary_passed_at",
    "content_generation_completed_at",
    "retry_reason_code",
    "retry_message_safe",
    "work_unit_kind",
    "bound_catalog_item_id",
    "bound_content_attempt_ordinal",
    "bound_content_phase",
    "stage_progress_json",
)
BUILD_COLUMNS = (
    "execution_mode",
    "content_manifest_version",
    "canary_manifest_json",
    "stage_ceiling",
)
ITEM_COLUMNS = (
    "execution_mode_snapshot",
    "content_manifest_version_snapshot",
    "subject_ordinal",
    "boundary_ordinal",
    "content_phase",
    "content_gate_status",
    "content_gate_attempt_count",
    "content_gate_passed_at",
    "content_validation_contract_version",
    "content_receipt_hash",
    "content_lease_token",
    "content_lease_expires_at",
    "content_heartbeat_at",
    "content_attempt_started_at",
    "content_provider_attempt_hard_deadline_at",
    "content_work_unit_deadline_at",
    "content_claim_attempt_ordinal",
)


class LearningCurriculumPreparationContentStageMigrationTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)
        self.plan_repository = LearningCurriculumPreparationRepository(self.database)
        self.catalog_repository = LearningCatalogRepository(self.database)

    def test_056_two_real_replays_have_one_marker_and_exact_schema(self):
        self._require_migration()

        for _ in range(2):
            with self.database.transaction() as conn:
                conn.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (MIGRATION_VERSION,),
                )
            run_migrations(self.database_url, verbose=False)

        with self.database.transaction() as conn:
            marker = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            ).fetchone()
            plan_columns = self._column_names(
                conn, "learning_curriculum_preparation_plans"
            )
            build_columns = self._column_names(conn, "learning_catalog_build_jobs")
            item_columns = self._column_names(conn, "learning_catalog_build_items")
            dispatch_columns = self._column_names(
                conn, "learning_course_provider_dispatches"
            )
            old_check = self._constraint_count(
                conn,
                "learning_curriculum_preparation_plans",
                "chk_learning_prep_state_evidence",
            )
            new_check = self._constraint_count(
                conn,
                "learning_curriculum_preparation_plans",
                "chk_learning_prep_content_state_evidence",
            )
            dispatch_unique = self._unique_index_columns(
                conn, "learning_course_provider_dispatches"
            )
            residue = {
                table: int(
                    conn.execute(f"SELECT COUNT(*) AS count FROM {table}")
                    .fetchone()["count"]
                )
                for table in (
                    "learning_curriculum_preparation_plans",
                    "learning_catalog_build_jobs",
                    "learning_catalog_build_items",
                    "learning_course_provider_dispatches",
                )
            }

        self.assertEqual(marker["count"], 1)
        self.assertTrue(set(PLAN_COLUMNS).issubset(plan_columns))
        self.assertTrue(set(BUILD_COLUMNS).issubset(build_columns))
        self.assertTrue(set(ITEM_COLUMNS).issubset(item_columns))
        self.assertTrue(
            {
                "id",
                "build_item_id",
                "logical_attempt",
                "phase",
                "phase_ordinal",
                "generation_request_id",
                "item_lease_token",
                "provider",
                "model",
                "profile",
                "input_sha256",
                "status",
                "checkpoint_json",
                "output_sha256",
                "attempt_started_at",
                "attempt_hard_deadline_at",
                "provider_request_id_hash",
                "input_tokens",
                "output_tokens",
                "billing_evidence",
                "safe_error_code",
                "dispatched_at",
                "completed_at",
            }.issubset(dispatch_columns)
        )
        self.assertEqual(old_check, 0)
        self.assertEqual(new_check, 1)
        self.assertEqual(
            dispatch_unique["uq_learning_provider_dispatch_phase"],
            ("build_item_id", "logical_attempt", "phase"),
        )
        self.assertEqual(
            dispatch_unique["uq_learning_provider_dispatch_ordinal"],
            ("build_item_id", "logical_attempt", "phase_ordinal"),
        )
        self.assertEqual(
            residue,
            {
                "learning_curriculum_preparation_plans": 0,
                "learning_catalog_build_jobs": 0,
                "learning_catalog_build_items": 0,
                "learning_course_provider_dispatches": 0,
            },
        )

    def test_marker_rejects_same_name_wrong_dispatch_contract(self):
        corruptions = {
            "phase_unique_wrong_columns": (
                "ALTER TABLE learning_course_provider_dispatches "
                "DROP INDEX uq_learning_provider_dispatch_phase",
                "CREATE UNIQUE INDEX uq_learning_provider_dispatch_phase "
                "ON learning_course_provider_dispatches("
                "build_item_id, logical_attempt, model)",
            ),
            "ordinal_index_is_not_unique": (
                "ALTER TABLE learning_course_provider_dispatches "
                "DROP INDEX uq_learning_provider_dispatch_ordinal",
                "CREATE INDEX uq_learning_provider_dispatch_ordinal "
                "ON learning_course_provider_dispatches("
                "build_item_id, logical_attempt, phase_ordinal)",
            ),
            "attempt_check_wrong_clause": (
                "ALTER TABLE learning_course_provider_dispatches "
                "DROP CHECK chk_learning_provider_dispatch_attempt",
                "ALTER TABLE learning_course_provider_dispatches ADD CONSTRAINT "
                "chk_learning_provider_dispatch_attempt "
                "CHECK (logical_attempt >= 1)",
            ),
            "phase_check_wrong_clause": (
                "ALTER TABLE learning_course_provider_dispatches "
                "DROP CHECK chk_learning_provider_dispatch_phase",
                "ALTER TABLE learning_course_provider_dispatches ADD CONSTRAINT "
                "chk_learning_provider_dispatch_phase "
                "CHECK (phase_ordinal BETWEEN 1 AND 14)",
            ),
            "evidence_check_wrong_clause": (
                "ALTER TABLE learning_course_provider_dispatches "
                "DROP CHECK chk_learning_provider_dispatch_evidence",
                "ALTER TABLE learning_course_provider_dispatches ADD CONSTRAINT "
                "chk_learning_provider_dispatch_evidence "
                "CHECK (status IN ('dispatched', 'succeeded', 'failed_safe', "
                "'ambiguous'))",
            ),
            "foreign_key_wrong_target": (
                "ALTER TABLE learning_course_provider_dispatches "
                "DROP FOREIGN KEY fk_learning_provider_dispatch_item",
                "ALTER TABLE learning_course_provider_dispatches ADD CONSTRAINT "
                "fk_learning_provider_dispatch_item FOREIGN KEY (build_item_id) "
                "REFERENCES learning_catalog_build_jobs(id)",
            ),
            "critical_identity_column_nullable": (
                "ALTER TABLE learning_course_provider_dispatches "
                "MODIFY COLUMN profile VARCHAR(128) NULL",
            ),
        }
        observed = {}
        for label, statements in corruptions.items():
            config = fresh_test_config()
            database_url = config["DATABASE_URL"]
            self.assertIn("/ai_camera_app_test", database_url)
            self.assertNotIn("/ai_camera_app_dev", database_url)
            database = Database(database_url)
            with database.transaction() as conn:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (MIGRATION_VERSION,),
                )

            migration_error = None
            try:
                run_migrations(database_url, verbose=False)
            except pymysql.MySQLError as error:
                migration_error = int(error.args[0])
            with database.transaction() as conn:
                marker = int(
                    conn.execute(
                        "SELECT COUNT(*) AS count FROM schema_migrations "
                        "WHERE version = ?",
                        (MIGRATION_VERSION,),
                    ).fetchone()["count"]
                )
            observed[label] = (migration_error is not None, marker)

        self.assertEqual(
            observed,
            {label: (True, 0) for label in corruptions},
        )

    def test_marker_rejects_weak_task2_checks_and_composite_primary(self):
        corruptions = {
            "plan_state_check_wrong_clause": (
                "ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT "
                "chk_learning_prep_content_state_evidence "
                "CHECK (status IN ('queued', 'running', 'ready', 'failed', "
                "'superseded'))",
            ),
            "plan_counts_check_wrong_clause": (
                "ALTER TABLE learning_curriculum_preparation_plans "
                "DROP CHECK chk_learning_prep_content_counts",
                "ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT "
                "chk_learning_prep_content_counts CHECK (content_target_count >= 0)",
            ),
            "plan_progress_check_wrong_clause": (
                "ALTER TABLE learning_curriculum_preparation_plans "
                "DROP CHECK chk_learning_prep_stage_progress_json",
                "ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT "
                "chk_learning_prep_stage_progress_json "
                "CHECK (JSON_VALID(stage_progress_json) = 1)",
            ),
            "build_check_wrong_clause": (
                "ALTER TABLE learning_catalog_build_jobs "
                "DROP CHECK chk_learning_catalog_build_content_mode",
                "ALTER TABLE learning_catalog_build_jobs ADD CONSTRAINT "
                "chk_learning_catalog_build_content_mode "
                "CHECK (execution_mode IN ('full_pipeline', 'content_only'))",
            ),
            "item_check_wrong_clause": (
                "ALTER TABLE learning_catalog_build_items "
                "DROP CHECK chk_learning_catalog_item_content_state",
                "ALTER TABLE learning_catalog_build_items ADD CONSTRAINT "
                "chk_learning_catalog_item_content_state "
                "CHECK (execution_mode_snapshot IN ('full_pipeline', 'content_only'))",
            ),
            "plan_retry_code_wrong_length": (
                "ALTER TABLE learning_curriculum_preparation_plans "
                "MODIFY COLUMN retry_reason_code VARCHAR(64) NULL",
            ),
            "build_manifest_version_wrong_length": (
                "ALTER TABLE learning_catalog_build_jobs MODIFY COLUMN "
                "content_manifest_version VARCHAR(64) NULL",
            ),
            "item_lease_token_wrong_length": (
                "ALTER TABLE learning_catalog_build_items MODIFY COLUMN "
                "content_lease_token VARCHAR(64) NULL",
            ),
            "dispatch_composite_primary": (
                "ALTER TABLE learning_course_provider_dispatches DROP PRIMARY KEY",
                "ALTER TABLE learning_course_provider_dispatches "
                "ADD PRIMARY KEY (id, build_item_id)",
            ),
        }
        observed = {}
        for label, statements in corruptions.items():
            config = fresh_test_config()
            database_url = config["DATABASE_URL"]
            self.assertIn("/ai_camera_app_test", database_url)
            self.assertNotIn("/ai_camera_app_dev", database_url)
            database = Database(database_url)
            with database.transaction() as conn:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (MIGRATION_VERSION,),
                )

            migration_error = None
            try:
                run_migrations(database_url, verbose=False)
            except pymysql.MySQLError:
                migration_error = True
            with database.transaction() as conn:
                marker = int(
                    conn.execute(
                        "SELECT COUNT(*) AS count FROM schema_migrations "
                        "WHERE version = ?",
                        (MIGRATION_VERSION,),
                    ).fetchone()["count"]
                )
            observed[label] = (migration_error is not None, marker)

        self.assertEqual(
            observed,
            {label: (True, 0) for label in corruptions},
        )

    def test_restart_after_partial_ddl_repairs_half_state_and_partial_table(self):
        self._require_migration()
        target = build_preparation_target("primary_2")
        fingerprint = preparation_target_fingerprint(target)
        with self.database.transaction() as conn:
            self._insert_family_child(conn, "partial-family", "partial-child")
            plan, _ = self.plan_repository.reserve_plan(
                conn,
                family_id="partial-family",
                child_id="partial-child",
                grade_code="primary_2",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=target,
                target_fingerprint=fingerprint,
                request_id="partial-plan",
                shared_build_request_id=f"grade-build:{fingerprint}",
                now=1000,
            )
            conn.execute(
                "ALTER TABLE learning_curriculum_preparation_plans "
                "DROP CHECK chk_learning_prep_formal_state_evidence"
            )
            conn.execute(
                "UPDATE learning_curriculum_preparation_plans "
                "SET status = 'running', stage = 'queued', lease_token = 'legacy', "
                "lease_expires_at = 2000, heartbeat_at = 1000, "
                "hard_deadline_at = 3000 WHERE id = ?",
                (plan["id"],),
            )
            conn.execute(
                "ALTER TABLE learning_curriculum_preparation_plans "
                "DROP COLUMN retry_message_safe"
            )
            conn.execute("DROP TABLE learning_course_provider_dispatches")
            conn.execute(
                "CREATE TABLE learning_course_provider_dispatches("
                "id VARCHAR(128) PRIMARY KEY)"
            )
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            )

        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)

        with self.database.transaction() as conn:
            repaired = self.plan_repository.get_plan(conn, plan["id"])
            dispatch_columns = self._column_names(
                conn, "learning_course_provider_dispatches"
            )
            marker = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            ).fetchone()
        self.assertEqual(repaired["status"], "running")
        self.assertEqual(repaired["stage"], "planning")
        self.assertEqual(repaired["lease_token"], "legacy")
        self.assertIn("retry_message_safe", repaired)
        self.assertIn("completed_at", dispatch_columns)
        self.assertEqual(marker["count"], 1)

    def test_legacy_054_055_rows_backfill_without_mutating_registered_migrations(self):
        self._require_migration()
        legacy = self._restore_055_schema_and_insert_legacy_rows()

        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)

        with self.database.transaction() as conn:
            running = self.plan_repository.get_plan(conn, legacy["running_plan_id"])
            planning_retry = self.plan_repository.get_plan(
                conn, legacy["planning_retry_plan_id"]
            )
            unsafe_retry = self.plan_repository.get_plan(
                conn, legacy["unsafe_retry_plan_id"]
            )
            build = self.catalog_repository.get_build(
                conn, build_id=legacy["build_id"]
            )
            item = self.catalog_repository.get_item(conn, item_id=legacy["item_id"])

        self.assertEqual((running["status"], running["stage"]), ("running", "planning"))
        self.assertEqual(running["lease_token"], "legacy-running-token")
        self.assertEqual(running["hard_deadline_at"], 5000)
        self.assertEqual(
            (planning_retry["status"], planning_retry["stage"]),
            ("running", "planning"),
        )
        self.assertIsNone(planning_retry["lease_token"])
        self.assertIsNone(planning_retry["hard_deadline_at"])
        self.assertIsNone(planning_retry["retry_reason_code"])
        self.assertEqual(unsafe_retry["status"], "failed")
        self.assertEqual(unsafe_retry["stage"], "completed")
        self.assertEqual(
            unsafe_retry["error_code"], "preparation_upgrade_retry_state_invalid"
        )
        self.assertEqual(build["execution_mode"], "full_pipeline")
        self.assertEqual(build["stage_ceiling"], "active_release")
        self.assertIsNone(build["content_manifest_version"])
        self.assertEqual(item["execution_mode_snapshot"], "full_pipeline")
        self.assertEqual(item["content_phase"], "legacy_full_pipeline")
        self.assertEqual(item["content_gate_status"], "not_applicable")
        self.assertEqual(item["content_gate_attempt_count"], 0)

        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            self._sha256(root / "migrations" / "054_learning_curriculum_preparations.sql"),
            "fa424f71cde97a8615368e3906bd055bbe2370134c18c7c903985be0df994d90",
        )
        self.assertEqual(
            self._sha256(
                root / "migrations" / "055_learning_curriculum_preparation_runner_evidence.sql"
            ),
            "91210c958236b93f2d232b82a04719b036d25a525da8565b0db2b6dc5c7325ec",
        )

    def test_target_v1_v2_and_unknown_plan_shapes_are_explicit(self):
        self._require_migration()
        v1 = build_preparation_target("primary_2")
        v2 = build_preparation_target("primary_1")
        self.assertEqual(v1["schemaVersion"], TARGET_SCHEMA_V1)
        self.assertEqual(v2["schemaVersion"], TARGET_SCHEMA_V2)
        with self.database.transaction() as conn:
            self._insert_family_child(conn, "shape-family", "shape-v1")
            self._insert_family_child(conn, "shape-family", "shape-v2")
            legacy, _ = self.plan_repository.reserve_plan(
                conn,
                family_id="shape-family",
                child_id="shape-v1",
                grade_code="primary_2",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=v1,
                target_fingerprint=preparation_target_fingerprint(v1),
                request_id="shape-v1",
                shared_build_request_id="shape-v1-build",
                now=2000,
            )
            current, _ = self.plan_repository.reserve_plan(
                conn,
                family_id="shape-family",
                child_id="shape-v2",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=v2,
                target_fingerprint=preparation_target_fingerprint(v2),
                request_id="shape-v2",
                shared_build_request_id="shape-v2-build",
                now=2000,
            )

        self.assertEqual(legacy["preparation_contract_version"], current["preparation_contract_version"])
        self.assertEqual(legacy["content_target_count"], 0)
        self.assertEqual(legacy["content_canary_target_count"], 0)
        self.assertEqual(current["content_target_count"], 30)
        self.assertEqual(current["content_canary_target_count"], 3)
        self.assertEqual(json.loads(current["stage_progress_json"])["targetCount"], 30)

        invalid_updates = {
            "v2_target_must_be_30": (
                "UPDATE learning_curriculum_preparation_plans "
                "SET content_target_count = 29 WHERE id = ?",
                current["id"],
            ),
            "v2_initial_binding_must_be_null": (
                "UPDATE learning_curriculum_preparation_plans "
                "SET work_unit_kind = 'provider_phase' WHERE id = ?",
                current["id"],
            ),
            "unknown_target_schema_fails_closed": (
                "UPDATE learning_curriculum_preparation_plans "
                "SET target_spec_json = JSON_SET(target_spec_json, '$.schemaVersion', "
                "'mira.learning.preparation-target.v999') WHERE id = ?",
                current["id"],
            ),
            "stage_progress_missing_required_key_fails_closed": (
                "UPDATE learning_curriculum_preparation_plans "
                "SET stage_progress_json = JSON_SET(JSON_REMOVE(stage_progress_json, "
                "'$.candidateCount'), '$.unexpectedCount', 0) WHERE id = ?",
                current["id"],
            ),
            "v2_claimed_coordinator_kind_cannot_be_null": (
                "UPDATE learning_curriculum_preparation_plans "
                "SET status = 'running', stage = 'planning', "
                "lease_token = 'unknown-token', lease_expires_at = 4000, "
                "heartbeat_at = 3000, hard_deadline_at = 5000, "
                "work_unit_kind = NULL WHERE id = ?",
                current["id"],
            ),
        }
        for label, (sql, plan_id) in invalid_updates.items():
            with self.subTest(label=label):
                with self.assertRaises(pymysql.MySQLError) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(sql, (plan_id,))
                self.assertEqual(raised.exception.args[0], 3819)

    def test_build_and_item_shapes_reject_mysql_unknown_counterexamples(self):
        self._require_migration()
        build, item = self._create_full_pipeline_build("shape-build")
        self.assertEqual(build["execution_mode"], "full_pipeline")
        self.assertEqual(build["stage_ceiling"], "active_release")
        self.assertEqual(item["execution_mode_snapshot"], "full_pipeline")
        self.assertEqual(item["content_phase"], "legacy_full_pipeline")
        self.assertEqual(item["content_gate_status"], "not_applicable")

        canary = json.dumps(
            {"version": "mira.learning.primary-1-canary.v1", "targets": []},
            separators=(",", ":"),
        )
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_build_jobs SET execution_mode = 'content_only', "
                "content_manifest_version = ?, canary_manifest_json = ?, "
                "stage_ceiling = 'content_ready' WHERE id = ?",
                (TARGET_SCHEMA_V2, canary, build["id"]),
            )
            conn.execute(
                "UPDATE learning_catalog_build_items "
                "SET execution_mode_snapshot = 'content_only', "
                "content_manifest_version_snapshot = ?, subject_ordinal = 1, "
                "boundary_ordinal = 1, content_phase = 'not_started', "
                "content_gate_status = 'not_started', content_gate_attempt_count = 0 "
                "WHERE id = ?",
                (TARGET_SCHEMA_V2, item["id"]),
            )

        invalid_updates = {
            "content_build_null_canary": (
                "UPDATE learning_catalog_build_jobs SET canary_manifest_json = NULL WHERE id = ?",
                build["id"],
            ),
            "content_item_null_subject_ordinal": (
                "UPDATE learning_catalog_build_items SET subject_ordinal = NULL WHERE id = ?",
                item["id"],
            ),
            "content_item_package_bypass": (
                "UPDATE learning_catalog_build_items SET package_attempt_count = 1 WHERE id = ?",
                item["id"],
            ),
            "passed_gate_without_receipt": (
                "UPDATE learning_catalog_build_items SET status = 'course_ready', "
                "content_phase = 'course_ready', content_gate_status = 'passed', "
                "content_gate_passed_at = 3000, content_validation_contract_version = ?, "
                "content_receipt_hash = NULL WHERE id = ?",
                item["id"],
            ),
            "build_null_execution_mode": (
                "UPDATE learning_catalog_build_jobs SET execution_mode = NULL WHERE id = ?",
                build["id"],
            ),
            "build_null_stage_ceiling": (
                "UPDATE learning_catalog_build_jobs SET stage_ceiling = NULL WHERE id = ?",
                build["id"],
            ),
            "content_item_null_execution_mode": (
                "UPDATE learning_catalog_build_items "
                "SET execution_mode_snapshot = NULL WHERE id = ?",
                item["id"],
            ),
            "content_item_null_gate_attempt_count": (
                "UPDATE learning_catalog_build_items "
                "SET content_gate_attempt_count = NULL WHERE id = ?",
                item["id"],
            ),
            "provider_phase_null_claim_attempt_fails_closed": (
                "UPDATE learning_catalog_build_items SET status = 'processing', "
                "attempt_count = 1, active_generation_request_id = 'unknown-request', "
                "content_phase = 'outline', content_claim_attempt_ordinal = NULL, "
                "content_attempt_started_at = 3000, "
                "content_provider_attempt_hard_deadline_at = 5000, "
                "content_work_unit_deadline_at = 4000 WHERE id = ?",
                item["id"],
            ),
            "passed_gate_requires_positive_gate_attempt": (
                "UPDATE learning_catalog_build_items SET status = 'course_ready', "
                "attempt_count = 1, active_generation_request_id = 'gate-request', "
                "content_claim_attempt_ordinal = 1, content_phase = 'course_ready', "
                "content_gate_status = 'passed', content_gate_attempt_count = 0, "
                "course_id = 'course-1', course_version = 'course-v1', "
                "content_gate_passed_at = 3000, content_validation_contract_version = "
                "'mira.learning.primary-1-content-validation.v1', "
                "content_receipt_hash = REPEAT('a', 64) WHERE id = ?",
                item["id"],
            ),
        }
        for label, (sql, row_id) in invalid_updates.items():
            with self.subTest(label=label):
                params = (
                    ("mira.learning.primary-1-content-validation.v1", row_id)
                    if label == "passed_gate_without_receipt"
                    else (row_id,)
                )
                with self.assertRaises(pymysql.MySQLError) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(sql, params)
                expected_error = (
                    1048
                    if label
                    in {
                        "build_null_execution_mode",
                        "build_null_stage_ceiling",
                        "content_item_null_execution_mode",
                        "content_item_null_gate_attempt_count",
                    }
                    else 3819
                )
                self.assertEqual(raised.exception.args[0], expected_error)

    def test_failed_item_gate_evidence_is_exact_and_mysql_unknown_closed(self):
        build, item = self._create_full_pipeline_build("failed-item-shape")
        canary = json.dumps(
            {"version": "mira.learning.primary-1-canary.v1", "targets": []},
            separators=(",", ":"),
        )
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_build_jobs SET execution_mode = 'content_only', "
                "content_manifest_version = ?, canary_manifest_json = ?, "
                "stage_ceiling = 'content_ready' WHERE id = ?",
                (TARGET_SCHEMA_V2, canary, build["id"]),
            )
            conn.execute(
                "UPDATE learning_catalog_build_items SET "
                "execution_mode_snapshot = 'content_only', "
                "content_manifest_version_snapshot = ?, subject_ordinal = 1, "
                "boundary_ordinal = 1, status = 'failed', attempt_count = 1, "
                "active_generation_request_id = 'failed-generation', "
                "content_claim_attempt_ordinal = 1, content_phase = 'failed', "
                "content_gate_status = 'not_started', content_gate_attempt_count = 0, "
                "content_gate_passed_at = NULL, "
                "content_validation_contract_version = NULL, "
                "content_receipt_hash = NULL, content_lease_token = NULL, "
                "content_lease_expires_at = NULL, content_heartbeat_at = NULL, "
                "content_provider_attempt_hard_deadline_at = NULL, "
                "content_work_unit_deadline_at = NULL, "
                "error_code = 'content_failed', "
                "error_message_safe = 'content generation failed' WHERE id = ?",
                (TARGET_SCHEMA_V2, item["id"]),
            )
            not_started = conn.execute(
                "SELECT content_gate_status, content_gate_attempt_count "
                "FROM learning_catalog_build_items WHERE id = ?",
                (item["id"],),
            ).fetchone()
            conn.execute(
                "UPDATE learning_catalog_build_items "
                "SET content_gate_status = 'failed_deterministic', "
                "content_gate_attempt_count = 1 WHERE id = ?",
                (item["id"],),
            )
            deterministic_first = conn.execute(
                "SELECT content_gate_status, content_gate_attempt_count "
                "FROM learning_catalog_build_items WHERE id = ?",
                (item["id"],),
            ).fetchone()
            conn.execute(
                "UPDATE learning_catalog_build_items "
                "SET content_gate_attempt_count = 3 WHERE id = ?",
                (item["id"],),
            )
            deterministic_last = conn.execute(
                "SELECT content_gate_status, content_gate_attempt_count "
                "FROM learning_catalog_build_items WHERE id = ?",
                (item["id"],),
            ).fetchone()

        self.assertEqual(
            (not_started["content_gate_status"], not_started["content_gate_attempt_count"]),
            ("not_started", 0),
        )
        self.assertEqual(
            (
                deterministic_first["content_gate_status"],
                deterministic_first["content_gate_attempt_count"],
            ),
            ("failed_deterministic", 1),
        )
        self.assertEqual(deterministic_last["content_gate_attempt_count"], 3)

        invalid_mutations = {
            "pass_timestamp": "content_gate_passed_at = 1500",
            "validation_version": (
                "content_validation_contract_version = "
                "'mira.learning.primary-1-content-validation.v1'"
            ),
            "receipt_hash": "content_receipt_hash = REPEAT('a', 64)",
            "not_started_attempt_three": (
                "content_gate_status = 'not_started', content_gate_attempt_count = 3"
            ),
            "deterministic_attempt_zero": (
                "content_gate_status = 'failed_deterministic', "
                "content_gate_attempt_count = 0"
            ),
        }
        observed = {}
        for label, mutation in invalid_mutations.items():
            error_code = None
            try:
                with self.database.transaction() as conn:
                    conn.execute(
                        "UPDATE learning_catalog_build_items SET "
                        "content_gate_status = 'not_started', "
                        "content_gate_attempt_count = 0, "
                        "content_gate_passed_at = NULL, "
                        "content_validation_contract_version = NULL, "
                        "content_receipt_hash = NULL WHERE id = ?",
                        (item["id"],),
                    )
                    conn.execute(
                        f"UPDATE learning_catalog_build_items SET {mutation} WHERE id = ?",
                        (item["id"],),
                    )
            except pymysql.MySQLError as error:
                error_code = int(error.args[0])
            observed[label] = error_code

        self.assertEqual(
            observed,
            {label: 3819 for label in invalid_mutations},
        )

    def test_full_pipeline_build_identity_cannot_replay_as_content_only(self):
        self._require_migration()
        build, _ = self._create_full_pipeline_build("mode-identity")
        canary = json.dumps({"version": "v1", "targets": []})
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_build_jobs SET execution_mode = 'content_only', "
                "content_manifest_version = ?, canary_manifest_json = ?, "
                "stage_ceiling = 'content_ready' WHERE id = ?",
                (TARGET_SCHEMA_V2, canary, build["id"]),
            )

        with self.assertRaises(LearningCatalogBuildConflict):
            self._create_full_pipeline_build("mode-identity")

    def _require_migration(self) -> None:
        with self.database.transaction() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            ).fetchone()
        self.assertEqual(row["count"], 1, "056 must be registered on real MySQL")

    def _create_full_pipeline_build(self, request_id: str):
        target = build_preparation_target("primary_1")
        first = target["boundaries"][0]
        targets = [
            {
                "gradeCode": "primary_1",
                "subject": first["subject"],
                "skillId": first["skillId"],
                "boundaryVersion": first["boundaryVersion"],
            }
        ]
        with self.catalog_repository.transaction() as conn:
            build, _ = self.catalog_repository.create_or_get_build(
                conn,
                request_id=request_id,
                curriculum_version=target["curriculumVersion"],
                title="Task 2 schema fixture",
                target_spec={"request": request_id},
                targets=targets,
                variants_per_boundary=1,
                now=2500,
            )
            items = self.catalog_repository.list_build_items(
                conn, build_id=build["id"]
            )
        return build, items[0]

    def _restore_055_schema_and_insert_legacy_rows(self) -> dict[str, str]:
        with self.database.transaction() as conn:
            conn.execute("DROP TABLE learning_course_provider_dispatches")
            for table, constraints in (
                (
                    "learning_curriculum_preparation_plans",
                    (
                        "chk_learning_prep_content_state_evidence",
                        "chk_learning_prep_formal_state_evidence",
                        "chk_learning_prep_content_counts",
                        "chk_learning_prep_stage_progress_json",
                    ),
                ),
                (
                    "learning_catalog_build_jobs",
                    ("chk_learning_catalog_build_content_mode",),
                ),
                (
                    "learning_catalog_build_items",
                    ("chk_learning_catalog_item_content_state",),
                ),
            ):
                for constraint in constraints:
                    if self._constraint_count(conn, table, constraint):
                        conn.execute(f"ALTER TABLE {table} DROP CHECK {constraint}")
            for table, columns in (
                ("learning_curriculum_preparation_plans", PLAN_COLUMNS),
                ("learning_catalog_build_jobs", BUILD_COLUMNS),
                ("learning_catalog_build_items", ITEM_COLUMNS),
            ):
                for column in reversed(columns):
                    if column in self._column_names(conn, table):
                        conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.executescript(LEGACY_STATE_MIGRATION.read_text(encoding="utf-8"))
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            )
            self._insert_family_child(conn, "legacy-family", "legacy-running")
            self._insert_family_child(conn, "legacy-family", "legacy-planning-retry")
            self._insert_family_child(conn, "legacy-family", "legacy-unsafe-retry")
            running_id = self._insert_legacy_plan(
                conn,
                child_id="legacy-running",
                request_id="legacy-running",
                status="running",
                stage="queued",
                lease_token="legacy-running-token",
                lease_expires_at=4500,
                heartbeat_at=4000,
                next_run_at=4000,
                hard_deadline_at=5000,
                resume_stage=None,
            )
            planning_retry_id = self._insert_legacy_plan(
                conn,
                child_id="legacy-planning-retry",
                request_id="legacy-planning-retry",
                status="queued",
                stage="retry_wait",
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
                next_run_at=4100,
                hard_deadline_at=5100,
                resume_stage="planning",
            )
            unsafe_retry_id = self._insert_legacy_plan(
                conn,
                child_id="legacy-unsafe-retry",
                request_id="legacy-unsafe-retry",
                status="queued",
                stage="retry_wait",
                lease_token=None,
                lease_expires_at=None,
                heartbeat_at=None,
                next_run_at=4200,
                hard_deadline_at=5200,
                resume_stage="generating_content",
            )
            conn.execute(
                "INSERT INTO learning_catalog_releases("
                "id, curriculum_version, title, status, quality_status, "
                "required_boundary_count, ready_item_count, created_at, updated_at) "
                "VALUES ('legacy-release', 'primary-cn-2026.1', 'Legacy', 'draft', "
                "'building', 1, 0, 1, 1)"
            )
            conn.execute(
                "INSERT INTO learning_catalog_build_jobs("
                "id, request_id, release_id, curriculum_version, status, "
                "target_spec_json, total_item_count, ready_item_count, "
                "failed_item_count, created_at, updated_at) VALUES ("
                "'legacy-build', 'legacy-build-request', 'legacy-release', "
                "'primary-cn-2026.1', 'queued', '{}', 1, 0, 0, 1, 1)"
            )
            conn.execute(
                "INSERT INTO learning_catalog_build_items("
                "id, build_job_id, release_id, grade_code, subject, skill_id, "
                "curriculum_version, boundary_version, variant_ordinal, status, "
                "attempt_count, generation_request_id, package_attempt_count, "
                "created_at, updated_at) VALUES ("
                "'legacy-item', 'legacy-build', 'legacy-release', 'primary_2', "
                "'math', 'legacy-skill', 'primary-cn-2026.1', 'legacy-boundary', "
                "1, 'pending', 0, 'legacy-generation', 0, 1, 1)"
            )
        return {
            "running_plan_id": running_id,
            "planning_retry_plan_id": planning_retry_id,
            "unsafe_retry_plan_id": unsafe_retry_id,
            "build_id": "legacy-build",
            "item_id": "legacy-item",
        }

    def _insert_legacy_plan(
        self,
        conn,
        *,
        child_id: str,
        request_id: str,
        status: str,
        stage: str,
        lease_token: str | None,
        lease_expires_at: int | None,
        heartbeat_at: int | None,
        next_run_at: int | None,
        hard_deadline_at: int | None,
        resume_stage: str | None,
    ) -> str:
        target = build_preparation_target("primary_2")
        fingerprint = preparation_target_fingerprint(target)
        plan_id = f"legacy-plan-{child_id}"
        subject_progress = {
            subject: {
                "totalCourseCount": target["subjectTargets"][subject][
                    "totalCourseCount"
                ],
                "readyCourseCount": 0,
                "failedCourseCount": 0,
            }
            for subject in ("chinese", "math", "english")
        }
        conn.execute(
            """
            INSERT INTO learning_curriculum_preparation_plans(
              id, family_id, child_id, grade_code, school_year_start_year,
              grade_selection_revision, curriculum_version,
              preparation_contract_version, target_spec_json, target_fingerprint,
              request_id, shared_build_request_id, status, stage,
              total_course_count, ready_course_count, failed_course_count,
              progress_percent, subject_progress_json, retry_ordinal, resume_stage,
              lease_token, lease_expires_at, heartbeat_at, next_run_at,
              hard_deadline_at, last_progress_at, started_at, created_at, updated_at
            ) VALUES (?, 'legacy-family', ?, 'primary_2', 2026, 1, ?, ?, ?, ?, ?, ?,
              ?, ?, 27, 0, 0, 0, ?, 0, ?, ?, ?, ?, ?, ?, 1, 1, 1, 1)
            """,
            (
                plan_id,
                child_id,
                target["curriculumVersion"],
                target["preparationContractVersion"],
                json.dumps(target, ensure_ascii=False, separators=(",", ":")),
                fingerprint,
                request_id,
                f"legacy-build:{fingerprint}",
                status,
                stage,
                json.dumps(subject_progress, ensure_ascii=False, separators=(",", ":")),
                resume_stage,
                lease_token,
                lease_expires_at,
                heartbeat_at,
                next_run_at,
                hard_deadline_at,
            ),
        )
        return plan_id

    @staticmethod
    def _insert_family_child(conn, family_id: str, child_id: str) -> None:
        conn.execute(
            "INSERT IGNORE INTO families(id, name, created_at) VALUES (?, ?, 1)",
            (family_id, family_id),
        )
        conn.execute(
            "INSERT INTO children(id, family_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, 1)",
            (child_id, family_id, child_id),
        )

    @staticmethod
    def _column_names(conn, table: str) -> set[str]:
        rows = conn.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?",
            (table,),
        ).fetchall()
        return {str(row["COLUMN_NAME"]) for row in rows}

    @staticmethod
    def _constraint_count(conn, table: str, constraint: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? "
            "AND CONSTRAINT_NAME = ? AND CONSTRAINT_TYPE = 'CHECK'",
            (table, constraint),
        ).fetchone()
        return int(row["count"])

    @staticmethod
    def _unique_index_columns(conn, table: str) -> dict[str, tuple[str, ...]]:
        rows = conn.execute(
            "SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX FROM INFORMATION_SCHEMA.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND NON_UNIQUE = 0 "
            "ORDER BY INDEX_NAME, SEQ_IN_INDEX",
            (table,),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            if row["INDEX_NAME"] == "PRIMARY":
                continue
            result.setdefault(str(row["INDEX_NAME"]), []).append(str(row["COLUMN_NAME"]))
        return {name: tuple(columns) for name, columns in result.items()}

    @staticmethod
    def _sha256(path: Path) -> str:
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
