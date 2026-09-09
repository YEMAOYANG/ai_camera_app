from __future__ import annotations

import hashlib
import json
import threading
import unittest
from unittest import mock

import pymysql

from core.database import Database
from content.teacher_profiles import get_formal_runtime_teacher_contract
from repositories.learning_catalog_repository import (
    LearningCatalogActivationError,
    LearningCatalogRepository,
)
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from repositories.lesson_package_repository import LessonPackageRepository
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from integrations.openmaic_formal_media import generation_options
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.openmaic_full_runtime_service import (
    FORMAL_REQUIRED_FEATURES,
    OpenMaicFullRuntimeService,
    OpenMaicRuntimeServiceError,
)
from services.lesson_package_service import LessonPackageService
from services.lesson_package_validator import LessonPackageValidator
from tests.support import fresh_test_config


def _formal_course_content(seed: str) -> str:
    questions = []
    for ordinal in range(1, 6):
        questions.append(
            {
                "id": f"{seed}-q{ordinal}",
                "type": "numeric",
                "prompt": f"第{ordinal}题：一个十和{ordinal}个一是多少？",
                "answer": str(10 + ordinal),
                "skill": "number_sense_20",
                "hint": "先看十，再数一。",
                "explanation": "把一个十和几个一合起来。",
                "verificationExpression": f"10+{ordinal}",
                "evaluation": {
                    "expected": str(10 + ordinal),
                    "normalization": ["trim"],
                },
            }
        )
    ids = [question["id"] for question in questions]
    return json.dumps(
        {
            "schemaVersion": "mira.learning.course.v1",
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "sourceAuthority": {
                "basis": "provided_skill_boundary",
                "contentOrigin": "openmaic_kimi_candidate",
                "textbookDependency": "none",
            },
            "reviewPolicy": "programmatic_guarded",
            "intro": "学习一个十和几个一组成十几。",
            "estimatedMinutes": 10,
            "questions": questions,
            "teachingFlow": {
                "schemaVersion": "mira.learning.teaching-flow.v1",
                "teach": {
                    "title": "一个十和几个一",
                    "sayText": "先把十个看成一个十，再数剩下的几个一。",
                    "keyPoints": ["十个一是一个十", "十和几组成十几"],
                },
                "demoQuestionId": ids[0],
                "guidedQuestionIds": ids[1:3],
                "independentQuestionIds": ids[3:5],
                "recap": {"sayText": "一个十和几个一组成十几。"},
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class LearningCurriculumClassroomRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)
        self.catalog = LearningCatalogRepository(self.database)
        self.preparations = LearningCurriculumPreparationRepository(self.database)
        self.packages = LessonPackageRepository(self.database)
        self.runtimes = OpenMaicRuntimeRepository(self.database)

    def test_repositories_expose_formal_publication_boundaries(self) -> None:
        self.assertTrue(callable(self.catalog.reserve_classroom_item_receipt))
        self.assertTrue(callable(self.catalog.record_classroom_item_evidence))
        self.assertTrue(callable(self.catalog.activate_grade_release_pointer))
        self.assertTrue(callable(self.catalog.get_active_grade_release_pointer))
        self.assertTrue(callable(self.runtimes.bind_candidate_runtime))
        self.assertTrue(callable(self.preparations.complete_formal_ready))

    def test_formal_candidate_attempts_are_atomic_idempotent_and_capped(self) -> None:
        fixture, candidate = self._seed_staged_formal_candidate(
            "reserve-attempts"
        )
        manifest = self._formal_runtime_feature_manifest(candidate)

        def attempt_manifest(ordinal):
            value = json.loads(json.dumps(manifest))
            value['generationContract']['runtimeRequestId'] = f'formal-reserve-attempts-request-{ordinal}'
            return value

        def reserve(attempt: int):
            with self.database.transaction() as conn:
                return self.runtimes.reserve_candidate_runtime(
                    conn,
                    runtime_id=(
                        f"formal-reserve-attempts-candidate-attempt-{attempt}"
                    ),
                    runtime_request_id=f"formal-reserve-attempts-request-{attempt}",
                    build_item_id=str(fixture["item_id"]),
                    course_id=str(fixture["course_id"]),
                    course_version="1",
                    package_id=str(candidate["package_id"]),
                    package_version=1,
                    target_fingerprint=str(fixture["fingerprint"]),
                    feature_manifest=attempt_manifest(attempt),
                    now=3_000 + attempt,
                )

        first, created = reserve(1)
        self.assertTrue(created)
        self.assertEqual(first["attempt_ordinal"], 1)
        self.assertEqual(first["provider_attempt_ordinal"], 1)
        self.assertIsNone(first["retry_of_runtime_id"])
        self.assertEqual(first["candidate_build_item_id"], fixture["item_id"])

        with self.database.transaction() as conn:
            replay, replay_created = self.runtimes.reserve_candidate_runtime(
                conn,
                runtime_id="must-not-win",
                runtime_request_id="formal-reserve-attempts-request-1",
                build_item_id=str(fixture["item_id"]),
                course_id=str(fixture["course_id"]),
                course_version="1",
                package_id=str(candidate["package_id"]),
                package_version=1,
                target_fingerprint=str(fixture["fingerprint"]),
                feature_manifest=attempt_manifest(1),
                now=3_010,
            )
        self.assertFalse(replay_created)
        self.assertEqual(replay["id"], first["id"])

        previous = first
        for ordinal in (2, 3):
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_openmaic_runtime_classrooms SET "
                    "upstream_job_id = ?, status = 'failed', "
                    "quality_status = 'rejected', "
                    "error_code = 'openmaic_formal_generation_failed', "
                    "error_message_safe = 'safe failure', updated_at = ? "
                    "WHERE id = ?",
                    (f"formal-upstream-job-{ordinal - 1}", 3_020 + ordinal, previous["id"]),
                )
            current, current_created = reserve(ordinal)
            self.assertTrue(current_created)
            self.assertEqual(current["attempt_ordinal"], ordinal)
            self.assertEqual(current["provider_attempt_ordinal"], ordinal)
            self.assertEqual(
                current["candidate_build_item_id"], fixture["item_id"]
            )
            self.assertEqual(current["retry_of_runtime_id"], previous["id"])
            self.assertEqual(
                current["retry_reason"], f"formal_candidate_retry_{ordinal}"
            )
            self.assertEqual(
                current["expected_previous_job_id"],
                f"formal-upstream-job-{ordinal - 1}",
            )
            previous = current

        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_openmaic_runtime_classrooms SET "
                "upstream_job_id = 'formal-upstream-job-3', status = 'failed', "
                "quality_status = 'rejected', "
                "error_code = 'openmaic_formal_generation_failed', "
                "error_message_safe = 'safe failure', updated_at = 3040 "
                "WHERE id = ?",
                (previous["id"],),
            )
        with self.assertRaisesRegex(ValueError, "attempt limit"):
            reserve(4)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_openmaic_runtime_classrooms "
                "WHERE candidate_build_item_id = ?",
                (fixture["item_id"],),
            ).fetchone()
        self.assertEqual(count["count"], 3)

    def test_formal_candidate_same_request_converges_across_connections(self) -> None:
        fixture, candidate = self._seed_staged_formal_candidate(
            "reserve-concurrent"
        )
        manifest = self._formal_runtime_feature_manifest(candidate)
        manifest['generationContract']['runtimeRequestId'] = 'formal-concurrent-request-1'

        barrier = threading.Barrier(2)
        results: list[tuple[str, bool]] = []
        errors: list[BaseException] = []

        def worker(ordinal: int) -> None:
            try:
                barrier.wait(timeout=5)
                with self.database.transaction() as conn:
                    row, created = self.runtimes.reserve_candidate_runtime(
                        conn,
                        runtime_id=f"formal-concurrent-runtime-{ordinal}",
                        runtime_request_id="formal-concurrent-request-1",
                        build_item_id=str(fixture["item_id"]),
                        course_id=str(fixture["course_id"]),
                        course_version="1",
                        package_id=str(candidate["package_id"]),
                        package_version=1,
                        target_fingerprint=str(fixture["fingerprint"]),
                        feature_manifest=manifest,
                        now=4_000 + ordinal,
                    )
                    results.append((str(row["id"]), created))
            except BaseException as exc:  # surfaced below with its exact type
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(ordinal,)) for ordinal in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(len({runtime_id for runtime_id, _created in results}), 1)
        self.assertEqual(sum(1 for _runtime_id, created in results if created), 1)

    def test_candidate_runtime_rejects_a_legacy_published_package(self) -> None:
        fixture = self._seed_formal_candidate_handoff(
            "legacy-package-injection"
        )
        request_id = "formal-legacy-injection-request"

        with self.assertRaisesRegex(ValueError, "formal candidate package"):
            with self.database.transaction() as conn:
                self.runtimes.reserve_candidate_runtime(
                    conn,
                    runtime_id="formal-legacy-injection-runtime",
                    runtime_request_id="formal-legacy-injection-request",
                    build_item_id=str(fixture["item_id"]),
                    course_id=str(fixture["course_id"]),
                    course_version="1",
                    package_id=str(fixture["package_id"]),
                    package_version=1,
                    target_fingerprint=str(fixture["fingerprint"]),
                    feature_manifest={"schemaVersion": "formal-test.v1"},
                    now=2_500,
                )

        class GuardClient:
            def __init__(self):
                self.readiness_calls = 0
                self.query_calls = []
                self.start_calls = []

            def formal_generation_readiness(self):
                self.readiness_calls += 1
                return {"ready": True}

            def get_generation_job_by_request_id(self, runtime_request_id):
                self.query_calls.append(runtime_request_id)
                raise AssertionError("legacy package must stop before query")

            def start_generation(self, **kwargs):
                self.start_calls.append(kwargs)
                raise AssertionError("legacy package must stop before POST")

        client = GuardClient()
        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.generation_enabled = True
        service.public_url = "https://classroom.mira.test"
        service.video_export_enabled = False
        service.repository = self.runtimes
        service.client = client
        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.issue_candidate_generation(
                build_item_id=str(fixture["item_id"]),
                course_id=str(fixture["course_id"]),
                course_version="1",
                package_id=str(fixture["package_id"]),
                package_version=1,
                target_fingerprint=str(fixture["fingerprint"]),
                runtime_request_id=request_id,
            )
        self.assertEqual(
            raised.exception.code, "openmaic_formal_candidate_conflict"
        )
        self.assertEqual(client.readiness_calls, 1)
        self.assertEqual(client.query_calls, [])
        self.assertEqual(client.start_calls, [])
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count_value FROM "
                "learning_openmaic_runtime_classrooms "
                "WHERE request_id = 'formal-legacy-injection-request'"
            ).fetchone()
        self.assertEqual(int(count["count_value"]), 0)

    def test_candidate_runtime_rechecks_package_fingerprint_under_lock(self) -> None:
        fixture = self._seed_formal_candidate_handoff("package-fingerprint-drift")
        issued = []

        class Runtime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                issued.append(kwargs)
                return {
                    "ok": True,
                    "runtime": {
                        "id": "not-persisted-by-stub",
                        "requestId": kwargs["runtime_request_id"],
                        "status": "generating",
                    },
                }

        service = object.__new__(LessonPackageService)
        service.repository = self.packages
        service.validator = LessonPackageValidator()
        result = service.process_next_formal_candidate(Runtime())
        self.assertEqual(len(issued), 1)
        package_id = str(result.payload["package"]["id"])
        wrong_fingerprint = "0" * 64
        with self.database.transaction() as conn:
            package = self.packages.get_package_any_status(
                conn, package_id=package_id, package_version=1
            )
            public_payload = self.packages.decode_json(
                package["public_payload_json"]
            )
            public_payload["targetFingerprint"] = wrong_fingerprint
            public_json = self.packages.encode_json(public_payload)
            private_row = conn.execute(
                "SELECT * FROM learning_lesson_package_private "
                "WHERE package_id = ? AND package_version = 1 FOR UPDATE",
                (package_id,),
            ).fetchone()
            private_payload = self.packages.decode_json(private_row["payload_json"])
            private_payload["targetFingerprint"] = wrong_fingerprint
            private_json = self.packages.encode_json(private_payload)
            conn.execute(
                "UPDATE learning_lesson_packages SET public_payload_json = ?, "
                "public_content_hash = ?, private_content_hash = ? "
                "WHERE id = ? AND version = 1",
                (
                    public_json,
                    hashlib.sha256(public_json.encode()).hexdigest(),
                    hashlib.sha256(private_json.encode()).hexdigest(),
                    package_id,
                ),
            )
            conn.execute(
                "UPDATE learning_lesson_package_private SET payload_json = ?, "
                "content_hash = ? WHERE package_id = ? AND package_version = 1",
                (
                    private_json,
                    hashlib.sha256(private_json.encode()).hexdigest(),
                    package_id,
                ),
            )

        with self.assertRaisesRegex(ValueError, "formal candidate package"):
            with self.database.transaction() as conn:
                self.runtimes.reserve_candidate_runtime(
                    conn,
                    runtime_id="formal-package-fingerprint-drift-runtime",
                    **issued[0],
                    feature_manifest={"schemaVersion": "formal-test.v1"},
                    now=8_100,
                )

    def test_candidate_runtime_rechecks_release_and_plan_authority_before_post(self):
        for drift in ("retired_release", "superseded_plan"):
            with self.subTest(drift=drift):
                fixture = self._seed_formal_candidate_handoff(
                    f"runtime-authority-{drift}"
                )
                staged_calls = []

                class StagingRuntime:
                    @staticmethod
                    def issue_candidate_generation(**kwargs):
                        staged_calls.append(kwargs)
                        return {
                            "ok": True,
                            "runtime": {
                                "id": "staging-only",
                                "requestId": kwargs["runtime_request_id"],
                                "status": "generating",
                            },
                        }

                package_service = object.__new__(LessonPackageService)
                package_service.repository = self.packages
                package_service.validator = LessonPackageValidator()
                package_service.process_next_formal_candidate(StagingRuntime())
                self.assertEqual(len(staged_calls), 1)

                with self.database.transaction() as conn:
                    if drift == "retired_release":
                        conn.execute(
                            "UPDATE learning_catalog_releases SET retired_at = 8200 "
                            "WHERE id = ?",
                            (fixture["release_id"],),
                        )
                    else:
                        conn.execute(
                            "UPDATE learning_curriculum_preparation_plans "
                            "SET status = 'superseded', stage = 'completed', "
                            "completed_at = 8300, superseded_at = 8300, "
                            "next_run_at = NULL, updated_at = 8300 WHERE id = ?",
                            (fixture["plan_id"],),
                        )

                class GuardClient:
                    def __init__(self):
                        self.query_calls = []
                        self.start_calls = []

                    @staticmethod
                    def formal_generation_readiness():
                        return {"ready": True}

                    def get_generation_job_by_request_id(self, request_id):
                        self.query_calls.append(request_id)
                        raise AssertionError("authority drift must stop before query")

                    def start_generation(self, **kwargs):
                        self.start_calls.append(kwargs)
                        raise AssertionError("authority drift must stop before POST")

                client = GuardClient()
                runtime_service = object.__new__(OpenMaicFullRuntimeService)
                runtime_service.enabled = True
                runtime_service.generation_enabled = True
                runtime_service.public_url = "https://classroom.mira.test"
                runtime_service.video_export_enabled = False
                runtime_service.repository = self.runtimes
                runtime_service.client = client

                with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
                    runtime_service.issue_candidate_generation(**staged_calls[0])
                self.assertEqual(
                    raised.exception.code, "openmaic_formal_candidate_conflict"
                )
                self.assertEqual(client.query_calls, [])
                self.assertEqual(client.start_calls, [])
                with self.database.transaction() as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) AS count_value FROM "
                        "learning_openmaic_runtime_classrooms "
                        "WHERE request_id = ?",
                        (staged_calls[0]["runtime_request_id"],),
                    ).fetchone()
                self.assertEqual(int(count["count_value"]), 0)

    def test_candidate_completion_rechecks_authority_after_dispatch_before_receipt(self):
        fixture = self._seed_formal_candidate_handoff(
            "completion-authority-drift"
        )
        staged_calls = []

        class StagingRuntime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                staged_calls.append(kwargs)
                return {
                    "ok": True,
                    "runtime": {
                        "id": "staging-only",
                        "requestId": kwargs["runtime_request_id"],
                        "status": "generating",
                    },
                }

        package_service = object.__new__(LessonPackageService)
        package_service.repository = self.packages
        package_service.validator = LessonPackageValidator()
        package_service.process_next_formal_candidate(StagingRuntime())
        self.assertEqual(len(staged_calls), 1)
        kwargs = staged_calls[0]
        with self.database.transaction() as conn:
            runtime, created = self.runtimes.reserve_candidate_runtime(
                conn,
                runtime_id="formal-completion-authority-runtime",
                feature_manifest=self._formal_runtime_feature_manifest(kwargs),
                now=8_400,
                **kwargs,
            )
            self.assertTrue(created)
            self.runtimes.mark_generating(
                conn,
                runtime_id=str(runtime["id"]),
                upstream_job_id="formal-completion-authority-upstream",
                now=8_410,
            )
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_releases SET retired_at = 8420 "
                "WHERE id = ?",
                (fixture["release_id"],),
            )

        with self.assertRaisesRegex(ValueError, "completion authority"):
            with self.database.transaction() as conn:
                self.runtimes.assert_candidate_completion_authority(
                    conn,
                    runtime_id=str(runtime["id"]),
                    build_item_id=str(fixture["item_id"]),
                    target_fingerprint=str(fixture["fingerprint"]),
                    expected_upstream_job_id=(
                        "formal-completion-authority-upstream"
                    ),
                )
        with self.database.transaction() as conn:
            receipt = self.catalog.get_classroom_item_receipt(
                conn, build_item_id=str(fixture["item_id"])
            )
            current = self.runtimes.get_runtime_classroom(
                conn, runtime_id=str(runtime["id"])
            )
        self.assertIsNone(receipt)
        self.assertEqual(current["status"], "generating")
        self.assertEqual(
            current["upstream_job_id"], "formal-completion-authority-upstream"
        )

    def test_candidate_completion_rechecks_course_and_package_after_dispatch(self):
        for drift in (
            "retired_course",
            "retired_package",
            "content_drift",
            "item_course_drift",
            "item_curriculum_drift",
            "runtime_manifest_drift",
            "runtime_request_drift",
            "upstream_job_drift",
        ):
            with self.subTest(drift=drift):
                fixture = self._seed_formal_candidate_handoff(
                    f"completion-package-{drift}"
                )
                staged_calls = []

                class StagingRuntime:
                    @staticmethod
                    def issue_candidate_generation(**kwargs):
                        staged_calls.append(kwargs)
                        return {
                            "ok": True,
                            "runtime": {
                                "id": "staging-only",
                                "requestId": kwargs["runtime_request_id"],
                                "status": "generating",
                            },
                        }

                package_service = object.__new__(LessonPackageService)
                package_service.repository = self.packages
                package_service.validator = LessonPackageValidator()
                package_service.process_next_formal_candidate(StagingRuntime())
                self.assertEqual(len(staged_calls), 1)
                kwargs = staged_calls[0]
                with self.database.transaction() as conn:
                    runtime, created = self.runtimes.reserve_candidate_runtime(
                        conn,
                        runtime_id=f"formal-completion-{drift}-runtime",
                        feature_manifest=self._formal_runtime_feature_manifest(kwargs),
                        now=8_500,
                        **kwargs,
                    )
                    self.assertTrue(created)
                    self.runtimes.mark_generating(
                        conn,
                        runtime_id=str(runtime["id"]),
                        upstream_job_id=f"formal-completion-{drift}-upstream",
                        now=8_510,
                    )
                with self.database.transaction() as conn:
                    if drift == "retired_course":
                        conn.execute(
                            "UPDATE learning_courses SET retired_at = 8520 "
                            "WHERE id = ? AND version = '1'",
                            (fixture["course_id"],),
                        )
                    elif drift == "retired_package":
                        conn.execute(
                            "UPDATE learning_lesson_packages SET retired_at = 8520 "
                            "WHERE id = ? AND version = 1",
                            (kwargs["package_id"],),
                        )
                    elif drift == "content_drift":
                        conn.execute(
                            "UPDATE learning_courses SET content_json = ? "
                            "WHERE id = ? AND version = '1'",
                            (
                                _formal_course_content(
                                    f"drifted-{fixture['course_id']}"
                                ),
                                fixture["course_id"],
                            ),
                        )
                    elif drift == "item_course_drift":
                        second_item = conn.execute(
                            "SELECT course_id, course_version FROM "
                            "learning_catalog_build_items WHERE id = ? FOR UPDATE",
                            (fixture["item_ids"][1],),
                        ).fetchone()
                        conn.execute(
                            "UPDATE learning_catalog_build_items "
                            "SET course_id = ?, course_version = ? WHERE id = ?",
                            (
                                second_item["course_id"],
                                second_item["course_version"],
                                fixture["item_id"],
                            ),
                        )
                    elif drift == "item_curriculum_drift":
                        conn.execute(
                            "UPDATE learning_catalog_build_items "
                            "SET curriculum_version = 'drifted-curriculum' "
                            "WHERE id = ?",
                            (fixture["item_id"],),
                        )
                    elif drift == "runtime_manifest_drift":
                        conn.execute(
                            "UPDATE learning_openmaic_runtime_classrooms SET "
                            "feature_manifest_json = JSON_SET(" 
                            "feature_manifest_json, "
                            "'$.generationContract.course.id', 'wrong-course') "
                            "WHERE id = ?",
                            (runtime["id"],),
                        )
                    elif drift == "runtime_request_drift":
                        conn.execute(
                            "UPDATE learning_openmaic_runtime_classrooms "
                            "SET request_id = 'mira-formal:binding-drift:1' "
                            "WHERE id = ?",
                            (runtime["id"],),
                        )
                    else:
                        conn.execute(
                            "UPDATE learning_openmaic_runtime_classrooms "
                            "SET upstream_job_id = 'drifted-upstream-job' "
                            "WHERE id = ?",
                            (runtime["id"],),
                        )

                with self.assertRaisesRegex(ValueError, "completion.*authority"):
                    with self.database.transaction() as conn:
                        self.runtimes.assert_candidate_completion_authority(
                            conn,
                            runtime_id=str(runtime["id"]),
                            build_item_id=str(fixture["item_id"]),
                            target_fingerprint=str(fixture["fingerprint"]),
                            expected_upstream_job_id=(
                                f"formal-completion-{drift}-upstream"
                            ),
                        )
                with self.database.transaction() as conn:
                    receipt = self.catalog.get_classroom_item_receipt(
                        conn, build_item_id=str(fixture["item_id"])
                    )
                    current = self.runtimes.get_runtime_classroom(
                        conn, runtime_id=str(runtime["id"])
                    )
                self.assertIsNone(receipt)
                self.assertEqual(current["status"], "generating")

    def test_formal_scanner_rejects_self_consistent_stale_target_contract(self):
        fixture = self._seed_formal_candidate_handoff("stale-current-target")
        stale_target = build_preparation_target("primary_1")
        stale_target["sampleRuntimeReadiness"] = {
            "schemaVersion": "legacy.sample-runtime.v1"
        }
        stale_target_json = self.packages.encode_json(stale_target)
        stale_fingerprint = preparation_target_fingerprint(stale_target)
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_build_jobs SET target_spec_json = ? "
                "WHERE id = ?",
                (stale_target_json, fixture["build_id"]),
            )
            conn.execute(
                "UPDATE learning_curriculum_preparation_plans "
                "SET target_spec_json = ?, target_fingerprint = ? WHERE id = ?",
                (stale_target_json, stale_fingerprint, fixture["plan_id"]),
            )

        provider_calls = []

        class GuardRuntime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                provider_calls.append(kwargs)
                raise AssertionError("a stale target contract must not reach Provider")

        package_service = object.__new__(LessonPackageService)
        package_service.repository = self.packages
        package_service.validator = LessonPackageValidator()
        self.assertIsNone(package_service.process_next_formal_candidate(GuardRuntime()))
        self.assertEqual(provider_calls, [])
        with self.database.transaction() as conn:
            candidate_count = conn.execute(
                "SELECT COUNT(*) AS count_value FROM learning_lesson_packages "
                "WHERE status = 'candidate'"
            ).fetchone()
            runtime_count = conn.execute(
                "SELECT COUNT(*) AS count_value FROM "
                "learning_openmaic_runtime_classrooms "
                "WHERE candidate_build_item_id = ?",
                (fixture["item_id"],),
            ).fetchone()
        self.assertEqual(int(candidate_count["count_value"]), 0)
        self.assertEqual(int(runtime_count["count_value"]), 0)

    def test_shared_build_ignores_superseded_plan_when_current_plan_exists(self):
        fixture = self._seed_formal_candidate_handoff("shared-current-plan")
        target = build_preparation_target("primary_1")
        with self.database.transaction() as conn:
            build = conn.execute(
                "SELECT * FROM learning_catalog_build_jobs WHERE id = ? FOR UPDATE",
                (fixture["build_id"],),
            ).fetchone()
            conn.execute(
                "UPDATE learning_curriculum_preparation_plans "
                "SET status = 'superseded', stage = 'completed', "
                "completed_at = 7990, superseded_at = 7990, updated_at = 7990 "
                "WHERE id = ?",
                (fixture["plan_id"],),
            )
            conn.execute(
                "INSERT INTO families(id, name, created_at) "
                "VALUES ('shared-current-family', 'Shared current', 8000)"
            )
            conn.execute(
                "INSERT INTO children(id, family_id, name, created_at, updated_at) "
                "VALUES ('shared-current-child', 'shared-current-family', "
                "'Shared child', 8000, 8000)"
            )
            current_plan, created = self.preparations.reserve_plan(
                conn,
                family_id="shared-current-family",
                child_id="shared-current-child",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=target,
                target_fingerprint=str(fixture["fingerprint"]),
                request_id="shared-current-plan-request",
                shared_build_request_id=str(build["request_id"]),
                now=8_000,
            )
            self.assertTrue(created)
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'building_classrooms',
                  catalog_build_id = ?, catalog_release_id = ?,
                  content_candidate_count = 30, content_failed_count = 0,
                  content_canary_candidate_count = 3,
                  content_canary_failed_count = 0,
                  content_canary_passed_at = 8001,
                  content_generation_completed_at = 8002,
                  stage_progress_json = JSON_OBJECT(
                    'candidateCount', 30, 'canaryCandidateCount', 3,
                    'canaryFailedCount', 0, 'canaryTargetCount', 3,
                    'failedCount', 0, 'targetCount', 30),
                  progress_percent = 35, next_run_at = NULL,
                  last_progress_at = 8002, updated_at = 8002
                WHERE id = ?
                """,
                (fixture["build_id"], fixture["release_id"], current_plan["id"]),
            )

        staged_calls = []

        class StagingRuntime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                staged_calls.append(kwargs)
                return {"ok": True, "runtime": {"status": "generating"}}

        package_service = object.__new__(LessonPackageService)
        package_service.repository = self.packages
        package_service.validator = LessonPackageValidator()
        package_service.process_next_formal_candidate(StagingRuntime())
        self.assertEqual(len(staged_calls), 1)
        with self.database.transaction() as conn:
            runtime, created = self.runtimes.reserve_candidate_runtime(
                conn,
                runtime_id="formal-shared-current-runtime",
                feature_manifest=self._formal_runtime_feature_manifest(staged_calls[0]),
                now=8_100,
                **staged_calls[0],
            )
            self.assertTrue(created)
            self.runtimes.mark_generating(
                conn,
                runtime_id=str(runtime["id"]),
                upstream_job_id="formal-shared-current-upstream",
                now=8_110,
            )
            authority = self.runtimes.assert_candidate_completion_authority(
                conn,
                runtime_id=str(runtime["id"]),
                build_item_id=str(fixture["item_id"]),
                target_fingerprint=str(fixture["fingerprint"]),
                expected_upstream_job_id="formal-shared-current-upstream",
            )
        self.assertEqual(authority["preparation_plan_id"], current_plan["id"])

    def test_formal_package_staging_is_inert_idempotent_and_has_no_media_job(self):
        fixture = self._seed_formal_candidate_handoff("formal-package")

        runtime_calls = []

        class Runtime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                runtime_calls.append(kwargs)
                return {
                    "ok": True,
                    "runtime": {
                        "id": "formal-package-runtime",
                        "requestId": kwargs["runtime_request_id"],
                        "status": "generating",
                    },
                }

        service = object.__new__(LessonPackageService)
        service.repository = self.packages
        service.validator = LessonPackageValidator()
        first = service.process_next_formal_candidate(Runtime())
        second = service.process_next_formal_candidate(Runtime())

        self.assertEqual(first.payload["package"]["status"], "candidate")
        self.assertEqual(second.payload["package"], first.payload["package"])
        self.assertEqual(len(runtime_calls), 2)
        self.assertEqual(
            runtime_calls[0]["runtime_request_id"],
            runtime_calls[1]["runtime_request_id"],
        )
        with self.database.transaction() as conn:
            package = self.packages.get_package_any_status(
                conn,
                package_id=first.payload["package"]["id"],
                package_version=1,
            )
            media_jobs = conn.execute(
                "SELECT COUNT(*) AS count_value "
                "FROM learning_media_generation_jobs "
                "WHERE package_id = ? AND package_version = 1",
                (first.payload["package"]["id"],),
            ).fetchone()
            binding = conn.execute(
                "SELECT * FROM learning_course_lesson_package_bindings "
                "WHERE course_id = ? AND course_version = '1' "
                "AND package_id = ? LIMIT 1",
                (fixture["course_id"], first.payload["package"]["id"]),
            ).fetchone()
            staging_job = conn.execute(
                "SELECT generator, status, started_at, completed_at "
                "FROM learning_classroom_generation_jobs "
                "WHERE package_id = ? AND package_version = 1 LIMIT 1",
                (first.payload["package"]["id"],),
            ).fetchone()
        self.assertEqual(package["status"], "candidate")
        self.assertIsNone(package["published_at"])
        self.assertEqual(int(media_jobs["count_value"]), 0)
        self.assertIsNone(binding)
        self.assertEqual(staging_job["generator"], "formal_package_authority")
        self.assertEqual(staging_job["status"], "staged")
        self.assertIsNone(staging_job["started_at"])
        self.assertIsNone(staging_job["completed_at"])

    def test_formal_package_scanner_waits_for_exact_thirty_of_thirty_handoff(self):
        fixture = self._seed_candidate("formal-package-early")
        with self.database.transaction() as conn:
            conn.execute(
                "DELETE FROM learning_curriculum_classroom_item_receipts "
                "WHERE build_item_id = ?",
                (fixture["item_id"],),
            )
            conn.execute(
                "DELETE FROM learning_openmaic_runtime_classrooms WHERE id = ?",
                (fixture["runtime_id"],),
            )

        runtime_calls = []

        class Runtime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                runtime_calls.append(kwargs)
                raise AssertionError("an early content item must not reach Provider")

        service = object.__new__(LessonPackageService)
        service.repository = self.packages
        service.validator = LessonPackageValidator()

        self.assertIsNone(service.process_next_formal_candidate(Runtime()))
        self.assertEqual(runtime_calls, [])

    def test_formal_package_scanner_rejects_a_retired_release(self):
        fixture = self._seed_candidate("formal-package-retired")
        with self.database.transaction() as conn:
            conn.execute(
                "DELETE FROM learning_curriculum_classroom_item_receipts "
                "WHERE build_item_id = ?",
                (fixture["item_id"],),
            )
            conn.execute(
                "DELETE FROM learning_openmaic_runtime_classrooms WHERE id = ?",
                (fixture["runtime_id"],),
            )
            conn.execute(
                "UPDATE learning_catalog_releases SET retired_at = 2500 "
                "WHERE id = ?",
                (fixture["release_id"],),
            )

        runtime_calls = []

        class Runtime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                runtime_calls.append(kwargs)
                raise AssertionError("a retired release must not reach Provider")

        service = object.__new__(LessonPackageService)
        service.repository = self.packages
        service.validator = LessonPackageValidator()

        self.assertIsNone(service.process_next_formal_candidate(Runtime()))
        self.assertEqual(runtime_calls, [])

    def test_candidate_binding_and_winning_receipt_are_immutable(self) -> None:
        fixture = self._seed_candidate("binding")
        with self.database.transaction() as conn:
            replay = self.runtimes.bind_candidate_runtime(
                conn,
                runtime_id=fixture["runtime_id"],
                build_item_id=fixture["item_id"],
                target_fingerprint=fixture["fingerprint"],
                now=2_001,
            )
            receipt, created = self.catalog.reserve_classroom_item_receipt(
                conn,
                build_item_id=fixture["item_id"],
                runtime_classroom_id=fixture["runtime_id"],
                target_fingerprint=fixture["fingerprint"],
                now=2_001,
            )
            successor_id = self._insert_formal_retry_runtime(
                conn, fixture=fixture, attempt_ordinal=2
            )
        self.assertEqual(replay["candidate_bound_at"], 2_000)
        self.assertFalse(created)
        self.assertEqual(receipt["runtime_classroom_id"], fixture["runtime_id"])

        with self.assertRaises(LearningCatalogActivationError):
            with self.database.transaction() as conn:
                self.catalog.reserve_classroom_item_receipt(
                    conn,
                    build_item_id=fixture["item_id"],
                    runtime_classroom_id=successor_id,
                    target_fingerprint=fixture["fingerprint"],
                    now=2_002,
                )
        with self.assertRaises(ValueError):
            with self.database.transaction() as conn:
                self.runtimes.bind_candidate_runtime(
                    conn,
                    runtime_id=fixture["runtime_id"],
                    build_item_id=fixture["item_id"],
                    target_fingerprint="f" * 64,
                    now=2_002,
                )

    def test_exact_candidate_binding_replay_survives_grade_activation(self) -> None:
        fixture = self._seed_candidate("active-replay")
        self._pass_and_publish(fixture)
        with self.database.transaction() as conn:
            self.catalog.activate_grade_release_pointer(
                conn,
                grade_code="primary_1",
                build_id=str(fixture["build_id"]),
                target_fingerprint=str(fixture["fingerprint"]),
                contract_version=self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                publication_request_id="publication-active-replay",
                publication_receipt_hash="7" * 64,
                activated_at=4_940,
            )
            replay = self.runtimes.bind_candidate_runtime(
                conn,
                runtime_id=str(fixture["runtime_id"]),
                build_item_id=str(fixture["item_id"]),
                target_fingerprint=str(fixture["fingerprint"]),
                now=4_950,
            )
        self.assertEqual(replay["candidate_bound_at"], 2_000)

    def test_activation_rejects_binding_contract_drift_and_rolls_back(self) -> None:
        fixture = self._seed_candidate("binding-drift")
        self._pass_and_publish(fixture)
        with self.assertRaises(LearningCatalogActivationError):
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_curriculum_classroom_item_receipts "
                    "SET binding_contract_version = 'legacy.binding.v0' "
                    "WHERE build_item_id = ?",
                    (fixture["item_id"],),
                )
                conn.execute(
                    "UPDATE learning_openmaic_runtime_classrooms "
                    "SET candidate_binding_contract_version = 'legacy.binding.v0' "
                    "WHERE id = ?",
                    (fixture["runtime_id"],),
                )
                self.catalog.activate_grade_release_pointer(
                    conn,
                    grade_code="primary_1",
                    build_id=str(fixture["build_id"]),
                    target_fingerprint=str(fixture["fingerprint"]),
                    contract_version=self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                    publication_request_id="publication-binding-drift",
                    publication_receipt_hash="6" * 64,
                    activated_at=4_940,
                )
        with self.database.transaction() as conn:
            receipt = self.catalog.get_classroom_item_receipt(
                conn, build_item_id=str(fixture["item_id"])
            )
            runtime = self.runtimes.get_runtime_classroom(
                conn, runtime_id=str(fixture["runtime_id"])
            )
            pointer = self.catalog.get_active_grade_release_pointer(
                conn, grade_code="primary_1"
            )
        self.assertEqual(
            receipt["binding_contract_version"],
            self.catalog.CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION,
        )
        self.assertEqual(
            runtime["candidate_binding_contract_version"],
            self.runtimes.CANDIDATE_BINDING_CONTRACT_VERSION,
        )
        self.assertIsNone(pointer)

    def test_machine_validation_publication_and_human_approval_stay_separate(self) -> None:
        fixture = self._seed_candidate("evidence")
        with self.database.transaction() as conn:
            for ordinal, kind in enumerate(
                ("classroom", "tts", "asr_roundtrip", "conversation_provider"),
                start=1,
            ):
                row = self.catalog.record_classroom_item_evidence(
                    conn,
                    build_item_id=fixture["item_id"],
                    evidence_kind=kind,
                    outcome="passed",
                    receipt_hash=f"{ordinal + 30:064x}",
                    completed_at=3_000 + ordinal,
                    now=3_010,
                )
            auto = self.catalog.mark_classroom_auto_validated(
                conn,
                build_item_id=fixture["item_id"],
                validation_contract_version="mira.learning.classroom-validation.v1",
                receipt_hash="a" * 64,
                validated_at=3_020,
                now=3_020,
            )
            published = self.catalog.record_classroom_publication_evidence(
                conn,
                build_item_id=fixture["item_id"],
                outcome="published",
                receipt_hash="b" * 64,
                completed_at=3_030,
                now=3_030,
            )
            approved = self.catalog.mark_classroom_human_approved(
                conn,
                build_item_id=fixture["item_id"],
                approved_by="reviewer-1",
                receipt_hash="c" * 64,
                approved_at=3_040,
                now=3_040,
            )

        self.assertEqual(auto["auto_validated"], 1)
        self.assertEqual(auto["approved"], 0)
        self.assertEqual(published["publication_status"], "published")
        self.assertEqual(published["approved"], 0)
        self.assertEqual(approved["auto_validated"], 1)
        self.assertEqual(approved["approved"], 1)
        self.assertEqual(row["conversation_provider_status"], "passed")

    def test_failed_evidence_is_terminal_and_nullable_pass_is_rejected(self) -> None:
        failed_fixture = self._seed_candidate("failed")
        with self.database.transaction() as conn:
            failed = self.catalog.record_classroom_item_evidence(
                conn,
                build_item_id=failed_fixture["item_id"],
                evidence_kind="classroom",
                outcome="failed",
                receipt_hash="d" * 64,
                completed_at=4_000,
                now=4_000,
            )
        self.assertEqual(failed["classroom_status"], "failed")
        with self.assertRaises(LearningCatalogActivationError):
            with self.database.transaction() as conn:
                self.catalog.record_classroom_item_evidence(
                    conn,
                    build_item_id=failed_fixture["item_id"],
                    evidence_kind="classroom",
                    outcome="passed",
                    receipt_hash="e" * 64,
                    completed_at=4_001,
                    now=4_001,
                )

        null_fixture = self._seed_candidate("nullable")
        with self.assertRaises(Exception) as raised:
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_curriculum_classroom_item_receipts "
                    "SET tts_status = 'passed', tts_receipt_hash = NULL "
                    "WHERE build_item_id = ?",
                    (null_fixture["item_id"],),
                )
        self.assertEqual(raised.exception.args[0], 3819)

    def test_receipt_validation_and_publication_timeline_is_fail_closed(self) -> None:
        fixture = self._seed_candidate("receipt-timeline")
        invalid_updates = (
            (
                "UPDATE learning_curriculum_classroom_item_receipts SET "
                "auto_validated = 1, auto_validation_contract_version = 'v1', "
                "auto_validation_receipt_hash = REPEAT('a', 64), "
                "auto_validated_at = 2001, updated_at = 2001 "
                "WHERE build_item_id = ?",
                3819,
            ),
            (
                "UPDATE learning_curriculum_classroom_item_receipts SET "
                "classroom_status = 'passed', classroom_receipt_hash = REPEAT('1',64), "
                "classroom_completed_at = 2100, tts_status = 'passed', "
                "tts_receipt_hash = REPEAT('2',64), tts_completed_at = 2101, "
                "asr_roundtrip_status = 'passed', "
                "asr_roundtrip_receipt_hash = REPEAT('3',64), "
                "asr_roundtrip_completed_at = 2102, "
                "conversation_provider_status = 'passed', "
                "conversation_provider_receipt_hash = REPEAT('4',64), "
                "conversation_provider_completed_at = 2103, auto_validated = 1, "
                "auto_validation_contract_version = 'v1', "
                "auto_validation_receipt_hash = REPEAT('5',64), "
                "auto_validated_at = 2050, publication_status = 'published', "
                "publication_receipt_hash = REPEAT('6',64), published_at = 2040, "
                "updated_at = 2200 WHERE build_item_id = ?",
                3819,
            ),
        )
        for sql, error_code in invalid_updates:
            with self.subTest(sql=sql[:80]):
                with self.assertRaises(pymysql.MySQLError) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(sql, (fixture["item_id"],))
                self.assertEqual(raised.exception.args[0], error_code)

    def test_grade_pointer_is_idempotent_and_cross_grade_isolated(self) -> None:
        fixture = self._seed_candidate("pointer")
        self._pass_and_publish(fixture)
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO learning_curriculum_grade_release_pointers("
                "grade_code, pointer_revision, updated_at) "
                "VALUES ('primary_2', 0, 1)"
            )
            first = self.catalog.activate_grade_release_pointer(
                conn,
                grade_code="primary_1",
                build_id=fixture["build_id"],
                target_fingerprint=fixture["fingerprint"],
                contract_version=self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                publication_request_id="publication-pointer-1",
                publication_receipt_hash="f" * 64,
                activated_at=5_000,
            )
            replay = self.catalog.activate_grade_release_pointer(
                conn,
                grade_code="primary_1",
                build_id=fixture["build_id"],
                target_fingerprint=fixture["fingerprint"],
                contract_version=self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                publication_request_id="publication-pointer-1",
                publication_receipt_hash="f" * 64,
                activated_at=5_001,
            )
        self.assertEqual(first["history_id"], replay["history_id"])
        self.assertEqual(first["pointer_revision"], 1)

        with self.assertRaises(LearningCatalogActivationError):
            with self.database.transaction() as conn:
                self.catalog.activate_grade_release_pointer(
                    conn,
                    grade_code="primary_2",
                    build_id=fixture["build_id"],
                    target_fingerprint=fixture["fingerprint"],
                    contract_version=self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                    publication_request_id="publication-wrong-grade",
                    publication_receipt_hash="1" * 64,
                    activated_at=5_010,
                )
        with self.database.transaction() as conn:
            primary_one = self.catalog.get_active_grade_release_pointer(
                conn, grade_code="primary_1"
            )
            primary_two_slot = conn.execute(
                "SELECT * FROM learning_curriculum_grade_release_pointers "
                "WHERE grade_code = 'primary_2'"
            ).fetchone()
            history = self.catalog.list_grade_release_history(
                conn, grade_code="primary_1"
            )
        self.assertEqual(primary_one["release_id"], fixture["release_id"])
        self.assertEqual(primary_two_slot["pointer_revision"], 0)
        self.assertEqual(len(history), 1)

    def test_pointer_successor_validates_prior_and_rolls_back_every_write(self) -> None:
        fixture = self._seed_candidate("pointer-rollback")
        self._pass_and_publish(fixture)
        old_history_id = "pointer-rollback-old-history"
        old_release_id = "pointer-rollback-old-release"
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO learning_catalog_releases("
                "id, curriculum_version, title, status, quality_status, "
                "required_boundary_count, ready_item_count, created_at, updated_at) "
                "VALUES (?, 'primary-cn-2026.1', 'Old', 'retired', 'ready', "
                "1, 1, 100, 100)",
                (old_release_id,),
            )
            conn.execute(
                "INSERT INTO learning_curriculum_grade_release_history("
                "id, grade_code, pointer_revision, target_fingerprint, "
                "contract_version, release_id, activation_source, "
                "publication_request_id, publication_receipt_hash, "
                "activated_at, created_at) VALUES (?, 'primary_1', 1, "
                "REPEAT('a', 64), ?, ?, 'formal_publication', "
                "'pointer-rollback-old-request', REPEAT('b',64), 100, 100)",
                (
                    old_history_id,
                    self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                    old_release_id,
                ),
            )
            conn.execute(
                "INSERT INTO learning_curriculum_grade_release_pointers("
                "grade_code, pointer_revision, target_fingerprint, "
                "contract_version, release_id, history_id, activated_at, updated_at) "
                "VALUES ('primary_1', 1, REPEAT('a',64), ?, ?, ?, 100, 100)",
                (
                    self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                    old_release_id,
                    old_history_id,
                ),
            )

        with self.assertRaises(LearningCatalogActivationError):
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_curriculum_grade_release_history "
                    "SET superseded_at = 4999 WHERE id = ?",
                    (old_history_id,),
                )
                self.catalog.activate_grade_release_pointer(
                    conn,
                    grade_code="primary_1",
                    build_id=str(fixture["build_id"]),
                    target_fingerprint=str(fixture["fingerprint"]),
                    contract_version=self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                    publication_request_id="pointer-rollback-successor",
                    publication_receipt_hash="c" * 64,
                    activated_at=5_000,
                )

        with self.assertRaisesRegex(RuntimeError, "post-CAS read failed"):
            with self.database.transaction() as conn:
                with mock.patch.object(
                    self.catalog,
                    "get_active_grade_release_pointer",
                    side_effect=RuntimeError("post-CAS read failed"),
                ):
                    self.catalog.activate_grade_release_pointer(
                        conn,
                        grade_code="primary_1",
                        build_id=str(fixture["build_id"]),
                        target_fingerprint=str(fixture["fingerprint"]),
                        contract_version=self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                        publication_request_id="pointer-rollback-successor",
                        publication_receipt_hash="c" * 64,
                        activated_at=5_000,
                    )
        with self.database.transaction() as conn:
            pointer = self.catalog.get_active_grade_release_pointer(
                conn, grade_code="primary_1"
            )
            old_history = conn.execute(
                "SELECT * FROM learning_curriculum_grade_release_history "
                "WHERE id = ?",
                (old_history_id,),
            ).fetchone()
            history_count = conn.execute(
                "SELECT COUNT(*) AS count "
                "FROM learning_curriculum_grade_release_history "
                "WHERE grade_code = 'primary_1'"
            ).fetchone()
        self.assertEqual(pointer["history_id"], old_history_id)
        self.assertEqual(pointer["release_id"], old_release_id)
        self.assertIsNone(old_history["superseded_at"])
        self.assertEqual(history_count["count"], 1)

    def test_complete_formal_ready_is_exact_atomic_and_readable(self) -> None:
        fixture = self._seed_formal_ready_plan("complete-ready")
        with self.database.transaction() as conn:
            missing_pointer = self.preparations.complete_formal_ready(
                conn,
                plan_id=str(fixture["plan_id"]),
                lease_token=str(fixture["lease_token"]),
                target_fingerprint=str(fixture["fingerprint"]),
                subject_progress=fixture["subject_progress"],
                now=8_100,
            )
            unchanged = self.preparations.get_plan(
                conn, str(fixture["plan_id"]), for_update=True
            )
        self.assertFalse(missing_pointer)
        self.assertEqual(unchanged["stage"], "publishing")

        with self.database.transaction() as conn:
            pointer = self.catalog.activate_grade_release_pointer(
                conn,
                grade_code="primary_1",
                build_id=str(fixture["build_id"]),
                target_fingerprint=str(fixture["fingerprint"]),
                contract_version=self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                publication_request_id="complete-ready-publication",
                publication_receipt_hash="d" * 64,
                activated_at=8_050,
            )

        with self.assertRaises(pymysql.MySQLError) as forged:
            with self.database.transaction() as conn:
                conn.execute(
                    """
                    UPDATE learning_curriculum_preparation_plans
                    SET status = 'ready', stage = 'completed',
                      ready_course_count = total_course_count,
                      failed_course_count = 0, progress_percent = 100,
                      subject_progress_json = ?, classroom_ready_count = 30,
                      speech_ready_count = 30, validation_ready_count = 30,
                      published_course_count = 30,
                      formal_contract_version = ?,
                      formal_publication_history_id = 'missing-ready-history',
                      formal_publication_receipt_hash = REPEAT('d',64),
                      formal_ready_at = 8100, completed_at = 8100,
                      lease_token = NULL, lease_expires_at = NULL,
                      heartbeat_at = NULL, next_run_at = NULL,
                      hard_deadline_at = NULL, resume_stage = NULL,
                      work_unit_kind = NULL, bound_catalog_item_id = NULL,
                      bound_content_attempt_ordinal = NULL,
                      bound_content_phase = NULL, retry_reason_code = NULL,
                      retry_message_safe = NULL, updated_at = 8100
                    WHERE id = ?
                    """,
                    (
                        self.catalog.encode_json(fixture["subject_progress"]),
                        self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                        fixture["plan_id"],
                    ),
                )
        self.assertEqual(forged.exception.args[0], 1452)

        with self.assertRaisesRegex(RuntimeError, "rollback contract drift"):
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_curriculum_classroom_item_receipts "
                    "SET binding_contract_version = 'legacy.binding.v0' "
                    "WHERE build_item_id = ?",
                    (fixture["item_ids"][0],),
                )
                self.assertFalse(
                    self.preparations.complete_formal_ready(
                        conn,
                        plan_id=str(fixture["plan_id"]),
                        lease_token=str(fixture["lease_token"]),
                        target_fingerprint=str(fixture["fingerprint"]),
                        subject_progress=fixture["subject_progress"],
                        now=8_100,
                    )
                )
                drift_readback = self.preparations.get_plan(
                    conn, str(fixture["plan_id"]), for_update=True
                )
                self.assertEqual(drift_readback["stage"], "publishing")
                raise RuntimeError("rollback contract drift")

        with self.assertRaisesRegex(RuntimeError, "formal event failed"):
            with self.database.transaction() as conn:
                with mock.patch.object(
                    self.preparations,
                    "append_event",
                    side_effect=RuntimeError("formal event failed"),
                ):
                    self.preparations.complete_formal_ready(
                        conn,
                        plan_id=str(fixture["plan_id"]),
                        lease_token=str(fixture["lease_token"]),
                        target_fingerprint=str(fixture["fingerprint"]),
                        subject_progress=fixture["subject_progress"],
                        now=8_100,
                    )
        with self.database.transaction() as conn:
            rolled_back = self.preparations.get_plan(
                conn, str(fixture["plan_id"]), for_update=True
            )
        self.assertEqual(rolled_back["status"], "running")
        self.assertEqual(rolled_back["stage"], "publishing")
        self.assertEqual(rolled_back["lease_token"], fixture["lease_token"])

        with self.database.transaction() as conn:
            self.assertTrue(
                self.preparations.complete_formal_ready(
                    conn,
                    plan_id=str(fixture["plan_id"]),
                    lease_token=str(fixture["lease_token"]),
                    target_fingerprint=str(fixture["fingerprint"]),
                    subject_progress=fixture["subject_progress"],
                    now=8_100,
                )
            )
            ready = self.preparations.get_plan(
                conn, str(fixture["plan_id"]), for_update=True
            )
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["stage"], "completed")
        self.assertEqual(ready["formal_publication_history_id"], pointer["history_id"])
        self.assertEqual(ready["formal_publication_receipt_hash"], "d" * 64)
        self.assertEqual(ready["published_course_count"], 30)

        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO learning_curriculum_grade_release_history("
                "id, grade_code, pointer_revision, target_fingerprint, "
                "contract_version, release_id, activation_source, "
                "publication_request_id, publication_receipt_hash, "
                "activated_at, created_at) VALUES ("
                "'wrong-grade-ready-history', 'primary_2', 1, ?, ?, ?, "
                "'formal_publication', 'wrong-grade-ready-request', "
                "REPEAT('e',64), 8100, 8100)",
                (
                    fixture["fingerprint"],
                    self.catalog.FORMAL_PUBLICATION_CONTRACT_VERSION,
                    fixture["release_id"],
                ),
            )
        for forged_history_id in (
            "wrong-grade-ready-history",
            "history-that-does-not-exist",
        ):
            with self.subTest(forged_history_id=forged_history_id):
                with self.assertRaises(pymysql.MySQLError) as raised:
                    with self.database.transaction() as conn:
                        conn.execute(
                            "UPDATE learning_curriculum_preparation_plans "
                            "SET formal_publication_history_id = ? WHERE id = ?",
                            (forged_history_id, fixture["plan_id"]),
                        )
                self.assertEqual(raised.exception.args[0], 1452)
        with self.assertRaises(pymysql.MySQLError) as forged_hash:
            with self.database.transaction() as conn:
                conn.execute(
                    "UPDATE learning_curriculum_preparation_plans "
                    "SET formal_publication_receipt_hash = REPEAT('f',64) "
                    "WHERE id = ?",
                    (fixture["plan_id"],),
                )
        self.assertEqual(forged_hash.exception.args[0], 1452)

    def test_formal_stage_handoffs_use_frozen_deadlines_and_rollback(self) -> None:
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with self.database.transaction() as conn:
            build, _ = self.catalog.create_or_get_content_build(
                conn,
                request_id=f"grade-build:{fingerprint}",
                curriculum_version=str(target["curriculumVersion"]),
                title="Formal deadline",
                target_spec=target,
                target_fingerprint=fingerprint,
                now=6_000,
            )
            conn.execute(
                "INSERT INTO families(id, name, created_at) "
                "VALUES ('formal-family', 'Formal', 1)"
            )
            conn.execute(
                "INSERT INTO children(id, family_id, name, created_at, updated_at) "
                "VALUES ('formal-child', 'formal-family', 'Child', 1, 1)"
            )
            plan, _ = self.preparations.reserve_plan(
                conn,
                family_id="formal-family",
                child_id="formal-child",
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=target,
                target_fingerprint=fingerprint,
                request_id="formal-plan",
                shared_build_request_id=f"grade-build:{fingerprint}",
                now=6_000,
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'building_classrooms',
                  catalog_build_id = ?, catalog_release_id = ?,
                  content_candidate_count = 30, content_failed_count = 0,
                  content_canary_candidate_count = 3,
                  content_canary_failed_count = 0,
                  content_canary_passed_at = 6001,
                  content_generation_completed_at = 6002,
                  stage_progress_json = JSON_OBJECT(
                    'candidateCount', 30, 'canaryCandidateCount', 3,
                    'canaryFailedCount', 0, 'canaryTargetCount', 3,
                    'failedCount', 0, 'targetCount', 30),
                  progress_percent = 35, next_run_at = NULL,
                  last_progress_at = 6002, updated_at = 6002
                WHERE id = ?
                """,
                (build["id"], build["release_id"], plan["id"]),
            )
            self.assertTrue(
                self.preparations.start_formal_pipeline(
                    conn,
                    plan_id=plan["id"],
                    target_fingerprint=fingerprint,
                    now=6_100,
                )
            )
            claimed = self.preparations.claim_next(
                conn,
                now=6_100,
                lease_ms=60 * 60 * 1000,
                supported_stages=("building_classrooms",),
                grade_code="primary_1",
                target_fingerprint=fingerprint,
            )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["stage"], "building_classrooms")
        self.assertEqual(claimed["work_unit_kind"], "coordinator")
        self.assertEqual(
            claimed["hard_deadline_at"],
            6_100
            + self.preparations.STAGE_DEADLINE_MS["building_classrooms"],
        )
        self.assertEqual(claimed["lease_expires_at"], claimed["hard_deadline_at"])

        subject_progress = self._formal_subject_progress(ready=0)
        with self.assertRaisesRegex(RuntimeError, "event write failed"):
            with self.database.transaction() as conn:
                with mock.patch.object(
                    self.preparations,
                    "append_event",
                    side_effect=RuntimeError("event write failed"),
                ):
                    self.preparations.apply_stage_result(
                        conn,
                        plan_id=str(plan["id"]),
                        lease_token=str(claimed["lease_token"]),
                        target_fingerprint=fingerprint,
                        expected_stage="building_classrooms",
                        next_status="queued",
                        next_stage="generating_speech",
                        ready_course_count=0,
                        failed_course_count=0,
                        subject_progress=subject_progress,
                        next_run_at=6_101,
                        hard_deadline_at=None,
                        catalog_build_id=str(build["id"]),
                        catalog_release_id=str(build["release_id"]),
                        now=6_100,
                    )
        with self.database.transaction() as conn:
            rolled_back = self.preparations.get_plan(conn, str(plan["id"]))
        self.assertEqual(rolled_back["stage"], "building_classrooms")
        self.assertEqual(rolled_back["lease_token"], claimed["lease_token"])

        stage_now = 6_100
        current = claimed
        for expected_stage, next_stage in (
            ("building_classrooms", "generating_speech"),
            ("generating_speech", "validating"),
            ("validating", "publishing"),
        ):
            next_run_at = stage_now + 1
            with self.database.transaction() as conn:
                self.assertTrue(
                    self.preparations.apply_stage_result(
                        conn,
                        plan_id=str(plan["id"]),
                        lease_token=str(current["lease_token"]),
                        target_fingerprint=fingerprint,
                        expected_stage=expected_stage,
                        next_status="queued",
                        next_stage=next_stage,
                        ready_course_count=0,
                        failed_course_count=0,
                        subject_progress=subject_progress,
                        next_run_at=next_run_at,
                        hard_deadline_at=None,
                        catalog_build_id=str(build["id"]),
                        catalog_release_id=str(build["release_id"]),
                        now=stage_now,
                    )
                )
                handed_off = self.preparations.get_plan(
                    conn, str(plan["id"]), for_update=True
                )
                self.assertEqual(handed_off["status"], "running")
                self.assertEqual(handed_off["stage"], next_stage)
                self.assertIsNone(handed_off["lease_token"])
                self.assertIsNone(handed_off["work_unit_kind"])
                self.assertEqual(handed_off["next_run_at"], next_run_at)
                current = self.preparations.claim_next(
                    conn,
                    now=next_run_at,
                    lease_ms=60 * 60 * 1000,
                    supported_stages=(next_stage,),
                    grade_code="primary_1",
                    target_fingerprint=fingerprint,
                )
            self.assertIsNotNone(current)
            self.assertEqual(current["stage"], next_stage)
            self.assertEqual(
                current["hard_deadline_at"],
                next_run_at + self.preparations.STAGE_DEADLINE_MS[next_stage],
            )
            self.assertEqual(
                current["lease_expires_at"], current["hard_deadline_at"]
            )
            stage_now = next_run_at

    def _pass_and_publish(self, fixture: dict[str, object]) -> None:
        with self.database.transaction() as conn:
            for ordinal, kind in enumerate(
                ("classroom", "tts", "asr_roundtrip", "conversation_provider"),
                start=1,
            ):
                self.catalog.record_classroom_item_evidence(
                    conn,
                    build_item_id=str(fixture["item_id"]),
                    evidence_kind=kind,
                    outcome="passed",
                    receipt_hash=f"{ordinal + 40:064x}",
                    completed_at=4_900 + ordinal,
                    now=4_910,
                )
            self.catalog.mark_classroom_auto_validated(
                conn,
                build_item_id=str(fixture["item_id"]),
                validation_contract_version="mira.learning.classroom-validation.v1",
                receipt_hash="8" * 64,
                validated_at=4_920,
                now=4_920,
            )
            self.catalog.record_classroom_publication_evidence(
                conn,
                build_item_id=str(fixture["item_id"]),
                outcome="published",
                receipt_hash="9" * 64,
                completed_at=4_930,
                now=4_930,
            )

    def _formal_runtime_feature_manifest(
        self, candidate: dict[str, object]
    ) -> dict[str, object]:
        """Build the same immutable manifest the formal service reserves."""

        with self.database.transaction() as conn:
            authority = self.runtimes.get_formal_candidate_generation_authority(
                conn,
                build_item_id=str(candidate["build_item_id"]),
                course_id=str(candidate["course_id"]),
                course_version=str(candidate["course_version"]),
                package_id=str(candidate["package_id"]),
                package_version=int(candidate["package_version"]),
                target_fingerprint=str(candidate["target_fingerprint"]),
            )
        formal_contract = json.loads(
            json.dumps(
                OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        generation_contract = {
            "schemaVersion": (
                OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
            ),
            "authority": "mira_backend_formal_candidate",
            "buildItemId": str(candidate["build_item_id"]),
            "course": {
                "id": str(candidate["course_id"]),
                "version": str(candidate["course_version"]),
                "packageId": str(candidate["package_id"]),
                "packageVersion": int(candidate["package_version"]),
            },
            "targetFingerprint": str(candidate["target_fingerprint"]),
            "runtimeRequestId": str(candidate["runtime_request_id"]),
            "sourceCourseContentSha256": str(
                authority["sourceCourseContentSha256"]
            ),
            "teachingBriefSha256": str(authority["teachingBriefSha256"]),
            "teachingBrief": authority["teachingBrief"],
            "teacher": get_formal_runtime_teacher_contract(str(authority['teachingBrief']['course']['subject'])),
            "professionalCreationPolicy": authority["professionalCreationPolicy"],
            "gradeBoundary": authority["gradeBoundary"],
            "gradeBoundarySha256": authority["gradeBoundarySha256"],
            "coursewareAuthority": dict(OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY),
            "requiredClassroom": formal_contract,
            "generation": generation_options(authority["professionalCreationPolicy"]),
        }
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        manifest = service._requested_manifest(
            FORMAL_REQUIRED_FEATURES,
            FORMAL_REQUIRED_FEATURES,
            generation_contract=generation_contract,
        )
        manifest["formalRuntimeContract"] = formal_contract
        manifest["sourceCourseContentSha256"] = str(
            authority["sourceCourseContentSha256"]
        )
        manifest["teachingBriefSha256"] = str(authority["teachingBriefSha256"])
        return manifest

    @staticmethod
    def _formal_subject_progress(*, ready: int) -> dict[str, dict[str, int]]:
        remaining = int(ready)
        progress: dict[str, dict[str, int]] = {}
        for subject, total in (("chinese", 12), ("math", 9), ("english", 9)):
            ready_count = min(total, remaining)
            remaining -= ready_count
            progress[subject] = {
                "totalCourseCount": total,
                "readyCourseCount": ready_count,
                "failedCourseCount": 0,
                "contentCandidateCount": total,
                "contentFailedCount": 0,
            }
        return progress

    def _seed_formal_ready_plan(self, suffix: str) -> dict[str, object]:
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        with self.database.transaction() as conn:
            build, _ = self.catalog.create_or_get_content_build(
                conn,
                request_id=f"grade-build:{fingerprint}:{suffix}",
                curriculum_version=str(target["curriculumVersion"]),
                title=f"Formal ready {suffix}",
                target_spec=target,
                target_fingerprint=fingerprint,
                now=7_000,
            )
            items = self.catalog.list_build_items(
                conn, build_id=str(build["id"]), for_update=True
            )
            self.assertEqual(len(items), 30)
            item_ids: list[str] = []
            for ordinal, item in enumerate(items, start=1):
                item_id = str(item["id"])
                item_ids.append(item_id)
                course_id = f"formal-{suffix}-course-{ordinal}"
                package_id = f"formal-{suffix}-package-{ordinal}"
                job_id = f"formal-{suffix}-job-{ordinal}"
                artifact_id = f"formal-{suffix}-artifact-{ordinal}"
                runtime_id = f"formal-{suffix}-runtime-{ordinal}"
                conn.execute(
                    "INSERT INTO learning_courses("
                    "id, version, grade_code, subject, node_code, curriculum_version, "
                    "boundary_version, title, objective, status, quality_status, "
                    "content_json, created_at, updated_at) VALUES ("
                    "?, '1', ?, ?, ?, ?, ?, ?, 'Objective', 'validated', "
                    "'auto_validated', ?, 7000, 7000)",
                    (
                        course_id,
                        item["grade_code"],
                        item["subject"],
                        item["skill_id"],
                        item["curriculum_version"],
                        item["boundary_version"],
                        f"Formal {suffix} {ordinal}",
                        _formal_course_content(f"formal-{suffix}-{ordinal}"),
                    ),
                )
                conn.execute(
                    "INSERT INTO learning_classroom_generation_jobs("
                    "id, request_id, course_id, course_version, generator, status, "
                    "created_at, updated_at) VALUES (?, ?, ?, '1', 'formal', "
                    "'completed', 7000, 7000)",
                    (job_id, f"request-{job_id}", course_id),
                )
                conn.execute(
                    "INSERT INTO learning_classroom_source_artifacts("
                    "id, job_id, request_id, source_format, dsl_version, status, "
                    "source_hash, payload_json, created_at, updated_at) VALUES ("
                    "?, ?, ?, 'json', 'v1', 'validated', ?, '{}', 7000, 7000)",
                    (
                        artifact_id,
                        job_id,
                        f"request-{artifact_id}",
                        hashlib.sha256(f"source-{suffix}-{ordinal}".encode()).hexdigest(),
                    ),
                )
                conn.execute(
                    "INSERT INTO learning_lesson_packages("
                    "id, version, course_id, course_version, schema_version, status, "
                    "source_artifact_id, compiler_version, public_content_hash, "
                    "private_content_hash, public_payload_json, "
                    "validation_report_json, created_at, published_at, updated_at) "
                    "VALUES (?, 1, ?, '1', 'v1', 'published', ?, 'v1', ?, ?, "
                    "'{}', '{}', 7000, 7000, 7000)",
                    (
                        package_id,
                        course_id,
                        artifact_id,
                        hashlib.sha256(f"public-{suffix}-{ordinal}".encode()).hexdigest(),
                        hashlib.sha256(f"private-{suffix}-{ordinal}".encode()).hexdigest(),
                    ),
                )
                conn.execute(
                    "UPDATE learning_catalog_build_items SET status = 'course_ready', "
                    "attempt_count = 1, active_generation_request_id = ?, "
                    "course_id = ?, course_version = '1', "
                    "content_phase = 'course_ready', content_gate_status = 'passed', "
                    "content_gate_attempt_count = 1, content_gate_passed_at = 7000, "
                    "content_validation_contract_version = ?, content_receipt_hash = ?, "
                    "content_claim_attempt_ordinal = 1, updated_at = 7000 WHERE id = ?",
                    (
                        f"active-{suffix}-{ordinal}",
                        course_id,
                        "mira.learning.primary-1-content-validation.v1",
                        hashlib.sha256(f"content-{suffix}-{ordinal}".encode()).hexdigest(),
                        item_id,
                    ),
                )
                conn.execute(
                    "INSERT INTO learning_openmaic_runtime_classrooms("
                    "id, request_id, attempt_ordinal, course_id, course_version, "
                    "package_id, package_version, upstream_classroom_id, status, "
                    "quality_status, feature_manifest_json, created_at, updated_at, "
                    "ready_at, candidate_build_item_id, candidate_release_id, "
                    "candidate_grade_code, candidate_target_fingerprint, "
                    "candidate_binding_contract_version, candidate_bound_at) VALUES ("
                    "?, ?, 1, ?, '1', ?, 1, ?, 'ready', 'pending_review', '{}', "
                    "7001, 7002, 7002, ?, ?, 'primary_1', ?, ?, 7002)",
                    (
                        runtime_id,
                        f"request-{runtime_id}",
                        course_id,
                        package_id,
                        f"upstream-{runtime_id}",
                        item_id,
                        build["release_id"],
                        fingerprint,
                        self.runtimes.CANDIDATE_BINDING_CONTRACT_VERSION,
                    ),
                )
                conn.execute(
                    "INSERT INTO learning_curriculum_classroom_item_receipts("
                    "build_item_id, release_id, grade_code, target_fingerprint, "
                    "binding_contract_version, runtime_classroom_id, course_id, "
                    "course_version, package_id, package_version, classroom_status, "
                    "classroom_receipt_hash, classroom_completed_at, tts_status, "
                    "tts_receipt_hash, tts_completed_at, asr_roundtrip_status, "
                    "asr_roundtrip_receipt_hash, asr_roundtrip_completed_at, "
                    "conversation_provider_status, conversation_provider_receipt_hash, "
                    "conversation_provider_completed_at, auto_validated, "
                    "auto_validation_contract_version, auto_validation_receipt_hash, "
                    "auto_validated_at, publication_status, publication_receipt_hash, "
                    "published_at, created_at, updated_at) VALUES ("
                    "?, ?, 'primary_1', ?, ?, ?, ?, '1', ?, 1, 'passed', "
                    "REPEAT('1',64), 7010, 'passed', REPEAT('2',64), 7011, "
                    "'passed', REPEAT('3',64), 7012, 'passed', REPEAT('4',64), "
                    "7013, 1, 'mira.learning.classroom-validation.v1', "
                    "REPEAT('5',64), 7020, 'published', REPEAT('6',64), "
                    "7030, 7002, 7030)",
                    (
                        item_id,
                        build["release_id"],
                        fingerprint,
                        self.catalog.CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION,
                        runtime_id,
                        course_id,
                        package_id,
                    ),
                )
            family_id = f"formal-{suffix}-family"
            child_id = f"formal-{suffix}-child"
            conn.execute(
                "INSERT INTO families(id, name, created_at) VALUES (?, ?, 7000)",
                (family_id, family_id),
            )
            conn.execute(
                "INSERT INTO children(id, family_id, name, created_at, updated_at) "
                "VALUES (?, ?, ?, 7000, 7000)",
                (child_id, family_id, child_id),
            )
            plan, _ = self.preparations.reserve_plan(
                conn,
                family_id=family_id,
                child_id=child_id,
                grade_code="primary_1",
                school_year_start_year=2026,
                grade_selection_revision=1,
                target=target,
                target_fingerprint=fingerprint,
                request_id=f"formal-{suffix}-plan",
                shared_build_request_id=str(build["request_id"]),
                now=7_000,
            )
            lease_token = f"formal-{suffix}-publishing-lease"
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'publishing',
                  catalog_build_id = ?, catalog_release_id = ?,
                  content_candidate_count = 30, content_failed_count = 0,
                  content_canary_candidate_count = 3,
                  content_canary_failed_count = 0,
                  content_canary_passed_at = 7001,
                  content_generation_completed_at = 7002,
                  stage_progress_json = JSON_OBJECT(
                    'candidateCount', 30, 'canaryCandidateCount', 3,
                    'canaryFailedCount', 0, 'canaryTargetCount', 3,
                    'failedCount', 0, 'targetCount', 30),
                  progress_percent = 95, next_run_at = 8000,
                  lease_token = ?, lease_expires_at = 9000,
                  heartbeat_at = 8000, hard_deadline_at = 9000,
                  work_unit_kind = 'coordinator',
                  classroom_ready_count = 30, speech_ready_count = 30,
                  validation_ready_count = 30, published_course_count = 29,
                  last_progress_at = 8000, updated_at = 8000
                WHERE id = ?
                """,
                (build["id"], build["release_id"], lease_token, plan["id"]),
            )
        return {
            "plan_id": str(plan["id"]),
            "lease_token": lease_token,
            "build_id": str(build["id"]),
            "release_id": str(build["release_id"]),
            "fingerprint": fingerprint,
            "item_ids": item_ids,
            "subject_progress": self._formal_subject_progress(ready=30),
        }

    def _seed_formal_candidate_handoff(self, suffix: str) -> dict[str, object]:
        fixture = self._seed_formal_ready_plan(suffix)
        first_item_id = str(fixture["item_ids"][0])
        with self.database.transaction() as conn:
            first_item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? "
                "LIMIT 1 FOR UPDATE",
                (first_item_id,),
            ).fetchone()
            self.assertIsNotNone(first_item)
            conn.execute(
                "DELETE FROM learning_curriculum_classroom_item_receipts "
                "WHERE build_item_id = ?",
                (first_item_id,),
            )
            conn.execute(
                "DELETE FROM learning_openmaic_runtime_classrooms "
                "WHERE candidate_build_item_id = ?",
                (first_item_id,),
            )
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'building_classrooms',
                  content_candidate_count = 30, content_failed_count = 0,
                  content_canary_candidate_count = 3,
                  content_canary_failed_count = 0,
                  content_canary_passed_at = 7001,
                  content_generation_completed_at = 7002,
                  stage_progress_json = JSON_OBJECT(
                    'candidateCount', 30, 'canaryCandidateCount', 3,
                    'canaryFailedCount', 0, 'canaryTargetCount', 3,
                    'failedCount', 0, 'targetCount', 30),
                  progress_percent = 35, ready_course_count = 0,
                  failed_course_count = 0, next_run_at = NULL,
                  lease_token = NULL, lease_expires_at = NULL,
                  heartbeat_at = NULL, hard_deadline_at = NULL,
                  work_unit_kind = NULL, classroom_ready_count = 0,
                  speech_ready_count = 0, validation_ready_count = 0,
                  published_course_count = 0, updated_at = 8010
                WHERE id = ?
                """,
                (fixture["plan_id"],),
            )
            # Production handoff now requires a persisted successful provider
            # probe. This is fixture evidence only; no external call is made.
            self.runtimes.close_formal_provider_circuit_after_probe(conn, now=8020)
        return {
            **fixture,
            "item_id": first_item_id,
            "course_id": str(first_item["course_id"]),
            "package_id": f"formal-{suffix}-package-1",
        }

    def test_library_failure_is_skipped_without_reissuing_or_blocking_other_subjects(self):
        from repositories.course_supply_repository import record_supply_incident
        fixture = self._seed_formal_candidate_handoff('library-isolation')
        with self.database.transaction() as conn:
            plan = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id = ?', (fixture['plan_id'],)).fetchone()
            fingerprint = plan['target_fingerprint']
            conn.execute('UPDATE learning_curriculum_preparation_plans SET family_id = NULL, child_id = NULL, grade_selection_revision = 0, library_target_fingerprint = target_fingerprint WHERE id = ?', (plan['id'],))
            for subject, skill in [('chinese', 'pinyin_syllables'), ('math', 'number_sense_20'), ('english', 'letters_sounds')]:
                conn.execute("INSERT INTO learning_course_supply_requests(target_fingerprint,subject,skill_id,variant_ordinal,priority,purpose,created_at,updated_at) VALUES (?,?,?,1,0,'canary',1,1)", (fingerprint,subject,skill))
            conn.execute('DELETE FROM children WHERE id = ?', (plan['child_id'],))
            self.assertIsNotNone(conn.execute('SELECT id FROM learning_curriculum_preparation_plans WHERE id = ?', (plan['id'],)).fetchone())
            self.runtimes.close_formal_provider_circuit_after_probe(conn, now=8020)
            first = self.packages.get_next_formal_candidate_authority(conn)
            self.assertEqual(first['subject'], 'chinese')
            math_item = conn.execute("SELECT id FROM learning_catalog_build_items WHERE build_job_id = ? AND subject = 'math' AND skill_id = 'number_sense_20' AND variant_ordinal = 1", (plan['catalog_build_id'],)).fetchone()
            conn.execute('DELETE FROM learning_curriculum_classroom_item_receipts WHERE build_item_id = ?', (math_item['id'],))
            conn.execute('DELETE FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id = ?', (math_item['id'],))
            record_supply_incident(conn, item_id=first['build_item_id'], stage='classroom', reason='known_generation_failure', now=8021)
            next_item = self.packages.get_next_formal_candidate_authority(conn)
            self.assertEqual(next_item['subject'], 'math')
            self.assertNotEqual(next_item['build_item_id'], first['build_item_id'])
            self.runtimes.open_formal_provider_circuit(conn, reason_code='quota_exhausted', runtime_id=None, now=8022)
            self.assertIsNone(self.packages.get_next_formal_candidate_authority(conn))

    def test_library_sees_resumed_classroom_before_a_completion_receipt(self):
        from services.course_library_service import CourseLibraryService

        fixture, candidate = self._seed_staged_formal_candidate('library-resumed-progress')
        manifest = self._formal_runtime_feature_manifest(candidate)
        with self.database.transaction() as conn:
            conn.execute('UPDATE learning_curriculum_preparation_plans SET family_id = NULL, child_id = NULL, grade_selection_revision = 0, library_target_fingerprint = target_fingerprint WHERE id = ?', (fixture['plan_id'],))
            conn.execute("INSERT INTO learning_course_supply_requests(target_fingerprint,subject,skill_id,variant_ordinal,priority,purpose,created_at,updated_at) VALUES (?,'chinese','pinyin_syllables',1,0,'canary',1,1)", (fixture['fingerprint'],))
            runtime, _ = self.runtimes.reserve_candidate_runtime(
                conn, runtime_id='library-resumed-runtime', feature_manifest=manifest,
                now=840000, **candidate,
            )
            self.runtimes.mark_generating(conn, runtime_id=runtime['id'], upstream_job_id='library-resumed-upstream', now=840010)
        library = CourseLibraryService(self.database_url, clock=lambda: 860000)
        status = library.status()
        self.assertEqual(status['lastProgressAt'], 840000)
        self.assertEqual(status['items'][0]['runtime_status'], 'generating')
        self.assertFalse(status['stalled'])
        self.assertEqual(status['readyCount'], 0)
        with self.database.transaction() as conn:
            self.runtimes.mark_generating(conn, runtime_id=runtime['id'], upstream_job_id='library-resumed-upstream', now=1500000)
        library.clock = lambda: 1500000
        self.assertTrue(library.status()['stalled'])
        # A stopped worker cannot be required to discover a terminal failure
        # before the read-only status reports it to waiting families.
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_openmaic_runtime_classrooms SET status = 'failed', quality_status = 'rejected', error_code = 'openmaic_formal_generation_failed' WHERE id = ?", (runtime['id'],))
        self.assertTrue(library.status()['blocked'])

    def test_completion_uses_library_owner_and_never_falls_back_to_a_child_follower(self):
        fixture, candidate = self._seed_staged_formal_candidate('library-owner-completion')
        with self.database.transaction() as conn:
            runtime, _ = self.runtimes.reserve_candidate_runtime(
                conn, runtime_id='library-owner-completion-runtime',
                feature_manifest=self._formal_runtime_feature_manifest(candidate), now=8400, **candidate,
            )
            self.runtimes.mark_generating(conn, runtime_id=runtime['id'],
                upstream_job_id='library-owner-completion-upstream', now=8410)
            original = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id = ?',
                (fixture['plan_id'],)).fetchone()
            conn.execute('UPDATE learning_curriculum_preparation_plans SET family_id = NULL, child_id = NULL, '
                'grade_selection_revision = 0, library_target_fingerprint = target_fingerprint, published_course_count = 1, '
                'classroom_ready_count = 1, speech_ready_count = 1, validation_ready_count = 1 '
                'WHERE id = ?', (original['id'],))
            conn.execute('UPDATE learning_catalog_releases SET ready_item_count = 1 WHERE id = ?',
                (fixture['release_id'],))
            follower, _ = self.preparations.reserve_plan(conn, family_id=original['family_id'],
                child_id=original['child_id'], grade_code='primary_1', school_year_start_year=2026,
                grade_selection_revision=1, target=json.loads(original['target_spec_json']),
                target_fingerprint=fixture['fingerprint'], request_id='library-owner-child-follower',
                shared_build_request_id=original['shared_build_request_id'], now=8500)
            conn.execute("""UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'building_classrooms', catalog_build_id = ?, catalog_release_id = ?,
                  content_candidate_count = 30, content_canary_candidate_count = 3,
                  content_canary_passed_at = 8501, content_generation_completed_at = 8502,
                  progress_percent = 35, next_run_at = NULL, last_progress_at = 8502, updated_at = 8502,
                  stage_progress_json = JSON_OBJECT('candidateCount', 30, 'canaryCandidateCount', 3,
                    'canaryFailedCount', 0, 'canaryTargetCount', 3, 'failedCount', 0, 'targetCount', 30)
                WHERE id = ?""", (fixture['build_id'], fixture['release_id'], follower['id']))
            args = dict(runtime_id=runtime['id'], build_item_id=fixture['item_id'],
                target_fingerprint=fixture['fingerprint'], expected_upstream_job_id='library-owner-completion-upstream')
            authority = self.runtimes.assert_candidate_completion_authority(conn, **args)
            self.assertEqual(authority['preparation_plan_id'], original['id'])
            # Even a fully reconciled follower cannot authorize completion while
            # the actual production owner is no longer running.
            conn.execute("UPDATE learning_curriculum_preparation_plans SET status = 'failed', stage = 'completed', "
                "completed_at = 9000, error_code = 'test_owner_stopped', error_message_safe = 'Owner stopped' WHERE id = ?",
                (original['id'],))
            conn.execute('UPDATE learning_curriculum_preparation_plans SET published_course_count = 1, '
                'classroom_ready_count = 1, speech_ready_count = 1, validation_ready_count = 1 WHERE id = ?',
                (follower['id'],))
            with self.assertRaisesRegex(ValueError, 'completion authority'):
                self.runtimes.assert_candidate_completion_authority(conn, **args)

    def test_saved_publication_window_requires_exact_ready_runtime_and_expired_owner_lease(self):
        fixture = self._seed_formal_ready_plan('saved-publication-window')
        with self.database.transaction() as conn:
            conn.execute('UPDATE learning_curriculum_preparation_plans SET family_id = NULL, child_id = NULL, '
                'grade_selection_revision = 0, library_target_fingerprint = target_fingerprint WHERE id = ?',
                (fixture['plan_id'],))
            receipt = conn.execute('SELECT * FROM learning_curriculum_classroom_item_receipts WHERE build_item_id = ?',
                (fixture['item_ids'][0],)).fetchone()
            conn.execute("UPDATE learning_curriculum_classroom_item_receipts SET publication_status = 'pending', "
                'publication_receipt_hash = NULL, published_at = NULL WHERE build_item_id = ?', (fixture['item_ids'][0],))
            conn.execute("UPDATE learning_openmaic_runtime_classrooms SET upstream_job_id = 'saved-complete-job' WHERE id = ?",
                (receipt['runtime_classroom_id'],))
            args = dict(plan_id=fixture['plan_id'], lease_token=fixture['lease_token'],
                runtime_id=receipt['runtime_classroom_id'], upstream_job_id='saved-complete-job',
                target_fingerprint=fixture['fingerprint'], now=10_000, lease_ms=600_000)
            for wrong in ({'lease_token': 'stale-token'}, {'upstream_job_id': 'other-job'},
                          {'runtime_id': 'missing-runtime'}, {'now': 8_500}):
                self.assertIsNone(self.preparations.renew_saved_classroom_publication_lease(conn, **{**args, **wrong}))
            with self.assertRaises(ValueError):
                self.preparations.renew_saved_classroom_publication_lease(conn, **{**args, 'lease_ms': 600_001})
            renewed = self.preparations.renew_saved_classroom_publication_lease(conn, **args)
            self.assertEqual(renewed['hard_deadline_at'], 610_000)
            self.assertEqual(renewed['lease_expires_at'], 610_000)
            self.assertEqual(renewed['lease_token'], fixture['lease_token'])
            self.assertEqual(renewed['published_course_count'], 29)
            self.assertIsNone(self.preparations.renew_saved_classroom_publication_lease(conn, **args))

    def _seed_staged_formal_candidate(
        self, suffix: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        fixture = self._seed_formal_candidate_handoff(suffix)
        with self.database.transaction() as conn:
            self.runtimes.close_formal_provider_circuit_after_probe(
                conn,
                now=8_020,
            )
        issued: list[dict[str, object]] = []

        class StagingRuntime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                issued.append(dict(kwargs))
                return {
                    "ok": True,
                    "runtime": {
                        "id": f"formal-{suffix}-staging-only",
                        "requestId": kwargs["runtime_request_id"],
                        "status": "generating",
                    },
                }

        package_service = object.__new__(LessonPackageService)
        package_service.repository = self.packages
        package_service.validator = LessonPackageValidator()
        result = package_service.process_next_formal_candidate(StagingRuntime())
        self.assertIsNotNone(result)
        self.assertEqual(len(issued), 1)
        self.assertEqual(result.payload["package"]["status"], "candidate")
        return fixture, issued[0]

    def _seed_candidate(self, suffix: str) -> dict[str, object]:
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        boundary = target["boundaries"][0]
        course_id = f"formal-{suffix}-course"
        package_id = f"formal-{suffix}-package"
        runtime_id = f"formal-{suffix}-runtime-1"
        job_id = f"formal-{suffix}-job"
        artifact_id = f"formal-{suffix}-artifact"
        with self.database.transaction() as conn:
            build, _ = self.catalog.create_or_get_build(
                conn,
                request_id=f"formal-{suffix}-build",
                curriculum_version=str(target["curriculumVersion"]),
                title=f"Formal {suffix}",
                target_spec=target,
                targets=(
                    {
                        "gradeCode": "primary_1",
                        "subject": boundary["subject"],
                        "skillId": boundary["skillId"],
                        "boundaryVersion": boundary["boundaryVersion"],
                    },
                ),
                variants_per_boundary=1,
                now=1_000,
            )
            item = self.catalog.list_build_items(
                conn, build_id=str(build["id"]), for_update=True
            )[0]
            conn.execute(
                "UPDATE learning_catalog_build_jobs "
                "SET execution_mode = 'content_only', content_manifest_version = ?, "
                "canary_manifest_json = ?, stage_ceiling = 'content_ready' "
                "WHERE id = ?",
                (
                    target["schemaVersion"],
                    self.catalog.encode_json(target["canaryManifest"]),
                    build["id"],
                ),
            )
            conn.execute(
                "INSERT INTO learning_courses("
                "id, version, grade_code, subject, node_code, curriculum_version, "
                "boundary_version, title, objective, status, quality_status, "
                "content_json, created_at, updated_at) VALUES ("
                "?, '1', 'primary_1', ?, ?, ?, ?, ?, 'Objective', 'validated', "
                "'auto_validated', ?, 1, 1)",
                (
                    course_id,
                    boundary["subject"],
                    boundary["skillId"],
                    target["curriculumVersion"],
                    boundary["boundaryVersion"],
                    f"Formal {suffix}",
                    _formal_course_content(f"formal-{suffix}"),
                ),
            )
            conn.execute(
                "INSERT INTO learning_classroom_generation_jobs("
                "id, request_id, course_id, course_version, generator, status, "
                "created_at, updated_at) VALUES (?, ?, ?, '1', 'formal', "
                "'completed', 1, 1)",
                (job_id, f"request-{job_id}", course_id),
            )
            conn.execute(
                "INSERT INTO learning_classroom_source_artifacts("
                "id, job_id, request_id, source_format, dsl_version, status, "
                "source_hash, payload_json, created_at, updated_at) VALUES ("
                "?, ?, ?, 'json', 'v1', 'validated', ?, '{}', 1, 1)",
                (
                    artifact_id,
                    job_id,
                    f"request-{artifact_id}",
                    hashlib.sha256(f"source-{suffix}".encode()).hexdigest(),
                ),
            )
            conn.execute(
                "INSERT INTO learning_lesson_packages("
                "id, version, course_id, course_version, schema_version, status, "
                "source_artifact_id, compiler_version, public_content_hash, "
                "private_content_hash, public_payload_json, validation_report_json, "
                "created_at, published_at, updated_at) VALUES ("
                "?, 1, ?, '1', 'v1', 'published', ?, 'v1', ?, ?, '{}', '{}', "
                "1, 1, 1)",
                (
                    package_id,
                    course_id,
                    artifact_id,
                    hashlib.sha256(f"public-{suffix}".encode()).hexdigest(),
                    hashlib.sha256(f"private-{suffix}".encode()).hexdigest(),
                ),
            )
            conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET execution_mode_snapshot = 'content_only',
                  content_manifest_version_snapshot = ?, subject_ordinal = 1,
                  boundary_ordinal = 1, status = 'course_ready',
                  attempt_count = 1, active_generation_request_id = ?,
                  course_id = ?, course_version = '1',
                  content_phase = 'course_ready', content_gate_status = 'passed',
                  content_gate_attempt_count = 1, content_gate_passed_at = 1000,
                  content_validation_contract_version = ?,
                  content_receipt_hash = ?, content_claim_attempt_ordinal = 1,
                  updated_at = 1000
                WHERE id = ?
                """,
                (
                    target["schemaVersion"],
                    f"active-{suffix}-generation",
                    course_id,
                    "mira.learning.primary-1-content-validation.v1",
                    hashlib.sha256(f"content-{suffix}".encode()).hexdigest(),
                    item["id"],
                ),
            )
            runtime = self.runtimes.create_runtime_classroom(
                conn,
                runtime_id=runtime_id,
                request_id=f"runtime-{suffix}-request-1",
                course={
                    "course_id": course_id,
                    "course_version": "1",
                    "package_id": package_id,
                    "package_version": 1,
                },
                feature_manifest={"schemaVersion": "formal-test.v1"},
                now=1_500,
            )
            self.runtimes.mark_ready(
                conn,
                runtime_id=runtime_id,
                upstream_classroom_id=f"upstream-{suffix}-1",
                feature_manifest={"schemaVersion": "formal-test.v1"},
                now=1_600,
            )
            bound = self.runtimes.bind_candidate_runtime(
                conn,
                runtime_id=runtime_id,
                build_item_id=str(item["id"]),
                target_fingerprint=fingerprint,
                now=2_000,
            )
            receipt, created = self.catalog.reserve_classroom_item_receipt(
                conn,
                build_item_id=str(item["id"]),
                runtime_classroom_id=runtime_id,
                target_fingerprint=fingerprint,
                now=2_000,
            )
        self.assertEqual(runtime["id"], runtime_id)
        self.assertEqual(bound["candidate_build_item_id"], item["id"])
        self.assertTrue(created)
        self.assertEqual(receipt["runtime_classroom_id"], runtime_id)
        return {
            "target": target,
            "fingerprint": fingerprint,
            "build_id": str(build["id"]),
            "release_id": str(build["release_id"]),
            "item_id": str(item["id"]),
            "course_id": course_id,
            "package_id": package_id,
            "runtime_id": runtime_id,
            "suffix": suffix,
        }

    @staticmethod
    def _insert_formal_retry_runtime(
        conn, *, fixture: dict[str, object], attempt_ordinal: int
    ) -> str:
        runtime_id = f"formal-{fixture['suffix']}-runtime-{attempt_ordinal}"
        conn.execute(
            """
            INSERT INTO learning_openmaic_runtime_classrooms(
              id, request_id, attempt_ordinal, retry_of_runtime_id,
              retry_reason, expected_previous_job_id,
              course_id, course_version, package_id, package_version,
              upstream_classroom_id, status, quality_status,
              feature_manifest_json, created_at, updated_at, ready_at,
              candidate_build_item_id, candidate_release_id,
              candidate_grade_code, candidate_target_fingerprint,
              candidate_binding_contract_version, candidate_bound_at
            ) VALUES (?, ?, ?, ?, ?, 'formal-previous-job', ?, '1', ?, 1,
              ?, 'ready', 'pending_review', '{}', 2001, 2001, 2001,
              ?, ?, 'primary_1', ?, ?, 2001)
            """,
            (
                runtime_id,
                f"request-{runtime_id}",
                attempt_ordinal,
                fixture["runtime_id"],
                f"formal_candidate_retry_{attempt_ordinal}",
                fixture["course_id"],
                fixture["package_id"],
                f"upstream-{fixture['suffix']}-{attempt_ordinal}",
                fixture["item_id"],
                fixture["release_id"],
                fixture["fingerprint"],
                OpenMaicRuntimeRepository.CANDIDATE_BINDING_CONTRACT_VERSION,
            ),
        )
        return runtime_id


if __name__ == "__main__":
    unittest.main()
