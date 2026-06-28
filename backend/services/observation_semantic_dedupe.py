from __future__ import annotations

import json
from typing import Mapping


def semantic_dedupe_key(payload: Mapping[str, object]) -> str:
    raw = payload.get("rawDetail")
    if not isinstance(raw, dict):
        raw = {}
    signals = payload.get("signals")
    signal_type = ""
    if isinstance(signals, list) and signals:
        signal_type = str(signals[0].get("signalType") or "")
    canonical = {
        "scenario": payload.get("scenario"),
        "signalType": signal_type,
        "bucket": raw.get("session_bucket"),
        "risk": raw.get("session_risk"),
        "has_person": raw.get("has_person"),
        "meal_etiquette_issue": raw.get("meal_etiquette_issue"),
        "play_safety_reason": raw.get("play_safety_reason"),
    }
    return json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
