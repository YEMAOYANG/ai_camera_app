from __future__ import annotations

import hashlib
import json
import unittest

import pymysql

from core.database import Database
import repositories.dynamic_learning_course_repository as dispatch_repository
from services.learning_curriculum_preparation_contract import TARGET_SCHEMA_V2
from tests.support import fresh_test_config


MIGRATION_VERSION = "056_learning_curriculum_preparation_content_stage.sql"


def _checkpoint_sha256(checkpoint: dict[str, object]) -> str:
    canonical = json.dumps(
        checkpoint,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LearningCourseProviderDispatchSafeCodeContractTest(unittest.TestCase):
    def test_question_phase_diagnostic_codes_can_be_persisted_failed_safe(self):
        codes = (
            "question_phase_json_rejected",
            "question_phase_verification_json_rejected",
            "question_phase_verification_answers_rejected",
            "question_phase_verification_numeric_rejected",
            "question_phase_verification_review_rejected",
            "question_phase_verification_semantic_rejected",
            "question_phase_verification_checkpoint_rejected",
        )
        for code in codes:
            with self.subTest(code=code):
                dispatch_repository._validate_strict_terminal_result(
                    outcome="failed_safe",
                    checkpoint=None,
                    output_sha256=None,
                    provider_request_id_hash=None,
                    input_tokens=None,
                    output_tokens=None,
                    billing_evidence="unknown",
                    safe_error_code=code,
                )


class LearningCourseProviderDispatchRepositoryTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)
        with self.database.transaction() as conn:
            marker = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            ).fetchone()
        self.assertEqual(marker["count"], 1, "056 must be installed on real MySQL")
        self.begin_provider_dispatch = getattr(
            dispatch_repository, "begin_provider_dispatch", None
        )
        self.complete_provider_dispatch = getattr(
            dispatch_repository, "complete_provider_dispatch", None
        )
        self.assertTrue(callable(self.begin_provider_dispatch))
        self.assertTrue(callable(self.complete_provider_dispatch))
        self._insert_active_content_item()

    def test_begin_is_deterministic_exact_replay_and_conflict_safe(self):
        with self.database.transaction() as conn:
            first = self._begin(conn)
            replay = self._begin(conn)
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = ?",
                ("dispatch-item",),
            ).fetchone()

        self.assertEqual(first["id"], replay["id"])
        self.assertEqual(first["status"], "dispatched")
        self.assertEqual(count["count"], 1)

        with self.assertRaisesRegex(ValueError, "identity"):
            with self.database.transaction() as conn:
                self._begin(conn, provider="different-provider")

        with self.assertRaisesRegex(ValueError, "lease identity"):
            with self.database.transaction() as conn:
                self._begin(conn, attempt_hard_deadline_at=1860001)

        with self.assertRaisesRegex(ValueError, "unfinished provider dispatch"):
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_catalog_build_items "
                    "SET content_phase = 'raw_candidate' WHERE id = 'dispatch-item'"
                )
                self._begin(conn, phase="raw_candidate", phase_ordinal=2)

    def test_phase_name_and_ordinal_are_one_to_one_and_both_unique_keys_exist(self):
        with self.database.transaction() as conn:
            row = self._begin(conn)
            indexes = conn.execute(
                "SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX "
                "FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'learning_course_provider_dispatches' "
                "AND INDEX_NAME IN (?, ?) ORDER BY INDEX_NAME, SEQ_IN_INDEX",
                (
                    "uq_learning_provider_dispatch_phase",
                    "uq_learning_provider_dispatch_ordinal",
                ),
            ).fetchall()

        grouped: dict[str, list[str]] = {}
        for index in indexes:
            grouped.setdefault(str(index["INDEX_NAME"]), []).append(
                str(index["COLUMN_NAME"])
            )
        self.assertEqual(
            grouped,
            {
                "uq_learning_provider_dispatch_ordinal": [
                    "build_item_id",
                    "logical_attempt",
                    "phase_ordinal",
                ],
                "uq_learning_provider_dispatch_phase": [
                    "build_item_id",
                    "logical_attempt",
                    "phase",
                ],
            },
        )

        with self.assertRaisesRegex(ValueError, "ordinal"):
            with self.database.transaction() as conn:
                self._begin(conn, phase="raw_candidate", phase_ordinal=1)

        with self.assertRaises(pymysql.MySQLError) as raised:
            with self.database.transaction() as conn:
                conn.execute(
                    "INSERT INTO learning_course_provider_dispatches("
                    "id, build_item_id, logical_attempt, phase, phase_ordinal, "
                    "generation_request_id, item_lease_token, provider, model, "
                    "profile, input_sha256, status, attempt_started_at, "
                    "attempt_hard_deadline_at, dispatched_at) "
                    "SELECT CONCAT(id, '-duplicate'), build_item_id, logical_attempt, "
                    "phase, phase_ordinal, generation_request_id, item_lease_token, "
                    "provider, model, profile, input_sha256, status, attempt_started_at, "
                    "attempt_hard_deadline_at, dispatched_at "
                    "FROM learning_course_provider_dispatches WHERE id = ?",
                    (row["id"],),
                )
        self.assertEqual(raised.exception.args[0], 1062)

        with self.assertRaises(pymysql.MySQLError) as raised:
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_course_provider_dispatches "
                    "SET phase = 'raw_candidate' WHERE id = ?",
                    (row["id"],),
                )
        self.assertEqual(raised.exception.args[0], 3819)

    def test_new_dispatches_advance_strictly_beyond_max_succeeded_ordinal(self):
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO learning_course_provider_dispatches("
                "id, build_item_id, logical_attempt, phase, phase_ordinal, "
                "generation_request_id, item_lease_token, provider, model, profile, "
                "input_sha256, status, checkpoint_json, output_sha256, "
                "attempt_started_at, attempt_hard_deadline_at, billing_evidence, "
                "dispatched_at, completed_at) VALUES ("
                "'historical-phase-14', 'dispatch-item', 1, "
                "'verification_after_repair', 14, 'generation-request-1', "
                "'lease-token-1', 'kimi', 'kimi-k2.6', 'question-generator-v2', "
                "REPEAT('a', 64), 'succeeded', '{}', REPEAT('b', 64), "
                "1000, 1860000, 'unknown', 1100, 1500)"
            )
            rollback_error = None
            try:
                self._begin(conn)
            except ValueError as error:
                rollback_error = str(error)
            rollback_count = int(
                conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                    "WHERE build_item_id = 'dispatch-item'"
                ).fetchone()["count"]
            )

        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)
        self._insert_active_content_item()

        with self.database.transaction() as conn:
            first = self._begin(conn)
            self.assertTrue(
                self.complete_provider_dispatch(
                    conn,
                    dispatch_id=first["id"],
                    build_item_id="dispatch-item",
                    generation_request_id="generation-request-1",
                    item_lease_token="lease-token-1",
                    outcome="succeeded",
                    checkpoint={"phase": "outline"},
                    output_sha256=_checkpoint_sha256({"phase": "outline"}),
                    provider_request_id_hash=None,
                    input_tokens=None,
                    output_tokens=None,
                    billing_evidence="unknown",
                    safe_error_code=None,
                    completed_at=1500,
                )
            )
            conn.execute(
                "UPDATE learning_catalog_build_items "
                "SET content_phase = 'verification_after_repair' "
                "WHERE id = 'dispatch-item'"
            )
            last = self._begin(
                conn,
                phase="verification_after_repair",
                phase_ordinal=14,
            )
            self.assertTrue(
                self.complete_provider_dispatch(
                    conn,
                    dispatch_id=last["id"],
                    build_item_id="dispatch-item",
                    generation_request_id="generation-request-1",
                    item_lease_token="lease-token-1",
                    outcome="succeeded",
                    checkpoint={"phase": "verification_after_repair"},
                    output_sha256=_checkpoint_sha256(
                        {"phase": "verification_after_repair"}
                    ),
                    provider_request_id_hash=None,
                    input_tokens=None,
                    output_tokens=None,
                    billing_evidence="unknown",
                    safe_error_code=None,
                    completed_at=1500,
                )
            )
            replay = self._begin(
                conn,
                phase="verification_after_repair",
                phase_ordinal=14,
            )
            conn.execute(
                "UPDATE learning_catalog_build_items "
                "SET content_phase = 'raw_candidate' WHERE id = 'dispatch-item'"
            )
            lower_error = None
            try:
                self._begin(conn, phase="raw_candidate", phase_ordinal=2)
            except ValueError as error:
                lower_error = str(error)
            forward_count = int(
                conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                    "WHERE build_item_id = 'dispatch-item'"
                ).fetchone()["count"]
            )

        self.assertEqual(replay["id"], last["id"])
        self.assertEqual(
            (
                rollback_error is not None,
                rollback_count,
                lower_error is not None,
                forward_count,
            ),
            (True, 1, True, 2),
        )
        self.assertIn("ordinal", rollback_error or "")
        self.assertIn("ordinal", lower_error or "")

    def test_logical_attempt_is_exactly_one_or_two_in_python_and_mysql(self):
        for logical_attempt in (0, 3):
            with self.subTest(logical_attempt=logical_attempt):
                with self.assertRaisesRegex(ValueError, "logical attempt"):
                    with self.database.transaction() as conn:
                        self._begin(conn, logical_attempt=logical_attempt)

        with self.database.transaction() as conn:
            row = self._begin(conn)
        with self.assertRaises(pymysql.MySQLError) as raised:
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_course_provider_dispatches "
                    "SET logical_attempt = 0 WHERE id = ?",
                    (row["id"],),
                )
        self.assertEqual(raised.exception.args[0], 3819)

        with self.database.transaction() as conn:
            self.assertTrue(
                self.complete_provider_dispatch(
                    conn,
                    dispatch_id=row["id"],
                    build_item_id="dispatch-item",
                    generation_request_id="generation-request-1",
                    item_lease_token="lease-token-1",
                    outcome="succeeded",
                    checkpoint={"phase": "outline"},
                    output_sha256=_checkpoint_sha256({"phase": "outline"}),
                    provider_request_id_hash=None,
                    input_tokens=None,
                    output_tokens=None,
                    billing_evidence="unknown",
                    safe_error_code=None,
                    completed_at=1500,
                )
            )
            conn.execute(
                "UPDATE learning_catalog_build_items SET attempt_count = 2, "
                "content_claim_attempt_ordinal = 2, "
                "active_generation_request_id = 'generation-request-2', "
                "content_lease_token = 'lease-token-2' WHERE id = 'dispatch-item'"
            )
            second = self._begin(
                conn,
                logical_attempt=2,
                generation_request_id="generation-request-2",
                item_lease_token="lease-token-2",
            )
        self.assertEqual(second["logical_attempt"], 2)

    def test_success_completion_is_canonical_and_monotonic(self):
        checkpoint = {"questionCount": 5, "phase": "outline"}
        with self.database.transaction() as conn:
            row = self._begin(conn)
            completed = self.complete_provider_dispatch(
                conn,
                dispatch_id=row["id"],
                build_item_id="dispatch-item",
                generation_request_id="generation-request-1",
                item_lease_token="lease-token-1",
                outcome="succeeded",
                checkpoint=checkpoint,
                output_sha256=_checkpoint_sha256(checkpoint),
                provider_request_id_hash="c" * 64,
                input_tokens=12,
                output_tokens=34,
                billing_evidence="reported",
                safe_error_code=None,
                completed_at=1500,
            )
            persisted = conn.execute(
                "SELECT * FROM learning_course_provider_dispatches WHERE id = ?",
                (row["id"],),
            ).fetchone()
            replay = self.complete_provider_dispatch(
                conn,
                dispatch_id=row["id"],
                build_item_id="dispatch-item",
                generation_request_id="generation-request-1",
                item_lease_token="lease-token-1",
                outcome="succeeded",
                checkpoint=checkpoint,
                output_sha256=_checkpoint_sha256(checkpoint),
                provider_request_id_hash="c" * 64,
                input_tokens=12,
                output_tokens=34,
                billing_evidence="reported",
                safe_error_code=None,
                completed_at=1500,
            )

        self.assertTrue(completed)
        self.assertFalse(replay)
        self.assertEqual(persisted["status"], "succeeded")
        self.assertEqual(
            json.loads(persisted["checkpoint_json"]), checkpoint
        )
        self.assertEqual(persisted["output_sha256"], _checkpoint_sha256(checkpoint))
        self.assertEqual(persisted["provider_request_id_hash"], "c" * 64)
        self.assertEqual(persisted["billing_evidence"], "reported")
        self.assertEqual(persisted["input_tokens"], 12)
        self.assertEqual(persisted["output_tokens"], 34)
        self.assertIsNone(persisted["safe_error_code"])

    def test_terminal_receipt_shapes_and_mysql_unknown_are_closed(self):
        with self.database.transaction() as conn:
            row = self._begin(conn)

        invalid_api = (
            {
                "outcome": "succeeded",
                "checkpoint": None,
                "output_sha256": "d" * 64,
                "safe_error_code": None,
                "billing_evidence": "reported",
            },
            {
                "outcome": "failed_safe",
                "checkpoint": {"candidate": "must-not-persist"},
                "output_sha256": None,
                "safe_error_code": "provider_no_candidate",
                "billing_evidence": "unknown",
            },
            {
                "outcome": "ambiguous",
                "checkpoint": None,
                "output_sha256": None,
                "safe_error_code": None,
                "billing_evidence": "unknown",
            },
            {
                "outcome": "succeeded",
                "checkpoint": {"ok": True},
                "output_sha256": "d" * 64,
                "safe_error_code": None,
                "billing_evidence": "estimated",
            },
        )
        for mutation in invalid_api:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    with self.database.transaction() as conn:
                        self.complete_provider_dispatch(
                            conn,
                            dispatch_id=row["id"],
                            build_item_id="dispatch-item",
                            generation_request_id="generation-request-1",
                            item_lease_token="lease-token-1",
                            provider_request_id_hash=None,
                            input_tokens=None,
                            output_tokens=None,
                            completed_at=1500,
                            **mutation,
                        )

        invalid_dml = (
            "UPDATE learning_course_provider_dispatches SET status = 'succeeded', "
            "completed_at = 1500, output_sha256 = REPEAT('d', 64), "
            "billing_evidence = 'reported' WHERE id = ?",
            "UPDATE learning_course_provider_dispatches SET status = 'failed_safe', "
            "completed_at = 1500, checkpoint_json = '{}', billing_evidence = 'unknown', "
            "safe_error_code = 'provider_no_candidate' WHERE id = ?",
            "UPDATE learning_course_provider_dispatches SET status = 'ambiguous', "
            "completed_at = 1500, billing_evidence = 'unknown', safe_error_code = NULL "
            "WHERE id = ?",
            "UPDATE learning_course_provider_dispatches SET status = 'succeeded', "
            "completed_at = 1500, checkpoint_json = '{}', "
            "output_sha256 = REPEAT('d', 64), billing_evidence = 'reported', "
            "input_tokens = -1 WHERE id = ?",
            "UPDATE learning_course_provider_dispatches SET status = 'succeeded', "
            "completed_at = 1860001, checkpoint_json = '{}', "
            "output_sha256 = REPEAT('d', 64), billing_evidence = 'reported' "
            "WHERE id = ?",
        )
        for sql in invalid_dml:
            with self.subTest(sql=sql):
                with self.assertRaises(pymysql.MySQLError) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(sql, (row["id"],))
                self.assertEqual(raised.exception.args[0], 3819)

    def test_failed_safe_is_terminal_without_external_replay(self):
        with self.database.transaction() as conn:
            failed = self._begin(conn)
            self.assertTrue(
                self.complete_provider_dispatch(
                    conn,
                    dispatch_id=failed["id"],
                    build_item_id="dispatch-item",
                    generation_request_id="generation-request-1",
                    item_lease_token="lease-token-1",
                    outcome="failed_safe",
                    checkpoint=None,
                    output_sha256=None,
                    provider_request_id_hash="e" * 64,
                    input_tokens=10,
                    output_tokens=0,
                    billing_evidence="reported",
                    safe_error_code="question_phase_verification_semantic_rejected",
                    completed_at=1500,
                )
            )
            failed_replay = self._begin(conn)
            failed_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'dispatch-item' AND phase = 'outline'"
            ).fetchone()
            conn.execute(
                "UPDATE learning_catalog_build_items SET content_phase = 'raw_candidate' "
                "WHERE id = 'dispatch-item'"
            )
            with self.assertRaisesRegex(ValueError, "terminal provider dispatch"):
                self._begin(conn, phase="raw_candidate", phase_ordinal=2)
            rows = conn.execute(
                "SELECT phase, status, checkpoint_json, output_sha256, safe_error_code "
                "FROM learning_course_provider_dispatches ORDER BY phase_ordinal"
            ).fetchall()

        self.assertEqual(failed_replay["status"], "failed_safe")
        self.assertEqual(failed_count["count"], 1)
        self.assertEqual(
            [(row["phase"], row["status"]) for row in rows],
            [("outline", "failed_safe")],
        )
        self.assertTrue(all(row["checkpoint_json"] is None for row in rows))
        self.assertTrue(all(row["output_sha256"] is None for row in rows))
        self.assertEqual(
            rows[0]["safe_error_code"],
            "question_phase_verification_semantic_rejected",
        )

    def test_ambiguous_is_terminal_without_external_replay(self):
        with self.database.transaction() as conn:
            ambiguous = self._begin(conn)
            self.assertTrue(
                self.complete_provider_dispatch(
                    conn,
                    dispatch_id=ambiguous["id"],
                    build_item_id="dispatch-item",
                    generation_request_id="generation-request-1",
                    item_lease_token="lease-token-1",
                    outcome="ambiguous",
                    checkpoint=None,
                    output_sha256=None,
                    provider_request_id_hash=None,
                    input_tokens=None,
                    output_tokens=None,
                    billing_evidence="unknown",
                    safe_error_code="provider_outcome_unknown",
                    completed_at=1500,
                )
            )
            replay = self._begin(conn)
            conn.execute(
                "UPDATE learning_catalog_build_items SET content_phase = 'raw_candidate' "
                "WHERE id = 'dispatch-item'"
            )
            with self.assertRaisesRegex(ValueError, "terminal provider dispatch"):
                self._begin(conn, phase="raw_candidate", phase_ordinal=2)
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'dispatch-item'"
            ).fetchone()

        self.assertEqual(replay["status"], "ambiguous")
        self.assertEqual(count["count"], 1)

    def test_completion_cas_rejects_late_item_lease_and_generation_identity(self):
        with self.database.transaction() as conn:
            row = self._begin(conn)
            conn.execute(
                "UPDATE learning_catalog_build_items SET content_lease_token = 'new-owner' "
                "WHERE id = 'dispatch-item'"
            )
            late = self.complete_provider_dispatch(
                conn,
                dispatch_id=row["id"],
                build_item_id="dispatch-item",
                generation_request_id="generation-request-1",
                item_lease_token="lease-token-1",
                outcome="succeeded",
                checkpoint={"ok": True},
                output_sha256=_checkpoint_sha256({"ok": True}),
                provider_request_id_hash=None,
                input_tokens=None,
                output_tokens=None,
                billing_evidence="unknown",
                safe_error_code=None,
                completed_at=1500,
            )
            wrong_generation = self.complete_provider_dispatch(
                conn,
                dispatch_id=row["id"],
                build_item_id="dispatch-item",
                generation_request_id="wrong-generation",
                item_lease_token="new-owner",
                outcome="succeeded",
                checkpoint={"ok": True},
                output_sha256=_checkpoint_sha256({"ok": True}),
                provider_request_id_hash=None,
                input_tokens=None,
                output_tokens=None,
                billing_evidence="unknown",
                safe_error_code=None,
                completed_at=1500,
            )
            conn.execute(
                "UPDATE learning_catalog_build_items "
                "SET content_lease_token = 'lease-token-1', "
                "content_provider_attempt_hard_deadline_at = 1860001 "
                "WHERE id = 'dispatch-item'"
            )
            deadline_drift = self.complete_provider_dispatch(
                conn,
                dispatch_id=row["id"],
                build_item_id="dispatch-item",
                generation_request_id="generation-request-1",
                item_lease_token="lease-token-1",
                outcome="succeeded",
                checkpoint={"ok": True},
                output_sha256=_checkpoint_sha256({"ok": True}),
                provider_request_id_hash=None,
                input_tokens=None,
                output_tokens=None,
                billing_evidence="unknown",
                safe_error_code=None,
                completed_at=1500,
            )
            persisted = conn.execute(
                "SELECT status, completed_at FROM learning_course_provider_dispatches "
                "WHERE id = ?",
                (row["id"],),
            ).fetchone()

        self.assertFalse(late)
        self.assertFalse(wrong_generation)
        self.assertFalse(deadline_drift)
        self.assertEqual(persisted["status"], "dispatched")
        self.assertIsNone(persisted["completed_at"])

    def _begin(self, conn, **overrides):
        values = {
            "build_item_id": "dispatch-item",
            "logical_attempt": 1,
            "phase": "outline",
            "phase_ordinal": 1,
            "generation_request_id": "generation-request-1",
            "item_lease_token": "lease-token-1",
            "provider": "kimi",
            "model": "kimi-k2.6",
            "profile": "question-generator-v2",
            "input_sha256": "a" * 64,
            "attempt_started_at": 1000,
            "attempt_hard_deadline_at": 31 * 60 * 1000,
            "dispatched_at": 1100,
        }
        values.update(overrides)
        return self.begin_provider_dispatch(conn, **values)

    def _insert_active_content_item(self) -> None:
        canary = json.dumps(
            {"version": "mira.learning.primary-1-canary.v1", "targets": []},
            separators=(",", ":"),
        )
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO learning_catalog_releases("
                "id, curriculum_version, title, status, quality_status, "
                "required_boundary_count, ready_item_count, created_at, updated_at) "
                "VALUES ('dispatch-release', 'primary-cn-2026.1', 'Dispatch', 'draft', "
                "'building', 1, 0, 1, 1)"
            )
            conn.execute(
                "INSERT INTO learning_catalog_build_jobs("
                "id, request_id, release_id, curriculum_version, status, target_spec_json, "
                "total_item_count, ready_item_count, failed_item_count, execution_mode, "
                "content_manifest_version, canary_manifest_json, stage_ceiling, "
                "created_at, updated_at) VALUES ("
                "'dispatch-build', 'dispatch-build-request', 'dispatch-release', "
                "'primary-cn-2026.1', 'running', '{}', 1, 0, 0, 'content_only', ?, ?, "
                "'content_ready', 1, 1)",
                (TARGET_SCHEMA_V2, canary),
            )
            conn.execute(
                """
                INSERT INTO learning_catalog_build_items(
                  id, build_job_id, release_id, grade_code, subject, skill_id,
                  curriculum_version, boundary_version, variant_ordinal, status,
                  attempt_count, package_attempt_count, claim_origin_status,
                  generation_request_id, active_generation_request_id,
                  execution_mode_snapshot, content_manifest_version_snapshot,
                  subject_ordinal, boundary_ordinal, content_phase,
                  content_gate_status, content_gate_attempt_count,
                  content_lease_token, content_lease_expires_at,
                  content_heartbeat_at, content_attempt_started_at,
                  content_provider_attempt_hard_deadline_at,
                  content_work_unit_deadline_at, content_claim_attempt_ordinal,
                  created_at, updated_at
                ) VALUES (
                  'dispatch-item', 'dispatch-build', 'dispatch-release', 'primary_1',
                  'math', 'number_sense_20', 'primary-cn-2026.1', 'boundary-v1', 1,
                  'processing', 1, 0, 'pending', 'generation-request-1',
                  'generation-request-1', 'content_only', ?, 1, 1, 'outline',
                  'not_started', 0, 'lease-token-1', 2000, 1000, 1000,
                  1860000, 120000, 1, 1, 1
                )
                """,
                (TARGET_SCHEMA_V2,),
            )


if __name__ == "__main__":
    unittest.main()
