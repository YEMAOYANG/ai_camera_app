from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
import hashlib
import json
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app
from core.database import Database
from core.security import now_ms
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)
from repositories.learning_repository import LearningRepository
from services.formal_student_learning_access import assert_formal_student_grade_open
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_daily_preparation_runner import LearningDailyPreparationRunner
from services.service_factory import learning_service
from tests.fixtures.primary_subject_catalog import PRIMARY_COURSE_CATALOG
from tests.support import fresh_test_config, request_debug_code


SIDE_EFFECT_CATEGORIES = (
    "generation",
    "catalog_create",
    "catalog_run",
    "activation",
    "package",
    "runtime_external",
    "tts",
    "asr",
    "media",
    "provider",
)


class _RequestPathSideEffectGuard:
    _ALLOW_TARGETS = frozenset(
        {
            (
                "services.learning_catalog_release_service."
                "LearningCatalogReleaseService.run"
            ),
            (
                "services.learning_catalog_release_service."
                "LearningCatalogReleaseService.activate"
            ),
        }
    )
    _PATCH_POINTS = (
        (
            "services.dynamic_learning_course_generation_service."
            "DynamicLearningCourseGenerationService.generate",
            "generation",
        ),
        (
            "services.dynamic_learning_course_generation_service."
            "DynamicLearningCourseGenerationService.generate_for_skill",
            "generation",
        ),
        (
            "services.dynamic_learning_course_generation_service."
            "StagedContentCandidateGenerator.advance",
            "generation",
        ),
        (
            "services.dynamic_learning_course_generation_service."
            "DynamicLearningCourseGenerationService.ensure_supply",
            "generation",
        ),
        (
            "services.learning_content_generation_service."
            "LearningContentGenerationService.generate",
            "generation",
        ),
        (
            "services.learning_content_pipeline_service."
            "LearningContentPipelineService.generate",
            "generation",
        ),
        (
            "services.learning_catalog_release_service."
            "LearningCatalogReleaseService.create",
            "catalog_create",
        ),
        (
            "services.learning_catalog_release_service."
            "LearningCatalogReleaseService.run",
            "catalog_run",
        ),
        (
            "services.learning_catalog_release_service."
            "LearningCatalogReleaseService.activate",
            "activation",
        ),
        (
            "repositories.learning_catalog_repository."
            "LearningCatalogRepository.activate_release",
            "activation",
        ),
        (
            "repositories.learning_catalog_repository."
            "LearningCatalogRepository.claim_next_item",
            "catalog_run",
        ),
        (
            "repositories.learning_catalog_repository."
            "LearningCatalogRepository.claim_package_for_item",
            "package",
        ),
        (
            "services.learning_catalog_release_service."
            "LearningCatalogReleaseService._process_item",
            "catalog_run",
        ),
        (
            "services.learning_catalog_release_service."
            "LearningCatalogReleaseService._validate_release_items",
            "activation",
        ),
        (
            "services.learning_catalog_release_service."
            "LearningCatalogReleaseService.advance_content",
            "catalog_run",
        ),
        ("services.lesson_package_service.LessonPackageService.enqueue", "package"),
        ("services.lesson_package_service.LessonPackageService.generate", "package"),
        (
            "services.lesson_package_service."
            "LessonPackageService.process_next_pending",
            "package",
        ),
        (
            "services.lesson_package_service."
            "LessonPackageService.finalize_media_package",
            "package",
        ),
        (
            "services.openmaic_full_runtime_service."
            "OpenMaicFullRuntimeService.generate_classroom",
            "runtime_external",
        ),
        (
            "services.openmaic_full_runtime_service."
            "OpenMaicFullRuntimeService.retry_classroom",
            "runtime_external",
        ),
        (
            "services.openmaic_full_runtime_service."
            "OpenMaicFullRuntimeService.recover_classroom",
            "runtime_external",
        ),
        (
            "services.openmaic_full_runtime_service."
            "OpenMaicFullRuntimeService.redispatch_deterministic_recovery",
            "runtime_external",
        ),
        (
            "services.openmaic_full_runtime_service."
            "OpenMaicFullRuntimeService.generation_status",
            "runtime_external",
        ),
        (
            "services.openmaic_full_runtime_service."
            "OpenMaicFullRuntimeService.process_next_pending",
            "runtime_external",
        ),
        (
            "integrations.openmaic_full_runtime_client."
            "OpenMaicFullRuntimeClient._request_json",
            "runtime_external",
        ),
        (
            "integrations.openmaic_deterministic_recovery_client."
            "OpenMaicDeterministicRecoveryClient._request_json",
            "runtime_external",
        ),
        (
            "integrations.openmaic_conversation_probe_client."
            "OpenMaicConversationProbeClient._request",
            "runtime_external",
        ),
        (
            "services.openmaic_full_runtime_service."
            "OpenMaicFullRuntimeService.recover_tts_credentials",
            "tts",
        ),
        (
            "integrations.openmaic_tts_credential_recovery_client."
            "OpenMaicTtsCredentialRecoveryClient._request_json",
            "tts",
        ),
        ("integrations.tts.macos_say.MacOsSayTtsProvider.synthesize", "tts"),
        ("integrations.tts.voxcpm2.VoxCpm2HttpProvider.synthesize", "tts"),
        ("services.speech_gateway.SpeechGateway.transcribe_text", "asr"),
        (
            "services.learning_media_materialization_service."
            "LearningMediaMaterializationService.enqueue_narration",
            "media",
        ),
        (
            "services.learning_media_materialization_service."
            "LearningMediaMaterializationService.enqueue_narration_in_transaction",
            "media",
        ),
        (
            "services.learning_media_materialization_service."
            "LearningMediaMaterializationService.materialize_job",
            "media",
        ),
        (
            "services.learning_media_materialization_service."
            "LearningMediaMaterializationService.materialize_next_pending",
            "media",
        ),
        (
            "services.learning_media_asset_store."
            "FilesystemLearningMediaAssetStore.put_audio",
            "media",
        ),
        (
            "integrations.openmaic_question_adapter."
            "OpenMaicQuestionAdapter.generate",
            "provider",
        ),
        ("services.ai_text_provider.OpenAICompatibleTextProvider.complete", "provider"),
        (
            "integrations.ai.kimi_vision_provider."
            "OpenAICompatibleVisionProvider.analyze_image",
            "provider",
        ),
    )

    def __init__(self):
        self.counts = {category: 0 for category in SIDE_EFFECT_CATEGORIES}

    def snapshot(self):
        return dict(self.counts)

    def delta(self, before):
        return {
            category: self.counts[category] - before[category]
            for category in SIDE_EFFECT_CATEGORIES
        }

    def _forbid(self, target: str, category: str):
        def forbidden(*_args, **_kwargs):
            self.counts[category] += 1
            raise AssertionError(
                f"request path invoked forbidden {category} dependency: {target}"
            )

        return forbidden

    @contextmanager
    def installed(self, *, allow_targets=()):
        allowed = frozenset(allow_targets)
        unexpected = allowed - self._ALLOW_TARGETS
        if unexpected:
            raise AssertionError(
                f"unsupported zero-call allow_targets: {sorted(unexpected)}"
            )
        with ExitStack() as stack:
            for target, category in self._PATCH_POINTS:
                if target in allowed:
                    continue
                stack.enter_context(patch(target, new=self._forbid(target, category)))
            yield self


