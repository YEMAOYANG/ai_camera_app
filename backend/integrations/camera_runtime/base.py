from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CameraSnapshot:
    body: bytes
    content_type: str


class CameraRuntimeAdapter(Protocol):
    adapter_name: str

    def health(self) -> dict:
        ...

    def runtime(self) -> dict:
        ...

    def speaker_status(self) -> dict:
        ...

    def snapshot(self) -> CameraSnapshot:
        ...

    def open_stream(self):
        ...

    def webrtc_session(self) -> dict:
        ...

    def webrtc_offer(self, offer_sdp: str) -> dict:
        ...

    def speak(self, text: str) -> dict:
        ...

    def ptz_move(self, direction: str, step: int) -> dict:
        ...

    def start_monitor(self) -> dict:
        ...

    def stop_monitor(self) -> dict:
        ...

    def monitor_status(self) -> dict:
        ...

    def refresh_monitor_observation(self) -> dict:
        ...

    def task_observation(self, task: dict) -> dict:
        ...
