from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from core.errors import ApiError


class EncryptedFileCredentialStore:
    """Development/single-node credential store behind the existing secret_ref boundary.

    Production deployments should pass a stable key through configuration and mount
    the storage directory on durable, access-controlled storage, or replace this
    implementation with a managed secret store that keeps the same secret_ref API.
    """

    def __init__(
        self,
        *,
        root: str | Path,
        key: str | bytes | None = None,
        key_file: str | Path | None = None,
        allow_key_generation: bool = False,
    ):
        self.root = Path(root)
        self.key_file = Path(key_file) if key_file else None
        self.allow_key_generation = bool(allow_key_generation)
        self._configured_key = key
        self._fernet: Fernet | None = None

    def store_onvif_credentials(self, *, username: str, password: str) -> str:
        credential_id = uuid.uuid4().hex
        payload = json.dumps(
            {"username": username, "password": password},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        encrypted = self._fernet_instance().encrypt(payload)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{credential_id}.",
            suffix=".tmp",
            dir=self.root,
            delete=False,
        )
        temporary_path = Path(handle.name)
        try:
            with handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._credential_path(credential_id))
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return f"secret://onvif/{credential_id}"

    def load_onvif_credentials(self, secret_ref: str) -> dict[str, str]:
        credential_id = self._credential_id(secret_ref)
        try:
            encrypted = self._credential_path(credential_id).read_bytes()
            decoded = self._fernet_instance().decrypt(encrypted)
            payload = json.loads(decoded.decode("utf-8"))
        except (OSError, InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(
                "device_credentials_unavailable",
                "摄像头凭证暂时不可用，请重新绑定设备。",
                503,
            ) from exc
        username = str(payload.get("username") or "")
        password = str(payload.get("password") or "")
        if not username or not password:
            raise ApiError(
                "device_credentials_unavailable",
                "摄像头凭证暂时不可用，请重新绑定设备。",
                503,
            )
        return {"username": username, "password": password}

    def delete(self, secret_ref: str) -> None:
        try:
            credential_id = self._credential_id(secret_ref)
        except ApiError:
            return
        self._credential_path(credential_id).unlink(missing_ok=True)

    def _load_key(self, configured_key: str | bytes | None) -> bytes:
        if configured_key:
            key = configured_key.encode("ascii") if isinstance(configured_key, str) else configured_key
            return self._validate_key(key)
        if self.key_file and self.key_file.exists():
            return self._validate_key(self.key_file.read_bytes().strip())
        if not self.allow_key_generation or self.key_file is None:
            raise ApiError(
                "device_credential_store_not_configured",
                "摄像头凭证存储尚未配置。",
                503,
            )
        key = Fernet.generate_key()
        self.key_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                self.key_file,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            return self._validate_key(self.key_file.read_bytes().strip())
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
        return key

    def _fernet_instance(self) -> Fernet:
        if self._fernet is None:
            self._fernet = Fernet(self._load_key(self._configured_key))
        return self._fernet

    def _validate_key(self, key: bytes) -> bytes:
        try:
            Fernet(key)
        except (TypeError, ValueError) as exc:
            raise ApiError(
                "device_credential_store_not_configured",
                "摄像头凭证加密密钥格式不正确。",
                503,
            ) from exc
        return key

    def _credential_id(self, secret_ref: str) -> str:
        prefix = "secret://onvif/"
        value = str(secret_ref or "")
        credential_id = value[len(prefix) :] if value.startswith(prefix) else ""
        if not credential_id or len(credential_id) != 32:
            raise ApiError(
                "device_credentials_unavailable",
                "摄像头凭证引用无效。",
                503,
            )
        try:
            int(credential_id, 16)
        except ValueError as exc:
            raise ApiError(
                "device_credentials_unavailable",
                "摄像头凭证引用无效。",
                503,
            ) from exc
        return credential_id

    def _credential_path(self, credential_id: str) -> Path:
        return self.root / f"{credential_id}.token"
