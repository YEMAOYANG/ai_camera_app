from __future__ import annotations

import unittest
from unittest.mock import patch

from flask import Flask

from routes.api.v1.learning import learning_bp
from routes.api.v2.parent_student_access import parent_student_access_bp


class _StudentAccessContractService:
    def list_authorizations(self, access_token: str, child_id: str) -> dict:
        return {
            "ok": True,
            "childId": child_id,
            "authorizations": [],
        }

    def revoke_authorization(
        self,
        access_token: str,
        child_id: str,
        device_id: str,
    ) -> dict:
        return {
            "ok": True,
            "childId": child_id,
            "authorizationId": device_id,
            "status": "revoked",
        }

    def reset_pin(self, access_token: str, child_id: str, data: dict) -> dict:
        return {
            "ok": True,
            "childId": child_id,
            "pinUpdatedAt": 1_777_000_000_000,
            "existingDevicesRemainTrusted": True,
        }


class _LearningReportContractService:
    def list_reports(self, access_token: str, query: dict) -> dict:
        return {
            "ok": True,
            "childId": query.get("childId"),
            "items": [],
            "nextCursor": None,
        }

    def report_detail(
        self,
        access_token: str,
        report_id: str,
        query: dict,
    ) -> dict:
        return {
            "ok": True,
            "childId": query.get("childId"),
            "report": {"id": report_id},
        }


class ParentStudentLinkageApiContractTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.register_blueprint(
            parent_student_access_bp,
            url_prefix="/api/v2/parent",
        )
        self.app.register_blueprint(learning_bp, url_prefix="/api/learning")
        self.client = self.app.test_client()
        self.headers = {"Authorization": "Bearer parent_test_token"}

    def test_parent_authorization_routes_are_wired_without_exposing_secrets(self):
        service = _StudentAccessContractService()
        with patch(
            "routes.api.v2.parent_student_access.student_auth_service",
            return_value=service,
        ):
            listed = self.client.get(
                "/api/v2/parent/children/child_1/student-access/authorizations",
                headers=self.headers,
            )
            revoked = self.client.delete(
                "/api/v2/parent/children/child_1/student-access/authorizations/device_1",
                headers=self.headers,
            )
            reset = self.client.post(
                "/api/v2/parent/children/child_1/student-access/pin/reset",
                json={"pin": "2468"},
                headers=self.headers,
            )

        self.assertEqual(listed.status_code, 200, listed.get_json())
        self.assertEqual(revoked.status_code, 200, revoked.get_json())
        self.assertEqual(reset.status_code, 200, reset.get_json())
        combined = {**listed.get_json(), **revoked.get_json(), **reset.get_json()}
        for forbidden in (
            "pin",
            "pinHash",
            "deviceTokenHash",
            "accessHash",
            "refreshHash",
            "refreshToken",
        ):
            self.assertNotIn(forbidden, combined)

    def test_parent_learning_report_list_and_detail_routes_are_wired(self):
        service = _LearningReportContractService()
        with patch(
            "routes.api.v1.learning.learning_service",
            return_value=service,
        ):
            listed = self.client.get(
                "/api/learning/reports",
                query_string={"childId": "child_1", "limit": 10},
                headers=self.headers,
            )
            detail = self.client.get(
                "/api/learning/reports/report_1",
                query_string={"childId": "child_1"},
                headers=self.headers,
            )

        self.assertEqual(listed.status_code, 200, listed.get_json())
        self.assertEqual(listed.get_json()["items"], [])
        self.assertEqual(detail.status_code, 200, detail.get_json())
        self.assertEqual(detail.get_json()["report"]["id"], "report_1")


if __name__ == "__main__":
    unittest.main()
