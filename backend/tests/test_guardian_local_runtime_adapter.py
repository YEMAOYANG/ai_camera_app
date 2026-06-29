from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from integrations.camera_runtime.guardian_local_adapter import GuardianLocalRuntimeAdapter


class GuardianLocalRuntimeAdapterTests(unittest.TestCase):
    def test_delegates_media_to_ai_camera_test_when_base_url_configured(self):
        media = MagicMock()
        media.webrtc_session.return_value = {
            "ok": True,
            "signalingUrl": "ws://127.0.0.1:1984/api/ws?src=ipc45aw_hd",
            "stream": "ipc45aw_hd",
        }
        media.snapshot.return_value = MagicMock(body=b"\xff\xd8\xff\xd9", content_type="image/jpeg")

        with patch(
            "integrations.camera_runtime.guardian_local_adapter.AiCameraTestRuntimeAdapter",
            return_value=media,
        ) as factory:
            adapter = GuardianLocalRuntimeAdapter(media_base_url="http://127.0.0.1:8767")

        factory.assert_called_once_with("http://127.0.0.1:8767", vision_service=None)
        session = adapter.webrtc_session()
        self.assertEqual(session["signalingUrl"], "ws://127.0.0.1:1984/api/ws?src=ipc45aw_hd")
        adapter.snapshot()
        media.snapshot.assert_called_once()

    def test_falls_back_to_mock_media_without_base_url(self):
        adapter = GuardianLocalRuntimeAdapter()
        session = adapter.webrtc_session()
        self.assertIn("src=mock", session["signalingUrl"])


if __name__ == "__main__":
    unittest.main()
