from __future__ import annotations

from typing import Protocol

from services.vision_prefilter_service import PrefilterResult


class LocalVisionPrefilter(Protocol):
    """Adapter boundary for device-side or backend-side local vision prefilter."""

    def analyze_frame(self, image_bytes: bytes, *, previous: dict | None, now_ms: int) -> PrefilterResult:
        ...
