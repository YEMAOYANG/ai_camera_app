from __future__ import annotations

from pathlib import Path

from core.database import SQLiteDatabase
from core.errors import ApiError
from core.security import now_ms
from models.points import LEDGER_PARENT_ADJUSTMENT, LEDGER_TYPES
from repositories.point_repository import PointRepository
from schemas.points import point_account_payload, point_ledger_payload
from services.auth_service import AuthService


class PointService:
    def __init__(self, db_path: str | Path, *, auth_service: AuthService):
        self.auth_service = auth_service
        self.repository = PointRepository(SQLiteDatabase(db_path))

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
