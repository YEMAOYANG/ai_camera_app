from __future__ import annotations

from typing import Protocol


class HardwareDeviceAdapter(Protocol):
    adapter_name: str

    def status_for_device(self, device: dict) -> dict:
        ...
