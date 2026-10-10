"""Optional capability; existing camera adapters need not implement it.

Device implementations atomically acquire an idle speech channel, recheck
sleep/DND, deduplicate requestId, validate expiresAt and appointmentRevision,
and either play immediately or reject. They MUST NOT queue a delayed utterance,
preempt any speaker, change the camera view or stop care/streaming.
"""
from typing import Protocol


class ReviewReminderAdapter(Protocol):
    def review_reminder_capabilities(self) -> dict:
        """All of atomicIdleSpeech, expiry, idempotency, noQueue,
        appointmentRevision, sleepAndQuietHours must be true; schemaVersion=1.
        """
        ...

    def speak_review_if_idle(self, request: dict) -> dict:
        """requestId, appointmentRevision, expiresAt, text, nonPreemptive.

        Return {delivered, requestId, appointmentRevision, playedAt, reason}.
        Acknowledging/queueing is not delivery. No hidden automatic retry.
        """
        ...
