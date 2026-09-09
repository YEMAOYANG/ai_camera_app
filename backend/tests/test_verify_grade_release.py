from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import re
import unittest

from scripts.verify_grade_release import (
    FORMAL_PUBLICATION_CONTRACT_VERSION,
    REQUIRED_MIGRATIONS,
    REQUIRED_TABLES,
    VerificationInputError,
    verify_grade_release,
)


def _sha(payload) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _publication_rows() -> tuple[list[dict[str, object]], str]:
    rows = []
    aggregate_items = []
    provider_receipt_sha256 = _sha({"provider": "release-secret"})
    for ordinal in range(30):
        row = {
            "build_id": "build-secret",
            "build_item_id": f"item-secret-{ordinal:02d}",
            "runtime_classroom_id": f"runtime-secret-{ordinal:02d}",
            "course_id": f"course-secret-{ordinal:02d}",
            "course_version": "v1",
            "package_id": f"package-secret-{ordinal:02d}",
            "package_version": 1,
            "classroom_content_sha256": _sha({"classroom": ordinal}),
            "audio_receipt_sha256": _sha({"audio": ordinal}),
            "provider_receipt_sha256": provider_receipt_sha256,
            "provider_binding_receipt_sha256": _sha(
                {"providerBinding": ordinal}
            ),
        }
        item_payload = {
            "schemaVersion": FORMAL_PUBLICATION_CONTRACT_VERSION,
            "gradeCode": "primary_1",
            "buildId": row["build_id"],
            "releaseId": "release-secret",
            "targetFingerprint": "a" * 64,
            "buildItemId": row["build_item_id"],
            "runtimeClassroomId": row["runtime_classroom_id"],
            "course": {
                "id": row["course_id"],
                "version": row["course_version"],
            },
            "package": {
                "id": row["package_id"],
                "version": row["package_version"],
            },
            "classroomContentSha256": row["classroom_content_sha256"],
            "audioReceiptSha256": row["audio_receipt_sha256"],
            "providerReceiptSha256": row["provider_receipt_sha256"],
            "providerBindingReceiptSha256": row[
                "provider_binding_receipt_sha256"
            ],
        }
        row["publication_receipt_sha256"] = _sha(item_payload)
        rows.append(row)
        aggregate_items.append(
            {
                "buildItemId": row["build_item_id"],
                "receiptSha256": row["publication_receipt_sha256"],
            }
        )
    aggregate = {
        "schemaVersion": FORMAL_PUBLICATION_CONTRACT_VERSION,
        "gradeCode": "primary_1",
        "buildId": "build-secret",
        "releaseId": "release-secret",
        "targetFingerprint": "a" * 64,
        "items": aggregate_items,
    }
    return rows, _sha(aggregate)


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class _ReadOnlyConnection:
    def __init__(
        self,
        *,
        pointer_present: bool = True,
        contract_version: str = FORMAL_PUBLICATION_CONTRACT_VERSION,
        exact_item_count: int = 30,
        max_active_event_lag_ms: int = 2_000,
        history_superseded_at: int | None = None,
        exact_stream_count: int = 2,
        bound_session_count: int = 2,
        aggregate_receipt_exact: bool = True,
    ):
        self.pointer_present = pointer_present
        self.contract_version = contract_version
        self.exact_item_count = exact_item_count
        self.max_active_event_lag_ms = max_active_event_lag_ms
        self.history_superseded_at = history_superseded_at
        self.exact_stream_count = exact_stream_count
        self.bound_session_count = bound_session_count
        self.publication_rows, aggregate_hash = _publication_rows()
        self.aggregate_hash = (
            aggregate_hash if aggregate_receipt_exact else "b" * 64
        )
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        self.statements.append((normalized, tuple(params or ())))
        if "verify_grade_release:schema" in normalized:
            return _Cursor({"table_name": name} for name in REQUIRED_TABLES)
        if "verify_grade_release:migrations" in normalized:
            return _Cursor({"version": name} for name in REQUIRED_MIGRATIONS)
        if "verify_grade_release:pointer" in normalized:
            if not self.pointer_present:
                return _Cursor([])
            return _Cursor(
                [
                    {
                        "pointer_revision": 4,
                        "pointer_target_fingerprint": "a" * 64,
                        "pointer_contract_version": self.contract_version,
                        "pointer_release_id": "release-secret",
                        "pointer_history_id": "history-secret",
                        "pointer_activated_at": 1_000,
                        "history_grade_code": "primary_1",
                        "history_pointer_revision": 4,
                        "history_target_fingerprint": "a" * 64,
                        "history_contract_version": self.contract_version,
                        "history_release_id": "release-secret",
                        "history_id": "history-secret",
                        "history_activated_at": 1_000,
                        "history_activation_source": "formal_publication",
                        "history_publication_request_id": "request-secret",
                        "history_publication_receipt_hash": self.aggregate_hash,
                        "history_superseded_at": self.history_superseded_at,
                        "release_status": "published",
                        "release_quality_status": "ready",
                        "release_ready_item_count": 30,
                        "release_retired_at": None,
                    }
                ]
            )
        if "verify_grade_release:evidence" in normalized:
            return _Cursor(
                [
                    {
                        "item_count": 30,
                        "exact_item_count": self.exact_item_count,
                        "chinese_count": 12,
                        "math_count": 9,
                        "english_count": 9,
                    }
                ]
            )
        if "verify_grade_release:publication_receipts" in normalized:
            return _Cursor(self.publication_rows)
        if "verify_grade_release:event_lag" in normalized:
            return _Cursor(
                [
                    {
                        "bound_session_count": self.bound_session_count,
                        "stream_count": 2,
                        "exact_stream_count": self.exact_stream_count,
                        "active_stream_count": 1,
                        "completed_stream_count": 1,
                        "max_active_event_lag_ms": self.max_active_event_lag_ms,
                    }
                ]
            )
        if normalized == "SET TRANSACTION READ ONLY":
            return _Cursor([])
        raise AssertionError(f"unexpected verifier SQL: {normalized}")


