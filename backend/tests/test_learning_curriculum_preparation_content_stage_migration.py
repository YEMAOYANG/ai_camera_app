from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import psycopg

from core.database import Database
from repositories.learning_catalog_repository import (
    LearningCatalogBuildConflict,
    LearningCatalogRepository,
)
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from services.learning_curriculum_preparation_contract import (
    TARGET_SCHEMA_V1,
    TARGET_SCHEMA_V2,
    build_preparation_target,
    preparation_target_fingerprint,
)
from tests.support import fresh_test_config


# The PostgreSQL baseline carries the content-stage schema of MySQL migration
# 056; its replay, repair and legacy backfill tests retired with MySQL.
BASELINE_VERSION = "100_postgres_baseline_schema.sql"


class LearningCurriculumPreparationContentStageMigrationTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/mira_test", self.database_url)
        self.assertNotRegex(self.database_url, r"/mira(\?|$)")
        self.database = Database(self.database_url)
        self.plan_repository = LearningCurriculumPreparationRepository(self.database)
        self.catalog_repository = LearningCatalogRepository(self.database)

    def test_target_v1_v2_and_unknown_plan_shapes_are_explicit(self):
        self._require_migration()
        with patch("services.learning_curriculum_preparation_contract.formal_content_contract", return_value=None):
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
                "SET target_spec_json = jsonb_set(CAST(target_spec_json AS jsonb), "
                "'{schemaVersion}', '\"mira.learning.preparation-target.v999\"') WHERE id = ?",
                current["id"],
            ),
            "stage_progress_missing_required_key_fails_closed": (
                "UPDATE learning_curriculum_preparation_plans "
                "SET stage_progress_json = jsonb_set(JSON_REMOVE(stage_progress_json, "
                "'$.candidateCount'), '{unexpectedCount}', '0') WHERE id = ?",
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
                with self.assertRaises(psycopg.Error) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(sql, (plan_id,))
                self.assertEqual(raised.exception.sqlstate, "23514")  # check_violation

    def test_build_and_item_shapes_reject_sql_unknown_counterexamples(self):
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
                with self.assertRaises(psycopg.Error) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(sql, params)
                expected_error = (  # not_null_violation, else check_violation
                    "23502"
                    if label
                    in {
                        "build_null_execution_mode",
                        "build_null_stage_ceiling",
                        "content_item_null_execution_mode",
                        "content_item_null_gate_attempt_count",
                    }
                    else "23514"
                )
                self.assertEqual(raised.exception.sqlstate, expected_error)

    def test_failed_item_gate_evidence_is_exact_and_sql_unknown_closed(self):
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
            except psycopg.Error as error:
                error_code = error.sqlstate
            observed[label] = error_code

        self.assertEqual(
            observed,
            {label: "23514" for label in invalid_mutations},  # check_violation
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
                (BASELINE_VERSION,),
            ).fetchone()
        self.assertEqual(row["count"], 1, "the PostgreSQL baseline must be registered")

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

    @staticmethod
    def _insert_family_child(conn, family_id: str, child_id: str) -> None:
        conn.execute(
            "INSERT INTO families(id, name, created_at) VALUES (?, ?, 1) ON CONFLICT DO NOTHING",
            (family_id, family_id),
        )
        conn.execute(
            "INSERT INTO children(id, family_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, 1)",
            (child_id, family_id, child_id),
        )


if __name__ == "__main__":
    unittest.main()
