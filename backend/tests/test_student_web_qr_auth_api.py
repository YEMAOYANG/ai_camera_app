from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

from app import create_app
from core.database import Database
from core.security import hash_value, now_ms
from services.service_factory import student_auth_service
from services.formal_student_learning_access import assert_formal_student_grade_open
from tests.support import fresh_test_config, request_debug_code


class StudentWebQrAuthApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
        self.app.extensions["mira_formal_learning_access_checker"] = (
            lambda conn, child: assert_formal_student_grade_open(child)
        )
        self.client = self.app.test_client()
        self.parent_access_token = self._login_parent("13800003901")
        self.child_id = self._create_child("乐乐", "primary_1")
        self.database = Database(self.app.config["DATABASE_URL"])

    def test_pending_preview_approve_exchange_and_replay_contract(self):
        created = self._create_challenge()
        self.assertEqual(created.status_code, 200, created.json)
        self.assertEqual(created.json["status"], "pending")
        self.assertRegex(created.json["challengeId"], r"^msc_[A-Za-z0-9_-]{40,96}$")
        self.assertRegex(created.json["verifier"], r"^msv_[A-Za-z0-9_-]{40,96}$")
        self.assertRegex(created.json["displayCode"], r"^\d{4}$")
        self.assertEqual(created.json["pollingIntervalMs"], 1500)

        pending = self._exchange(created.json)
        self.assertEqual(pending.status_code, 202, pending.json)
        self.assertEqual(pending.json["status"], "pending")
        self.assertNotIn("tokens", pending.json)

        preview = self.client.get(
            self._parent_qr_path(created.json["challengeId"]),
            query_string={"childId": self.child_id},
            headers=self._parent_headers(),
        )
        self.assertEqual(preview.status_code, 200, preview.json)
        self.assertTrue(preview.json["requiresPin"])
        self.assertFalse(preview.json["pinConfigured"])
        self.assertEqual(preview.json["displayCode"], created.json["displayCode"])
        self.assertEqual(preview.json["clientDevice"]["label"], "客厅学习平板")
        self.assertEqual(preview.json["clientDevice"]["osVersion"], "14")
        self.assertEqual(preview.json["clientDevice"]["browserName"], "Chrome")
        self.assertEqual(preview.json["clientDevice"]["osName"], "Android")
        self.assertIn("requestedAt", preview.json)
        self.assertNotIn("verifier", preview.json)
        self.assertNotIn("familyId", preview.json)

        approved = self.client.post(
            f"{self._parent_qr_path(created.json['challengeId'])}/approve",
            json={"childId": self.child_id, "pin": "2468"},
            headers=self._parent_headers(),
        )
        self.assertEqual(approved.status_code, 200, approved.json)
        self.assertEqual(approved.json["status"], "approved")
        self.assertTrue(approved.json["pinConfigured"])

        exchanged = self._exchange(created.json)
        self.assertEqual(exchanged.status_code, 200, exchanged.json)
        self.assertEqual(exchanged.json["status"], "consumed")
        self.assertEqual(exchanged.json["student"]["childId"], self.child_id)
        self.assertEqual(exchanged.json["device"]["label"], "客厅学习平板")
        self.assertTrue(exchanged.json["deviceToken"].startswith("msd_"))
        self.assertTrue(exchanged.json["tokens"]["accessToken"].startswith("msa_"))

        replay = self._exchange(created.json)
        self.assertEqual(replay.status_code, 409, replay.json)
        self.assertEqual(replay.json["error"], "student_qr_challenge_consumed")

        with self.database.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM student_pairing_challenges WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()
        self.assertEqual(row["status"], "consumed")
        self.assertEqual(row["challenge_hash"], hash_value(created.json["challengeId"]))
        self.assertEqual(row["verifier_hash"], hash_value(created.json["verifier"]))
        self.assertNotEqual(row["challenge_hash"], created.json["challengeId"])
        self.assertNotEqual(row["verifier_hash"], created.json["verifier"])
        self.assertNotEqual(row["pin_hash"], "2468")
        self.assertEqual(row["display_code"], created.json["displayCode"])
        self.assertNotEqual(row["client_fingerprint_hash"], "browser-test-fingerprint-0001")

    def test_existing_principal_requires_no_pin_and_preserves_pin(self):
        paired = self._pair_with_code("1357")
        self.assertEqual(paired.status_code, 200, paired.json)
        with self.database.transaction() as conn:
            before = conn.execute(
                "SELECT pin_hash, pin_updated_at FROM student_principals WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()

        created = self._create_challenge()
        preview = self.client.get(
            self._parent_qr_path(created.json["challengeId"]),
            query_string={"childId": self.child_id},
            headers=self._parent_headers(),
        )
        self.assertEqual(preview.status_code, 200, preview.json)
        self.assertFalse(preview.json["requiresPin"])
        self.assertTrue(preview.json["pinConfigured"])
        approved = self.client.post(
            f"{self._parent_qr_path(created.json['challengeId'])}/approve",
            json={"childId": self.child_id},
            headers=self._parent_headers(),
        )
        self.assertEqual(approved.status_code, 200, approved.json)
        exchanged = self._exchange(created.json)
        self.assertEqual(exchanged.status_code, 200, exchanged.json)

        with self.database.transaction() as conn:
            after = conn.execute(
                "SELECT pin_hash, pin_updated_at FROM student_principals WHERE child_id = ?",
                (self.child_id,),
            ).fetchone()
        self.assertEqual(after["pin_hash"], before["pin_hash"])
        self.assertEqual(after["pin_updated_at"], before["pin_updated_at"])

        logout = self.client.post(
            "/api/v2/student/auth/logout",
            json={"refreshToken": exchanged.json["tokens"]["refreshToken"]},
            headers={
                "Authorization": f"Bearer {exchanged.json['tokens']['accessToken']}"
            },
        )
        self.assertEqual(logout.status_code, 200, logout.json)
        unlocked = self.client.post(
            "/api/v2/student/auth/unlock",
            json={"deviceToken": exchanged.json["deviceToken"], "pin": "1357"},
        )
        self.assertEqual(unlocked.status_code, 200, unlocked.json)

    def test_first_pairing_requires_pin_and_kindergarten_is_rejected(self):
        created = self._create_challenge()
        missing_pin = self.client.post(
            f"{self._parent_qr_path(created.json['challengeId'])}/approve",
            json={"childId": self.child_id},
            headers=self._parent_headers(),
        )
        self.assertEqual(missing_pin.status_code, 400, missing_pin.json)
        self.assertEqual(missing_pin.json["error"], "invalid_student_pin_format")

        kindergarten_id = self._insert_child("安安", "kindergarten_big")
        rejected = self.client.post(
            f"{self._parent_qr_path(created.json['challengeId'])}/approve",
            json={"childId": kindergarten_id, "pin": "2468"},
            headers=self._parent_headers(),
        )
        self.assertEqual(rejected.status_code, 409, rejected.json)
        self.assertEqual(rejected.json["error"], "student_learning_primary_only")

    def test_qr_approval_rejects_unopened_primary_grade_without_binding(self):
        created = self._create_challenge()
        primary_two_id = self._insert_child("安安", "primary_2")

        rejected = self.client.post(
            f"{self._parent_qr_path(created.json['challengeId'])}/approve",
            json={"childId": primary_two_id, "pin": "2468"},
            headers=self._parent_headers(),
        )

        self.assertEqual(rejected.status_code, 409, rejected.json)
        self.assertEqual(rejected.json["error"], "student_learning_grade_not_open")
        with self.database.transaction() as conn:
            challenge = conn.execute(
                "SELECT status, child_id FROM student_pairing_challenges WHERE challenge_hash = ?",
                (hash_value(created.json["challengeId"]),),
            ).fetchone()
            principals = conn.execute(
                "SELECT COUNT(*) AS count FROM student_principals WHERE child_id = ?",
                (primary_two_id,),
            ).fetchone()["count"]
        self.assertEqual(challenge["status"], "pending")
        self.assertIsNone(challenge["child_id"])
        self.assertEqual(int(principals), 0)

    def test_wrong_verifier_does_not_consume_and_expiry_is_terminal(self):
        created = self._create_challenge()
        wrong = self.client.post(
            "/api/v2/student/auth/qr/exchange",
            json={
                "challengeId": created.json["challengeId"],
                "verifier": "msv_" + "A" * 43,
            },
        )
        self.assertEqual(wrong.status_code, 401, wrong.json)
        self.assertEqual(wrong.json["error"], "invalid_student_qr_challenge")
        still_pending = self._exchange(created.json)
        self.assertEqual(still_pending.status_code, 202, still_pending.json)

        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE student_pairing_challenges SET expires_at = ? WHERE challenge_hash = ?",
                (now_ms() - 1, hash_value(created.json["challengeId"])),
            )
        expired = self._exchange(created.json)
        self.assertEqual(expired.status_code, 410, expired.json)
        self.assertEqual(expired.json["error"], "student_qr_challenge_expired")
        with self.database.transaction() as conn:
            row = conn.execute(
                "SELECT status FROM student_pairing_challenges WHERE challenge_hash = ?",
                (hash_value(created.json["challengeId"]),),
            ).fetchone()
        self.assertEqual(row["status"], "expired")

    def test_parent_preview_persists_expiry_and_reject_is_terminal(self):
        expired_challenge = self._create_challenge(fingerprint="browser-expiry-fingerprint")
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE student_pairing_challenges SET expires_at = ? WHERE challenge_hash = ?",
                (now_ms() - 1, hash_value(expired_challenge.json["challengeId"])),
            )
        preview = self.client.get(
            self._parent_qr_path(expired_challenge.json["challengeId"]),
            query_string={"childId": self.child_id},
            headers=self._parent_headers(),
        )
        self.assertEqual(preview.status_code, 404, preview.json)
        with self.database.transaction() as conn:
            expired_row = conn.execute(
                "SELECT status FROM student_pairing_challenges WHERE challenge_hash = ?",
                (hash_value(expired_challenge.json["challengeId"]),),
            ).fetchone()
        self.assertEqual(expired_row["status"], "expired")

        created = self._create_challenge(fingerprint="browser-reject-fingerprint")
        approved = self.client.post(
            f"{self._parent_qr_path(created.json['challengeId'])}/approve",
            json={"childId": self.child_id, "pin": "2468"},
            headers=self._parent_headers(),
        )
        self.assertEqual(approved.status_code, 200, approved.json)
        self.assertIn("approvalExpiresAt", approved.json)
        rejected = self.client.post(
            f"{self._parent_qr_path(created.json['challengeId'])}/reject",
            json={"childId": self.child_id},
            headers=self._parent_headers(),
        )
        self.assertEqual(rejected.status_code, 200, rejected.json)
        self.assertEqual(rejected.json["status"], "rejected")
        self.assertEqual(rejected.json["challengeId"], created.json["challengeId"])
        exchanged = self._exchange(created.json)
        self.assertEqual(exchanged.status_code, 403, exchanged.json)
        self.assertEqual(exchanged.json["error"], "student_qr_challenge_rejected")
        with self.database.transaction() as conn:
            rejected_row = conn.execute(
                """
                SELECT status, pin_hash, pin_salt, pin_iterations
                FROM student_pairing_challenges WHERE challenge_hash = ?
                """,
                (hash_value(created.json["challengeId"]),),
            ).fetchone()
        self.assertEqual(rejected_row["status"], "rejected")
        self.assertIsNone(rejected_row["pin_hash"])
        self.assertIsNone(rejected_row["pin_salt"])
        self.assertIsNone(rejected_row["pin_iterations"])

    def test_challenge_rate_limit_metadata_validation_and_ip_privacy(self):
        created_payloads = []
        for index in range(3):
            response = self._create_challenge(
                fingerprint="browser-rate-fingerprint",
                remote_addr="8.8.8.8",
            )
            self.assertEqual(response.status_code, 200, (index, response.json))
            created_payloads.append(response.json)
        limited = self._create_challenge(
            fingerprint="browser-rate-fingerprint",
            remote_addr="8.8.8.8",
        )
        self.assertEqual(limited.status_code, 429, limited.json)
        self.assertEqual(limited.json["error"], "student_qr_active_challenge_limit")
        with self.database.transaction() as conn:
            rows = conn.execute(
                "SELECT client_fingerprint_hash, request_ip_hash FROM student_pairing_challenges"
            ).fetchall()
        self.assertTrue(rows)
        self.assertTrue(all(row["request_ip_hash"] != "8.8.8.8" for row in rows))
        self.assertTrue(
            all(
                row["client_fingerprint_hash"] != "browser-rate-fingerprint"
                for row in rows
            )
        )

        old_cutoff = now_ms() - 8 * 24 * 60 * 60 * 1000
        old_hash = hash_value(created_payloads[0]["challengeId"])
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE student_pairing_challenges
                SET status = 'expired', updated_at = ?
                WHERE challenge_hash = ?
                """,
                (old_cutoff, old_hash),
            )
        with self.app.app_context():
            maintained = student_auth_service().cleanup_qr_challenges()
        self.assertTrue(maintained["ok"])
        self.assertGreaterEqual(maintained["deletedCount"], 1)
        with self.database.transaction() as conn:
            old_row = conn.execute(
                "SELECT id FROM student_pairing_challenges WHERE challenge_hash = ?",
                (old_hash,),
            ).fetchone()
        self.assertIsNone(old_row)

        invalid_metadata = self.client.post(
            "/api/v2/student/auth/qr/challenges",
            json={
                "clientDevice": {
                    "fingerprint": "browser-invalid-metadata",
                    "browserName": "<script>",
                }
            },
        )
        self.assertEqual(invalid_metadata.status_code, 400, invalid_metadata.json)
        self.assertEqual(invalid_metadata.json["error"], "invalid_student_client_device")

    def test_concurrent_challenge_creation_is_deadlock_safe_and_rate_limited(self):
        stale = self._create_challenge(
            fingerprint="browser-concurrent-stale-0001"
        )
        self.assertEqual(stale.status_code, 200, stale.json)
        stale_hash = hash_value(stale.json["challengeId"])
        old_cutoff = now_ms() - 8 * 24 * 60 * 60 * 1000
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE student_pairing_challenges
                SET status = 'expired', updated_at = ?
                WHERE challenge_hash = ?
                """,
                (old_cutoff, stale_hash),
            )

        distinct_results = self._create_challenges_concurrently(
            [f"browser-concurrent-distinct-{index:04d}" for index in range(8)]
        )
        self.assertEqual(
            [status for status, _payload in distinct_results],
            [200] * 8,
            distinct_results,
        )
        with self.database.transaction() as conn:
            stale_row = conn.execute(
                "SELECT id FROM student_pairing_challenges WHERE challenge_hash = ?",
                (stale_hash,),
            ).fetchone()
        self.assertIsNone(stale_row)

        shared_fingerprint = "browser-concurrent-shared-0001"
        shared_results = self._create_challenges_concurrently(
            [shared_fingerprint] * 6
        )
        statuses = sorted(status for status, _payload in shared_results)
        self.assertEqual(statuses, [200, 200, 200, 429, 429, 429], shared_results)
        for status, payload in shared_results:
            if status == 429:
                self.assertEqual(
                    payload["error"],
                    "student_qr_active_challenge_limit",
                )

    def test_parent_routes_require_auth_and_foreign_child_is_not_disclosed(self):
        created = self._create_challenge()
        path = self._parent_qr_path(created.json["challengeId"])
        preview = self.client.get(path)
        self.assertEqual(preview.status_code, 401, preview.json)
        approve = self.client.post(
            f"{path}/approve",
            json={"childId": self.child_id, "pin": "2468"},
        )
        self.assertEqual(approve.status_code, 401, approve.json)

        other_token = self._login_parent("13800003902")
        foreign = self.client.post(
            f"{path}/approve",
            json={"childId": self.child_id, "pin": "2468"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(foreign.status_code, 404, foreign.json)
        self.assertEqual(foreign.json["error"], "child_not_found")
        pending = self._exchange(created.json)
        self.assertEqual(pending.status_code, 202, pending.json)

    def _create_challenge(
        self,
        *,
        fingerprint: str = "browser-test-fingerprint-0001",
        remote_addr: str | None = None,
    ):
        request_options = (
            {"environ_base": {"REMOTE_ADDR": remote_addr}} if remote_addr else {}
        )
        return self.client.post(
            "/api/v2/student/auth/qr/challenges",
            json={
                "clientDevice": {
                    "fingerprint": fingerprint,
                    "label": "客厅学习平板",
                    "type": "tablet",
                    "platform": "android",
                    "model": "Mira Test Tablet",
                    "hardware": "tablet",
                    "osVersion": "14",
                    "browserName": "Chrome",
                    "osName": "Android",
                    "appVersion": "web-test",
                }
            },
            **request_options,
        )

    def _create_challenges_concurrently(
        self,
        fingerprints: list[str],
    ) -> list[tuple[int, dict]]:
        barrier = Barrier(len(fingerprints))

        def create(fingerprint: str) -> tuple[int, dict]:
            with self.app.test_client() as client:
                barrier.wait(timeout=5)
                response = client.post(
                    "/api/v2/student/auth/qr/challenges",
                    json={
                        "clientDevice": {
                            "fingerprint": fingerprint,
                            "label": "并发测试浏览器",
                            "type": "browser",
                            "platform": "web",
                            "model": "Concurrent Browser",
                            "hardware": "browser",
                            "osVersion": "test",
                            "browserName": "Chrome",
                            "osName": "macOS",
                            "appVersion": "web-test",
                        }
                    },
                )
                return response.status_code, response.get_json()

        with ThreadPoolExecutor(max_workers=len(fingerprints)) as executor:
            return list(executor.map(create, fingerprints))

    def _exchange(self, created: dict):
        return self.client.post(
            "/api/v2/student/auth/qr/exchange",
            json={
                "challengeId": created["challengeId"],
                "verifier": created["verifier"],
            },
        )

    @staticmethod
    def _parent_qr_path(challenge_id: str) -> str:
        return f"/api/v2/parent/student-access/qr-challenges/{challenge_id}"

    def _pair_with_code(self, pin: str):
        pairing = self.client.post(
            f"/api/v2/parent/children/{self.child_id}/student-access/pairing-codes",
            json={"pin": pin},
            headers=self._parent_headers(),
        )
        self.assertEqual(pairing.status_code, 200, pairing.json)
        return self.client.post(
            "/api/v2/student/auth/pair",
            json={
                "pairingCode": pairing.json["pairingCode"],
                "clientDevice": {"platform": "web", "type": "browser"},
            },
        )

    def _login_parent(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        response = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["tokens"]["accessToken"]

    def _create_child(self, name: str, grade_code: str) -> str:
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
                "name": name,
                "nickname": name,
                "gradeCode": grade_code,
                "schoolYearStartYear": datetime.now().year,
            },
            headers=self._parent_headers(),
        )
        self.assertEqual(child.status_code, 200, child.json)
        return child.json["child"]["id"]

    def _insert_child(self, name: str, grade_code: str) -> str:
        child_id = f"child-{grade_code}"
        now = now_ms()
        grade = "大班" if grade_code.startswith("kindergarten") else "一年级"
        stage = "幼儿园" if grade_code.startswith("kindergarten") else "小学"
        with self.database.transaction() as conn:
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
                    grade,
                    grade_code,
                    stage,
                    f"{stage} {grade}",
                    now,
                    now,
                ),
            )
        return child_id

    def _parent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.parent_access_token}"}


if __name__ == "__main__":
    unittest.main()
