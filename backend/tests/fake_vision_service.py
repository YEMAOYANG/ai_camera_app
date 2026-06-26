from __future__ import annotations

from core.security import now_ms
from schemas.vision import normalize_vision_observation
from services.vision_observation_enrich import enrich_observation_risks


class FakeVisionObservationService:
    def __init__(self, payload: dict | None = None):
        self.payload = dict(payload or {})
        self.calls: list[dict] = []

    def analyze_snapshot(self, **kwargs) -> dict:
        self.calls.append(dict(kwargs))
        payload = dict(self.payload)
        activity = str(payload.get("activity") or "")
        if activity == "阅读绘本":
            payload["activity"] = "看书"
        elif activity == "playing with toys":
            payload["activity"] = "玩玩具"
        payload.setdefault("observed_at", now_ms())
        payload.setdefault("method", "guardian_test")
        payload.setdefault("confidence", 0.88)
        normalized = normalize_vision_observation(payload, observed_at=payload["observed_at"])
        return enrich_observation_risks(normalized)


def build_fake_vision_observation_service(_config: dict, payload: dict | None = None):
    return FakeVisionObservationService(payload)
