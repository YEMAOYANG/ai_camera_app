from __future__ import annotations

import inspect
import sqlite3
import unittest

from repositories.learning_repository import (
    LearningRepository,
    _student_required_package_assets_sql,
    _student_visible_course_sql,
)
from repositories.formal_student_runtime_gate import current_formal_runtime_sql
from repositories.lesson_package_repository import LessonPackageRepository
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from repositories.student_learning_library_repository import (
    _classroom_availability_sql,
)
from services.formal_student_learning_access import (
    _load_active_formal_student_release,
)


class FormalStudentCatalogVisibilityContractTest(unittest.TestCase):
    def test_current_runtime_gate_requires_openmaic_one_professional_search_receipts(self):
        sql = " ".join(
            current_formal_runtime_sql(runtime_alias="runtime").lower().split()
        )

        self.assertIn("openmaic@1.0.0", sql)
        self.assertIn(
            "mira.openmaic.formal-runtime.v4-deepseek-professional",
            sql,
        )
        self.assertIn("courseware-authority.v2-professional", sql)
        self.assertIn("professional-creation-receipt.v1", sql)
        self.assertIn("professional-research-receipt.v1", sql)
        self.assertIn("professionalcreation.websearchenabled", sql)
        self.assertIn("generation.enablewebsearch", sql)
        self.assertIn("research.providerid", sql)
        self.assertIn(
            "'$.research.providerid' )) regexp '^[a-za-z0-9_-]{1,64}$'", sql
        )
        self.assertIn("formalevidence.research.providerid", sql)

    def test_today_and_assignment_accept_exact_grade_pointer_publication(self):
        joins = LearningRepository._catalog_release_joins().lower()
        filters = LearningRepository._catalog_release_filters().lower()

        self.assertIn("learning_curriculum_grade_release_pointers", joins)
        self.assertIn("learning_curriculum_classroom_item_receipts", filters)
        self.assertIn("learning_formal_qwen_audio_jobs", filters)
        self.assertIn("learning_openmaic_provider_readiness_jobs", filters)
        self.assertIn("formal-publication.v1", filters)
        self.assertIn("catalog_release.status = 'active'", filters)

    def test_library_formal_classroom_uses_machine_evidence_not_human_review(self):
        sql = _classroom_availability_sql(require_full_runtime=True).lower()

        self.assertIn("learning_curriculum_grade_release_pointers", sql)
        self.assertIn("learning_curriculum_classroom_item_receipts", sql)
        self.assertIn("learning_formal_qwen_audio_jobs", sql)
        self.assertIn("learning_openmaic_provider_readiness_jobs", sql)
        self.assertIn("runtime.quality_status = 'approved'", sql)
        self.assertIn("formal_audio.state = 'auto_validated'", sql)
        self.assertIn("formal_provider.state = 'auto_validated'", sql)

    def test_in_progress_library_session_can_resume_its_historical_binding(self):
        sql = _classroom_availability_sql(require_full_runtime=True).lower()

        self.assertIn("learning_student_formal_session_bindings", sql)
        self.assertIn("session.status <> 'completed'", sql)
        self.assertIn("session_binding.release_id = catalog_release.id", sql)
        self.assertIn(
            "session_binding.runtime_classroom_id = runtime.id",
            sql,
        )

    def test_formal_catalog_gate_is_shared_by_library_and_course_detail(self):
        source = inspect.getsource(
            __import__(
                "repositories.student_learning_library_repository",
                fromlist=["StudentLearningLibraryRepository"],
            ).StudentLearningLibraryRepository
        )
        self.assertGreaterEqual(source.count("_FULL_CLASSROOM_AVAILABILITY_SQL"), 2)

    def test_progressive_slots_overlay_active_fallback_only_with_full_evidence(self):
        sql = " ".join(_student_visible_course_sql().lower().split())

        self.assertEqual(sql.count("?"), 6)
        self.assertIn(
            "overlay_item.boundary_version = student_release_item.boundary_version",
            sql,
        )
        self.assertIn(
            "overlay_item.variant_ordinal = student_release_item.variant_ordinal",
            sql,
        )
        self.assertIn("and not exists", sql)
        self.assertIn("overlay_receipt.publication_status = 'published'", sql)
        self.assertIn("overlay_runtime.status = 'ready'", sql)
        self.assertIn("overlay_audio.state = 'auto_validated'", sql)
        self.assertIn("overlay_provider.state = 'auto_validated'", sql)
        self.assertIn("overlay_build_item.status = 'course_ready'", sql)
        self.assertIn("overlay_build_item.content_phase = 'course_ready'", sql)
        self.assertIn("overlay_build_item.content_gate_status = 'passed'", sql)
        self.assertIn(
            "overlay_provider.release_id = overlay_item.release_id",
            sql,
        )
        self.assertNotIn("overlay_provider.build_item_id", sql)
        self.assertNotIn("overlay_provider.runtime_classroom_id", sql)
        self.assertIn("overlay_runtime.feature_manifest_json", sql)
        self.assertIn("openmaic@1.0.0", sql)
        self.assertIn("formal-runtime.v4-deepseek-professional", sql)

    def test_active_fallback_accepts_content_ready_build_with_release_provider(self):
        sql = " ".join(_student_visible_course_sql().lower().split())

        self.assertIn("student_build_item.status = 'course_ready'", sql)
        self.assertIn("student_build_item.execution_mode_snapshot = 'content_only'", sql)
        self.assertIn("student_build_item.content_phase = 'course_ready'", sql)
        self.assertIn("student_build_item.content_gate_status = 'passed'", sql)
        self.assertIn("student_build_item.content_gate_passed_at is not null", sql)
        self.assertIn(
            "student_build_item.content_receipt_hash regexp '^[0-9a-f]{64}$'",
            sql,
        )
        self.assertIn(
            "student_provider.release_id = student_release_item.release_id",
            sql,
        )
        self.assertNotIn("student_provider.build_item_id", sql)
        self.assertNotIn("student_provider.runtime_classroom_id", sql)
        self.assertIn("student_runtime.feature_manifest_json", sql)
        self.assertIn("openmaic@1.0.0", sql)

    def test_correlated_visibility_preserves_both_child_plan_scopes(self):
        original = " ".join(_student_visible_course_sql().split())
        correlated = " ".join(
            _student_visible_course_sql(child_alias="current_child").split()
        )

        self.assertEqual(original.count("?"), 6)
        self.assertNotIn("?", correlated)
        for plan in ("student_plan", "overlay_plan"):
            for field, column in (
                ("family_id", "family_id"),
                ("child_id", "id"),
                ("grade_selection_revision", "grade_selection_revision"),
            ):
                correlated = correlated.replace(
                    f"{plan}.{field} = current_child.{column}",
                    f"{plan}.{field} = ?",
                )
        self.assertEqual(correlated, original)
        self.assertNotIn("learning_lesson_package_assets", original)

    def test_child_and_package_aliases_reject_sql_expressions(self):
        for alias in ("", "task.child", "x y", "x; SELECT 1", "x--", "1child", [], 1):
            with self.subTest(alias=alias):
                with self.assertRaises(ValueError):
                    _student_visible_course_sql(child_alias=alias)
                with self.assertRaises(ValueError):
                    _student_required_package_assets_sql(package_alias=alias)

    def test_new_task_availability_reuses_exact_scoped_catalog_and_asset_gate(self):
        shared = " ".join(
            _student_visible_course_sql(
                child_alias="availability_child",
                require_available_package_assets=True,
            ).split()
        )
        for require_full in (False, True):
            with self.subTest(require_full_runtime=require_full):
                sql = " ".join(
                    _classroom_availability_sql(
                        require_full_runtime=require_full
                    ).split()
                )
                self.assertNotIn("?", sql)
                self.assertIn(shared, sql)
                for scope in (
                    "FROM children AS availability_child WHERE session.id IS NULL",
                    "availability_child.family_id = task.family_id",
                    "availability_child.id = task.child_id",
                    "availability_child.grade_code = course.grade_code",
                    "availability_child.grade_selection_revision >= 1",
                    "course.status = 'published'",
                    "course.quality_status = 'released'",
                    "course.content_origin = 'openmaic_generated'",
                    "course.retired_at IS NULL",
                ):
                    self.assertIn(scope, sql)
                for package in ("package", "student_package"):
                    self.assertIn(
                        " ".join(
                            _student_required_package_assets_sql(
                                package_alias=package
                            ).split()
                        ),
                        sql,
                    )

    def test_required_package_assets_reject_unavailable_media(self):
        fixture = """
            CREATE TABLE package (id TEXT, version INTEGER);
            CREATE TABLE learning_lesson_package_assets (
              package_id TEXT, package_version INTEGER, asset_id TEXT,
              required_asset INTEGER
            );
            CREATE TABLE learning_media_assets (
              id TEXT, status TEXT, scan_status TEXT, moderation_status TEXT,
              transcode_status TEXT
            );
            CREATE TABLE learning_media_asset_variants (asset_id TEXT, status TEXT);
            CREATE TABLE learning_media_quality_reviews (
              asset_id TEXT, required_review INTEGER, status TEXT
            );
            INSERT INTO package VALUES ('selected', 1);
            INSERT INTO learning_lesson_package_assets VALUES ('selected', 1, 'a', 1);
            INSERT INTO learning_media_assets VALUES ('a', 'ready', 'passed', 'passed', 'passed');
            INSERT INTO learning_media_asset_variants VALUES ('a', 'ready');
            INSERT INTO learning_media_quality_reviews VALUES ('a', 1, 'approved');
        """
        cases = (
            ("all_ready", "", True),
            ("missing_asset", "DELETE FROM learning_media_assets", False),
            ("failed_asset", "UPDATE learning_media_assets SET status = 'failed'", False),
            ("failed_scan", "UPDATE learning_media_assets SET scan_status = 'failed'", False),
            ("missing_scan", "UPDATE learning_media_assets SET scan_status = NULL", False),
            ("failed_moderation", "UPDATE learning_media_assets SET moderation_status = 'failed'", False),
            ("failed_transcode", "UPDATE learning_media_assets SET transcode_status = 'failed'", False),
            ("missing_variant", "DELETE FROM learning_media_asset_variants", False),
            ("missing_review", "DELETE FROM learning_media_quality_reviews", False),
            ("failed_review", "INSERT INTO learning_media_quality_reviews VALUES ('a', 1, 'rejected')", False),
            ("other_package_review", "UPDATE learning_media_quality_reviews SET asset_id = 'other'", False),
            ("optional_missing_asset", "INSERT INTO learning_lesson_package_assets VALUES ('selected', 1, 'missing', 0)", True),
            ("other_package_missing_asset", "INSERT INTO learning_lesson_package_assets VALUES ('other', 1, 'missing', 1)", True),
            ("other_version_missing_asset", "INSERT INTO learning_lesson_package_assets VALUES ('selected', 2, 'missing', 1)", True),
        )
        for name, mutation, expected in cases:
            with self.subTest(case=name):
                conn = sqlite3.connect(":memory:")
                try:
                    conn.executescript(fixture)
                    if mutation:
                        conn.execute(mutation)
                    available = conn.execute(
                        "SELECT " + _student_required_package_assets_sql(
                            package_alias="package"
                        ) + " FROM package"
                    ).fetchone()[0]
                    self.assertEqual(bool(available), expected)
                finally:
                    conn.close()

    def test_package_and_session_binding_share_current_runtime_gate(self):
        package_source = inspect.getsource(
            LessonPackageRepository.get_active_formal_package
        )
        binding_source = inspect.getsource(
            OpenMaicRuntimeRepository.bind_formal_session_to_active_release
        )

        self.assertEqual(package_source.count("current_formal_runtime_sql"), 2)
        self.assertEqual(binding_source.count("current_formal_runtime_sql"), 2)

    def test_formal_generation_claim_requires_the_deepseek_pro_circuit(self):
        source = inspect.getsource(
            LessonPackageRepository.get_next_formal_candidate_authority
        )

        self.assertIn(
            "formal-generation:deepseek:deepseek-v4-pro",
            source,
        )
        self.assertIn("provider_circuit.provider_id = 'deepseek'", source)
        self.assertIn(
            "provider_circuit.model_id = 'deepseek-v4-pro'",
            source,
        )
        self.assertEqual(
            OpenMaicRuntimeRepository.FORMAL_PROVIDER_CIRCUIT_KEY,
            "formal-generation:deepseek:deepseek-v4-pro",
        )
        self.assertEqual(
            OpenMaicRuntimeRepository.FORMAL_PROVIDER_ID,
            "deepseek",
        )
        self.assertEqual(
            OpenMaicRuntimeRepository.FORMAL_PROVIDER_MODEL_ID,
            "deepseek-v4-pro",
        )

    def test_library_full_classroom_uses_current_runtime_gate(self):
        sql = " ".join(
            _classroom_availability_sql(require_full_runtime=True)
            .lower()
            .split()
        )

        self.assertIn("openmaic@1.0.0", sql)
        self.assertIn("formal-runtime.v4-deepseek-professional", sql)
        self.assertIn("professionalcreation.websearchenabled", sql)

    def test_active_release_availability_rejects_legacy_runtime_contract(self):
        source = inspect.getsource(_load_active_formal_student_release)

        self.assertIn("current_formal_runtime_sql", source)
        self.assertIn("current_release_item", source)


if __name__ == "__main__":
    unittest.main()
