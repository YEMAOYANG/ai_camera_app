from __future__ import annotations

import re

from core.database import DatabaseRow
from core.errors import ApiError


PAIRING_CODE_PATTERN = re.compile(r"^[A-HJ-NP-Z2-9]{8}$")
PIN_PATTERN = re.compile(r"^\d{4}$")
QR_CHALLENGE_ID_PATTERN = re.compile(r"^msc_[A-Za-z0-9_-]{40,96}$")
QR_VERIFIER_PATTERN = re.compile(r"^msv_[A-Za-z0-9_-]{40,96}$")
CLIENT_FINGERPRINT_PATTERN = re.compile(r"^[A-Za-z0-9._~:-]{16,128}$")
DEVICE_METADATA_PATTERN = re.compile(r"^[\w .()+/_-]*$", re.UNICODE)


def normalize_pairing_code(value: object) -> str:
    code = "".join(
        character
        for character in str(value or "").strip().upper()
        if character not in {" ", "-"}
    )
    if not PAIRING_CODE_PATTERN.fullmatch(code):
        raise ApiError("invalid_pairing_code", "配对码无效或已过期", 401)
    return code


def validate_student_pin(value: object) -> str:
    pin = str(value or "").strip()
    if not PIN_PATTERN.fullmatch(pin):
        raise ApiError("invalid_student_pin_format", "请输入4位数字学习 PIN")
    return pin


def normalize_qr_challenge_id(value: object) -> str:
    challenge_id = str(value or "").strip()
    if not QR_CHALLENGE_ID_PATTERN.fullmatch(challenge_id):
        raise ApiError(
            "invalid_student_qr_challenge",
            "二维码登录请求无效或已过期",
            401,
        )
    return challenge_id


def normalize_qr_verifier(value: object) -> str:
    verifier = str(value or "").strip()
    if not QR_VERIFIER_PATTERN.fullmatch(verifier):
        raise ApiError(
            "invalid_student_qr_challenge",
            "二维码登录请求无效或已过期",
            401,
        )
    return verifier


def normalize_student_client_device(value: object) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    platform = _clean(raw.get("platform")) or "web"
    device_type = _clean(raw.get("type")) or "browser"
    label = _clean(raw.get("label")) or _default_device_label(platform, device_type)
    fingerprint = _clean(raw.get("fingerprint"))
    if fingerprint and not CLIENT_FINGERPRINT_PATTERN.fullmatch(fingerprint):
        raise ApiError(
            "invalid_student_client_fingerprint",
            "浏览器标识格式不正确，请刷新页面重试",
        )
    return {
        "label": label[:80],
        "type": device_type[:40],
        "model": _clean(raw.get("model"))[:80],
        "hardware": _clean(raw.get("hardware"))[:80],
        "platform": platform[:40],
        "osVersion": _clean(raw.get("osVersion"))[:40],
        "browserName": _device_metadata(raw.get("browserName"), "浏览器名称"),
        "osName": _device_metadata(raw.get("osName"), "系统名称"),
        "appVersion": _clean(raw.get("appVersion"))[:40],
        "fingerprint": fingerprint,
    }


def student_client_device_payload(row: DatabaseRow) -> dict[str, str]:
    return {
        "label": str(row.get("device_label") or "学习网页"),
        "type": str(row.get("device_type") or "browser"),
        "model": str(row.get("device_model") or ""),
        "hardware": str(row.get("device_hardware") or ""),
        "platform": str(row.get("platform") or "web"),
        "osVersion": str(row.get("os_version") or ""),
        "browserName": str(row.get("browser_name") or ""),
        "osName": str(row.get("os_name") or ""),
        "appVersion": str(row.get("app_version") or ""),
    }


def student_payload(row: DatabaseRow) -> dict:
    nickname = str(row.get("child_nickname") or "").strip()
    name = str(row.get("child_name") or "").strip()
    return {
        "id": row["id"],
        "childId": row["child_id"],
        "displayName": nickname or name or "同学",
        "name": name,
        "nickname": nickname,
        "gradeCode": str(row.get("child_grade_code") or ""),
        "educationStage": str(row.get("child_education_stage") or ""),
        "status": row["status"],
    }


def student_device_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "label": row["device_label"],
        "type": row["device_type"],
        "model": row.get("device_model") or "",
        "hardware": row.get("device_hardware") or "",
        "platform": row["platform"],
        "osVersion": row.get("os_version") or "",
        "appVersion": row.get("app_version") or "",
        "status": row["status"],
        "trustedUntil": row["expires_at"],
        "lastActiveAt": row["last_active_at"],
    }


def parent_student_authorizations_payload(
    rows: list[DatabaseRow],
    *,
    now: int,
) -> list[dict]:
    """Serialize parent-visible device/session metadata without auth secrets."""

    authorizations: list[dict] = []
    by_device_id: dict[str, dict] = {}
    for row in rows:
        device_id = str(row["id"])
        authorization = by_device_id.get(device_id)
        if authorization is None:
            device_status = "active"
            if row.get("revoked_at") is not None or row.get("status") != "trusted":
                device_status = "revoked"
            elif int(row.get("expires_at") or 0) <= now:
                device_status = "expired"
            display_name = str(row.get("device_label") or "").strip()
            if not display_name:
                display_name = _default_device_label(
                    str(row.get("platform") or "web"),
                    str(row.get("device_type") or "browser"),
                )
            authorization = {
                "id": device_id,
                "displayName": display_name,
                "deviceType": str(row.get("device_type") or "browser"),
                "platform": str(row.get("platform") or "web"),
                "status": device_status,
                "trustedUntil": int(row.get("expires_at") or 0),
                "lastUsedAt": int(row.get("last_active_at") or 0),
                "createdAt": int(row.get("created_at") or 0),
                "sessions": [],
            }
            by_device_id[device_id] = authorization
            authorizations.append(authorization)

        session_id = str(row.get("session_id") or "").strip()
        if not session_id:
            continue
        refresh_expires_at = int(row.get("session_refresh_expires_at") or 0)
        authorization["sessions"].append(
            {
                "id": session_id,
                "status": "active" if refresh_expires_at > now else "expired",
                "lastUsedAt": int(row.get("session_last_active_at") or 0),
                "createdAt": int(row.get("session_created_at") or 0),
            }
        )
    return authorizations


def student_tokens_payload(
    *,
    access_token: str,
    refresh_token: str,
    access_expires_at: int,
    refresh_expires_at: int,
    access_token_seconds: int,
) -> dict:
    return {
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "accessTokenExpiresAt": access_expires_at,
        "refreshTokenExpiresAt": refresh_expires_at,
        "expiresInSeconds": access_token_seconds,
    }


def _clean(value: object) -> str:
    return str(value or "").strip()


def _device_metadata(value: object, field_label: str) -> str:
    text = _clean(value)
    if len(text) > 64 or not DEVICE_METADATA_PATTERN.fullmatch(text):
        raise ApiError(
            "invalid_student_client_device",
            f"{field_label}格式不正确",
        )
    return text


def _default_device_label(platform: str, device_type: str) -> str:
    combined = f"{platform} {device_type}".lower()
    if "ipad" in combined:
        return "学习 iPad"
    if "android" in combined and "tablet" in combined:
        return "学习平板"
    if "mac" in combined:
        return "Mac 浏览器"
    if "windows" in combined:
        return "Windows 浏览器"
    return "学习网页"
