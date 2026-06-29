from __future__ import annotations

import threading
from typing import Any


class VoiceRuntimeStore:
    _lock = threading.Lock()
    _states: dict[str, dict[str, Any]] = {}
    _profiles: dict[str, dict[str, Any]] = {}

    @classmethod
    def _key(cls, family_id: str, device_id: str) -> str:
        return f"{family_id}:{device_id}"

    @classmethod
    def set_profile(cls, *, family_id: str, device_id: str, profile: dict) -> None:
        key = cls._key(family_id, device_id)
        with cls._lock:
            cls._profiles[key] = dict(profile)

    @classmethod
    def get_profile(cls, *, family_id: str, device_id: str) -> dict:
        key = cls._key(family_id, device_id)
        with cls._lock:
            return dict(cls._profiles.get(key) or {})

    @classmethod
    def update_snapshot(
        cls,
        *,
        family_id: str,
        device_id: str,
        snapshot: dict,
        running: bool = True,
    ) -> None:
        key = cls._key(family_id, device_id)
        with cls._lock:
            current = dict(cls._states.get(key) or {})
            current.update(
                {
                    "running": running,
                    "snapshot": snapshot,
                }
            )
            cls._states[key] = current

    @classmethod
    def runtime_payload(cls, *, family_id: str, device_id: str) -> dict:
        key = cls._key(family_id, device_id)
        with cls._lock:
            state = dict(cls._states.get(key) or {})
            profile = dict(cls._profiles.get(key) or {})
        snapshot = dict(state.get("snapshot") or {})
        wake_name = str(profile.get("wakeName") or snapshot.get("wakeName") or "")
        return {
            "ok": True,
            "voice": {
                "state": snapshot.get("state") or "idle",
                "running": bool(state.get("running")),
                "wakeName": wake_name,
                "interactionProfile": profile,
                "lastWakeMatch": snapshot.get("last_wake_match"),
                "lastCommand": snapshot.get("last_command", ""),
                "lastReply": snapshot.get("last_reply", ""),
                "lastError": snapshot.get("last_error", ""),
            },
        }

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._states.clear()
            cls._profiles.clear()
