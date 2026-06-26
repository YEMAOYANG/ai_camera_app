from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from schemas.vision import ALLOWED_ACTIVITIES, normalize_vision_observation


JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
STRUCTURED_LEAK_RE = re.compile(r'^\s*[\{\[]')


@dataclass(frozen=True)
class VisionValidationResult:
    ok: bool
    observation: dict[str, Any]
    reason: str = ""


class VisionObservationValidator:
    def __init__(
        self,
        *,
        max_description_length: int = 180,
        max_summary_length: int = 80,
    ):
        self.max_description_length = max(32, int(max_description_length))
        self.max_summary_length = max(16, int(max_summary_length))

    def validate(
        self,
        raw_text: str | None,
        *,
        observed_at: int | None = None,
        method: str = "guardian_kimi_k26",
    ) -> VisionValidationResult:
        parsed = self._parse_json(raw_text)
        if parsed is None:
            return VisionValidationResult(
                ok=False,
                observation=normalize_vision_observation(
                    {
                        "has_person": None,
                        "activity": "",
                        "confidence": 0.0,
                        "description": "模型返回格式无效。",
                    },
                    observed_at=observed_at,
                    method=method,
                ),
                reason="invalid_json",
            )
        return self._validate_dict(parsed, observed_at=observed_at, method=method)

    def _validate_dict(
        self,
        parsed: Mapping[str, Any],
        *,
        observed_at: int | None,
        method: str,
    ) -> VisionValidationResult:
        if "has_person" not in parsed:
            return self._fallback(parsed, observed_at=observed_at, method=method, reason="missing_has_person")
        has_person = parsed.get("has_person")
        if not isinstance(has_person, bool):
            return self._fallback(parsed, observed_at=observed_at, method=method, reason="invalid_has_person")
        activity = str(parsed.get("activity") or "").strip()
        if not activity:
            return self._fallback(parsed, observed_at=observed_at, method=method, reason="missing_activity")
        if activity not in ALLOWED_ACTIVITIES:
            activity = "其他"
        try:
            confidence = float(parsed.get("confidence"))
        except (TypeError, ValueError):
            return self._fallback(parsed, observed_at=observed_at, method=method, reason="invalid_confidence")
        confidence = max(0.0, min(1.0, confidence))
        description = self._clean_text(parsed.get("description"), self.max_description_length)
        if _looks_like_structured_payload(description):
            description = ""
        raw_activity = self._clean_text(parsed.get("raw_activity") or activity, 80)
        child_message = self._clean_text(parsed.get("child_message"), 120)
        if _looks_like_structured_payload(child_message):
            child_message = ""
        observation = normalize_vision_observation(
            {
                "has_person": has_person,
                "activity": activity,
                "raw_activity": raw_activity,
                "description": description,
                "confidence": confidence,
                "posture_status": parsed.get("posture_status"),
                "bad_posture": bool(parsed.get("bad_posture")),
                "toys_visible": bool(parsed.get("toys_visible")),
                "toys_scattered": bool(parsed.get("toys_scattered")),
                "homework_like": bool(parsed.get("homework_like")),
                "child_message": child_message,
            },
            observed_at=observed_at,
            method=method,
        )
        return VisionValidationResult(ok=True, observation=observation)

    def _fallback(
        self,
        parsed: Mapping[str, Any],
        *,
        observed_at: int | None,
        method: str,
        reason: str,
    ) -> VisionValidationResult:
        return VisionValidationResult(
            ok=False,
            observation=normalize_vision_observation(
                {
                    "has_person": parsed.get("has_person") if isinstance(parsed.get("has_person"), bool) else None,
                    "activity": "",
                    "confidence": 0.0,
                    "description": "暂时无法稳定识别画面内容。",
                },
                observed_at=observed_at,
                method=method,
            ),
            reason=reason,
        )

    def _parse_json(self, raw_text: str | None) -> dict[str, Any] | None:
        value = str(raw_text or "").strip()
        if not value:
            return None
        fence = JSON_FENCE_RE.search(value)
        if fence:
            value = fence.group(1).strip()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            start = value.find("{")
            end = value.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                parsed = json.loads(value[start : end + 1])
            except json.JSONDecodeError:
                return None
        return parsed if isinstance(parsed, dict) else None

    def _clean_text(self, value: object, max_length: int) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text[:max_length]


def _looks_like_structured_payload(text: str) -> bool:
    if not text:
        return False
    if STRUCTURED_LEAK_RE.match(text):
        return True
    if '"activity"' in text or '"has_person"' in text:
        return True
    return False
