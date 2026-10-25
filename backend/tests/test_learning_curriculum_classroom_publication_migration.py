from __future__ import annotations

import unittest

import psycopg

from core.database import Database
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from tests.support import fresh_test_config


# The PostgreSQL baseline carries the grade publication contract that MySQL
# migration 057 introduced; its replay and backfill tests retired with MySQL.
BASELINE_VERSION = "100_postgres_baseline_schema.sql"


class LearningCurriculumClassroomPublicationMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/mira_test", self.database_url)
        self.assertNotRegex(self.database_url, r"/mira(\?|$)")
        self.database = Database(self.database_url)

    def test_baseline_registers_the_grade_publication_contract(self) -> None:
        with self.database.transaction() as conn:
            marker = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (BASELINE_VERSION,),
            ).fetchone()
            tables = {
                row["table_name"]
                for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = current_schema()"
                ).fetchall()
            }
            runtime_columns = self._columns(conn, "learning_openmaic_runtime_classrooms")
            plan_columns = self._columns(conn, "learning_curriculum_preparation_plans")

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

    def test_baseline_keeps_publication_checks_foreign_keys_and_indexes(self) -> None:
        with self.database.transaction() as conn:
            constraints = {
                (row["constraint_name"], row["constraint_type"])
                for row in conn.execute(
                    "SELECT constraint_name, constraint_type FROM information_schema.table_constraints "
                    "WHERE table_schema = current_schema()"
                ).fetchall()
            }
            indexes = {
                row["indexname"]
                for row in conn.execute(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
                ).fetchall()
            }
        checks = {name for name, kind in constraints if kind == "CHECK"}
        self.assertIn("chk_learning_prep_formal_state_evidence", checks)
        self.assertNotIn("chk_learning_prep_content_state_evidence", checks)
        self.assertIn("chk_learning_openmaic_runtime_candidate_attempt", checks)
        self.assertIn("chk_learning_classroom_receipt_timeline", checks)
        self.assertTrue(
            {
                ("fk_learning_grade_release_history_previous_exact", "FOREIGN KEY"),
                ("fk_learning_prep_formal_history_exact", "FOREIGN KEY"),
                ("uq_learning_grade_release_history_previous_exact", "UNIQUE"),
            }.issubset(constraints)
        )
        self.assertIn("uq_learning_grade_release_history_previous_exact", indexes)

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
                with self.assertRaises(psycopg.Error) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(statement)
                self.assertEqual(raised.exception.sqlstate, "23514")  # check_violation

    def test_history_previous_chain_rejects_cross_grade_authority(self) -> None:
        with self.database.transaction() as conn:
            conn.execute("DELETE FROM learning_curriculum_grade_release_pointers")
            conn.execute("DELETE FROM learning_curriculum_grade_release_history")
            for release_id in ("legacy-release", "cross-grade-successor"):
                conn.execute(
                    "INSERT INTO learning_catalog_releases("
                    "id, curriculum_version, title, status, quality_status, "
                    "required_boundary_count, ready_item_count, created_at, updated_at) "
                    "VALUES (?, 'primary-cn-2026.1', 'Cross grade', 'draft', 'building', "
                    "0, 0, 100, 100)",
                    (release_id,),
                )
            conn.execute(
                "INSERT INTO learning_curriculum_grade_release_history("
                "id, grade_code, pointer_revision, target_fingerprint, "
                "contract_version, release_id, activation_source, activated_at, "
                "created_at) VALUES ('primary-2-history', 'primary_2', 1, "
                "REPEAT('a', 64), 'mira.learning.grade-release-pointer.legacy.v1', "
                "'legacy-release', 'legacy_backfill', 100, 100)"
            )
        with self.assertRaises(psycopg.Error) as raised:
            with self.database.transaction() as conn:
                conn.execute(
                    "INSERT INTO learning_curriculum_grade_release_history("
                    "id, grade_code, pointer_revision, target_fingerprint, "
                    "contract_version, release_id, previous_history_id, "
                    "previous_release_id, activation_source, activated_at, "
                    "created_at) VALUES ('cross-grade-history', 'primary_1', 2, "
                    "REPEAT('a', 64), 'mira.learning.grade-release-pointer.legacy.v1', "
                    "'cross-grade-successor', 'primary-2-history', 'legacy-release', "
                    "'legacy_backfill', 200, 200)"
                )
        self.assertEqual(raised.exception.sqlstate, "23503")  # foreign_key_violation

    @staticmethod
    def _columns(conn, table: str) -> set[str]:
        return {
            row["column_name"]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = ?",
                (table,),
            ).fetchall()
        }


if __name__ == "__main__":
    unittest.main()
