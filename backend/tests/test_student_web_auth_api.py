from __future__ import annotations

import unittest
from datetime import datetime

from app import create_app
from core.config import ConfigError, validate_flask_config
from core.database import Database
from core.security import now_ms
from repositories.profile_repository import ProfileRepository
from services.formal_student_learning_access import assert_formal_student_grade_open
from tests.support import fresh_test_config, request_debug_code


class StudentWebAuthApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
        self.app.extensions["mira_formal_learning_access_checker"] = (
            lambda conn, child: assert_formal_student_grade_open(child)
        )
        self.client = self.app.test_client()
        self.parent_access_token = self._login_parent("13800002901")
        self.child_id = self._create_primary_child()

    def test_parent_pairs_student_and_auth_namespaces_are_isolated(self):
        created = self._create_pairing_code("2468")
        self.assertEqual(created.status_code, 200, created.json)
        pairing_code = created.json["pairingCode"]
        self.assertRegex(pairing_code, r"^[A-HJ-NP-Z2-9]{8}$")
        self.assertNotIn("pin", created.json)

        paired = self._pair(pairing_code)
        self.assertEqual(paired.status_code, 200, paired.json)
        self.assertEqual(paired.json["student"]["childId"], self.child_id)
        self.assertEqual(paired.json["student"]["displayName"], "乐乐")
        self.assertEqual(paired.json["student"]["gradeCode"], "primary_1")
        self.assertEqual(paired.json["device"]["label"], "客厅学习平板")
        self.assertTrue(paired.json["deviceToken"].startswith("msd_"))
        self.assertTrue(paired.json["tokens"]["accessToken"].startswith("msa_"))
        self.assertTrue(paired.json["tokens"]["refreshToken"].startswith("msr_"))

        student_access = paired.json["tokens"]["accessToken"]
        me = self.client.get(
            "/api/v2/student/me",
            headers=self._student_headers(student_access),
        )
        self.assertEqual(me.status_code, 200, me.json)
        self.assertEqual(me.json["device"]["id"], paired.json["device"]["id"])

        reused = self._pair(pairing_code)
        self.assertEqual(reused.status_code, 401, reused.json)
        self.assertEqual(reused.json["error"], "invalid_pairing_code")

        parent_in_student_namespace = self.client.get(
            "/api/v2/student/me",
            headers=self._student_headers(self.parent_access_token),
        )
        self.assertEqual(parent_in_student_namespace.status_code, 401)

        student_in_parent_namespace = self.client.get(
            "/api/profile/summary",
            headers=self._student_headers(student_access),
        )
        self.assertEqual(student_in_parent_namespace.status_code, 401)

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            pairing_row = conn.execute(
                "SELECT * FROM student_pairing_codes WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()
            principal = conn.execute(
                "SELECT * FROM student_principals WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()
            device = conn.execute(
                "SELECT * FROM student_trusted_devices WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()
            session = conn.execute(
                "SELECT * FROM student_sessions WHERE device_id = ?",
                (device["id"],),
            ).fetchone()
        self.assertNotEqual(pairing_row["code_hash"], pairing_code)
        self.assertNotEqual(pairing_row["pin_hash"], "2468")
        self.assertNotEqual(principal["pin_hash"], "2468")
        self.assertNotEqual(device["device_token_hash"], paired.json["deviceToken"])
        self.assertNotEqual(session["access_hash"], student_access)
        self.assertNotEqual(
            session["refresh_hash"],
            paired.json["tokens"]["refreshToken"],
        )

    def test_trusted_device_unlock_refresh_rotation_and_logout(self):
        paired = self._pair(self._create_pairing_code("1357").json["pairingCode"])
        tokens = paired.json["tokens"]
        device_token = paired.json["deviceToken"]

        logged_out = self.client.post(
            "/api/v2/student/auth/logout",
            json={"refreshToken": tokens["refreshToken"]},
            headers=self._student_headers(tokens["accessToken"]),
        )
        self.assertEqual(logged_out.status_code, 200, logged_out.json)

        stale = self.client.get(
            "/api/v2/student/me",
            headers=self._student_headers(tokens["accessToken"]),
        )
        self.assertEqual(stale.status_code, 401)

        wrong = self.client.post(
            "/api/v2/student/auth/unlock",
            json={"deviceToken": device_token, "pin": "0000"},
        )
        self.assertEqual(wrong.status_code, 401, wrong.json)
        self.assertEqual(wrong.json["error"], "invalid_student_pin")

        unlocked = self.client.post(
            "/api/v2/student/auth/unlock",
            json={"deviceToken": device_token, "pin": "1357"},
        )
        self.assertEqual(unlocked.status_code, 200, unlocked.json)
        self.assertNotIn("deviceToken", unlocked.json)
        unlocked_tokens = unlocked.json["tokens"]

        refreshed = self.client.post(
            "/api/v2/student/auth/refresh",
            json={"refreshToken": unlocked_tokens["refreshToken"]},
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.json)
        self.assertNotEqual(
            refreshed.json["tokens"]["refreshToken"],
            unlocked_tokens["refreshToken"],
        )

        reused_refresh = self.client.post(
            "/api/v2/student/auth/refresh",
            json={"refreshToken": unlocked_tokens["refreshToken"]},
        )
        self.assertEqual(reused_refresh.status_code, 401, reused_refresh.json)
        self.assertEqual(reused_refresh.json["error"], "student_refresh_expired")

        current = self.client.get(
            "/api/v2/student/me",
            headers=self._student_headers(refreshed.json["tokens"]["accessToken"]),
        )
        self.assertEqual(current.status_code, 200, current.json)

    def test_five_wrong_pin_attempts_lock_trusted_device(self):
        paired = self._pair(self._create_pairing_code("8642").json["pairingCode"])
        device_token = paired.json["deviceToken"]

        for attempt in range(1, 6):
            response = self.client.post(
                "/api/v2/student/auth/unlock",
                json={"deviceToken": device_token, "pin": "0000"},
            )
            expected_status = 429 if attempt == 5 else 401
            self.assertEqual(response.status_code, expected_status, response.json)

        locked_correct_pin = self.client.post(
            "/api/v2/student/auth/unlock",
            json={"deviceToken": device_token, "pin": "8642"},
        )
        self.assertEqual(locked_correct_pin.status_code, 429, locked_correct_pin.json)
        self.assertEqual(locked_correct_pin.json["error"], "student_pin_locked")

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            device = conn.execute(
                "SELECT * FROM student_trusted_devices WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()
        self.assertEqual(device["failed_pin_attempts"], 5)
        self.assertIsNotNone(device["locked_until"])

    def test_pairing_requires_parent_auth_and_four_digit_pin(self):
        missing_parent = self.client.post(
            f"/api/v2/parent/children/{self.child_id}/student-access/pairing-codes",
            json={"pin": "1234"},
        )
        self.assertEqual(missing_parent.status_code, 401)

        bad_pin = self._create_pairing_code("12345")
        self.assertEqual(bad_pin.status_code, 400, bad_pin.json)
        self.assertEqual(bad_pin.json["error"], "invalid_student_pin_format")

    def test_pairing_code_creation_rejects_non_primary_child(self):
        kindergarten_id = self._insert_child("安安", "kindergarten_big")

        response = self.client.post(
            f"/api/v2/parent/children/{kindergarten_id}/student-access/pairing-codes",
            json={"pin": "2468"},
            headers=self._parent_headers(),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_primary_only")

    def test_pairing_code_creation_checks_primary_grade_before_pin_format(self):
        kindergarten_id = self._insert_child("安安", "kindergarten_big")

        response = self.client.post(
            f"/api/v2/parent/children/{kindergarten_id}/student-access/pairing-codes",
            json={"pin": "12345"},
            headers=self._parent_headers(),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_primary_only")

    def test_pairing_code_creation_rejects_unopened_primary_grade(self):
        primary_two_id = self._insert_child("安安", "primary_2")

        response = self.client.post(
            f"/api/v2/parent/children/{primary_two_id}/student-access/pairing-codes",
            json={"pin": "2468"},
            headers=self._parent_headers(),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_grade_not_open")
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM student_pairing_codes WHERE child_id = ?",
                (primary_two_id,),
            ).fetchone()["count"]
        self.assertEqual(int(count), 0)

    def test_pairing_code_creation_allows_saved_grade_while_catalog_builds(self):
        self.app.extensions.pop("mira_formal_learning_access_checker", None)

        response = self._create_pairing_code("2468")

        self.assertEqual(response.status_code, 200, response.json)
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM student_pairing_codes WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()["count"]
        self.assertEqual(int(count), 1)

    def test_pairing_code_redemption_rejects_non_primary_child(self):
        kindergarten_id = self._insert_child("安安", "kindergarten_big")
        created = self._create_pairing_code("2468")
        self.assertEqual(created.status_code, 200, created.json)
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                "UPDATE student_pairing_codes SET child_id = ? WHERE child_id = ?",
                (kindergarten_id, self.child_id),
            )

        response = self._pair(created.json["pairingCode"])

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_primary_only")

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            pairing = conn.execute(
                """
                SELECT consumed_at FROM student_pairing_codes
                WHERE child_id = ?
                """,
                (kindergarten_id,),
            ).fetchone()
            principal_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM student_principals
                WHERE child_id = ?
                """,
                (kindergarten_id,),
            ).fetchone()["count"]
            device_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM student_trusted_devices
                WHERE child_id = ?
                """,
                (kindergarten_id,),
            ).fetchone()["count"]
            session_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM student_sessions AS sessions
                JOIN student_trusted_devices AS devices
                  ON devices.id = sessions.device_id
                WHERE devices.child_id = ?
                """,
                (kindergarten_id,),
            ).fetchone()["count"]
        self.assertIsNotNone(pairing)
        self.assertIsNone(pairing["consumed_at"])
        self.assertEqual(int(principal_count), 0)
        self.assertEqual(int(device_count), 0)
        self.assertEqual(int(session_count), 0)

    def test_existing_student_session_is_denied_after_grade_leaves_formal_scope(self):
        paired = self._pair(self._create_pairing_code("2468").json["pairingCode"])
        self.assertEqual(paired.status_code, 200, paired.json)
        access_token = paired.json["tokens"]["accessToken"]
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                """
                UPDATE children
                SET grade_code = 'primary_2', grade = '二年级',
                  education_stage = '小学', age_stage = '小学 二年级'
                WHERE id = ?
                """,
                (self.child_id,),
            )

        response = self.client.get(
            "/api/v2/student/me",
            headers=self._student_headers(access_token),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_grade_not_open")

    def test_orphan_family_cleanup_removes_student_identity_and_sessions(self):
        paired = self._pair(self._create_pairing_code("2468").json["pairingCode"])
        self.assertEqual(paired.status_code, 200, paired.json)

        database = Database(self.app.config["DATABASE_URL"])
        repository = ProfileRepository(database)
        with repository.transaction() as conn:
            principal = conn.execute(
                "SELECT * FROM student_principals WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()
            family_id = principal["family_id"]
            conn.execute("DELETE FROM users WHERE family_id = ?", (family_id,))
            repository.cleanup_orphan_family(conn, family_id=family_id)

            for table in (
                "student_sessions",
                "student_trusted_devices",
                "student_pairing_codes",
                "student_principals",
            ):
                count = conn.execute(
                    f"SELECT COUNT(*) AS count FROM {table}",
                ).fetchone()
                self.assertEqual(int(count["count"]), 0, table)
            family = conn.execute(
                "SELECT id FROM families WHERE id = ?",
                (family_id,),
            ).fetchone()
            self.assertIsNone(family)

    def _login_parent(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        response = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["tokens"]["accessToken"]

    def _create_primary_child(self) -> str:
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
            },
            headers=self._parent_headers(),
        )
        self.assertEqual(parent.status_code, 200, parent.json)
        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "乐乐",
                "nickname": "乐乐",
                "gradeCode": "primary_1",
                "schoolYearStartYear": datetime.now().year,
            },
            headers=self._parent_headers(),
        )
        self.assertEqual(child.status_code, 200, child.json)
        return child.json["child"]["id"]

    def _insert_child(self, name: str, grade_code: str) -> str:
        child_id = f"child-{grade_code}"
        now = now_ms()
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            family = conn.execute(
                "SELECT family_id FROM children WHERE id = ?",
                (self.child_id,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO children(
                  id, family_id, name, nickname, grade, grade_code,
                  education_stage, age_stage, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    child_id,
                    family["family_id"],
                    name,
                    name,
                    "大班",
                    grade_code,
                    "幼儿园",
                    "幼儿园 大班",
                    now,
                    now,
                ),
            )
        return child_id

    def _create_pairing_code(self, pin: str):
        return self.client.post(
            f"/api/v2/parent/children/{self.child_id}/student-access/pairing-codes",
            json={"pin": pin},
            headers=self._parent_headers(),
        )

    def _pair(self, pairing_code: str):
        return self.client.post(
            "/api/v2/student/auth/pair",
            json={
                "pairingCode": pairing_code,
                "clientDevice": {
                    "label": "客厅学习平板",
                    "type": "tablet",
                    "platform": "android",
                    "model": "Mira Test Tablet",
                    "osVersion": "14",
                    "appVersion": "web-test",
                },
            },
        )

    def _parent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.parent_access_token}"}

    @staticmethod
    def _student_headers(access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}


class StudentAuthConfigTest(unittest.TestCase):
    def test_production_rejects_missing_student_auth_pepper(self):
        with self.assertRaisesRegex(ConfigError, "APP_STUDENT_AUTH_PEPPER"):
            validate_flask_config(
                {
                    "APP_ENV": "production",
                    "DATABASE_URL": "mysql+pymysql://user:pass@db.example/mira",
                    "STUDENT_AUTH_PEPPER": "",
                    "DEV_ADAPTERS_ENABLED": False,
                    "SMS_PROVIDER": "aliyun",
                    "CAMERA_RUNTIME_PROVIDER": "disabled",
                    "INTERNAL_API_TOKEN": "internal-test-token",
                    "CORS_ORIGINS": ["https://student.example.com"],
                }
            )


if __name__ == "__main__":
    unittest.main()
