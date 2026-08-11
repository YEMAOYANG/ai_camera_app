from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def camera_image_analysis_authorized(
    privacy: Mapping[str, Any] | None,
) -> bool:
    if privacy is None:
        return False
    return (
        privacy.get("cameraCollectionAuthorized") is True
        and privacy.get("childPrivacyAuthorized") is True
    )
