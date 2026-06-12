from __future__ import annotations

from core.database import DatabaseRow

from flask import Request

from core.errors import AuthError
from models.auth import AuthSession


PHONE_REPR_ERROR = "请输入正确的 11 位手机号"


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    elif len(digits) == 15 and digits.startswith("0086"):
        digits = digits[4:]
    if len(digits) != 11 or digits[0] != "1" or digits[1] not in "3456789":
        raise AuthError("invalid_phone", PHONE_REPR_ERROR)
    return digits


def json_body(request: Request) -> dict:
    return request.get_json(silent=True) or {}


def bearer_token(request: Request) -> str:
    value = request.headers.get("Authorization", "")
    prefix = "Bearer "
    return value[len(prefix) :].strip() if value.startswith(prefix) else ""


def client_device_payload(request: Request, data: dict | None = None) -> dict:
    body_device = (data or {}).get("clientDevice") if isinstance(data, dict) else None
    body = body_device if isinstance(body_device, dict) else {}
    mapping = {
        "label": "X-Mira-Device-Label",
        "type": "X-Mira-Device-Type",
        "platform": "X-Mira-Device-Platform",
        "model": "X-Mira-Device-Model",
        "hardware": "X-Mira-Device-Hardware",
        "osVersion": "X-Mira-OS-Version",
        "appVersion": "X-Mira-App-Version",
    }
    payload: dict[str, str] = {}
    for key, header in mapping.items():
        value = request.headers.get(header) or body.get(key)
        value = str(value or "").strip()
        if value:
            payload[key] = value
    return payload


def user_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "phone": row["phone"],
        "familyId": row["family_id"],
        "displayName": row["display_name"],
    }


def family_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "familyCode": row.get("family_code") or "",
    }


def session_payload(
    *,
    user: dict,
    family: dict,
    session: AuthSession,
    access_token_seconds: int,
    pending_joins: list[dict] | None = None,
) -> dict:
    payload = {
        "ok": True,
        "user": user,
        "family": family,
        "tokens": {
            "accessToken": session.access_token,
            "refreshToken": session.refresh_token,
            "accessTokenExpiresAt": session.access_expires_at,
            "refreshTokenExpiresAt": session.refresh_expires_at,
            "expiresInSeconds": access_token_seconds,
        },
    }
    if pending_joins:
        payload["pendingJoins"] = pending_joins
    return payload
