from __future__ import annotations

import json
import unittest
from contextlib import contextmanager

from repositories.learning_catalog_repository import (
    LearningCatalogActivationError,
    LearningCatalogRepository,
)
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_curriculum_preparation_runner import (
    FormalProductionStageAdapter,
    PreparationDeterministicError,
)


def _plan(stage: str) -> dict[str, object]:
    return {
        "id": "plan-1",
        "lease_token": "lease-1",
        "stage": stage,
        "grade_code": "primary_2",
        "catalog_build_id": "build-1",
        "catalog_release_id": "release-1",
        "target_fingerprint": "a" * 64,
        "ready_course_count": 0,
        "failed_course_count": 0,
        "subject_progress_json": {
            "chinese": {
                "totalCourseCount": 12,
                "readyCourseCount": 0,
                "failedCourseCount": 0,
                "contentCandidateCount": 12,
                "contentFailedCount": 0,
            },
            "math": {
                "totalCourseCount": 9,
                "readyCourseCount": 0,
                "failedCourseCount": 0,
                "contentCandidateCount": 9,
                "contentFailedCount": 0,
            },
            "english": {
                "totalCourseCount": 9,
                "readyCourseCount": 0,
                "failedCourseCount": 0,
                "contentCandidateCount": 9,
                "contentFailedCount": 0,
            },
        },
    }


class _NoopRepository:
    pass


class _FormalPublicationService:
    def __init__(self, validation: dict[str, object]):
        self.validation = validation
        self.publication_calls: list[dict[str, object]] = []

    def advance_grade_validation(self, **_kwargs):
        return dict(self.validation)

    def activate_grade_release(self, **kwargs):
        self.publication_calls.append(dict(kwargs))
        return {
            "status": "ready",
            "stage": "completed",
            "completedPlanCount": 2,
            "releaseId": "release-1",
        }


