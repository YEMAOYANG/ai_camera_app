from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from core.database import DatabaseConnection
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)


# This is the sidecar transport budget, not a lifetime limit on the audit
# inventory.  The complete history remains authoritative at the Host gate;
# only the Provider-facing projection is bounded to this many hashes.
HISTORICAL_QUESTION_FINGERPRINT_LIMIT = 500


def historical_question_fingerprints(
    conn: DatabaseConnection,
    *,
    item: Mapping[str, object],
    attempt_started_at: int | None = None,
) -> list[str]:
    """Return the stable pre-attempt question inventory for one target."""

    cutoff = int(
        attempt_started_at
        if attempt_started_at is not None
        else item.get("content_attempt_started_at") or 0
    )
    grade_code = str(item.get("grade_code") or "")
    subject = str(item.get("subject") or "")
    node_code = str(item.get("skill_id") or "")
    if cutoff <= 0 or not grade_code or not subject or not node_code:
        raise ValueError(
            "historical question fingerprint authority is incomplete"
        )
    rows = conn.execute(
        """
        SELECT content_json
        FROM learning_courses
        WHERE grade_code = ? AND subject = ? AND node_code = ?
          AND generation_content_hash IS NOT NULL
          AND created_at <= ?
        ORDER BY created_at, id, version
        """,
        (grade_code, subject, node_code, cutoff),
    ).fetchall()
    fingerprints: set[str] = set()
    for course in rows:
        try:
            content = json.loads(str(course.get("content_json") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        questions = content.get("questions") if isinstance(content, Mapping) else None
        if not isinstance(questions, list):
            continue
        for question in questions:
            if not isinstance(question, Mapping):
                continue
            fingerprints.add(
                DynamicLearningCourseRepository.question_fingerprint(
                    grade_code=grade_code,
                    subject=subject,
                    node_code=node_code,
                    question=question,
                )
            )
    return sorted(fingerprints)


def provider_question_fingerprint_projection(
    *,
    authoritative_fingerprints: Sequence[str],
    required_fingerprints: Sequence[str],
    request_id: str,
    limit: int = HISTORICAL_QUESTION_FINGERPRINT_LIMIT,
) -> list[str]:
    """Project an unbounded Host inventory into the bounded sidecar contract.

    Fingerprints produced by prior variants in the same build (and by a
    rejected first attempt) are always retained.  When older history exceeds
    the remaining transport budget, rendezvous ranking rotates its coverage
    deterministically by generation request while keeping replay byte-stable.
    The complete inventory is still checked independently by the Host gate.
    """

    required = sorted(set(str(value) for value in required_fingerprints))
    authoritative = sorted(
        set(str(value) for value in authoritative_fingerprints)
        | set(required)
    )
    if limit <= 0 or len(required) > limit:
        raise ValueError("question fingerprint projection authority is invalid")
    if len(authoritative) <= limit:
        return authoritative
    required_set = set(required)
    ranked = sorted(
        (value for value in authoritative if value not in required_set),
        key=lambda value: (
            hashlib.sha256(
                f"{request_id}\0{value}".encode("utf-8")
            ).hexdigest(),
            value,
        ),
    )
    return sorted([*required, *ranked[: limit - len(required)]])


def historical_question_fingerprint_snapshots(
    conn: DatabaseConnection,
    *,
    item: Mapping[str, object],
    histories: Mapping[int, Mapping[str, object]],
) -> dict[int, list[str]]:
    snapshots: dict[int, list[str]] = {}
    current_attempt = int(item.get("attempt_count") or 0)
    current_started_at = int(item.get("content_attempt_started_at") or 0)
    for attempt in (1, 2):
        history = histories.get(attempt)
        dispatches = (
            history.get("dispatches")
            if isinstance(history, Mapping)
            else None
        )
        if not isinstance(dispatches, Sequence):
            raise ValueError("content attempt dispatch history is missing")
        starts = {
            int(dispatch["attempt_started_at"])
            for dispatch in dispatches
            if isinstance(dispatch, Mapping)
            and type(dispatch.get("attempt_started_at")) is int
        }
        valid_start_count = sum(
            isinstance(dispatch, Mapping)
            and type(dispatch.get("attempt_started_at")) is int
            for dispatch in dispatches
        )
        if len(starts) > 1 or valid_start_count != len(dispatches):
            raise ValueError(
                "content attempt fingerprint snapshot authority drift"
            )
        started_at = next(iter(starts), 0)
        if (
            started_at == 0
            and attempt == current_attempt
            and current_started_at > 0
        ):
            started_at = current_started_at
        snapshots[attempt] = (
            historical_question_fingerprints(
                conn,
                item=item,
                attempt_started_at=started_at,
            )
            if started_at > 0
            else []
        )
    return snapshots
