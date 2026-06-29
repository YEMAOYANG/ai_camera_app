from __future__ import annotations

from integrations.camera_runtime.ai_camera_test_adapter import AiCameraTestRuntimeAdapter
from integrations.camera_runtime.mock_adapter import MockCameraRuntimeAdapter
from services.voice_runtime_store import VoiceRuntimeStore


class GuardianLocalRuntimeAdapter(MockCameraRuntimeAdapter):
    adapter_name = "guardian_local_runtime"

    def __init__(
        self,
        *,
        family_id: str | None = None,
        device_id: str | None = None,
        vision_service=None,
        media_base_url: str | None = None,
    ):
        super().__init__(vision_service=vision_service)
        self.family_id = str(family_id or "").strip() or None
        self.device_id = str(device_id or "").strip() or None
        self._interaction_profile: dict = {}
        base_url = str(media_base_url or "").strip().rstrip("/")
        self._media = (
            AiCameraTestRuntimeAdapter(base_url, vision_service=vision_service)
            if base_url
            else None
        )

    def set_context(self, *, family_id: str | None, device_id: str | None) -> None:
        self.family_id = str(family_id or "").strip() or None
        self.device_id = str(device_id or "").strip() or None

    def sync_interaction_profile(self, profile: dict) -> dict:
        self._interaction_profile = dict(profile or {})
        if self.family_id and self.device_id:
            VoiceRuntimeStore.set_profile(
                family_id=self.family_id,
                device_id=self.device_id,
                profile=self._interaction_profile,
            )
        return {"ok": True, "interactionProfile": self._interaction_profile}

    def health(self) -> dict:
        if self._media is not None:
            return self._media.health()
        return super().health()

    def speaker_status(self) -> dict:
        if self._media is not None:
            return self._media.speaker_status()
        return super().speaker_status()

    def snapshot(self):
        if self._media is not None:
            return self._media.snapshot()
        return super().snapshot()

    def open_stream(self):
        if self._media is not None:
            return self._media.open_stream()
        return super().open_stream()

    def webrtc_session(self) -> dict:
        if self._media is not None:
            return self._media.webrtc_session()
        return super().webrtc_session()

    def webrtc_offer(self, offer_sdp: str) -> dict:
        if self._media is not None:
            return self._media.webrtc_offer(offer_sdp)
        return super().webrtc_offer(offer_sdp)

    def speak(self, text: str) -> dict:
        if self._media is not None:
            return self._media.speak(text)
        return super().speak(text)

    def ptz_move(self, direction: str, step: int) -> dict:
        if self._media is not None:
            return self._media.ptz_move(direction, step)
        return super().ptz_move(direction, step)

    def start_monitor(self) -> dict:
        if self._media is not None:
            return self._media.start_monitor()
        return super().start_monitor()

    def stop_monitor(self) -> dict:
        if self._media is not None:
            return self._media.stop_monitor()
        return super().stop_monitor()

    def monitor_status(self) -> dict:
        if self._media is not None:
            return self._media.monitor_status()
        return super().monitor_status()

    def refresh_monitor_observation(self, *, vision_context: dict | None = None) -> dict:
        if self._media is not None:
            return self._media.refresh_monitor_observation(vision_context=vision_context)
        return super().refresh_monitor_observation(vision_context=vision_context)

    def task_observation(self, task: dict) -> dict:
        if self._media is not None:
            return self._media.task_observation(task)
        return super().task_observation(task)

    def runtime(self) -> dict:
        payload = super().runtime()
        profile = dict(self._interaction_profile)
        if self.family_id and self.device_id:
            stored = VoiceRuntimeStore.runtime_payload(
                family_id=self.family_id,
                device_id=self.device_id,
            )
            voice = stored.get("voice") if isinstance(stored, dict) else {}
            if isinstance(voice, dict):
                profile = dict(voice.get("interactionProfile") or profile)
                payload["voice"] = {
                    **dict(payload.get("voice") or {}),
                    **voice,
                    "interactionProfile": profile,
                }
                return payload
        wake_name = str(profile.get("wakeName") or "")
        payload["voice"] = {
            **dict(payload.get("voice") or {}),
            "wakeName": wake_name,
            "interactionProfile": profile,
        }
        return payload
