from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
import unittest

from app import create_app
from content.primary_skill_boundaries import (
    PRIMARY_CURRICULUM_VERSION,
    PRIMARY_SKILL_BOUNDARIES,
    boundaries_for,
)
from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.learning_repository import LearningRepository
from repositories.learning_catalog_repository import (
    LearningCatalogBuildConflict,
    LearningCatalogRepository,
)
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from services.dynamic_learning_course_generation_service import (
    DynamicLearningCourseGenerationService,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_catalog_validator import LearningCatalogValidator
from tests.support import fresh_test_config, validated_test_database_url
from tests.test_dynamic_learning_course_generation_service import (
    _WidgetCompatibleQuestionAdapter,
)
from tests.test_lesson_package_v2 import _FakeClassroomAdapter
from tests.support_learning_media import AutoPublishingLessonPackageService


class LearningCatalogReleaseTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.config = config
        self.database_url = config["DATABASE_URL"]
        self.assertEqual(validated_test_database_url(self.database_url), self.database_url)
        self.question_adapter = _WidgetCompatibleQuestionAdapter(vary_by_request=True)
        self.classroom_adapter = _FakeClassroomAdapter()
        self.dynamic = DynamicLearningCourseGenerationService(
            self.database_url,
            adapter=self.question_adapter,
        )
        self.lesson = AutoPublishingLessonPackageService(
            self.database_url,
            adapter=self.classroom_adapter,
        )
        self.service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=self.dynamic,
            lesson_package_service=self.lesson,
        )

    def tearDown(self):
        self.lesson.close()

    def test_new_build_is_not_activatable_before_release_ready_packages(self):
        created = self.service.create(
            {
                "requestId": "catalog-release-readiness-payload",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        self.assertFalse(created["canActivate"])
        self.assertEqual(created["build"]["releaseReadyItemCount"], 0)
        self.assertEqual(created["build"]["mediaPendingItemCount"], 0)

    def test_public_create_rejects_content_authority_injection_and_stays_full_pipeline(self):
        for key, value in (
            ("executionMode", "content_only"),
            ("stageCeiling", "content_ready"),
            ("contentManifestVersion", "mira.learning.preparation-target.v2"),
            ("canaryManifest", {"targets": []}),
            ("preparationTarget", {"schemaVersion": "injected"}),
        ):
            with self.subTest(key=key):
                with self.assertRaises(ApiError) as raised:
                    self.service.create(
                        {"requestId": f"catalog-public-injection-{key}", key: value}
                    )
                self.assertEqual(raised.exception.status_code, 400)

        created = self.service.create(
            {
                "requestId": "catalog-public-full-pipeline-only",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        repository = LearningCatalogRepository(Database(self.database_url))
        with repository.transaction() as conn:
            build = repository.get_build(
                conn,
                build_id=created["build"]["id"],
            )
        self.assertEqual(build["execution_mode"], "full_pipeline")
        self.assertEqual(build["stage_ceiling"], "active_release")
        self.assertIsNone(build["content_manifest_version"])
        self.assertIsNone(build["canary_manifest_json"])

    def test_concurrent_identical_create_has_one_item_creator_and_shared_identity(self):
        winner_inserted = Event()
        loser_entered = Event()
        loser_returned = Event()
        allow_winner_commit = Event()
        first_creator_lock = Lock()
        first_creator = {"claimed": False}
        targets = [
            boundary.to_catalog_payload()
            for boundary in PRIMARY_SKILL_BOUNDARIES
            if boundary.grade_code == "primary_1"
        ]
        target_spec = {
            "schemaVersion": "mira.learning.catalog-build-target.v1",
            "curriculumVersion": PRIMARY_CURRICULUM_VERSION,
            "grades": ["primary_1"],
            "subjects": ["chinese", "math", "english"],
            "variantsPerBoundary": 3,
            "allowPartial": True,
            "boundaryVersions": [item["boundaryVersion"] for item in targets],
        }

        class PausingRepository(LearningCatalogRepository):
            def create_or_get_build(self, conn, **kwargs):
                result = super().create_or_get_build(conn, **kwargs)
                if result[1]:
                    with first_creator_lock:
                        pause = not first_creator["claimed"]
                        first_creator["claimed"] = True
                    if pause:
                        winner_inserted.set()
                        self.assert_wait(allow_winner_commit)
                return result

            @staticmethod
            def assert_wait(event):
                if not event.wait(timeout=10):
                    raise AssertionError("winner commit was not released")

        connection_ids = []
        isolation_levels = []

        def create_once(*, wait_for_winner: bool):
            repository = PausingRepository(Database(self.database_url))
            with repository.transaction() as conn:
                session = conn.execute(
                    "SELECT CONNECTION_ID() AS connection_id, "
                    "@@transaction_isolation AS isolation_level"
                ).fetchone()
                connection_ids.append(session["connection_id"])
                isolation_levels.append(str(session["isolation_level"]).upper())
                if wait_for_winner:
                    if not winner_inserted.wait(timeout=10):
                        raise AssertionError("winner did not insert")
                    loser_entered.set()
                build, created = repository.create_or_get_build(
                    conn,
                    request_id="catalog-concurrent-grade-preparation",
                    curriculum_version=PRIMARY_CURRICULUM_VERSION,
                    title="Mira primary_1 正式课程",
                    target_spec=target_spec,
                    targets=targets,
                    variants_per_boundary=3,
                    now=10_000,
                )
                release = repository.get_release(
                    conn,
                    release_id=str(build["release_id"]),
                    for_update=True,
                )
                items = repository.list_build_items(
                    conn,
                    build_id=str(build["id"]),
                    for_update=True,
                )
            if wait_for_winner:
                loser_returned.set()
            return build, release, items, created

        with ThreadPoolExecutor(max_workers=2) as executor:
            winner = executor.submit(create_once, wait_for_winner=False)
            self.assertTrue(winner_inserted.wait(timeout=10))
            loser = executor.submit(create_once, wait_for_winner=True)
            self.assertTrue(loser_entered.wait(timeout=10))
            self.assertFalse(loser_returned.wait(timeout=0.25))
            allow_winner_commit.set()
            results = [winner.result(timeout=10), loser.result(timeout=10)]

        self.assertEqual(sorted(result[3] for result in results), [False, True])
        self.assertEqual(results[0][0]["id"], results[1][0]["id"])
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        self.assertEqual(len(set(connection_ids)), 2)
        self.assertEqual(isolation_levels, ["REPEATABLE-READ", "REPEATABLE-READ"])
        build_id = str(results[0][0]["id"])
        expected_items = set()
        for target in targets:
            for ordinal in range(1, 4):
                identity = (
                    f"{build_id}:{target['gradeCode']}:{target['subject']}:"
                    f"{target['skillId']}:{ordinal}"
                )
                digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                expected_items.add(
                    (
                        f"catalog_build_item_{digest[:24]}",
                        target["gradeCode"],
                        target["subject"],
                        target["skillId"],
                        ordinal,
                        f"catalog_gen_{digest[:48]}",
                    )
                )
        for result in results:
            actual_items = {
                (
                    item["id"],
                    item["grade_code"],
                    item["subject"],
                    item["skill_id"],
                    item["variant_ordinal"],
                    item["generation_request_id"],
                )
                for item in result[2]
            }
            self.assertEqual(actual_items, expected_items)
        self.assertEqual(self.question_adapter.generate_calls, [])
        self.assertEqual(self.classroom_adapter.calls, [])

    def test_same_concurrent_request_with_different_target_is_conflict(self):
        request_id = "catalog-concurrent-target-conflict"
        winner_inserted = Event()
        allow_winner_commit = Event()
        loser_entered = Event()
        loser_returned = Event()
        connection_ids = []
        isolation_levels = []

        # Pause at the repository boundary after all rows exist but before the
        # surrounding transaction commits; the loser must block on that winner.
        class PausingRepository(LearningCatalogRepository):
            def create_or_get_build(self, conn, **kwargs):
                result = super().create_or_get_build(conn, **kwargs)
                if result[1]:
                    winner_inserted.set()
                    if not allow_winner_commit.wait(timeout=10):
                        raise AssertionError("winner commit was not released")
                return result

        math_targets = [
            boundary.to_catalog_payload()
            for boundary in boundaries_for("primary_1", "math")
        ]
        english_targets = [
            boundary.to_catalog_payload()
            for boundary in boundaries_for("primary_1", "english")
        ]

        def create(targets, subject, *, loser):
            repository = PausingRepository(Database(self.database_url))
            with repository.transaction() as conn:
                session = conn.execute(
                    "SELECT CONNECTION_ID() AS connection_id, "
                    "@@transaction_isolation AS isolation_level"
                ).fetchone()
                connection_ids.append(session["connection_id"])
                isolation_levels.append(str(session["isolation_level"]).upper())
                if loser:
                    if not winner_inserted.wait(timeout=10):
                        raise AssertionError("winner did not insert")
                    loser_entered.set()
                try:
                    return repository.create_or_get_build(
                        conn,
                        request_id=request_id,
                        curriculum_version=PRIMARY_CURRICULUM_VERSION,
                        title="conflict",
                        target_spec={"subject": subject},
                        targets=targets,
                        variants_per_boundary=1,
                        now=10_100,
                    )
                finally:
                    if loser:
                        loser_returned.set()

        with ThreadPoolExecutor(max_workers=2) as executor:
            winner = executor.submit(create, math_targets, "math", loser=False)
            self.assertTrue(winner_inserted.wait(timeout=10))
            loser = executor.submit(create, english_targets, "english", loser=True)
            self.assertTrue(loser_entered.wait(timeout=10))
            self.assertFalse(loser_returned.wait(timeout=0.25))
            allow_winner_commit.set()
            winner_result = winner.result(timeout=10)
            with self.assertRaisesRegex(
                LearningCatalogBuildConflict, "another catalog target"
            ):
                loser.result(timeout=10)

        self.assertTrue(winner_result[1])
        self.assertEqual(len(set(connection_ids)), 2)
        self.assertEqual(isolation_levels, ["REPEATABLE-READ", "REPEATABLE-READ"])
        repository = LearningCatalogRepository(Database(self.database_url))
        with repository.transaction() as conn:
            items = repository.list_build_items(
                conn, build_id=str(winner_result[0]["id"])
            )
        self.assertEqual(
            {(item["subject"], item["skill_id"]) for item in items},
            {("math", target["skillId"]) for target in math_targets},
        )
        self.assertEqual(len(items), len(math_targets))

    def test_build_resumes_then_only_active_ready_release_is_recommended(self):
        created = self.service.create(
            {
                "requestId": "catalog-release-primary-3-math",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "variantsPerBoundary": 1,
                "allowPartial": True,
            }
        )
        self.assertTrue(created["created"])
        self.assertEqual(created["build"]["totalItemCount"], 3)
        build_id = created["build"]["id"]
        release_id = created["release"]["id"]

        first_slice = self.service.run(
            build_id, {"maxItems": 1, "retryFailed": True}
        )
        self.assertEqual(first_slice["build"]["readyItemCount"], 1)
        self.assertFalse(first_slice["canActivate"])

        resumed_service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=self.dynamic,
            lesson_package_service=self.lesson,
        )
        completed = resumed_service.run(
            build_id, {"maxItems": 10, "retryFailed": True}
        )
        self.assertEqual(completed["build"]["status"], "completed")
        self.assertEqual(completed["build"]["readyItemCount"], 3)
        self.assertTrue(completed["canActivate"])

        database = Database(self.database_url)
        repository = LearningRepository(database)
        boundary = boundaries_for("primary_3", "math")[0]
        with repository.transaction() as conn:
            before = repository.get_recommended_course(
                conn,
                family_id="family-catalog-test",
                child_id="child-catalog-test",
                grade_code="primary_3",
                learning_date="2026-09-01",
                subject="math",
                required_node_code=boundary.skill_id,
                content_origins=("openmaic_generated",),
                require_teaching_flow=True,
                require_catalog_release=True,
                curriculum_version=PRIMARY_CURRICULUM_VERSION,
                boundary_version=boundary.boundary_version,
            )
        self.assertIsNone(before)

        activated = resumed_service.activate(release_id)
        self.assertEqual(activated["release"]["status"], "active")
        with repository.transaction() as conn:
            recommended = repository.get_recommended_course(
                conn,
                family_id="family-catalog-test",
                child_id="child-catalog-test",
                grade_code="primary_3",
                learning_date="2026-09-01",
                subject="math",
                required_node_code=boundary.skill_id,
                content_origins=("openmaic_generated",),
                require_teaching_flow=True,
                require_catalog_release=True,
                curriculum_version=PRIMARY_CURRICULUM_VERSION,
                boundary_version=boundary.boundary_version,
            )
        self.assertIsNotNone(recommended)
        self.assertEqual(recommended["status"], "published")
        self.assertEqual(recommended["quality_status"], "released")
        self.assertEqual(recommended["boundary_version"], boundary.boundary_version)

        runtime_repository = OpenMaicRuntimeRepository(Database(self.database_url))
        with runtime_repository.transaction() as conn:
            runtime_candidate = runtime_repository.get_next_release_without_runtime(conn)
        self.assertIsNotNone(runtime_candidate)
        self.assertEqual(runtime_candidate["grade_code"], "primary_3")
        self.assertEqual(runtime_candidate["subject"], "math")
        self.assertIn(
            runtime_candidate["node_code"],
            {item.skill_id for item in boundaries_for("primary_3", "math")},
        )

    def test_039_retires_stale_pinyin_in_place_without_deleting_history(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "039_learning_catalog_releases.sql"
        ).read_text(encoding="utf-8")
        retirement = migration[migration.index("UPDATE learning_courses") :]
        self.assertIn("status = 'retired'", retirement)
        self.assertIn("retired_boundary_mismatch", retirement)
        self.assertIn("node_code = 'pinyin_syllables'", retirement)
        self.assertNotIn("DELETE", retirement.upper())
        self.assertNotIn("UPDATE tasks", retirement)
        self.assertNotIn("UPDATE learning_sessions", retirement)

    def test_failed_package_item_retries_without_regenerating_its_course(self):
        fail_once = _FailOnceLessonService(self.lesson)
        service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=self.dynamic,
            lesson_package_service=fail_once,
        )
        created = service.create(
            {
                "requestId": "catalog-release-recover-package",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        failed = service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        self.assertEqual(len(failed["processed"]), 3)
        self.assertEqual(failed["build"]["failedItemCount"], 0)
        self.assertEqual(failed["build"]["readyItemCount"], 2)
        self.assertTrue(
            all(item["attemptCount"] == 1 for item in failed["processed"]),
            failed,
        )
        package_failures = [
            item for item in failed["processed"] if item["status"] == "course_ready"
        ]
        self.assertEqual(len(package_failures), 1, failed)
        self.assertEqual(package_failures[0]["packageAttemptCount"], 1)
        generated_before_retry = len(self.question_adapter.generate_calls)

        recovered = service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        self.assertEqual(recovered["build"]["readyItemCount"], 3)
        self.assertEqual(recovered["build"]["status"], "completed")
        self.assertEqual(len(self.question_adapter.generate_calls), generated_before_retry)

    def test_content_rejection_retires_course_without_spending_package_attempt(self):
        gate = _RejectOnceCatalogValidator()
        service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=self.dynamic,
            lesson_package_service=self.lesson,
            catalog_validator=gate,
        )
        created = service.create(
            {
                "requestId": "catalog-content-reject-course-retry",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        first = service.run(
            created["build"]["id"],
            {"maxItems": 1, "retryFailed": True},
        )
        rejected = first["processed"][0]
        self.assertEqual(rejected["status"], "failed", first)
        self.assertEqual(rejected["attemptCount"], 1)
        self.assertEqual(rejected["packageAttemptCount"], 0)
        self.assertIsNone(rejected["courseId"])
        self.assertEqual(len(self.classroom_adapter.calls), 0)
        with Database(self.database_url).transaction() as conn:
            retired = conn.execute(
                """
                SELECT status, quality_status FROM learning_courses
                WHERE id = ? AND version = '1.0.0'
                """,
                (gate.rejected_course_id,),
            ).fetchone()
        self.assertEqual(retired["status"], "retired")
        self.assertEqual(retired["quality_status"], "rejected_content_gate")

        retry = service.run(
            created["build"]["id"],
            {"maxItems": 1, "retryFailed": True},
        )
        recovered = retry["processed"][0]
        self.assertEqual(recovered["status"], "ready", retry)
        self.assertEqual(recovered["attemptCount"], 2)
        self.assertEqual(recovered["packageAttemptCount"], 1)
        self.assertNotEqual(recovered["courseId"], gate.rejected_course_id)

    def test_failed_item_is_never_claimed_more_than_twice(self):
        always_fail = _AlwaysFailLessonService()
        service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=self.dynamic,
            lesson_package_service=always_fail,
        )
        created = service.create(
            {
                "requestId": "catalog-release-bounded-retry",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )

        first = service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        self.assertEqual(len(first["processed"]), 3)
        self.assertTrue(
            all(item["attemptCount"] == 1 for item in first["processed"]),
            first,
        )
        self.assertTrue(
            all(item["packageAttemptCount"] == 1 for item in first["processed"]),
            first,
        )
        self.assertTrue(
            all(item["status"] == "course_ready" for item in first["processed"]),
            first,
        )

        second = service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        self.assertEqual(len(second["processed"]), 3)
        self.assertTrue(
            all(item["attemptCount"] == 1 for item in second["processed"]),
            second,
        )
        self.assertTrue(
            all(item["packageAttemptCount"] == 2 for item in second["processed"]),
            second,
        )

        third = service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        self.assertEqual(third["processed"], [])
        self.assertEqual(always_fail.calls, 6)

    def test_concurrent_claim_is_unique_and_stale_retry_replays_same_attempt(self):
        created = self.service.create(
            {
                "requestId": "catalog-release-claim-lease",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        build_id = created["build"]["id"]
        repository = LearningCatalogRepository(Database(self.database_url))
        with repository.transaction() as conn:
            items = repository.list_build_items(conn, build_id=build_id)
        target_id = str(items[0]["id"])
        excluded_ids = tuple(str(item["id"]) for item in items[1:])
        barrier = Barrier(2)

        def claim_once():
            repository = LearningCatalogRepository(Database(self.database_url))
            barrier.wait()
            with repository.transaction() as conn:
                return repository.claim_next_item(
                    conn,
                    build_id=build_id,
                    now=10_000,
                    retry_failed=True,
                    stale_before=9_000,
                    excluding_item_ids=excluded_ids,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: claim_once(), range(2)))
        claimed = [claim for claim in claims if claim is not None]
        self.assertEqual(len(claimed), 1, claims)
        first = claimed[0]
        self.assertEqual(first["id"], target_id)
        self.assertEqual(first["attempt_count"], 1)
        self.assertEqual(first["claim_origin_status"], "pending")
        self.assertEqual(
            first["active_generation_request_id"], first["generation_request_id"]
        )

        with repository.transaction() as conn:
            repository.mark_item_failed(
                conn,
                item_id=target_id,
                error_code="test_transient_failure",
                error_message="test transient failure",
                expected_generation_request_id=str(
                    first["active_generation_request_id"]
                ),
                now=11_000,
            )
        with repository.transaction() as conn:
            retry = repository.claim_next_item(
                conn,
                build_id=build_id,
                now=12_000,
                retry_failed=True,
                stale_before=11_500,
                excluding_item_ids=excluded_ids,
            )
        self.assertIsNotNone(retry)
        self.assertEqual(retry["attempt_count"], 2)
        self.assertEqual(retry["claim_origin_status"], "failed")
        self.assertEqual(retry["prior_error_code"], "test_transient_failure")
        self.assertEqual(
            retry["prior_error_message_safe"], "test transient failure"
        )
        retry_request_id = retry["active_generation_request_id"]
        self.assertEqual(
            retry_request_id,
            f"{retry['generation_request_id']}.retry2",
        )

        with repository.transaction() as conn:
            stale = repository.claim_next_item(
                conn,
                build_id=build_id,
                now=30_000,
                retry_failed=True,
                stale_before=20_000,
                excluding_item_ids=excluded_ids,
            )
        self.assertIsNotNone(stale)
        self.assertEqual(stale["claimed_from_status"], "processing")
        self.assertEqual(stale["attempt_count"], 2)
        self.assertEqual(stale["active_generation_request_id"], retry_request_id)
        self.assertEqual(stale["prior_error_code"], "test_transient_failure")
        self.assertEqual(
            stale["prior_error_message_safe"], "test transient failure"
        )

        recorder = _RecordingFailedDynamicService()
        resumed_service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=recorder,
            lesson_package_service=_AlwaysFailLessonService(),
        )
        resumed = resumed_service._process_item(stale)
        self.assertEqual(resumed["status"], "failed")
        self.assertEqual(recorder.request_ids, [retry_request_id])
        self.assertEqual(
            recorder.generation_feedback,
            [None],
        )

    def test_external_failure_replays_same_attempt_only_when_explicit(self):
        created = self.service.create(
            {
                "requestId": "catalog-external-provider-recovery",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        build_id = created["build"]["id"]
        repository = LearningCatalogRepository(Database(self.database_url))
        with repository.transaction() as conn:
            items = repository.list_build_items(conn, build_id=build_id)
        target_id = str(items[0]["id"])
        excluded_ids = tuple(str(item["id"]) for item in items[1:])
        with repository.transaction() as conn:
            claimed = repository.claim_next_item(
                conn,
                build_id=build_id,
                now=10_000,
                retry_failed=False,
                retry_external=False,
                stale_before=9_000,
                excluding_item_ids=excluded_ids,
            )
        self.assertIsNotNone(claimed)
        request_id = str(claimed["active_generation_request_id"])
        with repository.transaction() as conn:
            external = repository.mark_item_external_failed(
                conn,
                item_id=target_id,
                error_code="generation_failed",
                error_message="Moonshot returned HTTP 429: quota exceeded",
                expected_generation_request_id=request_id,
                now=11_000,
            )
            build = repository.refresh_build_counts(
                conn,
                build_id=build_id,
                now=11_001,
            )
        self.assertEqual(external["status"], "external_failed")
        self.assertEqual(external["attempt_count"], 1)
        self.assertEqual(build["status"], "running")
        self.assertEqual(build["failed_item_count"], 0)

        with repository.transaction() as conn:
            passive = repository.claim_next_item(
                conn,
                build_id=build_id,
                now=12_000,
                retry_failed=False,
                retry_external=False,
                stale_before=11_500,
                excluding_item_ids=excluded_ids,
            )
        self.assertIsNone(passive)

        with repository.transaction() as conn:
            recovered = repository.claim_next_item(
                conn,
                build_id=build_id,
                now=13_000,
                retry_failed=False,
                retry_external=True,
                stale_before=12_500,
                excluding_item_ids=excluded_ids,
            )
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["claimed_from_status"], "external_failed")
        self.assertEqual(recovered["claim_origin_status"], "external_failed")
        self.assertEqual(recovered["attempt_count"], 1)
        self.assertEqual(recovered["active_generation_request_id"], request_id)
        self.assertNotIn("prior_error_code", recovered)

    def test_package_claim_is_unique_and_late_attempt_cannot_overwrite_new_lease(self):
        created = self.service.create(
            {
                "requestId": "catalog-package-atomic-claim",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        repository = LearningCatalogRepository(Database(self.database_url))
        with repository.transaction() as conn:
            items = repository.list_build_items(
                conn,
                build_id=created["build"]["id"],
            )
            course_claim = repository.claim_next_item(
                conn,
                build_id=created["build"]["id"],
                now=10_000,
                retry_failed=True,
                stale_before=9_000,
                excluding_item_ids=tuple(str(item["id"]) for item in items[1:]),
            )
        generated = self.dynamic.generate_for_skill(
            grade_code=str(course_claim["grade_code"]),
            subject=str(course_claim["subject"]),
            skill_id=str(course_claim["skill_id"]),
            attempts=1,
            request_id=str(course_claim["active_generation_request_id"]),
            enqueue_classroom=False,
        )
        self.assertTrue(generated.payload["ok"], generated.payload)
        with repository.transaction() as conn:
            leased = repository.mark_course_ready_for_content_gate(
                conn,
                item_id=str(course_claim["id"]),
                course_id=str(generated.payload["course"]["id"]),
                course_version=str(generated.payload["course"]["version"]),
                expected_generation_request_id=str(
                    course_claim["active_generation_request_id"]
                ),
                now=11_000,
            )
        self.assertEqual(leased["package_attempt_count"], 0)

        barrier = Barrier(2)

        def claim_package_once():
            local = LearningCatalogRepository(Database(self.database_url))
            barrier.wait()
            with local.transaction() as conn:
                return local.claim_package_for_item(
                    conn,
                    item_id=str(course_claim["id"]),
                    now=12_000,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: claim_package_once(), range(2)))
        winners = [claim for claim in claims if claim is not None]
        self.assertEqual(len(winners), 1, claims)
        first_request = str(winners[0]["active_package_request_id"])
        self.assertEqual(winners[0]["package_attempt_count"], 1)

        with repository.transaction() as conn:
            repository.mark_package_failed(
                conn,
                item_id=str(course_claim["id"]),
                error_code="package_attempt_one_failed",
                error_message="package attempt one failed",
                expected_request_id=first_request,
                now=13_000,
            )
        with repository.transaction() as conn:
            content_claim = repository.claim_next_item(
                conn,
                build_id=created["build"]["id"],
                now=14_000,
                retry_failed=True,
                stale_before=13_500,
                excluding_item_ids=tuple(str(item["id"]) for item in items[1:]),
            )
            second = repository.claim_package_for_item(
                conn,
                item_id=str(course_claim["id"]),
                now=14_001,
            )
        self.assertEqual(content_claim["package_claim_kind"], "content_gate")
        self.assertEqual(second["package_attempt_count"], 2)
        second_request = str(second["active_package_request_id"])
        self.assertNotEqual(second_request, first_request)

        with repository.transaction() as conn:
            late = repository.mark_item_ready(
                conn,
                item_id=str(course_claim["id"]),
                package_id="late-package",
                package_version=1,
                expected_request_id=first_request,
                now=15_000,
            )
        self.assertEqual(late["status"], "processing")
        self.assertEqual(late["active_package_request_id"], second_request)

    def test_late_stale_course_worker_cannot_downgrade_winner_ready_item(self):
        created = self.service.create(
            {
                "requestId": "catalog-course-late-worker-cas",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        repository = LearningCatalogRepository(Database(self.database_url))
        with repository.transaction() as conn:
            items = repository.list_build_items(
                conn,
                build_id=created["build"]["id"],
            )
        excluded = tuple(str(item["id"]) for item in items[1:])
        with repository.transaction() as conn:
            original = repository.claim_next_item(
                conn,
                build_id=created["build"]["id"],
                now=10_000,
                retry_failed=True,
                stale_before=9_000,
                excluding_item_ids=excluded,
            )
        with repository.transaction() as conn:
            recovered = repository.claim_next_item(
                conn,
                build_id=created["build"]["id"],
                now=30_000,
                retry_failed=True,
                stale_before=20_000,
                excluding_item_ids=excluded,
            )
        self.assertEqual(
            recovered["active_generation_request_id"],
            original["active_generation_request_id"],
        )
        generated = self.dynamic.generate_for_skill(
            grade_code=str(recovered["grade_code"]),
            subject=str(recovered["subject"]),
            skill_id=str(recovered["skill_id"]),
            attempts=1,
            request_id=str(recovered["active_generation_request_id"]),
            enqueue_classroom=False,
        )
        self.assertTrue(generated.payload["ok"], generated.payload)
        with repository.transaction() as conn:
            winner = repository.mark_course_ready_for_content_gate(
                conn,
                item_id=str(recovered["id"]),
                course_id=str(generated.payload["course"]["id"]),
                course_version=str(generated.payload["course"]["version"]),
                expected_generation_request_id=str(
                    recovered["active_generation_request_id"]
                ),
                now=31_000,
            )
            package = repository.claim_package_for_item(
                conn,
                item_id=str(recovered["id"]),
                now=31_001,
            )
            ready = repository.mark_item_ready(
                conn,
                item_id=str(recovered["id"]),
                package_id="winner-package",
                package_version=1,
                expected_request_id=str(package["active_package_request_id"]),
                now=31_002,
            )
        self.assertEqual(winner["status"], "processing")
        self.assertEqual(ready["status"], "ready")

        with repository.transaction() as conn:
            late_course = repository.mark_course_ready_for_content_gate(
                conn,
                item_id=str(original["id"]),
                course_id=str(generated.payload["course"]["id"]),
                course_version=str(generated.payload["course"]["version"]),
                expected_generation_request_id=str(
                    original["active_generation_request_id"]
                ),
                now=32_000,
            )
            late_failure = repository.mark_item_failed(
                conn,
                item_id=str(original["id"]),
                error_code="late_worker_failed",
                error_message="late worker failed",
                expected_generation_request_id=str(
                    original["active_generation_request_id"]
                ),
                now=32_001,
            )
        self.assertIsNone(late_course)
        self.assertEqual(late_failure["status"], "ready")
        self.assertEqual(late_failure["package_id"], "winner-package")

    def test_media_pending_package_keeps_course_ready_without_failure(self):
        pending_once = _PendingOnceLessonService(self.lesson)
        service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=self.dynamic,
            lesson_package_service=pending_once,
        )
        created = service.create(
            {
                "requestId": "catalog-release-media-pending",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        pending = service.run(
            created["build"]["id"],
            {"maxItems": 1, "retryFailed": True},
        )
        self.assertEqual(pending["build"]["failedItemCount"], 0)
        self.assertEqual(pending["processed"][0]["status"], "course_ready")
        generated_before_resume = len(self.question_adapter.generate_calls)

        resumed = service.run(
            created["build"]["id"],
            {"maxItems": 1, "retryFailed": True},
        )
        self.assertEqual(resumed["build"]["readyItemCount"], 1)
        self.assertEqual(resumed["processed"][0]["attemptCount"], 1)
        self.assertEqual(
            len(self.question_adapter.generate_calls),
            generated_before_resume,
        )

    def test_activation_rejects_required_media_that_has_not_passed_review(self):
        created = self.service.create(
            {
                "requestId": "catalog-release-unreviewed-media",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        completed = self.service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        self.assertEqual(completed["build"]["status"], "completed", completed)
        first_item = completed["processed"][0]
        timestamp = now_ms()
        with Database(self.database_url).transaction() as conn:
            conn.execute(
                """
                INSERT INTO learning_media_assets(
                  id, kind, storage_key, content_hash, mime_type, byte_size,
                  scan_status, moderation_status, transcode_status, status,
                  source_type, created_at, updated_at
                )
                VALUES (
                  'asset_catalog_unreviewed_audio', 'audio',
                  'catalog-test/unreviewed.wav',
                  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                  'audio/wav', 128, 'passed', 'passed', 'not_required',
                  'ready', 'catalog_test', ?, ?
                )
                """,
                (timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO learning_media_asset_variants(
                  asset_id, variant_key, storage_key, content_hash, mime_type,
                  byte_size, status, created_at, updated_at
                )
                VALUES (
                  'asset_catalog_unreviewed_audio', 'original',
                  'catalog-test/unreviewed.wav',
                  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                  'audio/wav', 128, 'ready', ?, ?
                )
                """,
                (timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO learning_lesson_package_assets(
                  package_id, package_version, asset_id, scene_id,
                  usage_kind, required_asset
                )
                VALUES (?, ?, 'asset_catalog_unreviewed_audio',
                  'scene-teach', 'narration', 1)
                """,
                (first_item["packageId"], first_item["packageVersion"]),
            )

        blocked_status = self.service.status(created["build"]["id"])
        self.assertFalse(blocked_status["canActivate"])
        self.assertEqual(blocked_status["build"]["mediaPendingItemCount"], 1)
        self.assertEqual(
            blocked_status["build"]["releaseReadyItemCount"],
            blocked_status["build"]["totalItemCount"] - 1,
        )
        with self.assertRaises(ApiError) as raised:
            self.service.activate(created["release"]["id"])
        self.assertEqual(raised.exception.code, "catalog_release_not_ready")
        self.assertEqual(raised.exception.status_code, 409)

        with Database(self.database_url).transaction() as conn:
            conn.execute(
                """
                INSERT INTO learning_media_quality_reviews(
                  id, asset_id, review_kind, required_review, status,
                  reviewer_type, reviewer_id, findings_json, reviewed_at,
                  created_at, updated_at
                )
                VALUES (
                  'review_catalog_unreviewed_audio',
                  'asset_catalog_unreviewed_audio', 'manual_pronunciation', 1,
                  'approved', 'human', 'catalog-reviewer', '{}', ?, ?, ?
                )
                """,
                (timestamp, timestamp, timestamp),
            )
        activated = self.service.activate(created["release"]["id"])
        self.assertEqual(activated["release"]["status"], "active")

    def test_stored_auto_validated_course_is_rechecked_before_release_activation(self):
        created = self.service.create(
            {
                "requestId": "catalog-release-activation-content-recheck",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        completed = self.service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        self.assertTrue(completed["canActivate"], completed)
        checker = _RejectingActivationValidator()
        self.service.catalog_validator = checker

        with self.assertRaises(ApiError) as raised:
            self.service.activate(created["release"]["id"])
        self.assertEqual(raised.exception.code, "catalog_release_not_ready")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertGreater(checker.calls, 0)
        with Database(self.database_url).transaction() as conn:
            release = self.service.repository.get_release(
                conn,
                release_id=created["release"]["id"],
            )
        self.assertEqual(release["status"], "draft")

    def test_activation_rejects_package_compiled_from_another_course_hash(self):
        created = self.service.create(
            {
                "requestId": "catalog-release-activation-hash-recheck",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            }
        )
        completed = self.service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        first = completed["processed"][0]
        with Database(self.database_url).transaction() as conn:
            conn.execute(
                """
                UPDATE learning_lesson_packages
                SET source_course_content_hash = ?
                WHERE id = ? AND version = ?
                """,
                ("0" * 64, first["packageId"], first["packageVersion"]),
            )

        with self.assertRaises(ApiError) as raised:
            self.service.activate(created["release"]["id"])
        self.assertEqual(raised.exception.code, "catalog_release_not_ready")
        self.assertEqual(raised.exception.status_code, 409)

    def test_internal_catalog_api_is_guarded_and_additive(self):
        token = "catalog-release-internal-token"
        app = create_app({**self.config, "INTERNAL_API_TOKEN": token})
        app.extensions["mira_learning_catalog_release_service"] = self.service
        client = app.test_client()
        unauthorized = client.post(
            "/internal/learning/content/catalog/builds",
            json={"requestId": "catalog-api-unauthorized"},
        )
        self.assertEqual(unauthorized.status_code, 401, unauthorized.json)
        headers = {
            "X-Mira-Internal-Token": token,
            "X-Mira-Internal-Source": "catalog-release-test",
        }
        created = client.post(
            "/internal/learning/content/catalog/builds",
            json={
                "requestId": "catalog-api-primary-3-math",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "allowPartial": True,
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 201, created.json)
        build_id = created.json["build"]["id"]
        release_id = created.json["release"]["id"]
        status = client.get(
            f"/internal/learning/content/catalog/builds/{build_id}",
            headers=headers,
        )
        self.assertEqual(status.status_code, 200, status.json)
        self.assertEqual(status.json["build"]["totalItemCount"], 3)
        run = client.post(
            f"/internal/learning/content/catalog/builds/{build_id}/run",
            json={"maxItems": 1},
            headers=headers,
        )
        self.assertEqual(run.status_code, 200, run.json)
        self.assertEqual(run.json["build"]["readyItemCount"], 1)
        not_ready = client.post(
            f"/internal/learning/content/catalog/releases/{release_id}/activate",
            headers=headers,
        )
        self.assertEqual(not_ready.status_code, 409, not_ready.json)
        self.assertEqual(not_ready.json["error"], "catalog_release_not_ready")


class _FailOnceLessonService:
    def __init__(self, delegate):
        self.delegate = delegate
        self.failed = False

    def generate(self, data):
        if not self.failed:
            self.failed = True
            return SimpleNamespace(
                payload={
                    "ok": False,
                    "status": "failed",
                    "error": "temporary_media_pipeline_failure",
                    "message": "媒体处理暂时失败",
                }
            )
        return self.delegate.generate(data)


class _AlwaysFailLessonService:
    def __init__(self):
        self.calls = 0

    def generate(self, data):
        self.calls += 1
        return SimpleNamespace(
            payload={
                "ok": False,
                "status": "failed",
                "error": "permanent_classroom_failure",
                "message": "课堂生成持续失败",
            }
        )


class _RecordingFailedDynamicService:
    def __init__(self):
        self.request_ids = []
        self.generation_feedback = []

    def generate_for_skill(
        self,
        *,
        grade_code,
        subject,
        skill_id,
        attempts,
        request_id,
        enqueue_classroom,
        generation_feedback=None,
        retry_transient_failed=False,
    ):
        self.assert_catalog_managed = enqueue_classroom is False
        self.request_ids.append(request_id)
        self.generation_feedback.append(generation_feedback)
        self.retry_transient_failed = retry_transient_failed
        return SimpleNamespace(
            payload={
                "ok": False,
                "error": "recorded_generation_failure",
                "message": "recorded generation failure",
            }
        )


class _PendingOnceLessonService:
    def __init__(self, delegate):
        self.delegate = delegate
        self.pending = True

    def generate(self, data):
        if self.pending:
            self.pending = False
            return SimpleNamespace(
                payload={
                    "ok": False,
                    "status": "media_pending",
                    "message": "媒体资产正在生成和审核",
                }
            )
        return self.delegate.generate(data)


class _RejectingActivationValidator:
    def __init__(self):
        self.calls = 0

    def validate_course(self, course):
        self.calls += 1
        raise ApiError(
            "invalid_learning_catalog",
            "stored course failed activation content recheck",
            503,
        )


class _RejectOnceCatalogValidator:
    def __init__(self):
        self.delegate = LearningCatalogValidator()
        self.rejected_course_id = None

    def validate_course(self, course):
        if self.rejected_course_id is None:
            self.rejected_course_id = str(course["id"])
            raise ApiError(
                "invalid_learning_catalog",
                "deterministic release content gate rejected the course",
                503,
            )
        self.delegate.validate_course(course)


if __name__ == "__main__":
    unittest.main()
