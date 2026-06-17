from __future__ import annotations

import json

from core.security import now_ms
from models.care import (
    DEFAULT_CAPABILITY_CONFIGS,
    DEFAULT_DAY_TYPES,
    DEFAULT_FALLBACK_TEMPLATES,
    DEFAULT_ROUTINE_WINDOWS,
)
from repositories.care_repository import CareRepository


def ensure_default_capability_configs(
    repository: CareRepository,
    conn,
    *,
    family_id: str,
    child_id: str,
    device_id: str | None = None,
) -> None:
    now = now_ms()
    for item in DEFAULT_CAPABILITY_CONFIGS:
        scenario = item["scenario"]
        existing = repository.get_capability_config(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=scenario,
        )
        if existing:
            continue
        repository.upsert_capability_config(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=scenario,
            enabled=True,
            day_types=_json_text(DEFAULT_DAY_TYPES),
            time_windows=_json_text(item["timeWindows"]),
            min_observation_seconds=item["minObservationSeconds"],
            confidence_threshold=item["confidenceThreshold"],
            cooldown_seconds=item["cooldownSeconds"],
            daily_limit=item["dailyLimit"],
            parent_notify_threshold=item["parentNotifyThreshold"],
            allow_speaker=item["allowSpeaker"],
            record_only=item["recordOnly"],
            prompt_id=item["promptId"],
            prompt_version="v1",
            fallback_templates=_json_text(DEFAULT_FALLBACK_TEMPLATES[scenario]),
            now=now,
        )


def ensure_default_routine_windows(
    repository: CareRepository,
    conn,
    *,
    family_id: str,
    child_id: str,
) -> None:
    existing = repository.list_routine_windows(
        conn,
        family_id=family_id,
        child_id=child_id,
    )
    if existing:
        return
    now = now_ms()
    for item in DEFAULT_ROUTINE_WINDOWS:
        repository.upsert_routine_window(
            conn,
            family_id=family_id,
            child_id=child_id,
            day_type=item["dayType"],
            window_type=item["windowType"],
            start_time=item["startTime"],
            end_time=item["endTime"],
            enabled=True,
            timezone="Asia/Shanghai",
            now=now,
        )


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
