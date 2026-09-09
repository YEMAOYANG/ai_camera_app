from __future__ import annotations

import unittest
from contextlib import contextmanager

from core.errors import ApiError
from services.learning_catalog_release_service import LearningCatalogReleaseService


def _item(**overrides):
    row = {
        "id": "catalog_item_unit",
        "grade_code": "primary_1",
        "subject": "math",
        "skill_id": "number_sense_20",
        "curriculum_version": "primary_core_v1",
        "boundary_version": "primary_1_math_number_sense_20_v1",
        "variant_ordinal": 1,
        "status": "processing",
        "attempt_count": 1,
        "package_attempt_count": 0,
        "generation_request_id": "catalog_gen_unit",
        "active_generation_request_id": "catalog_gen_unit",
        "active_package_request_id": None,
        "course_id": None,
        "course_version": None,
        "package_id": None,
        "package_version": None,
        "error_code": None,
        "error_message_safe": None,
        "updated_at": 1234,
    }
    row.update(overrides)
    return row


class _RepositoryRecorder:
    def __init__(self, *, current=None, package_claim=None):
        self.current = current
        self.package_claim = package_claim
        self.calls = []

    @contextmanager
    def transaction(self):
        yield object()

    def mark_item_failed(self, _conn, **kwargs):
        self.calls.append(("mark_item_failed", kwargs))
        return _item(
            status="failed",
            error_code=kwargs["error_code"],
            error_message_safe=kwargs["error_message"],
        )

    def mark_item_external_failed(self, _conn, **kwargs):
        self.calls.append(("mark_item_external_failed", kwargs))
        return _item(
            status="external_failed",
            error_code=kwargs["error_code"],
            error_message_safe=kwargs["error_message"],
        )

    def mark_content_gate_deferred(self, _conn, **kwargs):
        self.calls.append(("mark_content_gate_deferred", kwargs))
        return _item(
            course_id=kwargs["expected_course_id"],
            course_version=kwargs["expected_course_version"],
            status="course_ready",
            error_code=kwargs["error_code"],
            error_message_safe=kwargs["error_message"],
        )

    def claim_package_for_item(self, _conn, **kwargs):
        self.calls.append(("claim_package_for_item", kwargs))
        return self.package_claim

    def get_item(self, _conn, *, item_id):
        self.calls.append(("get_item", {"item_id": item_id}))
        return self.current


class _FailingDynamicService:
    def generate_for_skill(self, **_kwargs):
        raise RuntimeError("model unavailable")


class _RecordingDynamicFailureService:
    def __init__(
        self,
        *,
        error: str = "still_invalid",
        message: str = "still invalid",
    ):
        self.feedback = []
        self.retry_transient = []
        self.error = error
        self.message = message

    def generate_for_skill(self, **kwargs):
        self.feedback.append(kwargs.get("generation_feedback"))
        self.retry_transient.append(kwargs.get("retry_transient_failed"))
        return type(
            "Result",
            (),
            {
                "payload": {
                    "ok": False,
                    "error": self.error,
                    "message": self.message,
                }
            },
        )()


class _UnexpectedLessonService:
    def generate(self, _data):
        raise AssertionError("lesson package generation must not be called")


class _ContentOnlyRepositoryRecorder:
    def __init__(self):
        self.calls = []

    @contextmanager
    def transaction(self):
        yield object()

    def lock_build_authority(self, _conn, *, build_id):
        self.calls.append(
            ("lock_build_authority", {"build_id": build_id})
        )
        return (
            {"id": "catalog_release_content_only"},
            {
                "id": build_id,
                "status": "queued",
                "execution_mode": "content_only",
                "stage_ceiling": "content_ready",
            },
        )

    def list_build_items(self, _conn, *, build_id, for_update=False):
        self.calls.append(
            (
                "list_build_items",
                {"build_id": build_id, "for_update": for_update},
            )
        )
        return []

    def claim_next_item(self, _conn, **_kwargs):
        raise AssertionError("legacy claim must not run for content-only build")


class _NoDatabaseRepository:
    @contextmanager
    def transaction(self):
        raise AssertionError("public content-mode injection reached the database")
        yield object()


