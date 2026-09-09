from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import secrets
import time
from pathlib import Path
from typing import Callable

import pymysql

from core.database import Database, DatabaseRow
from core.errors import ApiError, AuthError
from core.security import hash_value, new_token, now_ms
from repositories.profile_repository import ProfileRepository
from repositories.student_access_repository import StudentAccessRepository
from schemas.profile import role_capabilities_from_option
from schemas.student_auth import (
    normalize_pairing_code,
    normalize_qr_challenge_id,
    normalize_qr_verifier,
    normalize_student_client_device,
    parent_student_authorizations_payload,
    student_client_device_payload,
    student_device_payload,
    student_payload,
    student_tokens_payload,
    validate_student_pin,
)
from services.auth_service import AuthService
from services.formal_student_learning_access import (
    assert_formal_student_workspace_open,
)


PAIRING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MANAGE_STUDENT_ACCESS_CAPABILITY = "manage_child_profile"
PARENT_CAPABILITY_FALLBACKS = {
    "admin": {MANAGE_STUDENT_ACCESS_CAPABILITY},
    "guardian": {MANAGE_STUDENT_ACCESS_CAPABILITY},
    "viewer": set(),
}
QR_MAINTENANCE_RETRYABLE_DB_CODES = {1205, 1213}
log = logging.getLogger(__name__)


