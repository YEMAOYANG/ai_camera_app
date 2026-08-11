from __future__ import annotations

import unittest

from services.camera_signaling_ticket import CameraSignalingTicketStore


class CameraSignalingTicketStoreTest(unittest.TestCase):
    def test_ticket_is_scoped_and_can_only_be_consumed_once(self):
        now = [1_000]
        store = CameraSignalingTicketStore(
            ttl_seconds=60,
            clock_ms=lambda: now[0],
        )

        ticket = store.issue(
            family_id="family-1",
            user_id="user-1",
            session_id="session-1",
            device_id="device-1",
            stream_name="mira_stream_preview",
        )
        record = store.consume(ticket)

        self.assertEqual(record.family_id, "family-1")
        self.assertEqual(record.user_id, "user-1")
        self.assertEqual(record.session_id, "session-1")
        self.assertEqual(record.device_id, "device-1")
        self.assertEqual(record.stream_name, "mira_stream_preview")
        with self.assertRaises(ValueError):
            store.consume(ticket)

    def test_expired_and_unknown_tickets_are_rejected(self):
        now = [1_000]
        store = CameraSignalingTicketStore(
            ttl_seconds=10,
            clock_ms=lambda: now[0],
        )
        ticket = store.issue(
            family_id="family-1",
            user_id="user-1",
            session_id="session-1",
            device_id="device-1",
            stream_name="mira_stream_preview",
        )

        now[0] += 10_001
        with self.assertRaises(ValueError):
            store.consume(ticket)
        with self.assertRaises(ValueError):
            store.consume("camera_ws_unknown")


if __name__ == "__main__":
    unittest.main()