class LearningCatalogReleaseStateMachineUnitTest(unittest.TestCase):
    def _service(self, *, dynamic=None, lesson=None):
        return LearningCatalogReleaseService(
            "mysql://unused@127.0.0.1/unused",
            dynamic_generation_service=dynamic or _FailingDynamicService(),
            lesson_package_service=lesson or _UnexpectedLessonService(),
        )

    def test_course_failure_uses_the_exact_generation_request_cas(self):
        repository = _RepositoryRecorder()
        service = self._service()
        service.repository = repository

        result = service._process_item(_item())

        self.assertEqual(result["status"], "failed")
        call, kwargs = repository.calls[-1]
        self.assertEqual(call, "mark_item_failed")
        self.assertEqual(
            kwargs["expected_generation_request_id"], "catalog_gen_unit"
        )

    def test_prior_generation_feedback_is_explicit_opt_in(self):
        item = _item(
            prior_error_code="invalid_generated_course",
            prior_error_message_safe="q4 缺少比较证据",
        )
        for enabled, expected in (
            (False, None),
            (
                True,
                {
                    "code": "invalid_generated_course",
                    "message": "q4 缺少比较证据",
                },
            ),
        ):
            dynamic = _RecordingDynamicFailureService()
            repository = _RepositoryRecorder()
            service = self._service(dynamic=dynamic)
            service.repository = repository

            result = service._process_item(
                item,
                use_generation_feedback=enabled,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(dynamic.feedback, [expected])
            self.assertEqual(dynamic.retry_transient, [False])

    def test_quota_failure_is_recoverable_and_reuses_the_external_claim(self):
        dynamic = _RecordingDynamicFailureService(
            error="generation_failed",
            message="Moonshot returned HTTP 429: token quota exceeded",
        )
        repository = _RepositoryRecorder()
        service = self._service(dynamic=dynamic)
        service.repository = repository

        result = service._process_item(
            _item(claimed_from_status="external_failed", attempt_count=2)
        )

        self.assertEqual(result["status"], "external_failed")
        self.assertEqual(dynamic.retry_transient, [True])
        call, kwargs = repository.calls[-1]
        self.assertEqual(call, "mark_item_external_failed")
        self.assertEqual(
            kwargs["expected_generation_request_id"], "catalog_gen_unit"
        )

    def test_content_gate_defer_uses_course_and_lease_cas(self):
        repository = _RepositoryRecorder()
        service = self._service()
        service.repository = repository
        service._validate_course_for_package = lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("course store temporarily unavailable")
        )

        result = service._process_item(
            _item(
                course_id="course_unit",
                course_version="1.0.0",
                updated_at=5678,
            )
        )

        self.assertEqual(result["status"], "course_ready")
        call, kwargs = repository.calls[-1]
        self.assertEqual(call, "mark_content_gate_deferred")
        self.assertEqual(kwargs["expected_course_id"], "course_unit")
        self.assertEqual(kwargs["expected_course_version"], "1.0.0")
        self.assertEqual(
            kwargs["expected_generation_request_id"], "catalog_gen_unit"
        )
        self.assertEqual(kwargs["expected_updated_at"], 5678)

    def test_lost_package_claim_is_an_observer_noop(self):
        current = _item(
            course_id="course_unit",
            course_version="1.0.0",
            active_package_request_id="catalog_pkg_other_worker",
            package_attempt_count=1,
        )
        repository = _RepositoryRecorder(current=current, package_claim=None)
        service = self._service()
        service.repository = repository
        service._validate_course_for_package = lambda **_kwargs: None

        result = service._process_item(
            _item(course_id="course_unit", course_version="1.0.0")
        )

        self.assertEqual(result["status"], "processing")
        self.assertEqual(
            result["packageAttemptCount"],
            1,
        )
        self.assertEqual(
            [name for name, _kwargs in repository.calls],
            ["claim_package_for_item", "get_item"],
        )

    def test_legacy_run_locks_release_build_items_then_rejects_content_only(self):
        repository = _ContentOnlyRepositoryRecorder()
        service = self._service()
        service.repository = repository

        with self.assertRaises(ApiError) as raised:
            service.run("catalog_build_content_only", {"maxItems": 1})

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            repository.calls,
            [
                (
                    "lock_build_authority",
                    {"build_id": "catalog_build_content_only"},
                ),
                (
                    "list_build_items",
                    {
                        "build_id": "catalog_build_content_only",
                        "for_update": True,
                    },
                ),
            ],
        )

    def test_public_create_rejects_every_content_mode_injection_before_database(self):
        service = self._service()
        service.repository = _NoDatabaseRepository()
        for key, value in (
            ("executionMode", "content_only"),
            ("stageCeiling", "content_ready"),
            ("contentManifestVersion", "mira.learning.preparation-target.v2"),
            ("canaryManifest", {"targets": []}),
            ("preparationTarget", {"schemaVersion": "injected"}),
        ):
            with self.subTest(key=key):
                with self.assertRaises(ApiError) as raised:
                    service.create({"requestId": f"public-injection-{key}", key: value})
                self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
