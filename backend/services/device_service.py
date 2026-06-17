from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from integrations.hardware.base import HardwareDeviceAdapter
from integrations.hardware.disabled_adapter import DisabledHardwareDeviceAdapter
from repositories.device_repository import DeviceRepository
from schemas.devices import device_payload, device_runtime_config_payload, runtime_config_json
from schemas.profile import role_capabilities_from_option
from services.camera_bridge_service import CameraBridgeService
from services.auth_service import AuthService
from services.device_runtime_resolver import DeviceRuntimeResolver

FALLBACK_ROLE_CAPABILITIES = {
    "admin": ["manage_devices"],
    "guardian": [],
    "viewer": [],
}

RUNTIME_PROVIDERS = {"disabled", "mock", "ai_camera_test", "future_hardware", "self_owned_camera"}
DEVELOPMENT_RUNTIME_PROVIDERS = {"mock", "ai_camera_test"}
RESERVED_RUNTIME_PROVIDERS = {"future_hardware", "self_owned_camera"}
SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "apikey",
    "api_key",
    "accesskey",
    "access_key",
    "authorization",
    "cookie",
    "privatekey",
    "private_key",
    "certificate",
    "credential",
)
SENSITIVE_VALUE_MARKERS = (
    "-----begin",
    "bearer ",
    "password=",
    "passwd=",
    "token=",
    "api_key=",
    "apikey=",
    "secret=",
    "authorization:",
    "set-cookie:",
    "private key",
)
SPEAKER_CAPABILITIES_SCHEMA = {
    "enabled": "bool",
    "duplex": "bool",
    "volume": "number",
}
RUNTIME_CONFIG_SCHEMAS = {
    "disabled": {},
    "mock": {
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
    },
    "ai_camera_test": {
        "baseUrl": "url",
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
    },
    "future_hardware": {
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
        "deviceProfile": {
            "model": "text",
            "region": "text",
            "firmwareChannel": "text",
        },
    },
    "self_owned_camera": {
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
        "deviceProfile": {
            "model": "text",
            "region": "text",
            "firmwareChannel": "text",
        },
    },
}


