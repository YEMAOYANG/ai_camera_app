from __future__ import annotations

import time
from typing import Any, Mapping

from integrations.ai.kimi_vision_provider import AiVisionProvider
from schemas.vision import VISION_METHOD, VISION_METHOD_CACHED, insufficient_observation, with_observation_reliability
from services.prompt_registry import PromptRegistry
from services.vision_observation_cadence import VisionCadenceGate
from services.vision_observation_enrich import enrich_observation
from services.parent_facing_copy import sanitize_parent_facing_observation
from services.vision_observation_validator import VisionObservationValidator


_GLOBAL_CADENCE = VisionCadenceGate()
_DEVICE_LAST_ACTIVITY: dict[str, str] = {}


class VisionObservationService:
    def __init__(
        self,
        *,
        vision_provider: AiVisionProvider,
        prompt_registry: PromptRegistry,
        validator: VisionObservationValidator | None = None,
        cadence: VisionCadenceGate | None = None,
        enabled: bool = True,
        min_interval_seconds: float = 60.0,
        max_calls_per_hour: int = 20,
        backoff_seconds: float = 300.0,
    ):
        self.vision_provider = vision_provider
        self.prompt_registry = prompt_registry
        self.validator = validator or VisionObservationValidator()
        self.enabled = bool(enabled)
        self.cadence = cadence or _GLOBAL_CADENCE
        self.cadence.min_interval_seconds = max(1.0, float(min_interval_seconds))
        self.cadence.max_calls_per_hour = max(1, int(max_calls_per_hour))
        self.cadence.backoff_seconds = max(1.0, float(backoff_seconds))

    def analyze_snapshot(
        self,
        *,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
        observed_at: int | None = None,
        context: dict | None = None,
        device_key: str = "default",
        force_analyze: bool = False,
    ) -> dict[str, Any]:
        now_ms = observed_at if observed_at is not None else int(time.time() * 1000)
        if not self.enabled:
            return insufficient_observation(reason="vision_not_configured", observed_at=now_ms)
        if not self.cadence.should_call_cloud(device_key, force=force_analyze):
            cached = self.cadence.cached_result(device_key)
            if cached is not None:
                cached = enrich_observation(dict(cached))
                cached.setdefault("observed_at", now_ms)
                return with_observation_reliability(cached)
            return insufficient_observation(reason="vision_rate_limited", observed_at=now_ms)
        prompt = self.prompt_registry.get_prompt("vision.scene_observation", "v1")
        if prompt is None or not prompt.body.strip():
            return insufficient_observation(reason="vision_prompt_missing", observed_at=now_ms)
        last_activity = _DEVICE_LAST_ACTIVITY.get(device_key, "未知")
        user_prompt = _render_user_prompt(prompt.body, context=context, last_activity=last_activity)
        disable_thinking = bool(getattr(self.vision_provider, "disable_thinking", False))
        response = self.vision_provider.analyze_image(
            system_prompt="你是儿童摄像头视觉观察模块，只输出 JSON。",
            user_prompt=user_prompt,
            image_bytes=image_bytes,
            content_type=content_type,
            max_tokens=640,
            # kimi-k2.6 关闭 thinking 时仅允许 0.6；开启 thinking 时需更高 max_tokens 且用 1.0。
            temperature=0.6 if disable_thinking else 1.0,
        )
        if response is None:
            cached = self.cadence.cached_result(device_key)
            if cached is not None:
                cached = enrich_observation(dict(cached))
                cached.setdefault("observed_at", now_ms)
                return with_observation_reliability(cached)
            return insufficient_observation(reason="vision_provider_unavailable", observed_at=now_ms)
        validation = self.validator.validate(response.text, observed_at=now_ms, method=VISION_METHOD)
        observation = dict(validation.observation)
        child_reference = str((context or {}).get("child_reference") or "孩子")
        description = str(observation.get("description") or "").strip()
        if description:
            observation["description"] = sanitize_parent_facing_observation(
                description,
                child_reference=child_reference,
            )
        observation = enrich_observation(observation)
        activity = str(observation.get("activity") or observation.get("raw_activity") or "").strip()
        if activity:
            _DEVICE_LAST_ACTIVITY[device_key] = activity
        observation["vision_cadence"] = {
            "called_cloud": True,
            "forced": bool(force_analyze),
            "validation_ok": validation.ok,
        }
        self.cadence.record_cloud_call(device_key, observation)
        return with_observation_reliability(observation)


def _render_user_prompt(body: str, *, context: Mapping[str, object] | None, last_activity: str) -> str:
    ctx = dict(context or {})
    ctx.setdefault("last_activity", last_activity)
    rendered = body
    for key, value in ctx.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered.replace("{last_activity}", last_activity)
