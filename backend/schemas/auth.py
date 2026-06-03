from __future__ import annotations

import sqlite3

from flask import Request

from core.errors import AuthError
from models.auth import AuthSession


PHONE_REPR_ERROR = "请输入正确的 11 位手机号"


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) != 11 or digits[0] != "1" or digits[1] not in "3456789":
        raise AuthError("invalid_phone", PHONE_REPR_ERROR)
    return digits


def json_body(request: Request) -> dict:
    return request.get_json(silent=True) or {}


def bearer_token(request: Request) -> str:
    value = request.headers.get("Authorization", "")
    prefix = "Bearer "
    return value[len(prefix) :].strip() if value.startswith(prefix) else ""


def user_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "phone": row["phone"],
        "familyId": row["family_id"],
        "displayName": row["display_name"],
    }


def family_payload(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "name": row["name"]}


def session_payload(
    *,
    user: dict,
    family: dict,
    session: AuthSession,
    access_token_seconds: int,
) -> dict:
    return {
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
