from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from core.database import Database
from core.security import now_ms
from models.care import (
    CARE_SCENARIO_BEDTIME,
    CARE_SCENARIO_MEAL_START,
    CARE_SCENARIO_NAP_TIME,
    CARE_SCENARIO_WAKE_UP,
)
from repositories.care_repository import CareRepository
from repositories.device_repository import DeviceRepository
from services.care_defaults import ensure_default_capability_configs, ensure_default_routine_windows
from services.camera_ai_observation_service import CameraAiObservationService


DEFAULT_TIMEZONE = "Asia/Shanghai"

WINDOW_SCENARIOS = {
    "wake_up": CARE_SCENARIO_WAKE_UP,
    "breakfast": CARE_SCENARIO_MEAL_START,
    "lunch": CARE_SCENARIO_MEAL_START,
    "dinner": CARE_SCENARIO_MEAL_START,
    "nap": CARE_SCENARIO_NAP_TIME,
    "bedtime": CARE_SCENARIO_BEDTIME,
}

WINDOW_LABELS = {
    "wake_up": "起床",
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "nap": "午睡",
    "bedtime": "睡觉",
}


class RoutineReminderService:
    def __init__(self, database_url: str | Path):
        self.database_url = database_url
        database = Database(database_url)
        self.repository = CareRepository(database)
        self.device_repository = DeviceRepository(database)
        self.observation_service = CameraAiObservationService(database_url)

    def tick(self, *, now: int | None = None) -> dict:
        current = now if now is not None else now_ms()
        payloads = []
        skipped = []
        with self.repository.transaction() as conn:
            children = conn.execute(
                """
                SELECT id, family_id
                FROM children
                ORDER BY family_id, created_at, id
                """
            ).fetchall()
            for child in children:
                family_id = str(child["family_id"])
                child_id = str(child["id"])
                ensure_default_capability_configs(
                    self.repository,
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    device_id=None,
                )
                ensure_default_routine_windows(
                    self.repository,
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                )
                device = self.device_repository.ensure_default_device(
                    conn,
                    family_id=family_id,
                    now=current,
                )
                if device is None:
                    skipped.append({"childId": child_id, "reason": "no_device"})
                    continue
                windows = self.repository.list_routine_windows(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                )
                for window in windows:
                    payload = self._payload_for_due_window(
                        family_id=family_id,
                        child_id=child_id,
                        device_id=str(device["id"]),
                        window=window,
                        now=current,
                    )
                    if payload is not None:
                        payloads.append(payload)

        responses = []
        for payload in payloads:
            responses.append(self.observation_service.record_observation(payload))
        return {
            "ok": True,
            "checkedAt": current,
            "candidateCount": len(payloads),
            "triggeredCount": len(responses),
            "responses": responses,
            "skipped": skipped,
        }

    def _payload_for_due_window(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
        window,
        now: int,
    ) -> dict | None:
        if not bool(window.get("enabled")):
            return None
        window_type = str(window.get("window_type") or "")
        scenario = WINDOW_SCENARIOS.get(window_type)
        if scenario is None or not _time_in_window(now, window):
            return None
        label = WINDOW_LABELS.get(window_type, "作息")
        day_type = str(window.get("day_type") or "")
        local_date = _local_datetime(now, str(window.get("timezone") or DEFAULT_TIMEZONE)).date().isoformat()
        source_event_id = _routine_source_event_id(
            device_id=device_id,
            scenario=scenario,
            window_type=window_type,
            day_type=day_type,
            local_date=local_date,
            start_time=str(window.get("start_time") or ""),
            end_time=str(window.get("end_time") or ""),
        )
        return {
            "familyId": family_id,
            "childId": child_id,
            "deviceId": device_id,
            "scenario": scenario,
            "observedAt": now,
            "confidence": 1.0,
            "evidenceType": "routine_window",
            "parentSummary": f"到{label}时间",
            "source": "routine_reminder",
            "sourceEventId": source_event_id,
            "dayType": day_type,
            "recordCareEvent": False,
            "signals": [
                {
                    "signalType": "routine_due",
                    "signalValue": "active",
                    "confidence": 1.0,
                    "durationSeconds": 300,
                    "metadata": {
                        "windowType": window_type,
                        "dayType": day_type,
                        "label": label,
                    },
                }
            ],
            "rawDetail": {
                "window_type": window_type,
                "day_type": day_type,
                "description": f"到{label}时间，按家庭作息生成提醒。",
            },
        }


def _time_in_window(now: int, row) -> bool:
    local_time = _local_datetime(now, str(row.get("timezone") or DEFAULT_TIMEZONE)).time()
    start_time = _parse_clock(str(row.get("start_time") or ""))
    end_time = _parse_clock(str(row.get("end_time") or ""))
    if start_time is None or end_time is None:
        return False
    if start_time <= end_time:
        return start_time <= local_time <= end_time
    return local_time >= start_time or local_time <= end_time


def _window_start_ms(now: int, row) -> int:
    return _window_bound_ms(now, row, str(row.get("start_time") or "00:00"))


def _window_end_ms(now: int, row) -> int:
    return _window_bound_ms(now, row, str(row.get("end_time") or "23:59"))


def _window_bound_ms(now: int, row, clock_text: str) -> int:
    zone = _zone(str(row.get("timezone") or DEFAULT_TIMEZONE))
    current = datetime.fromtimestamp(now / 1000, tz=zone)
    clock = _parse_clock(clock_text) or time.min
    bound = datetime.combine(current.date(), clock, tzinfo=zone)
    return int(bound.timestamp() * 1000)


def _local_datetime(now: int, timezone: str) -> datetime:
    return datetime.fromtimestamp(now / 1000, tz=_zone(timezone))


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _parse_clock(value: str) -> time | None:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(int(hour_text), int(minute_text))
    except (TypeError, ValueError):
        return None


def _routine_source_event_id(
    *,
    device_id: str,
    scenario: str,
    window_type: str,
    day_type: str,
    local_date: str,
    start_time: str,
    end_time: str,
) -> str:
    return f"routine:{device_id}:{scenario}:{window_type}:{day_type}:{local_date}:{start_time}:{end_time}"
