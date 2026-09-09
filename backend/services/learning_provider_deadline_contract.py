from __future__ import annotations


FORMAL_PROVIDER_ATTEMPT_HARD_DEADLINE_MS = 30 * 60 * 1000
FORMAL_PROVIDER_ATTEMPT_MAX_CONTINUATION_MS = 90 * 60 * 1000


def provider_attempt_deadline_is_valid(
    attempt_started_at: object,
    attempt_hard_deadline_at: object,
) -> bool:
    """Accept the normal window or one bounded checkpoint continuation.

    A continuation never changes Provider call identity or replays a completed
    phase. The item and every durable dispatch must still carry the same
    start/deadline pair, and the total window remains capped.
    """

    if (
        isinstance(attempt_started_at, bool)
        or not isinstance(attempt_started_at, int)
        or isinstance(attempt_hard_deadline_at, bool)
        or not isinstance(attempt_hard_deadline_at, int)
        or attempt_started_at <= 0
    ):
        return False
    duration = attempt_hard_deadline_at - attempt_started_at
    return (
        FORMAL_PROVIDER_ATTEMPT_HARD_DEADLINE_MS
        <= duration
        <= FORMAL_PROVIDER_ATTEMPT_MAX_CONTINUATION_MS
    )