class LearningGradeAtomicPublicationTest(unittest.TestCase):
    def _adapter(self, service: _FormalPublicationService):
        return FormalProductionStageAdapter(
            service,
            repository=_NoopRepository(),
            runtime_candidate_processor=None,
            formal_repository=None,
            formal_audio_service=None,
            formal_auto_publication_enabled=True,
            formal_provider_readiness_client=object(),
            formal_route_probe_service=object(),
            formal_route_probe_client=object(),
            clock=lambda: 1_000,
        )

    def test_ambiguous_provider_receipt_stops_before_publication(self):
        adapter = self._adapter(
            _FormalPublicationService(
                {
                    "total": 30,
                    "ready": 7,
                    "failed": 0,
                    "ambiguous": 1,
                }
            )
        )

        with self.assertRaises(PreparationDeterministicError):
            adapter.advance(
                _plan("validating"), now_ms=1_000, heartbeat=lambda: True
            )

    def test_complete_validation_hands_off_to_publishing(self):
        service = _FormalPublicationService(
            {"total": 30, "ready": 30, "failed": 0, "ambiguous": 0}
        )
        adapter = self._adapter(service)

        result = adapter.advance(
            _plan("validating"), now_ms=1_000, heartbeat=lambda: True
        )

        self.assertEqual((result.next_status, result.next_stage), ("running", "publishing"))
        self.assertTrue(result.already_persisted)
        self.assertEqual(service.publication_calls, [])

    def test_publishing_uses_one_grade_scoped_request_and_completes_ready(self):
        service = _FormalPublicationService(
            {"total": 30, "ready": 30, "failed": 0, "ambiguous": 0}
        )
        adapter = self._adapter(service)

        result = adapter.advance(
            _plan("publishing"), now_ms=1_000, heartbeat=lambda: True
        )

        self.assertEqual((result.next_status, result.next_stage), ("ready", "completed"))
        self.assertTrue(result.already_persisted)
        self.assertEqual(len(service.publication_calls), 1)
        call = service.publication_calls[0]
        self.assertEqual(call["grade_code"], "primary_2")
        self.assertEqual(call["build_id"], "build-1")
        self.assertEqual(call["target_fingerprint"], "a" * 64)
        self.assertEqual(call["publisher_plan_id"], "plan-1")
        self.assertEqual(call["publisher_lease_token"], "lease-1")
        self.assertTrue(str(call["publication_request_id"]).startswith("formal-publish:"))
        self.assertEqual(
            {
                subject: item["readyCourseCount"]
                for subject, item in call["subject_progress"].items()
            },
            {"chinese": 12, "math": 9, "english": 9},
        )
        self.assertEqual(
            sum(
                item["readyCourseCount"]
                for item in result.subject_progress.values()
            ),
            30,
        )

    def test_classroom_receipt_recheck_binds_formal_teacher_evidence(self):
        row = {
            "build_item_id": "item-1",
            "runtime_classroom_id": "runtime-1",
            "runtime_request_id": "runtime-request-1",
            "upstream_job_id": "upstream-job-1",
            "upstream_classroom_id": "upstream-classroom-1",
            "audio_target_fingerprint": "a" * 64,
        }
        manifest = {
            "sourceCourseContentSha256": "b" * 64,
            "teachingBriefSha256": "c" * 64,
            "generationContract": {
                "teacher": {"runtime": {"name": "小数老师"}},
            },
            "classroomContentSha256": "d" * 64,
            "formalRuntimeContract": {"exactSceneCount": 10},
            "formalEvidence": {
                "teacher": {
                    "agentId": "teacher-1",
                    "name": "小数老师",
                    "avatar": "/avatars/math-teacher.png",
                    "teacherGender": "male",
                    "voiceGender": "male",
                    "voiceId": "Ethan",
                }
            },
        }

        original = LearningCatalogRepository.formal_classroom_receipt_sha256(
            row, manifest
        )
        drifted = dict(manifest)
        drifted["formalEvidence"] = {
            "teacher": {**manifest["formalEvidence"]["teacher"], "voiceId": "Serena"}
        }

        self.assertNotEqual(
            original,
            LearningCatalogRepository.formal_classroom_receipt_sha256(
                row, drifted
            ),
        )

    def test_classroom_receipt_recheck_recovers_legacy_nested_source_hashes(self):
        row = {
            "build_item_id": "item-1",
            "runtime_classroom_id": "runtime-1",
            "runtime_request_id": "runtime-request-1",
            "upstream_job_id": "upstream-job-1",
            "upstream_classroom_id": "upstream-classroom-1",
            "audio_target_fingerprint": "a" * 64,
        }
        manifest = {
            "sourceCourseContentSha256": "b" * 64,
            "teachingBriefSha256": "c" * 64,
            "generationContract": {
                "sourceCourseContentSha256": "b" * 64,
                "teachingBriefSha256": "c" * 64,
            },
            "classroomContentSha256": "d" * 64,
            "formalRuntimeContract": {"exactSceneCount": 10},
            "formalEvidence": {"teacher": {"voiceId": "Serena"}},
        }
        expected = LearningCatalogRepository.formal_classroom_receipt_sha256(
            row, manifest
        )
        legacy_manifest = dict(manifest)
        legacy_manifest.pop("sourceCourseContentSha256")
        legacy_manifest.pop("teachingBriefSha256")

        self.assertEqual(
            LearningCatalogRepository.formal_classroom_receipt_sha256(
                row, legacy_manifest
            ),
            expected,
        )

    def test_release_provider_receipt_is_bound_uniquely_to_each_item(self):
        witness = {
            "build_item_id": "item-1",
            "runtime_classroom_id": "runtime-1",
            "classroom_content_sha256": "1" * 64,
            "audio_terminal_receipt_hash": "2" * 64,
        }
        base = {
            "release_id": "release-1",
            "grade_code": "primary_1",
            "receipt_target_fingerprint": "a" * 64,
            "classroom_receipt_hash": "3" * 64,
            "tts_receipt_hash": "4" * 64,
            "asr_roundtrip_receipt_hash": "5" * 64,
            "audio_terminal_receipt_hash": "6" * 64,
        }
        first = LearningCatalogRepository.formal_provider_item_binding_sha256(
            {
                **base,
                "build_item_id": "item-1",
                "runtime_classroom_id": "runtime-1",
            },
            witness=witness,
            provider_receipt_hash="7" * 64,
        )
        second = LearningCatalogRepository.formal_provider_item_binding_sha256(
            {
                **base,
                "build_item_id": "item-2",
                "runtime_classroom_id": "runtime-2",
            },
            witness=witness,
            provider_receipt_hash="7" * 64,
        )

        self.assertNotEqual(first, second)


