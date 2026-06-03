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
