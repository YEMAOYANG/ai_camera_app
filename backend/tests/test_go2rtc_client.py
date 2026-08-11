from __future__ import annotations

import traceback
import unittest
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from integrations.camera_runtime.go2rtc_client import (
    Go2RtcClient,
    Go2RtcConfigurationError,
    Go2RtcProtocolError,
    Go2RtcUnavailableError,
)


class _FakeResponse:
    def __init__(self, body: bytes = b"", *, status: int = 200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit: int = -1) -> bytes:
        if limit < 0:
            return self.body
        return self.body[:limit]


class _RecordingOpener:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        return self.responses.pop(0)


class Go2RtcClientTest(unittest.TestCase):
    def test_rejects_non_http_base_urls_and_userinfo(self):
        for value in (
            "ws://gateway.local:1984",
            "file:///tmp/go2rtc",
            "http://admin:secret@gateway.local:1984",
        ):
            with self.subTest(value=value):
                with self.assertRaises(Go2RtcConfigurationError):
                    Go2RtcClient(value)

    def test_health_and_stream_existence_use_internal_api(self):
        opener = _RecordingOpener(
            [
                _FakeResponse(b'{"version":"1.9.14"}'),
                _FakeResponse(b'{"camera-dev-1":{"producers":[]}}'),
                _FakeResponse(b'{"camera-dev-1":{"producers":[]}}'),
            ]
        )
        client = Go2RtcClient(
            api_base_url="http://127.0.0.1:1984/",
            timeout_seconds=1.25,
            opener=opener,
        )

        self.assertEqual(client.health(), {"version": "1.9.14"})
        self.assertTrue(client.stream_exists("camera-dev-1"))
        self.assertFalse(client.stream_exists("camera-dev-2"))
        self.assertEqual(
            [call[0].full_url for call in opener.calls],
            [
                "http://127.0.0.1:1984/api",
                "http://127.0.0.1:1984/api/streams",
                "http://127.0.0.1:1984/api/streams",
            ],
        )
        self.assertEqual([call[1] for call in opener.calls], [1.25, 1.25, 1.25])

    def test_register_stream_uses_non_persistent_patch_and_encoded_query(self):
        opener = _RecordingOpener([_FakeResponse()])
        captured_requests = []

        def request_factory(*args, **kwargs):
            from urllib.request import Request

            request = Request(*args, **kwargs)
            captured_requests.append(request)
            return request

        client = Go2RtcClient(
            api_base_url="http://gateway.local:1984",
            opener=opener,
            request_factory=request_factory,
        )
        source = "rtsp://admin:p@ss&word@192.168.1.20:554/stream2?mode=live"

        self.assertTrue(client.register_stream("camera_dev-1", source))
        self.assertEqual(len(captured_requests), 1)
        request = captured_requests[0]
        self.assertEqual(request.method, "PATCH")
        parsed = urlsplit(request.full_url)
        self.assertEqual(parsed.path, "/api/streams")
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "name": ["camera_dev-1"],
                "src": [source],
            },
        )

    def test_delete_stream_uses_delete_with_name_as_source(self):
        opener = _RecordingOpener([_FakeResponse()])
        client = Go2RtcClient(
            api_base_url="http://gateway.local:1984",
            opener=opener,
        )

        self.assertTrue(client.delete_stream("camera_dev-1"))
        request = opener.calls[0][0]
        parsed = urlsplit(request.full_url)
        self.assertEqual(request.method, "DELETE")
        self.assertEqual(parsed.path, "/api/streams")
        self.assertEqual(parse_qs(parsed.query), {"src": ["camera_dev-1"]})

    def test_stream_name_rejects_characters_outside_safe_identifier_set(self):
        client = Go2RtcClient(
            api_base_url="http://gateway.local:1984",
            opener=_RecordingOpener([]),
        )

        for name in ("camera dev", "camera/dev", "camera.dev", "摄像头"):
            with self.subTest(name=name):
                with self.assertRaises(Go2RtcConfigurationError):
                    client.websocket_url(name)

    def test_websocket_url_uses_public_scheme_and_never_embeds_credentials(self):
        client = Go2RtcClient(
            api_base_url="http://127.0.0.1:1984",
            public_base_url="https://camera.example.com/media/",
        )

        parsed = urlsplit(client.websocket_url("camera_dev-1"))
        self.assertEqual(parsed.scheme, "wss")
        self.assertEqual(parsed.netloc, "camera.example.com")
        self.assertEqual(parsed.path, "/media/api/ws")
        self.assertEqual(parse_qs(parsed.query), {"src": ["camera_dev-1"]})
        self.assertIsNone(parsed.username)
        self.assertIsNone(parsed.password)

    def test_transport_error_does_not_leak_rtsp_password(self):
        password = "super-secret-camera-password"

        def failing_opener(request, *, timeout):
            raise URLError(f"failed request: {request.full_url}")

        client = Go2RtcClient(
            api_base_url="http://gateway.local:1984",
            opener=failing_opener,
        )

        with self.assertRaises(Go2RtcUnavailableError) as raised:
            client.register_stream(
                "camera-dev-1",
                f"rtsp://admin:{password}@192.168.1.20/stream2",
            )

        rendered = "".join(
            traceback.format_exception_only(type(raised.exception), raised.exception)
        )
        self.assertNotIn(password, str(raised.exception))
        self.assertNotIn(password, rendered)
        self.assertIsNone(raised.exception.__context__)

    def test_invalid_json_is_reported_without_response_detail(self):
        secret = "response-must-stay-private"
        client = Go2RtcClient(
            api_base_url="http://gateway.local:1984",
            opener=_RecordingOpener(
                [_FakeResponse(f"not-json:{secret}".encode("utf-8"))]
            ),
        )

        with self.assertRaises(Go2RtcProtocolError) as raised:
            client.health()

        self.assertNotIn(secret, str(raised.exception))

    def test_is_healthy_converts_gateway_failure_to_false(self):
        def failing_opener(request, *, timeout):
            raise TimeoutError("timeout")

        client = Go2RtcClient(
            api_base_url="http://gateway.local:1984",
            opener=failing_opener,
        )

        self.assertFalse(client.is_healthy())


if __name__ == "__main__":
    unittest.main()
