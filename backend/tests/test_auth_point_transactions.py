"""Authentication and point-write regressions using only in-memory storage."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import Mock, patch

from flask import Flask

from core.errors import ApiError
from core.security import hash_value, now_ms
from repositories.auth_repository import AuthRepository
from repositories.point_repository import PointRepository
from repositories.profile_repository import ProfileRepository
from routes.api.v1.points import points_bp
from services.auth_service import AuthService
from services.point_service import PointService
from services.profile_service import ProfileService
from services.sms_provider import SmsDelivery
from tests.isolated_transactions import MemoryDatabase


PHONE = "13800000000"
NEXT_PHONE = "13800000001"
CODE = "654321"


class AuthPointTransactionTest(unittest.TestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        self.addCleanup(self.db.close)
        self.auth = AuthService("postgresql://localhost/unused", sms_resend_cooldown_seconds=0)
        self.auth.repository = AuthRepository(self.db)
        # Invitation presentation does not participate in code/session mutation.
        self.auth.repository.list_pending_family_invitations_by_phone = Mock(return_value=[])
        self.auth.sms_provider = Mock()
        self.auth.sms_provider.issue_verification_code.return_value = SmsDelivery(
            code=CODE, provider="isolated", template_id="test", delivery_status="delivered")
        self.points_repo = PointRepository(self.db)
        self.db.allow_runtime_schema_creation = False
        with self.db.transaction() as conn:
            conn.executescript("""
                CREATE TABLE children(id TEXT PRIMARY KEY, family_id TEXT);
                CREATE TABLE family_members(id TEXT, family_id TEXT, user_id TEXT, role TEXT);
                CREATE TABLE app_option_items(catalog_key TEXT, item_key TEXT, enabled INTEGER, metadata_json TEXT);
                CREATE TABLE parent_identities(family_id TEXT);
            """)

    def login(self):
        self.auth.request_sms_code(PHONE)
        return self.auth.login_with_sms(PHONE, CODE)

    def error(self, operation, code, status=None):
        with self.assertRaises(ApiError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        if status is not None:
            self.assertEqual(caught.exception.status_code, status)

    def attempts(self, phone=PHONE):
        row = self.db.one("SELECT attempt_count FROM sms_codes WHERE phone=?", (phone,))
        return row["attempt_count"] if row else None

    def test_rejected_sms_attempts_commit_and_sixth_request_is_limited(self):
        self.auth.request_sms_code(PHONE)
        for attempt in range(1, 6):
            self.error(lambda: self.auth.login_with_sms(PHONE, "wrong"), "invalid_code")
            self.assertEqual(self.attempts(), attempt)
        for value in ("wrong", CODE):
            self.error(lambda: self.auth.login_with_sms(PHONE, value), "sms_attempts_exceeded", 429)
        self.assertEqual(self.attempts(), 5)

    def test_resend_resets_attempts_and_correct_code_is_consumed_once(self):
        self.auth.request_sms_code(PHONE)
        for _ in range(5):
            self.error(lambda: self.auth.login_with_sms(PHONE, "wrong"), "invalid_code")
        self.auth.request_sms_code(PHONE)
        self.assertEqual(self.attempts(), 0)
        result = self.auth.login_with_sms(PHONE, CODE)
        self.assertTrue(result["ok"])
        self.assertEqual(self.auth.authenticate(result["tokens"]["accessToken"])["user"]["phone"], PHONE)
        self.assertIsNone(self.attempts())
        self.error(lambda: self.auth.login_with_sms(PHONE, CODE), "invalid_code")
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM sessions")["n"], 1)

    def test_failed_success_path_rolls_back_code_consumption_and_account_creation(self):
        self.auth.request_sms_code(PHONE)
        with patch.object(self.auth, "_session_payload", side_effect=RuntimeError("isolated failure")):
            with self.assertRaises(RuntimeError):
                self.auth.login_with_sms(PHONE, CODE)
        self.assertEqual(self.attempts(), 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM users")["n"], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM sessions")["n"], 0)

    def test_expired_code_does_not_create_an_account(self):
        self.auth.request_sms_code(PHONE)
        with self.db.transaction() as conn:
            conn.execute("UPDATE sms_codes SET expires_at=0")
        self.error(lambda: self.auth.login_with_sms(PHONE, CODE), "invalid_code")
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM users")["n"], 0)

    def concurrent(self, operation, count):
        barrier = Barrier(count)
        def run(_):
            barrier.wait(timeout=5)
            try:
                return operation()
            except ApiError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(run, range(count)))

    def test_concurrent_wrong_codes_preserve_five_attempt_limit(self):
        self.auth.request_sms_code(PHONE)
        results = self.concurrent(lambda: self.auth.login_with_sms(PHONE, "wrong"), 8)
        self.assertEqual(results.count("invalid_code"), 5)
        self.assertEqual(results.count("sms_attempts_exceeded"), 3)
        self.assertEqual(self.attempts(), 5)
        self.assertTrue(any("sms_codes" in sql and "FOR UPDATE" in sql for sql in self.db.statements))

    def test_concurrent_correct_code_only_creates_one_session(self):
        self.auth.request_sms_code(PHONE)
        results = self.concurrent(lambda: self.auth.login_with_sms(PHONE, CODE), 2)
        self.assertEqual(sum(isinstance(value, dict) and value["ok"] for value in results), 1)
        self.assertEqual(results.count("invalid_code"), 1)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM sessions")["n"], 1)

    def profile(self):
        login = self.login()
        service = object.__new__(ProfileService)
        service.auth_service = self.auth
        service.repository = ProfileRepository(self.db)
        # Keep family display metadata out of this transaction-focused fixture.
        service._current_member_identity = Mock(return_value=({"role": "admin", "name": "家长"}, "", ""))
        service._family_role_label = Mock(return_value="管理员")
        service._capabilities_for_role = Mock(return_value=[])
        return service, login["tokens"]["accessToken"]

    def test_phone_change_rejections_commit_without_changing_phone(self):
        profile, token = self.profile()
        self.auth.request_sms_code(NEXT_PHONE)
        for attempt in range(1, 6):
            self.error(lambda: profile.change_account_phone(token, {"phone": NEXT_PHONE, "code": "wrong"}), "invalid_code")
            self.assertEqual(self.attempts(NEXT_PHONE), attempt)
        self.error(lambda: profile.change_account_phone(token, {"phone": NEXT_PHONE, "code": CODE}), "sms_attempts_exceeded", 429)
        self.assertEqual(self.db.one("SELECT phone FROM users")["phone"], PHONE)

    def test_phone_change_resend_and_success_consume_code(self):
        profile, token = self.profile()
        self.auth.request_sms_code(NEXT_PHONE)
        self.error(lambda: profile.change_account_phone(token, {"phone": NEXT_PHONE, "code": "wrong"}), "invalid_code")
        self.auth.request_sms_code(NEXT_PHONE)
        self.assertEqual(self.attempts(NEXT_PHONE), 0)
        with patch("services.profile_service.account_profile_payload", return_value={}), \
             patch("services.profile_service.account_security_payload", return_value={}):
            result = profile.change_account_phone(token, {"phone": NEXT_PHONE, "code": CODE})
        self.assertTrue(result["ok"])
        self.assertEqual(self.db.one("SELECT phone FROM users")["phone"], NEXT_PHONE)
        self.assertIsNone(self.attempts(NEXT_PHONE))
        self.assertTrue(any("sms_codes" in sql and "FOR UPDATE" in sql for sql in self.db.statements))

    def test_phone_change_unexpected_error_rolls_back_phone_and_code(self):
        profile, token = self.profile()
        self.auth.request_sms_code(NEXT_PHONE)
        with patch("services.profile_service.account_profile_payload", side_effect=RuntimeError("isolated failure")):
            with self.assertRaises(RuntimeError):
                profile.change_account_phone(token, {"phone": NEXT_PHONE, "code": CODE})
        self.assertEqual(self.db.one("SELECT phone FROM users")["phone"], PHONE)
        self.assertEqual(self.attempts(NEXT_PHONE), 0)

    def test_refresh_rotation_rejects_reuse_and_still_allows_logout(self):
        tokens = self.login()["tokens"]
        refreshed = self.auth.refresh(tokens["refreshToken"])["tokens"]
        self.error(lambda: self.auth.refresh(tokens["refreshToken"]), "refresh_expired", 401)
        self.auth.logout(refreshed["accessToken"], refreshed["refreshToken"])
        self.error(lambda: self.auth.authenticate(refreshed["accessToken"]), "access_expired", 401)
        self.error(lambda: self.auth.refresh(refreshed["refreshToken"]), "refresh_expired", 401)

    def test_logout_before_refresh_prevents_rotation(self):
        tokens = self.login()["tokens"]
        self.auth.logout(tokens["accessToken"], tokens["refreshToken"])
        self.error(lambda: self.auth.refresh(tokens["refreshToken"]), "refresh_expired", 401)
        self.assertIsNone(self.db.one("SELECT rotated_at FROM sessions")["rotated_at"])

    def test_concurrent_refresh_has_only_one_winner(self):
        tokens = self.login()["tokens"]
        results = self.concurrent(lambda: self.auth.refresh(tokens["refreshToken"]), 2)
        self.assertEqual(sum(isinstance(value, dict) and value["ok"] for value in results), 1)
        self.assertEqual(results.count("refresh_expired"), 1)
        self.assertTrue(any("refresh_hash" in sql and "FOR UPDATE" in sql for sql in self.db.statements))

    def test_rotation_compare_and_swap_rejects_revoked_or_stale_session(self):
        tokens = self.login()["tokens"]
        before = self.db.one("SELECT * FROM sessions")
        kwargs = dict(session_id=before["id"], **{key: before[key] for key in (
            "device_label", "device_type", "device_model", "device_hardware", "platform", "os_version", "app_version",
            "access_expires_at", "refresh_expires_at")}, access_hash=hash_value("new-access"),
            refresh_hash=hash_value("new-refresh"), rotated_at=now_ms(), expected_refresh_hash=hash_value("stale"))
        with self.db.transaction() as conn:
            self.assertFalse(self.auth.repository.rotate_session(conn, **kwargs))
        self.auth.logout(tokens["accessToken"], tokens["refreshToken"])
        kwargs["expected_refresh_hash"] = before["refresh_hash"]
        with self.db.transaction() as conn:
            self.assertFalse(self.auth.repository.rotate_session(conn, **kwargs))
        after = self.db.one("SELECT * FROM sessions")
        self.assertEqual(after["refresh_hash"], before["refresh_hash"])
        self.assertIsNotNone(after["revoked_at"])

    def test_rotation_failure_never_returns_new_tokens(self):
        tokens = self.login()["tokens"]
        with patch.object(self.auth.repository, "rotate_session", return_value=False):
            self.error(lambda: self.auth.refresh(tokens["refreshToken"]), "refresh_expired", 401)
        self.assertEqual(self.db.one("SELECT refresh_hash FROM sessions")["refresh_hash"], hash_value(tokens["refreshToken"]))

    def point_client(self, role):
        login = self.login()
        family, user = login["family"]["id"], login["user"]["id"]
        with self.db.transaction() as conn:
            conn.execute("INSERT INTO children VALUES ('child',?)", (family,))
            conn.execute("INSERT INTO family_members VALUES ('member',?,?,?)", (family, user, role))
        service = object.__new__(PointService)
        service.auth_service = self.auth
        service.repository = self.points_repo
        service.profile_repository = ProfileRepository(self.db)
        app = Flask(__name__)
        app.register_blueprint(points_bp, url_prefix="/api/points")
        factory = patch("routes.api.v1.points.point_service", return_value=service)
        factory.start(); self.addCleanup(factory.stop)
        return app.test_client(), {"Authorization": "Bearer " + login["tokens"]["accessToken"]}

    def test_viewer_cannot_adjust_points_or_create_ledger(self):
        client, headers = self.point_client("viewer")
        for delta in (500, -1):
            result = client.post("/api/points/adjust", json={"childId": "child", "delta": delta}, headers=headers)
            self.assertEqual(result.status_code, 403)
            self.assertEqual(result.json["error"], "permission_denied")
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM point_accounts")["n"], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM point_ledger")["n"], 0)

    def test_admin_can_adjust_but_cannot_cross_family_or_overdraw(self):
        self.check_allowed_point_role("admin")

    def test_guardian_can_adjust_but_cannot_cross_family_or_overdraw(self):
        self.check_allowed_point_role("guardian")

    def check_allowed_point_role(self, role):
        client, headers = self.point_client(role)
        for delta in (10, -3):
            result = client.post("/api/points/adjust", json={"childId": "child", "delta": delta}, headers=headers)
            self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["account"]["balance"], 7)
        for child, delta, status in (("child", -8, 400), ("other-child", 1, 404)):
            response = client.post("/api/points/adjust", json={"childId": child, "delta": delta}, headers=headers)
            self.assertEqual(response.status_code, status)
        self.assertEqual(self.db.one("SELECT balance FROM point_accounts")["balance"], 7)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM point_ledger")["n"], 2)


if __name__ == "__main__":
    unittest.main()
