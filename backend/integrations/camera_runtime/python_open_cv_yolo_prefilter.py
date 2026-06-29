from __future__ import annotations

from typing import Mapping

from integrations.camera_runtime.local_vision_prefilter import LocalVisionPrefilter
from services.vision_prefilter_service import PrefilterResult, analyze_prefilter


class PythonOpenCvYoloPrefilter:
    """Default backend implementation until hardware reports prefilter events."""

    def analyze_frame(
        self,
        image_bytes: bytes,
        *,
        previous: Mapping[str, object] | None,
        now_ms: int,
    ) -> PrefilterResult:
        return analyze_prefilter(image_bytes, previous=previous, now_ms=now_ms)


def default_local_vision_prefilter() -> LocalVisionPrefilter:
    return PythonOpenCvYoloPrefilter()
