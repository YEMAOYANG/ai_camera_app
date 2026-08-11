from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from core.database import Database
from core.security import hash_value
from integrations.camera_runtime.onvif_rtsp_adapter import OnvifRtspRuntimeAdapter
from integrations.camera_runtime.onvif_rtsp_adapter import (
    _rtsp_uri_with_credentials,
)
from integrations.onvif.client import (
    DiscoveredOnvifDevice,
    OnvifClient,
    OnvifProtocolError,
    VerifiedOnvifDevice,
    _RejectRedirectHandler,
    _probe_send_offsets,
    _select_preview_profile,
    normalize_local_service_url,
    normalize_local_target_ip,
)
from services.camera_bridge_service import CameraBridgeService
from services.device_credential_store import EncryptedFileCredentialStore
from services.device_runtime_resolver import onvif_preview_stream_name
from tests.support import fresh_test_config, request_debug_code


def _verified_device(
    *,
    manufacturer: str = "Vatilon",
    model: str = "T62",
) -> VerifiedOnvifDevice:
    return VerifiedOnvifDevice(
        manufacturer=manufacturer,
        model=model,
        firmware_version="V1.17.74",
        serial_number="SERIAL-001",
        hardware_id="HW-001",
        profile_token="MainStreamToken",
        profile_name="MainStream",
        video_encoding="H264",
        width=3200,
        height=1800,
        audio_encoding="G711",
        has_ptz=True,
        has_audio=True,
        rtsp_uri="rtsp://192.168.10.20:554/stream1",
    )


class _FakeOnvifClient:
    def __init__(self):
        self.candidates = [
            DiscoveredOnvifDevice(
                endpoint_reference="urn:uuid:t62-test",
                device_service_url="http://192.168.10.20/onvif/device_service",
                scopes=(
                    "onvif://www.onvif.org/manufacturer/Vatilon",
                    "onvif://www.onvif.org/hardware/T62",
                    "onvif://www.onvif.org/name/T62",
                    "onvif://www.onvif.org/type/audio_encoder",
                    "onvif://www.onvif.org/type/ptz",
                ),
                types=("dn:NetworkVideoTransmitter",),
                display_name="T62",
                manufacturer_hint="Vatilon",
                model_hint="T62",
            ),
            DiscoveredOnvifDevice(
                endpoint_reference="urn:uuid:unsupported-camera",
                device_service_url="http://192.168.10.21/onvif/device_service",
                scopes=(),
                types=("dn:NetworkVideoTransmitter",),
                display_name="Other Camera",
                manufacturer_hint="Other",
                model_hint="IPC",
            ),
        ]
        self.verified = _verified_device()
        self.last_target_ip = None
        self.last_timeout_ms = None
        self.last_username = None
        self.last_password = None
        self.inspect_count = 0
        self.expected_password = "camera-password"

    def discover(self, *, target_ip=None, timeout_ms=None):
        self.last_target_ip = target_ip
        self.last_timeout_ms = timeout_ms
        return list(self.candidates)

    def inspect_and_verify(self, *, device_service_url, username, password):
        self.inspect_count += 1
        self.last_username = username
        self.last_password = password
        if username != "admin" or password != self.expected_password:
            raise AssertionError("test credentials did not reach fake ONVIF client")
        return self.verified

    def fetch_snapshot(self, **kwargs):
        return b"\xff\xd8\xff\xd9", "image/jpeg"


class OnvifDeviceApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.credential_store = EncryptedFileCredentialStore(
            root=root / "secrets",
            key_file=root / "device-secret.key",
            allow_key_generation=True,
        )
        self.onvif_client = _FakeOnvifClient()
        self.client_patch = patch(
            "services.service_factory.onvif_client",
            return_value=self.onvif_client,
        )
        self.store_patch = patch(
            "services.service_factory.device_credential_store",
            return_value=self.credential_store,
        )
        self.client_patch.start()
        self.store_patch.start()
        self.app = create_app(
            fresh_test_config(
                ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED=True,
                ONVIF_BOOTSTRAP_USERNAME="admin",
                ONVIF_BOOTSTRAP_PASSWORD="camera-password",
            )
        )
        self.client = self.app.test_client()
        code = request_debug_code(self.client, "13800002991")
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002991", "code": code},
        )
        self.assertEqual(login.status_code, 200, login.json)
        self.access_token = login.json["tokens"]["accessToken"]
        self.family_id = login.json["family"]["id"]
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(parent.status_code, 200, parent.json)

    def tearDown(self):
        self.store_patch.stop()
        self.client_patch.stop()
        self.temp_dir.cleanup()

    def test_discovery_pair_redacts_secrets_filters_bound_and_cleans_up_on_unbind(self):
        discovery = self.client.post(
            "/api/devices/discovery/onvif",
            json={"targetIp": "192.168.10.20", "timeoutMs": 8000},
            headers=self._auth_headers(),
        )
        self.assertEqual(discovery.status_code, 200, discovery.json)
        self.assertEqual(self.onvif_client.last_target_ip, "192.168.10.20")
        self.assertEqual(self.onvif_client.last_timeout_ms, 5000)
        self.assertEqual(len(discovery.json["candidates"]), 1)
        candidate = discovery.json["candidates"][0]
        self.assertTrue(candidate["supported"])
        self.assertEqual(candidate["bindingState"], "available")
        self.assertFalse(candidate["requiresCredentials"])
        self.assertFalse(candidate["capabilities"]["ptz"])
        self.assertNotIn("192.168.", json.dumps(discovery.json))
        self.assertNotIn("deviceServiceUrl", json.dumps(discovery.json))

        self.onvif_client.expected_password = " camera-password "
        pair = self.client.post(
            "/api/devices/pair/onvif",
            json={
                "discoveryToken": candidate["discoveryToken"],
                "username": "admin",
                "password": " camera-password ",
                "name": "儿童房摄像头",
                "location": "儿童房",
                "setAsDefault": True,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(pair.status_code, 200, pair.json)
        response_text = json.dumps(pair.json)
        self.assertNotIn("camera-password", response_text)
        self.assertNotIn("rtsp://", response_text)
        self.assertNotIn("192.168.", response_text)
        self.assertTrue(pair.json["connection"]["verified"])
        self.assertFalse(pair.json["connection"]["liveReady"])
        self.assertFalse(pair.json["connection"]["capabilities"]["ptz"])
        device_id = pair.json["device"]["id"]

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            runtime_row = conn.execute(
                """
                SELECT * FROM device_runtime_configs
                WHERE family_id = ? AND device_id = ?
                """,
                (self.family_id, device_id),
            ).fetchone()
        self.assertEqual(runtime_row["provider"], "onvif_rtsp")
        self.assertTrue(str(runtime_row["secret_ref"]).startswith("secret://onvif/"))
        self.assertNotIn("camera-password", str(runtime_row["config_json"]))
        self.assertNotIn("rtsp://", str(runtime_row["config_json"]))
        private_runtime = json.loads(str(runtime_row["config_json"]))
        self.assertEqual(
            private_runtime["endpointReference"],
            "urn:uuid:t62-test",
        )
        self.assertEqual(private_runtime["hardwareId"], "HW-001")
        credential_id = str(runtime_row["secret_ref"]).rsplit("/", 1)[-1]
        credential_path = Path(self.temp_dir.name) / "secrets" / f"{credential_id}.token"
        self.assertTrue(credential_path.exists())
        self.assertNotIn(b"camera-password", credential_path.read_bytes())
        self.assertEqual(
            self.credential_store.load_onvif_credentials(runtime_row["secret_ref"]),
            {"username": "admin", "password": " camera-password "},
        )

        runtime = self.client.get(
            f"/api/devices/{device_id}/runtime-config",
            headers=self._auth_headers(),
        )
        self.assertEqual(runtime.status_code, 200, runtime.json)
        runtime_payload = runtime.json["runtimeConfig"]
        self.assertTrue(runtime_payload["adapterImplemented"])
        self.assertTrue(runtime_payload["hasSecretRef"])
        runtime_text = json.dumps(runtime_payload)
        self.assertNotIn("secretRef", runtime_payload)
        self.assertNotIn("deviceServiceUrl", runtime_text)
        self.assertNotIn("endpointReference", runtime_text)
        self.assertNotIn("hardwareId", runtime_text)
        self.assertNotIn("profileToken", runtime_text)
        self.assertNotIn("serialNumber", runtime_text)
        self.assertNotIn("192.168.", runtime_text)

        rediscovery = self.client.post(
            "/api/devices/discovery/onvif",
            json={},
            headers=self._auth_headers(),
        )
        self.assertEqual(rediscovery.status_code, 200, rediscovery.json)
        self.assertEqual(rediscovery.json["candidates"], [])

        unbind = self.client.post(
            f"/api/devices/{device_id}/unbind",
            headers=self._auth_headers(),
        )
        self.assertEqual(unbind.status_code, 200, unbind.json)
        self.assertFalse(credential_path.exists())

    def test_expired_token_and_pair_time_model_allowlist(self):
        self.onvif_client.candidates = [
            DiscoveredOnvifDevice(
                endpoint_reference="urn:uuid:no-scopes",
                device_service_url="http://192.168.10.30/onvif/device_service",
                scopes=(),
                types=("dn:NetworkVideoTransmitter",),
                display_name="AI 看护摄像头",
            )
        ]
        automatic = self.client.post(
            "/api/devices/discovery/onvif",
            json={"timeoutMs": 2500},
            headers=self._auth_headers(),
        )
        self.assertEqual(automatic.status_code, 200, automatic.json)
        self.assertEqual(automatic.json["candidates"], [])
        discovery = self.client.post(
            "/api/devices/discovery/onvif",
            json={"targetIp": "192.168.10.30", "timeoutMs": 2500},
            headers=self._auth_headers(),
        )
        token = discovery.json["candidates"][0]["discoveryToken"]
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            conn.execute(
                """
                UPDATE onvif_discovery_sessions
                SET expires_at = 0
                WHERE token_hash = ?
                """,
                (hash_value(token),),
            )
        expired = self._pair(token)
        self.assertEqual(expired.status_code, 410, expired.json)
        self.assertEqual(expired.json["error"], "onvif_discovery_token_expired")
        self.assertEqual(self.onvif_client.inspect_count, 0)

        fresh = self.client.post(
            "/api/devices/discovery/onvif",
            json={"targetIp": "192.168.10.30"},
            headers=self._auth_headers(),
        )
        fresh_token = fresh.json["candidates"][0]["discoveryToken"]
        self.onvif_client.verified = _verified_device(
            manufacturer="TP-LINK",
            model="TP-IPC",
        )
        unsupported = self._pair(fresh_token)
        self.assertEqual(unsupported.status_code, 422, unsupported.json)
        self.assertEqual(unsupported.json["error"], "onvif_device_unsupported")
        secret_files = list((Path(self.temp_dir.name) / "secrets").glob("*.token"))
        self.assertEqual(secret_files, [])

    def test_pair_uses_engineering_credentials_when_request_omits_them(self):
        discovery = self.client.post(
            "/api/devices/discovery/onvif",
            json={"targetIp": "192.168.10.20"},
            headers=self._auth_headers(),
        )
        self.assertEqual(discovery.status_code, 200, discovery.json)
        token = discovery.json["candidates"][0]["discoveryToken"]

        missing_password = self.client.post(
            "/api/devices/pair/onvif",
            json={"discoveryToken": token, "username": "admin"},
            headers=self._auth_headers(),
        )
        self.assertEqual(missing_password.status_code, 400, missing_password.json)
        self.assertEqual(missing_password.json["error"], "missing_password")
        self.assertEqual(self.onvif_client.inspect_count, 0)

        missing_username = self.client.post(
            "/api/devices/pair/onvif",
            json={"discoveryToken": token, "password": "camera-password"},
            headers=self._auth_headers(),
        )
        self.assertEqual(missing_username.status_code, 400, missing_username.json)
        self.assertEqual(missing_username.json["error"], "missing_username")
        self.assertEqual(self.onvif_client.inspect_count, 0)

        pair = self.client.post(
            "/api/devices/pair/onvif",
            json={
                "discoveryToken": token,
                "name": "智能摄像机",
                "location": "儿童房",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(pair.status_code, 200, pair.json)
        self.assertEqual(self.onvif_client.last_username, "admin")
        self.assertEqual(self.onvif_client.last_password, "camera-password")
        self.assertNotIn("camera-password", json.dumps(pair.json))

    def test_invalid_timeout_is_rejected_before_network(self):
        for value in ("slow", float("nan"), float("inf"), True):
            response = self.client.post(
                "/api/devices/discovery/onvif",
                json={"timeoutMs": value},
                headers=self._auth_headers(),
            )
            self.assertEqual(response.status_code, 400, response.json)
            self.assertEqual(response.json["error"], "invalid_onvif_timeout")
        self.assertIsNone(self.onvif_client.last_timeout_ms)

    def _pair(self, token: str):
        return self.client.post(
            "/api/devices/pair/onvif",
            json={
                "discoveryToken": token,
                "username": "admin",
                "password": "camera-password",
            },
            headers=self._auth_headers(),
        )

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


class OnvifSecurityAndRuntimeTest(unittest.TestCase):
    def test_preview_profile_prefers_bounded_h264_substream(self):
        profile = _select_preview_profile(
            [
                {
                    "token": "MainStreamToken",
                    "name": "MainStream",
                    "video_encoding": "H264",
                    "width": 3200,
                    "height": 1800,
                    "audio_encoding": "G711",
                },
                {
                    "token": "SubStreamToken",
                    "name": "SubStream",
                    "video_encoding": "H.264",
                    "width": 640,
                    "height": 480,
                    "audio_encoding": "G711",
                },
            ]
        )

        self.assertEqual(profile["token"], "SubStreamToken")

    def test_discovery_schedules_three_distinct_probes_inside_timeout(self):
        offsets = _probe_send_offsets(2.5)

        self.assertEqual(len(offsets), 3)
        self.assertEqual(offsets[0], 0)
        self.assertEqual(list(offsets), sorted(offsets))
        self.assertLess(offsets[-1], 2.5)

    def test_probe_response_must_match_udp_sender_and_be_network_video_transmitter(self):
        body = b"""<?xml version="1.0"?>
        <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
          xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
          xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing">
          <s:Body><d:ProbeMatches><d:ProbeMatch>
            <a:EndpointReference><a:Address>urn:uuid:t62</a:Address></a:EndpointReference>
            <d:Types>dn:NetworkVideoTransmitter</d:Types>
            <d:Scopes>onvif://www.onvif.org/manufacturer/Vatilon onvif://www.onvif.org/hardware/T62</d:Scopes>
            <d:XAddrs>http://192.168.10.20/onvif/device_service</d:XAddrs>
          </d:ProbeMatch></d:ProbeMatches></s:Body>
        </s:Envelope>"""
        client = OnvifClient()
        accepted = client._parse_probe_responses([(body, "192.168.10.20")])
        self.assertEqual(len(accepted), 1)
        rejected = client._parse_probe_responses([(body, "192.168.10.99")])
        self.assertEqual(rejected, [])
        non_camera = body.replace(b"NetworkVideoTransmitter", b"Computer")
        self.assertEqual(
            client._parse_probe_responses([(non_camera, "192.168.10.20")]),
            [],
        )

    def test_local_target_validation_rejects_ssrf_addresses_and_redirects(self):
        self.assertEqual(normalize_local_target_ip("192.168.10.20"), "192.168.10.20")
        for value in ("127.0.0.1", "169.254.169.254", "0.0.0.0", "8.8.8.8"):
            with self.assertRaises(OnvifProtocolError):
                normalize_local_target_ip(value)
        with self.assertRaises(OnvifProtocolError):
            normalize_local_service_url("http://127.0.0.1/onvif/device_service")
        handler = _RejectRedirectHandler()
        self.assertIsNone(
            handler.redirect_request(
                None,
                None,
                302,
                "Found",
                {},
                "http://192.168.10.99/admin",
            )
        )

    def test_encrypted_store_never_writes_plain_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = EncryptedFileCredentialStore(
                root=root / "secrets",
                key_file=root / "key",
                allow_key_generation=True,
            )
            secret_ref = store.store_onvif_credentials(
                username="admin",
                password="do-not-write-plain",
            )
            credential_id = secret_ref.rsplit("/", 1)[-1]
            encrypted = (root / "secrets" / f"{credential_id}.token").read_bytes()
            self.assertNotIn(b"do-not-write-plain", encrypted)
            self.assertEqual(
                store.load_onvif_credentials(secret_ref),
                {"username": "admin", "password": "do-not-write-plain"},
            )
            store.delete(secret_ref)
            self.assertFalse((root / "secrets" / f"{credential_id}.token").exists())

    def test_runtime_reports_snapshot_only_until_media_gateway_exists(self):
        client = _FakeOnvifClient()

        class _Store:
            def load_onvif_credentials(self, secret_ref):
                return {"username": "admin", "password": "camera-password"}

        adapter = OnvifRtspRuntimeAdapter(
            config={
                "deviceServiceUrl": "http://192.168.10.20/onvif/device_service",
                "profileToken": "MainStreamToken",
            },
            secret_ref="secret://onvif/test",
            client=client,
            credential_store=_Store(),
        )
        status = CameraBridgeService(adapter=adapter).status()["status"]
        self.assertEqual(status["connectionStatus"], "online")
        self.assertFalse(status["streamAvailable"])
        self.assertTrue(status["snapshotAvailable"])
        self.assertFalse(status["ptzAvailable"])
        self.assertFalse(status["monitorAvailable"])
        self.assertFalse(status["speakerAvailable"])

    def test_gateway_health_does_not_register_and_session_registers_once(self):
        client = _FakeOnvifClient()
        client.expected_password = "p@ss word"
        client.verified = VerifiedOnvifDevice(
            **{
                **_verified_device().__dict__,
                "preview_profile_token": "SubStreamToken",
                "preview_profile_name": "SubStream",
                "preview_video_encoding": "H264",
                "preview_width": 640,
                "preview_height": 480,
                "preview_audio_encoding": "G711",
                "preview_rtsp_uri": "rtsp://192.168.10.20:554/stream2",
            }
        )

        class _Store:
            def load_onvif_credentials(self, secret_ref):
                return {
                    "username": "admin",
                    "password": "p@ss word",
                }

        class _Gateway:
            def __init__(self):
                self.exists = False
                self.registered = []

            def is_healthy(self):
                return True

            def stream_exists(self, name):
                return self.exists

            def register_stream(self, name, source):
                self.registered.append((name, source))
                self.exists = True

            def websocket_url(self, name):
                return f"ws://127.0.0.1:1984/api/ws?src={name}"

        gateway = _Gateway()
        adapter = OnvifRtspRuntimeAdapter(
            config={
                "deviceServiceUrl": "http://192.168.10.20/onvif/device_service",
                "profileToken": "MainStreamToken",
            },
            secret_ref="secret://onvif/test",
            client=client,
            credential_store=_Store(),
            media_gateway=gateway,
            stream_name="mira_test_preview",
        )

        status = CameraBridgeService(adapter=adapter).status()["status"]
        self.assertTrue(status["streamAvailable"])
        self.assertEqual(gateway.registered, [])

        first = adapter.webrtc_session()
        second = adapter.webrtc_session()
        self.assertEqual(first["stream"], "mira_test_preview")
        self.assertEqual(second["stream"], "mira_test_preview")
        self.assertEqual(len(gateway.registered), 1)
        source = gateway.registered[0][1]
        self.assertIn("admin:p%40ss%20word@", source)
        self.assertTrue(source.endswith("/stream2"))
        self.assertNotIn("/stream1", source)

    def test_rtsp_credentials_and_stream_identity_are_private_and_stable(self):
        source = _rtsp_uri_with_credentials(
            "rtsp://192.168.10.20:554/stream2",
            username="admin/name",
            password="p@ss?#",
        )
        self.assertEqual(
            source,
            "rtsp://admin%2Fname:p%40ss%3F%23@192.168.10.20:554/stream2",
        )
        first = onvif_preview_stream_name(
            "dev-1",
            "secret://onvif/one",
        )
        second = onvif_preview_stream_name(
            "dev-1",
            "secret://onvif/two",
        )
        self.assertNotEqual(first, second)
        self.assertNotIn("dev-1", first)
        self.assertNotIn("onvif", first)


if __name__ == "__main__":
    unittest.main()
