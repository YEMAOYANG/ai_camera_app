from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest

from integrations.openmaic_conversation_probe_client import (
    OpenMaicConversationProbeClient,
    OpenMaicConversationProbeClientError,
)


class _ProbeGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    challenge = "ompc_" + "a" * 43
    session = "omps_" + "b" * 43
    classroom_id = "classroom-1"
    proof_enabled = True

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/mira/probe?ticket=ompt_"):
            self.send_response(204)
            self.send_header("Set-Cookie", "mira_probe=ompr_" + "c" * 43 + "; Path=/; HttpOnly")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(content_length)
        if self.path == "/api/chat":
            if "mira_probe=ompr_" not in self.headers.get("Cookie", ""):
                self._json(401, {"error": "unauthorized"})
                return
            payload = json.loads(body.decode("utf-8"))
            if payload.get("stageId") != self.classroom_id:
                self._json(403, {"error": "wrong_stage"})
                return
            self._raw(200, "data: " + json.dumps(self._proof(payload["probeChallenge"])) + "\n\n", "text/event-stream")
            return
        if self.path == "/api/transcription":
            content = body.decode("latin-1")
            challenge = self.challenge if self.challenge in content else ""
            if 'name="providerId"' in content:
                self._json(400, {"errorCode": "INVALID_REQUEST"})
                return
            self._json(
                200,
                {"proof": {**self._proof(challenge), "asrPolicy": {
                    "providerId": "qwen-asr", "modelId": "qwen3-asr-flash", "fallbackAllowed": False,
                }}},
            )
            return
        self._json(404, {"error": "not_found"})

    def log_message(self, *_args):
        return

    @classmethod
    def _proof(cls, challenge: str) -> dict:
        if not cls.proof_enabled:
            return {}
        return {
            "schemaVersion": "mira.openmaic.conversation-proof.v1",
            "challenge": challenge,
            "runtimeSessionId": cls.session,
            "classroomId": cls.classroom_id,
            "providerCall": False,
        }

    def _json(self, status: int, value: dict):
        self._raw(status, json.dumps(value), "application/json")

    def _raw(self, status: int, value: str, content_type: str):
        raw = value.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class OpenMaicConversationProbeClientTest(unittest.TestCase):
    def setUp(self):
        _ProbeGatewayHandler.proof_enabled = True
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeGatewayHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = OpenMaicConversationProbeClient(
            f"http://127.0.0.1:{self.server.server_port}"
        )
        self.probe = {
            "ticket": "ompt_" + "d" * 43,
            "challenge": _ProbeGatewayHandler.challenge,
            "runtimeId": "runtime-1",
            "classroomId": _ProbeGatewayHandler.classroom_id,
        }

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_verify_proves_gateway_policy_without_provider_calls(self):
        receipts = self.client.verify(self.probe)

        self.assertEqual(receipts["chat"]["noCookieStatus"], 401)
        self.assertEqual(receipts["chat"]["wrongStageStatus"], 403)
        self.assertEqual(receipts["chat"]["proof"]["runtimeSessionId"], _ProbeGatewayHandler.session)
        self.assertFalse(receipts["transcription"]["proof"]["providerCall"])
        self.assertEqual(receipts["transcription"]["proof"]["asrPolicy"]["providerId"], "qwen-asr")
        self.assertEqual(receipts["transcription"]["proof"]["asrPolicy"]["modelId"], "qwen3-asr-flash")

    def test_verify_requires_versioned_gateway_proof(self):
        _ProbeGatewayHandler.proof_enabled = False

        with self.assertRaisesRegex(
            OpenMaicConversationProbeClientError,
            "证明",
        ):
            self.client.verify(self.probe)
        _ProbeGatewayHandler.proof_enabled = True


if __name__ == "__main__":
    unittest.main()
