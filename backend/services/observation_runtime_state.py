from __future__ import annotations

import json
import os
from typing import Any, Mapping

from repositories.care_repository import CareRepository


RUNTIME_SCENARIO = "_observation_runtime"
RUNTIME_STATE = "gate"


def runtime_config() -> dict:
    return {
        "absence_confirm_ticks": int(os.getenv("APP_ABSENCE_CONFIRM_TICKS", "3")),
        "absence_check_interval_seconds": int(os.getenv("APP_ABSENCE_CHECK_INTERVAL_SECONDS", "300")),
        "absence_long_interval_seconds": int(os.getenv("APP_ABSENCE_LONG_INTERVAL_SECONDS", "600")),
        "absence_long_after_seconds": int(os.getenv("APP_ABSENCE_LONG_AFTER_SECONDS", "1800")),
        "session_dedupe_seconds": int(os.getenv("APP_OBSERVATION_SESSION_DEDUPE_SECONDS", "600")),
    }


def default_runtime_payload() -> dict[str, Any]:
    return {
        "absence": {
            "mode": "active",
            "consecutive_no_person": 0,
            "absence_started_at": 0,
            "next_check_at": 0,
            "recorded_absent": False,
        },
        "session": {
            "bucket": "other",
            "risk": "none",
            "last_record_at": 0,
            "last_cloud_at": 0,
        },
        "frame": {
            "hash": "",
            "last_changed_at": 0,
            "updated_at": 0,
        },
        "display": {
            "observed_at": 0,
        },
    }


class ObservationRuntimeStateStore:
    def __init__(self, repository: CareRepository):
        self.repository = repository

    def load(self, conn, *, family_id: str, child_id: str, device_id: str) -> dict[str, Any]:
        row = self.repository.get_current_behavior_state(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=RUNTIME_SCENARIO,
            state=RUNTIME_STATE,
        )
        if row is None:
            return default_runtime_payload()
        raw = row.get("raw_detail_json")
        if not raw:
            return default_runtime_payload()
        try:
            parsed = json.loads(str(raw))
        except json.JSONDecodeError:
            return default_runtime_payload()
        if not isinstance(parsed, dict):
            return default_runtime_payload()
        merged = default_runtime_payload()
        for key in ("absence", "session", "frame", "display"):
            section = parsed.get(key)
            if isinstance(section, dict):
                merged[key].update(section)
        return merged

    def save(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
        payload: Mapping[str, Any],
        now: int,
    ) -> None:
        existing = self.repository.get_current_behavior_state(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=RUNTIME_SCENARIO,
            state=RUNTIME_STATE,
        )
        started_at = int(existing.get("started_at") or now) if existing else now
        self.repository.upsert_behavior_state(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=RUNTIME_SCENARIO,
            state=RUNTIME_STATE,
            status="active",
            started_at=started_at,
            last_observed_at=now,
            confidence=1.0,
            consecutive_seconds=0,
            parent_summary=None,
            raw_detail_json=json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")),
            now=now,
        )
