from __future__ import annotations

import unittest
from contextlib import contextmanager

from core.errors import ApiError
from services.student_learning_service import StudentLearningService


class _StudentAuthStub:
    def authenticate(self, _access_token: str) -> dict:
        return {
            "principal": {
                "id": "student-1",
                "family_id": "family-1",
                "child_id": "child-1",
            },
            "student": {"childId": "child-1"},
        }


class _AuthAdapterStub:
    @contextmanager
    def bind(self, _context: dict):
        yield


class _LearningStub:
    def start_session(
        self,
        _access_token: str,
        data: dict,
        *,
        atomic_session_binder=None,
        **_kwargs,
    ) -> dict:
        payload = {
            "ok": True,
            "session": {"id": "session-1"},
            "taskId": data["taskId"],
        }
        if atomic_session_binder is not None:
            return atomic_session_binder(object(), payload)
        return payload


class _RuntimeStub:
    def __init__(self):
        self.attach_calls = 0
        self.runtime_calls = 0
        self.complete_calls = 0
        self.formal_runtime_bound = False

    def attach_classroom(self, **kwargs) -> dict:
        self.attach_calls += 1
        return {
            **kwargs["start_payload"],
            "classroom": {"id": "classroom-1"},
            "package": {"schemaVersion": "mira.lesson-package.v2"},
        }

    def attach_classroom_in_transaction(self, _conn, **kwargs) -> dict:
        return self.attach_classroom(**kwargs)

    def has_formal_runtime_binding_in_transaction(self, _conn, **_kwargs) -> bool:
        return self.formal_runtime_bound

    def runtime(self, **_kwargs) -> dict:
        self.runtime_calls += 1
        return {"classroom": {"id": "classroom-1"}}

    def complete_action(self, **_kwargs) -> dict:
        self.complete_calls += 1
        return {"ok": True, "status": "completed"}


class StudentClassroomReleaseGateTest(unittest.TestCase):
    def test_default_closed_gate_never_exposes_classroom_to_student(self):
        service, runtime = self._service(enabled=False)
        started = service.start_session("student-access", {"taskId": "task-1"})
        self.assertNotIn("classroom", started)
        self.assertEqual(runtime.attach_calls, 0)

        for operation in (
            lambda: service.classroom_runtime("student-access", "session-1"),
            lambda: service.complete_classroom_action(
                "student-access",
                "session-1",
                "action-1",
                {},
            ),
        ):
            with self.assertRaises(ApiError) as raised:
                operation()
            self.assertEqual(raised.exception.status_code, 404)
            self.assertEqual(raised.exception.code, "learning_classroom_not_available")
        self.assertEqual(runtime.runtime_calls, 0)
        self.assertEqual(runtime.complete_calls, 0)

    def test_explicit_open_gate_preserves_classroom_runtime_behavior(self):
        service, runtime = self._service(enabled=True)
        started = service.start_session("student-access", {"taskId": "task-1"})
        self.assertEqual(started["classroom"]["id"], "classroom-1")
        self.assertEqual(runtime.attach_calls, 1)
        self.assertEqual(
            service.classroom_runtime("student-access", "session-1")["classroom"]["id"],
            "classroom-1",
        )
        self.assertTrue(
            service.complete_classroom_action(
                "student-access",
                "session-1",
                "action-1",
                {},
            )["ok"]
        )
        self.assertEqual(runtime.runtime_calls, 1)
        self.assertEqual(runtime.complete_calls, 1)

    def test_open_gate_does_not_silently_fallback_without_a_published_package(self):
        service, runtime = self._service(enabled=True)
        runtime.attach_classroom_in_transaction = (
            lambda _conn, **kwargs: dict(kwargs["start_payload"])
        )

        with self.assertRaises(ApiError) as raised:
            service.start_session("student-access", {"taskId": "task-1"})

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.code, "learning_classroom_preparing")

    def test_formal_runtime_binding_continues_to_launch_without_legacy_package_fields(self):
        service, runtime = self._service(enabled=True)
        runtime.formal_runtime_bound = True
        runtime.attach_classroom_in_transaction = (
            lambda _conn, **kwargs: dict(kwargs["start_payload"])
        )

        started = service.start_session("student-access", {"taskId": "task-1"})

        self.assertEqual(started["session"]["id"], "session-1")
        self.assertNotIn("classroom", started)
        self.assertNotIn("package", started)
        self.assertNotIn("cursor", started)

    @staticmethod
    def _service(*, enabled: bool):
        service = object.__new__(StudentLearningService)
        runtime = _RuntimeStub()
        service.student_auth_service = _StudentAuthStub()
        service._auth_adapter = _AuthAdapterStub()
        service.learning_service = _LearningStub()
        service.lesson_runtime_service = runtime
        service.classroom_student_release_enabled = enabled
        service._assert_task_belongs_to_student = lambda **_kwargs: None
        return service, runtime


if __name__ == "__main__":
    unittest.main()
