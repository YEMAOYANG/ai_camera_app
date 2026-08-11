from __future__ import annotations

from typing import Any, Mapping

from integrations.onvif.client import VerifiedOnvifDevice


def build_onvif_runtime_config(
    *,
    device_service_url: str,
    endpoint_reference: str,
    verified: VerifiedOnvifDevice,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the private runtime metadata without persisting an RTSP URI."""

    config = dict(base or {})
    config.update(
        {
            "deviceServiceUrl": str(device_service_url or "").strip(),
            "endpointReference": str(endpoint_reference or "").strip(),
            "hardwareId": str(verified.hardware_id or "").strip(),
            "profileToken": verified.profile_token,
            "streamProfile": verified.profile_name or "primary",
            "previewProfileToken": (
                verified.preview_profile_token or verified.profile_token
            ),
            "previewStreamProfile": (
                verified.preview_profile_name
                or verified.profile_name
                or "preview"
            ),
            "previewVideoEncoding": (
                verified.preview_video_encoding or verified.video_encoding
            ),
            "previewWidth": verified.preview_width or verified.width,
            "previewHeight": verified.preview_height or verified.height,
        }
    )
    config["speakerCapabilities"] = {
        **_mapping(config.get("speakerCapabilities")),
        "enabled": False,
        "duplex": False,
    }
    config["deviceProfile"] = {
        **_mapping(config.get("deviceProfile")),
        **{
            key: value
            for key, value in {
                "manufacturer": verified.manufacturer,
                "model": verified.model,
                "firmwareVersion": verified.firmware_version,
                "serialNumber": verified.serial_number,
                "hardwareId": verified.hardware_id,
            }.items()
            if value
        },
    }
    config["capabilities"] = {
        **_mapping(config.get("capabilities")),
        "ptz": False,
        "detectedPtz": bool(verified.has_ptz),
        "audio": bool(verified.has_audio),
    }
    return config


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