class StudentAuthService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        parent_auth_service: AuthService,
        pepper: str,
        access_token_seconds: int = 900,
        refresh_token_seconds: int = 60 * 60 * 24 * 30,
        device_token_seconds: int = 60 * 60 * 24 * 180,
        pairing_code_ttl_seconds: int = 600,
        qr_challenge_ttl_seconds: int = 300,
        qr_approval_exchange_seconds: int = 60,
        qr_polling_interval_ms: int = 1500,
        qr_active_challenge_limit: int = 3,
        qr_ip_active_challenge_limit: int = 100,
        qr_rate_limit_window_seconds: int = 60,
        qr_rate_limit_max: int = 8,
        qr_ip_rate_limit_max: int = 120,
        qr_retention_seconds: int = 60 * 60 * 24 * 7,
        pin_pbkdf2_iterations: int = 210_000,
        pin_max_attempts: int = 5,
        pin_lock_seconds: int = 900,
        formal_learning_access_checker: Callable[[object, DatabaseRow], None]
        | None = None,
    ):
        if not str(pepper or "").strip():
            raise RuntimeError("Student authentication pepper is not configured.")
        database = Database(database_url)
        self.parent_auth_service = parent_auth_service
        self.repository = StudentAccessRepository(database)
        self.profile_repository = ProfileRepository(database)
        self.formal_learning_access_checker = formal_learning_access_checker
        self.pepper = pepper.encode("utf-8")
        self.access_token_seconds = int(access_token_seconds)
        self.refresh_token_seconds = int(refresh_token_seconds)
        self.device_token_seconds = int(device_token_seconds)
        self.pairing_code_ttl_seconds = int(pairing_code_ttl_seconds)
        self.qr_challenge_ttl_seconds = int(qr_challenge_ttl_seconds)
        self.qr_approval_exchange_seconds = int(qr_approval_exchange_seconds)
        self.qr_polling_interval_ms = int(qr_polling_interval_ms)
        self.qr_active_challenge_limit = int(qr_active_challenge_limit)
        self.qr_ip_active_challenge_limit = int(qr_ip_active_challenge_limit)
        self.qr_rate_limit_window_seconds = int(qr_rate_limit_window_seconds)
        self.qr_rate_limit_max = int(qr_rate_limit_max)
        self.qr_ip_rate_limit_max = int(qr_ip_rate_limit_max)
        self.qr_retention_seconds = int(qr_retention_seconds)
        self.pin_pbkdf2_iterations = int(pin_pbkdf2_iterations)
        self.pin_max_attempts = int(pin_max_attempts)
        self.pin_lock_seconds = int(pin_lock_seconds)

    def list_authorizations(
        self,
        parent_access_token: str,
        child_id: str,
    ) -> dict:
        context = self.parent_auth_service.authenticate(parent_access_token)
        family_id = context["family"]["id"]
        with self.repository.transaction() as conn:
            child = self.profile_repository.get_child(
                conn,
                family_id=family_id,
                child_id=child_id,
            )
            if child is None:
                raise ApiError("child_not_found", "孩子资料不存在", 404)
            self._assert_parent_can_manage_student_access(conn, context)
            rows = self.repository.list_owned_authorizations(
                conn,
                family_id=family_id,
                child_id=child_id,
            )
        return {
            "ok": True,
            "childId": child_id,
            "authorizations": parent_student_authorizations_payload(
                rows,
                now=now_ms(),
            ),
        }

    def revoke_authorization(
        self,
        parent_access_token: str,
        child_id: str,
        device_id: str,
    ) -> dict:
        context = self.parent_auth_service.authenticate(parent_access_token)
        family_id = context["family"]["id"]
        normalized_device_id = str(device_id or "").strip()
        now = now_ms()
        with self.repository.transaction() as conn:
            child = self.profile_repository.get_child(
                conn,
                family_id=family_id,
                child_id=child_id,
            )
            if child is None:
                raise ApiError("child_not_found", "孩子资料不存在", 404)
            self._assert_parent_can_manage_student_access(conn, context)
            device = self.repository.get_owned_device_for_update(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=normalized_device_id,
            )
            if device is None:
                raise ApiError(
                    "student_authorization_not_found",
                    "学生设备授权不存在",
                    404,
                )
            already_revoked = device.get("revoked_at") is not None
            if not already_revoked:
                self.repository.revoke_trusted_device(
                    conn,
                    device_id=normalized_device_id,
                    revoked_at=now,
                )
            revoked_session_count = self.repository.revoke_device_sessions(
                conn,
                device_id=normalized_device_id,
                revoked_at=now,
            )
        return {
            "ok": True,
            "childId": child_id,
            "authorizationId": normalized_device_id,
            "status": "revoked",
            "alreadyRevoked": already_revoked,
            "revokedSessionCount": revoked_session_count,
            "revokedAt": int(device.get("revoked_at") or now),
        }

    def reset_pin(
        self,
        parent_access_token: str,
        child_id: str,
        data: dict,
    ) -> dict:
        context = self.parent_auth_service.authenticate(parent_access_token)
        pin = validate_student_pin((data or {}).get("pin"))
        family_id = context["family"]["id"]
        now = now_ms()
        pin_salt, pin_hash = self._new_pin_hash(pin)
        with self.repository.transaction() as conn:
            child = self.profile_repository.get_child(
                conn,
                family_id=family_id,
                child_id=child_id,
            )
            if child is None:
                raise ApiError("child_not_found", "孩子资料不存在", 404)
            self._assert_parent_can_manage_student_access(conn, context)
            principal = self.repository.get_principal_for_child(
                conn,
                family_id=family_id,
                child_id=child_id,
                for_update=True,
            )
            if principal is None:
                raise ApiError(
                    "student_access_not_configured",
                    "请先为孩子开通学生学习空间",
                    404,
                )
            self.repository.update_principal_pin(
                conn,
                principal_id=principal["id"],
                pin_hash=pin_hash,
                pin_salt=pin_salt,
                pin_iterations=self.pin_pbkdf2_iterations,
                now=now,
            )
            self.repository.revoke_active_pairing_codes(
                conn,
                family_id=family_id,
                child_id=child_id,
                revoked_at=now,
            )
            revoked_session_count = self.repository.revoke_principal_sessions(
                conn,
                principal_id=principal["id"],
                revoked_at=now,
            )
            trusted_device_count = (
                self.repository.reset_principal_device_pin_failures(
                    conn,
                    principal_id=principal["id"],
                    now=now,
                )
            )
        return {
            "ok": True,
            "childId": child_id,
            "pinUpdatedAt": now,
            "revokedSessionCount": revoked_session_count,
            "trustedDeviceCount": trusted_device_count,
            "existingDevicesRemainTrusted": True,
            "requiresUnlockWithNewPin": True,
        }

    def create_pairing_code(
        self,
        parent_access_token: str,
        child_id: str,
        data: dict,
    ) -> dict:
        context = self.parent_auth_service.authenticate(parent_access_token)
        family_id = context["family"]["id"]
        now = now_ms()

        with self.repository.transaction() as conn:
            child = self.profile_repository.get_child(
                conn,
                family_id=family_id,
                child_id=child_id,
            )
            if child is None:
                raise ApiError("child_not_found", "孩子资料不存在", 404)
            self._assert_formal_learning_access(conn, child)
            self._assert_parent_can_manage_student_access(conn, context)
            pin = validate_student_pin(data.get("pin"))
            expires_at = now + self.pairing_code_ttl_seconds * 1000
            pin_salt, pin_hash = self._new_pin_hash(pin)
            self.repository.revoke_active_pairing_codes(
                conn,
                family_id=family_id,
                child_id=child_id,
                revoked_at=now,
            )
            pairing_code = self._new_unique_pairing_code(conn)
            self.repository.create_pairing_code(
                conn,
                family_id=family_id,
                child_id=child_id,
                created_by_user_id=context["user"]["id"],
                code_hash=self._pairing_code_hash(pairing_code),
                pin_hash=pin_hash,
                pin_salt=pin_salt,
                pin_iterations=self.pin_pbkdf2_iterations,
                expires_at=expires_at,
                created_at=now,
            )
            return {
                "ok": True,
                "pairingCode": pairing_code,
                "expiresAt": expires_at,
                "child": {
                    "id": child["id"],
                    "name": child["name"],
                    "nickname": child.get("nickname") or "",
                },
            }

    def pair(self, data: dict) -> dict:
        pairing_code = normalize_pairing_code(data.get("pairingCode"))
        client_device = normalize_student_client_device(data.get("clientDevice"))
        now = now_ms()
        device_token = new_token("msd")
        session_tokens = self._new_session_tokens(now)

        with self.repository.transaction() as conn:
            pairing = self.repository.get_pairing_code_for_update(
                conn,
                code_hash=self._pairing_code_hash(pairing_code),
            )
            if not self._pairing_code_is_usable(pairing, now=now):
                raise AuthError("invalid_pairing_code", "配对码无效或已过期", 401)
            child = self.profile_repository.get_child(
                conn,
                family_id=pairing["family_id"],
                child_id=pairing["child_id"],
            )
            if child is None:
                raise AuthError("invalid_pairing_code", "配对码无效或已过期", 401)
            self._assert_formal_learning_access(conn, child)

            principal = self.repository.get_principal_for_child(
                conn,
                family_id=pairing["family_id"],
                child_id=pairing["child_id"],
                for_update=True,
            )
            if principal is None:
                principal = self.repository.create_principal(
                    conn,
                    family_id=pairing["family_id"],
                    child_id=pairing["child_id"],
                    pin_hash=pairing["pin_hash"],
                    pin_salt=pairing["pin_salt"],
                    pin_iterations=int(pairing["pin_iterations"]),
                    now=now,
                )
            else:
                principal = self.repository.update_principal_pin(
                    conn,
                    principal_id=principal["id"],
                    pin_hash=pairing["pin_hash"],
                    pin_salt=pairing["pin_salt"],
                    pin_iterations=int(pairing["pin_iterations"]),
                    now=now,
                )

            device = self.repository.create_trusted_device(
                conn,
                principal_id=principal["id"],
                family_id=principal["family_id"],
                child_id=principal["child_id"],
                device_token_hash=hash_value(device_token),
                client_device=client_device,
                expires_at=now + self.device_token_seconds * 1000,
                now=now,
            )
            session = self._create_session(
                conn,
                principal_id=principal["id"],
                device_id=device["id"],
                tokens=session_tokens,
                now=now,
            )
            self.repository.consume_pairing_code(
                conn,
                pairing_id=pairing["id"],
                consumed_at=now,
            )
            response = self._session_response(
                conn,
                principal_id=principal["id"],
                device=device,
                session=session,
                tokens=session_tokens,
            )
            response["deviceToken"] = device_token
            return response

    def create_qr_challenge(
        self,
        data: dict,
        *,
        request_ip: str | None = None,
    ) -> dict:
        client_device = normalize_student_client_device(data.get("clientDevice"))
        challenge_id = new_token("msc")
        verifier = new_token("msv")
        display_code = f"{secrets.randbelow(10_000):04d}"
        now = now_ms()
        expires_at = now + self.qr_challenge_ttl_seconds * 1000
        request_ip_hash = self._qr_request_ip_hash(request_ip)
        client_fingerprint_hash = self._qr_client_fingerprint_hash(
            client_device,
            request_ip_hash=request_ip_hash,
        )
        self._maintain_qr_challenges_before_create(now=now)
        with self.repository.transaction() as conn:
            self.repository.lock_qr_rate_bucket(
                conn,
                bucket_kind="fingerprint",
                bucket_hash=client_fingerprint_hash,
                now=now,
            )
            if request_ip_hash:
                self.repository.lock_qr_rate_bucket(
                    conn,
                    bucket_kind="ip",
                    bucket_hash=request_ip_hash,
                    now=now,
                )
            active_fingerprint, active_ip = self.repository.count_active_qr_challenges(
                conn,
                client_fingerprint_hash=client_fingerprint_hash,
                request_ip_hash=request_ip_hash,
                now=now,
            )
            recent_fingerprint, recent_ip = self.repository.count_recent_qr_challenges(
                conn,
                client_fingerprint_hash=client_fingerprint_hash,
                request_ip_hash=request_ip_hash,
                window_started_at=(
                    now - self.qr_rate_limit_window_seconds * 1000
                ),
            )
            if (
                active_fingerprint >= self.qr_active_challenge_limit
                or active_ip >= self.qr_ip_active_challenge_limit
            ):
                raise ApiError(
                    "student_qr_active_challenge_limit",
                    "当前设备已有待确认的二维码，请先使用或刷新当前二维码",
                    429,
                )
            if (
                recent_fingerprint >= self.qr_rate_limit_max
                or recent_ip >= self.qr_ip_rate_limit_max
            ):
                raise ApiError(
                    "student_qr_rate_limited",
                    "二维码刷新太频繁，请稍后再试",
                    429,
                )
            self.repository.create_qr_challenge(
                conn,
                challenge_hash=hash_value(challenge_id),
                verifier_hash=hash_value(verifier),
                display_code=display_code,
                client_device=client_device,
                client_fingerprint_hash=client_fingerprint_hash,
                request_ip_hash=request_ip_hash,
                expires_at=expires_at,
                now=now,
            )
        return {
            "ok": True,
            "status": "pending",
            "challengeId": challenge_id,
            "verifier": verifier,
            "displayCode": display_code,
            "expiresAt": expires_at,
            "pollingIntervalMs": self.qr_polling_interval_ms,
        }

    def preview_qr_challenge(
        self,
        parent_access_token: str,
        challenge_id: str,
        *,
        child_id: str | None = None,
    ) -> dict:
        context = self.parent_auth_service.authenticate(parent_access_token)
        normalized_id = normalize_qr_challenge_id(challenge_id)
        family_id = context["family"]["id"]
        now = now_ms()
        terminal_error: ApiError | None = None
        response: dict | None = None
        with self.repository.transaction() as conn:
            self._assert_parent_can_manage_student_access(conn, context)
            challenge = self.repository.get_qr_challenge_for_update(
                conn,
                challenge_hash=hash_value(normalized_id),
            )
            if challenge is None:
                terminal_error = self._qr_challenge_unavailable_error()
            else:
                status = self._effective_qr_challenge_status(
                    conn,
                    challenge,
                    now=now,
                )
                if status != "pending":
                    terminal_error = self._qr_challenge_unavailable_error()
                else:
                    selected_child = None
                    requested_child_id = str(child_id or "").strip()
                    if requested_child_id:
                        selected_child = self.profile_repository.get_child(
                            conn,
                            family_id=family_id,
                            child_id=requested_child_id,
                        )
                        if selected_child is None:
                            raise ApiError("child_not_found", "孩子资料不存在", 404)
                    else:
                        selected_child = self.profile_repository.current_child(
                            conn,
                            family_id=family_id,
                        )
                    principal = None
                    if selected_child is not None:
                        self._assert_formal_learning_access(conn, selected_child)
                        principal = self.repository.get_principal_for_child(
                            conn,
                            family_id=family_id,
                            child_id=selected_child["id"],
                        )
                    response = {
                        "ok": True,
                        "status": "pending",
                        "challengeId": normalized_id,
                        "displayCode": str(challenge["display_code"]),
                        "requiresPin": principal is None,
                        "pinConfigured": principal is not None,
                        "clientDevice": student_client_device_payload(challenge),
                        "requestedAt": int(challenge["created_at"]),
                        "expiresAt": int(challenge["expires_at"]),
                    }

        if terminal_error is not None:
            raise terminal_error
        if response is None:
            raise self._qr_challenge_unavailable_error()
        return response

    def approve_qr_challenge(
        self,
        parent_access_token: str,
        challenge_id: str,
        data: dict,
    ) -> dict:
        context = self.parent_auth_service.authenticate(parent_access_token)
        normalized_id = normalize_qr_challenge_id(challenge_id)
        child_id = str(data.get("childId") or "").strip()
        if not child_id:
            raise ApiError("missing_child_id", "请选择要登录的孩子")
        family_id = context["family"]["id"]
        now = now_ms()
        terminal_error: ApiError | None = None
        response: dict | None = None
        with self.repository.transaction() as conn:
            self._assert_parent_can_manage_student_access(conn, context)
            challenge = self.repository.get_qr_challenge_for_update(
                conn,
                challenge_hash=hash_value(normalized_id),
            )
            if challenge is None:
                terminal_error = self._qr_challenge_unavailable_error()
            else:
                status = self._effective_qr_challenge_status(
                    conn,
                    challenge,
                    now=now,
                )
                if status != "pending":
                    terminal_error = self._qr_challenge_unavailable_error()
                else:
                    child = self.profile_repository.get_child(
                        conn,
                        family_id=family_id,
                        child_id=child_id,
                    )
                    if child is None:
                        raise ApiError("child_not_found", "孩子资料不存在", 404)
                    self._assert_formal_learning_access(conn, child)
                    principal = self.repository.get_principal_for_child(
                        conn,
                        family_id=family_id,
                        child_id=child_id,
                        for_update=True,
                    )
                    pin_hash = None
                    pin_salt = None
                    pin_iterations = None
                    if principal is None:
                        pin = validate_student_pin(data.get("pin"))
                        pin_salt, pin_hash = self._new_pin_hash(pin)
                        pin_iterations = self.pin_pbkdf2_iterations
                    elif data.get("pin") not in {None, ""}:
                        validate_student_pin(data.get("pin"))
                    approved_expires_at = (
                        now + self.qr_approval_exchange_seconds * 1000
                    )
                    approved = self.repository.approve_qr_challenge(
                        conn,
                        challenge_row_id=challenge["id"],
                        family_id=family_id,
                        child_id=child_id,
                        approved_by_user_id=context["user"]["id"],
                        pin_hash=pin_hash,
                        pin_salt=pin_salt,
                        pin_iterations=pin_iterations,
                        approved_expires_at=approved_expires_at,
                        now=now,
                    )
                    if approved is None:
                        raise ApiError(
                            "student_qr_challenge_unavailable",
                            "二维码登录请求无效或已过期",
                            409,
                        )
                    response = {
                        "ok": True,
                        "status": "approved",
                        "challengeId": normalized_id,
                        "requiresPin": False,
                        "pinConfigured": True,
                        "approvalExpiresAt": approved_expires_at,
                        "child": {
                            "id": child["id"],
                            "name": child["name"],
                            "nickname": child.get("nickname") or "",
                        },
                    }

        if terminal_error is not None:
            raise terminal_error
        if response is None:
            raise self._qr_challenge_unavailable_error()
        return response

    def reject_qr_challenge(
        self,
        parent_access_token: str,
        challenge_id: str,
        data: dict,
    ) -> dict:
        context = self.parent_auth_service.authenticate(parent_access_token)
        normalized_id = normalize_qr_challenge_id(challenge_id)
        child_id = str(data.get("childId") or "").strip()
        if not child_id:
            raise ApiError("missing_child_id", "请选择要取消授权的孩子")
        family_id = context["family"]["id"]
        now = now_ms()
        terminal_error: ApiError | None = None
        response: dict | None = None
        with self.repository.transaction() as conn:
            self._assert_parent_can_manage_student_access(conn, context)
            challenge = self.repository.get_qr_challenge_for_update(
                conn,
                challenge_hash=hash_value(normalized_id),
            )
            if challenge is None:
                terminal_error = self._qr_challenge_unavailable_error()
            else:
                status = self._effective_qr_challenge_status(
                    conn,
                    challenge,
                    now=now,
                )
                bound_family_id = str(challenge.get("family_id") or "")
                bound_child_id = str(challenge.get("child_id") or "")
                if status not in {"pending", "approved"} or (
                    bound_family_id and bound_family_id != family_id
                ) or (bound_child_id and bound_child_id != child_id):
                    terminal_error = self._qr_challenge_unavailable_error()
                else:
                    child = self.profile_repository.get_child(
                        conn,
                        family_id=family_id,
                        child_id=child_id,
                    )
                    if child is None:
                        raise ApiError("child_not_found", "孩子资料不存在", 404)
                    rejected = self.repository.reject_qr_challenge(
                        conn,
                        challenge_row_id=challenge["id"],
                        family_id=family_id,
                        child_id=child_id,
                        rejected_by_user_id=context["user"]["id"],
                        now=now,
                    )
                    if rejected is None:
                        terminal_error = self._qr_challenge_unavailable_error()
                    else:
                        response = {
                            "ok": True,
                            "status": "rejected",
                            "challengeId": normalized_id,
                            "rejectedAt": now,
                        }

        if terminal_error is not None:
            raise terminal_error
        if response is None:
            raise self._qr_challenge_unavailable_error()
        return response

    def exchange_qr_challenge(self, data: dict) -> dict:
        challenge_id = normalize_qr_challenge_id(data.get("challengeId"))
        verifier = normalize_qr_verifier(data.get("verifier"))
        now = now_ms()
        terminal_error: AuthError | None = None
        response: dict | None = None
        with self.repository.transaction() as conn:
            challenge = self.repository.get_qr_challenge_for_update(
                conn,
                challenge_hash=hash_value(challenge_id),
            )
            if challenge is None or not hmac.compare_digest(
                str(challenge.get("verifier_hash") or ""),
                hash_value(verifier),
            ):
                raise AuthError(
                    "invalid_student_qr_challenge",
                    "二维码登录请求无效或已过期",
                    401,
                )
            status = self._effective_qr_challenge_status(
                conn,
                challenge,
                now=now,
            )
            if status == "pending":
                return {
                    "ok": True,
                    "status": "pending",
                    "challengeId": challenge_id,
                    "expiresAt": int(challenge["expires_at"]),
                    "pollingIntervalMs": self.qr_polling_interval_ms,
                }
            if status == "expired":
                terminal_error = AuthError(
                    "student_qr_challenge_expired",
                    "二维码登录请求已过期",
                    410,
                )
            elif status == "rejected":
                terminal_error = AuthError(
                    "student_qr_challenge_rejected",
                    "家长未批准这次登录",
                    403,
                )
            elif status == "consumed":
                terminal_error = AuthError(
                    "student_qr_challenge_consumed",
                    "二维码登录请求已使用",
                    409,
                )
            elif status != "approved":
                terminal_error = AuthError(
                    "invalid_student_qr_challenge",
                    "二维码登录请求无效或已过期",
                    401,
                )
            else:
                family_id = str(challenge.get("family_id") or "")
                child_id = str(challenge.get("child_id") or "")
                if not family_id or not child_id:
                    terminal_error = AuthError(
                        "invalid_student_qr_challenge",
                        "二维码登录请求无效或已过期",
                        401,
                    )
                child = (
                    self.profile_repository.get_child(
                        conn,
                        family_id=family_id,
                        child_id=child_id,
                    )
                    if terminal_error is None
                    else None
                )
                if terminal_error is None and child is None:
                    terminal_error = AuthError(
                        "invalid_student_qr_challenge",
                        "二维码登录请求无效或已过期",
                        401,
                    )
                if terminal_error is None:
                    self._assert_formal_learning_access(conn, child)
                    principal = self.repository.get_principal_for_child(
                        conn,
                        family_id=family_id,
                        child_id=child_id,
                        for_update=True,
                    )
                    if principal is None and not all(
                        challenge.get(key)
                        for key in ("pin_hash", "pin_salt", "pin_iterations")
                    ):
                        terminal_error = AuthError(
                            "student_qr_pin_required",
                            "请让家长重新扫码并设置学习 PIN",
                            409,
                        )
                    elif principal is None:
                        principal = self.repository.create_principal(
                            conn,
                            family_id=family_id,
                            child_id=child_id,
                            pin_hash=challenge["pin_hash"],
                            pin_salt=challenge["pin_salt"],
                            pin_iterations=int(challenge["pin_iterations"]),
                            now=now,
                        )
                    elif principal["status"] != "active":
                        terminal_error = AuthError(
                            "student_access_disabled",
                            "学生访问已停用",
                            403,
                        )

                if terminal_error is None:
                    device_token = new_token("msd")
                    session_tokens = self._new_session_tokens(now)
                    device = self.repository.create_trusted_device(
                        conn,
                        principal_id=principal["id"],
                        family_id=family_id,
                        child_id=child_id,
                        device_token_hash=hash_value(device_token),
                        client_device=student_client_device_payload(challenge),
                        expires_at=now + self.device_token_seconds * 1000,
                        now=now,
                    )
                    session = self._create_session(
                        conn,
                        principal_id=principal["id"],
                        device_id=device["id"],
                        tokens=session_tokens,
                        now=now,
                    )
                    if not self.repository.consume_qr_challenge(
                        conn,
                        challenge_row_id=challenge["id"],
                        now=now,
                    ):
                        raise AuthError(
                            "student_qr_challenge_consumed",
                            "二维码登录请求已使用",
                            409,
                        )
                    else:
                        response = self._session_response(
                            conn,
                            principal_id=principal["id"],
                            device=device,
                            session=session,
                            tokens=session_tokens,
                        )
                        response["status"] = "consumed"
                        response["deviceToken"] = device_token

        if terminal_error is not None:
            raise terminal_error
        if response is None:
            raise AuthError(
                "invalid_student_qr_challenge",
                "二维码登录请求无效或已过期",
                401,
            )
        return response

    def unlock(self, data: dict) -> dict:
        device_token = str(data.get("deviceToken") or "").strip()
        if not device_token:
            raise AuthError("missing_student_device_token", "这台设备需要重新配对", 401)
        pin = validate_student_pin(data.get("pin"))
        now = now_ms()
        pending_error: AuthError | None = None
        response: dict | None = None

        with self.repository.transaction() as conn:
            device = self.repository.get_trusted_device_by_token_hash_for_update(
                conn,
                device_token_hash=hash_value(device_token),
            )
            if device is None or device.get("revoked_at") is not None:
                raise AuthError("invalid_student_device", "这台设备需要重新配对", 401)
            if device["status"] != "trusted" or int(device["expires_at"]) < now:
                raise AuthError("student_device_expired", "这台设备的信任已过期，请让家长重新配对", 401)
            locked_until = int(device.get("locked_until") or 0)
            if locked_until > now:
                raise AuthError("student_pin_locked", "PIN 输入次数过多，请稍后再试", 429)

            principal = self.repository.get_principal(
                conn,
                principal_id=device["principal_id"],
                for_update=True,
            )
            if principal is None or principal["status"] != "active":
                raise AuthError("student_access_disabled", "学生访问已停用", 403)
            child = self.profile_repository.get_child(
                conn,
                family_id=principal["family_id"],
                child_id=principal["child_id"],
            )
            if child is None:
                raise AuthError("student_profile_not_found", "学生资料不存在", 404)
            self._assert_formal_learning_access(conn, child)

            if not self._verify_pin(pin, principal):
                previous_attempts = 0 if locked_until else int(device["failed_pin_attempts"] or 0)
                failed_attempts = previous_attempts + 1
                next_locked_until = None
                status_code = 401
                message = "学习 PIN 不正确"
                code = "invalid_student_pin"
                if failed_attempts >= self.pin_max_attempts:
                    next_locked_until = now + self.pin_lock_seconds * 1000
                    status_code = 429
                    message = "PIN 输入次数过多，请稍后再试"
                    code = "student_pin_locked"
                self.repository.record_failed_pin(
                    conn,
                    device_id=device["id"],
                    failed_attempts=failed_attempts,
                    locked_until=next_locked_until,
                    now=now,
                )
                pending_error = AuthError(code, message, status_code)
            else:
                session_tokens = self._new_session_tokens(now)
                self.repository.mark_device_unlocked(conn, device_id=device["id"], now=now)
                self.repository.revoke_device_sessions(
                    conn,
                    device_id=device["id"],
                    revoked_at=now,
                )
                session = self._create_session(
                    conn,
                    principal_id=principal["id"],
                    device_id=device["id"],
                    tokens=session_tokens,
                    now=now,
                )
                device = self.repository.get_trusted_device(conn, device_id=device["id"])
                response = self._session_response(
                    conn,
                    principal_id=principal["id"],
                    device=device,
                    session=session,
                    tokens=session_tokens,
                )

        if pending_error is not None:
            raise pending_error
        if response is None:
            raise AuthError("student_unlock_failed", "暂时无法进入学习空间", 503)
        return response

    def refresh(self, data: dict) -> dict:
        refresh_token = str(data.get("refreshToken") or "").strip()
        if not refresh_token:
            raise AuthError("missing_student_refresh_token", "缺少学生 refresh token", 401)
        now = now_ms()
        session_tokens = self._new_session_tokens(now)

        with self.repository.transaction() as conn:
            session = self.repository.find_session_by_refresh_hash_for_update(
                conn,
                refresh_hash=hash_value(refresh_token),
            )
            if session is None or int(session["refresh_expires_at"]) < now:
                raise AuthError("student_refresh_expired", "学习登录状态已过期", 401)
            principal, device = self._active_principal_and_device(
                conn,
                session=session,
                now=now,
            )
            session = self.repository.rotate_session(
                conn,
                session_id=session["id"],
                access_hash=hash_value(session_tokens["accessToken"]),
                refresh_hash=hash_value(session_tokens["refreshToken"]),
                access_expires_at=session_tokens["accessTokenExpiresAt"],
                refresh_expires_at=session_tokens["refreshTokenExpiresAt"],
                now=now,
            )
            self.repository.touch_device(conn, device_id=device["id"], now=now)
            device = self.repository.get_trusted_device(conn, device_id=device["id"])
            return self._session_response(
                conn,
                principal_id=principal["id"],
                device=device,
                session=session,
                tokens=session_tokens,
            )

    def authenticate(self, access_token: str) -> dict:
        access_token = str(access_token or "").strip()
        if not access_token:
            raise AuthError("missing_student_access_token", "缺少学生 access token", 401)
        now = now_ms()
        with self.repository.transaction() as conn:
            session = self.repository.find_session_by_access_hash(
                conn,
                access_hash=hash_value(access_token),
                for_update=True,
            )
            if session is None or int(session["access_expires_at"]) < now:
                raise AuthError("student_access_expired", "学习登录状态需要刷新", 401)
            principal, device = self._active_principal_and_device(
                conn,
                session=session,
                now=now,
            )
            self.repository.touch_session(conn, session_id=session["id"], now=now)
            self.repository.touch_device(conn, device_id=device["id"], now=now)
            student = self.repository.get_student_context(
                conn,
                principal_id=principal["id"],
            )
            device = self.repository.get_trusted_device(conn, device_id=device["id"])
            return {
                "principal": principal,
                "session": session,
                "student": student_payload(student),
                "device": student_device_payload(device),
            }

    def me(self, access_token: str) -> dict:
        context = self.authenticate(access_token)
        return {
            "ok": True,
            "student": context["student"],
            "device": context["device"],
        }

    def logout(self, access_token: str, data: dict) -> dict:
        context = self.authenticate(access_token)
        refresh_token = str(data.get("refreshToken") or "").strip()
        if refresh_token and hash_value(refresh_token) != context["session"]["refresh_hash"]:
            raise AuthError("invalid_student_refresh_token", "refresh token 与当前会话不匹配", 401)
        with self.repository.transaction() as conn:
            self.repository.revoke_session(
                conn,
                session_id=context["session"]["id"],
                revoked_at=now_ms(),
            )
        return {"ok": True}

    def cleanup_qr_challenges(self) -> dict:
        now = now_ms()
        with self.repository.transaction() as conn:
            result = self._maintain_qr_challenges(conn, now=now)
        return {"ok": True, **result}

    def _maintain_qr_challenges_before_create(self, *, now: int) -> None:
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                with self.repository.transaction() as conn:
                    self._maintain_qr_challenges(conn, now=now)
                return
            except pymysql.MySQLError as exc:
                error_code = exc.args[0] if exc.args else None
                if error_code not in QR_MAINTENANCE_RETRYABLE_DB_CODES:
                    raise
                if attempt + 1 < max_attempts:
                    time.sleep(0.01 * (attempt + 1))
                    continue
                log.warning(
                    "Skipping QR maintenance after retryable MySQL error %s; "
                    "challenge creation will continue in a fresh transaction.",
                    error_code,
                )

    def _maintain_qr_challenges(self, conn, *, now: int) -> dict[str, int]:
        older_than = now - self.qr_retention_seconds * 1000
        # Keep the maintenance lock order aligned with challenge creation:
        # rate bucket rows are touched before challenge rows.
        deleted_bucket_count = self.repository.delete_old_qr_rate_buckets(
            conn,
            older_than=older_than,
        )
        expired_count = self.repository.expire_due_qr_challenges(conn, now=now)
        deleted_count = self.repository.delete_terminal_qr_challenges(
            conn,
            older_than=older_than,
        )
        return {
            "expiredCount": expired_count,
            "deletedCount": deleted_count,
            "deletedBucketCount": deleted_bucket_count,
        }

    def _qr_client_fingerprint_hash(
        self,
        client_device: dict,
        *,
        request_ip_hash: str | None,
    ) -> str:
        supplied = str(client_device.get("fingerprint") or "").strip()
        if supplied:
            source = supplied
        else:
            source = "\x1f".join(
                [
                    "fallback",
                    request_ip_hash or "private-or-proxied",
                    str(client_device.get("type") or ""),
                    str(client_device.get("platform") or ""),
                    str(client_device.get("browserName") or ""),
                    str(client_device.get("osName") or ""),
                    str(client_device.get("model") or ""),
                ]
            )
        return self._scoped_qr_hash("client-fingerprint", source)

    def _qr_request_ip_hash(self, request_ip: str | None) -> str | None:
        text = str(request_ip or "").strip()
        if not text:
            return None
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            return None
        if not address.is_global:
            return None
        return self._scoped_qr_hash("request-ip", address.compressed)

    def _scoped_qr_hash(self, scope: str, value: str) -> str:
        return hmac.new(
            self.pepper,
            f"student-qr:{scope}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _qr_challenge_unavailable_error() -> ApiError:
        return ApiError(
            "student_qr_challenge_unavailable",
            "二维码登录请求无效或已过期",
            404,
        )

    def _effective_qr_challenge_status(
        self,
        conn,
        challenge: DatabaseRow,
        *,
        now: int,
    ) -> str:
        status = str(challenge.get("status") or "")
        expired = status == "pending" and int(challenge["expires_at"]) <= now
        expired = expired or (
            status == "approved"
            and int(challenge.get("approved_expires_at") or 0) <= now
        )
        if expired:
            self.repository.expire_qr_challenge(
                conn,
                challenge_row_id=challenge["id"],
                now=now,
            )
            return "expired"
        return status

    def _assert_formal_learning_access(
        self,
        conn,
        child: DatabaseRow,
        *,
        for_update: bool = False,
    ) -> None:
        checker = self.formal_learning_access_checker
        if checker is not None:
            checker(conn, child)
        assert_formal_student_workspace_open(child)

    def _assert_parent_can_manage_student_access(self, conn, context: dict) -> None:
        member = self.profile_repository.get_family_member_by_user(
            conn,
            family_id=context["family"]["id"],
            user_id=context["user"]["id"],
        )
        if member is None:
            member = self.profile_repository.ensure_owner_member(
                conn,
                family_id=context["family"]["id"],
                user_id=context["user"]["id"],
                name=context["user"].get("displayName") or "家长",
                phone=context["user"].get("phone") or "",
                now=now_ms(),
            )
        role_row = self.profile_repository.get_app_option_item(
            conn,
            catalog_key="family_role",
            item_key=member["role"],
        )
        capabilities = set(role_capabilities_from_option(role_row))
        if not capabilities:
            capabilities = PARENT_CAPABILITY_FALLBACKS.get(member["role"], set())
        if MANAGE_STUDENT_ACCESS_CAPABILITY not in capabilities:
            raise ApiError("permission_denied", "当前身份不能开通学生学习空间", 403)

    def _new_unique_pairing_code(self, conn) -> str:
        for _ in range(12):
            code = "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(8))
            if not self.repository.pairing_code_hash_exists(
                conn,
                code_hash=self._pairing_code_hash(code),
            ):
                return code
        raise ApiError("student_pairing_code_generation_failed", "配对码生成失败，请稍后再试", 503)

    def _pairing_code_hash(self, code: str) -> str:
        return hmac.new(self.pepper, code.encode("ascii"), hashlib.sha256).hexdigest()

    @staticmethod
    def _pairing_code_is_usable(row: DatabaseRow | None, *, now: int) -> bool:
        return bool(
            row
            and row.get("consumed_at") is None
            and row.get("revoked_at") is None
            and int(row["expires_at"]) >= now
        )

    def _new_pin_hash(self, pin: str) -> tuple[str, str]:
        salt = secrets.token_bytes(16)
        digest = self._pin_digest(pin, salt=salt, iterations=self.pin_pbkdf2_iterations)
        return salt.hex(), digest

    def _verify_pin(self, pin: str, principal: DatabaseRow) -> bool:
        try:
            salt = bytes.fromhex(str(principal["pin_salt"]))
            iterations = int(principal["pin_iterations"])
        except (TypeError, ValueError):
            return False
        actual = self._pin_digest(pin, salt=salt, iterations=iterations)
        return hmac.compare_digest(actual, str(principal["pin_hash"]))

    def _pin_digest(self, pin: str, *, salt: bytes, iterations: int) -> str:
        peppered_pin = hmac.new(self.pepper, pin.encode("ascii"), hashlib.sha256).digest()
        return hashlib.pbkdf2_hmac(
            "sha256",
            peppered_pin,
            salt,
            iterations,
        ).hex()

    def _new_session_tokens(self, now: int) -> dict:
        access_token = new_token("msa")
        refresh_token = new_token("msr")
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "accessTokenExpiresAt": now + self.access_token_seconds * 1000,
            "refreshTokenExpiresAt": now + self.refresh_token_seconds * 1000,
        }

    def _create_session(
        self,
        conn,
        *,
        principal_id: str,
        device_id: str,
        tokens: dict,
        now: int,
    ) -> DatabaseRow:
        return self.repository.create_session(
            conn,
            principal_id=principal_id,
            device_id=device_id,
            access_hash=hash_value(tokens["accessToken"]),
            refresh_hash=hash_value(tokens["refreshToken"]),
            access_expires_at=tokens["accessTokenExpiresAt"],
            refresh_expires_at=tokens["refreshTokenExpiresAt"],
            now=now,
        )

    def _active_principal_and_device(
        self,
        conn,
        *,
        session: DatabaseRow,
        now: int,
    ) -> tuple[DatabaseRow, DatabaseRow]:
        principal = self.repository.get_principal(
            conn,
            principal_id=session["principal_id"],
        )
        if principal is None or principal["status"] != "active":
            raise AuthError("student_access_disabled", "学生访问已停用", 403)
        child = self.profile_repository.get_child(
            conn,
            family_id=principal["family_id"],
            child_id=principal["child_id"],
        )
        if child is None:
            raise AuthError("student_profile_not_found", "学生资料不存在", 404)
        self._assert_formal_learning_access(conn, child)
        device = self.repository.get_trusted_device(
            conn,
            device_id=session["device_id"],
        )
        if (
            device is None
            or device["principal_id"] != principal["id"]
            or device["status"] != "trusted"
            or device.get("revoked_at") is not None
            or int(device["expires_at"]) < now
        ):
            raise AuthError("student_device_expired", "这台设备需要重新配对", 401)
        return principal, device

    def _session_response(
        self,
        conn,
        *,
        principal_id: str,
        device: DatabaseRow,
        session: DatabaseRow,
        tokens: dict,
    ) -> dict:
        student = self.repository.get_student_context(conn, principal_id=principal_id)
        if student is None:
            raise AuthError("student_profile_not_found", "学生资料不存在", 404)
        return {
            "ok": True,
            "student": student_payload(student),
            "device": student_device_payload(device),
            "tokens": student_tokens_payload(
                access_token=tokens["accessToken"],
                refresh_token=tokens["refreshToken"],
                access_expires_at=int(session["access_expires_at"]),
                refresh_expires_at=int(session["refresh_expires_at"]),
                access_token_seconds=self.access_token_seconds,
            ),
        }