class RequestPathSideEffectGuardContractTest(unittest.TestCase):
    def test_guard_freezes_exact_categories_and_real_execution_targets(self):
        expected_categories = (
            "generation",
            "catalog_create",
            "catalog_run",
            "activation",
            "package",
            "runtime_external",
            "tts",
            "asr",
            "media",
            "provider",
        )
        required_patch_points = (
            (
                "services.learning_catalog_release_service."
                "LearningCatalogReleaseService.activate",
                "activation",
            ),
            (
                "repositories.learning_catalog_repository."
                "LearningCatalogRepository.activate_release",
                "activation",
            ),
            (
                "repositories.learning_catalog_repository."
                "LearningCatalogRepository.claim_next_item",
                "catalog_run",
            ),
            (
                "repositories.learning_catalog_repository."
                "LearningCatalogRepository.claim_package_for_item",
                "package",
            ),
            (
                "services.learning_catalog_release_service."
                "LearningCatalogReleaseService._process_item",
                "catalog_run",
            ),
            (
                "services.learning_catalog_release_service."
                "LearningCatalogReleaseService._validate_release_items",
                "activation",
            ),
            (
                "services.lesson_package_service."
                "LessonPackageService.process_next_pending",
                "package",
            ),
            (
                "services.lesson_package_service."
                "LessonPackageService.finalize_media_package",
                "package",
            ),
            (
                "services.openmaic_full_runtime_service."
                "OpenMaicFullRuntimeService.generate_classroom",
                "runtime_external",
            ),
            (
                "services.openmaic_full_runtime_service."
                "OpenMaicFullRuntimeService.process_next_pending",
                "runtime_external",
            ),
            (
                "services.openmaic_full_runtime_service."
                "OpenMaicFullRuntimeService.recover_classroom",
                "runtime_external",
            ),
            (
                "services.openmaic_full_runtime_service."
                "OpenMaicFullRuntimeService.recover_tts_credentials",
                "tts",
            ),
            (
                "integrations.openmaic_full_runtime_client."
                "OpenMaicFullRuntimeClient._request_json",
                "runtime_external",
            ),
            (
                "integrations.openmaic_deterministic_recovery_client."
                "OpenMaicDeterministicRecoveryClient._request_json",
                "runtime_external",
            ),
            (
                "integrations.openmaic_tts_credential_recovery_client."
                "OpenMaicTtsCredentialRecoveryClient._request_json",
                "tts",
            ),
            (
                "integrations.openmaic_conversation_probe_client."
                "OpenMaicConversationProbeClient._request",
                "runtime_external",
            ),
            ("services.speech_gateway.SpeechGateway.transcribe_text", "asr"),
            (
                "services.learning_media_materialization_service."
                "LearningMediaMaterializationService.enqueue_narration_in_transaction",
                "media",
            ),
            (
                "services.learning_media_materialization_service."
                "LearningMediaMaterializationService.materialize_next_pending",
                "media",
            ),
            (
                "services.learning_media_asset_store."
                "FilesystemLearningMediaAssetStore.put_audio",
                "media",
            ),
            (
                "integrations.openmaic_question_adapter."
                "OpenMaicQuestionAdapter.generate",
                "provider",
            ),
        )

        with self.subTest(contract="exact_categories"):
            self.assertEqual(SIDE_EFFECT_CATEGORIES, expected_categories)

        actual_patch_points = set(_RequestPathSideEffectGuard._PATCH_POINTS)
        actual_categories = {category for _, category in actual_patch_points}
        actual_targets = {target for target, _ in actual_patch_points}
        with self.subTest(contract="all_patch_categories_are_exact"):
            self.assertEqual(actual_categories, set(expected_categories))
        with self.subTest(contract="required_patch_points"):
            self.assertEqual(
                set(required_patch_points) - actual_patch_points,
                set(),
                "zero-call guard is missing real execution patch points",
            )
        with self.subTest(contract="exact_allowed_entrypoints"):
            expected_allowed_entrypoints = frozenset(
                {
                    (
                        "services.learning_catalog_release_service."
                        "LearningCatalogReleaseService.run"
                    ),
                    (
                        "services.learning_catalog_release_service."
                        "LearningCatalogReleaseService.activate"
                    ),
                }
            )
            self.assertEqual(
                getattr(_RequestPathSideEffectGuard, "_ALLOW_TARGETS", frozenset()),
                expected_allowed_entrypoints,
            )
            self.assertEqual(expected_allowed_entrypoints - actual_targets, set())
            with self.assertRaises(AssertionError):
                with _RequestPathSideEffectGuard().installed(
                    allow_targets={
                        (
                            "services.learning_catalog_release_service."
                            "LearningCatalogReleaseService.create"
                        )
                    }
                ):
                    pass
        forbidden_local_boundaries = {
            "services.service_factory.openmaic_full_runtime_service",
            (
                "services.openmaic_full_runtime_service."
                "OpenMaicFullRuntimeService.create_student_launch"
            ),
            "services.service_factory.lesson_runtime_service",
        }
        with self.subTest(contract="local_read_boundaries_are_not_poisoned"):
            self.assertEqual(actual_targets & forbidden_local_boundaries, set())

        for target, _category in required_patch_points:
            with self.subTest(contract="target_exists", target=target):
                try:
                    with patch(target):
                        pass
                except (AttributeError, ImportError) as exc:
                    self.fail(f"zero-call patch target is not importable: {target}: {exc}")


class LearningCheckpointRequestPathZeroCallsTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
        self.app.extensions["mira_formal_learning_access_checker"] = (
            lambda conn, child: assert_formal_student_grade_open(child)
        )
        self.client = self.app.test_client()
        self.database = Database(self.app.config["DATABASE_URL"])
        LearningRepository(self.database).ensure_published_courses(
            PRIMARY_COURSE_CATALOG,
            now=int(datetime.now().timestamp() * 1000),
        )

    def test_request_paths_construct_and_call_no_generation_or_provider_dependency(self):
        evidence = self._exercise_request_paths_with_zero_guard()
        zero_counts = {category: 0 for category in SIDE_EFFECT_CATEGORIES}

        self.assertEqual(
            evidence,
            {
                "setup_grade_save": zero_counts,
                "profile_grade_save_primary_1": zero_counts,
                "preparation_current_v2_get": zero_counts,
                "preparation_retry_202_post": zero_counts,
                "learning_today_get": zero_counts,
                "legacy_parent_learning_today_assign_rejected": zero_counts,
            },
        )

    def test_student_candidate_is_invisible_and_history_is_immutable(self):
        zero_counts = {category: 0 for category in SIDE_EFFECT_CATEGORIES}
        expected_evidence = {
            "student_library": zero_counts,
            "student_candidate_detail": zero_counts,
            "student_latest_report": zero_counts,
            "student_candidate_launch": zero_counts,
        }
        expected_history_keys = {
            "active_release",
            "active_release_items",
            "task",
            "session",
            "report",
        }
        result = self._exercise_student_candidate_with_zero_guard()

        with self.subTest(contract="student_zero_side_effect_labels"):
            self.assertEqual(result["evidence"], expected_evidence)
        with self.subTest(contract="unchanged_history_keys"):
            self.assertEqual(set(result["before"]), expected_history_keys)
            self.assertEqual(result["after"], result["before"])

    def test_daily_runner_rechecks_without_external_side_effects(self):
        zero_counts = {category: 0 for category in SIDE_EFFECT_CATEGORIES}
        access_token = self._login("13800002828")
        headers = {"Authorization": f"Bearer {access_token}"}
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "日常准备家长",
                "relationship": "家长",
                "relationshipKey": "other",
            },
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200, parent.json)
        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "日常准备孩子",
                "nickname": "日常准备孩子",
                "gradeCode": "primary_1",
                "schoolYearStartYear": 2026,
            },
            headers=headers,
        )
        self.assertEqual(child.status_code, 200, child.json)
        child_id = child.json["child"]["id"]

        self.app.config["LEARNING_STATIC_CATALOG_ENABLED"] = True
        self.app.extensions.pop("mira_learning_service", None)
        runner = LearningDailyPreparationRunner()
        now = datetime(2026, 9, 9, 5, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
        evidence = {}
        guard = _RequestPathSideEffectGuard()

        with self.app.app_context(), guard.installed():
            snapshot = guard.snapshot()
            result = runner.run_due_once(
                now=now,
                hour=5,
                minute=0,
                prepare=lambda learning_date: (
                    learning_service().ensure_today_for_all_primary_children(
                        learning_date=learning_date
                    )
                ),
            )
            evidence["daily_runner_prepare"] = guard.delta(snapshot)
            self.assertIsNotNone(result)
            self.assertEqual(
                result,
                {
                    "ok": True,
                    "date": "2026-09-09",
                    "childrenChecked": 1,
                    "childrenEnsured": 0,
                    "childrenSkipped": 1,
                    "createdCount": 0,
                    "skipped": [
                        {
                            "childId": child_id,
                            "code": "student_learning_release_not_ready",
                            "message": "该年级正式课程尚未准备完成",
                        }
                    ],
                    "failures": [],
                },
            )

            snapshot = guard.snapshot()
            replay = runner.run_due_once(
                now=now,
                hour=5,
                minute=0,
                prepare=lambda learning_date: (
                    learning_service().ensure_today_for_all_primary_children(
                        learning_date=learning_date
                    )
                ),
            )
            evidence["daily_runner_same_day_replay"] = guard.delta(snapshot)
            self.assertEqual(replay, result)
            self.assertEqual(runner.status()["lastPreparedDate"], "2026-09-09")

        with self.database.transaction() as conn:
            task_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM tasks
                WHERE child_id = ?
                  AND scheduled_date = ?
                  AND type = 'learning'
                """,
                (child_id, "2026-09-09"),
            ).fetchone()["count"]
            session_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_sessions
                WHERE child_id = ?
                """,
                (child_id,),
            ).fetchone()["count"]
        self.assertEqual(task_count, 0)
        self.assertEqual(session_count, 0)

        self.assertEqual(
            evidence,
            {
                "daily_runner_prepare": zero_counts,
                "daily_runner_same_day_replay": zero_counts,
            },
        )

    def test_content_only_internal_routes_reject_legacy_bypass(self):
        zero_counts = {category: 0 for category in SIDE_EFFECT_CATEGORIES}
        target = build_preparation_target("primary_1")
        service = LearningCatalogReleaseService(
            self.app.config["DATABASE_URL"],
            dynamic_generation_service=None,
            lesson_package_service=None,
        )
        created = service.create_preparation_content_build(
            request_id="task11-content-only-internal-bypass",
            title="Task 11 内容候选隔离",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        build_id = created["build"]["id"]
        release_id = created["release"]["id"]
        self.app.config.update(
            INTERNAL_API_TOKEN="task11-content-only-token",
            INTERNAL_ALLOWED_SOURCES=[],
        )
        self.app.extensions.pop("mira_learning_catalog_release_service", None)
        headers = {
            "X-Mira-Internal-Token": "task11-content-only-token",
            "X-Mira-Internal-Source": "task11-zero-bypass",
        }

        before = self._content_only_business_state(
            build_id=build_id,
            release_id=release_id,
        )
        self.assertEqual(before["itemCount"], 30)
        self.assertTrue(all(len(value) == 64 for value in before["hashes"].values()))
        self.assertEqual(
            before["downstreamCounts"],
            {
                "releaseItems": 0,
                "lessonPackages": 0,
                "classroomJobs": 0,
                "mediaJobs": 0,
                "mediaAssets": 0,
                "runtimeClassrooms": 0,
                "ttsRecoveries": 0,
                "providerDispatches": 0,
            },
        )
        with self.database.transaction() as conn:
            audit_count_before = conn.execute(
                "SELECT COUNT(*) AS count FROM audit_events "
                "WHERE audit_domain = 'internal_api'"
            ).fetchone()["count"]

        evidence = {}
        guard = _RequestPathSideEffectGuard()
        run_target = (
            "services.learning_catalog_release_service."
            "LearningCatalogReleaseService.run"
        )
        activate_target = (
            "services.learning_catalog_release_service."
            "LearningCatalogReleaseService.activate"
        )
        original_run = LearningCatalogReleaseService.run
        original_activate = LearningCatalogReleaseService.activate
        entry_calls = {"run": 0, "activate": 0}

        def observed_run(instance, *args, **kwargs):
            entry_calls["run"] += 1
            return original_run(instance, *args, **kwargs)

        def observed_activate(instance, *args, **kwargs):
            entry_calls["activate"] += 1
            return original_activate(instance, *args, **kwargs)

        with patch(
            run_target,
            new=observed_run,
        ), guard.installed(allow_targets={run_target}):
            snapshot = guard.snapshot()
            run = self.client.post(
                f"/internal/learning/content/catalog/builds/{build_id}/run",
                json={"maxItems": 1},
                headers=headers,
            )
            evidence["content_only_legacy_run"] = guard.delta(snapshot)
            self.assertEqual(run.status_code, 409, run.json)
            self.assertEqual(run.json["error"], "catalog_content_only_build_isolated")

        with patch(
            activate_target,
            new=observed_activate,
        ), guard.installed(allow_targets={activate_target}):
            snapshot = guard.snapshot()
            activate = self.client.post(
                "/internal/learning/content/catalog/releases/"
                f"{release_id}/activate",
                headers=headers,
            )
            evidence["content_only_legacy_activate"] = guard.delta(snapshot)
            self.assertEqual(activate.status_code, 409, activate.json)
            self.assertEqual(
                activate.json["error"],
                "catalog_content_only_build_isolated",
            )
        self.assertEqual(entry_calls, {"run": 1, "activate": 1})

        after = self._content_only_business_state(
            build_id=build_id,
            release_id=release_id,
        )
        self.assertEqual(after, before)
        with self.database.transaction() as conn:
            audit_rows = conn.execute(
                """
                SELECT route, accepted, reason, payload_ref
                FROM audit_events
                WHERE audit_domain = 'internal_api'
                ORDER BY route
                """
            ).fetchall()
        self.assertEqual(len(audit_rows) - int(audit_count_before), 2)
        self.assertEqual(
            {row["route"] for row in audit_rows},
            {
                "/internal/learning/content/catalog/builds/:buildId/run",
                "/internal/learning/content/catalog/releases/:releaseId/activate",
            },
        )
        self.assertTrue(
            all(
                int(row["accepted"]) == 1 and row["reason"] == "ok"
                for row in audit_rows
            )
        )
        self.assertEqual(
            {row["payload_ref"] for row in audit_rows},
            {build_id, release_id},
        )

        self.assertEqual(
            evidence,
            {
                "content_only_legacy_run": zero_counts,
                "content_only_legacy_activate": zero_counts,
            },
        )

    def _content_only_business_state(self, *, build_id: str, release_id: str):
        with self.database.transaction() as conn:
            build_rows = conn.execute(
                "SELECT * FROM learning_catalog_build_jobs WHERE id = ?",
                (build_id,),
            ).fetchall()
            release_rows = conn.execute(
                "SELECT * FROM learning_catalog_releases WHERE id = ?",
                (release_id,),
            ).fetchall()
            item_rows = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE build_job_id = ?
                ORDER BY subject_ordinal, boundary_ordinal, variant_ordinal, id
                """,
                (build_id,),
            ).fetchall()
            downstream_counts = {
                "releaseItems": conn.execute(
                    "SELECT COUNT(*) AS count "
                    "FROM learning_catalog_release_items WHERE release_id = ?",
                    (release_id,),
                ).fetchone()["count"],
                "lessonPackages": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_lesson_packages"
                ).fetchone()["count"],
                "classroomJobs": conn.execute(
                    "SELECT COUNT(*) AS count "
                    "FROM learning_classroom_generation_jobs"
                ).fetchone()["count"],
                "mediaJobs": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_media_generation_jobs"
                ).fetchone()["count"],
                "mediaAssets": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_media_assets"
                ).fetchone()["count"],
                "runtimeClassrooms": conn.execute(
                    "SELECT COUNT(*) AS count "
                    "FROM learning_openmaic_runtime_classrooms"
                ).fetchone()["count"],
                "ttsRecoveries": conn.execute(
                    "SELECT COUNT(*) AS count "
                    "FROM learning_openmaic_tts_credential_recoveries"
                ).fetchone()["count"],
                "providerDispatches": conn.execute(
                    "SELECT COUNT(*) AS count "
                    "FROM learning_course_provider_dispatches"
                ).fetchone()["count"],
            }
        self.assertEqual(len(build_rows), 1)
        self.assertEqual(len(release_rows), 1)
        self.assertEqual(len(item_rows), 30)
        return {
            "hashes": {
                "build": self._canonical_rows_hash(build_rows),
                "release": self._canonical_rows_hash(release_rows),
                "items": self._canonical_rows_hash(item_rows),
            },
            "itemCount": len(item_rows),
            "downstreamCounts": downstream_counts,
        }

    def _exercise_student_candidate_with_zero_guard(self):
        parent_token = self._login("13800002818")
        parent_headers = {"Authorization": f"Bearer {parent_token}"}
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "候选隔离家长",
                "relationship": "家长",
                "relationshipKey": "other",
            },
            headers=parent_headers,
        )
        self.assertEqual(parent.status_code, 200, parent.json)
        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "候选隔离孩子",
                "nickname": "候选隔离孩子",
                "gradeCode": "primary_1",
                "schoolYearStartYear": datetime.now().year,
            },
            headers=parent_headers,
        )
        self.assertEqual(child.status_code, 200, child.json)
        child_id = child.json["child"]["id"]
        student_token = self._pair_student(
            parent_headers=parent_headers,
            child_id=child_id,
            pin="2468",
        )
        student_headers = {"Authorization": f"Bearer {student_token}"}

        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-08", "scheduledStart": "18:45"},
            headers=student_headers,
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        task_id = assigned.json["task"]["id"]
        course_id = assigned.json["recommendation"]["courseId"]
        course_version = assigned.json["recommendation"]["courseVersion"]
        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": task_id},
            headers=student_headers,
        )
        self.assertEqual(started.status_code, 200, started.json)
        session_id = started.json["session"]["id"]
        completed = None
        for answer in self._correct_answers_for_task(task_id):
            completed = self.client.post(
                f"/api/v2/student/learning/sessions/{session_id}/answer",
                json={"answer": answer},
                headers=student_headers,
            )
            self.assertEqual(completed.status_code, 200, completed.json)
        self.assertIsNotNone(completed)
        self.assertTrue(completed.json["completed"])
        report = completed.json["report"]
        report_id = report["id"]

        release_id = self._install_old_active_release(
            course_id=course_id,
            course_version=course_version,
        )
        candidate = self._install_unpublished_candidate()
        before = self._history_hashes(
            release_id=release_id,
            task_id=task_id,
            session_id=session_id,
            report_id=report_id,
        )

        self.app.config.update(
            OPENMAIC_FULL_RUNTIME_ENABLED=True,
            OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED=False,
            OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED=False,
            OPENMAIC_FULL_RUNTIME_INTERNAL_URL="http://127.0.0.1:3100",
            OPENMAIC_FULL_RUNTIME_PUBLIC_URL="http://127.0.0.1:3101",
        )
        self.app.extensions.pop("mira_openmaic_full_runtime_service", None)

        evidence = {}
        guard = _RequestPathSideEffectGuard()

        def record(label, request_call, expected_status):
            snapshot = guard.snapshot()
            response = request_call()
            self.assertEqual(response.status_code, expected_status, response.json)
            evidence[label] = guard.delta(snapshot)
            return response

        with guard.installed():
            library = record(
                "student_library",
                lambda: self.client.get(
                    "/api/v2/student/learning/library",
                    query_string={"bucket": "all"},
                    headers=student_headers,
                ),
                200,
            )
            serialized_library = json.dumps(
                library.json,
                ensure_ascii=False,
                sort_keys=True,
            )
            self.assertNotIn(candidate["id"], serialized_library)
            self.assertNotIn(candidate["course_id"], serialized_library)

            detail = record(
                "student_candidate_detail",
                lambda: self.client.get(
                    f"/api/v2/student/learning/courses/{candidate['course_id']}",
                    query_string={"version": candidate["course_version"]},
                    headers=student_headers,
                ),
                404,
            )
            self.assertEqual(detail.json["error"], "learning_course_not_found")

            latest = record(
                "student_latest_report",
                lambda: self.client.get(
                    "/api/v2/student/learning/reports/latest",
                    query_string={"subject": report["subject"]},
                    headers=student_headers,
                ),
                200,
            )
            self.assertEqual(latest.json["report"]["id"], report_id)

            launch = record(
                "student_candidate_launch",
                lambda: self.client.post(
                    "/api/v2/student/learning/sessions/"
                    "session_candidate_hidden/openmaic-launch",
                    headers=student_headers,
                ),
                404,
            )
            self.assertEqual(launch.json["error"], "learning_session_not_found")

        after = self._history_hashes(
            release_id=release_id,
            task_id=task_id,
            session_id=session_id,
            report_id=report_id,
        )
        return {"evidence": evidence, "before": before, "after": after}

    def _exercise_request_paths_with_zero_guard(self):
        access_token = self._login("13800002808")
        headers = {"Authorization": f"Bearer {access_token}"}
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "家长",
                "relationship": "家长",
                "relationshipKey": "other",
            },
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200, parent.json)

        evidence = {}
        guard = _RequestPathSideEffectGuard()

        def record(label, request_call, expected_status):
            before = guard.snapshot()
            response = request_call()
            self.assertEqual(response.status_code, expected_status, response.json)
            evidence[label] = guard.delta(before)
            return response

        current_year = datetime.now().year
        with guard.installed():
            setup_saved = record(
                "setup_grade_save",
                lambda: self.client.post(
                    "/api/setup/child",
                    json={
                        "name": "验证孩子",
                        "nickname": "验证孩子",
                        "gradeCode": "primary_1",
                        "schoolYearStartYear": current_year,
                    },
                    headers=headers,
                ),
                200,
            )
            child_id = setup_saved.json["child"]["id"]
            self.assertEqual(setup_saved.json["child"]["gradeCode"], "primary_1")
            self.assertEqual(
                setup_saved.json["learningPreparation"]["gradeCode"],
                "primary_1",
            )

            profile_saved = record(
                "profile_grade_save_primary_1",
                lambda: self.client.patch(
                    f"/api/children/{child_id}",
                    json={
                        "gradeCode": "primary_1",
                        "schoolYearStartYear": current_year,
                    },
                    headers=headers,
                ),
                200,
            )
            self.assertEqual(profile_saved.json["child"]["gradeCode"], "primary_1")
            self.assertEqual(
                profile_saved.json["learningPreparation"]["gradeCode"],
                "primary_1",
            )
            plan_id = profile_saved.json["learningPreparation"]["id"]

            current = record(
                "preparation_current_v2_get",
                lambda: self.client.get(
                    "/api/learning/preparations/current",
                    query_string={"childId": child_id},
                    headers={
                        **headers,
                        "X-Mira-Preparation-Schema": (
                            "mira.learning.preparation.v2"
                        ),
                    },
                ),
                200,
            )
            self.assertIn(
                "X-Mira-Preparation-Schema",
                current.headers.get("Vary", ""),
            )
            self.assertEqual(
                current.json["preparation"]["schemaVersion"],
                "mira.learning.preparation.v2",
            )
            self.assertEqual(
                current.json["preparation"]["contentProgress"],
                {
                    "candidateCount": 0,
                    "failedCount": 0,
                    "targetCount": 30,
                    "canary": {
                        "targetCount": 3,
                        "candidateCount": 0,
                        "failedCount": 0,
                        "passed": False,
                    },
                },
            )

        self._mark_plan_failed(plan_id)

        with guard.installed():
            retry = record(
                "preparation_retry_202_post",
                lambda: self.client.post(
                    f"/api/learning/preparations/{plan_id}/retry",
                    json={"requestId": "task-11-parent-retry"},
                    headers={
                        **headers,
                        "X-Mira-Preparation-Schema": (
                            "mira.learning.preparation.v2"
                        ),
                    },
                ),
                202,
            )
            self.assertIn(
                "X-Mira-Preparation-Schema",
                retry.headers.get("Vary", ""),
            )
            self.assertEqual(
                retry.json["preparation"]["schemaVersion"],
                "mira.learning.preparation.v2",
            )
            self.assertEqual(retry.json["preparation"]["attempt"], 2)
            self.assertEqual(
                retry.json["preparation"]["contentProgress"],
                {
                    "candidateCount": 0,
                    "failedCount": 0,
                    "targetCount": 30,
                    "canary": {
                        "targetCount": 3,
                        "candidateCount": 0,
                        "failedCount": 0,
                        "passed": False,
                    },
                },
            )

            record(
                "learning_today_get",
                lambda: self.client.get(
                    "/api/learning/today",
                    query_string={"childId": child_id, "date": "2026-08-20"},
                    headers=headers,
                ),
                200,
            )
            record(
                "legacy_parent_learning_today_assign_rejected",
                lambda: self.client.post(
                    "/api/learning/today/assign",
                    json={
                        "childId": child_id,
                        "date": "2026-08-20",
                        "scheduledStart": "19:30",
                    },
                    headers=headers,
                ),
                410,
            )

        return evidence

    def _mark_plan_failed(self, plan_id: str):
        failed_at = int(datetime.now().timestamp() * 1000)
        with self.database.transaction() as conn:
            plan = conn.execute(
                "SELECT * FROM learning_curriculum_preparation_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        self.assertIsNotNone(plan)
        target = json.loads(str(plan["target_spec_json"]))
        catalog = LearningCatalogReleaseService(
            self.app.config["DATABASE_URL"],
            dynamic_generation_service=None,
            lesson_package_service=None,
        )
        catalog_payload = catalog.create_preparation_content_build(
            request_id=str(plan["shared_build_request_id"]),
            title="Task 11 parent retry authority",
            preparation_target=target,
            target_fingerprint=str(plan["target_fingerprint"]),
        )
        build_id = str(catalog_payload["build"]["id"])
        release_id = str(catalog_payload["release"]["id"])
        subject_progress = {
            "chinese": {
                "totalCourseCount": 12,
                "readyCourseCount": 0,
                "failedCourseCount": 12,
                "contentCandidateCount": 0,
                "contentFailedCount": 0,
            },
            "math": {
                "totalCourseCount": 9,
                "readyCourseCount": 0,
                "failedCourseCount": 9,
                "contentCandidateCount": 0,
                "contentFailedCount": 0,
            },
            "english": {
                "totalCourseCount": 9,
                "readyCourseCount": 0,
                "failedCourseCount": 9,
                "contentCandidateCount": 0,
                "contentFailedCount": 0,
            },
        }
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'failed', stage = 'completed',
                  catalog_build_id = ?, catalog_release_id = ?,
                  ready_course_count = 0, failed_course_count = total_course_count,
                  subject_progress_json = ?,
                  error_code = 'preparation_dependency_unavailable',
                  error_message_safe = '课程准备未完成，请重试',
                  lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
                  next_run_at = NULL, hard_deadline_at = NULL, resume_stage = NULL,
                  completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    build_id,
                    release_id,
                    json.dumps(subject_progress, ensure_ascii=False),
                    failed_at,
                    failed_at,
                    plan_id,
                ),
            )

    def _pair_student(self, *, parent_headers, child_id: str, pin: str) -> str:
        pairing = self.client.post(
            f"/api/v2/parent/children/{child_id}/student-access/pairing-codes",
            json={"pin": pin},
            headers=parent_headers,
        )
        self.assertEqual(pairing.status_code, 200, pairing.json)
        paired = self.client.post(
            "/api/v2/student/auth/pair",
            json={
                "pairingCode": pairing.json["pairingCode"],
                "clientDevice": {
                    "label": "零调用验证浏览器",
                    "type": "browser",
                    "platform": "web",
                },
            },
        )
        self.assertEqual(paired.status_code, 200, paired.json)
        return paired.json["tokens"]["accessToken"]

    def _correct_answers_for_task(self, task_id: str):
        with self.database.transaction() as conn:
            row = conn.execute(
                """
                SELECT course.content_json
                FROM tasks AS task
                JOIN learning_courses AS course
                  ON course.id = task.learning_course_id
                 AND course.version = task.learning_course_version
                WHERE task.id = ?
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        content = json.loads(row["content_json"])
        answers = []
        for question in content["questions"]:
            question_type = question.get("type")
            evaluation = question.get("evaluation") or {}
            if question_type == "accepted_text":
                accepted = (
                    evaluation.get("acceptedAnswers")
                    or question.get("acceptedAnswers")
                    or question.get("answer")
                )
                answers.append(accepted[0])
            elif question_type == "sequence":
                answers.append(
                    list(evaluation.get("expectedSequence") or question.get("answer"))
                )
            elif "answer" in question:
                answers.append(question["answer"])
            elif "expectedOptionId" in evaluation:
                answers.append({"optionId": evaluation["expectedOptionId"]})
            elif "expectedSequence" in evaluation:
                answers.append(list(evaluation["expectedSequence"]))
            elif "acceptedAnswers" in evaluation:
                answers.append(evaluation["acceptedAnswers"][0])
            else:
                answers.append(evaluation.get("expected"))
        return answers

    def _install_old_active_release(
        self,
        *,
        course_id: str,
        course_version: str,
    ) -> str:
        timestamp = now_ms()
        job_id = "job_zero_call_history"
        artifact_id = "artifact_zero_call_history"
        package_id = "package_zero_call_history"
        release_id = "release_zero_call_history"
        curriculum = "mira.primary.cn.v1"
        boundary = "boundary-zero-call-history"
        with self.database.transaction() as conn:
            course = conn.execute(
                """
                SELECT grade_code, subject, node_code
                FROM learning_courses WHERE id = ? AND version = ?
                """,
                (course_id, course_version),
            ).fetchone()
            self.assertIsNotNone(course)
            conn.execute(
                """
                UPDATE learning_courses
                SET status = 'published', quality_status = 'released',
                  content_origin = 'openmaic_generated',
                  curriculum_version = ?, boundary_version = ?, retired_at = NULL
                WHERE id = ? AND version = ?
                """,
                (curriculum, boundary, course_id, course_version),
            )
            conn.execute(
                """
                INSERT INTO learning_classroom_generation_jobs(
                  id, request_id, course_id, course_version, generator, status,
                  source_artifact_id, package_id, package_version,
                  started_at, completed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'openmaic', 'completed', ?, ?, 1,
                  ?, ?, ?, ?)
                """,
                (
                    job_id,
                    "request-zero-call-history",
                    course_id,
                    course_version,
                    artifact_id,
                    package_id,
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_classroom_source_artifacts(
                  id, job_id, request_id, source_format, source_package_version,
                  dsl_version, status, source_hash, payload_json,
                  validation_report_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'openmaic_dsl', '0.3.2', '0.3.2',
                  'validated', ?, '{}', '{}', ?, ?)
                """,
                (
                    artifact_id,
                    job_id,
                    "request-zero-call-history",
                    "1" * 64,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_lesson_packages(
                  id, version, course_id, course_version,
                  source_course_content_hash, schema_version,
                  status, source_artifact_id, compiler_version,
                  public_content_hash, private_content_hash,
                  public_payload_json, validation_report_json,
                  created_at, published_at, updated_at
                ) VALUES (?, 1, ?, ?, SHA2((
                    SELECT content_json FROM learning_courses
                    WHERE id = ? AND version = ? LIMIT 1
                  ), 256), 'mira.lesson-package.v2', 'published', ?,
                  'zero-call-history', ?, ?, '{}', '{}', ?, ?, ?)
                """,
                (
                    package_id,
                    course_id,
                    course_version,
                    course_id,
                    course_version,
                    artifact_id,
                    "2" * 64,
                    "3" * 64,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_course_lesson_package_bindings(
                  course_id, course_version, package_id, package_version, updated_at
                ) VALUES (?, ?, ?, 1, ?)
                """,
                (course_id, course_version, package_id, timestamp),
            )
            conn.execute(
                """
                INSERT INTO learning_catalog_releases(
                  id, curriculum_version, title, status, quality_status,
                  required_boundary_count, ready_item_count,
                  activated_at, created_at, updated_at
                ) VALUES (?, ?, 'Zero-call history release', 'active', 'ready',
                  1, 1, ?, ?, ?)
                """,
                (release_id, curriculum, timestamp, timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO learning_catalog_release_items(
                  release_id, course_id, course_version, grade_code, subject,
                  skill_id, curriculum_version, boundary_version,
                  variant_ordinal, package_id, package_version, status,
                  quality_status, published_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1,
                  'published', 'ready', ?, ?, ?)
                """,
                (
                    release_id,
                    course_id,
                    course_version,
                    course["grade_code"],
                    course["subject"],
                    course["node_code"],
                    curriculum,
                    boundary,
                    package_id,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
        return release_id

    def _install_unpublished_candidate(self):
        timestamp = now_ms()
        source = json.loads(
            json.dumps(PRIMARY_COURSE_CATALOG[0], ensure_ascii=False)
        )
        source["id"] = "course_cp2_candidate_hidden"
        source["version"] = "candidate-v1"
        source["title"] = "不可见候选课程"
        repository = DynamicLearningCourseRepository(self.database)
        with repository.transaction() as conn:
            job, _ = repository.create_or_get_job(
                conn,
                request_id="request_cp2_candidate_hidden",
                grade_code=source["gradeCode"],
                subject=source["subject"],
                node_code=source["nodeCode"],
                generator="openmaic",
                provider="test-only",
                model="test-only",
                prompt_version="test-only",
                requested_candidate_count=1,
                generation_spec=None,
                now=timestamp,
            )
            candidate, _ = repository.create_or_get_candidate(
                conn,
                job_id=job["id"],
                ordinal=1,
                course=source,
                now=timestamp,
            )
        with self.database.transaction() as conn:
            candidate_counts = {
                "jobs": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_course_generation_jobs "
                    "WHERE id = ?",
                    (job["id"],),
                ).fetchone()["count"],
                "candidates": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_course_generation_candidates "
                    "WHERE id = ?",
                    (candidate["id"],),
                ).fetchone()["count"],
                "courses": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_courses "
                    "WHERE id = ? AND version = ?",
                    (candidate["course_id"], candidate["course_version"]),
                ).fetchone()["count"],
                "tasks": conn.execute(
                    "SELECT COUNT(*) AS count FROM tasks "
                    "WHERE learning_course_id = ? AND learning_course_version = ?",
                    (candidate["course_id"], candidate["course_version"]),
                ).fetchone()["count"],
                "release_items": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_catalog_release_items "
                    "WHERE course_id = ? AND course_version = ?",
                    (candidate["course_id"], candidate["course_version"]),
                ).fetchone()["count"],
                "packages": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_lesson_packages "
                    "WHERE course_id = ? AND course_version = ?",
                    (candidate["course_id"], candidate["course_version"]),
                ).fetchone()["count"],
                "runtimes": conn.execute(
                    "SELECT COUNT(*) AS count FROM learning_openmaic_runtime_classrooms "
                    "WHERE course_id = ? AND course_version = ?",
                    (candidate["course_id"], candidate["course_version"]),
                ).fetchone()["count"],
            }
        self.assertEqual(
            candidate_counts,
            {
                "jobs": 1,
                "candidates": 1,
                "courses": 0,
                "tasks": 0,
                "release_items": 0,
                "packages": 0,
                "runtimes": 0,
            },
        )
        return {
            "id": str(candidate["id"]),
            "course_id": str(candidate["course_id"]),
            "course_version": str(candidate["course_version"]),
        }

    def _history_hashes(
        self,
        *,
        release_id: str,
        task_id: str,
        session_id: str,
        report_id: str,
    ):
        with self.database.transaction() as conn:
            rows = {
                "active_release": conn.execute(
                    "SELECT * FROM learning_catalog_releases WHERE id = ?",
                    (release_id,),
                ).fetchall(),
                "active_release_items": conn.execute(
                    """
                    SELECT * FROM learning_catalog_release_items
                    WHERE release_id = ?
                    ORDER BY course_id, course_version
                    """,
                    (release_id,),
                ).fetchall(),
                "task": conn.execute(
                    "SELECT * FROM tasks WHERE id = ?",
                    (task_id,),
                ).fetchall(),
                "session": conn.execute(
                    "SELECT * FROM learning_sessions WHERE id = ?",
                    (session_id,),
                ).fetchall(),
                "report": conn.execute(
                    "SELECT * FROM learning_reports WHERE id = ?",
                    (report_id,),
                ).fetchall(),
            }
        for label, values in rows.items():
            self.assertTrue(values, f"missing history row for {label}")
        return {
            label: self._canonical_rows_hash(values)
            for label, values in rows.items()
        }

    @staticmethod
    def _canonical_rows_hash(rows):
        def normalize(value):
            if isinstance(value, bytes):
                return {"bytesHex": value.hex()}
            if isinstance(value, datetime):
                return value.isoformat()
            return value

        payload = [
            {
                key: normalize(row[key])
                for key in sorted(row.keys())
            }
            for row in rows
        ]
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _login(self, phone: str):
        code = request_debug_code(self.client, phone)
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(login.status_code, 200, login.json)
        return login.json["tokens"]["accessToken"]


if __name__ == "__main__":
    unittest.main()
