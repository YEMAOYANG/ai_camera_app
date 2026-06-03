from __future__ import annotations

from pathlib import Path

from core.database import SQLiteDatabase
from core.errors import AuthError
from core.security import hash_value, new_token, now_ms
from models.auth import AuthSession
from repositories.auth_repository import AuthRepository
from schemas.auth import family_payload, normalize_phone, session_payload, user_payload
from services.sms_provider import MockSmsProvider, SmsProvider


class AuthService:
    def __init__(
        self,
        db_path: str | Path,
        *,
        access_token_seconds: int = 900,
        refresh_token_seconds: int = 60 * 60 * 24 * 30,
        dev_sms_code: str = "0426",
        sms_provider: SmsProvider | None = None,
    ):
        self.access_token_seconds = access_token_seconds
        self.refresh_token_seconds = refresh_token_seconds
        self.dev_sms_code = dev_sms_code
        self.sms_provider = sms_provider or MockSmsProvider(dev_sms_code)
        self.repository = AuthRepository(SQLiteDatabase(db_path))

    def request_sms_code(self, phone: str) -> dict:
        normalized = normalize_phone(phone)
        delivery = self.sms_provider.issue_verification_code(normalized)
        now = now_ms()
        expires_at = now + 5 * 60 * 1000
        with self.repository.transaction() as conn:
            self.repository.upsert_sms_code(
                conn,
                phone=normalized,
                code_hash=hash_value(delivery.code),
                expires_at=expires_at,
                created_at=now,
            )
        return {
            "phone": normalized,
            "expiresAt": expires_at,
            "debugCode": delivery.debug_code,
            "provider": delivery.provider,
            "templateId": delivery.template_id,
            "deliveryStatus": delivery.delivery_status,
        }

    def login_with_sms(self, phone: str, code: str) -> dict:
        normalized = normalize_phone(phone)
        code = (code or "").strip()
        if not code:
            raise AuthError("missing_code", "请输入验证码")

        now = now_ms()
        with self.repository.transaction() as conn:
            sms = self.repository.find_sms_code(conn, normalized)
            if not sms or sms["expires_at"] < now or sms["code_hash"] != hash_value(code):
                raise AuthError("invalid_code", "验证码不正确，请重新输入")

            user = self.repository.find_user_by_phone(conn, normalized)
            if user is None:
                user = self.repository.create_parent_user(conn, phone=normalized, now=now)

            self.repository.delete_sms_code(conn, normalized)
            session = self._new_session(now)
            self.repository.create_session(
                conn,
                user_id=user["id"],
                access_hash=hash_value(session.access_token),
                refresh_hash=hash_value(session.refresh_token),
                access_expires_at=session.access_expires_at,
                refresh_expires_at=session.refresh_expires_at,
                created_at=now,
            )
            return self._session_payload(conn, user["id"], session)

    def refresh(self, refresh_token: str) -> dict:
        refresh_token = (refresh_token or "").strip()
        if not refresh_token:
            raise AuthError("missing_refresh_token", "缺少 refresh token", 401)

        now = now_ms()
        with self.repository.transaction() as conn:
            row = self.repository.find_session_by_refresh_hash(conn, hash_value(refresh_token))
            if row is None or row["refresh_expires_at"] < now:
                raise AuthError("refresh_expired", "登录状态已过期，请重新登录", 401)

            session = self._new_session(now)
            self.repository.rotate_session(
                conn,
                session_id=row["id"],
                access_hash=hash_value(session.access_token),
                refresh_hash=hash_value(session.refresh_token),
                access_expires_at=session.access_expires_at,
                refresh_expires_at=session.refresh_expires_at,
                rotated_at=now,
            )
            return self._session_payload(conn, row["user_id"], session)

    def authenticate(self, access_token: str) -> dict:
        access_token = (access_token or "").strip()
        if not access_token:
            raise AuthError("missing_access_token", "缺少 access token", 401)

        now = now_ms()
        with self.repository.transaction() as conn:
            row = self.repository.find_session_by_access_hash(conn, hash_value(access_token))
            if row is None or row["access_expires_at"] < now:
                raise AuthError("access_expired", "登录状态需要刷新", 401)
            user = self._user_payload(conn, row["user_id"])
            return {"user": user, "family": self._family_payload(conn, user["familyId"])}

    def logout(self, access_token: str | None = None, refresh_token: str | None = None) -> None:
        self.repository.revoke_sessions(
            access_hash=hash_value(access_token) if access_token else None,
            refresh_hash=hash_value(refresh_token) if refresh_token else None,
            revoked_at=now_ms(),
        )

    def _new_session(self, now: int) -> AuthSession:
        return AuthSession(
            access_token=new_token("mga"),
            refresh_token=new_token("mgr"),
            access_expires_at=now + self.access_token_seconds * 1000,
            refresh_expires_at=now + self.refresh_token_seconds * 1000,
        )

    def _session_payload(self, conn, user_id: str, session: AuthSession) -> dict:
        user = self._user_payload(conn, user_id)
        return session_payload(
            user=user,
            family=self._family_payload(conn, user["familyId"]),
            session=session,
            access_token_seconds=self.access_token_seconds,
        )

    def _user_payload(self, conn, user_id: str) -> dict:
        row = self.repository.find_user_by_id(conn, user_id)
        if row is None:
            raise AuthError("user_not_found", "用户不存在", 404)
        return user_payload(row)

    def _family_payload(self, conn, family_id: str) -> dict:
        row = self.repository.find_family_by_id(conn, family_id)
        if row is None:
            raise AuthError("family_not_found", "家庭账户不存在", 404)
        return family_payload(row)
