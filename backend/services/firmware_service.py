from __future__ import annotations

from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.device_repository import DeviceRepository
from repositories.firmware_repository import FirmwareRepository
from schemas.devices import device_payload
from schemas.firmware import firmware_job_payload, firmware_package_payload
from services.auth_service import AuthService


class FirmwareService:
    def __init__(self, database_url: str | Path, *, auth_service: AuthService):
        self.auth_service = auth_service
        database = Database(database_url)
        self.device_repository = DeviceRepository(database)
        self.repository = FirmwareRepository(database)

    def device_status(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            packages = self.repository.list_packages(conn)
            latest_job = self.repository.latest_job_for_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
            )
            payload = {
                "ok": True,
                "device": device_payload(device),
                "firmware": {
                    "currentVersion": "0.1.0-dev",
                    "updateAvailable": False,
                    "latestPackage": firmware_package_payload(packages[0]) if packages else None,
                    "lastJob": firmware_job_payload(latest_job) if latest_job else None,
                    "execution": "reserved_boundary_only",
                },
            }
            return payload

    def packages(self, access_token: str) -> dict:
        self._auth_context(access_token)
        with self.repository.transaction() as conn:
            rows = self.repository.list_packages(conn)
            return {"ok": True, "packages": [firmware_package_payload(row) for row in rows]}

    def create_job(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        device_id = self._required_text(data, "deviceId", "缺少设备 ID")
        package_id = self._required_text(data, "packageId", "缺少固件包 ID")
        now = now_ms()
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            package = self.repository.get_package(conn, package_id)
            if package is None:
                raise ApiError("firmware_package_not_found", "固件包不存在", 404)
            job = self.repository.create_job(
                conn,
                family_id=context["family"]["id"],
                device_id=device["id"],
                package_id=package["id"],
                now=now,
            )
            return {
                "ok": True,
                "job": firmware_job_payload(job),
                "execution": "reserved_boundary_only",
            }

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _device_or_error(self, conn, family_id: str, device_id: str):
        device = self.device_repository.get_device(conn, family_id=family_id, device_id=device_id)
        if device is None:
            raise ApiError("device_not_found", "设备不存在", 404)
        return device

    def _required_text(self, data: dict, key: str, message: str) -> str:
        value = data.get(key)
        value = str(value).strip() if value is not None else ""
        if not value:
            raise ApiError(f"missing_{key}", message)
        return value
