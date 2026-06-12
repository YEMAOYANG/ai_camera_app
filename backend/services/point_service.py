from __future__ import annotations

import json
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.points import LEDGER_PARENT_ADJUSTMENT, LEDGER_TYPES
from repositories.point_repository import PointRepository
from repositories.profile_repository import ProfileRepository
from schemas.profile import role_capabilities_from_option
from schemas.points import point_account_payload, point_ledger_payload
from schemas.points import point_reward_unit_payload, point_settings_payload
from services.auth_service import AuthService


POINT_SETTINGS_KEY = "points-rewards"
POINT_UNIT_CATALOG = "point_reward_unit"
POINT_SETTINGS_DEFAULTS = {"stageThreshold": 10, "unit": "flower"}
FALLBACK_ROLE_CAPABILITIES = {
    "admin": {"manage_rewards"},
    "guardian": {"manage_rewards"},
    "viewer": set(),
}


class PointService:
    def __init__(self, database_url: str | Path, *, auth_service: AuthService):
        self.auth_service = auth_service
        database = Database(database_url)
        self.repository = PointRepository(database)
        self.profile_repository = ProfileRepository(database)

    def account(self, access_token: str, *, child_id: str | None = None) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            if child_id:
                self._ensure_child(conn, context["family"]["id"], child_id)
                account = self.repository.get_or_create_account(
                    conn,
                    family_id=context["family"]["id"],
                    child_id=child_id,
                    now=now,
                )
                return {"ok": True, "account": point_account_payload(account)}
            accounts = [
                point_account_payload(row)
                for row in self.repository.list_accounts(conn, family_id=context["family"]["id"])
            ]
            if not accounts:
                children = self.repository.list_children(conn, family_id=context["family"]["id"])
                accounts = [
                    point_account_payload(
                        self.repository.get_or_create_account(
                            conn,
                            family_id=context["family"]["id"],
                            child_id=child["id"],
                            now=now,
                        )
                    )
                    for child in children
                ]
            return {"ok": True, "accounts": accounts}

    def ledger(self, access_token: str, *, child_id: str | None = None) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            if child_id:
                self._ensure_child(conn, context["family"]["id"], child_id)
            rows = self.repository.list_ledger(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
            )
            return {"ok": True, "ledger": [point_ledger_payload(row) for row in rows]}

    def settings(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            unit_options = self._unit_options(conn)
            row = self.repository.get_setting(
                conn,
                family_id=context["family"]["id"],
                key=POINT_SETTINGS_KEY,
            )
            value = self._setting_value(row, unit_options)
            return {
                "ok": True,
                "settings": point_settings_payload(
                    value,
                    unit_options,
                    updated_at=row["updated_at"] if row else None,
                ),
            }

    def update_settings(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        incoming = data.get("value") if isinstance(data.get("value"), dict) else data
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_rewards")
            unit_options = self._unit_options(conn)
            row = self.repository.get_setting(
                conn,
                family_id=context["family"]["id"],
                key=POINT_SETTINGS_KEY,
            )
            current = self._setting_value(row, unit_options)
            threshold = (
                self._positive_int(incoming.get("stageThreshold"), "stageThreshold")
                if "stageThreshold" in incoming
                else current["stageThreshold"]
            )
            if threshold > 99:
                raise ApiError("invalid_stageThreshold", "阶段阈值不能超过 99")
            unit = self._optional_text(incoming, "unit") or current["unit"]
            unit_keys = {item["key"] for item in unit_options}
            if unit not in unit_keys:
                raise ApiError("invalid_point_unit", "积分计量类型不支持")
            value = {"stageThreshold": threshold, "unit": unit}
            saved = self.repository.upsert_setting(
                conn,
                family_id=context["family"]["id"],
                key=POINT_SETTINGS_KEY,
                value=value,
                now=now,
            )
            return {
                "ok": True,
                "settings": point_settings_payload(
                    value,
                    unit_options,
                    updated_at=saved["updated_at"],
                ),
            }

    def adjust(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        child_id = self._required_text(data, "childId", "缺少孩子 ID")
        delta = self._int_value(data.get("delta"), "delta")
        if delta == 0:
            raise ApiError("invalid_delta", "积分调整不能为 0")
        note = self._optional_text(data, "note")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._ensure_child(conn, context["family"]["id"], child_id)
            ledger = self.repository.adjust_points(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                delta=delta,
                ledger_type=LEDGER_PARENT_ADJUSTMENT,
                source_type="parent_adjustment",
                source_id=context["user"]["id"],
                note=note,
                now=now,
            )
            account = self.repository.get_or_create_account(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                now=now,
            )
            return {
                "ok": True,
                "account": point_account_payload(account),
                "ledgerEntry": point_ledger_payload(ledger),
            }

    def acknowledge_stage_notice(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        child_id = self._required_text(data, "childId", "缺少孩子 ID")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_rewards")
            self._ensure_child(conn, context["family"]["id"], child_id)
            account = self.repository.acknowledge_stage_notice(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                now=now,
            )
            return {"ok": True, "account": point_account_payload(account)}

    def apply_delta(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        delta: int,
        ledger_type: str,
        source_type: str | None,
        source_id: str | None,
        note: str | None,
        now: int,
    ):
        if ledger_type not in LEDGER_TYPES:
            raise ApiError("invalid_ledger_type", "积分流水类型不支持")
        return self.repository.adjust_points(
            conn,
            family_id=family_id,
            child_id=child_id,
            delta=delta,
            ledger_type=ledger_type,
            source_type=source_type,
            source_id=source_id,
            note=note,
            now=now,
        )

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _ensure_child(self, conn, family_id: str, child_id: str) -> None:
        if not self.repository.child_exists(conn, family_id=family_id, child_id=child_id):
            raise ApiError("child_not_found", "孩子资料不存在", 404)

    def _unit_options(self, conn) -> list[dict]:
        rows = self.repository.list_app_option_items(
            conn,
            catalog_key=POINT_UNIT_CATALOG,
        )
        options = [point_reward_unit_payload(row) for row in rows]
        if not options:
            raise ApiError("point_unit_options_missing", "积分计量类型配置不可用", 503)
        return options

    def _setting_value(self, row, unit_options: list[dict]) -> dict:
        value = dict(POINT_SETTINGS_DEFAULTS)
        if row is not None:
            try:
                stored = json.loads(row["value"])
            except (TypeError, ValueError, json.JSONDecodeError):
                stored = {}
            if isinstance(stored, dict):
                if "stageThreshold" in stored:
                    try:
                        value["stageThreshold"] = int(stored["stageThreshold"])
                    except (TypeError, ValueError):
                        value["stageThreshold"] = POINT_SETTINGS_DEFAULTS["stageThreshold"]
                if "unit" in stored:
                    value["unit"] = str(stored["unit"]).strip()
        value["stageThreshold"] = int(value["stageThreshold"])
        if value["stageThreshold"] <= 0 or value["stageThreshold"] > 99:
            value["stageThreshold"] = POINT_SETTINGS_DEFAULTS["stageThreshold"]
        unit_keys = {item["key"] for item in unit_options}
        if value["unit"] not in unit_keys:
            value["unit"] = unit_options[0]["key"]
        return value

    def _assert_capability(self, conn, context: dict, capability: str) -> None:
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
        role = member["role"]
        row = self.profile_repository.get_app_option_item(
            conn,
            catalog_key="family_role",
            item_key=role,
        )
        capabilities = set(role_capabilities_from_option(row)) or FALLBACK_ROLE_CAPABILITIES.get(
            role,
            set(),
        )
        if capability not in capabilities:
            raise ApiError("permission_denied", "当前身份不能进行此操作", 403)

    def _required_text(self, data: dict, key: str, message: str) -> str:
        value = self._optional_text(data, key)
        if not value:
            raise ApiError(f"missing_{key}", message)
        return value

    def _optional_text(self, data: dict, key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _int_value(self, value, key: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ApiError(f"invalid_{key}", "积分必须是整数") from exc

    def _positive_int(self, value, key: str) -> int:
        result = self._int_value(value, key)
        if result <= 0:
            raise ApiError(f"invalid_{key}", "请输入大于 0 的积分数量")
        return result