class _AtomicCatalogRepository:
    def __init__(self, *, item_count: int = 30):
        self.conn = object()
        self.item_count = item_count
        self.calls: list[tuple[str, object]] = []

    @contextmanager
    def transaction(self):
        yield self.conn

    def lock_formal_publication_authority(self, conn, **_kwargs):
        self.calls.append(("lock", conn))
        return {
            "releaseId": "release-1",
            "itemCount": self.item_count,
            "readyItemCount": self.item_count,
            "publicationReceiptSha256": "b" * 64,
        }

    def publish_formal_grade_release(self, conn, **_kwargs):
        self.calls.append(("publish", conn))

    def activate_grade_release_pointer(self, conn, **_kwargs):
        self.calls.append(("pointer", conn))
        return {
            "history_id": "history-1",
            "release_id": "release-1",
            "publication_receipt_hash": "b" * 64,
        }


class _AtomicPreparationRepository:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def complete_matching_formal_ready(self, conn, **_kwargs):
        self.calls.append(("complete", conn))
        return 2


class _ObserveCatalogRepository(_AtomicCatalogRepository):
    def prepare_formal_validation_step(self, conn, **_kwargs):
        self.calls.append(("prepare", conn))
        return {"action": "observe", "requestId": "provider-ready-1"}

    def persist_formal_provider_readiness(self, conn, **kwargs):
        self.calls.append(("persist", conn))
        self.persisted_response = kwargs["response"]
        self.persisted_kwargs = kwargs

    def formal_validation_counts(self, conn, **_kwargs):
        self.calls.append(("counts", conn))
        return {"total": 30, "ready": 30, "failed": 0, "ambiguous": 0}


class _ObserveClient:
    def __init__(self):
        self.get_calls: list[str] = []

    def start_formal_provider_readiness(self, **_kwargs):
        raise AssertionError("an observed readiness job must never be POSTed again")

    def get_formal_provider_readiness(self, request_id: str):
        self.get_calls.append(request_id)
        return {
            "requestId": request_id,
            "status": "auto_validated",
            "providerReceiptSha256": "c" * 64,
        }


class _ValidationPreparationRepository:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def persist_formal_validation_progress(self, conn, **_kwargs):
        self.calls.append(("handoff", conn))
        return True, "publishing"


class _ProgressiveCatalogRepository:
    def __init__(self):
        self.conn = object()
        self.calls: list[tuple[str, object]] = []
        self.publications: list[dict[str, object]] = []

    @contextmanager
    def transaction(self):
        yield self.conn

    def prepare_formal_validation_step(self, conn, **_kwargs):
        self.calls.append(("prepare", conn))
        return {"action": "complete"}

    def formal_validation_counts(self, conn, **_kwargs):
        self.calls.append(("counts", conn))
        return {"total": 3, "ready": 3, "failed": 0, "ambiguous": 0}

    def lock_progressive_formal_publication_authority(self, conn, **_kwargs):
        self.calls.append(("lock-progressive", conn))
        return {
            "releaseId": "release-1",
            "itemCount": 3,
            "readyItemCount": 3,
            "publishedAt": 2_000,
            "items": [{"build_item_id": f"item-{ordinal}"} for ordinal in range(3)],
        }

    def publish_formal_grade_release(self, conn, **kwargs):
        self.calls.append(("publish-progressive", conn))
        self.publications.append(dict(kwargs))


class _ProgressivePreparationRepository:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def persist_progressive_formal_counts(self, conn, **_kwargs):
        self.calls.append(("persist-progressive", conn))
        return 3


