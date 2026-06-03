from __future__ import annotations

from integrations.hardware.base import HardwareDeviceAdapter


class DisabledHardwareDeviceAdapter(HardwareDeviceAdapter):
    adapter_name = "disabled_hardware_device"

    def status_for_device(self, device: dict) -> dict:
        return {
            "deviceId": device["id"],
            "connectionStatus": "unknown",
            "privacyMode": None,
            "firmwareVersion": None,
            "network": {
                "type": device.get("networkType") or "wifi",
                "quality": "unknown",
            },
            "capabilities": {
                "snapshot": False,
                "stream": False,
                "twoWayAudio": False,
                "ota": False,
            },
            "adapter": self.adapter_name,
            "message": "硬件适配器尚未配置。",
        }
