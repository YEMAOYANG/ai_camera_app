from __future__ import annotations

from pathlib import Path

from core.database import Database
from core.errors import ApiError
from integrations.hardware.base import HardwareDeviceAdapter
from integrations.hardware.disabled_adapter import DisabledHardwareDeviceAdapter
from repositories.device_repository import DeviceRepository
from schemas.devices import device_payload
from services.auth_service import AuthService


class DeviceService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        hardware_adapter: HardwareDeviceAdapter | None = None,
    ):
        self.auth_service = auth_service
        self.repository = DeviceRepository(Database(database_url))
        self.hardware_adapter = hardware_adapter or DisabledHardwareDeviceAdapter()

    def list_devices(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            rows = self.repository.list_devices(conn, family_id=context["family"]["id"])
            return {"ok": True, "devices": [device_payload(row) for row in rows]}

    def get_device(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            return {"ok": True, "device": device_payload(device)}

    def device_status(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            return {
                "ok": True,
                "device": device_payload(device),
                "status": self.hardware_adapter.status_for_device(device_payload(device)),
            }

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _device_or_error(self, conn, family_id: str, device_id: str):
        device = self.repository.get_device(conn, family_id=family_id, device_id=device_id)
        if device is None:
            raise ApiError("device_not_found", "设备不存在", 404)
        return device