class DeviceService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        hardware_adapter: HardwareDeviceAdapter | None = None,
        camera_service: CameraBridgeService | None = None,
        runtime_resolver: DeviceRuntimeResolver | None = None,
        app_env: str = "production",
        dev_adapters_enabled: bool = False,
    ):
        self.auth_service = auth_service
        self.repository = DeviceRepository(Database(database_url))
        self.hardware_adapter = hardware_adapter or DisabledHardwareDeviceAdapter()
        self.camera_service = camera_service
        self.runtime_resolver = runtime_resolver
        self.app_env = str(app_env or "production").strip().lower()
        self.dev_adapters_enabled = bool(dev_adapters_enabled)

    def list_devices(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self.repository.ensure_default_device(
                conn,
                family_id=context["family"]["id"],
                now=now_ms(),
            )
            rows = self.repository.list_devices(conn, family_id=context["family"]["id"])
            return {"ok": True, "devices": [device_payload(row) for row in rows]}

    def bind_device(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        binding_code = self._required_text(data, "bindingCode", "请输入设备绑定码")
        name = (
            self._optional_text(data, "name")
            or self._optional_text(data, "deviceName")
            or "小守"
        )
        location = self._optional_text(data, "location")
        set_as_default = bool(data.get("setAsDefault"))
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            family_id = context["family"]["id"]
            global_existing = self.repository.find_active_device_by_binding_code_global(
                conn,
                binding_code=binding_code,
            )
            if global_existing and global_existing["family_id"] != family_id:
                raise ApiError("device_already_bound", "这台设备已绑定到其他家庭。", 409)
            existing = self.repository.find_active_device_by_binding_code(
                conn,
                family_id=family_id,
                binding_code=binding_code,
            )
            duplicate = existing is not None
            if existing:
                device = self.repository.get_device(
                    conn,
                    family_id=family_id,
                    device_id=existing["id"],
                )
            else:
                unbound = self.repository.find_unbound_device_by_binding_code(
                    conn,
                    family_id=family_id,
                    binding_code=binding_code,
                )
                if unbound:
                    device = self.repository.rebind_device(
                        conn,
                        family_id=family_id,
                        device_id=unbound["id"],
                        name=name,
                        location=location,
                        now=now,
                    )
                else:
                    device = self.repository.create_device(
                        conn,
                        family_id=family_id,
                        binding_code=binding_code,
                        name=name,
                        location=location,
                        now=now,
                    )
            default_device = self.repository.get_default_device(conn, family_id=family_id)
            if device and (set_as_default or default_device is None):
                default_device = self.repository.set_default_device(
                    conn,
                    family_id=family_id,
                    device_id=device["id"],
                    now=now,
                )
                device = self.repository.get_device(
                    conn,
                    family_id=family_id,
                    device_id=device["id"],
                )
            return {
                "ok": True,
                "duplicate": duplicate,
                "device": device_payload(device),
                "defaultDevice": device_payload(default_device) if default_device else None,
            }

    def get_device(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            return {"ok": True, "device": device_payload(device)}

    def default_device(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self.repository.ensure_default_device(
                conn,
                family_id=context["family"]["id"],
                now=now_ms(),
            )
            return {"ok": True, "device": device_payload(device) if device else None}

    def get_runtime_config(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            self._active_device_or_error(conn, context["family"]["id"], device_id)
            row = self.repository.get_device_runtime_config(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
            )
            return {
                "ok": True,
                "runtimeConfig": self._runtime_config_payload(row) if row else None,
            }

    def update_runtime_config(self, access_token: str, device_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        provider = self._runtime_provider(data.get("provider"))
        config = data.get("config") if "config" in data else {}
        sanitized_config = self._runtime_config(provider, config)
        secret_ref = self._secret_ref(data.get("secretRef"))
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            self._active_device_or_error(conn, context["family"]["id"], device_id)
            row = self.repository.upsert_device_runtime_config(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                provider=provider,
                config_json=json.dumps(sanitized_config, ensure_ascii=False, separators=(",", ":")),
                secret_ref=secret_ref,
                status="active",
                now=now,
            )
            return {
                "ok": True,
                "runtimeConfig": self._runtime_config_payload(row),
            }

    def set_default_device(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            device = self._active_device_or_error(conn, context["family"]["id"], device_id)
            default_device = self.repository.set_default_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device["id"],
                now=now,
            )
            return {"ok": True, "device": device_payload(default_device)}

    def update_device(self, access_token: str, device_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        fields: dict = {}
        if "name" in data:
            fields["name"] = self._required_text(data, "name", "请输入设备名称")
        if "location" in data:
            fields["location"] = self._optional_text(data, "location")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
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
            self._assert_capability(conn, context, "manage_devices")
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
            self._assert_capability(conn, context, "manage_devices")
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            if device["status"] == "unbound":
                default_device = self.repository.get_default_device(conn, family_id=context["family"]["id"])
                return {
                    "ok": True,
                    "device": device_payload(device),
                    "defaultDevice": device_payload(default_device) if default_device else None,
                }
            was_default = bool(device.get("is_default"))
            device = self.repository.unbind_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                now=now,
            )
            default_device = self.repository.get_default_device(conn, family_id=context["family"]["id"])
            if was_default:
                replacement = self.repository.find_replacement_default_device(
                    conn,
                    family_id=context["family"]["id"],
                    exclude_device_id=device_id,
                )
                if replacement:
                    default_device = self.repository.set_default_device(
                        conn,
                        family_id=context["family"]["id"],
                        device_id=replacement["id"],
                        now=now,
                    )
                else:
                    self.repository.clear_default_device(conn, family_id=context["family"]["id"])
                    default_device = None
            return {
                "ok": True,
                "device": device_payload(device),
                "defaultDevice": device_payload(default_device) if default_device else None,
            }

    def device_status(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            hardware_status = self.hardware_adapter.status_for_device(device_payload(device))
            camera_status = self._camera_status_for_device(context["family"]["id"], device_id)
            return {
                "ok": True,
                "device": device_payload(device),
                "status": self._merge_status(hardware_status, camera_status),
            }

    def _camera_status_for_device(self, family_id: str, device_id: str) -> dict:
        if self.runtime_resolver is not None:
            return self.runtime_resolver.resolve(
                family_id=family_id,
                device_id=device_id,
                require_device=True,
            ).bridge.status()["status"]
        if self.camera_service is not None:
            return self.camera_service.status()["status"]
        return {}

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _device_or_error(self, conn, family_id: str, device_id: str):
        device = self.repository.get_device(conn, family_id=family_id, device_id=device_id)
        if device is None:
            raise ApiError("device_not_found", "设备不存在", 404)
        return device

    def _active_device_or_error(self, conn, family_id: str, device_id: str):
        device = self._device_or_error(conn, family_id, device_id)
        if device["status"] == "unbound":
            raise ApiError("device_unbound", "设备已解绑", 409)
        return device

    def _assert_current_admin(self, conn, context: dict):
        member = self.repository.get_family_member_by_user(
            conn,
            family_id=context["family"]["id"],
            user_id=context["user"]["id"],
        )
        if member is None:
            user = context["user"]
            member = self.repository.ensure_owner_member(
                conn,
                family_id=context["family"]["id"],
                user_id=user["id"],
                name=user.get("displayName") or "家长",
                phone=user.get("phone") or "",
                now=now_ms(),
            )
        if member is None:
            raise ApiError("member_not_found", "家庭成员不存在", 404)
        if member["role"] != "admin":
            raise ApiError("admin_required", "只有家庭管理员可以进行此操作", 403)
        return member

    def _assert_capability(self, conn, context: dict, capability: str):
        member = self.repository.get_family_member_by_user(
            conn,
            family_id=context["family"]["id"],
            user_id=context["user"]["id"],
        )
        if member is None:
            user = context["user"]
            member = self.repository.ensure_owner_member(
                conn,
                family_id=context["family"]["id"],
                user_id=user["id"],
                name=user.get("displayName") or "家长",
                phone=user.get("phone") or "",
                now=now_ms(),
            )
        if member is None:
            raise ApiError("member_not_found", "家庭成员不存在", 404)
        row = self.repository.get_app_option_item(
            conn,
            catalog_key="family_role",
            item_key=member["role"],
        )
        capabilities = role_capabilities_from_option(row) or FALLBACK_ROLE_CAPABILITIES.get(
            member["role"],
            [],
        )
        if capability not in capabilities:
            raise ApiError("permission_denied", "当前身份不能进行此操作", 403)
        return member

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

    def _runtime_config_payload(self, row) -> dict:
        provider = str(row["provider"] or "").strip().lower()
        return device_runtime_config_payload(
            row,
            config=runtime_config_json(row),
            adapter_implemented=provider not in RESERVED_RUNTIME_PROVIDERS,
        )

    def _runtime_provider(self, value) -> str:
        provider = str(value or "").strip().lower()
        if not provider:
            raise ApiError("missing_provider", "请选择摄像头运行方式。")
        if provider not in RUNTIME_PROVIDERS:
            raise ApiError("unsupported_runtime_provider", "暂不支持这个摄像头运行方式。")
        if provider in DEVELOPMENT_RUNTIME_PROVIDERS and not self._dev_runtime_allowed():
            raise ApiError(
                "development_adapter_not_allowed",
                "开发摄像头运行方式只能在测试环境中启用。",
                403,
            )
        return provider

    def _dev_runtime_allowed(self) -> bool:
        return self.dev_adapters_enabled and self.app_env in {"development", "test"}

    def _runtime_config(self, provider: str, value) -> dict:
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise ApiError("invalid_runtime_config", "摄像头运行配置格式不正确。")
        self._assert_no_sensitive_config(value, path="config")
        return self._sanitize_config_object(
            value,
            RUNTIME_CONFIG_SCHEMAS[provider],
            path="config",
        )

    def _assert_no_sensitive_config(self, value, *, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key or "")
                compact_key = key_text.replace("-", "_").replace(" ", "").lower()
                if any(part in compact_key for part in SENSITIVE_KEY_PARTS):
                    raise ApiError("sensitive_runtime_config", f"{path}.{key_text} 不能包含敏感配置。")
                self._assert_no_sensitive_config(child, path=f"{path}.{key_text}")
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                self._assert_no_sensitive_config(child, path=f"{path}[{index}]")
            return
        if isinstance(value, str):
            lower_value = value.lower()
            if any(marker in lower_value for marker in SENSITIVE_VALUE_MARKERS):
                raise ApiError("sensitive_runtime_config", f"{path} 不能包含敏感配置。")

    def _sanitize_config_object(self, value: Mapping[str, Any], schema: Mapping[str, Any], *, path: str) -> dict:
        allowed = {key.lower(): (key, spec) for key, spec in schema.items()}
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key or "")
            lookup = key_text.lower()
            if lookup not in allowed:
                raise ApiError("runtime_config_key_not_allowed", f"{path}.{key_text} 暂不支持。")
            canonical_key, spec = allowed[lookup]
            if canonical_key in sanitized:
                raise ApiError("duplicate_runtime_config_key", f"{path}.{key_text} 重复。")
            sanitized[canonical_key] = self._sanitize_config_value(
                child,
                spec,
                path=f"{path}.{canonical_key}",
            )
        return sanitized

    def _sanitize_config_value(self, value, spec, *, path: str):
        if isinstance(spec, dict):
            if not isinstance(value, dict):
                raise ApiError("invalid_runtime_config", f"{path} 格式不正确。")
            return self._sanitize_config_object(value, spec, path=path)
        if spec == "url":
            return self._sanitize_url(value, path=path)
        if spec == "text":
            if not isinstance(value, str):
                raise ApiError("invalid_runtime_config", f"{path} 必须是文本。")
            text = value.strip()
            if not text:
                raise ApiError("invalid_runtime_config", f"{path} 不能为空。")
            if len(text) > 255:
                raise ApiError("invalid_runtime_config", f"{path} 过长。")
            return text
        if spec == "bool":
            if not isinstance(value, bool):
                raise ApiError("invalid_runtime_config", f"{path} 必须是开关值。")
            return value
        if spec == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ApiError("invalid_runtime_config", f"{path} 必须是数字。")
            return value
        raise ApiError("invalid_runtime_config", f"{path} 格式不正确。")

    def _sanitize_url(self, value, *, path: str) -> str:
        if not isinstance(value, str):
            raise ApiError("invalid_runtime_config", f"{path} 必须是链接。")
        url = value.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ApiError("invalid_runtime_config_url", f"{path} 只支持 http/https 链接。")
        if parsed.username or parsed.password:
            raise ApiError("invalid_runtime_config_url", f"{path} 不能包含账号或密码。")
        if len(url) > 512:
            raise ApiError("invalid_runtime_config_url", f"{path} 过长。")
        return url

    def _secret_ref(self, value) -> str | None:
        if value is None:
            return None
        secret_ref = str(value or "").strip()
        if not secret_ref:
            return None
        if len(secret_ref) > 255 or any(char.isspace() for char in secret_ref):
            raise ApiError("invalid_secret_ref", "凭证引用格式不正确。")
        lower_value = secret_ref.lower()
        if any(marker in lower_value for marker in SENSITIVE_VALUE_MARKERS):
            raise ApiError("invalid_secret_ref", "请保存凭证引用，不要填写真实密钥。")
        allowed_prefixes = ("vault://", "kms://", "secret://", "ref://", "arn:")
        if not secret_ref.startswith(allowed_prefixes):
            raise ApiError("invalid_secret_ref", "请使用凭证引用，不要填写真实密钥。")
        return secret_ref

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
