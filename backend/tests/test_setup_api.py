from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier, Lock
from unittest.mock import patch

from app import create_app
from core.database import Database
from repositories.setup_repository import SetupRepository
from tests.support import fresh_test_config, request_debug_code


PREPARATION_SCHEMA_HEADER = "X-Mira-Preparation-Schema"
PREPARATION_SCHEMA_V2 = "mira.learning.preparation.v2"
V1_PREPARATION_KEYS = {
    "schemaVersion",
    "id",
    "childId",
    "gradeCode",
    "gradeLabel",
    "subjects",
    "status",
    "stage",
    "progressPercent",
    "totalCourseCount",
    "readyCourseCount",
    "failedCourseCount",
    "attempt",
    "canRetry",
    "retryAfterMs",
    "message",
    "lastProgressAt",
    "updatedAt",
    "completedAt",
    "error",
}
V1_SUBJECT_KEYS = {
    "code",
    "label",
    "readyCourseCount",
    "failedCourseCount",
    "totalCourseCount",
}


class SetupApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
        self.client = self.app.test_client()

    def test_setup_status_initial_state(self):
        access_token = self._login()

        response = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["setup"]["completed"])
        self.assertEqual(response.json["setup"]["parentIdentity"], "pending")
        self.assertEqual(response.json["setup"]["deviceBinding"], "pending")
        self.assertEqual(response.json["setup"]["nextStep"], "parentIdentity")

    def test_lightweight_setup_steps_save_and_complete_persists(self):
        access_token = self._login()

        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "爸爸",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)
        self.assertEqual(parent.json["setup"]["parentIdentity"], "done")
        self.assertEqual(parent.json["parentIdentity"]["displayName"], "爸爸")
        self.assertEqual(parent.json["parentIdentity"]["relationshipKey"], "dad")
        self.assertEqual(parent.json["setup"]["nextStep"], "child")

        parent_status = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent_status.status_code, 200)
        self.assertEqual(parent_status.json["parentIdentity"]["displayName"], "爸爸")
        self.assertEqual(parent_status.json["parentIdentity"]["relationship"], "爸爸")
        self.assertEqual(parent_status.json["parentIdentity"]["relationshipKey"], "dad")
        summary = self.client.get(
            "/api/profile/summary",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["summary"]["role"], "admin")

        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "小宇",
                "nickname": "小宇",
                "gender": "unspecified",
                "ageStage": "幼儿园 中班",
                "educationStage": "幼儿园",
                "grade": "中班",
                "birthday": "2019-05-20",
                "sleepTime": "21:15",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200)
        self.assertTrue(child.json["setup"]["completed"])
        self.assertEqual(child.json["setup"]["childProfile"], "done")
        self.assertEqual(child.json["child"]["name"], "小宇")
        self.assertEqual(child.json["child"]["gender"], "unspecified")
        self.assertEqual(child.json["child"]["birthday"], "2019-05-20")
        self.assertEqual(child.json["child"]["sleepTime"], "21:15")
        self.assertEqual(child.json["child"]["gradeCode"], "kindergarten_middle")
        self.assertEqual(child.json["child"]["gradeLabel"], "中班")
        self.assertEqual(child.json["child"]["educationStageCode"], "kindergarten")
        self.assertEqual(child.json["child"]["contentMode"], "kindergarten_growth")
        self.assertEqual(
            child.json["child"]["schoolYearStartYear"],
            datetime.now().year,
        )
        self.assertIsInstance(child.json["child"]["gradeConfirmedAt"], int)
        self.assertFalse(child.json["child"]["gradeSelectionRequired"])
        self.assertEqual(child.json["setup"]["nextStep"], "home")

        complete = self.client.post(
            "/api/setup/complete",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(complete.status_code, 200)
        self.assertTrue(complete.json["setup"]["completed"])
        self.assertEqual(complete.json["setup"]["nextStep"], "home")

        status = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json["setup"]["completed"])
        self.assertEqual(status.json["setup"]["nextStep"], "home")
        self.assertEqual(status.json["child"]["sleepTime"], "21:15")
        self.assertIsNone(status.json["device"])
        self.assertIsNone(status.json["cameraName"])
        self.assertEqual(status.json["setup"]["deviceBinding"], "pending")
        self.assertEqual(status.json["setup"]["contacts"], "pending")

        contacts = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "妈妈", "phone": "13900002026", "relationship": "mother"},
                    {"name": "外婆", "phone": "13800002027", "relationship": "grandparent"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(contacts.status_code, 200)
        self.assertEqual(contacts.json["contacts"]["count"], 2)

    def test_grade_based_setup_requires_name_and_nickname_then_persists(self):
        access_token = self._login("13800002036")
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "爸爸",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)

        current_year = datetime.now().year
        grade_only = self.client.post(
            "/api/setup/child",
            json={
                "gradeCode": "primary_3",
                "schoolYearStartYear": current_year,
            },
            headers=self._auth_headers(access_token),
        )

        self.assertEqual(grade_only.status_code, 400, grade_only.json)
        self.assertEqual(grade_only.json["error"], "missing_name")

        missing_nickname = self.client.post(
            "/api/setup/child",
            json={
                "name": "乐乐",
                "gradeCode": "primary_3",
                "schoolYearStartYear": current_year,
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(missing_nickname.status_code, 400, missing_nickname.json)
        self.assertEqual(missing_nickname.json["error"], "missing_nickname")

        forbidden_factory_paths = (
            "services.service_factory.dynamic_learning_course_generation_service",
            "services.service_factory.openmaic_full_runtime_service",
            "services.service_factory.learning_media_materialization_service",
        )
        with patch(forbidden_factory_paths[0]) as dynamic_factory, patch(
            forbidden_factory_paths[1]
        ) as openmaic_factory, patch(
            forbidden_factory_paths[2]
        ) as media_factory:
            for factory in (dynamic_factory, openmaic_factory, media_factory):
                factory.side_effect = AssertionError(
                    "grade save must not construct generation dependencies"
                )
            saved = self.client.post(
                "/api/setup/child",
                json={
                    "name": "乐乐",
                    "nickname": "乐乐",
                    "gradeCode": "primary_1",
                    "schoolYearStartYear": current_year,
                },
                headers={
                    **self._auth_headers(access_token),
                    PREPARATION_SCHEMA_HEADER: PREPARATION_SCHEMA_V2,
                },
            )
            for factory in (dynamic_factory, openmaic_factory, media_factory):
                factory.assert_not_called()

        self.assertEqual(saved.status_code, 200, saved.json)
        child = saved.json["child"]
        self.assertEqual(child["name"], "乐乐")
        self.assertEqual(child["nickname"], "乐乐")
        self.assertEqual(child["gender"], "unspecified")
        self.assertEqual(child["birthday"], "")
        self.assertEqual(child["grade"], "一年级")
        self.assertEqual(child["gradeCode"], "primary_1")
        self.assertEqual(child["gradeLabel"], "一年级")
        self.assertEqual(child["educationStage"], "小学")
        self.assertEqual(child["educationStageCode"], "primary")
        self.assertEqual(child["educationStageLabel"], "小学")
        self.assertEqual(child["contentMode"], "primary_learning")
        self.assertEqual(child["schoolYearStartYear"], current_year)
        self.assertIsInstance(child["gradeConfirmedAt"], int)
        self.assertFalse(child["gradeSelectionRequired"])
        preparation = saved.json["learningPreparation"]
        self.assertEqual(set(preparation), V1_PREPARATION_KEYS)
        self.assertEqual(
            preparation["schemaVersion"],
            "mira.learning.preparation.v1",
        )
        self.assertNotIn("contentProgress", preparation)
        for subject in preparation["subjects"]:
            self.assertEqual(set(subject), V1_SUBJECT_KEYS)
        self.assertEqual(preparation["status"], "queued")
        self.assertEqual(preparation["totalCourseCount"], 30)
        self.assertEqual(preparation["gradeLabel"], "一年级")
        self.assertEqual(
            saved.json["learningPreparationAvailability"],
            {
                "status": "preparing",
                "gradeCode": "primary_1",
                "message": "已开始准备",
            },
        )
        self.assertEqual(
            [item["label"] for item in preparation["subjects"]],
            ["语文", "数学", "英语"],
        )

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            persisted = conn.execute(
                "SELECT * FROM children WHERE id = ?",
                (child["id"],),
            ).fetchone()
            self.assertEqual(persisted["grade_selection_revision"], 1)
            self.assertEqual(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM learning_curriculum_preparation_plans
                    WHERE child_id = ?
                    """,
                    (child["id"],),
                ).fetchone()["count"],
                1,
            )

        for _ in range(5):
            repeated = self.client.post(
                "/api/setup/child",
                json={
                    "name": "乐乐",
                    "nickname": "乐乐",
                    "gradeCode": "primary_1",
                    "schoolYearStartYear": current_year,
                },
                headers=self._auth_headers(access_token),
            )
            self.assertEqual(repeated.status_code, 200, repeated.json)
            self.assertEqual(
                repeated.json["learningPreparation"]["id"],
                preparation["id"],
            )

        changed = self.client.post(
            "/api/setup/child",
            json={
                "name": "乐乐",
                "nickname": "乐乐",
                "gradeCode": "primary_2",
                "schoolYearStartYear": current_year,
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(changed.status_code, 200, changed.json)
        self.assertNotIn("learningPreparation", changed.json)
        self.assertEqual(
            changed.json["learningPreparationAvailability"],
            {
                "status": "unavailable",
                "gradeCode": "primary_2",
                "message": "该年级正式课程尚未开放",
            },
        )

        returned = self.client.post(
            "/api/setup/child",
            json={
                "name": "乐乐",
                "nickname": "乐乐",
                "gradeCode": "primary_1",
                "schoolYearStartYear": current_year,
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(returned.status_code, 200, returned.json)
        self.assertNotEqual(returned.json["learningPreparation"]["id"], preparation["id"])

        with database.transaction() as conn:
            persisted = conn.execute(
                "SELECT * FROM children WHERE id = ?",
                (child["id"],),
            ).fetchone()
            self.assertEqual(persisted["grade_selection_revision"], 3)
            plans = conn.execute(
                """
                SELECT grade_code, grade_selection_revision, status
                FROM learning_curriculum_preparation_plans
                WHERE child_id = ?
                ORDER BY grade_selection_revision
                """,
                (child["id"],),
            ).fetchall()
        self.assertEqual(
            [
                (row["grade_code"], row["grade_selection_revision"], row["status"])
                for row in plans
            ],
            [
                ("primary_1", 1, "superseded"),
                ("primary_1", 3, "queued"),
            ],
        )

        status = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["child"]["gradeCode"], "primary_1")
        self.assertEqual(status.json["child"]["contentMode"], "primary_learning")
        self.assertEqual(status.json["child"]["schoolYearStartYear"], current_year)

    def test_nickname_only_setup_save_does_not_reserve_or_increment_revision(self):
        access_token = self._login("13800002038")
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)
        created = self.client.post(
            "/api/setup/child",
            json={"name": "星星", "nickname": "星星", "ageStage": "primary"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(created.status_code, 200, created.json)
        self.assertNotIn("learningPreparation", created.json)

        renamed = self.client.post(
            "/api/setup/child",
            json={"nickname": "小星"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(renamed.status_code, 200, renamed.json)
        self.assertNotIn("learningPreparation", renamed.json)

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            child = conn.execute(
                "SELECT * FROM children WHERE id = ?",
                (created.json["child"]["id"],),
            ).fetchone()
            plan_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_curriculum_preparation_plans
                WHERE child_id = ?
                """,
                (child["id"],),
            ).fetchone()["count"]
        self.assertEqual(child["grade_selection_revision"], 0)
        self.assertEqual(plan_count, 0)

    def test_concurrent_first_setup_grade_saves_create_one_child_and_one_plan(self):
        access_token = self._login("13800002039")
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)
        barrier = Barrier(3)
        connection_ids: list[int] = []
        connection_ids_lock = Lock()
        original_lock_family = SetupRepository.lock_family

        def record_lock_connection(repository, conn, *, family_id: str):
            connection_id = conn.execute(
                "SELECT CONNECTION_ID() AS id"
            ).fetchone()["id"]
            with connection_ids_lock:
                connection_ids.append(connection_id)
            return original_lock_family(repository, conn, family_id=family_id)

        def save_from_independent_client():
            client = self.app.test_client()
            barrier.wait(timeout=5)
            return client.post(
                "/api/setup/child",
                json={
                    "name": "并发宝贝",
                    "nickname": "并发宝贝",
                    "gradeCode": "primary_1",
                    "schoolYearStartYear": datetime.now().year,
                },
                headers=self._auth_headers(access_token),
            )

        with patch.object(SetupRepository, "lock_family", record_lock_connection):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(save_from_independent_client) for _ in range(2)
                ]
                barrier.wait(timeout=5)
                responses = [future.result(timeout=15) for future in futures]
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(len(connection_ids), 2)
        self.assertEqual(len(set(connection_ids)), 2)

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            children = conn.execute(
                "SELECT * FROM children WHERE family_id = ?",
                (self.family_id,),
            ).fetchall()
            plans = conn.execute(
                """
                SELECT * FROM learning_curriculum_preparation_plans
                WHERE family_id = ?
                """,
                (self.family_id,),
            ).fetchall()
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]["grade_selection_revision"], 1)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["status"], "queued")

    def test_grade_only_setup_rejects_invalid_missing_year_and_stage_conflict(self):
        access_token = self._login("13800002037")
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)

        current_year = datetime.now().year
        invalid = self.client.post(
            "/api/setup/child",
            json={
                "gradeCode": "primary_7",
                "schoolYearStartYear": current_year,
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json["error"], "invalid_grade_code")

        missing_year = self.client.post(
            "/api/setup/child",
            json={"gradeCode": "primary_3"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(missing_year.status_code, 400)
        self.assertEqual(
            missing_year.json["error"],
            "missing_school_year_start_year",
        )

        conflict = self.client.post(
            "/api/setup/child",
            json={
                "gradeCode": "primary_3",
                "schoolYearStartYear": current_year,
                "educationStage": "幼儿园",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(conflict.status_code, 400)
        self.assertEqual(conflict.json["error"], "grade_stage_conflict")

    def test_parent_identity_can_save_family_role(self):
        access_token = self._login("13800002029")

        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
                "role": "guardian",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)
        self.assertEqual(parent.json["parentIdentity"]["role"], "guardian")
        self.assertEqual(parent.json["parentIdentity"]["roleLabel"], "监护人")

        status = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["parentIdentity"]["role"], "guardian")

        summary = self.client.get(
            "/api/profile/summary",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["summary"]["role"], "guardian")

    def test_setup_device_endpoint_remains_available_after_setup(self):
        access_token = self._login("13800002027")
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)
        child = self.client.post(
            "/api/setup/child",
            json={"name": "小星", "nickname": "小星", "ageStage": "幼儿园 小班"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200)
        self.assertTrue(child.json["setup"]["completed"])

        device = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-2027", "location": "儿童房"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(device.status_code, 200, device.json)
        self.assertEqual(device.json["device"]["status"], "bound")
        self.assertEqual(device.json["device"]["name"], "儿童房暖瞳摄像头")
        self.assertEqual(device.json["setup"]["nextStep"], "home")

        fallback = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-2027-NO-ROOM"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(fallback.status_code, 409)

        other_token = self._login("13800002028")
        other_parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "爸爸",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(other_token),
        )
        self.assertEqual(other_parent.status_code, 200)
        default_name = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-2028"},
            headers=self._auth_headers(other_token),
        )
        self.assertEqual(default_name.status_code, 200, default_name.json)
        self.assertEqual(default_name.json["device"]["name"], "暖瞳摄像头")

    def test_setup_contacts_allow_parent_identity_and_reject_contact_duplicates(self):
        access_token = self._login("13800003026")

        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "爸爸",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)

        early_contacts = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "妈妈", "phone": "13900003025", "relationship": "mother"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(early_contacts.status_code, 409)
        self.assertEqual(early_contacts.json["error"], "setup_step_out_of_order")

        self._complete_setup_before_contacts(access_token)

        contacts = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "妈妈", "phone": "13900003026", "relationship": "mother"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(contacts.status_code, 200)

        duplicate_contacts = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "外婆", "phone": "13900003027", "relationshipKey": "maternal_grandma"},
                    {"name": "外婆", "phone": "13900003028", "relationship": "外婆"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(duplicate_contacts.status_code, 400)
        self.assertEqual(duplicate_contacts.json["error"], "duplicate_guardian_identity")

    def test_setup_complete_requires_all_steps(self):
        access_token = self._login()

        complete = self.client.post(
            "/api/setup/complete",
            headers=self._auth_headers(access_token),
        )

        self.assertEqual(complete.status_code, 400)
        self.assertEqual(complete.json["error"], "setup_incomplete")

    def test_camera_name_updates_default_device_in_multi_device_family(self):
        access_token = self._login("13800003029")
        headers = self._auth_headers(access_token)
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"},
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200)
        first = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-CAMERA-NAME-1", "deviceName": "客厅设备", "location": "客厅"},
            headers=headers,
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/api/devices",
            json={
                "bindingCode": "BIND-CAMERA-NAME-2",
                "name": "儿童房设备",
                "location": "儿童房",
                "setAsDefault": True,
            },
            headers=headers,
        )
        self.assertEqual(second.status_code, 200, second.json)
        second_id = second.json["device"]["id"]
        wifi = self.client.post(
            "/api/setup/wifi",
            json={"ssid": "Home-5G", "password": "not-stored", "authType": "wpa2"},
            headers=headers,
        )
        self.assertEqual(wifi.status_code, 200)
        child = self.client.post(
            "/api/setup/child",
            json={"name": "小宇", "nickname": "小宇", "ageStage": "kindergarten_middle"},
            headers=headers,
        )
        self.assertEqual(child.status_code, 200)

        camera_name = self.client.post(
            "/api/setup/camera-name",
            json={"wakeName": "小守"},
            headers=headers,
        )
        self.assertEqual(camera_name.status_code, 200, camera_name.json)
        self.assertEqual(camera_name.json["cameraName"]["deviceId"], second_id)

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            rows = conn.execute(
                "SELECT id, wake_name FROM devices WHERE family_id = ? ORDER BY created_at",
                (self.family_id,),
            ).fetchall()
        wake_names = {row["id"]: row.get("wake_name") for row in rows}
        self.assertEqual(wake_names[first.json["device"]["id"]], "小暖")
        self.assertEqual(wake_names[second_id], "小守")

    def _login(self, phone: str = "13800002026") -> str:
        code = request_debug_code(self.client, phone)
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(login.status_code, 200)
        self.family_id = login.json["family"]["id"]
        return login.json["tokens"]["accessToken"]

    def _complete_setup_before_contacts(self, access_token: str) -> None:
        child = self.client.post(
            "/api/setup/child",
            json={"name": "小宇", "nickname": "小宇", "ageStage": "kindergarten_middle"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200)

    def _auth_headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}


if __name__ == "__main__":
    unittest.main()