class OpenMaicProgressiveRuntimeAuthorityTest(unittest.TestCase):
    def test_partial_handoff_allows_only_canary_until_canary_gate_passes(self):
        from services.learning_curriculum_preparation_contract import build_preparation_target
        target = build_preparation_target("primary_1")
        release = {
            "status": "draft",
            "quality_status": "building",
            "activated_at": None,
            "retired_at": None,
            "ready_item_count": 0,
        }
        build = {
            "target_spec_json": json.dumps(target),
            "execution_mode": "content_only",
            "stage_ceiling": "content_ready",
            "status": "running",
            "total_item_count": 30,
            "ready_item_count": 0,
            "failed_item_count": 0,
            "error_code": None,
            "error_message_safe": None,
            "completed_at": None,
            "content_manifest_version": "manifest-v1",
            "canary_manifest_json": json.dumps(
                {
                    "targets": [
                        {
                            "subject": "chinese",
                            "skillId": "chi-1",
                            "variantOrdinal": 1,
                        }
                    ]
                }
            ),
        }
        item = {
            "grade_code": "primary_1",
            "subject": "chinese",
            "skill_id": "chi-1",
            "variant_ordinal": 1,
            "content_phase": "course_ready",
            "status": "course_ready",
            "content_gate_status": "passed",
            "content_receipt_hash": "b" * 64,
            "execution_mode_snapshot": "content_only",
            "content_manifest_version_snapshot": "manifest-v1",
        }
        plan = {
            "grade_code": "primary_1",
            "target_spec_json": json.dumps(target),
            "status": "running",
            "stage": "generating_content",
            "content_target_count": 30,
            "content_candidate_count": 1,
            "content_failed_count": 0,
            "content_canary_target_count": 3,
            "content_canary_candidate_count": 1,
            "content_canary_failed_count": 0,
            "content_canary_passed_at": None,
            "content_generation_completed_at": None,
            "ready_course_count": 0,
            "failed_course_count": 0,
            "published_course_count": 0,
            "completed_at": None,
            "superseded_at": None,
            "error_code": None,
            "error_message_safe": None,
        }

        self.assertTrue(
            OpenMaicRuntimeRepository._candidate_content_handoff_is_current(
                release=release,
                build=build,
                item=item,
                plan=plan,
                complete_item_count=1,
            )
        )
        non_canary = {**item, "subject": "math", "skill_id": "math-2"}
        self.assertFalse(
            OpenMaicRuntimeRepository._candidate_content_handoff_is_current(
                release=release,
                build=build,
                item=non_canary,
                plan=plan,
                complete_item_count=1,
            )
        )
        passed_plan = {
            **plan,
            "content_candidate_count": 3,
            "content_canary_candidate_count": 3,
            "content_canary_passed_at": 2_000,
        }
        self.assertTrue(
            OpenMaicRuntimeRepository._candidate_content_handoff_is_current(
                release=release,
                build=build,
                item=non_canary,
                plan=passed_plan,
                complete_item_count=3,
            )
        )

        # The same handoff stays strict for the registered 27-course grades.
        for grade in ("primary_2", "primary_6"):
            grade_target = build_preparation_target(grade)
            grade_build = {**build, "target_spec_json": json.dumps(grade_target), "total_item_count": 27}
            grade_item = {**item, "grade_code": grade}
            grade_plan = {**plan, "grade_code": grade, "target_spec_json": json.dumps(grade_target), "content_target_count": 27}
            with self.subTest(grade=grade):
                self.assertTrue(OpenMaicRuntimeRepository._candidate_content_handoff_is_current(
                    release=release, build=grade_build, item=grade_item, plan=grade_plan, complete_item_count=1))
                for invalid in ({"content_target_count": 30}, {"grade_code": "primary_1"}, {"status": "failed"}):
                    self.assertFalse(OpenMaicRuntimeRepository._candidate_content_handoff_is_current(
                        release=release, build=grade_build, item=grade_item, plan={**grade_plan, **invalid}, complete_item_count=1))


