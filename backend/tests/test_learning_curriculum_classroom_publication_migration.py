from __future__ import annotations

import unittest
from pathlib import Path

import pymysql

from core.database import Database
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from scripts.migrate import run_migrations
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from tests.support import fresh_test_config


MIGRATION_VERSION = "057_learning_curriculum_classroom_publication.sql"


class LearningCurriculumClassroomPublicationMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)

    def test_057_registers_the_grade_publication_contract(self) -> None:
        with self.database.transaction() as conn:
            marker = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            ).fetchone()
            tables = {
                row["TABLE_NAME"]
                for row in conn.execute(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                ).fetchall()
            }
            runtime_columns = {
                row["COLUMN_NAME"]
                for row in conn.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'"
                ).fetchall()
            }
            plan_columns = {
                row["COLUMN_NAME"]
                for row in conn.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = 'learning_curriculum_preparation_plans'"
                ).fetchall()
            }

        self.assertEqual(marker["count"], 1)
        self.assertTrue(
            {
                "learning_curriculum_grade_release_history",
                "learning_curriculum_grade_release_pointers",
                "learning_curriculum_classroom_item_receipts",
            }.issubset(tables)
        )
        self.assertTrue(
            {
                "candidate_build_item_id",
                "candidate_release_id",
                "candidate_grade_code",
                "candidate_target_fingerprint",
                "candidate_binding_contract_version",
                "candidate_bound_at",
            }.issubset(runtime_columns)
        )
        self.assertTrue(
            {
                "classroom_ready_count",
                "speech_ready_count",
                "validation_ready_count",
                "published_course_count",
                "formal_contract_version",
                "formal_publication_history_id",
                "formal_publication_receipt_hash",
                "formal_ready_at",
            }.issubset(plan_columns)
        )

    def test_057_replays_twice_and_repairs_a_missing_pointer_table(self) -> None:
        for _ in range(2):
            with self.database.transaction() as conn:
                conn.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    (MIGRATION_VERSION,),
                )
            run_migrations(self.database_url, verbose=False)
        with self.database.transaction() as conn:
            conn.execute(
                "ALTER TABLE learning_curriculum_classroom_item_receipts "
                "DROP CHECK chk_learning_classroom_receipt_timeline"
            )
            conn.execute(
                "ALTER TABLE learning_curriculum_grade_release_history "
                "DROP FOREIGN KEY "
                "fk_learning_grade_release_history_previous_exact"
            )
            conn.execute(
                "ALTER TABLE learning_curriculum_grade_release_history "
                "DROP INDEX uq_learning_grade_release_history_previous_exact"
            )
            conn.execute(
                "ALTER TABLE learning_curriculum_preparation_plans "
                "DROP FOREIGN KEY fk_learning_prep_formal_history_exact"
            )
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            )
        run_migrations(self.database_url, verbose=False)
        with self.database.transaction() as conn:
            conn.execute("DROP TABLE learning_curriculum_grade_release_pointers")
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
            pointer_table = conn.execute(
                "SELECT COUNT(*) AS count FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = "
                "'learning_curriculum_grade_release_pointers'"
            ).fetchone()
            checks = {
                row["CONSTRAINT_NAME"]
                for row in conn.execute(
                    "SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'CHECK'"
                ).fetchall()
            }
            constraints = {
                row["CONSTRAINT_NAME"]
                for row in conn.execute(
                    "SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                ).fetchall()
            }
            indexes = {
                row["INDEX_NAME"]
                for row in conn.execute(
                    "SELECT DISTINCT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                ).fetchall()
            }
        self.assertEqual(marker["count"], 1)
        self.assertEqual(pointer_table["count"], 1)
        self.assertIn("chk_learning_prep_formal_state_evidence", checks)
        self.assertNotIn("chk_learning_prep_content_state_evidence", checks)
        self.assertIn("chk_learning_openmaic_runtime_candidate_attempt", checks)
        self.assertTrue(
            {
                "chk_learning_classroom_receipt_timeline",
                "fk_learning_grade_release_history_previous_exact",
                "fk_learning_prep_formal_history_exact",
            }.issubset(constraints)
        )
        self.assertIn(
            "uq_learning_grade_release_history_previous_exact", indexes
        )

    def test_057_legacy_active_release_backfills_each_distinct_grade(self) -> None:
        with self.database.transaction() as conn:
            conn.execute("DELETE FROM learning_curriculum_grade_release_pointers")
            conn.execute("DELETE FROM learning_curriculum_grade_release_history")
            self._insert_legacy_release_item(conn, grade_code="primary_1", ordinal=1)
            self._insert_legacy_release_item(conn, grade_code="primary_2", ordinal=2)
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            )
        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)

        with self.database.transaction() as conn:
            pointers = conn.execute(
                "SELECT grade_code, pointer_revision, release_id, contract_version "
                "FROM learning_curriculum_grade_release_pointers "
                "ORDER BY grade_code"
            ).fetchall()
            history = conn.execute(
                "SELECT grade_code, pointer_revision, release_id, activation_source "
                "FROM learning_curriculum_grade_release_history "
                "ORDER BY grade_code"
            ).fetchall()
        self.assertEqual(
            [
                (
                    row["grade_code"],
                    row["pointer_revision"],
                    row["release_id"],
                    row["contract_version"],
                )
                for row in pointers
            ],
            [
                (
                    "primary_1",
                    1,
                    "legacy-multi-grade-release",
                    "mira.learning.grade-release-pointer.legacy.v1",
                ),
                (
                    "primary_2",
                    1,
                    "legacy-multi-grade-release",
                    "mira.learning.grade-release-pointer.legacy.v1",
                ),
            ],
        )
        self.assertEqual(
            [
                (
                    row["grade_code"],
                    row["pointer_revision"],
                    row["release_id"],
                    row["activation_source"],
                )
                for row in history
            ],
            [
                ("primary_1", 1, "legacy-multi-grade-release", "legacy_backfill"),
                ("primary_2", 1, "legacy-multi-grade-release", "legacy_backfill"),
            ],
        )

    def test_nullable_pointer_history_and_formal_ready_evidence_fail_closed(self) -> None:
        repository = LearningCurriculumPreparationRepository(self.database)
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO learning_curriculum_grade_release_pointers("
                "grade_code, pointer_revision, updated_at) VALUES ('primary_1', 0, 1)"
            )
            conn.execute(
                "INSERT INTO learning_catalog_releases("
                "id, curriculum_version, title, status, quality_status, "
                "required_boundary_count, ready_item_count, created_at, updated_at) "
                "VALUES ('nullable-release', 'primary-cn-2026.1', 'Nullable', "
                "'draft', 'building', 0, 0, 1, 1)"
            )
            conn.execute(
                "INSERT INTO families(id, name, created_at) "
                "VALUES ('nullable-family', 'Nullable', 1)"
            )
            conn.execute(
                "INSERT INTO children(id, family_id, name, created_at, updated_at) "
                "VALUES ('nullable-child', 'nullable-family', 'Child', 1, 1)"
            )
            plan, _ = repository.reserve_plan(
                conn,
                family_id="nullable-family",
                child_id="nullable-child",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=target,
                target_fingerprint=fingerprint,
                request_id="nullable-plan",
                shared_build_request_id=f"grade-build:{fingerprint}",
                now=1,
            )

        invalid_statements = (
            "UPDATE learning_curriculum_grade_release_pointers "
            "SET target_fingerprint = REPEAT('a', 64) WHERE grade_code = 'primary_1'",
            "INSERT INTO learning_curriculum_grade_release_history("
            "id, grade_code, pointer_revision, target_fingerprint, contract_version, "
            "release_id, activation_source, publication_request_id, "
            "publication_receipt_hash, activated_at, created_at) VALUES ("
            "'nullable-history', 'primary_1', 1, REPEAT('a', 64), "
            "'mira.learning.formal-publication.v1', 'nullable-release', "
            "'formal_publication', 'nullable-request', NULL, 1, 1)",
            "UPDATE learning_curriculum_preparation_plans "
            "SET status = 'ready', stage = 'completed', progress_percent = 100, "
            "ready_course_count = total_course_count, completed_at = 2, "
            "next_run_at = NULL WHERE id = '" + str(plan["id"]) + "'",
        )
        for statement in invalid_statements:
            with self.subTest(statement=statement[:80]):
                with self.assertRaises(pymysql.MySQLError) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(statement)
                self.assertEqual(raised.exception.args[0], 3819)

    def test_history_previous_chain_rejects_cross_grade_authority(self) -> None:
        with self.database.transaction() as conn:
            conn.execute("DELETE FROM learning_curriculum_grade_release_pointers")
            conn.execute("DELETE FROM learning_curriculum_grade_release_history")
            self._insert_legacy_release_item(conn, grade_code="primary_1", ordinal=1)
            self._insert_legacy_release_item(conn, grade_code="primary_2", ordinal=2)
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            )
        run_migrations(self.database_url, verbose=False)
        with self.database.transaction() as conn:
            previous = conn.execute(
                "SELECT id, release_id FROM learning_curriculum_grade_release_history "
                "WHERE grade_code = 'primary_2'"
            ).fetchone()
            conn.execute(
                "INSERT INTO learning_catalog_releases("
                "id, curriculum_version, title, status, quality_status, "
                "required_boundary_count, ready_item_count, created_at, updated_at) "
                "VALUES ('cross-grade-successor', 'primary-cn-2026.1', "
                "'Cross grade', 'draft', 'building', 0, 0, 200, 200)"
            )
        with self.assertRaises(pymysql.MySQLError) as raised:
            with self.database.transaction() as conn:
                conn.execute(
                    "INSERT INTO learning_curriculum_grade_release_history("
                    "id, grade_code, pointer_revision, target_fingerprint, "
                    "contract_version, release_id, previous_history_id, "
                    "previous_release_id, activation_source, activated_at, "
                    "created_at) VALUES ('cross-grade-history', 'primary_1', 2, "
                    "REPEAT('a', 64), 'mira.learning.grade-release-pointer.legacy.v1', "
                    "'cross-grade-successor', ?, ?, 'legacy_backfill', 200, 200)",
                    (previous["id"], previous["release_id"]),
                )
        self.assertEqual(raised.exception.args[0], 1452)

    def test_legacy_same_grade_history_backfills_parent_before_successor(self) -> None:
        migration = Path(__file__).resolve().parents[1] / "migrations" / MIGRATION_VERSION
        self.assertIn(
            "ORDER BY ranked.grade_code, ranked.pointer_revision",
            migration.read_text(encoding="utf-8"),
        )
        with self.database.transaction() as conn:
            conn.execute("DELETE FROM learning_curriculum_grade_release_pointers")
            conn.execute("DELETE FROM learning_curriculum_grade_release_history")
            self._insert_legacy_release_item(
                conn,
                grade_code="primary_1",
                ordinal=12,
                release_id="z-release",
                activated_at=100,
            )
            self._insert_legacy_release_item(
                conn,
                grade_code="primary_1",
                ordinal=11,
                release_id="a-release",
                activated_at=100,
            )
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            )
        run_migrations(self.database_url, verbose=False)
        run_migrations(self.database_url, verbose=False)
        with self.database.transaction() as conn:
            history = conn.execute(
                "SELECT * FROM learning_curriculum_grade_release_history "
                "WHERE grade_code = 'primary_1' ORDER BY pointer_revision"
            ).fetchall()
            pointer = conn.execute(
                "SELECT * FROM learning_curriculum_grade_release_pointers "
                "WHERE grade_code = 'primary_1'"
            ).fetchone()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["pointer_revision"], 1)
        self.assertEqual(history[0]["release_id"], "a-release")
        self.assertEqual(history[0]["superseded_at"], 100)
        self.assertEqual(history[1]["pointer_revision"], 2)
        self.assertEqual(history[1]["release_id"], "z-release")
        self.assertEqual(history[1]["previous_history_id"], history[0]["id"])
        self.assertEqual(
            history[1]["previous_release_id"], history[0]["release_id"]
        )
        self.assertIsNone(history[1]["superseded_at"])
        self.assertEqual(pointer["pointer_revision"], 2)
        self.assertEqual(pointer["history_id"], history[1]["id"])

    @staticmethod
    def _insert_legacy_release_item(
        conn,
        *,
        grade_code: str,
        ordinal: int,
        release_id: str = "legacy-multi-grade-release",
        activated_at: int = 100,
    ) -> None:
        course_id = f"legacy-{grade_code}-{ordinal}-course"
        package_id = f"legacy-{grade_code}-{ordinal}-package"
        job_id = f"legacy-{grade_code}-{ordinal}-job"
        artifact_id = f"legacy-{grade_code}-{ordinal}-artifact"
        conn.execute(
            "INSERT IGNORE INTO learning_catalog_releases("
            "id, curriculum_version, title, status, quality_status, "
            "required_boundary_count, ready_item_count, activated_at, "
            "created_at, updated_at) VALUES (?, 'primary-cn-2026.1', "
            "'Legacy multi grade', 'active', 'ready', 1, 1, ?, 10, ?)",
            (release_id, activated_at, activated_at),
        )
        conn.execute(
            "INSERT INTO learning_courses("
            "id, version, grade_code, subject, node_code, curriculum_version, "
            "boundary_version, title, objective, status, quality_status, "
            "content_json, published_at, created_at, updated_at) VALUES ("
            "?, '1', ?, 'math', ?, 'primary-cn-2026.1', ?, ?, 'Objective', "
            "'published', 'released', '{}', 100, 1, 100)",
            (
                course_id,
                grade_code,
                f"legacy_skill_{ordinal}",
                f"legacy-boundary-{ordinal}",
                f"Legacy {grade_code}",
            ),
        )
        conn.execute(
            "INSERT INTO learning_classroom_generation_jobs("
            "id, request_id, course_id, course_version, generator, status, "
            "created_at, updated_at) VALUES (?, ?, ?, '1', 'legacy', "
            "'completed', 1, 1)",
            (job_id, f"request-{job_id}", course_id),
        )
        conn.execute(
            "INSERT INTO learning_classroom_source_artifacts("
            "id, job_id, request_id, source_format, dsl_version, status, "
            "source_hash, payload_json, created_at, updated_at) VALUES ("
            "?, ?, ?, 'json', 'v1', 'validated', ?, '{}', 1, 1)",
            (artifact_id, job_id, f"request-{artifact_id}", f"{ordinal:064x}"),
        )
        conn.execute(
            "INSERT INTO learning_lesson_packages("
            "id, version, course_id, course_version, schema_version, status, "
            "source_artifact_id, compiler_version, public_content_hash, "
            "private_content_hash, public_payload_json, validation_report_json, "
            "created_at, published_at, updated_at) VALUES ("
            "?, 1, ?, '1', 'v1', 'published', ?, 'v1', ?, ?, '{}', '{}', "
            "1, 100, 100)",
            (
                package_id,
                course_id,
                artifact_id,
                f"{ordinal + 10:064x}",
                f"{ordinal + 20:064x}",
            ),
        )
        conn.execute(
            "INSERT INTO learning_catalog_release_items("
            "release_id, course_id, course_version, grade_code, subject, "
            "skill_id, curriculum_version, boundary_version, variant_ordinal, "
            "package_id, package_version, status, quality_status, published_at, "
            "created_at, updated_at) VALUES (?, ?, '1', ?, 'math', ?, "
            "'primary-cn-2026.1', ?, 1, ?, 1, 'published', 'ready', 100, 1, 100)",
            (
                release_id,
                course_id,
                grade_code,
                f"legacy_skill_{ordinal}",
                f"legacy-boundary-{ordinal}",
                package_id,
            ),
        )


if __name__ == "__main__":
    unittest.main()
