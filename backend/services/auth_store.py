from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


PHONE_REPR_ERROR = "请输入正确的 11 位手机号"


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str
    access_expires_at: int
    refresh_expires_at: int


def _now_ms() -> int:
    return int(time.time() * 1000)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) != 11 or digits[0] != "1" or digits[1] not in "3456789":
        raise AuthError("invalid_phone", PHONE_REPR_ERROR)
    return digits


class AuthStore:
    def __init__(
        self,
        db_path: str | Path,
        *,
        access_token_seconds: int = 900,
        refresh_token_seconds: int = 60 * 60 * 24 * 30,
        dev_sms_code: str = "0426",
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.access_token_seconds = access_token_seconds
        self.refresh_token_seconds = refresh_token_seconds
        self.dev_sms_code = dev_sms_code
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS families (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY,
                  phone TEXT NOT NULL UNIQUE,
                  family_id TEXT NOT NULL,
                  display_name TEXT NOT NULL,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sms_codes (
                  phone TEXT PRIMARY KEY,
                  code_hash TEXT NOT NULL,
                  expires_at INTEGER NOT NULL,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  access_hash TEXT NOT NULL UNIQUE,
                  refresh_hash TEXT NOT NULL UNIQUE,
                  access_expires_at INTEGER NOT NULL,
                  refresh_expires_at INTEGER NOT NULL,
                  created_at INTEGER NOT NULL,
                  rotated_at INTEGER,
                  revoked_at INTEGER
                );
                """
            )

    def request_sms_code(self, phone: str) -> dict:
        normalized = _normalize_phone(phone)
        now = _now_ms()
        expires_at = now + 5 * 60 * 1000
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sms_codes(phone, code_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(phone) DO UPDATE SET
                  code_hash = excluded.code_hash,
                  expires_at = excluded.expires_at,
                  created_at = excluded.created_at
                """,
                (normalized, _hash(self.dev_sms_code), expires_at, now),
            )
        return {"phone": normalized, "expiresAt": expires_at, "debugCode": self.dev_sms_code}

    def login_with_sms(self, phone: str, code: str) -> dict:
        normalized = _normalize_phone(phone)
        code = (code or "").strip()
        if not code:
            raise AuthError("missing_code", "请输入验证码")

        now = _now_ms()
        with self._connect() as conn:
            sms = conn.execute(
                "SELECT * FROM sms_codes WHERE phone = ?",
                (normalized,),
            ).fetchone()
            if not sms or sms["expires_at"] < now or sms["code_hash"] != _hash(code):
                raise AuthError("invalid_code", "验证码不正确，请重新输入")

            user = conn.execute("SELECT * FROM users WHERE phone = ?", (normalized,)).fetchone()
            if user is None:
                family_id = f"fam_{uuid.uuid4().hex}"
                user_id = f"user_{uuid.uuid4().hex}"
                conn.execute(
                    "INSERT INTO families(id, name, created_at) VALUES (?, ?, ?)",
                    (family_id, "我的家庭", now),
                )
                conn.execute(
                    """
                    INSERT INTO users(id, phone, family_id, display_name, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, normalized, family_id, "家长", now),
                )
                user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

            conn.execute("DELETE FROM sms_codes WHERE phone = ?", (normalized,))
            session = self._create_session(conn, user["id"], now)
            return self._session_payload(conn, user["id"], session)

    def refresh(self, refresh_token: str) -> dict:
        refresh_token = (refresh_token or "").strip()
        if not refresh_token:
            raise AuthError("missing_refresh_token", "缺少 refresh token", 401)

        now = _now_ms()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM sessions
                WHERE refresh_hash = ? AND revoked_at IS NULL
                """,
                (_hash(refresh_token),),
            ).fetchone()
            if row is None or row["refresh_expires_at"] < now:
                raise AuthError("refresh_expired", "登录状态已过期，请重新登录", 401)

            access_token = _token("mga")
            refresh_token = _token("mgr")
            access_expires_at = now + self.access_token_seconds * 1000
            refresh_expires_at = now + self.refresh_token_seconds * 1000
            conn.execute(
                """
                UPDATE sessions SET
                  access_hash = ?,
                  refresh_hash = ?,
                  access_expires_at = ?,
                  refresh_expires_at = ?,
                  rotated_at = ?
                WHERE id = ?
                """,
                (
                    _hash(access_token),
                    _hash(refresh_token),
                    access_expires_at,
                    refresh_expires_at,
                    now,
                    row["id"],
                ),
            )
            session = AuthSession(
                access_token=access_token,
                refresh_token=refresh_token,
                access_expires_at=access_expires_at,
                refresh_expires_at=refresh_expires_at,
            )
            return self._session_payload(conn, row["user_id"], session)

    def authenticate(self, access_token: str) -> dict:
        access_token = (access_token or "").strip()
        if not access_token:
            raise AuthError("missing_access_token", "缺少 access token", 401)

        now = _now_ms()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM sessions
                WHERE access_hash = ? AND revoked_at IS NULL
                """,
                (_hash(access_token),),
            ).fetchone()
            if row is None or row["access_expires_at"] < now:
                raise AuthError("access_expired", "登录状态需要刷新", 401)
            user = self._user_payload(conn, row["user_id"])
            return {"user": user, "family": self._family_payload(conn, user["familyId"])}

    def logout(self, access_token: str | None = None, refresh_token: str | None = None) -> None:
        now = _now_ms()
        clauses = []
        values: list[str | int] = [now]
        if access_token:
            clauses.append("access_hash = ?")
            values.append(_hash(access_token))
        if refresh_token:
            clauses.append("refresh_hash = ?")
            values.append(_hash(refresh_token))
        if not clauses:
            return
        with self._connect() as conn:
            conn.execute(
                f"UPDATE sessions SET revoked_at = ? WHERE revoked_at IS NULL AND ({' OR '.join(clauses)})",
                values,
            )

    def _create_session(self, conn: sqlite3.Connection, user_id: str, now: int) -> AuthSession:
        access_token = _token("mga")
        refresh_token = _token("mgr")
        access_expires_at = now + self.access_token_seconds * 1000
        refresh_expires_at = now + self.refresh_token_seconds * 1000
        conn.execute(
            """
            INSERT INTO sessions(
              id, user_id, access_hash, refresh_hash,
              access_expires_at, refresh_expires_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"sess_{uuid.uuid4().hex}",
                user_id,
                _hash(access_token),
                _hash(refresh_token),
                access_expires_at,
                refresh_expires_at,
                now,
            ),
        )
        return AuthSession(access_token, refresh_token, access_expires_at, refresh_expires_at)

    def _session_payload(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        session: AuthSession,
    ) -> dict:
        user = self._user_payload(conn, user_id)
        return {
            "ok": True,
            "user": user,
            "family": self._family_payload(conn, user["familyId"]),
            "tokens": {
                "accessToken": session.access_token,
                "refreshToken": session.refresh_token,
                "accessTokenExpiresAt": session.access_expires_at,
                "refreshTokenExpiresAt": session.refresh_expires_at,
                "expiresInSeconds": self.access_token_seconds,
            },
        }

    def _user_payload(self, conn: sqlite3.Connection, user_id: str) -> dict:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise AuthError("user_not_found", "用户不存在", 404)
        return {
            "id": row["id"],
            "phone": row["phone"],
            "familyId": row["family_id"],
            "displayName": row["display_name"],
        }

    def _family_payload(self, conn: sqlite3.Connection, family_id: str) -> dict:
        row = conn.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
        if row is None:
            raise AuthError("family_not_found", "家庭账户不存在", 404)
        return {"id": row["id"], "name": row["name"]}