class LearningGradePublicationServiceTest(unittest.TestCase):
    def _service(self, repository):
        return LearningCatalogReleaseService(
            "sqlite://ignored",
            dynamic_generation_service=None,
            lesson_package_service=None,
            repository=repository,
            clock_ms=lambda: 2_000,
        )

    def test_existing_readiness_job_is_observed_by_get_only(self):
        repository = _ObserveCatalogRepository()
        preparations = _ValidationPreparationRepository()
        client = _ObserveClient()
        service = self._service(repository)

        result = service.advance_grade_validation(
            grade_code="primary_2",
            build_id="build-1",
            release_id="release-1",
            target_fingerprint="a" * 64,
            publisher_plan_id="plan-1",
            publisher_lease_token="lease-1",
            preparation_repository=preparations,
            provider_readiness_client=client,
            route_probe_service=object(),
            route_probe_client=object(),
        )

        self.assertEqual(client.get_calls, ["provider-ready-1"])
        self.assertEqual(result["ready"], 30)
        self.assertEqual(repository.persisted_kwargs["publisher_plan_id"], "plan-1")
        self.assertEqual(
            repository.persisted_kwargs["publisher_lease_token"], "lease-1"
        )
        self.assertEqual(preparations.calls, [("handoff", repository.conn)])

    def test_progressive_canary_publication_is_repeatable_without_pointer_switch(self):
        repository = _ProgressiveCatalogRepository()
        preparations = _ProgressivePreparationRepository()
        service = self._service(repository)
        args = {
            "grade_code": "primary_1",
            "build_id": "build-1",
            "release_id": "release-1",
            "target_fingerprint": "a" * 64,
            "publisher_plan_id": "plan-1",
            "publisher_lease_token": "lease-1",
            "publisher_stage": "generating_content",
            "preparation_repository": preparations,
            "provider_readiness_client": object(),
            "route_probe_service": object(),
            "route_probe_client": object(),
        }

        first = service.advance_progressive_grade_validation(**args)
        second = service.advance_progressive_grade_validation(**args)

        self.assertEqual(
            first,
            {
                "total": 3,
                "ready": 3,
                "failed": 0,
                "ambiguous": 0,
                "published": 3,
            },
        )
        self.assertEqual(second, first)
        self.assertEqual(len(repository.publications), 2)
        request_ids = {
            str(call["publication_request_id"])
            for call in repository.publications
        }
        self.assertEqual(len(request_ids), 1)
        self.assertTrue(next(iter(request_ids)).startswith("formal-progressive:"))
        self.assertTrue(
            all(call["finalize_release"] is False for call in repository.publications)
        )
        self.assertFalse(
            any(name == "pointer" for name, _conn in repository.calls)
        )
        self.assertTrue(all(conn is repository.conn for _, conn in repository.calls))
        self.assertEqual(
            preparations.calls,
            [
                ("persist-progressive", repository.conn),
                ("persist-progressive", repository.conn),
            ],
        )

    def test_atomic_publication_rejects_29_items_without_side_effects(self):
        repository = _AtomicCatalogRepository(item_count=29)
        preparations = _AtomicPreparationRepository()
        service = self._service(repository)

        with self.assertRaises(LearningCatalogActivationError):
            service.activate_grade_release(
                grade_code="primary_2",
                build_id="build-1",
                target_fingerprint="a" * 64,
                publication_request_id="formal-publish:one",
                publisher_plan_id="plan-1",
                publisher_lease_token="lease-1",
                preparation_repository=preparations,
                subject_progress={
                    "chinese": {"target": 10, "ready": 10, "failed": 0},
                    "math": {"target": 10, "ready": 10, "failed": 0},
                    "english": {"target": 10, "ready": 10, "failed": 0},
                },
            )

        self.assertEqual(repository.calls, [("lock", repository.conn)])
        self.assertEqual(preparations.calls, [])

    def test_atomic_publication_switches_pointer_and_plans_in_one_transaction(self):
        repository = _AtomicCatalogRepository()
        preparations = _AtomicPreparationRepository()
        service = self._service(repository)

        result = service.activate_grade_release(
            grade_code="primary_2",
            build_id="build-1",
            target_fingerprint="a" * 64,
            publication_request_id="formal-publish:one",
            publisher_plan_id="plan-1",
            publisher_lease_token="lease-1",
            preparation_repository=preparations,
            subject_progress={
                "chinese": {"target": 10, "ready": 10, "failed": 0},
                "math": {"target": 10, "ready": 10, "failed": 0},
                "english": {"target": 10, "ready": 10, "failed": 0},
            },
        )

        self.assertEqual([name for name, _ in repository.calls], ["lock", "publish", "pointer"])
        self.assertTrue(all(conn is repository.conn for _, conn in repository.calls))
        self.assertEqual(preparations.calls, [("complete", repository.conn)])
        self.assertEqual(result["completedPlanCount"], 2)
        self.assertEqual(result["releaseId"], "release-1")


if __name__ == "__main__":
    unittest.main()
