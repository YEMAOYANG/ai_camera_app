from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.care import (
    CARE_SCENARIOS,
    DEFAULT_DAY_TYPES,
    DEFAULT_FALLBACK_TEMPLATES,
    DAY_TYPES,
    ROUTINE_WINDOW_TYPES,
)
from repositories.care_repository import CareRepository
from schemas.care import (
    capability_payload,
    parent_review_event_payload,
    routine_window_payload,
)
from services.auth_service import AuthService
from services.care_defaults import ensure_default_capability_configs, ensure_default_routine_windows


class CareConfigService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
    ):
        self.repository = CareRepository(Database(database_url))
        self.auth_service = auth_service

    def list_capabilities(self, access_token: str, args) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        child_id = _optional_text(args.get("childId") if args else None)
        device_id = _optional_text(args.get("deviceId") if args else None)
        with self.repository.transaction() as conn:
            resolved_child_id = self._resolve_child_id(conn, family_id, child_id)
            if not resolved_child_id:
                return {"ok": True, "capabilities": []}
            self._ensure_defaults(conn, family_id=family_id, child_id=resolved_child_id, device_id=device_id)
            rows = self.repository.list_capability_configs(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
                device_id=device_id,
            )
        return {"ok": True, "childId": resolved_child_id, "capabilities": [capability_payload(row) for row in rows]}

    def update_capabilities(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        raw_capabilities = data.get("capabilities")
        if isinstance(raw_capabilities, list):
            updates = raw_capabilities
        else:
            updates = [data]
        child_id = _optional_text(data.get("childId"))
        device_id = _optional_text(data.get("deviceId"))
        now = now_ms()
        with self.repository.transaction() as conn:
            resolved_child_id = self._resolve_child_id(conn, family_id, child_id)
            if not resolved_child_id:
                raise ApiError("child_required", "请先完善孩子资料。")
            self._ensure_defaults(conn, family_id=family_id, child_id=resolved_child_id, device_id=device_id)
            for update in updates:
                if not isinstance(update, dict):
                    continue
                scenario = _scenario(update.get("scenario"))
                existing = self.repository.get_capability_config(
                    conn,
                    family_id=family_id,
                    child_id=resolved_child_id,
                    device_id=device_id,
                    scenario=scenario,
                )
                if existing is None:
                    continue
                payload = capability_payload(existing)
                merged = {**payload, **update}
                self.repository.upsert_capability_config(
                    conn,
                    family_id=family_id,
                    child_id=resolved_child_id,
                    device_id=device_id,
                    scenario=scenario,
                    enabled=_bool(merged.get("enabled")),
                    day_types=_json_text(_valid_day_types(merged.get("dayTypes"))),
                    time_windows=_json_text(_valid_time_windows(merged.get("timeWindows"))),
                    min_observation_seconds=_positive_int(merged.get("minObservationSeconds"), 20),
                    confidence_threshold=_threshold(merged.get("observationThreshold")),
                    cooldown_seconds=_positive_int(merged.get("cooldownSeconds"), 900),
                    daily_limit=_positive_int(merged.get("dailyLimit"), 4),
                    parent_notify_threshold=_positive_int(merged.get("parentNotifyThreshold"), 3),
                    allow_speaker=_bool(merged.get("allowSpeaker")),
                    record_only=_bool(merged.get("recordOnly")),
                    prompt_id=str(existing.get("prompt_id") or f"reminder.{scenario}"),
                    prompt_version=str(existing.get("prompt_version") or "v1"),
                    fallback_templates=str(existing.get("fallback_templates") or _json_text(_valid_fallbacks(None, scenario))),
                    now=now,
                )
            rows = self.repository.list_capability_configs(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
                device_id=device_id,
            )
        return {"ok": True, "childId": resolved_child_id, "capabilities": [capability_payload(row) for row in rows]}

    def list_routine_windows(self, access_token: str, args) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        child_id = _optional_text(args.get("childId") if args else None)
        day_type = _optional_text(args.get("dayType") if args else None)
        if day_type and day_type not in DAY_TYPES:
            raise ApiError("invalid_day_type", "作息类型暂不支持。")
        with self.repository.transaction() as conn:
            resolved_child_id = self._resolve_child_id(conn, family_id, child_id)
            if not resolved_child_id:
                return {"ok": True, "windows": []}
            self._ensure_routine_defaults(conn, family_id=family_id, child_id=resolved_child_id)
            rows = self.repository.list_routine_windows(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
                day_type=day_type,
            )
        return {"ok": True, "childId": resolved_child_id, "windows": [routine_window_payload(row) for row in rows]}

    def replace_routine_windows(self, access_token: str, data: dict, args=None) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        raw_windows = data.get("windows")
        if not isinstance(raw_windows, list):
            raise ApiError("invalid_routine_windows", "请提供作息时间段。")
        child_id = _optional_text(data.get("childId"))
        day_type_scope = _optional_text((args or {}).get("dayType") if args else None) or _optional_text(data.get("dayType"))
        if day_type_scope and day_type_scope not in DAY_TYPES:
            raise ApiError("invalid_day_type", "作息类型暂不支持。")
        now = now_ms()
        with self.repository.transaction() as conn:
            resolved_child_id = self._resolve_child_id(conn, family_id, child_id)
            if not resolved_child_id:
                raise ApiError("child_required", "请先完善孩子资料。")
            self.repository.delete_routine_windows_for_child(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
                day_type=day_type_scope,
            )
            for item in raw_windows:
                if not isinstance(item, dict):
                    continue
                item_day_type = _day_type(item.get("dayType") or day_type_scope)
                if day_type_scope and item_day_type != day_type_scope:
                    raise ApiError("routine_window_scope_mismatch", "作息类型不一致。")
                self.repository.upsert_routine_window(
                    conn,
                    family_id=family_id,
                    child_id=resolved_child_id,
                    day_type=item_day_type,
                    window_type=_window_type(item.get("windowType")),
                    start_time=_time_text(item.get("startTime")),
                    end_time=_time_text(item.get("endTime")),
                    enabled=_bool(item.get("enabled", True)),
                    timezone=str(item.get("timezone") or "Asia/Shanghai")[:64],
                    now=now,
                )
            rows = self.repository.list_routine_windows(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
                day_type=day_type_scope,
            )
        return {"ok": True, "childId": resolved_child_id, "windows": [routine_window_payload(row) for row in rows]}

    def acknowledge_parent_review(self, access_token: str, review_id: str) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        review_id = str(review_id or "").strip()
        if not review_id:
            raise ApiError("review_item_id_required", "待办 id 不能为空。", 400)
        resolved_by = str(context.get("user", {}).get("id") or "")
        now = now_ms()
        with self.repository.transaction() as conn:
            row = self.repository.get_review_item(
                conn,
                review_id=review_id,
                family_id=family_id,
            )
            if row is None:
                raise ApiError("review_item_not_found", "待办不存在。", 404)
            if str(row.get("status") or "") != "pending":
                raise ApiError("review_item_already_resolved", "这条已经处理过了。", 409)
            updated = self.repository.resolve_parent_review_item(
                conn,
                review_id=review_id,
                family_id=family_id,
                resolved_by=resolved_by,
                now=now,
            )
        if updated is None:
            raise ApiError("review_item_not_found", "待办不存在。", 404)
        return {"ok": True, "reviewItem": parent_review_event_payload(updated)}

    def summary(self, access_token: str, args) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        child_id = _optional_text(args.get("childId") if args else None)
        with self.repository.transaction() as conn:
            resolved_child_id = self._resolve_child_id(conn, family_id, child_id)
            if not resolved_child_id:
                return {"ok": True, "summary": {"currentStage": "资料待完善", "nextReminder": None}}
            self._ensure_defaults(conn, family_id=family_id, child_id=resolved_child_id, device_id=None)
            self._ensure_routine_defaults(conn, family_id=family_id, child_id=resolved_child_id)
            capabilities = self.repository.list_capability_configs(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
            )
            windows = self.repository.list_routine_windows(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
                day_type=_today_day_type(),
            )
            reviews = self.repository.list_pending_parent_review_events(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
                limit=5,
            )
        current_stage = _current_stage(windows)
        return {
            "ok": True,
            "summary": {
                "childId": resolved_child_id,
                "dayType": _today_day_type(),
                "currentStage": current_stage,
                "nextReminder": _next_window(windows),
                "todayReminderCount": 0,
                "capabilities": [capability_payload(row) for row in capabilities],
                "needsParentReview": [parent_review_event_payload(row) for row in reviews],
                "observationSuggestion": "设备在线时会按作息观察。",
            },
        }

    def _ensure_defaults(self, conn, *, family_id: str, child_id: str, device_id: str | None) -> None:
        ensure_default_capability_configs(
            self.repository,
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
        )

    def _ensure_routine_defaults(self, conn, *, family_id: str, child_id: str) -> None:
        ensure_default_routine_windows(
            self.repository,
            conn,
            family_id=family_id,
            child_id=child_id,
        )

    def _resolve_child_id(self, conn, family_id: str, child_id: str | None) -> str:
        if child_id:
            if not self.repository.child_exists(conn, family_id=family_id, child_id=child_id):
                raise ApiError("child_not_found", "孩子资料不存在。", 404)
            return child_id
        children = self.repository.list_children(conn, family_id=family_id)
        return str(children[0]["id"]) if children else ""


def _scenario(value: object) -> str:
    scenario = str(value or "").strip()
    if scenario not in CARE_SCENARIOS:
        raise ApiError("invalid_care_scenario", "看护能力暂不支持。")
    return scenario


def _day_type(value: object) -> str:
    day_type = str(value or "").strip()
    if day_type not in DAY_TYPES:
        raise ApiError("invalid_day_type", "作息类型暂不支持。")
    return day_type


def _window_type(value: object) -> str:
    window_type = str(value or "").strip()
    if window_type not in ROUTINE_WINDOW_TYPES:
        raise ApiError("invalid_window_type", "作息时间段暂不支持。")
    return window_type


def _time_text(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 5 and text[2] == ":":
        hour, minute = text.split(":", 1)
        if hour.isdigit() and minute.isdigit() and 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
            return text
    raise ApiError("invalid_time", "请使用正确的时间。")


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _valid_day_types(value: object) -> list[str]:
    if not isinstance(value, list):
        return DEFAULT_DAY_TYPES
    result = [str(item) for item in value if str(item) in DAY_TYPES]
    return result or DEFAULT_DAY_TYPES


def _valid_time_windows(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item) in ROUTINE_WINDOW_TYPES]


def _valid_fallbacks(value: object, scenario: str) -> list[str]:
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item).strip()]
        if result:
            return result[:8]
    return DEFAULT_FALLBACK_TEMPLATES.get(scenario, DEFAULT_FALLBACK_TEMPLATES["transition"])


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _threshold(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.72
    return max(0.0, min(parsed, 1.0))


def _today_day_type() -> str:
    return "weekend" if datetime.now().weekday() >= 5 else "school_day"


VISIBLE_ROUTINE_WINDOW_TYPES = {"wake_up", "breakfast", "lunch", "nap", "dinner", "bedtime"}


def _current_stage(windows: list[dict]) -> str:
    now = datetime.now().strftime("%H:%M")
    for row in windows:
        if row["window_type"] not in VISIBLE_ROUTINE_WINDOW_TYPES:
            continue
        if row["enabled"] and row["start_time"] <= now <= row["end_time"]:
            return _stage_label(row["window_type"])
    return "安静观察"


def _next_window(windows: list[dict]) -> dict | None:
    now = datetime.now().strftime("%H:%M")
    enabled = [
        row
        for row in windows
        if row["enabled"] and row["window_type"] in VISIBLE_ROUTINE_WINDOW_TYPES
    ]
    for row in enabled:
        if row["start_time"] >= now:
            return {
                "windowType": row["window_type"],
                "label": _stage_label(row["window_type"]),
                "startTime": row["start_time"],
                "endTime": row["end_time"],
            }
    return None


def _stage_label(window_type: str) -> str:
    return {
        "wake_up": "起床",
        "breakfast": "早餐",
        "lunch": "午餐",
        "nap": "午睡",
        "dinner": "晚餐",
        "bedtime": "睡前",
        "toy_cleanup": "收纳",
        "posture": "坐姿",
        "transition": "转场",
    }.get(window_type, "日常作息")
