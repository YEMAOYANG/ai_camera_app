from __future__ import annotations

import unittest
from unittest.mock import patch

from flask import Flask

from core.errors import ApiError
from routes.internal.openmaic_runtime import internal_openmaic_runtime_bp


class _Guard:
    def authorize(self, **kwargs):
        if kwargs["headers"].get("X-Mira-Internal-Token") != "internal-token":
            raise ApiError("invalid_internal_token", "内部调用未通过校验。", 401)
        return {
            "auditId": "audit-1",
            "sourceName": kwargs["headers"].get("X-Mira-Internal-Source", ""),
            "sourceIp": "127.0.0.1",
        }


class _EventService:
    def __init__(self):
        self.calls = []
        self.status_calls = []

    def record(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "ok": True,
            "schemaVersion": "mira.openmaic.student-runtime-event-receipt.v1",
            "sequence": kwargs["data"]["sequence"],
            "receiptSha256": "a" * 64,
        }

    def status(self, **kwargs):
        self.status_calls.append(kwargs)
        return {
            "ok": True,
            "schemaVersion": "mira.openmaic.student-runtime-event-receipt.v1",
            "lastSequence": 3,
            "nextSequence": 4,
            "completed": False,
            "reportId": None,
        }


class InternalOpenMaicRuntimeEventsApiTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(
            internal_openmaic_runtime_bp,
            url_prefix="/internal/learning/openmaic",
        )
        self.client = app.test_client()
        self.service = _EventService()
        self.guard_patch = patch(
            "routes.internal.openmaic_runtime.internal_request_guard",
            return_value=_Guard(),
        )
        self.service_patch = patch(
            "routes.internal.openmaic_runtime._runtime_event_service",
            return_value=self.service,
        )
        self.guard_patch.start()
        self.service_patch.start()
        self.addCleanup(self.guard_patch.stop)
        self.addCleanup(self.service_patch.stop)

    def test_gateway_source_and_trusted_session_headers_are_mandatory(self):
        body = {
            "schemaVersion": "mira.openmaic.student-runtime-event.v1",
            "sequence": 1,
            "type": "scene_entered",
            "payload": {"sceneIndex": 0, "sceneId": "scene-0"},
            "idempotencyKey": "b" * 64,
        }
        wrong_source = self.client.post(
            "/internal/learning/openmaic/runtime/events",
            json=body,
            headers={
                "X-Mira-Internal-Token": "internal-token",
                "X-Mira-Internal-Source": "student-web",
                "X-Mira-Runtime-Session": "runtime-session-1",
                "X-Mira-Learning-Session": "learning-session-1",
                "X-Mira-Runtime-Classroom-Id": "classroom-1",
            },
        )
        self.assertEqual(wrong_source.status_code, 403, wrong_source.json)
        self.assertEqual(self.service.calls, [])

        missing_binding = self.client.post(
            "/internal/learning/openmaic/runtime/events",
            json=body,
            headers={
                "X-Mira-Internal-Token": "internal-token",
                "X-Mira-Internal-Source": "openmaic-runtime-gateway",
            },
        )
        self.assertEqual(missing_binding.status_code, 400, missing_binding.json)
        self.assertEqual(self.service.calls, [])

        accepted = self.client.post(
            "/internal/learning/openmaic/runtime/events",
            json=body,
            headers={
                "X-Mira-Internal-Token": "internal-token",
                "X-Mira-Internal-Source": "openmaic-runtime-gateway",
                "X-Mira-Runtime-Session": "runtime-session-1",
                "X-Mira-Learning-Session": "learning-session-1",
                "X-Mira-Runtime-Classroom-Id": "classroom-1",
            },
        )
        self.assertEqual(accepted.status_code, 200, accepted.json)
        self.assertEqual(
            self.service.calls[0]["runtime_session_id"],
            "runtime-session-1",
        )
        self.assertEqual(
            self.service.calls[0]["learning_session_id"],
            "learning-session-1",
        )
        self.assertEqual(
            self.service.calls[0]["upstream_classroom_id"],
            "classroom-1",
        )

    def test_gateway_can_read_only_the_bound_stream_cursor_for_reload_resume(self):
        response = self.client.get(
            "/internal/learning/openmaic/runtime/events",
            headers={
                "X-Mira-Internal-Token": "internal-token",
                "X-Mira-Internal-Source": "openmaic-runtime-gateway",
                "X-Mira-Runtime-Session": "runtime-session-1",
                "X-Mira-Learning-Session": "learning-session-1",
                "X-Mira-Runtime-Classroom-Id": "classroom-1",
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["nextSequence"], 4)
        self.assertEqual(
            self.service.status_calls,
            [
                {
                    "runtime_session_id": "runtime-session-1",
                    "learning_session_id": "learning-session-1",
                    "upstream_classroom_id": "classroom-1",
                }
            ],
        )

    def test_gateway_headers_preserve_255_character_learning_and_classroom_ids(self):
        learning_session_id = "l" + "a" * 254
        classroom_id = "c" + "b" * 254
        response = self.client.get(
            "/internal/learning/openmaic/runtime/events",
            headers={
                "X-Mira-Internal-Token": "internal-token",
                "X-Mira-Internal-Source": "openmaic-runtime-gateway",
                "X-Mira-Runtime-Session": "runtime-session-1",
                "X-Mira-Learning-Session": learning_session_id,
                "X-Mira-Runtime-Classroom-Id": classroom_id,
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            self.service.status_calls[-1],
            {
                "runtime_session_id": "runtime-session-1",
                "learning_session_id": learning_session_id,
                "upstream_classroom_id": classroom_id,
            },
        )


if __name__ == "__main__":
    unittest.main()
