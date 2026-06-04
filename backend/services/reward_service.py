from __future__ import annotations

import uuid
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.points import LEDGER_REDEMPTION_CANCELLED, LEDGER_REDEMPTION_SPENT
from models.rewards import REDEMPTION_CANCELLED, REDEMPTION_FULFILLED, REDEMPTION_REDEEMED, REWARD_ACTIVE
from repositories.point_repository import PointRepository
from repositories.reward_repository import RewardRepository
from schemas.points import point_account_payload, point_ledger_payload
from schemas.rewards import redemption_payload, reward_item_payload, validate_reward_status
from services.auth_service import AuthService
from services.point_service import PointService


class RewardService:
    def __init__(self, database_url: str | Path, *, auth_service: AuthService):
        self.auth_service = auth_service
        database = Database(database_url)
        self.repository = RewardRepository(database)
        self.point_repository = PointRepository(database)
        self.point_service = PointService(database_url, auth_service=auth_service)

    def list_items(self, access_token: str, query: dict) -> dict:
        context = self._auth_context(access_token)
        child_id = self._optional_text(query, "childId")
        status = self._optional_text(query, "status")
        if status:
            validate_reward_status(status)
        with self.repository.transaction() as conn:
            if child_id:
                self._ensure_child(conn, context["family"]["id"], child_id)
            rows = self.repository.list_items(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                status=status,
            )
            return {"ok": True, "items": [reward_item_payload(row) for row in rows]}

    def get_item(self, access_token: str, item_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            item = self._item_or_error(conn, context["family"]["id"], item_id)
            return {"ok": True, "item": reward_item_payload(item)}

    def create_item(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        child_id = self._required_text(data, "childId", "缺少孩子 ID")
        title = self._required_text(data, "title", "请输入奖励名称")
        points_cost = self._positive_int(data.get("pointsCost"), "pointsCost")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._ensure_child(conn, context["family"]["id"], child_id)
            item = self.repository.create_item(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                title=title,
                description=self._optional_text(data, "description"),
                points_cost=points_cost,
                category=self._optional_text(data, "category"),
                icon=self._optional_text(data, "icon"),
                created_by=context["user"]["id"],
                now=now,
            )
            return {"ok": True, "item": reward_item_payload(item)}

    def update_item(self, access_token: str, item_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        fields: dict = {}
        mapping = {
            "title": "title",
            "description": "description",
            "pointsCost": "points_cost",
            "category": "category",
            "status": "status",
            "icon": "icon",
        }
        for key, column in mapping.items():
            if key not in data:
                continue
            if key == "pointsCost":
                fields[column] = self._positive_int(data[key], key)
            elif key == "status":
                fields[column] = validate_reward_status(str(data[key]))
            else:
                fields[column] = self._optional_text(data, key)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._item_or_error(conn, context["family"]["id"], item_id)
            item = self.repository.update_item(
                conn,
                family_id=context["family"]["id"],
                item_id=item_id,
                fields=fields,
                now=now,
            )
            return {"ok": True, "item": reward_item_payload(item)}

    def delete_item(self, access_token: str, item_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._item_or_error(conn, context["family"]["id"], item_id)
            item = self.repository.update_item(
                conn,
                family_id=context["family"]["id"],
                item_id=item_id,
                fields={"status": "archived"},
                now=now,
            )
            return {"ok": True, "item": reward_item_payload(item)}

    def list_redemptions(self, access_token: str, query: dict) -> dict:
        context = self._auth_context(access_token)
        child_id = self._optional_text(query, "childId")
        status = self._optional_text(query, "status")
        with self.repository.transaction() as conn:
            if child_id:
                self._ensure_child(conn, context["family"]["id"], child_id)
            rows = self.repository.list_redemptions(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                status=status,
            )
            return {"ok": True, "redemptions": [redemption_payload(row) for row in rows]}

    def create_redemption(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        reward_item_id = self._required_text(data, "rewardItemId", "缺少奖励 ID")
        now = now_ms()
        with self.repository.transaction() as conn:
            item = self._item_or_error(conn, context["family"]["id"], reward_item_id)
            if item["status"] != REWARD_ACTIVE:
                raise ApiError("reward_unavailable", "奖励当前不可兑换")
            redemption_id = f"redemption_{uuid.uuid4().hex}"
            ledger = self.point_service.apply_delta(
                conn,
                family_id=context["family"]["id"],
                child_id=item["child_id"],
                delta=-item["points_cost"],
                ledger_type=LEDGER_REDEMPTION_SPENT,
                source_type="redemption",
                source_id=redemption_id,
                note=f"兑换奖励：{item['title']}",
                now=now,
            )
            redemption = self.repository.create_redemption(
                conn,
                redemption_id=redemption_id,
                family_id=context["family"]["id"],
                child_id=item["child_id"],
                reward_item_id=item["id"],
                reward_title=item["title"],
                points_cost=item["points_cost"],
                requested_by=context["user"]["id"],
                now=now,
            )
            account = self.point_repository.get_or_create_account(
                conn,
                family_id=context["family"]["id"],
                child_id=item["child_id"],
                now=now,
            )
            return {
                "ok": True,
                "redemption": redemption_payload(redemption),
                "account": point_account_payload(account),
                "ledgerEntry": point_ledger_payload(ledger),
            }

    def fulfill_redemption(self, access_token: str, redemption_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            redemption = self._redemption_or_error(conn, context["family"]["id"], redemption_id)
            if redemption["status"] == REDEMPTION_CANCELLED:
                raise ApiError("redemption_cancelled", "已取消的兑换不能兑现")
            if redemption["status"] != REDEMPTION_FULFILLED:
                redemption = self.repository.fulfill_redemption(
                    conn,
                    family_id=context["family"]["id"],
                    redemption_id=redemption_id,
                    fulfilled_by=context["user"]["id"],
                    now=now,
                )
            return {"ok": True, "redemption": redemption_payload(redemption)}

    def cancel_redemption(self, access_token: str, redemption_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            redemption = self._redemption_or_error(conn, context["family"]["id"], redemption_id)
            if redemption["status"] == REDEMPTION_FULFILLED:
                raise ApiError("redemption_fulfilled", "已兑现的兑换不能取消")
            ledger_payload = None
            if redemption["status"] != REDEMPTION_CANCELLED:
                ledger = self.point_service.apply_delta(
                    conn,
                    family_id=context["family"]["id"],
                    child_id=redemption["child_id"],
                    delta=redemption["points_cost"],
                    ledger_type=LEDGER_REDEMPTION_CANCELLED,
                    source_type="redemption",
                    source_id=redemption["id"],
                    note=f"取消兑换返还：{redemption['reward_title']}",
                    now=now,
                )
                ledger_payload = point_ledger_payload(ledger)
                redemption = self.repository.cancel_redemption(
                    conn,
                    family_id=context["family"]["id"],
                    redemption_id=redemption_id,
                    cancelled_by=context["user"]["id"],
                    now=now,
                )
            account = self.point_repository.get_or_create_account(
                conn,
                family_id=context["family"]["id"],
                child_id=redemption["child_id"],
                now=now,
            )
            payload = {
                "ok": True,
                "redemption": redemption_payload(redemption),
                "account": point_account_payload(account),
            }
            if ledger_payload:
                payload["ledgerEntry"] = ledger_payload
            return payload

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _ensure_child(self, conn, family_id: str, child_id: str) -> None:
        if not self.repository.child_exists(conn, family_id=family_id, child_id=child_id):
            raise ApiError("child_not_found", "孩子资料不存在", 404)

    def _item_or_error(self, conn, family_id: str, item_id: str):
        item = self.repository.get_item(conn, family_id=family_id, item_id=item_id)
        if item is None:
            raise ApiError("reward_not_found", "奖励不存在", 404)
        return item

    def _redemption_or_error(self, conn, family_id: str, redemption_id: str):
        redemption = self.repository.get_redemption(
            conn,
            family_id=family_id,
            redemption_id=redemption_id,
        )
        if redemption is None:
            raise ApiError("redemption_not_found", "兑换记录不存在", 404)
        return redemption

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

    def _positive_int(self, value, key: str) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ApiError(f"invalid_{key}", "数值必须是整数") from exc
        if result <= 0:
            raise ApiError(f"invalid_{key}", "数值必须大于 0")
        return result
