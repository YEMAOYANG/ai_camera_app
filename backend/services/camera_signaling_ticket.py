from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from core.security import hash_value, new_token, now_ms


@dataclass(frozen=True)
class CameraSignalingTicket:
    family_id: str
    user_id: str
    session_id: str
    device_id: str
    stream_name: str
    expires_at: int


class CameraSignalingTicketStore:
    """Process-local, one-time tickets for the colocated WebSocket proxy."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 60,
        clock_ms: Callable[[], int] = now_ms,
    ):
        self.ttl_ms = max(10, min(int(ttl_seconds), 120)) * 1000
        self.clock_ms = clock_ms
        self._lock = threading.Lock()
        self._tickets: dict[str, CameraSignalingTicket] = {}

    def issue(
        self,
        *,
        family_id: str,
        user_id: str,
        session_id: str,
        device_id: str,
        stream_name: str,
    ) -> str:
        issued_at = self.clock_ms()
        ticket = new_token("camera_ws")
        record = CameraSignalingTicket(
            family_id=_required_value(family_id),
            user_id=_required_value(user_id),
            session_id=_required_value(session_id),
            device_id=_required_value(device_id),
            stream_name=_required_value(stream_name),
            expires_at=issued_at + self.ttl_ms,
        )
        with self._lock:
            self._prune_locked(issued_at)
            self._tickets[hash_value(ticket)] = record
        return ticket

    def consume(self, ticket: str) -> CameraSignalingTicket:
        value = str(ticket or "").strip()
        if not value:
            raise ValueError("camera signaling ticket is missing")
        current_time = self.clock_ms()
        with self._lock:
            self._prune_locked(current_time)
            record = self._tickets.pop(hash_value(value), None)
        if record is None or record.expires_at <= current_time:
            raise ValueError("camera signaling ticket is invalid")
        return record

    def _prune_locked(self, current_time: int) -> None:
        expired = [
            key
            for key, record in self._tickets.items()
            if record.expires_at <= current_time
        ]
        for key in expired:
            self._tickets.pop(key, None)


def _required_value(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("camera signaling ticket scope is incomplete")
    return text


camera_signaling_ticket_store = CameraSignalingTicketStore()
