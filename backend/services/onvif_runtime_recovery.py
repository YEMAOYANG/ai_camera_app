from __future__ import annotations

import json
from typing import Any, Mapping

from core.security import now_ms
from integrations.onvif.client import OnvifClient, VerifiedOnvifDevice
from integrations.onvif.identity import onvif_binding_code
from repositories.device_repository import DeviceRepository
from services.device_credential_store import EncryptedFileCredentialStore
from services.onvif_runtime_config import build_onvif_runtime_config


RecoveredOnvifRuntime = tuple[dict[str, Any], VerifiedOnvifDevice]


class OnvifRuntimeRecoveryService:
    """Recover a bound ONVIF device after DHCP changes its local address."""

    def __init__(
        self,
        *,
        repository: DeviceRepository,
        client: OnvifClient,
        credential_store: EncryptedFileCredentialStore,
    ):
        self.repository = repository
        self.client = client
        self.credential_store = credential_store

    def recover(
        self,
        *,
        family_id: str,
        device_id: str,
        secret_ref: str,
        current_config: Mapping[str, Any],
    ) -> RecoveredOnvifRuntime | None:
        state = self._state(
            family_id=family_id,
            device_id=device_id,
        )
        if not self._state_is_eligible(state, secret_ref=secret_ref):
            return None

        binding_code = str(state.get("binding_code") or "")
        candidates = [
            candidate
            for candidate in self.client.discover()
            if candidate.endpoint_reference
            and onvif_binding_code(candidate.endpoint_reference) == binding_code
        ]
        if len(candidates) != 1:
            return None
        candidate = candidates[0]

        credentials = self.credential_store.load_onvif_credentials(secret_ref)
        verified = self.client.inspect_and_verify(
            device_service_url=candidate.device_service_url,
            username=credentials["username"],
            password=credentials["password"],
        )
        if not _verified_identity_matches(
            current_config=current_config,
            endpoint_reference=candidate.endpoint_reference,
            verified=verified,
        ):
            return None

        old_service_url = str(current_config.get("deviceServiceUrl") or "").strip()
        with self.repository.transaction() as conn:
            locked = self.repository.get_onvif_runtime_recovery_state(
                conn,
                family_id=family_id,
                device_id=device_id,
                for_update=True,
            )
            if not self._state_is_eligible(locked, secret_ref=secret_ref):
                return None
            latest_config = _config_json(locked.get("config_json"))
            latest_service_url = str(
                latest_config.get("deviceServiceUrl") or ""
            ).strip()
            if latest_service_url not in {
                old_service_url,
                candidate.device_service_url,
            }:
                return None
            if latest_service_url == candidate.device_service_url:
                return latest_config, verified

            next_config = build_onvif_runtime_config(
                device_service_url=candidate.device_service_url,
                endpoint_reference=candidate.endpoint_reference,
                verified=verified,
                base=latest_config,
            )
            updated = self.repository.update_onvif_runtime_config_json(
                conn,
                runtime_config_id=str(locked["runtime_config_id"]),
                config_json=json.dumps(
                    next_config,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                now=now_ms(),
            )
            if not updated:
                return None
        return next_config, verified

    def _state(
        self,
        *,
        family_id: str,
        device_id: str,
    ) -> Mapping[str, Any]:
        with self.repository.transaction() as conn:
            row = self.repository.get_onvif_runtime_recovery_state(
                conn,
                family_id=family_id,
                device_id=device_id,
                for_update=False,
            )
        return row or {}

    def _state_is_eligible(
        self,
        state: Mapping[str, Any],
        *,
        secret_ref: str,
    ) -> bool:
        return (
            bool(state)
            and str(state.get("device_status") or "") != "unbound"
            and str(state.get("runtime_status") or "") == "active"
            and str(state.get("provider") or "") == "onvif_rtsp"
            and str(state.get("secret_ref") or "") == secret_ref
            and bool(str(state.get("binding_code") or "").strip())
        )


def _verified_identity_matches(
    *,
    current_config: Mapping[str, Any],
    endpoint_reference: str,
    verified: VerifiedOnvifDevice,
) -> bool:
    stored_endpoint = str(
        current_config.get("endpointReference") or ""
    ).strip()
    if stored_endpoint and _identity_text(stored_endpoint) != _identity_text(
        endpoint_reference
    ):
        return False

    profile = current_config.get("deviceProfile")
    stored_profile = dict(profile) if isinstance(profile, Mapping) else {}
    comparisons = (
        ("manufacturer", verified.manufacturer),
        ("model", verified.model),
        ("serialNumber", verified.serial_number),
        (
            "hardwareId",
            verified.hardware_id,
        ),
    )
    for key, actual in comparisons:
        expected = str(
            stored_profile.get(key)
            or (
                current_config.get("hardwareId")
                if key == "hardwareId"
                else ""
            )
            or ""
        ).strip()
        if expected and _identity_text(expected) != _identity_text(actual):
            return False
    return True


def _config_json(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(str(value or ""))
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _identity_text(value: object) -> str:
    return str(value or "").strip().casefold()
