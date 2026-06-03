from __future__ import annotations

from integrations.hardware.base import HardwareDeviceAdapter


class MockHardwareDeviceAdapter(HardwareDeviceAdapter):
    adapter_name = "mock_hardware_device"

    def status_for_device(self, device: dict) -> dict:
        connection = "online" if device["status"] in {"bound", "online"} else "offline"
        return {
            "deviceId": device["id"],
            "connectionStatus": connection,
            "privacyMode": False,
            "firmwareVersion": "0.1.0-dev",
            "network": {
                "type": "wifi",
                "quality": "good" if connection == "online" else "unknown",
            },
            "capabilities": {
                "snapshot": True,
                "stream": True,
                "twoWayAudio": False,
                "ota": False,
            },
            "adapter": self.adapter_name,
        }
