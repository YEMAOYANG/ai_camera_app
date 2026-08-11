from __future__ import annotations

import json
import os
from typing import Any, Mapping

from repositories.care_repository import CareRepository
from services.observation_cloud_gate import default_care_behavior_state, default_cloud_gate_state


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
        "prefilter": {
            "last_frame_thumb_b64": "",
            "motion_score": 0.0,
            "motion_pixels": 0,
            "person_detected": None,
            "person_confidence": 0.0,
            "person_count": 0,
            "person_available": False,
            "motion_available": False,
            "checked_at": 0,
        },
        "cloud_gate": default_cloud_gate_state(),
        "care_behavior": default_care_behavior_state(),
    }


def display_freshness_config() -> dict[str, int]:
    return {
        "fresh_seconds": int(os.getenv("APP_DISPLAY_FRESH_SECONDS", "300")),
    }


def display_freshness_from_runtime(
    *,
    now_ms: int,
    display: Mapping[str, Any] | None,
    last_kimi_at_ms: int = 0,
) -> str:
    """Return fresh | stale | prefilter_only for parent-facing display."""
    section = dict(display or {})
    observed_at = int(section.get("observed_at") or 0)
    freshness = str(section.get("freshness") or "").strip().lower()
    if freshness in {"fresh", "stale", "prefilter_only"}:
        return freshness
    if last_kimi_at_ms <= 0 and observed_at <= 0:
        return "prefilter_only"
    config = display_freshness_config()
    anchor = max(observed_at, last_kimi_at_ms)
    if anchor <= 0:
        return "prefilter_only"
    age_seconds = max(0, (now_ms - anchor) // 1000)
    if age_seconds <= config["fresh_seconds"]:
        return "fresh"
    return "stale"


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
        for key in ("absence", "session", "frame", "display", "prefilter", "cloud_gate", "care_behavior"):
            section = parsed.get(key)
            if isinstance(section, dict):
                merged[key].update(section)
        merged["prefilter"]["last_frame_thumb_b64"] = ""
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
        stored_payload = dict(payload)
        stored_payload["prefilter"] = dict(
            stored_payload.get("prefilter") or {}
        )
        stored_payload["prefilter"]["last_frame_thumb_b64"] = ""
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
            raw_detail_json=json.dumps(
                stored_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            now=now,
        )
