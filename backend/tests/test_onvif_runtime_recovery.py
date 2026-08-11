from __future__ import annotations

import json
import unittest
from contextlib import contextmanager

from integrations.camera_runtime.onvif_rtsp_adapter import OnvifRtspRuntimeAdapter
from integrations.onvif.client import (
    DiscoveredOnvifDevice,
    OnvifAuthenticationError,
    OnvifUnavailableError,
    VerifiedOnvifDevice,
)
from integrations.onvif.identity import onvif_binding_code
from services.onvif_runtime_recovery import OnvifRuntimeRecoveryService


class OnvifRuntimeRecoveryServiceTest(unittest.TestCase):
    def test_recovers_same_endpoint_at_new_ip_and_persists_no_rtsp(self):
        endpoint = "urn:uuid:t62-stable"
        current = _runtime_config("http://192.168.1.20/onvif/device_service")
        repository = _RecoveryRepository(
            binding_code=onvif_binding_code(endpoint),
            config=current,
        )
        client = _RecoveryClient(
            endpoint=endpoint,
            service_url="http://192.168.1.99/onvif/device_service",
        )
        service = OnvifRuntimeRecoveryService(
            repository=repository,
            client=client,
            credential_store=_Store(),
        )

        recovered = service.recover(
            family_id="fam_1",
            device_id="dev_1",
            secret_ref="secret://onvif/one",
            current_config=current,
        )

        self.assertIsNotNone(recovered)
        config, _ = recovered
        self.assertEqual(
            config["deviceServiceUrl"],
            "http://192.168.1.99/onvif/device_service",
        )
        self.assertEqual(config["endpointReference"], endpoint)
        self.assertEqual(config["hardwareId"], "HW-001")
        stored = json.dumps(repository.config)
        self.assertNotIn("rtsp://", stored)
        self.assertNotIn("123456", stored)
        self.assertEqual(repository.secret_ref, "secret://onvif/one")
        self.assertEqual(repository.update_count, 1)

    def test_different_endpoint_or_serial_cannot_take_over_binding(self):
        current = _runtime_config("http://192.168.1.20/onvif/device_service")
        repository = _RecoveryRepository(
            binding_code=onvif_binding_code("urn:uuid:expected"),
            config=current,
        )
        wrong_endpoint = _RecoveryClient(
            endpoint="urn:uuid:other",
            service_url="http://192.168.1.99/onvif/device_service",
        )
        service = OnvifRuntimeRecoveryService(
            repository=repository,
            client=wrong_endpoint,
            credential_store=_Store(),
        )
        self.assertIsNone(
            service.recover(
                family_id="fam_1",
                device_id="dev_1",
                secret_ref="secret://onvif/one",
                current_config=current,
            )
        )
        self.assertEqual(wrong_endpoint.inspect_count, 0)
        self.assertEqual(repository.update_count, 0)

        correct_endpoint = _RecoveryClient(
            endpoint="urn:uuid:expected",
            service_url="http://192.168.1.99/onvif/device_service",
            verified=VerifiedOnvifDevice(
                **{
                    **_verified().__dict__,
                    "serial_number": "OTHER-SERIAL",
                }
            ),
        )
        service = OnvifRuntimeRecoveryService(
            repository=repository,
            client=correct_endpoint,
            credential_store=_Store(),
        )
        self.assertIsNone(
            service.recover(
                family_id="fam_1",
                device_id="dev_1",
                secret_ref="secret://onvif/one",
                current_config=current,
            )
        )
        self.assertEqual(repository.update_count, 0)


