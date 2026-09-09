from __future__ import annotations

import re
import unittest
from pathlib import Path

from core.database import _split_sql_script


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "060_learning_student_formal_session_bindings.sql"
CONTRACT_SPLIT_MIGRATION = (
    ROOT
    / "migrations"
    / "066_learning_student_formal_session_binding_contract_split.sql"
)
BUILD_PACKAGE_SPLIT_MIGRATION = (
    ROOT
    / "migrations"
    / "067_learning_student_formal_session_binding_build_package_split.sql"
)
PROGRESSIVE_AUTHORITY_MIGRATION = (
    ROOT
    / "migrations"
    / "070_learning_student_progressive_session_authority.sql"
)


class LearningStudentFormalSessionBindingsMigrationTest(unittest.TestCase):
    def _sql(self) -> tuple[str, str]:
        self.assertTrue(
            MIGRATION.exists(),
            "060 must add the immutable formal student session binding",
        )
        sql = MIGRATION.read_text(encoding="utf-8")
        return sql, re.sub(r"\s+", " ", sql).lower()

    def test_binding_freezes_the_complete_formal_identity_per_session(self) -> None:
        sql, normalized = self._sql()
        self.assertGreaterEqual(len(_split_sql_script(sql)), 2)
        self.assertIn(
            "create table if not exists learning_student_formal_session_bindings",
            normalized,
        )
        required_columns = (
            "learning_session_id varchar(255) primary key",
            "family_id varchar(255) not null",
            "child_id varchar(255) not null",
            "grade_code varchar(64) not null",
            "pointer_history_id varchar(128) not null",
            "pointer_revision integer not null",
            "release_id varchar(128) not null",
            "target_fingerprint char(64) not null",
            "publication_contract_version varchar(128) not null",
            "build_item_id varchar(128) not null",
            "course_id varchar(255) not null",
            "course_version varchar(64) not null",
            "package_id varchar(128) not null",
            "package_version integer not null",
            "package_content_hash char(64) not null",
            "runtime_classroom_id varchar(128) not null",
            "upstream_classroom_id varchar(255) not null",
            "bound_at bigint not null",
            "created_at bigint not null",
        )
        for fragment in required_columns:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, normalized)
        self.assertIn(
            "alter table learning_sessions modify column family_id varchar(255) not null, modify column child_id varchar(255) not null",
            normalized,
        )

    def test_binding_uses_history_and_exact_source_authorities(self) -> None:
        _, normalized = self._sql()
        required_authorities = (
            "references learning_sessions",
            "references children",
            "references learning_curriculum_grade_release_history",
            "references learning_catalog_release_items",
            "references learning_catalog_build_items",
            "references learning_lesson_packages",
            "references learning_openmaic_runtime_classrooms",
            "references learning_curriculum_classroom_item_receipts",
        )
        for fragment in required_authorities:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, normalized)
        self.assertNotIn(
            "references learning_curriculum_grade_release_pointers", normalized
        )
        self.assertIn(
            "uq_learning_receipt_formal_binding", normalized
        )

    def test_binding_rejects_cross_child_and_cross_artifact_identity(self) -> None:
        _, normalized = self._sql()
        structure = re.sub(r"\s*([(),])\s*", r"\1", normalized)
        exact_foreign_keys = (
            "foreign key(learning_session_id,family_id,child_id)",
            "foreign key(family_id,child_id)",
            "foreign key(pointer_history_id,grade_code,pointer_revision,target_fingerprint,publication_contract_version,release_id)",
            "foreign key(release_id,grade_code,course_id,course_version,package_id,package_version)",
            "foreign key(build_item_id,release_id,grade_code)",
            "foreign key(build_item_id,course_id,course_version)",
            "foreign key(build_item_id,package_id,package_version)",
            "foreign key(package_id,package_version,course_id,course_version,package_content_hash)",
            "foreign key(runtime_classroom_id,build_item_id,release_id,grade_code,target_fingerprint,publication_contract_version)",
            "foreign key(runtime_classroom_id,upstream_classroom_id)",
            "foreign key(build_item_id,release_id,runtime_classroom_id)",
        )
        for fragment in exact_foreign_keys:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, structure)

    def test_binding_has_fail_closed_identity_and_timeline_checks(self) -> None:
        _, normalized = self._sql()
        for fragment in (
            "grade_code regexp '^primary_[1-6]$'",
            "pointer_revision >= 1",
            "target_fingerprint regexp '^[0-9a-f]{64}$'",
            "publication_contract_version = 'mira.learning.formal-publication.v1'",
            "package_content_hash regexp '^[0-9a-f]{64}$'",
            "package_version > 0",
            "bound_at > 0",
            "created_at = bound_at",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, normalized)

    def test_migration_does_not_relabel_legacy_sessions_from_current_pointer(self) -> None:
        _, normalized = self._sql()
        self.assertNotIn(
            "insert into learning_student_formal_session_bindings select", normalized
        )
        self.assertNotIn(
            "from learning_curriculum_grade_release_pointers", normalized
        )

    def test_contract_split_keeps_publication_and_runtime_authorities_separate(
        self,
    ) -> None:
        self.assertTrue(CONTRACT_SPLIT_MIGRATION.exists())
        sql = CONTRACT_SPLIT_MIGRATION.read_text(encoding="utf-8")
        normalized = re.sub(r"\s+", " ", sql).lower()
        structure = re.sub(r"\s*([(),])\s*", r"\1", normalized)

        self.assertIn(
            "add column runtime_binding_contract_version varchar(128) not null",
            normalized,
        )
        self.assertIn(
            "foreign key(runtime_classroom_id,build_item_id,release_id,grade_code,target_fingerprint,runtime_binding_contract_version)",
            structure,
        )
        self.assertIn(
            "drop index fk_lsfsb_runtime_candidate",
            normalized,
        )
        self.assertNotIn(
            "foreign key(runtime_classroom_id,build_item_id,release_id,grade_code,target_fingerprint,publication_contract_version) references",
            structure.split("add constraint fk_lsfsb_runtime_candidate")[-1],
        )
        self.assertIn(
            "runtime_binding_contract_version = ''mira.learning.candidate-runtime-binding.v1''",
            normalized,
        )
        self.assertIn(
            "alter column runtime_binding_contract_version drop default",
            normalized,
        )

    def test_build_package_split_removes_only_the_invalid_build_package_link(
        self,
    ) -> None:
        self.assertTrue(BUILD_PACKAGE_SPLIT_MIGRATION.exists())
        sql = BUILD_PACKAGE_SPLIT_MIGRATION.read_text(encoding="utf-8")
        normalized = re.sub(r"\s+", " ", sql).lower()

        self.assertIn("drop foreign key fk_lsfsb_build_package", normalized)
        self.assertIn("drop index fk_lsfsb_build_package", normalized)
        self.assertIn("067 schema verification failed", normalized)
        self.assertNotIn("update learning_catalog_build_items", normalized)
        self.assertNotIn("insert into learning_catalog_build_items", normalized)
        self.assertNotIn("delete from learning_catalog_build_items", normalized)

    def test_progressive_authority_uses_a_real_plan_without_fabricating_history(
        self,
    ) -> None:
        self.assertTrue(PROGRESSIVE_AUTHORITY_MIGRATION.exists())
        sql = PROGRESSIVE_AUTHORITY_MIGRATION.read_text(encoding="utf-8")
        normalized = re.sub(r"\s+", " ", sql).lower()
        structure = re.sub(r"\s*([(),])\s*", r"\1", normalized)

        self.assertIn("authority_kind varchar(32) not null", normalized)
        self.assertIn("preparation_plan_id varchar(128) null", normalized)
        self.assertIn("grade_selection_revision integer null", normalized)
        self.assertIn(
            "foreign key(preparation_plan_id)references learning_curriculum_preparation_plans(id)",
            structure,
        )
        self.assertIn(
            "authority_kind = 'progressive_plan' and pointer_history_id is null and pointer_revision is null",
            normalized,
        )
        self.assertIn(
            "authority_kind = 'active_pointer' and pointer_history_id is not null",
            normalized,
        )
        self.assertIn("bound_at > 0", normalized)
        self.assertIn("created_at = bound_at", normalized)
        self.assertNotIn(
            "insert into learning_curriculum_grade_release_history",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