class _ReadOnlyDatabase:
    def __init__(self, connection: _ReadOnlyConnection):
        self.connection = connection
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self.connection


class VerifyGradeReleaseTest(unittest.TestCase):
    def _verify(self, connection, *, phase="postflight", lag_ms=300_000):
        database = _ReadOnlyDatabase(connection)
        result = verify_grade_release(
            database,
            phase=phase,
            configured_grade_allowlist=["primary_1"],
            now_ms=500_000,
            max_event_lag_ms=lag_ms,
        )
        self.assertEqual(database.transaction_count, 1)
        return result

    def test_postflight_accepts_exact_release_and_executes_read_only_sql(self):
        connection = _ReadOnlyConnection()

        result = self._verify(connection)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["releaseItemCount"], 30)
        self.assertEqual(result["summary"]["maxActiveEventLagMs"], 2_000)
        self.assertEqual(connection.statements[0][0], "SET TRANSACTION READ ONLY")
        statements = "\n".join(sql for sql, _ in connection.statements)
        self.assertIn("$.formalEvidence.speechActionCount", statements)
        self.assertIn("audio.expected_segment_count =", statements)
        self.assertIsNone(
            re.search(
                r"\b(INSERT|UPDATE|DELETE|REPLACE|ALTER|DROP|CREATE|TRUNCATE)\b",
                statements,
                re.IGNORECASE,
            )
        )
        rendered = json.dumps(result, sort_keys=True)
        self.assertNotIn("release-secret", rendered)
        self.assertNotIn("history-secret", rendered)
        self.assertNotIn("request-secret", rendered)
        self.assertNotIn("a" * 64, rendered)
        self.assertNotIn("b" * 64, rendered)

    def test_postflight_fails_closed_when_one_item_lacks_exact_evidence(self):
        result = self._verify(_ReadOnlyConnection(exact_item_count=29))

        self.assertFalse(result["ok"])
        evidence = next(
            check for check in result["checks"] if check["name"] == "releaseEvidence"
        )
        self.assertFalse(evidence["ok"])

    def test_contract_drift_is_rejected(self):
        result = self._verify(
            _ReadOnlyConnection(contract_version="mira.learning.legacy.v1")
        )

        self.assertFalse(result["ok"])
        pointer = next(
            check for check in result["checks"] if check["name"] == "activePointer"
        )
        self.assertFalse(pointer["ok"])

    def test_pointer_aggregate_receipt_drift_is_rejected(self):
        result = self._verify(
            _ReadOnlyConnection(aggregate_receipt_exact=False)
        )

        self.assertFalse(result["ok"])

    def test_postflight_accepts_pointer_rollback_without_rewriting_history(self):
        result = self._verify(
            _ReadOnlyConnection(history_superseded_at=400_000)
        )

        self.assertTrue(result["ok"])

    def test_stale_active_event_stream_fails_postflight(self):
        result = self._verify(
            _ReadOnlyConnection(max_active_event_lag_ms=300_001),
            lag_ms=300_000,
        )

        self.assertFalse(result["ok"])
        event_lag = next(
            check for check in result["checks"] if check["name"] == "eventLag"
        )
        self.assertFalse(event_lag["ok"])

    def test_event_sequence_gap_fails_postflight(self):
        result = self._verify(_ReadOnlyConnection(exact_stream_count=1))

        self.assertFalse(result["ok"])
        event_check = next(
            check
            for check in result["checks"]
            if check["name"] == "eventConsistency"
        )
        self.assertFalse(event_check["ok"])

    def test_event_stream_without_formal_binding_fails_postflight(self):
        result = self._verify(_ReadOnlyConnection(bound_session_count=1))

        self.assertFalse(result["ok"])

    def test_preflight_allows_no_active_pointer_but_allowlist_is_exact(self):
        result = self._verify(
            _ReadOnlyConnection(pointer_present=False), phase="preflight"
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["summary"]["activePointerPresent"])

        with self.assertRaises(VerificationInputError):
            verify_grade_release(
                _ReadOnlyDatabase(_ReadOnlyConnection()),
                phase="preflight",
                configured_grade_allowlist=["primary_1", "primary_2"],
                now_ms=500_000,
                max_event_lag_ms=300_000,
            )


if __name__ == "__main__":
    unittest.main()