class OnvifRuntimeAdapterRecoveryTest(unittest.TestCase):
    def test_snapshot_retries_once_with_recovered_runtime(self):
        verified = _verified()

        class _Client:
            def __init__(self):
                self.snapshot_urls = []

            def fetch_snapshot(self, **kwargs):
                service_url = kwargs["device_service_url"]
                self.snapshot_urls.append(service_url)
                if "192.168.1.20" in service_url:
                    raise OnvifUnavailableError("old IP unavailable")
                return b"jpeg", "image/jpeg"

        client = _Client()
        recovery_calls = []

        def recover(config):
            recovery_calls.append(dict(config))
            return (
                _runtime_config(
                    "http://192.168.1.99/onvif/device_service"
                ),
                verified,
            )

        adapter = OnvifRtspRuntimeAdapter(
            config=_runtime_config(
                "http://192.168.1.20/onvif/device_service"
            ),
            secret_ref="secret://onvif/one",
            client=client,
            credential_store=_Store(),
            recover_runtime=recover,
        )

        snapshot = adapter.snapshot()

        self.assertEqual(snapshot.body, b"jpeg")
        self.assertEqual(len(recovery_calls), 1)
        self.assertEqual(
            client.snapshot_urls,
            [
                "http://192.168.1.20/onvif/device_service",
                "http://192.168.1.99/onvif/device_service",
            ],
        )

    def test_authentication_error_never_triggers_rediscovery(self):
        class _Client:
            def fetch_snapshot(self, **_kwargs):
                raise OnvifAuthenticationError("bad credentials")

        recovery_calls = []
        adapter = OnvifRtspRuntimeAdapter(
            config=_runtime_config(
                "http://192.168.1.20/onvif/device_service"
            ),
            secret_ref="secret://onvif/one",
            client=_Client(),
            credential_store=_Store(),
            recover_runtime=lambda config: recovery_calls.append(config),
        )

        with self.assertRaises(OnvifAuthenticationError):
            adapter.snapshot()
        self.assertEqual(recovery_calls, [])


class _RecoveryRepository:
    def __init__(self, *, binding_code, config):
        self.binding_code = binding_code
        self.config = dict(config)
        self.secret_ref = "secret://onvif/one"
        self.update_count = 0

    @contextmanager
    def transaction(self):
        yield self

    def get_onvif_runtime_recovery_state(
        self,
        _conn,
        *,
        family_id,
        device_id,
        for_update,
    ):
        return {
            "binding_code": self.binding_code,
            "device_status": "bound",
            "runtime_config_id": "runtime_1",
            "provider": "onvif_rtsp",
            "config_json": json.dumps(self.config),
            "secret_ref": self.secret_ref,
            "runtime_status": "active",
        }

    def update_onvif_runtime_config_json(
        self,
        _conn,
        *,
        runtime_config_id,
        config_json,
        now,
    ):
        self.config = json.loads(config_json)
        self.update_count += 1
        return True


class _RecoveryClient:
    def __init__(self, *, endpoint, service_url, verified=None):
        self.endpoint = endpoint
        self.service_url = service_url
        self.verified = verified or _verified()
        self.inspect_count = 0

    def discover(self):
        return [
            DiscoveredOnvifDevice(
                endpoint_reference=self.endpoint,
                device_service_url=self.service_url,
                scopes=(),
                types=("dn:NetworkVideoTransmitter",),
                display_name="T62",
            )
        ]

    def inspect_and_verify(self, **_kwargs):
        self.inspect_count += 1
        return self.verified


class _Store:
    def load_onvif_credentials(self, _secret_ref):
        return {"username": "admin", "password": "123456"}


def _runtime_config(service_url):
    return {
        "deviceServiceUrl": service_url,
        "profileToken": "MainStreamToken",
        "deviceProfile": {
            "manufacturer": "Vatilon",
            "model": "T62",
            "serialNumber": "SERIAL-001",
        },
    }


def _verified():
    return VerifiedOnvifDevice(
        manufacturer="Vatilon",
        model="T62",
        firmware_version="V1",
        serial_number="SERIAL-001",
        hardware_id="HW-001",
        profile_token="MainStreamToken",
        profile_name="MainStream",
        video_encoding="H264",
        width=1920,
        height=1080,
        audio_encoding="G711",
        has_ptz=False,
        has_audio=True,
        rtsp_uri="rtsp://192.168.1.99/stream1",
        preview_profile_token="SubStreamToken",
        preview_profile_name="SubStream",
        preview_video_encoding="H264",
        preview_width=640,
        preview_height=480,
        preview_audio_encoding="G711",
        preview_rtsp_uri="rtsp://192.168.1.99/stream2",
    )


if __name__ == "__main__":
    unittest.main()
