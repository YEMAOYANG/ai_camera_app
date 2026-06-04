from __future__ import annotations

from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from integrations.hardware.base import HardwareDeviceAdapter
from integrations.hardware.disabled_adapter import DisabledHardwareDeviceAdapter
from repositories.device_repository import DeviceRepository
from schemas.devices import device_payload
from services.camera_bridge_service import CameraBridgeService
from services.auth_service import AuthService


class DeviceService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        hardware_adapter: HardwareDeviceAdapter | None = None,
        camera_service: CameraBridgeService | None = None,
    ):
        self.auth_service = auth_service
        self.repository = DeviceRepository(Database(database_url))
        self.hardware_adapter = hardware_adapter or DisabledHardwareDeviceAdapter()
        self.camera_service = camera_service

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

    def update_device(self, access_token: str, device_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        fields: dict = {}
        if "name" in data:
            fields["name"] = self._required_text(data, "name", "请输入设备名称")
        if "location" in data:
            fields["location"] = self._optional_text(data, "location")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._device_or_error(conn, context["family"]["id"], device_id)
            device = self.repository.update_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                fields=fields,
                now=now,
            )
            return {"ok": True, "device": device_payload(device)}

    def rename_device(self, access_token: str, device_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        name = self._required_text(data, "name", "请输入设备名称")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._device_or_error(conn, context["family"]["id"], device_id)
            device = self.repository.update_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                fields={"name": name},
                now=now,
            )
            return {"ok": True, "device": device_payload(device)}

    def unbind_device(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            if device["status"] == "unbound":
                return {"ok": True, "device": device_payload(device)}
            device = self.repository.unbind_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                now=now,
            )
            return {"ok": True, "device": device_payload(device)}

    def device_status(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            hardware_status = self.hardware_adapter.status_for_device(device_payload(device))
            camera_status = (
                self.camera_service.status()["status"] if self.camera_service is not None else {}
            )
            return {
                "ok": True,
                "device": device_payload(device),
                "status": self._merge_status(hardware_status, camera_status),
            }

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _device_or_error(self, conn, family_id: str, device_id: str):
        device = self.repository.get_device(conn, family_id=family_id, device_id=device_id)
        if device is None:
            raise ApiError("device_not_found", "设备不存在", 404)
        return device

    def _merge_status(self, hardware_status: dict, camera_status: dict) -> dict:
        if not camera_status:
            return hardware_status
        capabilities = dict(hardware_status.get("capabilities") or {})
        capabilities.update(
            {
                "snapshot": bool(camera_status.get("snapshotAvailable")),
                "stream": bool(camera_status.get("streamAvailable")),
                "twoWayAudio": bool(camera_status.get("speakerAvailable")),
                "monitor": bool(camera_status.get("monitorAvailable")),
            }
        )
        connection = camera_status.get("connectionStatus") or hardware_status.get("connectionStatus")
        return {
            **hardware_status,
            "connectionStatus": connection,
            "lastSeenAt": camera_status.get("lastSeenAt"),
            "message": camera_status.get("message") or hardware_status.get("message") or "",
            "capabilities": capabilities,
            "camera": camera_status,
        }

    def _required_text(self, data: dict, key: str, message: str) -> str:
        value = self._optional_text(data, key)
        if not value:
            raise ApiError(f"missing_{key}", message)
        return value

    def _optional_text(self, data: dict, key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        value = str(value).strip()
        return value or None
